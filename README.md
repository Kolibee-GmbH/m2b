<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/logo-dark.png">
    <img src="docs/images/logo-light.png" alt="m2b" width="230">
  </picture>
  <br><em>A second brain for Claude Code. The right context in every session.</em>
</p>

<p align="center">
  <a href="https://github.com/Kolibee-GmbH/m2b/releases"><img src="https://img.shields.io/github/v/release/Kolibee-GmbH/m2b?style=flat-square" alt="Release"></a>
  <a href="https://github.com/Kolibee-GmbH/m2b/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Kolibee-GmbH/m2b/ci.yml?branch=main&style=flat-square&label=CI" alt="CI on main"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/Claude%20Code-2.1.319%2B-c96442?style=flat-square" alt="Claude Code 2.1.319 or later">
  <img src="https://img.shields.io/badge/Python-3.9%2B-3776ab?style=flat-square" alt="Python 3.9 or later">
</p>

<p align="center">
  <a href="#quick-start"><strong>Quick start</strong></a> · <a href="#what-you-can-say">What you can say</a> · <a href="#how-it-works">How it works</a> ·
  <a href="#the-band">The band</a> · <a href="#what-runs-on-your-machine">What runs on your machine</a> · <a href="#install">Install</a> ·
  <a href="#limits">Limits</a> · <a href="#docs">Docs</a> · <a href="SECURITY.md">Security</a> · <a href="CHANGELOG.md">Changelog</a>
</p>

![Three steps in a terminal. First, in a Claude Code session in the project invoice-tool, the prompt "remember that Dana's birthday is on 3 March" makes Claude call the m2b note tool, which saves the sentence as one file, and the status line below the prompt reads "1 in inbox". Second, the next Claude Code session starts in the same project and nobody types anything: its start begins a curation run in the background, and the status line goes from "1 in inbox" to "0 in inbox". Third, a new Claude Code session in another project, garden-site, is asked "when is Dana's birthday?" and answers 3 March from the note dana.md, without a tool call](docs/images/demo.gif)

<sub>One sentence from a prompt into a later session: three real Claude Code sessions on a demo machine with invented notes, recorded by `scripts/readme-demo`. The start of the second begins the real background run that files the note; nobody types a command. The waits are shortened.</sub>

Tell Claude Code "remember that Dana's birthday is on 3 March" in one project. A run in the
background files the note, and from then on every session, in any project, starts knowing it. You
type no command for it: you say what to keep and ask for what you need. Your notes stay plain
Markdown files in a folder you own.

What m2b adds to Claude Code's own memory, the notes Claude keeps for itself for each project:
- one memory for all your projects and machines, in a folder you choose and sync as you like;
- your words kept as you said them, and every fact pointing back to them;
- tasks from the same sentence: "remind me to call the plumber on Friday" lands in your task list.

**What it costs.** Setup is three slash commands in Claude Code and a few questions; setup itself,
started as `/m2b:setup` with every answer given at once, took 15 seconds (2026-11-12). A session
starts with a summary of your notes, at most 8 KB, and about 10,000 characters of tool and skill
descriptions, without a model call. Filing uses your Claude Code login: five notes cost US$0.013 at
API prices (2026-11-08).

