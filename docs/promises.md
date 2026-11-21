# Promises

What m2b promises in its [README](../README.md), and the cases that prove each promise before a
release. `scripts/promises` reads the table below, runs every case and says per promise whether it
holds. A case checks the outcome you would see, from what you say to what a later session does;
the steps in between are checked by the unit tests, the stub scenarios and the evals, at the level
that shows each best ([Contributing](../CONTRIBUTING.md#promises)).

| # | Promise | Against Claude Code alone | Cases | Checked in part by |
|---|---|---|---|---|
| 1 | Say it once, every project knows it | compared | `E22-recall-across-projects` | `recall` |
| 2 | A sentence becomes a task | not compared | open | `E26-tick-a-task` |
| 3 | Facts with an end date are rewritten | not compared | open | `E16-expiring-fact` |
| 4 | Your words stay, every fact points to them | not compared | open | `details` |
| 5 | A correction you keep you do not repeat | compared | open | `correction` |
| 6 | A project knows where it lies | compared | open | `E33-project-known` |
| 7 | Nothing from another project, nothing filed without you | not compared | `no-leak` / `no-leak-de` / `no-leak-plain`, `propose-person` / `propose-person-de` / `propose-person-plain`, `propose-planted` / `propose-planted-de` / `propose-planted-plain` | `topic` |
| 8 | The start stays small | not compared | open | |

## When a promise holds

Every case runs three times with m2b, each time from a fresh start: its own store, its own Claude
Code folder, nothing left from the run before. A case holds when all three runs pass. A case that
passes once or twice is unsteady, a defect of the product or of the case, and is fixed before a
release; it is never waived.

Where the table says **compared**, the promise is something m2b adds to Claude Code, and the same
case also runs three times against Claude Code alone: no m2b, Claude Code's own memory on, no rule
written by hand. It may pass there at most once. A case that passes there more often shows nothing
about m2b, and the promise counts as having no difference: it is narrowed or leaves the README
instead of being claimed. A promise that is **not compared** guards against harm, or names
something Claude Code does not do at all; only the runs with m2b count.

A run against Claude Code alone counts only when it was a fair try. A case marks the step that shows
it, its control: for a fact told in one project, a session in that same project has to know it, which
shows that Claude Code kept it. When the control fails, or a step before it, the run shows nothing,
and so does a run the command never started because its time ran out. A case with such a run is
incomplete and does not hold.

**Three wordings.** The three runs of a case say what the owner says in three wordings, at least one
of them in German, so that a promise never rests on one lucky sentence. A scenario holds its
wordings in its `model.json`; an eval case holds one prompt, so a case of evals names three of them,
one per wording, joined by ` / `: the case of the suite in `plugins/m2b/evals/` and two rewordings
of it in `plugins/m2b/evals-wordings/`, which start as it does and check the same. A case with one
wording does not hold.

A promise holds when it has a case and every case holds. A promise without a case is open, and an
open promise does not hold either.

## Reading the report

`scripts/promises` prints one line per promise, held or why not, and under it each case with its
runs: `✓` for a run that passed, `✗` for one that did not, first with m2b and, where compared,
without. For a run that did not pass it gives what broke. The report ends with the Claude Code
version, the models the sessions answered with and the m2b commit it ran on. An account the runs
cannot use stops the command before the first run and is reported as that, never as a broken
promise.
