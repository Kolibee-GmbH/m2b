"""Every text of one session a quote can stand in, read from the session's transcript.

A session can hand in a proposal for the memory with the words it stands on. This module reads the
one transcript of that session and gives each text the words may be found in, a place, with where
it is from: what the person typed, what they pasted, what a tool returned, what Claude answered.
The reading of a period's sessions (``sessions.read_sessions``) takes prompts only and is not
changed by anything here.

A place is one text, its white space collapsed. Nothing joins two texts: a quote that begins in
one and ends in the next stands nowhere, so no place holds words side by side that did not stand
so in the session.

What the person typed is told from everything else by where it stands, not by reading marks that
other text can imitate. Of a prompt, typed is what stands before the first opening of a tag,
whatever its name: Claude Code marks a paste, a block of its own, the output of a shell line and
what an editor adds to a prompt with tags, and their names change with its versions. Everything
behind that opening is pasted, also a sentence the person typed behind a paste: pasted text can
hold any mark it likes, a paste's closing tag among them, and none of them moves a word of it in
front of the first. A prompt of several text parts is pasted whole, since nothing says which part
was typed. The reading of a period tells the two apart mark by mark and shows a model both; here
a label is at stake that says whose words they are. One thing no reader can tell: a short text
the terminal pasted as if it were typed carries no mark at all and reads as typed.

What makes the texts of a tool's result:

- Each text part of a result is read for itself; a connector returns two mails as two parts.
- A block Claude Code wrote into a result is no place, and it parts the text: what stood before
  it and what stood behind it are two places. A document that quotes such a block cannot make
  words meet that way.
- ``Read`` numbers the lines of a file; the numbers go, so a quote across two lines stands.
- A text that is JSON gives one place per string in it, decoded. A quote copied as it reads
  stands, and JSON syntax is no part of any quote. JSON that was cut gives its whole strings.
- A long result Claude Code moved out of the transcript is the note it left there; the first part
  of the output in that note is the result, as much as the model saw.

Not a place: the input of a call, a subagent's conversation, a record Claude Code flags as its
own (a skill's text, the summary after a context cut, an answer it made up for an error), what
the model thought, and a prompt without Claude Code's mark of a human sender, which is what a
headless run was started with. What a subagent reported back is a place of Claude's, not of a
tool: a model worded it. Unlike the reading of a period, a headless transcript is not left out
whole: the caller asks about the one session it was called from.

A tool's place carries the tool's name and the texts of the call's input, so a caller can tell a
result that only gives back what the agent wrote into that call (``echo``). A place also carries
the end of the text that stood right before it in its record, where a mark, a block or the
syntax of JSON parted the two, and for a JSON value the key it stands under: a credential is
known by the name before it.

Where the session worked is told apart from its places, for a caller that must leave some work
out: every working folder a record names, the session's subagents' among them, and every path a
call names plainly. The folders are Claude Code's own account. The paths are a guard against a
session that reads a file of other work by accident and no more: the fields a tool takes a path
in, and the words of a shell command that hold a slash. A path in a variable, built by a
program, behind ``find``, without a slash in a folder the command changed to, or read by a tool
of a connector is not seen.

Nothing here is redacted; a caller that keeps a quote redacts it.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import os.path
import re
import shlex
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m2b.claude_code import PROMPT_BLOCK_TAGS
from m2b.folders_left_out import LONGEST_PATH
from m2b.glean import AGENT, PASTED, TOOL, TYPED
from m2b.sessions import NOT_THE_MAIN_CONVERSATION, prompt_of_a_person, time_of

# How far a text is looked at, as the reader of a period looks at a paste. Claude Code moves a
# longer result out of the transcript, so this cuts little a session holds and bounds what a
# damaged or foreign file costs.
LOOKED_AT = 64 * 1024
READ_TOOL = "Read"
# The tools through which Claude answers itself: what comes back was worded by a model.
SUBAGENT_TOOLS = ("Agent", "Task")
# How much of the text right before a place is kept with it, for a caller's redaction: the name
# of a credential typed before a paste that begins with its value, or written before a block.
BEFORE_LENGTH = 200
# No session of a person names more paths.
PATHS_KEPT = 5000

_SESSION_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_SUBAGENTS = "subagents"
# A line as ``Read`` gives it: the line's number, a tab, the line.
_NUMBERED_LINE = re.compile(r"^[ \t]*\d+\t", re.M)
# The opening tag of a block Claude Code writes. Its attributes are short, and the bound keeps a
# text full of openings without an end from costing its length each.
_BLOCK_OPENS = re.compile(r"<(" + "|".join(PROMPT_BLOCK_TAGS) + r")\b[^>]{0,200}>")
# Where a prompt stops being what the person typed: the opening of a tag of any name.
_NOBODY_TYPED_FROM_HERE = re.compile(r"<[A-Za-z_]")
_PASTE_TAG = re.compile(r"</?pasted_content\b[^>]{0,200}>")
_MOVED_OUT = "<persisted-output>"
_MOVED_OUT_ENDS = "</persisted-output>"
# The line of the note behind which the first part of the output stands.
_FIRST_PART_FOLLOWS = re.compile(r"^Preview \([^)\n]*\):[ \t]*\n", re.M)
_LOOKS_LIKE_JSON = re.compile(r"\s*[\[{]\s*[\"\[{]")
# A string as JSON writes one. The last may be cut: this takes it in one pass, and no reader of
# JSON accepts it, so it gives nothing.
_STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*(?:"|\Z)')
# The fields a tool takes one path in, those that take several, the one a pattern of file names
# is in and the one a shell command is in.
_PATH_FIELDS = ("file_path", "path", "notebook_path", "directory", "cwd")
_PATHS_FIELDS = ("paths",)
_PATTERN_FIELD = "pattern"
_COMMAND_FIELD = "command"
_PATTERN_STARTS = re.compile(r"[*?\[{]")
# What a shell puts between two commands or between a command and a file it reads or writes.
_SHELL_OPERATORS = re.compile(r"[;&|<>()]+")
_CHANGES_FOLDER = ("cd", "pushd")
_HOME_VARIABLE = re.compile(r"\$HOME\b|\$\{HOME\}")
# The working folder, a path field or a command as a line names it that could not be read as a record.
_NAMED_IN_A_LINE = re.compile(
    r'"(cwd|' + "|".join((*_PATH_FIELDS[:-1], _COMMAND_FIELD)) + r')"\s*:\s*("(?:[^"\\]|\\.)*")'
)


@dataclass(frozen=True)
class Place:
    """One text of a session and where it is from."""

    source: str
    text: str
    time: datetime.datetime
    # For a tool's result: the tool, and every text of the input of the call it answers.
    tool: str | None = None
    call_input: tuple[str, ...] = ()
    # The end of the text that stood right before this one in its record, where something parted
    # the two; for a value of JSON, the key it stands under.
    before: str = ""


@dataclass(frozen=True)
class CallInput:
    """The texts of the input of one call, and how many places stood before it in the session."""

    places_before: int
    texts: tuple[str, ...]


@dataclass(frozen=True)
class SessionPlaces:
    places: tuple[Place, ...]
    # Every working folder a record names, in the order they first appear, the subagents' behind
    # the session's own; the first is where the session started. A line that cannot be read
    # still gives its folder.
    folders: tuple[str, ...]
    # Every path a call names plainly, the subagents' calls among them, in the order they first
    # appear. A path that is not absolute stands behind the working folder of its record.
    paths: tuple[str, ...]
    # Whether ``paths`` is not all of them: the session named more than are kept, one longer than a
    # file system opens, a command longer than is looked at, or a subagent's transcript could not
    # be read.
    paths_incomplete: bool = False
    # What Claude wrote into its calls, in their order, a subagent's task among them: a caller can
    # tell a result that only gives back what was written before it.
    inputs: tuple[CallInput, ...] = ()


@dataclass(frozen=True)
class _Call:
    tool: str
    input_texts: tuple[str, ...]


def is_session_id(text: str) -> bool:
    """Whether the text has the form of a session's id: only then may it be part of a file's name."""
    return _SESSION_ID.fullmatch(text) is not None


def transcripts_of(transcripts_folder: Path, session_id: str) -> list[Path]:
    """The transcripts with this session's id, in the folder of every project; none for a text that is no id."""
    if not is_session_id(session_id) or not transcripts_folder.is_dir():
        return []
    return sorted(path for path in transcripts_folder.glob(f"*/{session_id}.jsonl") if path.is_file())