**No server, no account, no telemetry.** [What runs on your machine](#what-runs-on-your-machine)
says what m2b starts, when, and what leaves the machine.

## Quick start

On macOS 14 or newer or Linux, in a Claude Code session, three slash commands:

```
/plugin marketplace add Kolibee-GmbH/m2b
```

```
/plugin install m2b@m2b
```

```
/m2b:m2b setup
```

Setup's first offer is a new folder `~/m2b` with tasks as Markdown files; nothing else is
installed. Then say "remember that the spare key is under the blue pot", start a new session, and
in the one after it ask where the spare key is. [Getting started](docs/getting-started.md) shows
what you should see at each step, and [Install](#install) what m2b needs. Before you install:
[what runs on your machine](#what-runs-on-your-machine) and [uninstalling](#uninstalling).

![A Claude Code session in an unrelated project answers when Sam brings the plywood and where the shed key is, straight from the distillate, without a tool call; above the prompt the band asks whether planning the trip to Porto is still current, with keep and drop, and lists one task due today and one overdue; below it the status line counts 2 in the inbox and says when curation last ran](docs/images/session-start.png)

<sub>A new session in an unrelated repository already knows. Above the prompt, [the band](#the-band)
asks one question and lists what is due; Claude Code draws the ⚠ in front of every plugin's status
line, it is not a warning. All names and notes are invented.</sub>

## What you can say

| You say | What happens |
|---|---|
| "remember that Dana's birthday is on 3 March" | a note in your own words goes into the inbox, and the next run files it as a fact |
| "remind me to call the plumber on Friday" | the same, and a task due that day in your task list: Apple Reminders or Markdown files |
| "what's open?" | your open tasks by due date, and today's events where a calendar is set up |
| "I returned Sam's ladder, tick it off" | that task is ticked; m2b asks when more than one fits |
| "what did I note about the shed?" | the lines that match, each with its file, from a full-text search over everything you noted |
| "show me something old" | one or a few old notes, each with the reason it was picked |
| "put the dentist in my calendar, Thursday at 10" | an event in the calendar you name (macOS, experimental) |

Say that you want it kept: a sentence on its own, such as "Dana's birthday is on 3 March", stays
part of the conversation and is not captured. Sessions capture what you learn about people and
verbal agreements, at work too; documents of customers and what a third party told you in
confidence are never captured.

[Using m2b](docs/using.md) has each of these in detail. From a terminal or a script the same goes
through commands, such as `m2b capture "<text>"`; [Commands](docs/commands.md) lists every one.

## How it works

One sentence, followed from your prompt into a later session. The name and the note are invented;
the files are what m2b wrote in a run on 2026-11-12.

**1. You say it.** In any session: "remember that Dana's birthday is on 3 March". Claude writes
one file into `inbox/`, the folder for new notes, in your own words, without the
"remember that" around them. Nothing is filed while you work, and your words in the file are never
changed. `source` says who wrote it:
`claude` from a session, as here, `cli` from a terminal with `m2b capture`.

```markdown
---
created: 2026-11-12T21:58:13+01:00
source: claude
---
Dana's birthday is on 3 March.
```

**2. A run files it.** At the next session start m2b sees a note waiting and starts a curation
run in the background: a `claude -p` of its own, apart from your session, in which a model reads
the inbox and may call only the commands its step needs. Here it took 11 seconds. It wrote one
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

A run can also put the facts about one subject, such as a customer or a club, under a topic. A
session then starts with the topic's name only, and its facts come in when your prompt or the
project folder's path names one of the topic's words, or through a search
([The distillate at session start](docs/using.md#the-distillate-at-session-start)).

What a note becomes is the model's reading of it, by these rules:

| The note says | It becomes | For example |
|---|---|---|
| something that stays true | a fact: a line in the distillate and a fact file | "Dana's birthday is on 3 March" |
| something true until a known day | a fact with that day, rewritten once the day has passed | "Sam brings the plywood on Saturday" |
| something going on right now | a line under "Current" in the distillate; after a month without a new note about it, m2b asks whether it still holds | "I am planning the trip to Porto" |
| something to do | a task in your task list, due on the day the note names | "remind me to call the plumber on Friday" |

The store is a folder you choose: iCloud Drive, a synced folder, or any local folder. Apart from
the model's step, m2b is plain code: standard library Python, no database.

## The band

![The pane after /m2b-review: the last curation run with its times, the review row "1 fact changed: Sam", the fact about Sam with the old day struck through in red and the new one in green, where the facts from before the run lie, and a "Still current?" question with keep and drop; below the pane the band with its rows and the status line](docs/images/review.png)

Above the prompt, the band shows what needs an answer from you: a "Still current?" question for a
line under Current that no note has touched for a month, a "Remember?" fact that a script of
yours proposed, how many
proposals from your sessions wait, the tasks due today or overdue, and the review of the last run
with the facts it changed. `keep`, `drop` and `ok` are buttons you click with the mouse; a click
waits 5 seconds with `undo` before it writes. Below the prompt, a status line says how many notes
wait and when curation last ran.

`/m2b-review` opens the pane in the picture with the whole last run, `/m2b-proposals` the
proposals from your sessions, `/m2b-search <text>` search hits, and `/m2b-note <text>` notes a
text at once, without a model turn. The band is a mod, a module Claude Code loads with the plugin,
so it runs only while mods are on in Claude Code; `/m2b:m2b doctor` says whether the latest
session ran it ([The band](docs/band.md)).

**Proposals from your sessions.** A curation run can also read what you typed in Claude Code and
propose what you said in passing, without "remember this", each proposal with your own words
beside it; nothing is filed before you keep it
([Reading your sessions](docs/curation.md#reading-your-sessions)).

## What runs on your machine

Claude Code starts m2b's programs: the hooks, the band and, from a hook, the curation run. Only the
worklog add-on, off until its own setup, puts something outside Claude Code: a recorder in
[herdr](https://herdr.dev), the agent runtime in which it sees which workspace is in use, and a
timer of the operating system. After the install and before `/m2b:m2b setup`, the hooks print
nothing and no run starts.

| What | When | Model | What leaves the machine | How to turn it off |
|---|---|---|---|---|
| Session-start hooks | at every session start: four commands, each with a limit of 20 or 30 seconds | no | nothing by m2b. They print the distillate (at most 8 KB) and a routing rule into the session, start a curation run when one is due, keep the `m2b` command up to date and, with the worklog on, set its recording switch and keep its recorder, its link in herdr and its timer in place. Where sessions are read (below), they note the git remotes of the session's folder in a file on the machine | `m2b distillate off` in a folder keeps the distillate out of the sessions there and below; the other three commands have no switch of their own. With the plugin turned off in `/plugin`, none of the four runs |
| Prompt hook | before every prompt: one command, with a limit of 5 seconds | no | nothing by m2b. When the prompt names a topic, it adds that topic's facts to the session, at most 4 KB; it reads the prompt and stores nothing of it | it has no switch of its own; where the distillate is off, it adds nothing |
| Curation run | in the background, on the one machine that curates: at a session start when a capture waits or the last successful run is more than 20 hours old, on a schedule if you set one up, or with `m2b curate --force` | yes, in the steps with something to read: `claude -p` with `haiku` by default. A run with nothing to read starts no model | the captures in the inbox, your memory files, and what a step reads or searches in the archive, to the model | `m2b config set curation.paused true` on the curating machine: no session start and no schedule starts one there until you set it back to `false`, while `m2b curate --force` still runs one ([Pausing](docs/curation.md#pausing)). `m2b curate take-over` on another machine moves curation there; with the plugin turned off in `/plugin`, no session starts one, while a schedule you set up goes on until you delete it |
| Reading your sessions | once in a curation run, only after you said yes in setup | yes, one call that can use no tool | the distillate, your latest answers to its proposals and, for each session since the last reading, its folder, its day and the prompts you typed, with credentials redacted, to the model | `m2b config set curation.read_sessions false` |
| Worklog add-on | only after `/m2b:worklog-setup`, on the machine that curates: herdr starts its recorder on each event, a timer starts it every five minutes, and one step of a curation run writes the day's worklog | yes, once a day with sessions | the day's prompts, the end of each session's last answer, your commit subjects and, for each session, its folder, herdr workspace, repository and time spans, with the spheres of work and customers you named in its setup, the inbox, memory and what the step searches in the archive, to the model. The recordings stay on the machine | `m2b addons off worklog` stops its model step and, from the next session start, the recording; `/m2b:worklog-setup remove` also takes the recorder out of herdr and the timer out of the operating system |
| The band | while a session is open and mods are on in Claude Code: it asks `m2b` about once a minute and after each of your turns | no | nothing by m2b. The descriptions of its two tools, about 5,000 characters, are part of every session it runs in. A call of either tool runs without Claude Code's permission prompt, the note tool only for a note in your own words; your own `permissions.ask` and `permissions.deny` rules for `mcp__m2b__note` and `mcp__m2b__search` come first ([Security](SECURITY.md#the-tools-the-model-calls)) | it has no switch of its own; with mods off in Claude Code it does not run |

m2b opens no network connection of its own and sends no telemetry. Your notes reach a model only
through your Claude Code, under your login. In a session: the distillate, the facts of a topic a
prompt names, and what you ask the session to look up, such as search hits from the inbox, the
archive and memory, rediscovered notes, your open tasks and today's events. In a curation run:
what the table says. Whoever provides the model behind your Claude Code receives them as it
receives your sessions.

A store in a synced folder also goes where that service takes it; m2b has no sync of its own.
Tasks in Apple Reminders and events in a calendar go wherever that list or calendar syncs. In a
store that is a git repository a run commits and never pushes.

[Cost and privacy](docs/cost-and-privacy.md) says what each step hands the model.
[SECURITY.md](SECURITY.md) says what a hostile note can do and how the model's step is fenced.

## Install

The three commands of the [quick start](#quick-start). Install the plugin for your user, the
default; installed for one project only, nothing outside Claude Code finds it. `setup` walks
through the core and then offers each add-on, saying before each step what it does. It never
overwrites a store that exists: pointed at a folder another machine already uses, it joins it.
[Getting started](docs/getting-started.md) walks through it, including a first run without Claude
Code.

**Requirements:** macOS 14 or newer, or Linux; not Windows. Claude Code 2.1.319 or newer, logged
in, and Python 3.9 or newer as `python3`. On a fresh Mac, `python3` comes with the Command Line
Tools: `xcode-select --install`. Apple Reminders, Calendar and iCloud Drive are optional; without
them the store is a plain folder and tasks are Markdown files. For Apple Reminders:
[`reminders-cli`](https://github.com/keith/reminders-cli)
(`brew install keith/formulae/reminders-cli`).

Setup also writes the command `~/.local/bin/m2b`. Daily use does not need it in a terminal; to
type `m2b` yourself, put `~/.local/bin` on your `PATH`.

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
2. Uninstall the plugin in `/plugin`. That stops every hook, the band and the recorder. Then take
   the marketplace out as well, or Claude Code keeps its copy of this repository:

   ```
   /plugin marketplace remove m2b
   ```

3. Delete what m2b keeps on the machine, if you want it gone:

   ```bash
   rm -rf ~/.local/bin/m2b ~/.config/m2b ~/.local/state/m2b ~/.local/share/m2b
   ```

4. If you added `~/.local/bin` to your `PATH` for m2b alone, take that line out of `~/.zshrc`
   again.

Your store stays as it is: plain files, yours to keep or delete. So do the tasks m2b created in
your list, such as a review task or a "Remember? ..." candidate.

## Add-ons

One add-on comes with the plugin and is off until you set it up:

| Add-on | What it adds | Needs | Setup |
|---|---|---|---|
| [`worklog`](docs/addons/worklog.md) | A daily worklog of your sessions in herdr: topics, time spans per sphere of work, booking proposals for billable spheres, a ledger with CSV and XLSX exports | [herdr](https://herdr.dev) 0.9 or later, running; the curating machine, which alone records; your spheres of work and customers, which its setup asks for | `/m2b:worklog-setup` |

`m2b addons list` shows whether it is on, and `m2b addons off worklog` turns it off again and
keeps its settings. Its page says what it reads and writes; [Add-ons](docs/addons.md) is the
overview.

## Cost and privacy

A run over five captures took 48 seconds with `haiku`, and Claude Code put it at US$0.013 at API
prices (2026-11-08, Claude Code 2.1.319). `curation.max_turns` and `curation.max_budget_usd` cap a
model step; m2b does not record what a run used. [Cost and privacy](docs/cost-and-privacy.md)
lists what each step hands the model.

## Limits

**Status.** m2b is young: its first version is from 2026-11-09, and its author has used it every
day since 2026-11-08, on macOS with iCloud Drive and Apple Reminders. Linux is covered by the
tests, not by daily use. The store format is versioned, and the curating machine migrates the
store by itself when a version changes it ([Store format](docs/store-format.md#formats)); commands
and settings can still change before 1.0, and the [changelog](CHANGELOG.md) says when one does.

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
- The worklog needs [herdr](https://herdr.dev) 0.9 or later and records only the curating machine.
  It never books anything: its bookings are proposals for you to enter.
- Sync is whatever moves the folder. m2b has no sync and no server of its own. It knows a
  conflict copy by the name iCloud Drive gives it (backend `icloud`) or Dropbox and Syncthing
  give it (backend `folder`); the copies of another service are files like any other to it.
- Nothing captured is deleted automatically. What does get deleted: conflict copies identical
  to their original, the product's own leftover temp files and settled candidate tasks.

## Docs

| Page | What it has |
|---|---|
| [Getting started](docs/getting-started.md) | the first steps, with what you should see at each |
| [Using m2b](docs/using.md) | everything you can say, the distillate, what a run asks you, who it is for and how it differs from Claude Code's memory, the words used here |
| [The curation run](docs/curation.md) | its steps, taking a run back, pausing, a schedule, reading your sessions |
| [The band](docs/band.md) | its rows, the pane, its commands and the two tools the model notes and searches with |
| [Commands](docs/commands.md) | every command, and what to say instead of typing most |
| [Configuration](docs/configuration.md) | the three files m2b keeps its settings in, and every key |
| [Store format](docs/store-format.md) | the folder, the file names and the frontmatter |
| [Several machines](docs/several-machines.md) | joining a store from a second machine, moving curation |
| [Troubleshooting](docs/troubleshooting.md) | `m2b doctor`, `m2b status` and the causes met so far |
| [Cost and privacy](docs/cost-and-privacy.md) | what a run costs and what each step hands the model |
| [Add-ons](docs/addons.md) | the worklog |
| [Evals](docs/evals.md) | what m2b does to Claude's answers, measured with it and without |
| [SECURITY.md](SECURITY.md) | what a hostile note can do, how a model step is fenced, how to report |

## Develop

```bash
scripts/check --quick m2b   # unit tests of the core (or worklog, band)
scripts/check               # everything, must end with "check: passed"
scripts/e2e --level stub    # end-to-end scenarios without a model
```

[Architecture](docs/architecture.md) is the short tour of the code;
[CONTRIBUTING.md](CONTRIBUTING.md) has the ground rules. To write your own client, read
[Integrations](docs/integrations.md); to add a store, task or calendar backend, [Writing a
backend](docs/writing-a-backend.md). What m2b promises to do, and which defects it must not have, is
listed in [Behavior](docs/behavior.md). What it does to Claude's answers is measured:
[Evals](docs/evals.md) has eight cases, each run with m2b and without, and the scores of the last
run.

## License

MIT, see [LICENSE](LICENSE). Security reports: [SECURITY.md](SECURITY.md).
