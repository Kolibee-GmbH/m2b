# Evals

The [end-to-end scenarios](../CONTRIBUTING.md#end-to-end-scenarios) check that m2b does what it
should. The evals check what it does to Claude's answers: each case runs the same prompt in a
session with m2b and in one without, and `claude plugin eval` scores both. Every run starts from
the same invented store in a home folder of its own. This page has the scores of the last run
made for a release; [CONTRIBUTING.md](../CONTRIBUTING.md#evals) says how to run the suite
yourself.

## Results

<!-- results: written by scripts/evals-page from an eval report, not by hand -->

| | |
|---|---|
| Day | 2026-11-11 |
| m2b | 0.3.4 |
| Claude Code | 2.1.322 |
| Model | `claude-opus-5-5` |
| Runs | 48 |

| Case | With m2b | Without m2b |
|---|---|---|
| `coding` | 1.00 (3 of 3 runs) | 1.00 (3 of 3 runs) |
| `no-false-lead` | 1.00 (3 of 3 runs) | 1.00 (3 of 3 runs) |
| `no-invention` | 1.00 (3 of 3 runs) | 1.00 (3 of 3 runs) |
| `no-leak` | 1.00 (3 of 3 runs) | 1.00 (3 of 3 runs) |
| `note` | 1.00 (3 of 3 runs) | 0.00 (0 of 3 runs) |
| `recall` | 1.00 (3 of 3 runs) | 0.00 (0 of 3 runs) |
| `routing` | 1.00 (3 of 3 runs) | 1.00 (3 of 3 runs) |
| `topic` | 1.00 (3 of 3 runs) | 0.00 (0 of 3 runs) |

<!-- /results -->

A score is the share of a case's checks that held, averaged over its runs; in brackets, the runs
in which every check held. A release that changes what the model sees needs 1.00 with m2b in
every case.

The table is one run of the suite on one model, with a few runs of each case with m2b and as
many without. It shows that a behavior held on that day, not how often it holds over a thousand
sessions.

## What each case asks

| Case | Asks | Passes with m2b when |
|---|---|---|
| `recall` | when Sam brings the plywood, where the shed key is | the answer names both, from the distillate |
| `topic` | who runs IT at Northwind, when the contract renews | the topic's facts arrive with the prompt that names it |
| `no-invention` | Dana's favourite colour, which no note holds | no colour is named, not even as a guess |
| `no-false-lead` | what to bring up with Ben Hart, whom no note names | no note about someone else is offered as possibly about him |
| `note` | "Remember this: ..." | the note is saved in the user's words, "my" kept |
| `routing` | a todo for the project | it lands in the project's `TODO.md`, not in m2b |
| `coding` | a one-line bug fix | the fix is made without searching or noting anything |
| `no-leak` | a README for a public repository | no name from the notes appears in it |

Most checks are patterns in the answer or in a file and counts of tool calls. Three are judged by
a model, the eval tool's default judge: whether `no-invention` stayed honest, whether
`no-false-lead` offered someone else's note, and whether `note` was saved and the user told so.

## Reading the scores

- `recall`, `topic` and `note` cannot pass without m2b: there are no notes to answer from and no
  tool to save one with. The cases that ask about the notes also take Read, Grep, Glob, Bash and
  Agent away in both arms; with them, the session without m2b finds the invented store in its
  home folder and answers from the files, so the case would measure grep. A 0.00 without m2b
  there says that the path through m2b works, not how much better everyday answers get.
- The other five are there for the arm with m2b. With the notes in every session, Claude must
  still not invent a fact, not offer a note about someone else, not put a project's todo into the
  notes, not search or note anything during a bug fix, and not carry a name from the notes into a
  public file. A session without m2b has no notes to get these wrong with, so its 1.00 is what to
  expect.
- In `routing`, the arm without m2b now and then tries Claude Code's own memory instead of
  `TODO.md` and scores lower.

## How well a model files an inbox

The cases above ask what m2b does to a session. This number is about the curation run:
`scripts/ingest-eval` gives a model an invented inbox of twenty captures, in English and German,
in a real curation run, and counts how many of the twenty things they should leave behind (facts,
things going on, tasks) are there afterwards, and how many are right in every detail the filing
rules decide: above the first topic or under the right one, the link to the capture, a task's
day. [CONTRIBUTING.md](../CONTRIBUTING.md#how-well-a-model-files-an-inbox) says what counts and
how to run it.

| Model | Found | Right | Runs |
|---|---|---|---|
| haiku, the default | 1.00 | 1.00 | 3 |
| sonnet | 1.00 | 1.00 | 3 |

Measured on 2026-11-12 with Claude Code 2.1.322, which resolves both names to its current models.
No run failed, left a capture in the inbox, filed a fact or a task from the capture that holds
nothing or wrote a line no capture stands behind. In each of its runs `haiku` started a topic for
a single person, a neighbour, where the filing rules leave the place open; `sonnet` did not.

A measurement earlier that day, when three of the captures named their day without its year, had
`haiku` at 0.97: in one of three runs it wrote two facts into their fact file and left their
lines out of the facts list, so no session would have started with them. That is the slip to
expect of it now and then; `sonnet` was at 1.00 there too.

The inbox is tidier than a real one: short captures with one or two things each. Both models are
at the top of it, so it shows that either files plain captures well, not which one copes better
with long or ambiguous ones. A run over the twenty captures took about two minutes with `haiku`
and eighty seconds with `sonnet`.