def read(transcript: Path) -> SessionPlaces:
    """The places of the session ``transcript`` holds; an ``OSError`` when the file cannot be read.

    The transcripts of the session's subagents, which Claude Code keeps in a folder beside it,
    are read for where they worked; one of them that cannot be read leaves the paths incomplete.
    """
    places: list[Place] = []
    inputs: list[CallInput] = []
    worked = _Worked()
    calls: dict[str, _Call] = {}
    # The end of the answer block before, while answer follows answer: Claude Code writes a block a record.
    answered = ""
    with transcript.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            record = worked.note(line)
            if record is None:
                continue
            moment = time_of(record)
            if moment is None or any(record.get(flag) for flag in NOT_THE_MAIN_CONVERSATION):
                continue
            if record.get("type") == "assistant" and not record.get("isApiErrorMessage"):
                known = len(calls)
                for place in _of_claude(record, moment, calls):
                    places.append(dataclasses.replace(place, before=answered))
                    answered = place.text[-BEFORE_LENGTH:]
                inputs.extend(CallInput(len(places), call.input_texts) for call in list(calls.values())[known:])
            elif record.get("type") == "user":
                said = [*_of_the_person(record, moment), *_of_tools(record, moment, calls)]
                places.extend(said)
                answered = "" if said else answered
    # Claude Code keeps some of them in folders of their own below this one.
    for subagent in sorted((transcript.parent / transcript.stem / _SUBAGENTS).rglob("*.jsonl")):
        try:
            with subagent.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    worked.note(line)
        except OSError:
            worked.paths_incomplete = True
    return SessionPlaces(
        tuple(places), tuple(worked.folders), tuple(worked.paths), worked.paths_incomplete, tuple(inputs)
    )


