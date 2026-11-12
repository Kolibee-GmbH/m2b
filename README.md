<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/logo-dark.png">
    <img src="docs/images/logo-light.png" alt="m2b" width="230">
  </picture>
</p>

<p align="center"><em>A second brain for Claude Code. The right context in every session.</em></p>

<p align="center">
  <a href="https://github.com/Kolibee-GmbH/m2b/releases"><img src="https://img.shields.io/github/v/release/Kolibee-GmbH/m2b?style=flat-square" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/Claude%20Code-2.1.319%2B-c96442?style=flat-square" alt="Claude Code 2.1.319 or later">
  <img src="https://img.shields.io/badge/Python-3.9%2B-3776ab?style=flat-square" alt="Python 3.9 or later">
</p>

<p align="center">
  <a href="#install"><strong>Install</strong></a> · <a href="#how-it-works">How it works</a> ·
  <a href="#what-runs-on-your-machine">What runs on your machine</a> · <a href="#features">Features</a> ·
  <a href="#add-ons">Add-ons</a> · <a href="#configure">Configure</a> · <a href="docs/getting-started.md">Getting started</a> ·
  <a href="docs/commands.md">Commands</a> · <a href="SECURITY.md">Security</a> · <a href="CHANGELOG.md">Changelog</a>
</p>

Tell Claude Code "remember that Dana's birthday is on 3 March" in one project. A run in the
background files the note, and from then on every session, in any project, starts knowing it. Your
notes stay plain Markdown files in a folder you own.

What m2b adds to Claude Code's own memory, the notes Claude keeps for itself for each project:

- one memory for all your projects and machines, in a folder you choose and sync as you like;
- your words kept as you said them, and every fact pointing back to them;
- tasks from the same sentence: "remind me to call the plumber on Friday" lands in your task list.

**What it costs.** Setup is three commands and a few questions; setup itself, started as `/m2b:setup`
with every answer given at once, took 15 seconds (2026-11-12). A session starts with a summary of
your notes, at most 8 KB, and about 10,000 characters of tool and skill descriptions, without a model
call. Filing uses your Claude Code login: five notes cost US$0.013 at API prices (2026-11-08).

