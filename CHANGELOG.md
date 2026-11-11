# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/), with tags `vX.Y.Z`. How a release is made is in
[CONTRIBUTING.md](CONTRIBUTING.md#releasing).

## [Unreleased]

### Added

- [Evals](docs/evals.md) shows what m2b does to Claude's answers, measured: the score of each of
  the eight eval cases with m2b and without, and the model, the Claude Code version and the day of
  the run. Until now the scores a release was checked with were written down nowhere.
- The worklog leaves out the work you name in the profile: `worklog_leave_out` takes folders under
  your home folder. What ran there is in no worklog, not in what the model step reads, the note or
  the ledger. The profile is written as version 2 once it holds the setting, so every machine that
  shares the store needs this version
  ([docs/addons/worklog.md](docs/addons/worklog.md#leaving-work-out)).
- A curation run can read what you typed in Claude Code and propose what belongs in your memory
  although you never said "remember this": a person and their role, an agreement, a commitment
  with its day, something about your own life. It is off until you say yes: setup asks on the
  machine that curates, and `curation.read_sessions` in the machine config holds the answer. A run
  then reads what you typed since the last reading (the last 24 hours the first time, 7 days at
  most), asks the model once with nothing it can call, and keeps a proposal only when the words it
  quotes stand in one of your prompts and you did not capture the same thing yourself. Nothing is
  filed before you say keep: `m2b proposals` lists what waits, each with your own words and the day
  you said them; `m2b proposals keep <id>...`, `keep --all` and `drop <id>...` answer, and the next
  run files what you kept as a capture. While proposals wait, your task list holds one task that
  says how many, so a phone shows it too; completing it answers nothing. With the band, one row
  says how many wait, and `show` on it or `/m2b-proposals` opens them in the m2b pane, each with
  your words, keep and drop with the same 5 seconds of undo as a candidate, and keep all
  ([docs/band.md](docs/band.md#the-proposals-from-your-sessions-in-the-pane)). Only what you typed is
  read: no answer of Claude, no tool result, no pasted block, nothing another sender put into the
  session; credentials are redacted.
  Of a session in a folder of `worklog_leave_out`, or in one where you ran `m2b distillate off`,
  nothing reaches the model ([docs/curation.md](docs/curation.md#reading-your-sessions)). A new
  scenario, `E23-proposals-from-sessions`, runs it from setup's yes to the filed capture.

### Changed

- The model's note tool runs without asking only for a note in your own words: every word of it
  stands in one prompt you submitted in the session, in any order, apart from additions of up to
  four words in square brackets. For any other note Claude Code asks, as it does for a tool no rule
  allows. Before, the mod let every note run, so text the model had read elsewhere, such as a web
  page, could become a note without you seeing it. The `capture` skill's command is unchanged.
- The curation run treats what a capture says as data. A capture that gives instructions to
  whoever files it (to replace or delete facts, to write a given line or rule into memory, to run
  a command) is not carried out: nothing from it is filed, it goes into the archive as written, and
  the review names it, so you can capture what is true in your own words. The refresh step and the
  worklog's verdict follow the same rule for the text they read. A new model-level scenario,
  `E17-planted-capture`, checks it with two captures written to steer the run.

### Fixed

- The worklog's redaction also finds credentials as tools and environments write them: the value
  of `PGPASSWORD=...`, `SECRET_KEY: ...`, `AccountKey=...` and other names that hold password,
  secret, token or a kind of key, the password in a URL and after `curl -u name:`, and AWS access
  key ids. Commit subjects are redacted like prompts; before, they went into the note as written.
  `curl -u name:pw` no longer loses the URL after it while keeping the password.
- The worklog finishes an unfinished worklog only when the note's name in `intent.json` is one the
  worklog gives a note. Before, it joined any name to `inbox/`, so a changed `intent.json` in the
  synced store could create a file outside the store on the machine that curates. Such a file now
  counts as unreadable and nothing is written.

## [0.3.4] - 2026-11-11

### Fixed

- A search that finds nothing about the person or topic asked for no longer offers a hit about
  someone or something else as possibly the same, and does not search unrelated topics to have
  something to say ([#18](https://github.com/Kolibee-GmbH/m2b/pull/18)).

## [0.3.3] - 2026-11-11

### Changed

- The review in the band is one row when a curation run changed facts: `2 facts changed: Sam,
  Dana`, with `ok` to close the review task (5 seconds with `undo`, as keep), the other findings
  as before and a line naming `/m2b-review`. The pane shows each changed fact with its file and
  the added words green and the removed ones red, instead of the old and new line as two cut
  sentences, and names every copy of the facts from before a run the review covers. `ok` writes
  nothing when a run rewrote the review after the band drew it. The curation run keeps each change
  with its whole lines, and `m2b band --json` names those the open review holds under
  `tasks.review` ([#14](https://github.com/Kolibee-GmbH/m2b/pull/14)).

## [0.3.2] - 2026-11-11

### Added

- `/m2b-search --word <text>` matches whole words only, so a search for `Velo` no longer lists
  every line with `Developer` in it. Without `--word` a word still matches inside longer words
  ([#13](https://github.com/Kolibee-GmbH/m2b/pull/13)).

## [0.3.1] - 2026-11-11

### Fixed

- After an update of the worklog's recorder, `m2b-worklog recorder install` and the session start
  link it again in herdr, so herdr runs the new version's events and startup command. Before, the
  check asked herdr's plugin list, which shows the manifest's version as it is now instead of the
  one herdr registered, so a recorder linked by m2b 0.2.0 or earlier never wrote its sign of life
  at herdr's start ([#12](https://github.com/Kolibee-GmbH/m2b/pull/12)).

## [0.3.0] - 2026-11-11

### Added

- m2b has a logo: the README shows it, and `docs/images/` holds the mark, an icon and the image
  for link previews ([#9](https://github.com/Kolibee-GmbH/m2b/pull/9)).
- `m2b band --json` answers everything the band shows in one call: the open candidates, questions
  and review tasks from one look at the task list, and the status. A refresh of the band is one
  `m2b` call instead of four, and the list is read once instead of three times (with Apple
  Reminders, two calls instead of six) ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- `m2b-worklog state` shows the watermark, an unfinished worklog and the last period in the ledger,
  and names a file it cannot read ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The worklog's recorder writes a sign of life at herdr's start and, run by a timer of the operating
  system (a launch agent on macOS, a systemd user timer on Linux), every five minutes while herdr
  runs. A silence of more than 10 minutes appears in the note under "Not recorded" with its times,
  instead of reading as a time without work. The next session start updates the recorder, links it
  again in herdr and sets up the timer; `m2b-worklog recorder remove` takes the timer out too
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- `m2b-worklog recorder check` says whether herdr is installed, at least 0.9.0 and running. The
  worklog setup asks it first and stops before any question when herdr is missing, too old or not
  running ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- Undo in the band: keep and drop wait 5 seconds, while the row offers `undo`, and write only then.
  A click taken back, or a session closed within those seconds, leaves the task as it was
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- `/m2b-note <text>` writes the text into the inbox at once, without a model turn, also while a turn
  is working, and answers with one line showing how the note begins
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- `/m2b-review` opens a pane with the whole last curation run: its state and times, every finding
  whole, and every candidate and question with keep, drop and undo. `/m2b-search <text>` shows the
  hits of a search there, without a model turn ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The band shows your tasks due today or overdue in up to three quiet rows below the candidates;
  `m2b config set band.due_tasks false` turns them off
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- A failed curation run is shown once in every open session, in a line that says where its review
  is ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- A session whose band is older than the installed m2b says so in one line and names
  `/reload-plugins`; `m2b band --json` answers the installed `version` for that
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The model notes and searches through two tools of the mod, `mcp__m2b__note` and
  `mcp__m2b__search`, instead of a shell call. They follow the rules of the skills `capture` and
  `search`, which name them first and work as before where the mod does not run; a search answer
  is marked as data from your notes. Your permission rules for these names, and for
  `Bash(m2b capture:*)` and `Bash(m2b search:*)`, apply; where none decides, the tools run without
  asking, as the skills' commands do ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).

### Changed

- The band is part of m2b instead of an add-on: it starts wherever m2b is set up, with no switch
  and no setup skill (`/m2b:band-setup` is gone), also where it was turned off; `addons.band` in
  `config.json` is ignored and `m2b addons off band` removes it. It needs mods on in Claude Code.
  `m2b doctor` has a line `band` that says whether the latest session ran it, and if not, whether
  only mods or all plugin hooks were off. Its page moved to `docs/band.md`
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The status line reads `2 in inbox · curated 18:02` without its own `brain:`, since Claude Code
  already puts the plugin's name in front ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- Every row of the worklog's ledger carries two numbers: `minutes`, the work in the span, and
  `minutes_present`, the part with the workspace in focus, in `ledger.json`, the CSV and the XLSX.
  Rows from before have the second cell empty ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The worklog reads only the recorder's files written in the three days before its period, instead
  of the whole history at every run. An agent that asked for an approval longer ago is no longer
  reported as waiting ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- Each add-on has its own page under `docs/addons/`, and `docs/addons.md` is the overview that
  links them ([#6](https://github.com/Kolibee-GmbH/m2b/pull/6)).
- CI runs two jobs, macOS on the current Python and Ubuntu on 3.9, instead of four
  ([#7](https://github.com/Kolibee-GmbH/m2b/pull/7)).
- The repository moved to `Kolibee-GmbH/m2b`; new installs use
  `/plugin marketplace add Kolibee-GmbH/m2b`. An install from the old address keeps updating,
  because GitHub forwards it ([#8](https://github.com/Kolibee-GmbH/m2b/pull/8)).

### Removed

- The `herdr` add-on, which listed the other agent sessions open in herdr at session start. It
  never read or wrote the store; herdr shows those sessions itself
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The `backup` add-on, until a backup with a way back replaces it: it kept only a mirror of the
  store, had no restore, and could miss files iCloud Drive had not downloaded. The folder it wrote
  is left as it was. A `config.json` that still names either add-on loads as before, and
  `m2b addons off herdr` or `m2b addons off backup` removes the entry
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).

### Fixed

- A failing add-on step no longer makes the curation run fail. It is still a finding in the review
  task, but the run counts as succeeded, so the inbox keeps being filed and no wait of 1, 4 or 20
  hours starts; before, a worklog that kept failing held back curation to once every 20 hours
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The worklog no longer counts time nobody worked. Focus on a workspace counts up to 10 minutes
  after that workspace's own last event, also while agents in other workspaces keep sending events.
  An agent counts up to 30 minutes past its last sign of life, an event of its pane or a message in
  its transcript, so a machine asleep with an agent left working no longer becomes a night of agent
  time; an agent still at work when the worklog is written counts up to that moment instead of
  being dropped ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The worklog ledger refuses a worklog whose period overlaps one it holds, before anything is
  written, so a reset watermark no longer books days twice. Its messages about an
  unreadable watermark or unfinished worklog point to `m2b-worklog state` instead of advising to
  delete the file ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The worklog counts the same minutes once. A workspace closed and opened again on the same folder
  continues its session instead of starting a second one that held the same evening, and a
  transcript of a workspace without a folder of its own, or of a pane in another folder, goes to
  that workspace instead of a session of its own
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The worklog page no longer names `~/.claude/projects/` as the fixed place of the transcripts: it
  says that `CLAUDE_CONFIG_DIR` moves it, and that `M2B_HERDR` names the `herdr` executable for the
  worklog's commands too ([#10](https://github.com/Kolibee-GmbH/m2b/pull/10)).
- One control character in a title or a finding, such as an escape sequence pasted from terminal
  output, made Claude Code refuse the band's drawing, and the band vanished in every session. Every
  text is now drawn as one plain line ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- A failure inside the band's timers left the status line at its old state; it now says
  `could not look` ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- After a keep or drop, a second click on the same row during the reload claimed that another
  session had settled it. The row now stays locked until that reload has landed
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- Turns ending while `m2b` was slow queued one reload each, so the band could lag minutes behind;
  at most one reload waits now ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- A shared answer of another shape, or one stamped later than now after the clock was set back,
  could break the band or stop sessions from sharing; such an answer is loaded again
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- `M2B_HOME` starting with `~` left the band empty; it resolves under the home folder, as for the
  rest of m2b ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- A task id that starts with a dash reached `m2b tasks complete` as an option; the band now passes
  it after `--` ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The folder with the band's shared answer, which holds candidate titles and findings, is kept
  readable by its owner only ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The worklog's model step writes its verdict to a file instead of passing it as a shell argument,
  so a session in a folder with an apostrophe in its name, such as `Bob's project`, no longer fails
  the step on every run ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- The worklog redacts more before the model sees a prompt: a value a few words after "password",
  `pw=`, a credential after `Bearer`, and base64 keys with `/` and `+`. Its page says that redaction
  over patterns stays incomplete ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- A `<system-reminder>` in front of a prompt no longer uses up the prompt's 240 characters, and the
  summary after a context cut no longer counts as a prompt. The last answer is its last 500
  characters, as the page said, instead of its first
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- A topic starting with `=`, `+`, `-` or `@` is text in `ledger.csv`, not a formula
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- A worklog note whose blocks fall on two dates gives each block its date, and every time is in the
  offset of its own day, also across a change of summer time. Captures stamped with `Z` count on
  Python 3.9 and 3.10 too ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).
- More than three memory candidates, or a line break in a topic or note, make the verdict refused
  and handed back to the model, instead of reaching the note
  ([#11](https://github.com/Kolibee-GmbH/m2b/pull/11)).

## [0.2.0] - 2026-11-09

### Added

- [Add-ons](https://github.com/Kolibee-GmbH/m2b/blob/main/docs/addons.md) describes each add-on:
  what it does and needs, how to set it up and turn it off, what it reads and writes on the machine
  and in the store, its commands, and how you see that it runs
  ([#5](https://github.com/Kolibee-GmbH/m2b/pull/5)).

### Changed

- The herdr and worklog add-ons are no longer marked experimental
  ([#5](https://github.com/Kolibee-GmbH/m2b/pull/5)).
- A program outside the marketplace that writes into the store is now called an integration;
  the former `docs/addons.md` is now
  [Integrations](https://github.com/Kolibee-GmbH/m2b/blob/main/docs/integrations.md),
  `docs/addons.md` now describes the add-ons, and `STORE.md` gives an integration its state
  folder under `state/integrations/<name>/` instead of `state/addons/`
  ([#5](https://github.com/Kolibee-GmbH/m2b/pull/5)).
- The optional parts of m2b (band, backup, herdr, worklog) are now called add-ons: `m2b parts` is
  `m2b addons`, the key `parts` in `config.json` is `addons`, and their state in the store moves
  from `state/parts/<name>/` to `state/addons/<name>/`. `m2b status --json`,
  `m2b setup apply --json` and the run record `state/core/last-run.json` name them under `addons`
  instead of `parts`; a run record from 0.1.1 reads as no add-ons until the next curation run
  rewrites it. `m2b parts` now ends with a usage error, and a `config.json` that still has `parts`
  is refused until the key is renamed ([#5](https://github.com/Kolibee-GmbH/m2b/pull/5)).
- The workflows use action versions that run on Node 24
  ([#3](https://github.com/Kolibee-GmbH/m2b/pull/3)).

### Fixed

- The README now says that the worklog also reads the end of each session's last answer from the
  transcripts and that its model step may search the archive; it did so in 0.1.1 already
  ([#5](https://github.com/Kolibee-GmbH/m2b/pull/5)).
- The README lists what each add-on needs, links herdr, and says what the worklog's time
  spans measure; the worklog setup points out a sphere that nothing can match
  ([#3](https://github.com/Kolibee-GmbH/m2b/pull/3)).
- `m2b config set store.path` refuses a store path the curation fence cannot name on the curating
  machine, and `m2b setup inspect` names such a path before the setup interview starts
  ([#3](https://github.com/Kolibee-GmbH/m2b/pull/3)).

## [0.1.1] - 2026-11-09

### Changed

- A new key in `store.json` raises the store format, and a store is checked against the keys of its
  own format, so a key added later no longer stops capture on machines with an older m2b
  ([#1](https://github.com/Kolibee-GmbH/m2b/pull/1)).
- Releases are tagged `vX.Y.Z` on `main`, and the tag publishes the GitHub release with the
  changelog section as its notes ([#1](https://github.com/Kolibee-GmbH/m2b/pull/1)).

### Fixed

- A capture that cannot be written (no write permission, a full or read-only disk) exits 4 with one
  line saying it was not saved, instead of a traceback, and removes the follow-up task it had
  already created; the capture skill no longer reports such a note as saved
  ([#1](https://github.com/Kolibee-GmbH/m2b/pull/1)).
- A curation run stopped during a model step still checks `memory/` before it exits, and the next
  run compares `memory/` with the copy a run that never finished saved, names what it left in the
  review and keeps that copy ([#1](https://github.com/Kolibee-GmbH/m2b/pull/1)).
- An old journal month that iCloud keeps in the cloud no longer fails every curation run: it is
  fetched first, or left for the next run and named in the review with `m2b store fetch`
  ([#1](https://github.com/Kolibee-GmbH/m2b/pull/1)).
- A capture iCloud will not download no longer stops curation: it waits in the inbox, the run record
  names it, and it does not start a run at every session. `m2b capture` fetches an evicted
  `store.json` first and, when that fails, names the command that downloads it
  ([#1](https://github.com/Kolibee-GmbH/m2b/pull/1)).
- The review names the copy of `memory/` however many captures a step filed; from about eleven, the
  path used to be cut off ([#1](https://github.com/Kolibee-GmbH/m2b/pull/1)).
- `m2b todos` names a task file it cannot read, with its path, instead of saying "No open tasks.",
  and exits 1; the todos skill says it could not look at it
  ([#1](https://github.com/Kolibee-GmbH/m2b/pull/1)).
- Setup and `m2b curate take-over` refuse a store path such as `Notes (2026)` on a machine that is
  to curate, because the rules that fence curation cannot name it, and `m2b doctor` reports one
  already configured there; a machine that only captures may keep its store in such a folder
  ([#1](https://github.com/Kolibee-GmbH/m2b/pull/1)).

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
