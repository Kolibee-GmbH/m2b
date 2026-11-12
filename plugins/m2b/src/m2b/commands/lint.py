"""``lint scan / fix``: findings about the store for the lint step, and the two safe fixes."""

from __future__ import annotations

import argparse

from m2b import lint
from m2b.commands import Context
from m2b.commands.backends import configured_store, configured_tasks
from m2b.commands.output import print_json
from m2b.config.machine import load_machine_config
from m2b.config.profile import language_for_clients, load_profile
from m2b.config.store_settings import require_store_writable
from m2b.curate import report
from m2b.curate.model import CURATION_RUN_VARIABLE

STEP = "lint"


def lint_scan(arguments: argparse.Namespace, context: Context) -> int:
    """With ``--report`` every finding goes to the curation run; ``--json`` is what the model reads first."""
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    findings = lint.scan(store, configured_tasks(config, context.machine)).findings
    if arguments.report:
        token = context.environ.get(report.RUN_TOKEN_VARIABLE)
        if not token:
            raise report.NoRunError(f"lint scan --report needs a curation run; {report.RUN_TOKEN_VARIABLE} is not set")
        report.require_open_run(context.machine, token)
        for finding in findings:
            report.add_finding(context.machine, token, report.Finding(STEP, finding.kind, finding.text))
        print(f"{len(findings)} findings handed to the run")
        return 0
    if arguments.json:
        print_json(
            {
                "store": str(config.store.path),
                "language": language_for_clients(load_profile(store)),
                "curation_run": context.environ.get(CURATION_RUN_VARIABLE) == "1",
                "findings": [
                    {
                        "code": finding.code,
                        "kind": finding.kind,
                        "path": finding.path,
                        "text": finding.text,
                        "link": finding.link,
                        "candidates": list(finding.candidates),
                    }
                    for finding in findings
                ],
            }
        )
    else:
        for finding in findings:
            print(f"{finding.kind}: {finding.text}")
    return 1 if any(finding.kind == report.ACTION for finding in findings) else 0


def lint_fix(arguments: argparse.Namespace, context: Context) -> int:
    config = load_machine_config(context.machine)
    store = configured_store(config, context.machine)
    require_store_writable(store)
    removed = lint.fix(store, configured_tasks(config, context.machine))
    if arguments.json:
        print_json({"removed": removed})
    else:
        for relative in removed:
            print(f"removed {relative}")
    return 0
