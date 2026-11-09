# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/), with tags `vX.Y.Z`. How a release is made is in
[CONTRIBUTING.md](CONTRIBUTING.md#releasing).

## [Unreleased]

## [0.1.1] - 2026-11-09

### Changed

- A new key in `store.json` raises the store format, and a store is checked against the keys of its
  own format, so a key added later no longer stops capture on machines with an older m2b
  ([#1](https://github.com/b33eep/m2b/pull/1)).
- Releases are tagged `vX.Y.Z` on `main`, and the tag publishes the GitHub release with the
  changelog section as its notes ([#1](https://github.com/b33eep/m2b/pull/1)).

### Fixed

- A capture that cannot be written (no write permission, a full or read-only disk) exits 4 with one
  line saying it was not saved, instead of a traceback, and removes the follow-up task it had
  already created; the capture skill no longer reports such a note as saved
  ([#1](https://github.com/b33eep/m2b/pull/1)).
- A curation run stopped during a model step still checks `memory/` before it exits, and the next
  run compares `memory/` with the copy a run that never finished saved, names what it left in the
  review and keeps that copy ([#1](https://github.com/b33eep/m2b/pull/1)).
- An old journal month that iCloud keeps in the cloud no longer fails every curation run: it is
  fetched first, or left for the next run and named in the review with `m2b store fetch`
  ([#1](https://github.com/b33eep/m2b/pull/1)).
- A capture iCloud will not download no longer stops curation: it waits in the inbox, the run record
  names it, and it does not start a run at every session. `m2b capture` fetches an evicted
  `store.json` first and, when that fails, names the command that downloads it
  ([#1](https://github.com/b33eep/m2b/pull/1)).
- The review names the copy of `memory/` however many captures a step filed; from about eleven, the
  path used to be cut off ([#1](https://github.com/b33eep/m2b/pull/1)).
- `m2b todos` names a task file it cannot read, with its path, instead of saying "No open tasks.",
  and exits 1; the todos skill says it could not look at it
  ([#1](https://github.com/b33eep/m2b/pull/1)).
- Setup and `m2b curate take-over` refuse a store path such as `Notes (2026)` on a machine that is
  to curate, because the rules that fence curation cannot name it, and `m2b doctor` reports one
  already configured there; a machine that only captures may keep its store in such a folder
  ([#1](https://github.com/b33eep/m2b/pull/1)).

## [0.1.0] - 2026-11-09

The first release.

### Added

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
- **Band part.** A band above the prompt with open memory candidates and "Still current? ..."
  questions, each with keep and drop in place, the open review task with its findings, and a
  status line such as `brain: 3 in inbox · curated 18:02`. Open sessions share one refresh about
  once a minute.
- **Herdr part (experimental).** At session start inside herdr, one line per other agent session
  with workspace, task, state and place, so overlapping work is noticed before it starts.
  Nothing outside herdr.
- **Worklog part (experimental).** A recorder in herdr writes agent status changes, focus and
  workspace events on the curating machine; `m2b-worklog recorder install` and `remove` link and
  unlink it. Once a day a fenced model step judges the sessions of the period (topic, state,
  sphere, booking) from the recorder, Claude Code transcripts with prompts redacted, the owner's
  git commits and the inbox; a day without sessions costs no model run. The result is a worklog
  note, a ledger with booking proposals and CSV and XLSX exports, and memory candidates.
- **Backup part.** After each curation run, a local snapshot: a mirror of the store, a dated
  attic of replaced files and a dump of the task list.
