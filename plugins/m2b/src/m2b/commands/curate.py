"""``curate`` and its subcommands: the run itself, ``take-over``, a fenced model step and its reports."""

from __future__ import annotations

import argparse
import sys

from m2b import launcher
from m2b.commands import Context, ProblemError
from m2b.config.machine import load_machine_config
from m2b.curate import model, report, runner
from m2b.curate.detach import start_detached
from m2b.curate.take_over import take_over
from m2b.run_record import FAILED


def curate_run(arguments: argparse.Namespace, context: Context) -> int:
    """One run, or with ``--detach`` one started in the background; only a failed run exits 1."""
    if arguments.detach:
        start = start_detached(
            context.machine,
            context.environ,
            arguments.force,
            runner.now(),
            arguments.refresh_all,
            arguments.sort_facts,
        )
        print(start.message)
        return 0
    outcome = runner.curate(
        context.machine,
        context.environ,
        force=arguments.force,
        refresh_all=arguments.refresh_all,
        sort_facts=arguments.sort_facts,
    )
    if outcome.state == FAILED:
        print(f"the curation run failed: {outcome.message}. The review task names what to look at.")
        return 1
    print(outcome.message)
    return 0


def curate_take_over(arguments: argparse.Namespace, context: Context) -> int:
    result = take_over(context.machine, runner.now())
    if result.previous is None:
        print(f"this machine ({result.machine_id}) curates the store already")
        return 0
    print(f"this machine ({result.machine_id}) curates the store now; {result.previous} stops at its next run.")
    if result.record_problem:
        print(
            f"{result.record_problem}; the add-ons that were on at {result.previous} are not known, "
            f"so check there with m2b addons list"
        )
    if result.addons:
        print("These add-ons were on in the last run; set each up on this machine in Claude Code:")
        for name in result.addons:
            print(f"- /m2b:{name}-setup")
    return 0


def curate_model(arguments: argparse.Namespace, context: Context) -> int:
    """Runs one model step; inside a run its findings go to the run, alone they are printed."""
    config = load_machine_config(context.machine)
    plugin_dirs = {launcher.CORE_PLUGIN: launcher.PLUGIN_ROOT}
    given_token = context.environ.get(report.RUN_TOKEN_VARIABLE)
    if given_token:
        report.require_open_run(context.machine, given_token)
    token = given_token or report.open_run(context.machine)
    try:
        run = model.model_step(
            config, context.machine, context.environ, arguments.skill, arguments.allow, token, plugin_dirs
        )
        if not given_token:
            for finding in report.read_findings(context.machine, token):
                print(f"{finding.kind}: {finding.step}: {finding.text}")
    finally:
        if not given_token:
            report.close_run(context.machine, token)
    if run.error:
        raise ProblemError(f"{arguments.skill} failed: {run.error}")
    if run.denials:
        raise ProblemError(f"{arguments.skill} was denied {len(run.denials)} tool call(s) outside its rules")
    print(f"{arguments.skill}: done")
    return 0


def curate_report(arguments: argparse.Namespace, context: Context) -> int:
    token = context.environ.get(report.RUN_TOKEN_VARIABLE)
    if not token:
        raise report.NoRunError(
            f"only a model step of a curation run can report; {report.RUN_TOKEN_VARIABLE} is not set"
        )
    text = sys.stdin.read() if arguments.text == "-" else arguments.text
    report.add_finding(context.machine, token, report.Finding(arguments.step, arguments.kind, text))
    return 0