class _Worked:
    """Where a session worked, gathered line by line: its working folders and the paths its calls name."""

    def __init__(self) -> None:
        self.folders: dict[str, None] = {}
        self.paths: dict[str, None] = {}
        self.paths_incomplete = False

    def note(self, line: str) -> dict[str, Any] | None:
        """Notes what the line says of where the session worked; the record, or None for a line that is none."""
        try:
            record: Any = json.loads(line)
        # A line nested deeper than this Python reads is passed over like one that is no JSON.
        except (ValueError, RecursionError):
            self._note_unread(line)
            return None
        if not isinstance(record, dict):
            return None
        folder = record["cwd"] if isinstance(record.get("cwd"), str) else ""
        if folder:
            self.folders.setdefault(folder)
        if record.get("type") == "assistant":
            content = _content_of(record)
            for part in content if isinstance(content, list) else []:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    self._keep_paths_of(part.get("input"), folder)
        return record

    def _note_unread(self, line: str) -> None:
        """Of a line that could not be read, the folder and the path fields it names, by their form."""
        named: list[tuple[str, str]] = []
        for field, written in _NAMED_IN_A_LINE.findall(line):
            try:
                value = json.loads(written)
            except ValueError:
                continue
            if value.strip():
                named.append((field, value.strip()))
        folder = next((value for field, value in named if field == "cwd"), "")
        if folder:
            self.folders.setdefault(folder)
        for field, value in named:
            if field != "cwd":
                self._keep_paths_of({field: value}, folder)

    def _keep_paths_of(self, given: object, folder: str) -> None:
        command = given.get(_COMMAND_FIELD) if isinstance(given, dict) else None
        if isinstance(command, str) and len(command) > LOOKED_AT:
            self.paths_incomplete = True
        for path in _paths_named_in(given, folder):
            if path in self.paths:
                continue
            if len(path) > LONGEST_PATH or len(self.paths) >= PATHS_KEPT:
                self.paths_incomplete = True
                continue
            self.paths[path] = None


def _of_the_person(record: Mapping[str, Any], moment: datetime.datetime) -> Iterator[Place]:
    """What the person typed, up to the first mark of something nobody typed, and what stands behind it."""
    parts = prompt_of_a_person(record)
    if not parts:
        return
    typed, behind = "", [part[:LOOKED_AT] for part in parts]
    if len(parts) == 1:
        prompt = behind[0]
        mark = _NOBODY_TYPED_FROM_HERE.search(prompt)
        typed = _one_text(prompt if mark is None else prompt[: mark.start()])
        behind = [] if mark is None else [prompt[mark.start() :]]
    if typed:
        yield Place(TYPED, typed, moment)
    before = typed[-BEFORE_LENGTH:]
    for part in behind:
        for piece in _apart_from_blocks(part):
            for stretch in map(_one_text, _PASTE_TAG.split(piece)):
                if stretch:
                    yield Place(PASTED, stretch, moment, before=before)
                    before = stretch[-BEFORE_LENGTH:]


def _of_claude(record: Mapping[str, Any], moment: datetime.datetime, calls: dict[str, _Call]) -> Iterator[Place]:
    """What Claude answered in this record; the calls it made are noted for the results that follow."""
    content = _content_of(record)
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    for part in content if isinstance(content, list) else []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            text = _one_text(part["text"])
            if text:
                yield Place(AGENT, text, moment)
        elif part.get("type") == "tool_use" and isinstance(part.get("id"), str) and isinstance(part.get("name"), str):
            given = map(_one_text, _strings_in(part.get("input")))
            calls[part["id"]] = _Call(part["name"], tuple(text for text in given if text))


