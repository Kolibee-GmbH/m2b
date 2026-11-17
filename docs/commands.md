# Commands

Everything you can say, type after a slash, or run as `m2b` in a terminal, in one place. Most days
need none of it: you say what you want kept or want to know, and the session does the rest.

- [What you say in a session](#what-you-say-in-a-session)
- [Slash commands](#slash-commands): `/m2b:...` for skills, `/m2b-...` for the band
- [The `m2b` command](#the-m2b-command), for a terminal, a script or a schedule
- [Exit codes](#exit-codes)

## What you say in a session

| You say | What answers | What happens |
|---|---|---|
| "remember that the spare key is under the blue pot", "note this" | the note tool, or the `capture` skill where the band does not run | one file in `inbox/` with your words; the next curation run files it |
| "remind me to call the plumber on Friday" | the same | the note, and a task due that day in your task list |
| "keep this contract, ~/Documents/lease.pdf" | the `capture` skill, and Claude Code asks you before the copy | a copy of the file in `inbox/` with a note beside it that holds your words; the next curation run reads it |
| "put it in my calendar: dentist, Tuesday at 10" | the `capture` skill | an event in the calendar you name (macOS, with a calendar set up) |
| "what did I note about the shed?" | the search tool, or the `search` skill | the lines that match, each with its file |
| "what exactly does the rowing club's handbook say about lockers?" | the same, called with the fact file's name | the whole fact file, then the note of the document behind it with its outline |
| "what's open?", "what's on today?" | the `todos` skill | open tasks by due date, and today's events where a calendar is set up |
| "I returned Sam's ladder, tick it off", "the paint task is done" | the `todos` skill | ticks that task in your list; asks when more than one fits |
| "show me something old", "what did I note last spring?" | the `rediscover` skill | one or a few old notes, each with the reason it was picked |
| "is my second brain working?" | the `m2b` skill | what m2b is and what to type; `/m2b:m2b status` and `/m2b:m2b doctor` then show the state and check the machine |

A sentence on its own, such as "Dana's birthday is on 3 March", stays part of the conversation.
Say that you want it kept.

## Slash commands

There are two spellings, and they are two different things:

- **A name with a colon, `/m2b:search`, is a skill.** Claude reads the skill and acts on it, so it
  takes a model turn. Skills work in every session where the plugin is on.
- **A name with a dash, `/m2b-search`, is a command of the band.** It runs at once, without the
  model, also while a turn is working. It needs the band, so mods on in Claude Code
  ([The band](band.md#what-it-needs)).

### Skills

| Skill | What it does |
|---|---|
| `/m2b:m2b` | says what m2b is and what to type; `/m2b:m2b setup` guides through setup, `/m2b:m2b status` shows the inbox, the last curation run and the backends, `/m2b:m2b doctor` checks the machine, `/m2b:m2b addons` shows the add-ons. Claude Code also runs it for `/m2b` alone; the pane is `/m2b-pane` |
| `/m2b:setup` | sets this machine up, for a new store or one another machine already uses; `/m2b:m2b setup` starts it |
| `/m2b:capture` | captures a note, a task, a file you name with its path or a calendar entry; saying "remember ..." does the same |
| `/m2b:search` | searches archive, memory and inbox in full text |
| `/m2b:todos` | open tasks by due date, and today's events; ticks a task you say is done |
| `/m2b:rediscover` | brings one or a few old notes back into view |
| `/m2b:worklog-setup` | sets up the worklog add-on on the curating machine; `/m2b:worklog-setup remove` turns it off and takes its parts out again ([Worklog](addons/worklog.md)) |

Five more skills belong to the curation run, which starts each of them fenced: `/m2b:ingest`,
`/m2b:lint`, `/m2b:refresh`, `/m2b:sort-facts` and `/m2b:worklog-verdict`. Typed in a session they
do not do their work there. The first three start a curation run in the background, as
`m2b curate --force --detach` does; `/m2b:sort-facts` starts `m2b curate --sort-facts --detach`;
`/m2b:worklog-verdict` says that the worklog is written once a day by the curation run.

### Commands of the band

| Command | What it does |
|---|---|
| `/m2b-pane` | shows in the m2b pane its overview: what waits for you, what is due today, what m2b gave this session and how m2b itself stands; there a press shows a topic's lines, turns m2b off in the session's folder or, on the machine that curates, starts a curation run (`curate now`), and the tabs above lead to the other views, of which `Tasks` (every open task, with `done`) and `Facts` (what m2b knows, each fact with `details`) have no command of their own; under the fullscreen layout that pane opens by itself |
| `/m2b-note <text>` | writes the text into the inbox at once, through `m2b capture` |
| `/m2b-search [--word] <text>` | shows the hits of `m2b search` in the m2b pane; `--word` matches whole words only |
| `/m2b-review` | shows the last curation run in the m2b pane: every finding, candidate and question |
| `/m2b-proposals` | shows what your sessions proposed for your memory, each to keep or drop |
| `/m2b-settings` | shows every setting of m2b in the m2b pane, sorted by what you want from m2b, each with what it does and, for a switch, its values to press; it takes no value and answers none ([The band](band.md#every-setting-in-the-pane)) |

## The `m2b` command

Setup writes `~/.local/bin/m2b`. On macOS that folder is not on the `PATH` by default;
[Getting started](getting-started.md#in-claude-code) has the line to add. `m2b --help` lists the commands, `m2b <command>
--help` the options of one, `m2b --version` prints the version. A command that groups actions,
such as `m2b tasks`, prints its help when named alone. Where a line below has `[--json]`, the
command answers as JSON with it.

### Every day

| Command | What it does |
|---|---|
| `m2b capture [--follow-up <day>] [--quiet] [--source <name>] [--json] <text>` | writes a new note into the inbox; with `--follow-up YYYY-MM-DD` also a task due that day; `--quiet` keeps the note out of everything proactive; `--source` says who wrote it, `cli` when left out ([Integrations](integrations.md)); without text, or with `-`, it reads standard input |
| `m2b capture-file [--source <name>] <path> [<words>]` | copies a file into the inbox, the original stays where it is: the file under a new name and a note beside it with the words (with `-`, from standard input) and the file's original name, which the next curation run reads. A relative path, a folder, a symbolic link, a text file (capture its words with `m2b capture`) and a file over `capture.file_limit_mb` megabytes are refused in one line with exit 2. No skill may run it without asking |
| `m2b search [--any] [--word] [--json] <terms>` | full text over archive, memory and inbox; the terms are one phrase, with `--any` each term counts on its own |
| `m2b source [--json [--viewer]] <name>` | one fact file or note, read whole by its name: the name a distillate line ends with (`dana.md`), or a note's name from the archive (a document's or picture's name answers its note); a fact file with its lines, last day, earlier values and evidence, a note with its words and what curation added, a document's note with its original name and outline. A path or any other name is refused with exit 2; a file not on this machine is named with the command that fetches it. `--viewer` adds for a note whether `m2b store open` opens its file, why not, and where it lies; the pane passes it, the skill `m2b:search` cannot |
| `m2b todos [--json]` | open tasks by due date, and today's events |
| `m2b rediscover [--count <n>] [--month <YYYY-MM>] [--today <day>] [--json]` | old notes back into view, three without `--count`; `--today YYYY-MM-DD` sets the day that counts as today |
| `m2b status [--json]` | the inbox, the last curation run, whether one is due, the backends |
| `m2b doctor [--json]` | checks every backend and the programs m2b starts; the first thing to run when something looks wrong |

### Tasks and calendar

With Markdown tasks, these are how you look at a task's id and tick it in a terminal; with Apple
Reminders the Reminders app does the same. In a session, saying that a task is done ticks it, and
so does `done` on its row in the m2b pane's tab `Tasks`.

| Command | What it does |
|---|---|
| `m2b tasks list [--include-completed] [--marker <kind>] [--json]` | every open task with its id, the tasks m2b itself wrote among them: its review task and the "Remember?" candidates |
| `m2b tasks add [--due <day>] [--notes <text>] [--candidate] [--json] <title>` | adds a task and prints its id; with `--candidate` the title is a fact proposed for your memory, a task "Remember? ..." |
| `m2b tasks complete <id>` | ticks a task |
| `m2b tasks drop <id>` | marks a task dropped and completes it; for a candidate this is the "no" |
| `m2b tasks delete <id>` | deletes a task |
| `m2b tasks notes <id> <notes>` | replaces a task's notes |
| `m2b calendar list [--writable] [--json]` | the calendars, or only those an event can be added to |
| `m2b calendar events [--from <day>] [--to <day>] [--json]` | the events of some days, today without options |
| `m2b calendar add --calendar <name> --title <title> --start <start> [--end <end>] [--all-day] [--json]` | creates an event in the calendar you name |

### Curation

| Command | What it does |
|---|---|
| `m2b curate [--force] [--detach [--json] [--after-answers]]` | the curation run: without `--force` only when one is due, as a schedule calls it; `--detach` starts it in the background and says in one line whether a run started, with `--json` as data (`kind` and `message`), which is how `curate now` in the m2b pane starts one ([Curation](curation.md#when-it-runs)). `--detach --after-answers` starts one only where every proposal is answered and one is kept, which is what the pane asks for after an answer; `curation.run_after_answers` turns it off. `--refresh-all` and `--sort-facts` run now and do one more step, once ([Curation](curation.md#moving-over-an-older-distillate)) |
| `m2b curate take-over` | makes this machine the curating machine ([Several machines](several-machines.md)) |
| `m2b proposals [--json]` | what the reading of your sessions proposed and what sessions handed in, as far as it waits for your answer |
| `m2b proposals keep [--all] <ids>` | files these proposals with the next curation run; `--all` leaves those a session handed in, which you keep by id |
| `m2b proposals drop <ids>` | forgets these proposals |
| `m2b proposals add` | hands in a proposal of a session, read as one JSON object from standard input: `kind`, `text`, `quote`, `session`, optionally `due`. Off until `sessions.propose` is `true`. Refuses with one line when the quote does not stand in that session's transcript or the session worked where m2b does not read. The next curation run takes the proposal in |
| `m2b lint scan [--json]` | findings about the store: broken links, misnamed notes, conflict copies |

To pause the runs on a machine: `m2b config set curation.paused true`
([Pausing](curation.md#pausing)).

### Setup and settings

| Command | What it does |
|---|---|
| `m2b setup inspect [--store-backend <backend>] [--store-path <folder>] [--json]` | what a store folder holds, before anything is written |
| `m2b setup apply --answers <json> [--json]` | writes the setup from a JSON object of answers ([Getting started](getting-started.md)) |
| `m2b settings [--json]` | every setting of this machine, the store and the owner: its value, its default, what it does and what changes it; a list, the paths of programs and an add-on come as a count, never with what they hold; `--json` also names the group each has in the pane's settings ([Configuration](configuration.md#every-setting-in-one-list)) |
| `m2b settings set <key> <value>` | changes a switch to one of its values, such as `curation.paused true`; every other key is refused with a line that names what changes it |
| `m2b config get [--json] [<key>]` | the machine config, or one key such as `store.path` |
| `m2b config set <key> <value>` | sets one key of the machine config, validated first ([Configuration](configuration.md)) |
| `m2b profile get [--json] [<key>]` | the owner's profile, or one key of it |
| `m2b profile set <key> <value>` | sets one key of the profile |
| `m2b profile merge <json>` | merges a JSON object into the profile |
| `m2b distillate off [<folder>]` | no distillate in sessions in this folder and below, on this machine |
| `m2b distillate on [<folder>]` | the distillate again in this folder |
| `m2b distillate topic [--json] <name>` | the facts and current items of one topic, as the distillate holds them now; the m2b pane reads a topic's lines with it |
| `m2b distillate topics [--json]` | what every session starts with (the facts outside any topic, each with its fact file, and the current items) and each topic with its counts; the m2b pane's tab `Facts` reads it |
| `m2b addons list [--json]` | each add-on and whether it is on |
| `m2b addons on <addon>` | turns an add-on on; its setup skill does this once the add-on is set up |
| `m2b addons off <addon>` | turns an add-on off; its settings stay |
| `m2b launcher install` | writes or refreshes `~/.local/bin/m2b`. Setup and the session start keep it up to date by themselves; you run it when m2b says so, after moving a file of your own away from that path |
| `m2b launcher resolve <plugin>` | prints the install path of a plugin from the m2b marketplace, which is `m2b` itself, for a script or an integration of yours |

### The store's files

| Command | What it does |
|---|---|
| `m2b store check-local [--json] <paths>` | names the files among these that the sync service has not downloaded |
| `m2b store fetch [--timeout <seconds>] <paths>` | downloads them |
| `m2b store open <name>` | opens a PDF or a picture of the archive in the system's viewer, by its file name, never a path: only where its first bytes are of that kind, the file is on this machine and the session has a screen (not over SSH on a Mac; a display on Linux). Any other kind is refused with exit 2, since a viewer for it could run what it holds; the pane's `open the file` runs it |

### What m2b calls itself

These are listed by `--help`, but the plugin is their caller.

| Command | Who calls it |
|---|---|
| `m2b band [--tasks-only] [--session <id> [--session-only]] [--json]` | the band, for what its row and the pane show; with `--session`, also what m2b gave that session, and with `--session-only` nothing else |
| `m2b refresh due [--json]` | the refresh step, for the memory lines past their day |
| `m2b lint fix [--json]` | the lint step; it runs only inside a curation run |
| `m2b curate model --skill <plugin:skill> --allow <rule>` | the worklog add-on's step in a curation run, for its fenced model step. Run by hand it starts that step on its own, with the tool rules you give it, outside a run |
| `m2b curate report --step <name> --kind <kind> --text <text>` | a model step, to hand a finding to its run |

The commands of the curation run's own steps (`m2b ingest ...`, `m2b harvest`, `m2b journal`) and
`m2b hook <name>` are left out of `--help`. Those among them that move or edit store files refuse
to run outside a curation run; the hooks run at a session start. The worklog add-on has a command of its own, `m2b-worklog` ([Worklog](addons/worklog.md)).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success, also when there was nothing to do |
| 1 | the command ran and found a problem you must act on |
| 2 | a usage or configuration error, m2b not set up among them |
| 3 | a backend could not be reached: the store, the task list, the calendar or the model |
| 4 | a capture could not be written, so nothing was saved |

A session hook always exits 0, so it can never block a session start.
