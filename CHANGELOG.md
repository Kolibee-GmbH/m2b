# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/), with tags `vX.Y.Z`. How a release is made is in
[CONTRIBUTING.md](CONTRIBUTING.md#releasing).

## [Unreleased]

In short:

- A curation run can read what you typed in Claude Code and propose what belongs in your memory;
  nothing is filed before you keep it ([Reading your sessions](docs/curation.md#reading-your-sessions)).
- With the store in a git repository, each run ends with one commit, and `git revert` on it puts
  back what the run changed, the captures it filed included
  ([A commit per run](docs/curation.md#a-commit-per-run)).
- A run's model steps are fenced more tightly, and what a capture says is treated as data
  ([Security](SECURITY.md)).
- `curation.paused` pauses the background runs on a machine ([Pausing](docs/curation.md#pausing)),
  `m2b --version` prints the version, and [Commands](docs/commands.md) lists every command.
- A folder store recognizes the conflict copies of Dropbox and Syncthing, and a current item can
  stand under a topic, which makes the store format 3 ([Store format](docs/store-format.md#formats)).

### Added

- The README opens with a moving picture that follows one sentence from a prompt, through a
  curation run, into a session in another project; `scripts/readme-demo` records it from real
  sessions against a demo store with invented notes. Its comparison names two public projects,
  obsidian-second-brain and basic-memory, and says where each does more than m2b.
- A store on the `folder` backend recognizes the conflict copies of Dropbox and Syncthing, as the
  `icloud` backend recognizes iCloud's. Until now such a copy was a file like any other there: a
  copy of a task file was a second task, a copy in the inbox was filed as a second capture, and a
  copy in the archive was reported as a note that is not named by the schema. Now `m2b lint`
  reports a copy in the archive as a conflict copy and `m2b lint fix` removes it when it equals its
  original byte for byte, a curation run does the same in the inbox and gives a differing text
  copy a line that names its original, and the Markdown tasks do not read a copy of a task file
  as a second task. The names are
  `<name> (... conflicted copy ...).<ext>`, also with `in Konflikt stehende Kopie` as Dropbox
  writes it for a German account, and `<name>.sync-conflict-<date>-<time>-<device>.<ext>`, each
  only next to the file it is a copy of. There is nothing to set: every folder store recognizes
  both, and a copy that differs from its original is never removed.
- `m2b lint` names a conflict copy of a task file, where the tasks are Markdown files, in a store
  on either backend. A task ticked on one machine and changed on another leaves two files, and
  until now the copy was passed over without a word: nothing said that a second state of the
  task existed. Lint reports the copy as it reports one in the archive: as an action when it
  differs from the task (keep one of them), as an info when it equals the task, or when the two
  were not compared because one is not downloaded or cannot be read. `m2b lint fix` and the lint
  step of a curation run remove a copy that equals its task byte for byte and nothing else: the
  task and a differing copy stay as they are. With Reminders as the tasks backend a `tasks/`
  folder left in the store is not looked at.
- `m2b doctor` has a line `store-git`. It says whether the store folder is a git repository and,
  on the machine that curates, where the git directory lies that a run commits into and which
  git named it. `cannot commit` with the reason counts as a problem: a `.git` in the store folder
  on a curating machine without git, where a run commits nothing and says nothing, a `.git` that
  is not downloaded, a repository git cannot read, or one whose work tree is another folder.
  Where the folder holds a `.git` and this machine does not curate or has `curation.git_commit`
  off, the line says so and git is not started. The git directory and git's reason are printed
  with invisible characters written out, because both come from the `.git` in the store.
- `m2b doctor` has a line `prompt-hook`. The hook that brings a topic's facts before a prompt says
  nothing when it fails, so that no prompt waits or breaks for it; one that never worked looked
  the same as a prompt that named no topic. Doctor now starts it the way Claude Code does, within
  the same time limit, and reports `answers`, or `does not answer` with the reason (the distillate
  is not downloaded, the config is broken, Python is not found), or `missing`.
- A curation run started in the background, at a session start or with `m2b curate --detach`,
  keeps what it writes on standard error in `~/.local/state/m2b/detached-run.err`, replaced at
  each such start. Until now that output was discarded, and a run that died before it could write
  its record left no reason behind.
- A curation run ends with one git commit when you keep the store in a git repository: run
  `git init` in the store folder and commit the store once, and from then on
  `git revert <commit>` takes one run back. The
  commit holds what changed in the store while the run ran, and nothing else of what you left
  uncommitted or staged (a file the run also wrote goes in as it is on disk); its author is `m2b <m2b@localhost>`, so `git log --author=m2b` lists the
  runs. m2b makes no repository, writes no git configuration, never pushes, runs no hook and signs
  nothing; a commit that fails is reported in the review task and never fails the run. In a synced
  folder git gets only files that are on this machine, so nothing is downloaded for a commit.
  Without a repository in the store folder nothing changes, and `curation.git_commit: false` in
  the machine config turns it off ([A commit per run](docs/curation.md#a-commit-per-run)).
  A capture that came in after your last commit is a file git does not know, so before its first
  step a run commits such captures where they wait, in a commit of their own
  (`m2b: captures before the curation run ...`): only files in `inbox/` that git does not know,
  nothing you staged or changed. Reverting the run's commit then puts such a capture back into
  `inbox/` instead of deleting it from the store folder
  ([Taking a run back](docs/curation.md#taking-a-run-back) names what a revert does not put back).
- A current item can stand under a topic. In `## Current` of the distillate, a heading
  `### <name> (<word>, <word>)` now works as it does under `## Facts`: the items below it stay out
  of the session start and come in with the topic's facts, where the project folder's path or a
  prompt names one of its words. Until now every line under `## Current` reached every session, and
  lint reported such a heading as an error. Curation files what you are working on for one subject
  (a customer, an organisation's project, a club) under that subject's topic there, with the
  heading its facts have, and what goes on in your own life above the topics. An item that stands
  above the topics and is about one subject moves under its topic when a new capture is about the
  same thing; one you move under a topic yourself stays there. A model-level scenario, `E14-topics`, checks where a
  real ingest step puts both kinds. The store gets format 3
  at the curating machine's next run, and nothing in `memory/` changes; update the curating machine
  first. A machine on an older m2b keeps capturing and gives every session every current item until
  it is updated ([Store format](docs/store-format.md#memory)).
- [Evals](docs/evals.md) shows what m2b does to Claude's answers, measured: the score of each of
  the eight eval cases with m2b and without, and the model, the Claude Code version and the day of
  the run. Until now the scores a release was checked with were written down nowhere.
- The worklog leaves out the work you name in the profile: `worklog_leave_out` takes folders under
  your home folder (`path_under`) and parts of the URLs of git remotes (`git_remote_contains`),
  which name a repository in every folder it is checked out in. What ran there is in no worklog,
  not in what the model step reads, the note or the ledger. A worktree that is gone when the
  worklog runs is still known by its remote: on a machine that reads sessions, every session start
  notes the remotes of the folder it starts in, in `~/.local/state/m2b/session-remotes/`, without
  the user name or token of a URL. While you name a remote, work in a folder whose repository
  nobody can tell is left out too, and the note says in how many folders. A sphere's
  `git_remote_contains` now ignores upper and lower case and also finds the SSH spelling of an
  address. The profile is written as version 2 once it holds the setting, so every machine that
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
  Of a session `worklog_leave_out` names, by its folder or by a git remote of its repository, or
  in a folder where you ran `m2b distillate off`, nothing reaches the model ([docs/curation.md](docs/curation.md#reading-your-sessions)). A new
  scenario, `E23-proposals-from-sessions`, runs it from setup's yes to the filed capture.
- A proposal from your sessions that got no answer for 14 days expires: it waits no longer, does
  not count as dropped and is not proposed again for 90 days; `m2b proposals keep <id>` still keeps
  it in that time. Every curation run does this and removes the proposals kept, dropped or expired
  90 days ago, whether or not it reads the sessions. `m2b status` says what share you kept of the
  proposals you answered in the last 30 days and how many expired, and `m2b status --json` adds the
  counts per kind since the first reading: proposed, kept, dropped, expired, and refused because
  the words they quote do not stand, with at least three words, in a prompt of the session they
  name ([docs/curation.md](docs/curation.md#reading-your-sessions)).
- The reading of your sessions learns from your answers: it shows the model up to 30 proposals you
  kept and up to 30 you dropped, those a run settled last, each with its kind, its text and your
  words, and tells it to leave out what is like something you dropped. Expired proposals are not
  shown. On the invented day of `scripts/glean-eval`, which now holds five kept and four dropped
  proposals and one sentence like the dropped ones, `haiku` and `sonnet` proposed that sentence in
  six of six answers without the examples and in none of six with them, and found all twenty
  planted statements either way; `scripts/glean-eval --without-examples` measures the day without them.
- `m2b config set curation.paused true` pauses curation on a machine: no session start and no
  schedule starts a run there until the setting is `false` again. Until now the only ways to stop
  the background runs were to turn the plugin off, which also takes capture and the distillate
  away, or to move curation to another machine. A paused machine still captures, its sessions
  still get the distillate, and `m2b curate --force` still files the inbox when you ask for it;
  `m2b status` has a line `paused`, and a scheduled `m2b curate` shows there as
  `last attempt: paused at ...` ([Pausing](docs/curation.md#pausing)).
- [Commands](docs/commands.md) is a new page with everything you can say, type after a slash or
  run as `m2b`: what to say in a session, the skills (`/m2b:search`) and the band's commands
  (`/m2b-search`) with what tells them apart, every `m2b` command with one line, and the exit
  codes. The README lists the ten used most, `m2b tasks list` and `m2b tasks complete <id>` among
  them, which is how a Markdown task is ticked.
- `m2b --version` prints the version, also on a machine that is not set up. The bug template asks
  for it.
- A command that groups actions, such as `m2b lint`, `m2b tasks` or `m2b setup`, prints its help
  when it is named without an action. Until now it ended with a usage error and exit code 2.

### Changed

- `m2b curate` answers a run in two lines. After the line that says how the run ended comes what
  it did to the inbox, such as `inbox: 3 captures filed, 0 waiting`; when a run that ended well
  left something in the review task, the line says so. Until now the answer was
  `the curation run succeeded` alone, and whether anything was filed took a second command. Filed
  counts what reached the archive, so a ticked "Remember? ..." candidate the same run filed is in
  it. An answer without a run (not due, paused, `--detach`) is one line as before. A script that
  compared the whole output must take the second line into account.
- On a machine that is not set up, a command's answer names both ways in: `/m2b:m2b setup` in
  Claude Code and, without Claude Code, `m2b setup apply` with the address of Getting started.
  Until now it named only the first, which whoever tries m2b from a checkout does not have.
- The README explains six more of its words (fact file, review task, proposal, memory candidate,
  mod, herdr), shows under Troubleshooting what `m2b doctor` and `m2b status` answer on a healthy
  machine and which of their lines only look like a problem, and names two more things to remove
  when uninstalling: the marketplace and the `PATH` line. [Security](SECURITY.md) opens with five
  lines that sum it up and says that reports are taken for the latest release.
  [Getting started](docs/getting-started.md) lists the folder with the copies of `memory/` a run
  keeps on the machine.
- The README has a quick start right below its first screen, says what Claude Code prints when
  the install is done, says where m2b stands (young, in daily use by its author on macOS, Linux
  covered by the tests), that a run's usage is recorded nowhere, that the band's two tools run
  without Claude Code's permission prompt, and how to report a bug. It no longer says a session
  keeps your words "verbatim": the note is in your words without the request around them. It
  also says that a run can file facts under a topic,
  and that a session then starts with the topic's name only.
- [The curation run](docs/curation.md) has a section "Correcting what a run filed": a wrong fact,
  a fact under the wrong topic, a finding of lint in the review task, a note that should never
  have been kept. It also says to commit the store once before the first run commits into it:
  reverting the first run that touched a file git had never seen deletes that file, the
  distillate for one.
- lint's finding about a topic's words names the file and says where the words stand: "in
  memory/MEMORY.md, the topic Trip has 1 word in the brackets of its heading; it needs 2 to 5".
  Until now it read "the topic Trip has 1 words; it needs 2 to 5".
- [Getting started](docs/getting-started.md) says after each step in Claude Code what you should
  see and what to do when you do not, and which session knows a new fact: the session start after
  a capture starts the run, and the session after that one starts with the fact. The times in it
  are measured: 15 seconds for a setup with every answer given at once, 13 seconds for a run over
  one capture.
- `m2b search` prints nothing from the store with a character that draws nothing, as text and
  with `--json`: zero-width characters, marks that reorder text, variation selectors, soft
  hyphens and tag characters are gone from a hit's text, the joiners emoji and several scripts
  need stay. In a file's path, in
  the command that fetches a file and in the reason a file could not be read, such a character
  is written out as `<U+200B>`. A session that searches through the skill's command read a hit
  as it was stored until now, with whatever such a character carried.
- A proposal from your sessions whose topic is longer than the 60 characters a topic's name may
  have is left out and counted with the entries that are not in the form, like one whose text is
  over 300 characters.
- A curation step that fails over what it wrote to `memory/` names the line by its file and line
  number ("line 5 written to memory/MEMORY.md holds U+200B"), no longer by its text, and does not
  name a file the step added, whose name the model chose. `m2b status` and the review task show
  that reason to a session that asks, and a quoted line carried whatever a capture had made the
  model write. The notices at session start now go out without invisible characters, like the
  distillate below them.
- The session start says of a failed curation run when it failed and in which steps ("failed at
  2026-11-07 03:05 in ingest; m2b status says why"), no longer why. The reason can repeat what a
  model said when its run broke, the end of what an add-on's command printed or a file's name, and
  the notice stands in m2b's own voice above the line that marks the distillate as data.
  `m2b status` and the review task show the reason as before. Of a run that left no record the
  notice names the run log, and of a run record that cannot be read it quotes no value.
- A curation step's Claude Code session is fenced more tightly. It has only the tools its step's
  rules name (Bash, Read, Edit and Write for the steps of the core), no MCP server, no `CLAUDE.md`
  and no memory of Claude Code's own, and it keeps no transcript. Measured with Claude Code
  2.1.322, a step had some twenty more tools until now, and those that ask no permission ran: it
  listed the other Claude sessions on the machine, and no permission kept it from messaging one.
  The connectors of your claude.ai account were part of a step's session, your own
  `~/.claude/CLAUDE.md` was in every step's context, so an instruction you wrote for your sessions
  reached the step that files your notes too, and each step left a transcript under
  `~/.claude/projects/`. A step can no longer read or change a file in Claude Code's own folder
  either: Claude Code allows that in the memory folder it keeps for a session's project without
  any rule, and where your home folder is a git repository, that is the memory your sessions
  there start with. Other commands and files outside a step's rules were denied before as they are
  now. m2b checks what Claude Code gives the session: a step whose session starts with another
  tool or an MCP server is stopped and fails with their names, and a call of a tool the step does
  not have fails it like a denied call. An executable you put in `claude`'s place with
  `M2B_MODEL_RUNNER` has to print the line that names its tools and MCP servers
  ([SECURITY.md](SECURITY.md#the-fence-around-a-model-step)).
- The session-start and prompt hooks take every character that draws nothing out of the
  distillate before a session reads it, not only those that hide or reorder text: also soft
  hyphens, fillers, direction marks and variation selectors, which can carry bytes nobody sees.
  The core and the band now keep one table of these characters (what Unicode calls default
  ignorable, without the two joiners emoji and several scripts need), so the model's search tool
  and the hooks remove the same ones. What undoes a curation step stays as it was: a selector
  after an emoji or a soft hyphen in a pasted text is no reason to fail a run.
- `m2b search` answers with what is curated first: hits from `memory/` (the distillate, then the
  fact files), then from the archive, then from the inbox, and in the archive and the inbox the
  newest note first, by the time in the note's name. Before, hits came in the order the files are
  read: the inbox, the archive from its oldest note on, memory last. The `/m2b-search` pane and
  the model's search tool show the first 100 hits, so a word with more hits than that showed the
  inbox and the oldest notes and left out memory.
- The worklog proposes nothing for your memory any more and adds no task. Its model step judged
  prompts cut at 240 characters and proposed at most three facts a day, each as a task
  "Remember? ..."; what your sessions hold for memory comes from the curation run's reading of
  your sessions, once you turned it on, with your own words beside each proposal
  ([docs/curation.md](docs/curation.md#reading-your-sessions)). The worklog keeps topics, time
  spans and booking proposals. Its verdict names the sessions only, its note has no part
  "Proposed for memory", and its model step no longer reads your task list. "Remember? ..." tasks
  work as before for a fact proposed with `m2b tasks add --candidate`.
- The worklog takes as your prompts only what you sent. What Claude Code marks as sent by a
  plugin, a finished task or another session is no prompt in the facts its model step judges,
  while its time still counts as work; before, a plugin that drives a session filled the session's
  prompts with its own tasks. A prompt without the mark, from a Claude Code before the mark,
  counts as yours.
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

- A task gets the day its capture names in words: "on Wednesday", "tomorrow", "in two weeks",
  "am 11. November". The ingest skill asked for a day "only when the capture names a day
  (`YYYY-MM-DD` or `YYYY-MM-DD HH:MM`)", and `haiku`, the default model of a curation run, took
  that in some runs for a day written as a date: over eight invented captures of one Monday, each
  a task with such a day, it filed 42 of 240 tasks on no day in thirty curation runs, more often
  when the captures were ten days old than three. The skill now says that a day named in words is
  a day, that it counts from the capture's `created` and not from the day of the run (a weekday
  is the next such day after it, as for the last day of a fact), and that it is given also when
  it has passed by then, so the task shows as overdue. With that, `haiku` gave every day in thirty
  runs; `sonnet` did before and after. No run of either model counted from the day of the run.
- A question in one language over notes in another is answered in the language of the question.
  The search tool's description and the skill `search` already said so, and a session still
  answered an English question in German about one time in six where the distillate and the
  note were both German. The search tool now takes `question_language`, the language the
  question was asked in, and its result ends with a line that names it as the language to
  answer in. With it, 100 of 100 sessions on Sonnet answered in English; a sentence alone, at the
  end of the result or at the session's start, did not change the rate. The skill's command,
  used where the mod does not run, answered in English in 30 of 30 and is unchanged.
- Only a file is the original of a conflict copy. A folder with that name beside the copy was
  taken for the original, and comparing the two failed with a read error; a symlink with that
  name that pointed at the copy compared equal to it, so the copy, the only bytes, was removed.
- A conflict copy or an original that cannot be read no longer stops lint, the curation run's
  look at the inbox or the Markdown tasks: the pair is not compared, the copy stays, and lint
  says so in its finding.
- The worklog's redaction also finds credentials as tools and environments write them: the value
  of `PGPASSWORD=...`, `SECRET_KEY: ...`, `AccountKey=...` and other names that hold password,
  secret, token or a kind of key, the password in a URL and after `curl -u name:`, and AWS access
  key ids. Commit subjects are redacted like prompts; before, they went into the note as written.
  `curl -u name:pw` no longer loses the URL after it while keeping the password.
- The worklog finishes an unfinished worklog only when the note's name in `intent.json` is one the
  worklog gives a note. Before, it joined any name to `inbox/`, so a changed `intent.json` in the
  synced store could create a file outside the store on the machine that curates. Such a file now
  counts as unreadable and nothing is written.
- The worklog no longer puts a temporary file into the store's folder while it writes its note, the
  ledger, the two exports, the watermark or `intent.json`. It writes them with the code the core
  writes the store with, from a temporary file in `~/.local/state/m2b/tmp/`, so a synced store sees
  neither half a file of the worklog nor a leftover after a crash; only when that folder is on
  another volume than the store, a hidden temporary file stands beside the target while it is
  written. A new file of the worklog now gets the mode your umask gives, like every other file in
  the store, where it was readable by you alone before.
- The worklog starts git only when it starts without asking you anything. On a Mac without the
  developer tools, `/usr/bin/git` is a stand-in that opens a dialog offering to install them, and
  the daily worklog, which runs in the background, started it for every session's commits and
  remotes. Now it asks once per run which git there is to start, as the commit of a curation run
  and the session-start hook already did, and without one starts none: the note says under "Could
  not read" for each session whose folder is still there that this machine has no git to start,
  and while you leave work out by git remote, a folder's repository is known only by what a
  session start noted for it.

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