def _of_tools(record: Mapping[str, Any], moment: datetime.datetime, calls: Mapping[str, _Call]) -> Iterator[Place]:
    """What tools returned in this record; a result whose call is not known is no place."""
    content = _content_of(record)
    for part in content if isinstance(content, list) else []:
        if not isinstance(part, dict) or part.get("type") != "tool_result":
            continue
        answered = part.get("tool_use_id")
        call = calls.get(answered) if isinstance(answered, str) else None
        if call is None:
            continue
        before = ""
        for returned in _text_parts(part.get("content")):
            texts, before = _texts_of_a_result(returned, call.tool, before)
            for text, stood_before in texts:
                if call.tool in SUBAGENT_TOOLS:
                    yield Place(AGENT, text, moment, before=stood_before)
                else:
                    yield Place(TOOL, text, moment, call.tool, call.input_texts, stood_before)


def _content_of(record: Mapping[str, Any]) -> object:
    message = record.get("message")
    return message.get("content") if isinstance(message, dict) else None


def _text_parts(content: object) -> list[str]:
    """The texts a result holds: the text itself, or each of its text parts."""
    if isinstance(content, str):
        return [content]
    parts = content if isinstance(content, list) else []
    texts = [part.get("text") for part in parts if isinstance(part, dict) and part.get("type") == "text"]
    return [text for text in texts if isinstance(text, str)]


def _texts_of_a_result(returned: str, tool: str, before: str) -> tuple[list[tuple[str, str]], str]:
    """The texts of one text part of a result, each with what stood right before it, and the part's end.

    ``before`` is the end of the text part before this one.
    """
    returned = _first_part_of_moved_out(returned[:LOOKED_AT])
    if tool == READ_TOOL:
        returned = _NUMBERED_LINE.sub("", returned)
    texts: list[tuple[str, str]] = []
    for piece in _apart_from_blocks(returned):
        strings = _strings_of_json(piece)
        if strings is None:
            texts.append((_one_text(piece), before))
        else:
            texts.extend((_one_text(string), _one_text(name)[-BEFORE_LENGTH:]) for name, string in strings)
        before = _one_text(piece)[-BEFORE_LENGTH:]
    return [(text, stood_before) for text, stood_before in texts if text], before


def _first_part_of_moved_out(returned: str) -> str:
    """Of the note Claude Code leaves for a result it moved out, the first part of the output; any other text whole."""
    if not returned.lstrip().startswith(_MOVED_OUT):
        return returned
    follows = _FIRST_PART_FOLLOWS.search(returned)
    if follows is None:
        return ""
    return returned[follows.end() :].rsplit(_MOVED_OUT_ENDS, 1)[0]


def _apart_from_blocks(text: str) -> list[str]:
    """The pieces of ``text`` between the blocks Claude Code wrote into it, in one pass.

    A block without its end is text. Once a tag has no end behind one opening, it has none behind
    a later one, so each tag is looked for in vain once.
    """
    pieces = []
    piece_from = position = 0
    never_ends: set[str] = set()
    while True:
        opening = _BLOCK_OPENS.search(text, position)
        if opening is None:
            break
        tag = opening.group(1)
        position = opening.end()
        if tag in never_ends:
            continue
        closing = f"</{tag}>"
        end = text.find(closing, position)
        if end < 0:
            never_ends.add(tag)
            continue
        pieces.append(text[piece_from : opening.start()])
        piece_from = position = end + len(closing)
    pieces.append(text[piece_from:])
    return pieces


def _strings_of_json(text: str) -> list[tuple[str, str]] | None:
    """Every string in a text that is a JSON object or list, decoded, with what names it.

    None for any other text. What names a string is written as the text before it: the keys on
    the way to it and the string before it in the same object or list, then a colon. JSON that
    does not read whole, cut by a length or by a note's first part, gives the strings that are
    whole in it, a key among them, each named by the string before it.
    """
    if _LOOKS_LIKE_JSON.match(text) is None:
        return None
    try:
        value, end = json.JSONDecoder().raw_decode(text.lstrip())
    except (ValueError, RecursionError):
        whole = list(_whole_strings_in(text))
        return [(f"{name}: " if name else "", string) for name, string in zip(["", *whole], whole)]
    named = list(_named_strings_in(value))
    # What stands behind the JSON is a text of its own, behind the last string.
    return [*named, (named[-1][1] if named else "", text.lstrip()[end:])]


def _whole_strings_in(text: str) -> Iterator[str]:
    for written in _STRING_LITERAL.findall(text):
        try:
            string = json.loads(written)
        except ValueError:
            continue
        if isinstance(string, str):
            yield string