**No server, no account, no telemetry.** [What runs on your machine](#what-runs-on-your-machine)
says what m2b starts, when, and what leaves the machine.

![A Claude Code session in an unrelated project answers when Sam brings the plywood and where the shed key is, straight from the distillate, without a tool call; above the prompt the band asks whether planning the trip to Porto is still current, with keep and drop, and lists an overdue task to return Sam's ladder, below it the status line reads "2 in inbox · curated 08:15"](docs/images/session-start.png)

<sub>A new session in an unrelated repository already knows. The band above the prompt and the
status line below it are [the band](docs/band.md), where m2b asks you to keep or drop; Claude Code
draws the ⚠ in front of every plugin's status line, it is not a warning. All names and notes are
invented.</sub>

**Platform.** macOS 14 or newer, or Linux. Not Windows. Apple Reminders, Calendar and iCloud Drive
are optional; on Linux, and on a Mac if you like, the store is a plain folder and tasks are
Markdown files.

**Cost.** A curation run uses your Claude Code login, with Haiku by default. Measured on
2026-11-08 with Claude Code 2.1.319: a run over five captures took 48 seconds and 31 turns,
read about 365,000 input tokens (338,000 of them from Claude Code's prompt cache) and wrote 8,000;
Claude Code put it at US$0.013 at API prices. A run with nothing to read (an empty inbox, nothing
expiring, no memory link to repair) uses no model.

## How it works

One sentence, followed from your prompt into a later session. The name and the note are invented;
the files are what m2b wrote in a run on 2026-11-12.

**1. You say it.** In any session: "remember that Dana's birthday is on 3 March". Claude writes
one file into `inbox/`, the folder for new notes, with your words as you said them. Nothing is
filed while you work, and your words in the file are never changed. `source` says who wrote it:
`claude` from a session, `cli` from a terminal with `m2b capture`, as here.

```markdown
---
created: 2026-11-12T16:26:46+01:00
source: cli
---
Dana's birthday is on 3 March
```

**2. A run files it.** At the next session start m2b sees a note waiting and starts a curation
run in the background: a `claude -p` of its own, apart from your session, in which a model reads
the inbox and may call only the commands its step needs. Here it took 13 seconds. It wrote one
line into `memory/MEMORY.md`, the distillate:

```markdown
## Facts

- Dana's birthday is on 3 March (dana.md)
```

`memory/dana.md` holds the fact and a link to the note it came from. The note moved to the
archive, `corpus/2026/11/`, with your words as you said them. m2b marked it `curated: true` in its
frontmatter and added two lines below your words: a marker and `filed: fact dana.md`.

**3. Every later session starts with it.** A hook prints the distillate, at most 8 KB, at each
session start, in any project, without a model call. Asked when Dana's birthday is, Claude has
the line in front of it. The picture above shows such a session.

What a note becomes is the model's reading of it, by these rules:

| The note says | It becomes | For example |
|---|---|---|
| something that stays true | a fact: a line in the distillate and a fact file | "Dana's birthday is on 3 March" |
| something true until a known day | a fact with that day, rewritten once the day has passed | "Sam brings the plywood on Saturday" |
| something going on right now | a line under "Current" in the distillate; after a month without a new note about it, m2b asks whether it still holds | "I am planning the trip to Porto" |
| something to do | a task in your task list, due on the day the note names | "remind me to call the plumber on Friday" |

A note can be several of these, and a sentence that reads two ways is filed one way: "Sam brings
the ladder back on Saturday" became a task in one run and a fact until that Saturday in another.
The last line of the archived note says what was filed.

The store is a folder you choose: iCloud Drive, a synced folder, or any local folder. Tasks live
in Apple Reminders or in Markdown files next to the notes. Apart from the model's step, m2b is
plain code: standard library Python, no database.

## Words used here

| Word | Meaning |
|---|---|
| store | the folder that holds your notes: `inbox/`, `corpus/` (the archive), `memory/` |
| capture | one note as you said it, one file in `inbox/` |
| inbox | `inbox/` in the store: the captures no run has filed yet |
| archive | `corpus/` in the store: every filed capture, by the month it was captured in |
| curation run | the background run that files the inbox, on one machine per store, the curating machine |
| distillate | `memory/MEMORY.md`: lasting facts, each pointing to its fact file in `memory/`, and under "Current" what is going on now |
| topic | a heading in the distillate for one subject, such as a customer or a club, whose facts come in only when a session is about it |
| band | the rows above the prompt where you keep or drop what curation proposes, and the status line below it |
| add-on | an optional piece of m2b, off until its own setup: `worklog` |

## Who it is for

You work in Claude Code on more than one project and want what you learn about people,
agreements and your own life to outlast a session and a repository. A project's own decisions
belong in its repository and its `CLAUDE.md`; m2b is for what has no repository.

| | Holds | Where it lives | Who writes it |
|---|---|---|---|
| `CLAUDE.md` | instructions and facts for one project | in the repository | you, by hand |
| Claude Code's memory | short notes Claude keeps for itself | Claude Code's own files, per project or user | Claude, in the session |
| A notes MCP server | whatever the server stores | the server | the model, in the session |
| m2b | your notes, facts and tasks across all projects, as plain files you own | a folder you choose, synced as you like | you capture; a curation run files |

### m2b or Claude Code's auto memory

Claude Code keeps its own memory: short notes it writes for itself during a session, in files
under `~/.claude` for each project. It stays on beside m2b, and a first "remember this" may land
in either. The rule every session gets with the distillate keeps them apart: how Claude should
work stays with Claude Code, in its memory or in a `CLAUDE.md`; what concerns your life and world
across projects goes to m2b.

What m2b has that Claude Code's memory does not:

- your words kept as you said them, in the archive, with every fact pointing back to them;
- facts that end on a known day (`until`) and are rewritten once it has passed;
- tasks, in Apple Reminders or Markdown files, from the same "remind me";
- filing in a separate run, so your session never spends turns on it;
- topics, so a customer's facts reach only the sessions about that customer;
- one store across all projects and machines, in a folder you choose and sync as you like, as
  plain Markdown you can read, back up and move without m2b.

## What runs on your machine

Claude Code starts m2b's programs: the hooks, the band and, from a hook, the curation run. Only
the worklog add-on, off until its own setup, puts something outside Claude Code: a recorder in
[herdr](https://herdr.dev), the agent runtime in which it sees which workspace is in use, and a
timer of the operating system. After the install and before `/m2b:m2b setup`, the hooks print nothing and
no run starts.

| What | When | Model | What leaves the machine | How to turn it off |
|---|---|---|---|---|
| Session-start hooks | at every session start: four commands, each with a limit of 20 or 30 seconds | no | nothing by m2b. They print the distillate (at most 8 KB) and a routing rule into the session, start a curation run when one is due, keep the `m2b` command up to date and, with the worklog on, set its recording switch and keep its recorder, its link in herdr and its timer in place. Where sessions are read (below), they note the git remotes of the session's folder in a file on the machine | `m2b distillate off` in a folder keeps the distillate out of the sessions there and below; the other three commands have no switch of their own. With the plugin turned off in `/plugin`, none of the four runs |
| Prompt hook | before every prompt: one command, with a limit of 5 seconds | no | nothing by m2b. When the prompt names a topic, it adds that topic's facts to the session, at most 4 KB; it reads the prompt and stores nothing of it | it has no switch of its own; where the distillate is off, it adds nothing |
| Curation run | in the background, on the one machine that curates: at a session start when a capture waits or the last successful run is more than 20 hours old, on a schedule if you set one up, or with `m2b curate --force` | yes, in the steps with something to read: `claude -p` with `haiku` by default. A run with nothing to read starts no model | the captures in the inbox, your memory files, and what a step reads or searches in the archive, to the model | `m2b config set curation.paused true` on the curating machine: no session start and no schedule starts one there until you set it back to `false`, while `m2b curate --force` still runs one ([Pausing](docs/curation.md#pausing)). `m2b curate take-over` on another machine moves curation there; with the plugin turned off in `/plugin`, no session starts one, while a schedule you set up goes on until you delete it |
| Reading your sessions | once in a curation run, only after you said yes in setup | yes, one call that can use no tool | the distillate, your latest answers to its proposals and, for each session since the last reading, its folder, its day and the prompts you typed, with credentials redacted, to the model | `m2b config set curation.read_sessions false` |
| Worklog add-on | only after `/m2b:worklog-setup`, on the machine that curates: herdr starts its recorder on each event, a timer starts it every five minutes, and one step of a curation run writes the day's worklog | yes, once a day with sessions | the day's prompts, the end of each session's last answer, your commit subjects and, for each session, its folder, herdr workspace, repository and time spans, with the spheres of work and customers you named in its setup, the inbox, memory and what the step searches in the archive, to the model. The recordings stay on the machine | `m2b addons off worklog` stops its model step and, from the next session start, the recording; `/m2b:worklog-setup remove` also takes the recorder out of herdr and the timer out of the operating system |
| The band | while a session is open and mods are on in Claude Code: it asks `m2b` about once a minute and after each of your turns | no | nothing by m2b. The descriptions of its two tools, about 5,000 characters, are part of every session it runs in | it has no switch of its own; with mods off in Claude Code it does not run |

m2b opens no network connection of its own and sends no telemetry. Your notes reach a model only
through your Claude Code, under your login. In a session: the distillate, the facts of a topic a
prompt names, and what you ask the session to look up, such as search hits from the inbox, the
archive and memory, rediscovered notes, your open tasks and today's events. In a curation run:
what the table says. Whoever provides the model behind your Claude Code receives them as it
receives your sessions.

A store in a synced folder also goes where that service takes it; m2b has no sync of its own.
Tasks in Apple Reminders and events in a calendar go wherever that list or calendar syncs. In a
store that is a git repository a run commits and never pushes.

[Cost and privacy](#cost-and-privacy) says what each step hands the model.
[SECURITY.md](SECURITY.md) says what a hostile note can do and how the model's step is fenced.

## Install

```
/plugin marketplace add Kolibee-GmbH/m2b
```

```
/plugin install m2b@m2b
```

Install it for your user, the default; installed for one project only, nothing outside Claude
Code finds it. Then, in a Claude Code session:

```
/m2b:m2b setup
```

`setup` walks through the core and then offers each add-on, saying before each step what
it does. The quickest way is the first one it offers: a new folder `~/m2b` with tasks as Markdown
files, nothing else to install. It never overwrites a store that exists: pointed at a folder
another machine already uses, it joins it. [Getting started](docs/getting-started.md) walks
through it, including a first run without Claude Code.

Setup writes the command `~/.local/bin/m2b` for terminals and schedules. `~/.local/bin` is not on
the `PATH` by default on macOS; add it, for example in `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

**Requirements:** Claude Code 2.1.319 or newer, logged in, and Python 3.9 or newer as `python3`.
On a fresh Mac, `python3` comes with the Command Line Tools: `xcode-select --install`. For Apple
Reminders: [`reminders-cli`](https://github.com/keith/reminders-cli)
(`brew install keith/formulae/reminders-cli`).

### Updating

```
/plugin marketplace update m2b
```

```
/plugin update m2b@m2b
```

Then restart Claude Code. An update arrives only with a new version number: while the
installed version matches the marketplace's, `/plugin update` reports it as the latest, even if
the repository has newer commits. What each version changed is in the [changelog](CHANGELOG.md).
Your store, config and setup stay as they are. When a version changes a rule for what the store
holds, the curating machine's next run migrates the store by itself; update that machine first
([Several machines](docs/several-machines.md#machines-on-different-versions)).

### Uninstalling

1. Turn the add-ons off that left something outside Claude Code: with the worklog on, run
   `/m2b:worklog-setup remove` in a session, which turns it off and unlinks its herdr recorder;
   and delete any schedule you set up for `m2b curate` (a Shortcuts automation or a cron line).
2. Uninstall the plugin in `/plugin`. That stops every hook, the band and the recorder.
3. Delete what m2b keeps on the machine, if you want it gone:

   ```bash
   rm -rf ~/.local/bin/m2b ~/.config/m2b ~/.local/state/m2b ~/.local/share/m2b
   ```

Your store stays as it is: plain files, yours to keep or delete. So do the tasks m2b created in
your list, such as a review task or a "Remember? ..." candidate.

## Features

### Capture

In any session, say what you want kept: "remember that Dana's birthday is on 3 March", "note
this", "remind me to call the plumber on Friday". You type no command: the model's note tool,
or the `capture` skill where the band does not run, writes one file into `inbox/` with your words
verbatim, and with a date it also creates a task that points back to the note. Say that you want it
kept; a sentence on its own, such as "Dana's birthday is on 3 March", stays part of the
conversation and is not captured.

A reminder and a to-do are the same thing in m2b: a task in your task list, Apple Reminders or
Markdown files in the store. Its due date is a day, without a time of day; whether your phone
alerts for it is up to the Reminders app.

"Put it in my calendar" creates an event in the calendar you name, never in a default one: a
title, a start and an end, or a whole day. It goes through the `capture` skill, not the note tool.
It needs macOS, `calendar.backend` set to `apple-calendar` on that machine (setup asks), and full
access to calendars for the terminal Claude Code runs in (System Settings, Privacy & Security,
Calendars); `m2b calendar list --writable` names the calendars it can write. A Google or Exchange
calendar works when Apple Calendar shows it. Calendar entries are experimental: a small extra
beside a notes product, kept apart from what m2b promises, not a sign of known faults.

![Asked to remember that the shed roof needs 40 screws and to be reminded on Thursday, Claude calls the m2b note tool with a follow-up date, which writes one inbox file and a task due Thursday 12 November; below the answer the band shows a question and an overdue task, and the status line counts 3 in the inbox](docs/images/capture.png)

From a terminal or a script, without a Claude session, the same goes through the command:

```bash
m2b capture "Dana's birthday is on 3 March"
m2b capture --follow-up 2026-11-20 "Call the plumber about the shed"
```

### The distillate at session start

A session-start hook prints the distillate, at most 8 KB: lasting facts, each pointing to its
fact file, and what is going on right now. Facts that matter only for one subject sit under a
topic; a session sees the topic's name, and its facts come in when a prompt or the project
folder's path names it. The hook also prints one line when something needs you: the last
curation run failed, the curating machine has not run for three days, or the store cannot be
found. The distillate is marked as data from your notes, not instructions. In a project where it
should not appear, such as a screen share or a customer's repository, `m2b distillate off` in
that folder turns it off for every session there and below, on this machine.

Sessions capture what you learn about people and verbal agreements, at work too: who is who,
which role, what was agreed. Documents of customers and what a third party told you in confidence
are never captured. A customer's people land under that customer's topic, so their facts reach a
session only when it is about that customer. What you are working on for that customer lands under
the same topic in Current; what goes on in your own life stays above the topics there and reaches
every session.

### Search, todos, rediscover

"What did I note about the shed?", "what's open?", "show me something old": the `search`,
`todos` and `rediscover` skills answer from the store. Search is full text over archive, memory
and inbox; hits from memory come first, then the archive, then the inbox, in both the newest note
first. The skill searches a word together with its translation, so a note written in German
answers a question asked in English. Todos lists overdue, this week and undated tasks, and today's events when a calendar
is set up. Rediscover brings one or a few old notes back, each with its reason, also for "what
did I note last spring?". A file iCloud Drive has not downloaded is named, never read and never
counted as missing.

!["What's on my list?" runs the todos skill: one overdue task, the screws captured just before and a second task due within seven days, one without a date, and a note that no calendar is set up on this machine; the band below repeats the overdue task](docs/images/todos.png)

### The curation run

It starts by itself at session start on the curating machine when a capture waits in the inbox
or the last successful run is more than 20 hours old. A schedule is optional; it helps when captures arrive
while the curating machine has no session for days ([On a schedule](docs/curation.md#on-a-schedule)).
The model reads only when there is something to read: new captures, or a fact past the day it
was true until, such as an appointment. A step that fails is reported and the run goes on; the
review task in your list says what needs you. If the store folder is a git repository, each run
ends with one commit you can revert ([A commit per run](docs/curation.md#a-commit-per-run)). [The curation run](docs/curation.md) lists its
steps, the one-off runs for a distillate moved over from another tool, and the status line.

### What a run asks you

A line under Current that no capture has touched for a month comes back as a task "Still
current? ...": tick it and it stays; drop it in the band, or delete the task, and it leaves the
distillate.

**Proposals from your sessions.** Much of what belongs in a second brain you say in passing,
without "remember this": who runs what at a customer, what was agreed, what you promised by
Friday. A curation run can read what you typed in Claude Code since the last reading and propose
it, each proposal with your own words beside it. It is off until you say yes in setup
(`curation.read_sessions` in the machine config), and nothing is filed before you say keep: in
the band's pane, which `/m2b-proposals` opens, or with `m2b proposals`, `m2b proposals keep <id>`
and `m2b proposals drop <id>`. Only the prompts you typed are read, with credentials redacted: no
answer of Claude, no tool result, no pasted block, nothing a plugin or another agent sent, and no
session you left out by its folder or its git remote ([Reading your sessions](docs/curation.md#reading-your-sessions)).

**Memory candidates.** `m2b tasks add --candidate "<a fact>"` proposes one fact as a task
"Remember? ...", for a script or an integration of yours: tick it and the next run files it; drop
it in the band, or delete the task, and it does not come back for 90 days.

**Ticking a task.** With Apple Reminders you tick in the Reminders app. With Markdown tasks,
`m2b tasks list` shows every open task with its id, the review task and these questions among
them; `m2b tasks complete <id>` ticks one and `m2b tasks drop <id>` drops one. The band's keep and
drop buttons call the same two commands.

### Commands

The ten you will use most; [Commands](docs/commands.md) has every one, and what to say instead
of typing any.

| Command | What it does |
|---|---|
| `/m2b:m2b` | says what m2b is and what to type; `/m2b:m2b setup` sets a machine up |
| `/m2b-note <text>` | notes the text into the inbox at once, without a model turn |
| `m2b capture "<text>"` | the same from a terminal or a script |
| `m2b search <words>` | full text over archive, memory and inbox |
| `m2b todos` | open tasks by due date, and today's events |
| `m2b tasks list` | every open task with its id |
| `m2b tasks complete <id>` | ticks a task |
| `m2b status` | the inbox, the last curation run, whether one is due |
| `m2b doctor` | checks every backend and says what to fix |
| `m2b curate --force` | files the inbox now instead of at the next session start |

A slash command with a colon (`/m2b:search`) is a skill and takes a model turn; one with a dash
(`/m2b-search`) is a command of the band and runs at once.

## The band

Above the prompt, [the band](docs/band.md) shows memory candidates and "Still current?" questions,
each with keep and drop buttons you click with the mouse (a click waits 5 seconds with `undo`
before it writes), one row that says how many proposals from your sessions wait, and the open
review task: the facts a run changed in one row, its other
findings, and `ok` to close it; below the prompt, a status
line such as `3 in inbox · curated 18:02`. `/m2b-note <text>` notes a text into the inbox at once,
without a model turn, also while one is working. `/m2b-review` opens a pane with the whole last
curation run, `/m2b-proposals` shows the proposals from your sessions there, each with keep and
drop, and `/m2b-search <text>` shows search hits. The model notes and searches
through two tools of the mod, `mcp__m2b__note` and `mcp__m2b__search`, without a shell call. The
band is part of m2b and starts once m2b is set up. It is a mod, so it needs mods on in Claude Code; `m2b doctor` says
whether the latest session ran it, and why not.

## Add-ons

m2b is one plugin. One add-on in it is off until you set it up with its own setup skill, and
`m2b addons list` shows whether it is on.

| Add-on | What it adds | Needs | Setup |
|---|---|---|---|
| [`worklog`](docs/addons/worklog.md) | A daily worklog of your sessions in herdr: topics, time spans per sphere of work, booking proposals for billable spheres, a ledger with CSV and XLSX exports | [herdr](https://herdr.dev) 0.9 or later, running; the curating machine, which alone records; your spheres of work and customers, which its setup asks for | `/m2b:worklog-setup` |

Its page, linked in the table, says what it reads and writes on the machine and in the store, its
commands, and how you see that it runs. [Add-ons](docs/addons.md) is the overview. To turn it off
again, keeping its settings:

```bash
m2b addons off worklog
```

## Cost and privacy

**The model.** Only a curation run calls a model, and only for a step with something to read:
ingest for new captures, refresh for a fact past its day, lint for a broken link in memory with
exactly one candidate, the reading of your sessions once in a run while it is on and you typed
something since the last reading, and the worklog's verdict once a day while that add-on is on,
unless the day had no sessions. Each step runs with `curation.model` (`haiku` by default; setup offers `sonnet`
for more careful filing at a higher cost) and stops after `curation.max_turns` turns;
`curation.max_budget_usd`, unset by default, caps its spending. It runs on your Claude Code login
and is billed like your sessions.

**What reaches the model.** In a curation step: what the step's rules allow, nothing else. Ingest
and lint read the captures and memory files; refresh reads the distillate, the fact files that are
due and any archive file; sorting reads memory. Ingest, lint, `--refresh-all` and the worklog step
also get `m2b search` results over inbox, archive and memory. The reading of your sessions sends
the distillate, up to 30 proposals you kept and 30 you dropped lately, each with your words, and,
per session, its folder, its day and the prompts you typed, redacted, to a model that can call
nothing. With the worklog add-on, its step sees the period's prompts and last
answers, commits and session folders, the inbox and memory (below). In every session:
the distillate, the routing rule and the notices at session start; before a prompt that names a
topic, that topic's facts.

**What the worklog reads** (only while on, only on the curating machine): the herdr events its
recorder writes to `~/.local/state/m2b/worklog/`, the prompts and the end of each session's last
answer from your Claude Code transcripts for the period (with credentials and long tokens
redacted, and without a prompt a plugin, a finished task or another session sent), your own git commits (their subjects redacted the same way), and the inbox. Of the
work you tell it to leave out, by folder or by git remote, it keeps nothing; its model step may also search the archive. Its
ledger with time spans and booking proposals lands in the store under `state/addons/worklog/`.
A time span is when a workspace was in use: an agent at work (up to 30 minutes past its last sign
of life, so a machine asleep does not count), the workspace in focus (up to 10 minutes after each of
its own events, because herdr cannot tell typing from looking), or messages in its transcript at most
15 minutes apart, merged across gaps of up to 15 minutes; waiting for an approval does not count.
The same minutes count once, also when a workspace is closed and opened again. An agent left working
on its own, a loop through the night for one, counts as well, so check a booking proposal before you
enter it. A stretch the recorder did not record, because herdr was not running or the machine slept,
is named in the note as not recorded, never read as a time without work. The
[worklog page](docs/addons/worklog.md#time-spans) has the rules.

## Configure

Three files, each with one owner:

| File | Where | Holds |
|---|---|---|
| `config.json` | `~/.config/m2b/` on each machine | the store's folder and backend, the calendar, absolute paths of `python3`, `claude`, `reminders` and `osascript`, which add-ons are on and their settings |
| `store.json` | the store | the store format, the task backend, which machine curates |
| `profile.json` | the store | your name and language (`en` or `de`, for the task titles and notes m2b writes), and for the worklog your spheres and customers |

Change them through commands, which check each value and write the file whole, so a sync client
never picks up half a file:

```bash
m2b config set curation.model sonnet
m2b profile set language de
```

[Configuration](docs/configuration.md) lists every key. [Store format](docs/store-format.md)
describes the folder, the file names and the frontmatter. [Several machines](docs/several-machines.md)
covers joining a store from a second Mac and moving curation.

## Troubleshooting

```bash
m2b doctor
m2b status
```

`doctor` checks every backend and says what to fix; `status` shows the inbox, the last run and
whether a run is due.

- **`m2b: command not found`.** Add `~/.local/bin` to your `PATH` (see Install). Inside a
  session, `!m2b status` works without it.
- **No `python3`, or a message that m2b needs Python 3.9.** On a Mac run
  `xcode-select --install`; on Linux install `python3` from your distribution.
- **`m2b: the core plugin m2b@m2b is not installed for this user`, or `doctor` reports
  `claude-code: missing`.** m2b is not installed for your user: for one project only, or not at
  all. Remove a project install in `/plugin`, then install it for your user (see Install).
- **A step fails with a login message, or `claude` is not found.** Run `claude` in a terminal and
  log in. A schedule runs with a short `PATH`; record where `claude` is:
  `m2b config set executables.claude "$(command -v claude)"`.
- **The session start says the last run failed.** The review task in your list names the step
  and the cause. Fix it and run `m2b curate --force`.
- **A topic's facts do not come in when you name it.** The hook that brings them says nothing when
  it fails. `m2b doctor` starts it and says in its line `prompt-hook` why it does not answer.
- **`curating` for a long time.** A run is going on; each model step is stopped after
  `curation.model_timeout_minutes` (15). When it ends, its outcome is added to
  `~/.local/state/m2b/run.log`.
- **Tasks "not reachable" with Apple Reminders.** The terminal Claude Code runs in needs access:
  System Settings, Privacy & Security, Reminders.
- **"not set up".** Run `/m2b:m2b setup` on this machine.
- **Files "not downloaded".** iCloud Drive keeps them in the cloud ("Optimize Mac Storage").
  `m2b store fetch <path>` downloads them; m2b never reads them by accident.

## Limits

- One owner per store. No sharing, no multi-user store.
- Full text search only, no semantic search: a note is found by the words it holds, or their
  translation.
- macOS and Linux. Windows is not supported: m2b relies on `fcntl` locks, process groups and
  `sh` scripts.
- The task titles, notes and worklog m2b writes are in English or German; everything else it
  prints is in English. Your notes can be in any language.
- On Linux there is no calendar backend, and a schedule is a cron line instead of a Shortcut.
- An event goes into your own calendar only: no attendees, invitations, place or meeting link. A
  task is due on a day, not at a time.
- The worklog needs [herdr](https://herdr.dev) 0.9 or later and records only the curating machine. It never books anything: its
  bookings are proposals for you to enter.
- Sync is whatever moves the folder. m2b has no sync and no server of its own. It knows a
  conflict copy by the name iCloud Drive gives it (backend `icloud`) or Dropbox and Syncthing
  give it (backend `folder`); the copies of another service are files like any other to it.
- Nothing captured is deleted automatically. What does get deleted: conflict copies identical
  to their original, the product's own leftover temp files and settled candidate tasks.

## Develop

```bash
scripts/check --quick m2b   # unit tests of the core (or worklog, band)
scripts/check               # everything, must end with "check: passed"
scripts/e2e --level stub    # end-to-end scenarios without a model
```

[Architecture](docs/architecture.md) is the short tour of the code; [CONTRIBUTING.md](CONTRIBUTING.md)
has the ground rules. To write your own client, read [Integrations](docs/integrations.md); to add a store,
task or calendar backend, [Writing a backend](docs/writing-a-backend.md). What m2b promises to do,
and which defects it must not have, is listed in [Behavior](docs/behavior.md). What it does to
Claude's answers is measured: [Evals](docs/evals.md) has eight cases, each run with m2b and
without, and the scores of the last run.

## License

MIT, see [LICENSE](LICENSE). Security reports: [SECURITY.md](SECURITY.md).
