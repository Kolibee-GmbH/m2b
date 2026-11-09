# Changelog

All notable changes are listed here, per part of the one plugin `m2b`. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the plugin uses
[semantic versioning](https://semver.org/) with tags `m2b--vX.Y.Z`, the form `claude plugin tag`
creates. How a release is made is in [CONTRIBUTING.md](CONTRIBUTING.md#releasing).

## Unreleased

### m2b

- **Fixed: a capture that cannot be written says so.** When the inbox has no write permission or
  the disk is full or read-only, `m2b capture` exits 4 with one line saying the capture was not
  saved, instead of a traceback, and removes the follow-up task it had already created for it.
  The capture skill tells the user from that line that nothing was kept; before, it reported the
  note as saved and left a task pointing to no note.
- **Fixed: a curation run stopped during a model step still checks `memory/`.** A runner stopped
  with SIGTERM while ingest, refresh, lint or sorting ran skipped the check that puts `memory/`
  back when a line hides text. It now checks before it exits, and the next run compares `memory/`
  with the copy a run that never finished saved, lists what it left in the review and keeps that
  copy instead of pruning it.
- **Changed: a new key in `store.json` raises the store format.** An m2b refuses a key it does not
  know in a format it knows, so a key added without a new format would have stopped capture on
  every machine with an older m2b. A test now holds the keys of each format, and `CONTRIBUTING.md`
  states the rule.
- **Fixed: an old journal month in the cloud no longer fails every curation run.** The journal of
  completed tasks reads every month since `journal_since`, and a month file iCloud had evicted
  failed the run each time. The journal now fetches such files first; one that stays in the cloud
  is left for the next run and named in the review with `m2b store fetch`, and the other months
  are written.
- **Fixed: a capture iCloud will not download no longer stops curation, and capture fetches
  `store.json`.** One inbox file that did not download in time stopped every curation run at its
  start; it now waits in the inbox for the next run and the run record names it. On a machine where
  iCloud had evicted `store.json`, `m2b capture` refused at once; it now fetches the file first and,
  when that fails, says which command downloads it.
- **Fixed: the review names the copy of `memory/` however many captures a step filed.** The line
  that says where `memory/` as it was before the run is kept listed the captures first and the
  path last, so from about eleven captures the path was cut off the review task. The path now
  comes first.
- **Fixed: `m2b todos` no longer says "No open tasks." while a task file cannot be read.** A
  Markdown task file that held no readable task was left out silently. It is now named with its
  path and the reason, the command exits 1, and the todos skill says it could not look at it.

## 0.1.0 - not released yet

The first release. It gets its date on the day it is published.

### m2b

- **Setup.** `/m2b:m2b` explains what m2b does; `/m2b:m2b setup` sets up the core and then
  offers each optional part. The quick start creates a folder store at `~/m2b` with tasks as
  Markdown files. Setup never overwrites a store: pointed at a folder another machine uses, it
  joins it. `m2b status` and `m2b doctor` show the state and say what to fix. On a Python older
  than 3.9, `m2b` says so in one line.
- **Stores and tasks.** Notes are Markdown files in iCloud Drive or any folder; tasks live in
  Apple Reminders (through `reminders-cli`) or in Markdown files next to the notes. A calendar
  backend for Apple Calendar shows today's events, and "put it in my calendar" creates an event
  in the calendar the owner names (experimental).
- **Capture.** "Remember this" in any session, or `m2b capture` in a terminal, writes one file
  into the inbox with the owner's words as written; with a date it also creates a task that
  points back to the note. Sessions capture what the owner learns about people and verbal
  agreements, at work too, never documents or confidential statements of third parties.
- **Search, todos, rediscover.** Full text search over archive, memory and inbox, a word and its
  translation in one search (`m2b search --any -- "lawn mower" "Rasenmäher"`); open tasks
  grouped by due date with today's events; old notes brought back with a reason, also by month
  (`m2b rediscover --month 2026-03..2026-05`).
- **The distillate at session start.** A hook prints `memory/MEMORY.md`, marked as data, not
  instructions, with a line when something needs the owner (a failed run, a curating machine
  that has not run for three days, a store that cannot be found). It stays under Claude Code's
  10,000 character cap for a hook. `m2b distillate off` keeps it out of a project and its
  subfolders. A routing rule printed with it keeps Claude Code's own memory apart: how Claude
  should work stays with Claude Code, in its memory or in a `CLAUDE.md`; what concerns the
  owner's life goes to m2b.
- **Topics.** Facts that matter for one subject (a customer, a club, a project) sit under a
  topic in the distillate; a session sees the topic's name, and its facts come in when the
  project folder's path or a prompt names one of its words.
- **The curation run.** Starts at session start on the curating machine when it is due, or from
  a schedule (`docs/curation.md` says when one helps). Harvest, journal, the review task and the run record are code, and so is lint,
  except that it repairs a broken memory link with exactly one candidate in a model step. Ingest
  and refresh are fenced model steps that run only when there is something to read: from an empty
  folder, without the owner's settings, allowed only the commands and paths of their step, with
  `curation.model` (`haiku` by default), `curation.max_turns` and an optional
  `curation.max_budget_usd`. A failing step is reported in the review task and the run goes on;
  retries wait 1, 4, then 20 hours. A step that fails says why in Claude Code's words, and how to
  sign in when the login is missing. The commands that move, rename or edit store files run only
  inside a curation run.
- **Checks after the model.** Code compares `memory/` with a copy taken just before each model
  step: refresh is held to the facts that are due and undone otherwise; each facts line ingest
  or lint removed or rewrote is listed in every review until the owner completes the review task,
  with a copy of `memory/` from before the run kept in machine state; a line holding characters
  that hide or reorder text undoes the step, and the session-start and prompt hooks remove them.
- **Files m2b cannot read** stop nothing: an inbox file the run cannot file is named in the
  review and starts no further run until it changes; a Markdown task file m2b cannot read is
  left out of every list and named by lint and `m2b tasks list`.
- **Facts that expire.** Ingest gives a fact that ends on a known day `until: YYYY-MM-DD` and
  each current item `(since YYYY-MM-DD)`, and a fact that ends gets a fact file of its own beside
  the subject's lasting one; the refresh step rewrites the facts past their day. A current item no
  capture touched for 30 days becomes a task "Still current? ...", asked again after a switch to
  another task list.
- **Store formats.** `format` in `store.json` counts the rules for curated content. A later m2b
  that raises it migrates the store at the start of the curating machine's next run, each
  migration checked in code and undone when it fails; an older m2b reads such a store and
  captures into it, but does not curate it. `m2b doctor` and `m2b status` show the store's format
  against the installed m2b. 0.1.0 writes format 2.
- **Earlier values.** When a capture changes a fact, ingest keeps the old value in the fact file
  under `## Earlier` with the last day it held; lint checks the form. Format 2 adds it, and its
  migration changes nothing in an existing store.
- **Moving over from another tool.** `m2b curate --refresh-all` dates, once, memory lines
  written without dates; `m2b curate --sort-facts` sorts an older distillate into topics once,
  and code puts the old file back if any statement changed.
- **Memory candidates.** A proposed fact appears as a task "Remember? ..."; tick it and the next
  run files it, drop it and it does not come back for 90 days.
- **Optional parts** are off until their setup skill turns them on; `m2b parts list`, `on` and
  `off`. A part that is off prints nothing, draws nothing and runs no curation step.

### band part

- A band above the prompt with open memory candidates and "Still current? ..." questions, each
  with keep and drop in place, the open review task with its findings, and a status line such as
  `brain: 3 in inbox · curated 18:02`. Open sessions share one refresh about once a minute.

### herdr part (experimental)

- At session start inside herdr, one line per other agent session with workspace, task, state
  and place, so overlapping work is noticed before it starts. Nothing outside herdr.

### worklog part (experimental)

- A recorder in herdr writes agent status changes, focus and workspace events on the curating
  machine; `m2b-worklog recorder install` and `remove` link and unlink it.
- Once a day a fenced model step judges the sessions of the period (topic, state, sphere,
  booking) from the recorder, Claude Code transcripts with prompts redacted, the owner's git
  commits and the inbox; a day without sessions costs no model run. The result is a worklog
  note, a ledger with booking proposals and CSV and XLSX exports, and memory candidates.

### backup part

- After each curation run, a local snapshot: a mirror of the store, a dated attic of replaced
  files and a dump of the task list.