def _named_strings_in(value: object) -> Iterator[tuple[str, str]]:
    """The strings a JSON value holds as values, each with the text that names it; a key is no value.

    A credential is named by a key above it (``{"password": {"value": ...}}``) or by the string
    beside it (``{"name": "DB_PASSWORD", "value": ...}``), so both stand in the name.
    """
    waiting: list[tuple[str, object]] = [("", value)]
    while waiting:
        name, inner = waiting.pop()
        if isinstance(inner, str):
            yield f"{name}: " if name else "", inner
            continue
        below: list[tuple[str, object]] = []
        beside = ""
        items = inner.items() if isinstance(inner, dict) else enumerate(inner) if isinstance(inner, list) else ()
        for key, child in items:
            key_name = key if isinstance(key, str) else ""
            below.append((" ".join(part for part in (name, beside, key_name) if part)[-BEFORE_LENGTH:], child))
            if isinstance(child, str):
                beside = child[:BEFORE_LENGTH]
        waiting.extend(reversed(below))


def _strings_in(value: object) -> Iterator[str]:
    """The strings a JSON value holds as values, at any depth; a key is no value."""
    waiting = [value]
    while waiting:
        inner = waiting.pop()
        if isinstance(inner, str):
            yield inner
        elif isinstance(inner, dict):
            waiting.extend(reversed(list(inner.values())))
        elif isinstance(inner, list):
            waiting.extend(reversed(inner))


def _paths_named_in(given: object, folder: str) -> Iterator[str]:
    """The paths the input of a call names plainly: its path fields, and the paths in its shell command."""
    fields = given if isinstance(given, dict) else {}
    for name in _PATH_FIELDS:
        if isinstance(fields.get(name), str) and fields[name].strip():
            yield _behind_the_folder(fields[name].strip(), folder)
    for name in _PATHS_FIELDS:
        for path in fields[name] if isinstance(fields.get(name), list) else []:
            if isinstance(path, str) and path.strip():
                yield _behind_the_folder(path.strip(), folder)
    pattern = fields.get(_PATTERN_FIELD)
    # A pattern of file names that starts at the root or a home folder; any other may be a search's.
    if isinstance(pattern, str) and pattern.startswith(("/", "~")):
        yield _up_to_a_pattern(pattern)
    if isinstance(fields.get(_COMMAND_FIELD), str):
        yield from _paths_in_a_command(fields[_COMMAND_FIELD][:LOOKED_AT], folder)


def _paths_in_a_command(command: str, folder: str) -> Iterator[str]:
    """The words of a shell command that hold a slash, the home folder, and the folder it changes to.

    Quotes and escapes are read as a shell reads them, the home folder's variable as the home
    folder, and a pattern up to the folder its first pattern character stands in. A word that is
    no path costs nothing: it stands behind the working folder, where the session works anyway.
    """
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    changes_folder = False
    for written in words:
        for part in _SHELL_OPERATORS.split(_HOME_VARIABLE.sub("~", written)):
            word = _without_what_stands_before_the_path(part)
            names_a_path = word == "~" or ("/" in word and "://" not in word)
            if changes_folder and word and not word.startswith("-"):
                names_a_path = True
            changes_folder = word in _CHANGES_FOLDER
            if names_a_path and any(character.isalnum() or character == "~" for character in word):
                yield _behind_the_folder(_up_to_a_pattern(word), folder)


def _without_what_stands_before_the_path(word: str) -> str:
    """A word of a command without the name a value is given to and without the option a path is glued to."""
    if "/" not in word:
        return word
    before_the_slash = word.split("/", 1)[0]
    if "=" in before_the_slash:
        return word.split("=", 1)[1]
    return word[word.index("/") :] if word.startswith("-") else word


def _up_to_a_pattern(path: str) -> str:
    """``path`` whole, or the folder its first pattern character stands in."""
    pattern = _PATTERN_STARTS.search(path)
    return path if pattern is None else path[: pattern.start()].rsplit("/", 1)[0] or "/"


def _behind_the_folder(path: str, folder: str) -> str:
    """``path`` as written when it starts at the root or a home folder, else behind the working folder.

    Nothing is worked out of it here: where ``..`` leads depends on the links on the way.
    """
    if path.startswith(("/", "~")) or not folder:
        return path
    return os.path.join(folder, path)


def _one_text(text: str) -> str:
    """The text as a place holds it: as far as it is looked at, whole characters, white space collapsed."""
    return " ".join(text[:LOOKED_AT].encode("utf-8", errors="replace").decode("utf-8").split())
