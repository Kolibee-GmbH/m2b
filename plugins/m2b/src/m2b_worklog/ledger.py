"""The ledger: every worklog's time spans, keyed by its period, and two exports regenerated from it.

``ledger.json`` in ``state/addons/worklog/`` is the record; a period already in it is not added
again, which makes adding safe to repeat (B28), and a span that overlaps one of the same session
already in it is refused with the whole period (B87), so the same minutes are never booked twice
when a watermark was reset. A span is one block: ``start`` and ``end`` are its bounds, ``minutes``
the work inside it, so a gap within a block is never booked, and ``minutes_present`` the part of it
with the workspace in focus, the owner there (B86); a span written before that column has none.
``ledger.csv`` and
``ledger.xlsx`` are rebuilt from the whole ledger at every worklog and are not for editing: a
change there is gone at the next worklog. Booking columns are filled only for proposals; nothing
here writes into a timesheet anyone bills from, because a wrong booking ends up on an invoice.

The XLSX is a minimal workbook written with ``zipfile`` and plain XML, one sheet with inline
strings, and every ZIP entry carries the same fixed time, so the same ledger gives the same bytes.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from m2b_worklog.files import replace_file
from m2b_worklog.sources.inbox import is_evicted

LEDGER_VERSION = 1
LEDGER = "ledger.json"
# Where the ledger lives in the store, for the fetch command a message names.
RELATIVE_FOLDER = "state/addons/worklog"
CSV_EXPORT = "ledger.csv"
XLSX_EXPORT = "ledger.xlsx"
COLUMNS = (
    "period",
    "start",
    "end",
    "minutes",
    "minutes_present",
    "sphere",
    "billable",
    "topic",
    "customer",
    "project",
    "activity",
)
ZIP_TIME = (2000, 1, 1, 0, 0, 0)
# What opens a formula in Excel, LibreOffice and Google Sheets, a tab and a carriage return included.
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


class LedgerError(Exception):
    """The ledger cannot be read, so adding to it could lose what it holds."""


def read(folder: Path) -> dict[str, Any]:
    path = folder / LEDGER
    if not path.exists():
        return {"version": LEDGER_VERSION, "periods": {}}
    if is_evicted(path):
        raise LedgerError(f"{path} is not downloaded; m2b store fetch {RELATIVE_FOLDER}/{LEDGER} downloads it")
    try:
        ledger: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LedgerError(f"{path} cannot be read ({error}); fix it by hand, nothing was added") from error
    if not isinstance(ledger, dict) or not isinstance(ledger.get("periods"), dict):
        raise LedgerError(f"{path} is not a worklog ledger; fix it by hand, nothing was added")
    return ledger


def add(folder: Path, period: str, start: str, end: str, spans: Sequence[Mapping[str, Any]]) -> bool:
    """Adds the period's spans; False when the ledger holds the period already."""
    ledger = read(folder)
    if period in ledger["periods"]:
        return False
    refuse_overlap(ledger, start, end, spans)
    ledger["periods"][period] = {"start": start, "end": end, "spans": [dict(span) for span in spans]}
    folder.mkdir(parents=True, exist_ok=True)
    replace_file(folder / LEDGER, (json.dumps(ledger, ensure_ascii=False, indent=1) + "\n").encode())
    return True


def refuse_overlap(ledger: Mapping[str, Any], start: str, end: str, spans: Sequence[Mapping[str, Any]]) -> None:
    """Raises when the new period overlaps one the ledger holds; touching is fine.

    Periods follow each other from the watermark, so a new one that overlaps a held one means the
    watermark was reset. A span of the same session is named when there is one; the period is checked
    as well, because session keys can differ between runs (a workspace reopened under a new id).
    """
    held_spans = [span for period in ledger["periods"].values() for span in period["spans"]]
    for span in spans:
        for other in held_spans:
            if other.get("session") == span.get("session") and _overlap(span, other):
                _refuse(f"{other['session']} from {other['start']} to {other['end']}", span["start"], span["end"])
    for held in ledger["periods"].values():
        if _overlap({"start": start, "end": end}, held):
            _refuse(f"the period from {held['start']} to {held['end']}", start, end)


def _overlap(one: Mapping[str, Any], other: Mapping[str, Any]) -> bool:
    return _moment(one["start"]) < _moment(other["end"]) and _moment(other["start"]) < _moment(one["end"])


def _refuse(held: str, start: str, end: str) -> None:
    raise LedgerError(
        f"the ledger holds {held} already, and the new one from {start} to {end} overlaps it; nothing was added. "
        "The watermark was probably reset: m2b-worklog state shows the end of the last period in the ledger, "
        "which is where the watermark belongs"
    )


def _moment(text: Any) -> datetime.datetime:
    return datetime.datetime.fromisoformat(str(text))


def export(folder: Path) -> None:
    rows = _rows(read(folder))
    replace_file(folder / CSV_EXPORT, _csv(rows))
    replace_file(folder / XLSX_EXPORT, _xlsx(rows))


def _rows(ledger: Mapping[str, Any]) -> list[list[str]]:
    spans = [span for period in ledger["periods"].values() for span in period["spans"]]
    spans.sort(key=lambda span: (str(span["start"]), str(span["session"])))
    return [[_cell(span.get(column)) for column in COLUMNS] for span in spans]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _csv(rows: Sequence[Sequence[str]]) -> bytes:
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows([[_as_text(cell) for cell in row] for row in rows])
    return text.getvalue().encode("utf-8")


def _as_text(cell: str) -> str:
    """A cell a spreadsheet would read as a formula gets a leading apostrophe: topics come from a model.

    The XLSX needs none, its cells are written as text.
    """
    return f"'{cell}" if cell.startswith(FORMULA_STARTS) else cell


def _xlsx(rows: Sequence[Sequence[str]]) -> bytes:
    numbers = {COLUMNS.index("minutes"), COLUMNS.index("minutes_present")}
    sheet_rows = [_xlsx_row(1, COLUMNS)] + [_xlsx_row(index + 2, row, numbers) for index, row in enumerate(rows)]
    parts = {
        "[Content_Types].xml": (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Worklog" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>'
        ),
        "xl/worksheets/sheet1.xml": (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + "".join(sheet_rows)
            + "</sheetData></worksheet>"
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            entry = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body)
    return buffer.getvalue()


def _xlsx_row(number: int, cells: Sequence[str], numbers: frozenset[int] | set[int] = frozenset()) -> str:
    written = []
    for index, value in enumerate(cells):
        reference = f"{_column(index)}{number}"
        if index in numbers and value.isdigit():
            written.append(f'<c r="{reference}"><v>{value}</v></c>')
        elif value:
            written.append(f'<c r="{reference}" t="inlineStr"><is><t>{_xml_text(value)}</t></is></c>')
    return f'<row r="{number}">' + "".join(written) + "</row>"


def _column(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(ord("A") + rest) + name
    return name


def _xml_text(value: str) -> str:
    """Escaped, with the control characters XML 1.0 cannot hold left out."""
    kept = "".join(c for c in value if c in "\t\n\r" or ord(c) >= 0x20)
    return escape(kept)
