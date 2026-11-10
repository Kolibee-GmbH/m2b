# The worklog add-on

The worklog needs [herdr](https://herdr.dev) 0.9 or later, running on the curating machine: herdr
is where it sees which workspace is in use and when an agent works. It is one of the
[add-ons](../addons.md) of m2b, off until its setup turns it on.

## What it does

Once a day it writes a worklog of your sessions: for each session its topic and state, time spans
per sphere of work, and booking proposals for billable spheres. The note lands in the inbox like any
capture and is filed into the archive by the same run, so the distillate's Current section sees your
day. The time spans also go into a ledger in the store, with CSV and XLSX exports. It may propose a
fact for memory as a "Remember? ..." task; tick it and the next run files it.

## Spheres

Spheres are the areas your work falls into, such as an employer, a company of your own and private
projects. Each has an `id`, a `label`, whether its time is `billable`, and how it is recognized:
parts of git remote URLs (`git_remote_contains`) and folders under your home folder (`path_under`).
A session that matches none falls to the default sphere, the one with `"default": true`. A sphere
other than the default with neither is never matched, so its time lands in the default sphere. With
invented names:

```json
{"id": "acme", "label": "Acme Ltd", "billable": true, "match": {"git_remote_contains": ["github.com/acme-ltd/"], "path_under": ["~/code/acme"]}}
```

The spheres live in `profile.json` in the store, beside the list of customers a booking proposal may
name. The worklog only reads that list; it never adds to it.

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

The ledger never holds the same minutes twice. A worklog whose period overlaps one the ledger holds
is refused before anything is written, and the step fails with a message that names the period it
overlaps (and the span, when one of the same session overlaps too). That happens when
`watermark.json` was reset or lost, so the worklog reaches back over time it wrote before.

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
Claude Code transcripts for the period, the prompts and the last 500 characters of each session's
last answer, with credentials and long tokens redacted; your own git commits and the `origin` remote
in the session folders; and the names of the period's captures in the inbox. Its model step, once a
day, reads these facts, memory, the inbox notes and your task list, and may search the archive with
`m2b search` to place a session. The transcripts are read from the `projects/` folder of Claude
Code's own folder: the one `CLAUDE_CONFIG_DIR` names, or `~/.claude` when that variable is not set.

## What it writes

| Where | What |
|---|---|
| `~/.local/share/m2b/worklog-recorder/` | the recorder copy herdr links, outside the plugin's folder, which an update replaces, with `linked-version`, the version herdr last linked |
| `~/.local/state/m2b/worklog/` | the recorder's events, one file per workspace, a workspace cache, the switch file `recording` (`on` or `off`), and in `alive/` the signs of life (one file per month), the time of the timer's first run (`first-tick`) and the herdr sockets the events came from (`sockets.json`) |
| `~/Library/LaunchAgents/m2b.worklog-recorder.tick.plist` (macOS), `~/.config/systemd/user/m2b-worklog-recorder-tick.service` and `.timer` (Linux) | the timer that runs the recorder every five minutes |
| `~/.local/state/m2b/worklog-run/` | the facts and the verdict while one worklog is being written |
| `inbox/` in the store | the day's note, with `source: worklog` and `kind: worklog` |
| `state/addons/worklog/` in the store | `ledger.json` (the record), `ledger.csv` and `ledger.xlsx` (rebuilt every day, not for editing), `watermark.json` (where the next period starts), `intent.json` (only while a worklog is being written, so a rerun after a crash finishes the same plan) |
| the task list | "Remember? ..." candidates |

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
because the next worklog then reaches back over time the ledger holds already and is refused. The
other commands (`facts`, `verdict`, `collect`, `hook`) are for the curation run and the plugin's
hooks.

## How you see it runs

The switch file `~/.local/state/m2b/worklog/recording` says `on`, the newest file in `alive/` grows
by a line every five minutes while herdr runs (a timer the session-start hook could not set up is
named in one line at session start), and a note titled "Worklog ... to ..." lands in the archive once
a day. `ledger.csv` in `state/addons/worklog/` grows by the period's
spans. A worklog step that fails is a finding in the review task; the run goes on and still counts
as succeeded, and the next run writes the worklog for the time since the last one, at most three
days back.
