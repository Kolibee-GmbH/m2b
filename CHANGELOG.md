# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/), with tags `vX.Y.Z`. How a release is made is in
[CONTRIBUTING.md](CONTRIBUTING.md#releasing).

## [Unreleased]

## [0.12.0] - 2026-11-21

Sessions learn your projects and the corrections you keep: a project becomes a topic that knows
where its repository lies on each machine, and a correction you kept comes into every session, or
right before the command it is about.

### Added

- "Remember this project" in a session keeps the project of its folder with the address of its git
  remote, and the next run makes it a topic with a line `- Repository: github.com/acme/portal`.
  Where a prompt or the folder's path names the topic, it comes in with the folder the repository
  lies in on this machine, or with `not cloned on this machine`
  ([Using m2b](docs/using.md#a-project))
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).
- A project topic's lines can point into its repository, as a sentence, `→` and a path; the
  content stays in the repository. Lint reports a pointer whose file the clone no longer holds and
  a repository no folder was opened in for 30 days ([Store format](docs/store-format.md))
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).
- A curation run that reads your sessions proposes a repository you worked in on two days, and
  that no topic names, as a project, and a pointer when you stated a decision, an agreement, a
  person or a deadline in a project's repository and Claude wrote it into a file there
  ([Curation](docs/curation.md#reading-your-sessions))
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).
- Every session starts with the lessons you kept for every project, corrections you made and kept,
  in a block of their own (`memory/lessons/`). They come with m2b's notices and the routing rule
  in a second output at the session start, so the distillate keeps its 8 KB beside them. A lesson
  that `~/.claude/CLAUDE.md` or another source states now is left out ([Using m2b](docs/using.md#lessons))
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).
- A lesson about a command comes before Claude runs it: a hook before each Bash call stops the first
  call of a session whose command holds the lesson's words, with the lesson as the reason, and lets
  the next one through with it, or has Claude Code ask you first. "Keep this as a lesson" in
  a session keeps one with `m2b lesson add` ([Using m2b](docs/using.md#lessons))
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).
- A curation run that reads your sessions proposes a lesson when you made the same correction of
  Claude in two sessions. Before it is proposed, a second model call without tools checks it
  against the files a session in that folder loads: a line that says it wrongly makes it a fix of
  that line, a line that says it rightly a pointer to that line, and only where no file says
  anything does it become a lesson ([Curation](docs/curation.md#reading-your-sessions))
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).
- `m2b status` and the overview's part "m2b" name each lesson with how often you corrected Claude
  on it again since you kept it, and for a lesson about a command how often it fired and in how
  many Bash calls; a lesson corrected again is named `not working`
  ([Using m2b](docs/using.md#lessons))
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).
- A lesson about a command that did not fire for 30 days is asked about in your task list,
  `Still needed?`: a drop removes it, a tick keeps it for another 30 days. Where the block of
  lessons is full, a proposed lesson names the kept lesson it would replace, the one corrected again
  most often; keeping it removes that one ([Using m2b](docs/using.md#lessons))
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).
- A fix for a file Claude reads: say "keep this as a fix" with the file, what is wrong and the new
  wording, and `m2b fix add` keeps it. m2b never writes that file; the next session in a clone of
  that repository, or on this machine for a file under `~/.claude/`, names the fix, applies it with
  you and marks it done on your word. Where the file no longer holds the line, the session tells you
  ([Using m2b](docs/using.md#fixes-for-the-files-claude-reads))
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).
- `m2b status` says how large everything is that a session in this folder starts with: your
  `CLAUDE.md` files and rules, the output style, Claude Code's auto memory and m2b's part, each in
  KB and list points, with the sum, so you see where to cut. A file it cannot read is named as such
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).

### Changed

- Reading your sessions now sees, beside each prompt and never as your words, the last 500
  characters of Claude's answer before it, the shell commands Claude ran in that turn and, in a
  project's repository, the files the session wrote there, so a correction can be told by what it
  corrects ([Curation](docs/curation.md#reading-your-sessions))
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).
- The rule every session starts with sends a correction that holds in every project to an m2b
  lesson, and to `~/.claude/CLAUDE.md` only where you ask for that file, never into the memory of
  the project it was made in, and one that a
  `CLAUDE.md` says wrongly to a fix of that file. What touches both a project and you goes into the
  repository, and into the second brain as a sentence naming the file it stands in
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).
- The session start notes the git remotes of its folder in every session, not only where sessions
  are read, and keeps a note while its folder is there; for leaving work out a note still counts
  for 30 days
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).

### Fixed

- A "Still current?" question asked in a later curation run than the first one is remembered, so
  deleting it takes its line out of `## Current` as deleting the first one does. Before, only the
  questions of the first run were kept, and a later one you deleted left its line standing
  ([#41](https://github.com/Kolibee-GmbH/m2b/pull/41)).

## [0.11.0] - 2026-11-20

A message you send while Claude is still working counts as your prompt, and the reading of your
sessions knows which of its proposals still wait for your answer.

### Added

- The reading of your sessions is shown the proposals that wait for your answer, up to 30, so it
  does not propose one of them again in other words
  ([Reading your sessions](docs/curation.md#reading-your-sessions))
  ([#40](https://github.com/Kolibee-GmbH/m2b/pull/40)).

### Fixed

- A message you send while Claude is working, which Claude Code takes into the running turn, is
  read as your prompt: by the reading of your sessions, which proposes facts from it, by the
  worklog, and when a session hands in a proposal that quotes it. Claude Code writes such a
  message as an attachment of the turn, not as a prompt, and until now none of the three saw it
  ([Reading your sessions](docs/curation.md#reading-your-sessions))
  ([#40](https://github.com/Kolibee-GmbH/m2b/pull/40)).

## [0.10.1] - 2026-11-20

The README shows its logo and its picture of how m2b works in the theme you chose on GitHub.

### Fixed

- The README picked the light or the dark logo and overview picture by your system's setting, not
  by the theme you chose on GitHub, so with the two set differently it showed the dark files on a
  white page, their headings white and the logo's m almost invisible. It now follows GitHub's
  theme, and the m of the light logo is grey
  ([#39](https://github.com/Kolibee-GmbH/m2b/pull/39)).

## [0.10.0] - 2026-11-20

In a terminal the band moves below the prompt, where it leaves the space above to the session; in
the desktop app it stays above the prompt.

### Changed

- Without an entry for `band.place`, the band picks its place by where the session is drawn: in a
  terminal it is the end of the hint line below the prompt, as with `below`, and the space above
  the prompt stays the session's; in the desktop app and on the other surfaces it is the row above
  the prompt, as with `above`, because only a terminal draws the hint line's end. A value you set
  holds everywhere; `m2b config get band.place` answers `null` without an entry
  ([Where it stands](docs/band.md#where-it-stands))
  ([#37](https://github.com/Kolibee-GmbH/m2b/pull/37)).

## [0.9.1] - 2026-11-18

The band says that a session handed something in, so you see that a curation run is worth
starting.

### Added

- The band's row counts what your sessions handed in while it waits for a curation run:
  `m2b  1 handed in  [ open ]`. Until now the row said nothing between a session's "handed in" and
  the run, and the hint stood only in the last part of the pane's overview. On the machine that
  curates the count stands at full strength, on any other it is stepped back, and after the run
  the proposal is among what waits for you ([What it shows](docs/band.md#what-it-shows))
  ([#36](https://github.com/Kolibee-GmbH/m2b/pull/36)).

### Fixed

- In a narrow terminal the band's name no longer breaks over two lines (`m2` and `b`) where the
  row is longer than its line: `m2b` stays whole, and the counts are cut at their end
  ([#36](https://github.com/Kolibee-GmbH/m2b/pull/36)).

## [0.9.0] - 2026-11-17

From a said sentence to memory. What you keep is filed without a second step: a curation run
starts once you have answered the proposals. Before a run, m2b says how many proposals your
sessions handed in, and a current item opens the note it rests on. The run after your answers is
on from the update, and `curation.run_after_answers` turns it off; a session that started before
the update keeps the pane it has until `/reload-plugins`.

### Added

- What you keep reaches the memory without a second step: once you have answered every proposal
  that waits and kept at least one, a curation run starts in the background and files what you
  kept. The view of the proposals says that it runs. `curation.run_after_answers` turns that off;
  a paused machine starts no such run, and on a machine that does not curate the view names the
  machine whose run the answers wait for
  ([The proposals from your sessions, in the pane](docs/band.md#the-proposals-from-your-sessions-in-the-pane))
  ([#35](https://github.com/Kolibee-GmbH/m2b/pull/35)).
- While answers to proposals wait for a run, the view of the proposals and the overview say how
  many, with `curate now` below them on the machine that curates ([#35](https://github.com/Kolibee-GmbH/m2b/pull/35)).
- `m2b curate --detach --after-answers` starts a run only where the answers call for one, and
  with `--json` says why none started ([When it runs](docs/curation.md#when-it-runs)) ([#35](https://github.com/Kolibee-GmbH/m2b/pull/35)).
- What a session handed in shows before the next run takes it in: `m2b status` and `m2b proposals`
  say how many such proposals wait, `m2b band --json` carries the number, and the overview of the
  m2b pane says it above `curate now`. Only the number, never the words
  ([What a session hands in](docs/curation.md#what-a-session-hands-in)) ([#35](https://github.com/Kolibee-GmbH/m2b/pull/35)).
- A current item in the tab `Facts` and in a topic reads like a fact: its words and since when,
  with `show` below it for the note it rests on, which opens that note in the pane
  ([What m2b knows](docs/band.md#what-m2b-knows)) ([#35](https://github.com/Kolibee-GmbH/m2b/pull/35)).

### Changed

- A current item no longer shows the file name of its note in the line ([#35](https://github.com/Kolibee-GmbH/m2b/pull/35)).

## [0.8.0] - 2026-11-17

From a fact to what it rests on. The pane has two new tabs, `Tasks` and `Facts`; a fact opens its
file, and from there the note or the document behind it, a PDF or a picture in the system's
viewer. A session reads those details too, a long PDF is read whole with an outline of its pages,
and a file you name in a session goes into the inbox on your yes. What goes in from work is yours
to decide. Nothing is to do after the update; a session that started before it keeps the pane it
has until `/reload-plugins`.

### Added

- A PDF of more than one page in the inbox is read whole, up to its 60th page, and its note in the
  archive says what stands on which page: `pp. 4-5: fees 240, due 31 January; locker 37`. Until now
  a curation run read the first pages of a long document and filed what stood there; the rest was
  in no fact and in nothing a search reads. `m2b search` finds the outline, and the note says where
  the run stopped in a longer document ([A document in the inbox](docs/curation.md#a-document-in-the-inbox))
  ([#32](https://github.com/Kolibee-GmbH/m2b/pull/32)).
- A session reads what stands behind a fact. The search tool, called with the name a line of the
  distillate ends with (`dana.md`), answers that fact file whole: its lines, its last day, its
  earlier values and the notes it rests on, each with its day, what it is and its first line;
  called with one of those notes' names, it answers the note, and for a document its original
  name and the outline of what stands on which page. The new command behind it is
  `m2b source <name>`; it takes a name, never a path, and reads only fact files and notes of the
  archive ([Noting and searching as tools of the model](docs/band.md#noting-and-searching-as-tools-of-the-model))
  ([#32](https://github.com/Kolibee-GmbH/m2b/pull/32)).
- The pane has a tab `Tasks`: every open task of your list, in groups by when it is due
  (overdue, today, the next seven days, later, without a date), each with `done`, which ticks it
  after five seconds of `undo` ([All your open tasks](docs/band.md#all-your-open-tasks)). The tab
  stands between `Review` and `Facts` ([#32](https://github.com/Kolibee-GmbH/m2b/pull/32)).
- The pane has a tab `Facts`: what every session starts with, each fact with `details`, and every
  topic with its counts. `details` opens the fact's file, with what it rests on: the notes and
  documents behind it ([What m2b knows](docs/band.md#what-m2b-knows)). Behind it is a new command,
  `m2b distillate topics [--json]` ([#32](https://github.com/Kolibee-GmbH/m2b/pull/32)).
- Below a fact's file, `show` on each note or document it rests on opens it: a note's words as you
  captured them and what the curation run added, a document's original name and what stands on
  which page. A PDF or a picture on this machine has `open the file`, which opens it in the
  system's viewer; any other kind is named with where it lies and never started, since a viewer for
  it could run what it holds. The tab of the fact file leads back. Behind the button is a new
  command, `m2b store open <name>`, which opens only a PDF or a picture of the archive whose bytes
  are of that kind, and only where the session has a screen
  ([#32](https://github.com/Kolibee-GmbH/m2b/pull/32)).
- A session keeps a file you name with its path: "keep this contract, ~/Documents/lease.pdf".
  The `capture` skill copies it into the inbox with your words, through the new command
  `m2b capture-file <path> [words]`, and Claude Code asks you before every copy: no skill may run
  it alone, since the file goes into a folder that syncs. A folder, a link, a text file and a file
  over 25 MB are refused; the size is the new setting `capture.file_limit_mb`
  ([Capture](docs/using.md#capture)) ([#32](https://github.com/Kolibee-GmbH/m2b/pull/32)).

### Changed

- What goes into your second brain is yours to decide, also from work. The note and propose
  tools, the text every session starts with and the capture skill name what a note may hold from
  work, who is who, which role, what was agreed, and no longer tell a session never to keep a
  customer's document or what someone told you in confidence. [SECURITY.md](SECURITY.md#what-m2b-handles)
  says where such a document then lies and who reads it
  ([#32](https://github.com/Kolibee-GmbH/m2b/pull/32)).

## [0.7.0] - 2026-11-16

m2b is there in every session: the band's row stands above the prompt also while nothing waits,
calm, as the way into the m2b pane. A setting moves the band below the prompt or shows it only
while something waits, as before. The pane starts a curation run on a press. Nothing is to do
after the update. A session that started before it keeps the band it has until `/reload-plugins`,
and the pane's part "m2b" says so.

### Added

- A setting for where the band stands, `band.place`, in the settings under "What m2b shows":
  `above`, `below` or `waiting` (`m2b settings set band.place below`).
  - `above` is what a machine without an entry has: the band's row is above the prompt in every
    session. While nothing waits and no task is due it is calm, `m2b` and `open` alone, both
    stepped back, so the pane is one press away: Ctrl+X Tab, then Enter, or a click.
  - `waiting` is the band as it was: there only while something waits or a task is due, and
    `/m2b-pane` opens the pane otherwise.
  - `below` leaves the space above the prompt free and puts the band at the end of the hint line
    under it: `m2b`, the counts in their colors, as many as the line has room for (`…` stands
    for the rest), and, under the fullscreen layout, the button `open` for a mouse click; no key
    reaches a button there, so anywhere else the line names `/m2b-pane`. Where the line has not
    room for the first count, m2b's words are added to the engine's own line, stepped back, and
    cut where it ends (`m2b 1 waits for you · /m2b-pane`). The tasks due are counted there,
    never listed
    ([#30](https://github.com/Kolibee-GmbH/m2b/pull/30)).

- `curate now` in the m2b pane: on the machine that curates, the overview's part "m2b" has a
  button below the line that says when m2b last curated. A press waits five seconds with `undo`,
  then starts one curation run in the background, also while curation is paused; the part says
  `curating` while the run goes and names no button then. A press that started no run says why.
  On a machine that does not curate the part says which one does
  ([#30](https://github.com/Kolibee-GmbH/m2b/pull/30)).
- `m2b curate --detach --json` answers the start in the background as data: whether a run
  started and, where none did, why
  ([#30](https://github.com/Kolibee-GmbH/m2b/pull/30)).

### Changed

- The band above the prompt is there in every session unless `band.place` says otherwise: a
  session where nothing waits now shows one calm row, `m2b  [ open ]`, where it showed none.
  `m2b settings set band.place waiting` brings the band of 0.6.0 back
  ([#30](https://github.com/Kolibee-GmbH/m2b/pull/30)).
- `/m2b:m2b doctor` and `/m2b:setup` say what the band shows for each place. Asked about a band
  that shows nothing, the skill `m2b` reads the place with `m2b config get band.place`, which it
  may run without asking, and no longer calls an empty band no fault where the band stands above
  the prompt
  ([#30](https://github.com/Kolibee-GmbH/m2b/pull/30)).

## [0.6.1] - 2026-11-16

### Changed

- The README's first line and the plugin's description say whose second brain m2b is and what it
  has that Claude Code's own memory does not have by default: one store across all your projects
  and machines. The README says near its top what m2b is not, a linked knowledge base, and that
  facts with a last day are rewritten once it has passed. The description no longer says the pane
  sits beside the chat, which holds only under the fullscreen layout
  ([#28](https://github.com/Kolibee-GmbH/m2b/pull/28)).
- `m2b status` counts a proposal you answered apart from those that wait for an answer:
  `1 waiting, 2 answered for the next run, 3 kept, ...`, and `answered` beside `waiting` in its
  JSON. Until now a proposal counted as waiting until the next curation run had filed your answer,
  while `m2b proposals` said that none waits
  ([#28](https://github.com/Kolibee-GmbH/m2b/pull/28)).

### Fixed

- The band of every open session said `m2b could not read the tasks` for up to a minute when one
  session could not reach the task list, for one a session the Claude desktop app started, which
  has no access to Reminders: the sessions share one answer, and the failed one was shared too.
  A session that could not read the tasks now keeps that to itself, and no session takes such an
  answer from another. A session that still runs the band of 0.6.0 goes on sharing its failure
  until `/reload-plugins`; the sessions with the new band no longer show it
  ([#28](https://github.com/Kolibee-GmbH/m2b/pull/28)).
- A topic of the distillate over 4 KB came in with no prompt that named it, and nothing said so:
  a prompt brings whole topics only. Lint now reports such a topic as something to act on, in the
  review of the run, instead of as a size over the 2 KB target
  ([#28](https://github.com/Kolibee-GmbH/m2b/pull/28)).
- The README counted eight eval cases where [Evals](docs/evals.md) has fourteen, and
  [Using m2b](docs/using.md) said Claude Code keeps its own memory per project or user: it keeps
  it per repository, on one machine
  ([#28](https://github.com/Kolibee-GmbH/m2b/pull/28)).

## [0.6.0] - 2026-11-16

The band above the prompt is one row that counts what waits for you, and the m2b pane is where
you answer: keep, drop and `ok` are pressed there, under a row of tabs, and the settings are
sorted by what you want from m2b. Nothing is to do after the update. A session that started
before it keeps the band it has until `/reload-plugins`, and the pane's part "m2b" says so.

### Changed

- The band above the prompt is one row: `m2b`, how many things wait for your answer
  (`4 wait for you`), your tasks due, and one button, `open`, which shows the m2b pane. keep,
  drop and ok are pressed in the pane, where every candidate, question and the review stand
  with their buttons; the band holds no button that writes. The row is the same whether the
  pane is in view or not
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).
- The pane's overview is four parts in one order, each in a frame: "Waits for you", in the
  warning color with the number that waits while something does, "Today", "This session" and
  "m2b". A row is its text and, below it, what you can press; keep and `ok` are the accent, drop
  steps back. A task's title stands at full strength with `due today` or `overdue` in color
  before it. A topic is a button that bears its name. m2b in the session's folder is `on` or
  `off` with `turn off here` and `turn on here`, and the folder breaks only between its folders.
  A count of none is not said, and a part with nothing in it is one dim line. In a pane narrower
  than 36 columns a bar stands in for each frame
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).
- The proposals, the review, a topic's lines and a search are drawn like the overview: parts in a
  frame and rows with their buttons below. A proposal is its text, then keep and drop with what
  it is beside them, then the words it stands on. The review is two parts, the last curation run
  with what it changed, and what of it waits for you. No view has a heading that repeats its tab
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).
- A time is said one way: the time of day for today, the date before. The review's line about
  the last run reads `succeeded, 18:00 to 18:04`, and the note about a failed run names its start
  the same way
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).
- The part "m2b" says how m2b stands: when it last curated and what waits in the inbox while all
  is well, and what is wrong with its reason. That a session runs an older m2b than the installed
  one is said there, no longer in the band
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).
- What m2b says to a press that wrote nothing stands where the press was made, in the error
  color, until your next press there, no longer in the band
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).
- The m2b pane has one row of tabs above every view: `Overview`, `Proposals` with the number
  that wait, `Review` and `Settings`; a topic's lines and a search stand under a fifth tab while
  the pane shows them. The tab you look at is marked, every other turns the pane with one press.
  `back` above the views and `show` and `settings` on the start view are gone. After a press on
  a tab the focus stands on the tab that leads back, and after keep, drop or `ok` on the row's
  `undo`: after drop it stood on keep of the row below
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).
- The settings in the pane are sorted by what you want from m2b, in four parts: "What m2b
  shows", "What m2b reads", "Curation" and "About this setup". In the first three a setting is its
  title, what it does and its values side by side: the value in force is marked (`● count`), and
  a press on another value sets it, with the five seconds of `undo` as before. "About this setup"
  is one row, `22 settings`: a press on it shows what only informs or is changed by a command
  under a tab of its own, each with what changes it. The list by file with `open`, the card per
  setting, `previous`, `next`, `list`, `turn on` and `set to …` are gone. After `undo` and once a
  press is written the focus stands on the nearest button that sets nothing, the tab `Overview`
  or the row of "About this setup", never on a value. `m2b settings --json` names the groups
  under `groups`, and each setting's `group` and `place` in it; as text the list stays under the
  three files
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).
- The status line under the prompt says only what is wrong with m2b, such as `last curation run
  failed` or `calendar not reachable`, and is gone while nothing is. Claude Code draws a plugin's
  status line as a warning, so `0 in inbox · curated 18:02` warned in every session
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).
- `band.due_tasks` takes three values in place of on and off: `off`, `count` and `list`, and is
  `count` where the config names none. A config that holds `true` reads as `list`, `false` as
  `off`. `m2b band --json` names the tasks due in `tasks.due_by_today` whatever the band shows
  of them, and the machine's `band` settings in `band`. With `count` the band names how many
  are overdue and due today, with `list` the first three by name below its row, each with
  `overdue` or `due today` in color and its title at full strength; with `off` none. The pane
  lists them whatever the setting says
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).

### Added

- `band.topics`, a switch that is off until you turn it on: whether the band's row says how
  many topics m2b gave the session. Before, a row of its own said it in every such session
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).

### Fixed

- Asked about someone your notes do not know, Claude says so and no longer names a customer or a
  topic of your notes as a possible connection: the search tool and the search skill say it
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).
- The setup skill and `/m2b:m2b doctor` no longer call a band that shows nothing, or an empty
  status line, a fault, and the todos skill names the m2b pane as the place where candidates and
  questions are answered
  ([#27](https://github.com/Kolibee-GmbH/m2b/pull/27)).

## [0.5.0] - 2026-11-15

A session can hand in a proposal for your memory by itself. That is off until you turn it on.
Before you do, update m2b on every machine that shares the store: an m2b before this release
takes in nothing a session handed in, and on the curating machine its run stops at its start
while such a file is not downloaded.

### Added

- `m2b proposals add` takes a proposal a session hands in by itself, with the words it stands on,
  and checks them against that session's transcript before anything is written: the quote must
  stand in one text of the session, and the proposal says whether the person typed it, pasted it,
  a tool returned it or Claude wrote it. A session that worked in a folder or repository you
  leave out hands nothing in. It is off until you turn it on, with a press on its card in the m2b
  pane or with `m2b config set sessions.propose true` in a terminal of your own; in the shell of a
  Claude Code session that command refuses
  ([What a session hands in](SECURITY.md#what-a-session-hands-in),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- With that setting on, the band's mod gives the model a third tool, `mcp__m2b__propose`. The
  model calls it by itself when a session states who someone is, an agreement, a commitment of
  yours or something about your own life that your memory does not hold, also where the words
  stand in a mail or a document it read for you. The tool passes the proposal with the id of the
  session to `m2b proposals add` and answers with its line. It runs without a permission
  question; a rule of yours for `Bash(m2b proposals:*)` or for the tool's name comes first. Only
  the main conversation hands in, not a subagent, and the setting is read when a session
  starts. The tool's description, about 3,200 characters, is in the prompt of every session
  that has it
  ([Handing in a proposal](docs/band.md#handing-in-a-proposal-a-tool-you-turn-on),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- Every curation run that reaches its step for the proposals takes in what sessions handed in,
  whether or not it reads your sessions: each proposal then waits in the list with the others.
  It says that a session handed it in, also where its words were typed, and its line reads
  `in a result of <tool> on <day>` or `Claude wrote on <day>` for words a tool returned or
  Claude answered. The run reads no transcript; it checks the form again, takes the ten
  earliest of one session and removes the others, and leaves out what you captured yourself
  since the day before that day and what is like a proposal that waits, was answered or
  expired, so the same fact from several sessions waits once
  ([What a session hands in](docs/curation.md#what-a-session-hands-in),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- `m2b status` counts the proposals per way they came, a reading or a session, and per source of
  their words: how many wait and how many were kept, dropped and expired in the last 30 days,
  also on a machine that only lets sessions hand in; `--json` has them under
  `proposal_answers.ways`. In `m2b proposals --json` and `m2b band --json` each proposal names
  its `tool` and who proposed it, `by`
  ([#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- `/m2b-pane` opens the m2b pane in a view of three parts: what m2b gave this session (each topic
  with its facts lines and current items, how the start printed the distillate, whether the
  distillate is off for the folder, and how many notes the session wrote), what waits for you (the
  proposals, the memory candidates and questions with keep and drop, the review with `ok`) and the
  tasks due today. A topic that comes in with a prompt shows there while the turn still works
  ([The band](docs/band.md#this-session-what-waits-and-today-in-the-pane),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- Under the fullscreen layout the m2b pane opens by itself beside the conversation, in its start
  view and without taking the keyboard. Closing it there by hand keeps it closed, also in later
  sessions, until you open it again with `/m2b-pane`, another command that shows the pane or
  `show` in the band. On the main screen, where a pane is a block above the prompt, it still opens
  only when asked
  ([The band](docs/band.md#it-opens-by-itself-beside-the-chat),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- While the m2b pane sits beside the conversation in its start view, the band above the prompt
  steps back to one line, so nothing stands twice: why a press wrote nothing, the hint of an older
  band or an error where there is one, and else the counts of what needs an answer (`Waits for
  you: 2 to keep or drop, 1 proposal from your sessions, the review`). Where the pane is not in
  view (the main screen, a terminal too narrow for it, after you closed it, behind another
  plugin's pane) the band keeps every row and gets one more, `2 topics given to this session`,
  whose `show` opens the pane ([The band](docs/band.md#the-band-beside-the-pane),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- Minimized to its small form in the desktop app, the m2b pane draws three counts and no button:
  the topics this session was given, what waits for you and the tasks due
  ([The band](docs/band.md#the-band-beside-the-pane),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- In the pane's start view, `leave m2b out` turns the distillate off for the session's folder,
  after five seconds in which `undo` takes the press back, and `turn on` brings it back. It is
  `m2b distillate off` and `on` for the folder the pane names, one press away from where you see
  a customer's facts in a session about something else
  ([The band](docs/band.md#leaving-m2b-out-of-a-folder),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- `show` beside a topic in the start view shows the topic's facts and current items, as the
  distillate holds them now. The band keeps them only while the pane shows them: they are in no
  text its commands answer, not in the session's state and in nothing handed to the model
  ([The band](docs/band.md#a-topics-lines),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- `/m2b-settings`, or `settings` at the end of the pane's start view, shows every setting of
  m2b in the pane: a list under this machine, the store and the owner, and a card per setting
  with what it does and what changes it. `previous` and `next` walk through all of them, and with
  the keyboard in the pane Enter on `next` goes from card to card: the band puts the focus on the
  button that leads on, never on a switch. A switch is pressed on its card, waits five seconds
  with `undo` and is then written by `m2b settings set`; what the command refuses stands on the
  card ([The band](docs/band.md#every-setting-in-the-pane),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- The card of `sessions.propose` turns handing in on by a press, where the pane is drawn in a
  terminal, the desktop app or VS Code: the one setting a session's shell does not turn on
  needs no terminal outside Claude Code. In the mobile app the card names the command for
  such a terminal. The press is a threshold in the band and no boundary: nothing says who
  pressed, so another plugin, a client attached to the session that names itself the terminal,
  the desktop app or VS Code, or whatever types into your terminal or steers your screen can
  pass it ([Security](SECURITY.md#what-a-session-hands-in),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- `m2b settings` lists every setting of the three files, this machine's, the store's and the
  owner's: its value, its default, what it does and how it is changed, by a command, by a setup
  skill, by hand or not at all. A list, the paths of programs and an add-on come as a count or as
  on and off,
  never with what they hold, and a text from a file your other devices can write comes on one
  line, with a line break or an escape sequence written out. `--json` gives the same for a program
  ([Configuration](docs/configuration.md#every-setting-in-one-list),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- `m2b settings set <key> <value>` changes a switch to one of its values: `curation.read_sessions`,
  `curation.paused`, `curation.git_commit`, `band.due_tasks`, `sessions.propose`, `curation.model`
  and the profile's `language`. Every other key is refused with one line that names what changes
  it. It refuses what `m2b config set` refuses, in the same words: where `CLAUDECODE` is set, as
  it is in the shell of a Claude Code session, neither turns `sessions.propose` on
  ([#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- `m2b band --json --session <id>` says what m2b gave a session since its last start: the topics
  whose facts it got, each with the facts lines and current items it held when the session got
  it, and whether that start printed the distillate whole, cut or not at all, or the distillate
  is off for the folder. The session start and the prompt hook note this on the machine as they
  give it, so it is known for sessions that start from this release on
  ([The band](docs/band.md)). It names the session's folder under `distillate.folder`. With
  `--session-only` the answer is that part alone, without a look at the task list, the calendar or
  the store
  ([#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- `m2b distillate topic <name>` prints one topic's facts and current items from the distillate
  ([Commands](docs/commands.md),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).

### Changed

- `m2b proposals keep --all` and the pane's `keep all` leave the proposals a session handed in,
  and the command says how many: an agent worded them from what it read, so each is kept or
  dropped by its id, or with its own row in the pane
  ([#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- `proposals.json` has format 3 while it holds a proposal a session handed in. An m2b before this
  release on another machine then says "update m2b on this machine", where it would show that
  proposal as said and write it back without who proposed it. Without such a proposal the file
  keeps the format it had
  ([Proposals from your sessions](docs/store-format.md#proposals-from-your-sessions),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- Where the store is a git repository, a handed-in proposal is committed with the waiting
  captures before a run's first step, so taking a run back puts it where the next run takes it in
  again ([A commit per run](docs/curation.md#a-commit-per-run),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).
- The review, a search and the proposals are views of the m2b pane now: Escape, the close mark or
  the new `back` button above them lead back to the start view instead of closing the pane
  ([The band](docs/band.md#back-to-the-start-view),
  [#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).

### Fixed

- The reading of your sessions passes over a transcript line that is nested deeper than Python
  reads, as it passes over a line that is no JSON. Such a line failed the reading before
  ([#26](https://github.com/Kolibee-GmbH/m2b/pull/26)).

## [0.4.5] - 2026-11-15

### Changed

- The reading of your sessions takes what you pasted into a prompt too. Until now a pasted block
  was left out with what it held, because a mail or a document is somebody else's text. A longer
  text of your own, written elsewhere and pasted, arrives the same way and was lost with it, and
  who is who at a customer often stands in such a text. Now a prompt goes to the model with what
  you typed and what you pasted kept apart, 2,000 characters together, the typed text first. A
  proposal says where its words stand: `said on <day>` before words you typed, `pasted on <day>`
  before words from pasted text, which may be someone else's. Code finds that; the model is not
  asked. The line names where the quote stands, not who led the model to the proposal: text you
  pasted can lead it to a proposal that quotes words you typed, so read every proposal before you
  keep it, and before `m2b proposals keep --all`. A proposal that waited before reads as said.
  `proposals.json` keeps its format until a proposal stands on pasted text; from then on an m2b
  before this release on another machine says "update m2b on this machine", where it would show
  that proposal as said
  ([Reading your sessions](docs/curation.md#reading-your-sessions),
  [#25](https://github.com/Kolibee-GmbH/m2b/pull/25)).

## [0.4.4] - 2026-11-14

### Fixed

- The worklog is written after a day with many sessions too. Its model step got the facts of the
  period as the output of a command, and Claude Code hands a model such an output only up to a
  size: a larger one it saves in its own folder, which the step's fence does not let it read. The
  step stopped, no worklog was written, the watermark stayed, and the next run had more facts
  still. Now the facts are a file in the worklog's run folder that the step may read, in parts
  when the period was long, and `m2b-worklog facts` names the file and prints no fact. With
  Claude Code 2.1.325 and invented facts, 41 KB stopped the step before and are judged now, and
  122 KB in 2033 lines are judged, every session
  ([What it reads](docs/addons/worklog.md#what-it-reads),
  [#24](https://github.com/Kolibee-GmbH/m2b/pull/24)).

## [0.4.3] - 2026-11-14

One fix needs a step from you. If the `.git` in your store folder is a file, because you keep
its repository outside a synced folder, name that repository once on the curating machine after
the update, or its runs stop committing: `m2b config set curation.git_directory <path>`;
`m2b doctor` shows the path in its line `store-git`. The third entry says why, and what to do
where `.git` is a symlink.

### Fixed

- A symlink in the store is never read or followed. Until now a symlink to a file was read like
  the file: one in `inbox/` that points at any file of the curating machine had its target's bytes
  copied into a note by the next curation run, and one in the place of `memory/MEMORY.md` was
  printed at every session start, with no model taking part. A symlink in the place of a folder,
  `inbox/` itself for one, was entered the same way. Whoever can put a file into the store can put
  a symlink there: a sync service brings what another device or an integration wrote. Now m2b
  lists and reads no symlink below the store's folder and writes through no folder that is one, a
  file is opened so that a symlink taking its place in that moment is not followed either, and
  lint names each symlink in the review task. The store's folder itself may be a link. The
  worklog's reading of the inbox keeps the same rule. `scripts/fence-probe` now also asks Claude
  Code whether a step's Read of a symlink that leads out of the store is refused; with Claude Code
  2.1.325 it was ([Security](SECURITY.md#untrusted-input),
  [#23](https://github.com/Kolibee-GmbH/m2b/pull/23)).
- Reverting a run's commit no longer deletes a capture the run never touched. The commit held
  every file that changed while the run ran, so a capture that was taken or synced in during those
  minutes and still waited in `inbox/` at the end was in it as a new file. `git revert` on that
  commit deleted it from the store folder, and a sync service carried the deletion to every
  device; the text stayed in git. Now a capture that came into `inbox/` during a run and still
  lies there stays out of the run's commit. It shows as untracked until the next run commits it
  before its first step, like every capture git does not know yet. What the run adds to a capture
  that was there when it began still goes in: the new name it gave it, and the note and the
  reading copy it put beside a picture or a PDF
  ([A commit per run](docs/curation.md#a-commit-per-run),
  [#23](https://github.com/Kolibee-GmbH/m2b/pull/23)).
- A run follows a `.git` file in the store folder only to the git directory this machine's
  config names. A store in a synced folder keeps its repository outside, and the `.git` file in the
  store folder names where; git followed that line, and whoever writes the store can rewrite it,
  so a run could be made to commit your notes into another repository, or into a folder whose
  configuration names commands git then ran. Now m2b reads the line itself and commits only into
  the directory `curation.git_directory` names; otherwise the run commits nothing, starts no git
  for a commit, and its review task and `m2b doctor` say why. **If your store has such a `.git` file**, name
  its directory once on the curating machine, or runs stop committing:
  `m2b config set curation.git_directory <path>`; `m2b doctor` shows the path the file holds in
  its line `store-git`. The directory must lie outside the store folder; one inside it, or
  reached through a link in it, is refused, because it would be as open to every writer of the
  store as the file is. A `.git` folder in the store folder needs nothing. A `.git` that is a
  symlink is no longer followed, and runs stop committing there too: put a `.git` file with the
  line `gitdir: <path>` in its place and name the directory as above
  ([A commit per run](docs/curation.md#a-commit-per-run),
  [#23](https://github.com/Kolibee-GmbH/m2b/pull/23)).
- No git that m2b starts reaches a remote or starts a program a repository names for signatures.
  The commit of a run could fetch: in a store that was a partial clone, git fetched the objects
  it lacked and ran the command the repository named for that. The worklog's `git log`, run in
  every folder a session ran in, started the `gpg.program` of a repository that asked for
  signatures to be shown. Now every git m2b starts, for the commit, for a folder's remotes and
  for the worklog's commits, gets the same settings: no hook, no file-system monitor, no
  signature check, every transport closed and no fetching of missing objects. A store that is a
  partial clone is not committed into, and the review task says so
  ([Security](SECURITY.md#what-m2b-handles),
  [#23](https://github.com/Kolibee-GmbH/m2b/pull/23)).
- A reason that quotes bytes that are no UTF-8 no longer keeps a run from writing its record
  and its review, or `m2b doctor` from printing. A file name or a program's message with such
  bytes reaches a text as half a character, which cannot be written: a commit that failed over
  such a file name kept the run record from being written, and `m2b doctor` ended in an error
  where it should have named the cause. Such a character is now written as `?` in the run
  record, the review task and the run's notes on the machine, and printed as `?` in what `m2b`
  prints to standard output; an error message shows it escaped, like `\udcff`.
  Filing a capture whose own name is no UTF-8, which Linux allows and macOS does not, is not
  covered by this
  ([#23](https://github.com/Kolibee-GmbH/m2b/pull/23)).
- The worklog reads a commit whose author time has no offset from UTC on Python 3.9 and 3.10
  too. git writes such a time with a `Z`, which Python reads only from 3.11 on, so the commit was
  left out of the day ([#23](https://github.com/Kolibee-GmbH/m2b/pull/23)).

## [0.4.2] - 2026-11-13

### Changed

- An install no longer brings m2b's Python tests. Claude Code copies the plugin's folder whole,
  and until now 86 test files came with it; they moved to `tests/unit/` in the repository. The
  installed plugin has 220 files instead of 306 and 1.2 MB instead of 2.5 MB. The band's tests and
  the eval cases stay in the plugin's folder, where Claude Code looks for them. Nothing m2b does
  changes ([#22](https://github.com/Kolibee-GmbH/m2b/pull/22)).

## [0.4.1] - 2026-11-12

### Added

- Say in a session that a task is done, "I returned Sam's ladder, tick it off", and the todos
  skill ticks it, without Claude Code asking first: it finds the task in your list, asks when more
  than one fits, and writes no note about it ([Security](SECURITY.md#the-tools-the-model-calls)
  says how to have it ask). Until now no skill knew such a sentence; asked that way, a model
  searched the notes or wrote a note that the task was done, and the task stayed open. A
  model-level scenario, `E26-tick-a-task`, holds it
  ([#20](https://github.com/Kolibee-GmbH/m2b/pull/20)).

### Changed

- The README is a little more than half as long. One table says what you can say and what
  happens then, the band is shown with a picture of its pane, and the detail moved to three new
  pages: [Using m2b](docs/using.md), [Troubleshooting](docs/troubleshooting.md) and
  [Cost and privacy](docs/cost-and-privacy.md). It no longer compares m2b with other memory
  projects by name; what m2b does not do stands under [Limits](README.md#limits). It shows the
  state of the checks on `main` ([#20](https://github.com/Kolibee-GmbH/m2b/pull/20)).
- The pictures are recorded again, and two new ones show the band's pane: the review of a run
  that changed a fact, and the proposals from your sessions
  ([The band](docs/band.md#the-whole-review-and-search-in-a-pane))
  ([#20](https://github.com/Kolibee-GmbH/m2b/pull/20)).
- The license and the plugin's manifests name Kolibee GmbH as the holder of the copyright and as
  the author, where they said "m2b contributors"; the license stays MIT
  ([#20](https://github.com/Kolibee-GmbH/m2b/pull/20)).

## [0.4.0] - 2026-11-12

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
  obsidian-second-brain and basic-memory, and says where each does more than m2b
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
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
  both, and a copy that differs from its original is never removed
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- `m2b lint` names a conflict copy of a task file, where the tasks are Markdown files, in a store
  on either backend. A task ticked on one machine and changed on another leaves two files, and
  until now the copy was passed over without a word: nothing said that a second state of the
  task existed. Lint reports the copy as it reports one in the archive: as an action when it
  differs from the task (keep one of them), as an info when it equals the task, or when the two
  were not compared because one is not downloaded or cannot be read. `m2b lint fix` and the lint
  step of a curation run remove a copy that equals its task byte for byte and nothing else: the
  task and a differing copy stay as they are. With Reminders as the tasks backend a `tasks/`
  folder left in the store is not looked at ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- `m2b doctor` has a line `store-git`. It says whether the store folder is a git repository and,
  on the machine that curates, where the git directory lies that a run commits into and which
  git named it. `cannot commit` with the reason counts as a problem: a `.git` in the store folder
  on a curating machine without git, where a run commits nothing and says nothing, a `.git` that
  is not downloaded, a repository git cannot read, or one whose work tree is another folder.
  Where the folder holds a `.git` and this machine does not curate or has `curation.git_commit`
  off, the line says so and git is not started. The git directory and git's reason are printed
  with invisible characters written out, because both come from the `.git` in the store
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- `m2b doctor` has a line `prompt-hook`. The hook that brings a topic's facts before a prompt says
  nothing when it fails, so that no prompt waits or breaks for it; one that never worked looked
  the same as a prompt that named no topic. Doctor now starts it the way Claude Code does, within
  the same time limit, and reports `answers`, or `does not answer` with the reason (the distillate
  is not downloaded, the config is broken, Python is not found), or `missing`
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- A curation run started in the background, at a session start or with `m2b curate --detach`,
  keeps what it writes on standard error in `~/.local/state/m2b/detached-run.err`, replaced at
  each such start. Until now that output was discarded, and a run that died before it could write
  its record left no reason behind ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
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
  ([Taking a run back](docs/curation.md#taking-a-run-back) names what a revert does not put back)
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
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
  it is updated ([Store format](docs/store-format.md#memory))
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- [Evals](docs/evals.md) shows what m2b does to Claude's answers, measured: the score of each of
  the eight eval cases with m2b and without, and the model, the Claude Code version and the day of
  the run. Until now the scores a release was checked with were written down nowhere
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
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
  ([docs/addons/worklog.md](docs/addons/worklog.md#leaving-work-out))
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
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
  scenario, `E23-proposals-from-sessions`, runs it from setup's yes to the filed capture
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- A proposal from your sessions that got no answer for 14 days expires: it waits no longer, does
  not count as dropped and is not proposed again for 90 days; `m2b proposals keep <id>` still keeps
  it in that time. Every curation run does this and removes the proposals kept, dropped or expired
  90 days ago, whether or not it reads the sessions. `m2b status` says what share you kept of the
  proposals you answered in the last 30 days and how many expired, and `m2b status --json` adds the
  counts per kind since the first reading: proposed, kept, dropped, expired, and refused because
  the words they quote do not stand, with at least three words, in a prompt of the session they
  name ([docs/curation.md](docs/curation.md#reading-your-sessions))
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The reading of your sessions learns from your answers: it shows the model up to 30 proposals you
  kept and up to 30 you dropped, those a run settled last, each with its kind, its text and your
  words, and tells it to leave out what is like something you dropped. Expired proposals are not
  shown. On the invented day of `scripts/glean-eval`, which now holds five kept and four dropped
  proposals and one sentence like the dropped ones, `haiku` and `sonnet` proposed that sentence in
  six of six answers without the examples and in none of six with them, and found all twenty
  planted statements either way; `scripts/glean-eval --without-examples` measures the day without them
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- `m2b config set curation.paused true` pauses curation on a machine: no session start and no
  schedule starts a run there until the setting is `false` again. Until now the only ways to stop
  the background runs were to turn the plugin off, which also takes capture and the distillate
  away, or to move curation to another machine. A paused machine still captures, its sessions
  still get the distillate, and `m2b curate --force` still files the inbox when you ask for it;
  `m2b status` has a line `paused`, and a scheduled `m2b curate` shows there as
  `last attempt: paused at ...` ([Pausing](docs/curation.md#pausing))
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- [Commands](docs/commands.md) is a new page with everything you can say, type after a slash or
  run as `m2b`: what to say in a session, the skills (`/m2b:search`) and the band's commands
  (`/m2b-search`) with what tells them apart, every `m2b` command with one line, and the exit
  codes. The README lists the ten used most, `m2b tasks list` and `m2b tasks complete <id>` among
  them, which is how a Markdown task is ticked ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- `m2b --version` prints the version, also on a machine that is not set up. The bug template asks
  for it ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- A command that groups actions, such as `m2b lint`, `m2b tasks` or `m2b setup`, prints its help
  when it is named without an action. Until now it ended with a usage error and exit code 2
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).

### Changed

- `m2b curate` answers a run in two lines. After the line that says how the run ended comes what
  it did to the inbox, such as `inbox: 3 captures filed, 0 waiting`; when a run that ended well
  left something in the review task, the line says so. Until now the answer was
  `the curation run succeeded` alone, and whether anything was filed took a second command. Filed
  counts what reached the archive, so a ticked "Remember? ..." candidate the same run filed is in
  it. An answer without a run (not due, paused, `--detach`) is one line as before. A script that
  compared the whole output must take the second line into account
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- On a machine that is not set up, a command's answer names both ways in: `/m2b:m2b setup` in
  Claude Code and, without Claude Code, `m2b setup apply` with the address of Getting started.
  Until now it named only the first, which whoever tries m2b from a checkout does not have
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The README explains six more of its words (fact file, review task, proposal, memory candidate,
  mod, herdr), shows under Troubleshooting what `m2b doctor` and `m2b status` answer on a healthy
  machine and which of their lines only look like a problem, and names two more things to remove
  when uninstalling: the marketplace and the `PATH` line. [Security](SECURITY.md) opens with five
  lines that sum it up and says that reports are taken for the latest release.
  [Getting started](docs/getting-started.md) lists the folder with the copies of `memory/` a run
  keeps on the machine ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The README has a quick start right below its first screen, says what Claude Code prints when
  the install is done, says where m2b stands (young, in daily use by its author on macOS, Linux
  covered by the tests), that a run's usage is recorded nowhere, that the band's two tools run
  without Claude Code's permission prompt, and how to report a bug. It no longer says a session
  keeps your words "verbatim": the note is in your words without the request around them. It
  also says that a run can file facts under a topic,
  and that a session then starts with the topic's name only
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- [The curation run](docs/curation.md) has a section "Correcting what a run filed": a wrong fact,
  a fact under the wrong topic, a finding of lint in the review task, a note that should never
  have been kept. It also says to commit the store once before the first run commits into it:
  reverting the first run that touched a file git had never seen deletes that file, the
  distillate for one ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- lint's finding about a topic's words names the file and says where the words stand: "in
  memory/MEMORY.md, the topic Trip has 1 word in the brackets of its heading; it needs 2 to 5".
  Until now it read "the topic Trip has 1 words; it needs 2 to 5"
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- [Getting started](docs/getting-started.md) says after each step in Claude Code what you should
  see and what to do when you do not, and which session knows a new fact: the session start after
  a capture starts the run, and the session after that one starts with the fact. The times in it
  are measured: 15 seconds for a setup with every answer given at once, 13 seconds for a run over
  one capture ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- `m2b search` prints nothing from the store with a character that draws nothing, as text and
  with `--json`: zero-width characters, marks that reorder text, variation selectors, soft
  hyphens and tag characters are gone from a hit's text, the joiners emoji and several scripts
  need stay. In a file's path, in
  the command that fetches a file and in the reason a file could not be read, such a character
  is written out as `<U+200B>`. A session that searches through the skill's command read a hit
  as it was stored until now, with whatever such a character carried
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- A proposal from your sessions whose topic is longer than the 60 characters a topic's name may
  have is left out and counted with the entries that are not in the form, like one whose text is
  over 300 characters ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- A curation step that fails over what it wrote to `memory/` names the line by its file and line
  number ("line 5 written to memory/MEMORY.md holds U+200B"), no longer by its text, and does not
  name a file the step added, whose name the model chose. `m2b status` and the review task show
  that reason to a session that asks, and a quoted line carried whatever a capture had made the
  model write. The notices at session start now go out without invisible characters, like the
  distillate below them ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The session start says of a failed curation run when it failed and in which steps ("failed at
  2026-11-07 03:05 in ingest; m2b status says why"), no longer why. The reason can repeat what a
  model said when its run broke, the end of what an add-on's command printed or a file's name, and
  the notice stands in m2b's own voice above the line that marks the distillate as data.
  `m2b status` and the review task show the reason as before. Of a run that left no record the
  notice names the run log, and of a run record that cannot be read it quotes no value
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
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
  ([SECURITY.md](SECURITY.md#the-fence-around-a-model-step))
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The session-start and prompt hooks take every character that draws nothing out of the
  distillate before a session reads it, not only those that hide or reorder text: also soft
  hyphens, fillers, direction marks and variation selectors, which can carry bytes nobody sees.
  The core and the band now keep one table of these characters (what Unicode calls default
  ignorable, without the two joiners emoji and several scripts need), so the model's search tool
  and the hooks remove the same ones. What undoes a curation step stays as it was: a selector
  after an emoji or a soft hyphen in a pasted text is no reason to fail a run
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- `m2b search` answers with what is curated first: hits from `memory/` (the distillate, then the
  fact files), then from the archive, then from the inbox, and in the archive and the inbox the
  newest note first, by the time in the note's name. Before, hits came in the order the files are
  read: the inbox, the archive from its oldest note on, memory last. The `/m2b-search` pane and
  the model's search tool show the first 100 hits, so a word with more hits than that showed the
  inbox and the oldest notes and left out memory
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The worklog proposes nothing for your memory any more and adds no task. Its model step judged
  prompts cut at 240 characters and proposed at most three facts a day, each as a task
  "Remember? ..."; what your sessions hold for memory comes from the curation run's reading of
  your sessions, once you turned it on, with your own words beside each proposal
  ([docs/curation.md](docs/curation.md#reading-your-sessions)). The worklog keeps topics, time
  spans and booking proposals. Its verdict names the sessions only, its note has no part
  "Proposed for memory", and its model step no longer reads your task list. "Remember? ..." tasks
  work as before for a fact proposed with `m2b tasks add --candidate`
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The worklog takes as your prompts only what you sent. What Claude Code marks as sent by a
  plugin, a finished task or another session is no prompt in the facts its model step judges,
  while its time still counts as work; before, a plugin that drives a session filled the session's
  prompts with its own tasks. A prompt without the mark, from a Claude Code before the mark,
  counts as yours ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The model's note tool runs without asking only for a note in your own words: every word of it
  stands in one prompt you submitted in the session, in any order, apart from additions of up to
  four words in square brackets. For any other note Claude Code asks, as it does for a tool no rule
  allows. Before, the mod let every note run, so text the model had read elsewhere, such as a web
  page, could become a note without you seeing it. The `capture` skill's command is unchanged
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The curation run treats what a capture says as data. A capture that gives instructions to
  whoever files it (to replace or delete facts, to write a given line or rule into memory, to run
  a command) is not carried out: nothing from it is filed, it goes into the archive as written, and
  the review names it, so you can capture what is true in your own words. The refresh step and the
  worklog's verdict follow the same rule for the text they read. A new model-level scenario,
  `E17-planted-capture`, checks it with two captures written to steer the run
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).

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
  runs; `sonnet` did before and after. No run of either model counted from the day of the run
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- A question in one language over notes in another is answered in the language of the question.
  The search tool's description and the skill `search` already said so, and a session still
  answered an English question in German about one time in six where the distillate and the
  note were both German. The search tool now takes `question_language`, the language the
  question was asked in, and its result ends with a line that names it as the language to
  answer in. With it, 100 of 100 sessions on Sonnet answered in English; a sentence alone, at the
  end of the result or at the session's start, did not change the rate. The skill's command,
  used where the mod does not run, answered in English in 30 of 30 and is unchanged
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- Only a file is the original of a conflict copy. A folder with that name beside the copy was
  taken for the original, and comparing the two failed with a read error; a symlink with that
  name that pointed at the copy compared equal to it, so the copy, the only bytes, was removed
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- A conflict copy or an original that cannot be read no longer stops lint, the curation run's
  look at the inbox or the Markdown tasks: the pair is not compared, the copy stays, and lint
  says so in its finding ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The worklog's redaction also finds credentials as tools and environments write them: the value
  of `PGPASSWORD=...`, `SECRET_KEY: ...`, `AccountKey=...` and other names that hold password,
  secret, token or a kind of key, the password in a URL and after `curl -u name:`, and AWS access
  key ids. Commit subjects are redacted like prompts; before, they went into the note as written.
  `curl -u name:pw` no longer loses the URL after it while keeping the password
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The worklog finishes an unfinished worklog only when the note's name in `intent.json` is one the
  worklog gives a note. Before, it joined any name to `inbox/`, so a changed `intent.json` in the
  synced store could create a file outside the store on the machine that curates. Such a file now
  counts as unreadable and nothing is written ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The worklog no longer puts a temporary file into the store's folder while it writes its note, the
  ledger, the two exports, the watermark or `intent.json`. It writes them with the code the core
  writes the store with, from a temporary file in `~/.local/state/m2b/tmp/`, so a synced store sees
  neither half a file of the worklog nor a leftover after a crash; only when that folder is on
  another volume than the store, a hidden temporary file stands beside the target while it is
  written. A new file of the worklog now gets the mode your umask gives, like every other file in
  the store, where it was readable by you alone before
  ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).
- The worklog starts git only when it starts without asking you anything. On a Mac without the
  developer tools, `/usr/bin/git` is a stand-in that opens a dialog offering to install them, and
  the daily worklog, which runs in the background, started it for every session's commits and
  remotes. Now it asks once per run which git there is to start, as the commit of a curation run
  and the session-start hook already did, and without one starts none: the note says under "Could
  not read" for each session whose folder is still there that this machine has no git to start,
  and while you leave work out by git remote, a folder's repository is known only by what a
  session start noted for it ([#19](https://github.com/Kolibee-GmbH/m2b/pull/19)).

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
