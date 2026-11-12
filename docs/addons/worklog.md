# The worklog add-on

The worklog needs [herdr](https://herdr.dev) 0.9 or later, running on the curating machine: herdr
is where it sees which workspace is in use and when an agent works. It is one of the
[add-ons](../addons.md) of m2b, off until its setup turns it on.

## What it does

Once a day it writes a worklog of your sessions: for each session its topic and state, time spans
per sphere of work, and booking proposals for billable spheres. The note lands in the inbox like any
capture and is filed into the archive by the same run, so the distillate's Current section sees your
day. The time spans also go into a ledger in the store, with CSV and XLSX exports. It proposes
nothing for your memory and adds no task: what your sessions hold for memory is proposed by the
curation run's own [reading of your sessions](../curation.md#reading-your-sessions), once you
turned that on.

## Spheres

Spheres are the areas your work falls into, such as an employer, a company of your own and private
projects. Each has an `id`, a `label`, whether its time is `billable`, and how it is recognized:
parts of the URL of the `origin` remote (`git_remote_contains`, compared without regard to case and
in both spellings of an SSH address) and folders under your home folder (`path_under`).
A session that matches none falls to the default sphere, the one with `"default": true`. A sphere
other than the default with neither is never matched, so its time lands in the default sphere. With
invented names:

```json
{"id": "acme", "label": "Acme Ltd", "billable": true, "match": {"git_remote_contains": ["github.com/acme-ltd/"], "path_under": ["~/code/acme"]}}
```

The spheres live in `profile.json` in the store, beside the list of customers a booking proposal may
name. The worklog only reads that list; it never adds to it.

## Leaving work out

Work whose prompts and commits must not reach your store at all, such as a customer's under a
confidentiality agreement, is named in the profile: by its folders under your home folder, by a
part of the URL of its repository's git remote, or by both.

```bash
m2b profile set worklog_leave_out.path_under '["~/code/globex", "~/worktrees/globex"]'
m2b profile set worklog_leave_out.git_remote_contains '["git.globex.example/", "github.com/globex-ag/"]'
```

What ran in such a folder, in any folder below it, or in a folder of such a repository is in no
worklog: a session there is not in the facts the model step reads, not in the note and not in the
ledger, and a transcript from there is left out also where another session's pane worked in it.
Its time is in no time span either, so the ledger shows a gap. The worklog still reads these
transcripts and recordings to learn where a session ran; it keeps nothing of them.

### By git remote

A remote names a repository once, in every folder it is checked out in, so no worktree is
forgotten. Every remote of the repository counts, `origin` or not, and so does the address a
remote is pushed to when that is another one. A part is compared without
regard to upper and lower case, and one written like a web address also finds the SSH spelling:
`github.com/globex-ag/` finds `git@github.com:Globex-AG/portal.git`. A remote counts as your git
configuration writes it and as git rewrites it (`url.<base>.insteadOf`), so the address
`git remote -v` shows is found too.

A worktree is often gone by the time the worklog runs, and then nobody can ask git there. So on a
machine that reads sessions (this add-on on, or `curation.read_sessions`), every Claude Code
session notes the remotes of the folder it starts in, in `~/.local/state/m2b/session-remotes/`:
on this machine only, never in the store, and without the user name or token a URL may carry. The
worklog takes what was noted for a folder and what git says there when it runs. What to know:

- **Work whose repository nobody can tell is left out too**, while you name a remote: a folder
  for which nothing was noted and where git says nothing, because it is gone, git does not
  answer or the machine has no git to start. It cannot be shown to be other work. The note says under "Could not read" in how many
  folders that was; it does not name them. This meets a worktree that is gone and in which no
  session has started since this machine notes remotes, and a herdr workspace in which no Claude
  Code session ever started.
- **A session counts by the folder it started in.** One that starts in a folder above the
  repository, or in another repository, and works in the confidential one through commands is not
  found by its remote; name the folder it starts in.
- **A remote stays noted for 30 days** after it was last seen in a folder. A folder you reuse for
  other work stays left out that long.
- **A repository without a remote** cannot be named by one; name its folder.

### By folder

- **Name every folder the repository is checked out in**: the clone and the folder your worktrees
  live in. A folder counts as it was recorded, so a worktree that is gone by the time the worklog
  runs is still left out; no symbolic link is followed and the spelling counts, upper and lower
  case included.
- **A commit made in the repository while no session there was at work** can still appear under
  another checkout of the same repository that is not left out.

### Either way

- **Commits.** A commit made in a session left out is shown by no other session.
- **A pane of another workspace** that changes into such a folder keeps adding its time to that
  workspace's session; its prompts are left out.
- **Every machine needs this version.** The profile is written as version 2 once it holds the
  setting. An m2b from before reads it without the setting and says to update when asked to
  change the profile, so update every machine that shares the store, the curating one first.

The setting holds from the next worklog on; what earlier worklogs wrote stays as it is. To take it
back, set a list to empty: `m2b profile set worklog_leave_out.path_under '[]'`, and the same for
`git_remote_contains`. `m2b profile merge` with `worklog_leave_out` replaces both lists at once.

## Time spans

A time span is when a workspace was in use: an agent at work, the workspace in focus, or messages
in its transcript at most 15 minutes apart, merged across gaps of up to 15 minutes. Waiting for an
approval does not count; an agent left working on its own does, so check a proposal before you
enter it. Three rules keep a span from growing past the work:

- **Focus counts up to 10 minutes after each event of that workspace.** herdr cannot tell typing
  from looking, so a workspace left in focus stops counting 10 minutes after its own last event.
  Events of other workspaces do not keep it going: an agent busy in another workspace while you are
  away does not turn the focused one into your working time.
- **An agent counts up to 30 minutes past its last sign of life.** A sign of life is an event of
  its pane or a message in the session's transcript. herdr sends nothing while the machine sleeps,
  so an agent left working when you close the lid would otherwise count the whole night; a silent
  stretch longer than 30 minutes counts 30. An agent still writing to its transcript when the
  worklog is written counts up to that moment, and the next worklog continues from there. A long
  command that writes nothing for more than 30 minutes is counted short.
- **A stretch nobody recorded is named, not counted as idle.** A timer of the operating system runs
  the recorder every five minutes, and while herdr runs it writes a sign of life; herdr's start and
  every event are signs too. A silence of more than 10 minutes was not recorded: herdr was not
  running, the machine was asleep, recording was off or the timer did not run. It begins five
  minutes after the last sign, when the next one was due, and ends at the next sign. A worklog's
  note lists these stretches under a heading of their own, "Not recorded", as `2026-03-14 10:55 to
  13:00`, so a gap in the recording does not read as a time without work; a night with the machine
  asleep shows there too. A period with no session at all writes no note, as before. Nothing is
  named before the timer's first run, so a recorder without the timer claims nothing.
- **The same minutes count once.** Workspaces on the same folder are one session, so a workspace
  you close and open again, which herdr gives a new id, continues its session. A transcript belongs
  to the workspace whose folder, or one of whose panes' folders, holds its working folder: first
  one that was open while it was written, then one whose own folder holds it, then the closest
  folder. A workspace without a folder of its own takes the folder of the transcript it holds, so
  its sphere and commits are found. A transcript no workspace holds is a session of its own.

## Booking proposals

A booking proposal comes only from a span of a billable sphere with a customer from your list. The
worklog never books: you enter the proposal in your timesheet, because a wrong booking ends up on an
invoice.

## The ledger

Each span of a session is one row in the ledger, with two numbers of minutes:

- `minutes`: the work inside the span, without its gaps. An agent working on its own counts here.
- `minutes_present`: the part of it with the workspace in focus, so you were there. Without herdr's
  focus events this is 0.

The worklog reads the recorder's files written in the last three days before its period; older
files hold nothing it counts. A workspace left in focus for longer keeps its focus. An agent that
asked for an approval more than three days before the period is no longer reported as waiting, which
is mostly a crash's leftover.

An afternoon where you set an agent going at 14:00, look at its result at 16:20 and stop at 16:30
gives a span from 14:00 to 16:30 with `minutes` 150 and `minutes_present` about 20. Whether the
agent's time is billable depends on your agreement with the customer; the ledger shows both, and
you decide. Rows written before m2b 0.3.0 have no `minutes_present`; the exports leave that cell
empty.

In `ledger.csv`, a cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return gets a
leading apostrophe, so a
spreadsheet shows a topic the model wrote as text instead of running it as a formula; the XLSX
writes every text cell as text and the two minute columns as numbers, so it needs none.

The ledger never holds the same minutes twice. A worklog whose period overlaps one the ledger holds
is refused before anything is written, and the step fails with a message that names the period it
overlaps (and the span, when one of the same session overlaps too). That happens when
`watermark.json` was reset or lost, so the worklog reaches back over time it wrote before.

## The note

Every time in the note and the facts is in your machine's local time, in the offset of its own day,
so a period across a change to or from summer time keeps each day's times on the clock. When the
blocks of a note fall on more than one date, each block carries its date, and a block that runs to
midnight ends with the next date:

```text
- 2026-03-13 23:30-2026-03-14 00:00, 2026-03-14 10:00-10:50
```

On a single date the times stand alone, as `10:00-10:50`. A topic, detail, note, project or
activity is one line, and the verdict names the sessions and nothing else: one that breaks either
rule is refused and handed back to the model to fix.

## The period

A period starts where the last one ended and reaches at most three days back, so a long pause costs
one catch-up of three days. The step does nothing while the last worklog ended less than 20 hours
ago.

## What it needs

herdr 0.9 or later, running, on the `PATH` Claude Code sees or named in the environment variable
`M2B_HERDR` (the recorder uses the herdr that starts it). `m2b-worklog recorder check` says whether
it is there, new enough and running; setup asks it first and stops before any question when it is
not. Beside herdr: the curating machine, the only one that records, so a day is never counted on
two machines; your spheres and customers, which its setup asks for.

## Set up and turn off

`/m2b:worklog-setup` first checks herdr, then asks for the spheres and customers, writes them to the
profile, and turns the worklog on. It also hooks a plugin into herdr, the recorder
`m2b.worklog-recorder`: a copy in `~/.local/share/m2b/worklog-recorder/` that herdr runs at its start
and on each event; `herdr plugin list` shows it. And it sets up the timer that runs the same copy
every five minutes: a launch agent `m2b.worklog-recorder.tick` on macOS (`launchctl list | grep m2b`
shows it), a systemd user timer `m2b-worklog-recorder-tick.timer` on Linux (`systemctl --user
list-timers`). Each run takes a moment and ends at once; on a machine that does not record it ends
without writing. Where neither exists, the worklog works without the timer and names no stretch as
not recorded. Setup checks that the timer is loaded and starts it when it is not; the session-start
hook keeps it in place and links a new recorder version in herdr again. `/m2b:worklog-setup remove`
takes out the timer, deletes the copy and unlinks the recorder, also when herdr is gone; by hand:

```bash
m2b addons off worklog
m2b-worklog recorder remove
m2b-worklog hook session-start
```

The last command sets the recording switch to `off` at once instead of at the next session start.
Without m2b, `herdr plugin unlink m2b.worklog-recorder` takes the plugin out of herdr, and
`launchctl bootout gui/$(id -u)/m2b.worklog-recorder.tick` with deleting
`~/Library/LaunchAgents/m2b.worklog-recorder.tick.plist` (macOS) or `systemctl --user disable --now
m2b-worklog-recorder-tick.timer` with deleting its two files in `~/.config/systemd/user/` (Linux)
takes out the timer. The recordings stay until `m2b-worklog recordings delete` removes them.

## What it reads

Only while it is on and only on the curating machine: the herdr events its recorder wrote; from your
Claude Code transcripts for the period, the prompts (240 characters each) and the last 500
characters of each session's last answer, where a question to you stands; your own git commits and
the `origin` remote in the session folders, and every remote there while you
[leave work out by remote](#by-git-remote); and the names of the period's captures in the inbox.
Git is started only when it starts without asking you anything: on a Mac without the developer
tools, where `/usr/bin/git` only opens a dialog that offers to install them, the worklog starts
none, and the note says under "Could not read" for each session whose folder is still there that
this machine has no git to start (`xcode-select --install` installs the tools). A
prompt loses the blocks Claude Code adds to it, such as a `<system-reminder>`, before it is cut, and
the summary Claude Code writes after a context cut counts as no prompt. Neither does what Claude
Code marks as sent by someone else than you: a plugin that drives the session, a finished task,
another session. Its time still counts as work. A prompt without that mark, which a Claude Code
before the mark writes, counts as yours.

Prompts, answers and commit subjects are redacted before the model sees them: the value after a
word such as password, `pw`, secret or token ("the password for the db is hunter2" becomes "the
password for the db is [removed]"), the value of an assignment whose name holds such a word
(`PGPASSWORD=...`, `SECRET_KEY: ...`, `AccountKey=...`), the password in a URL
(`postgres://admin:[removed]@host`) and after `-u` or `--user`, a credential after `Bearer` or
`Basic`, an AWS access key id, and long tokens of mixed letters and digits, also base64 keys with
`/` and `+`. Redaction works on patterns and stays incomplete: a secret written in words of its
own, a passphrase of several words (only its first word goes), an option such as `-phunter2`, or a
short value with no such name before it goes through. With the name, the whole value up to the
next space goes, so the rest of a connection string after `AccountKey=` goes too. For work where
that is not enough, see "Leaving work out". The facts wait in
`~/.local/state/m2b/worklog-run/`, readable by you only, while the model step runs. Its model step, once a
day, reads these facts and, to place a session, may read memory and the inbox notes and search the
archive with `m2b search`. The transcripts are read from the `projects/` folder of Claude
Code's own folder: the one `CLAUDE_CONFIG_DIR` names, or `~/.claude` when that variable is not set.

## What it writes

| Where | What |
|---|---|
| `~/.local/share/m2b/worklog-recorder/` | the recorder copy herdr links, outside the plugin's folder, which an update replaces, with `linked-version`, the version herdr last linked |
| `~/.local/state/m2b/worklog/` | the recorder's events, one file per workspace, a workspace cache, the switch file `recording` (`on` or `off`), and in `alive/` the signs of life (one file per month), the time of the timer's first run (`first-tick`) and the herdr sockets the events came from (`sockets.json`) |
| `~/Library/LaunchAgents/m2b.worklog-recorder.tick.plist` (macOS), `~/.config/systemd/user/m2b-worklog-recorder-tick.service` and `.timer` (Linux) | the timer that runs the recorder every five minutes |
| `~/.local/state/m2b/worklog-run/` | while one worklog is being written: the facts, `verdict-draft.json`, which the model step writes and `m2b-worklog verdict` checks, and the accepted verdict |
| `inbox/` in the store | the day's note, with `source: worklog` and `kind: worklog` |
| `state/addons/worklog/` in the store | `ledger.json` (the record), `ledger.csv` and `ledger.xlsx` (rebuilt every day, not for editing), `watermark.json` (where the next period starts), `intent.json` (only while a worklog is being written, so a rerun after a crash finishes the same plan) |

A file in the store is written whole, with the code the core writes the store with: from a temporary
file in `~/.local/state/m2b/tmp/`, so the service that syncs the store sees neither half a file nor
a leftover of the worklog. Only when that folder is on another volume than the store, a hidden
temporary file stands beside the target while it is written. On the machine, the recorder copy, the
timer's files, the switch, the facts and the accepted verdict are replaced whole too, each from a
hidden temporary file beside it.

The recorder writes only while the m2b plugin is installed and on in Claude Code and the switch says
`on`. The worklog's session-start hook sets the switch: on while the worklog is on, this machine
curates and the recorder is installed, off otherwise. So a take-over by another machine or `m2b
addons off worklog` turns recording off at the next session start.

## Its commands

`m2b-worklog machine` says whether this machine curates, so it may record. `m2b-worklog recorder
check` says whether herdr is installed, at least 0.9.0 and running. `m2b-worklog recorder install`
and `remove` link and unlink the recorder, `m2b-worklog recordings delete` deletes what it
recorded, and `m2b-worklog run` is the curation step. `m2b-worklog state` shows where the worklog
stands, and names a file it cannot read:

```text
watermark: 2026-03-14T18:00:00+01:00
unfinished worklog: none
ledger: 12 periods, the last from 2026-03-13T18:00:00+01:00 to 2026-03-14T18:00:00+01:00
```

The watermark belongs at the end of the last period. When a message says `watermark.json` or
`intent.json` cannot be read, repair the file by hand with what `state` shows; do not delete it,
because the next worklog then reaches back over time the ledger holds already and is refused. An
`intent.json` whose note has another name than the worklog gives one
(`20260314T170000Z-worklog-1a2b.md`: the period's end in UTC and four characters of the period's
id) cannot be read either, because the name says where the note is written. The other commands
(`facts`, `verdict`, `collect`, `hook`) are for the curation run and the plugin's hooks.

## How you see it runs

The switch file `~/.local/state/m2b/worklog/recording` says `on`, the newest file in `alive/` grows
by a line every five minutes while herdr runs (a timer the session-start hook could not set up is
named in one line at session start), and a note titled "Worklog ... to ..." lands in the archive once
a day. `ledger.csv` in `state/addons/worklog/` grows by the period's
spans. A worklog step that fails is a finding in the review task; the run goes on and still counts
as succeeded, and the next run writes the worklog for the time since the last one, at most three
days back.
