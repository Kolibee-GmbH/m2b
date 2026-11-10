# The worklog add-on

One of the [add-ons](../addons.md) of m2b, off until its setup turns it on.

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

A time span is when a workspace was in use: an agent at work, the workspace in focus (herdr cannot
tell typing from looking, so focus counts for a limited time after each event), or messages in its
transcript at most 15 minutes apart, merged across gaps of up to 15 minutes. Waiting for an approval
does not count; an agent left working on its own does, so check a proposal before you enter it.

## Booking proposals

A booking proposal comes only from a span of a billable sphere with a customer from your list. The
worklog never books: you enter the proposal in your timesheet, because a wrong booking ends up on an
invoice.

## The period

A period starts where the last one ended and reaches at most three days back, so a long pause costs
one catch-up of three days. The step does nothing while the last worklog ended less than 20 hours
ago.

## What it needs

herdr 0.9 or later; the curating machine, the only one that records, so a day is never counted on
two machines; your spheres and customers, which its setup asks for.

## Set up and turn off

`/m2b:worklog-setup` asks for the spheres and customers, writes them to the profile, installs the
recorder in herdr and turns the worklog on. `/m2b:worklog-setup remove` turns it off and unlinks the
recorder; by hand:

```bash
m2b addons off worklog
m2b-worklog recorder remove
m2b-worklog hook session-start
```

The last command sets the recording switch to `off` at once instead of at the next session start.
The recordings stay until `m2b-worklog recordings delete` removes them.

## What it reads

Only while it is on and only on the curating machine: the herdr events its recorder wrote; from your
Claude Code transcripts for the period under `~/.claude/projects/`, the prompts and the last 500
characters of each session's last answer, with credentials and long tokens redacted; your own git
commits and the `origin` remote in the session folders; and the names of the period's captures in
the inbox. Its model step, once a day, reads these facts, memory, the inbox notes and your task
list, and may search the archive with `m2b search` to place a session.

## What it writes

| Where | What |
|---|---|
| `~/.local/share/m2b/worklog-recorder/` | the recorder copy herdr links, outside the plugin's folder, which an update replaces |
| `~/.local/state/m2b/worklog/` | the recorder's events, one file per workspace, a workspace cache, and the switch file `recording` (`on` or `off`) |
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
install` and `remove` link and unlink the recorder, `m2b-worklog recordings delete` deletes what it
recorded, and `m2b-worklog run` is the curation step. The others (`facts`, `verdict`, `collect`,
`hook`) are for the curation run and the plugin's hooks.

## How you see it runs

The switch file `~/.local/state/m2b/worklog/recording` says `on`, and a note titled "Worklog ... to
..." lands in the archive once a day. `ledger.csv` in `state/addons/worklog/` grows by the period's
spans. A worklog step that fails is a finding in the review task, and the run goes on.
