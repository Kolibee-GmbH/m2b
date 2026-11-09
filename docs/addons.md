# Add-ons

m2b is one plugin with four add-ons in it: `band`, `backup`, `herdr` and `worklog`. Each is off
until its own setup skill turns it on, and an add-on that is off runs no curation step, prints
nothing at session start and draws nothing. Which ones are on is kept per machine, in
`~/.config/m2b/config.json`:

```bash
m2b addons list
m2b addons on backup
m2b addons off backup
```

Turning an add-on off keeps its settings, so its setup skill turns it on again with what was set
before. An add-on reaches the core only through the `m2b` command, the way an
[integration](integrations.md) does, and keeps what it needs to remember in the store under
`state/addons/<add-on>/`.

| Add-on | Runs on | When |
|---|---|---|
| `band` | every machine where it is on | in each session, about once a minute and after each of your turns |
| `backup` | the curating machine | after each curation run, as its last step |
| `herdr` | every machine where it is on, in sessions started in a herdr pane | at session start |
| `worklog` | the curating machine only | records in herdr all the time; writes once a day, in the curation run before the inbox is filed |

## band

**What it does.** A band above the prompt shows the open memory candidates ("Remember? ...") and
"Still current?" questions, each with keep and drop, and the open review task with its findings.
Keep completes the task; drop marks it dropped and completes it; nothing else changes. Below
the prompt, a status line sums up the brain, such as `brain: 3 in inbox · curated 18:02`; what
each of its states means is in [The curation run](curation.md#the-status-line).

**What it needs.** Mods turned on in Claude Code, and the launcher `~/.local/bin/m2b`, which the
core writes at the first session start after setup. With Apple Reminders, the terminal Claude
Code runs in needs access to Reminders, or the band shows one error line instead of the tasks.

**Set up and turn off.** `/m2b:band-setup` checks the launcher and the task list and turns the
band on; `/m2b:band-setup remove`, or `m2b addons off band`, turns it off. The band and the status
line are gone after your next turn, or within two minutes without one.

**What it reads and writes.** It calls `m2b addons list`, `m2b status` and `m2b tasks list` and
nothing else; keep and drop call `m2b tasks complete` and `m2b tasks drop`. Every open session
asks about once a minute, so the answers are shared between sessions for 55 seconds in
`~/.local/state/m2b/band-addons.json`, `band-snapshot.json` and `band-status.json`. Apart from
keep and drop, which change that one task in your task list (with the `markdown` backend, its file
in `tasks/` of the store), it writes nothing in the store.

**Its commands.** None of its own; it is the mod in `plugins/m2b/hooks/`.

**How you see it runs.** The status line under the prompt. When m2b cannot answer, it says
`brain: could not look` instead of an old state. An empty band is normal while there is no
candidate, no question and no open review.

## backup

**What it does.** After each curation run, it makes a local snapshot of the store in a folder you
choose:

```
<target>/mirror/            the store's visible files as of the last backup
<target>/attic/YYYY-MM-DD/  each mirror file a backup replaced or removed, under that day
<target>/tasks.json         the task list with completed tasks
```

iCloud Drive and other synced folders copy a mistake to every machine within minutes, so the
store alone is no backup.

**What it needs.** A folder outside the store and outside any synced folder, which exists
already, and the curating machine: the backup runs as a step of the curation run.

**Set up and turn off.** `/m2b:backup-setup` asks for the folder and the days, writes both, turns
the backup on and makes the first backup at once. By hand:

```bash
m2b config set addons.backup.target ~/Backups/m2b
m2b config set addons.backup.attic_days 30
m2b addons on backup
```

`m2b addons off backup` turns it off; the settings and the snapshot stay.

**What it reads and writes.** It reads the store's visible files, the task list through
`m2b tasks list` and its own settings through `m2b config get addons`. Hidden files, Excel lock
files (`~$<name>`) and files iCloud Drive has not downloaded are not copied: a file that is not
downloaded keeps the copy the mirror has, and the backup counts it. It writes only in the target
folder, and removes there only attic folders older than `attic_days` (30 by default), folders in
the mirror that became empty, and its own leftover temporary files. In a curation run it reports
what it could not copy, such as files not downloaded, in the review task. A target on a disk that
is not connected makes the backup fail instead of writing somewhere else.

**Its commands.** `m2b-backup run` makes one backup now, the same as the curation step.

**How you see it runs.** `m2b-backup run` prints how many files it copied and how many tasks it
dumped. In a curation run, a backup that fails is a finding in the review task, and the run goes
on.

## herdr

**What it does.** At session start, the session gets one line for each other agent session open
in [herdr](https://herdr.dev), the terminal workspace manager for agents: workspace, task (the
terminal title), state in plain words and the last two parts of its folder. Overlapping work is
noticed before it starts. With invented names:

```
- garden-plan · Order the raised beds · working · projects/garden-plan
- invoices · Claude Code · idle · worktrees/invoices
```

**What it needs.** herdr 0.9 or later, on the `PATH` Claude Code sees or named in the environment
variable `M2B_HERDR`, and a session started in a herdr pane. In a session started outside herdr it
prints nothing.

**Set up and turn off.** `/m2b:herdr-setup` checks that herdr answers and turns the add-on on;
`m2b addons off herdr` turns it off. There is nothing to install or register in herdr.

**What it reads and writes.** It reads herdr's session snapshot (`herdr api snapshot`) with a
2 second limit, and only at session start, never inside a curation run. It writes nothing, on the
machine or in the store. When herdr cannot be read, the line says so, so "herdr could not be read"
never looks like "no other sessions".

**Its commands.** `m2b-herdr check` says whether herdr answers and how many agent sessions are
open, and changes nothing. `m2b-herdr neighbours` is the session-start hook.

**How you see it runs.** The lines at the start of a session in a herdr pane, under the
distillate. Recording what you do is the worklog's job, never this one's.

## worklog

**What it does.** Once a day it writes a worklog of your sessions: for each session its topic and
state, time spans per sphere of work, and booking proposals for billable spheres. The note lands
in the inbox like any capture and is filed into the archive by the same run, so the distillate's
Current section sees your day. The time spans also go into a ledger in the store, with CSV and
XLSX exports. It may propose a fact for memory as a "Remember? ..." task; tick it and the next run
files it.

- **Spheres** are the areas your work falls into, such as an employer, a company of your own and
  private projects. Each has an `id`, a `label`, whether its time is `billable`, and how it is
  recognized: parts of git remote URLs (`git_remote_contains`) and folders under your home folder
  (`path_under`). A session that matches none falls to the default sphere. They live in
  `profile.json` in the store, beside the list of customers a booking proposal may name.
- **A time span** is when a workspace was in use: an agent at work, the workspace in focus (herdr
  cannot tell typing from looking, so focus counts for a limited time after each event), or
  messages in its transcript at most 15 minutes apart, merged across gaps of up to 15 minutes.
  Waiting for an approval does not count; an agent left working on its own does, so check a
  proposal before you enter it.
- **A booking proposal** comes only from a span of a billable sphere with a customer from your
  list. The worklog never books: you enter the proposal in your timesheet, because a wrong booking
  ends up on an invoice.

A period starts where the last one ended and reaches at most three days back, so a long pause
costs one catch-up of three days. The step does nothing while the last worklog ended less than
20 hours ago.

**What it needs.** herdr 0.9 or later; the curating machine, the only one that records, so a day
is never counted on two machines; your spheres and customers, which its setup asks for.

**Set up and turn off.** `/m2b:worklog-setup` asks for the spheres and customers, writes them to
the profile, installs the recorder in herdr and turns the worklog on. `/m2b:worklog-setup remove`
turns it off and unlinks the recorder; by hand:

```bash
m2b addons off worklog
m2b-worklog recorder remove
m2b-worklog hook session-start
```

The last command sets the recording switch to `off` at once instead of at the next session start.
The recordings stay until `m2b-worklog recordings delete` removes them.

**What it reads.** Only while it is on and only on the curating machine: the herdr events its
recorder wrote; from your Claude Code transcripts for the period under `~/.claude/projects/`, the
prompts and the last 500 characters of each session's last answer, with credentials and long
tokens redacted; your own git commits and the `origin` remote in the session folders; and the
names of the period's captures in the inbox. Its model step, once a day, reads these facts,
memory, the inbox notes and your task list, and may search the archive with `m2b search` to place
a session.

**What it writes.**

| Where | What |
|---|---|
| `~/.local/share/m2b/worklog-recorder/` | the recorder copy herdr links, outside the plugin's folder, which an update replaces |
| `~/.local/state/m2b/worklog/` | the recorder's events, one file per workspace, a workspace cache, and the switch file `recording` (`on` or `off`) |
| `~/.local/state/m2b/worklog-run/` | the facts and the verdict while one worklog is being written |
| `inbox/` in the store | the day's note, with `source: worklog` and `kind: worklog` |
| `state/addons/worklog/` in the store | `ledger.json` (the record), `ledger.csv` and `ledger.xlsx` (rebuilt every day, not for editing), `watermark.json` (where the next period starts), `intent.json` (only while a worklog is being written, so a rerun after a crash finishes the same plan) |
| the task list | "Remember? ..." candidates |

The recorder writes only while the m2b plugin is installed and on in Claude Code and the switch
says `on`. The worklog's session-start hook sets the switch: on while the worklog is on, this
machine curates and the recorder is installed, off otherwise. So a take-over by another machine
or `m2b addons off worklog` turns recording off at the next session start.

**Its commands.** `m2b-worklog machine` says whether this machine curates, so it may record.
`m2b-worklog recorder install` and `remove` link and unlink the recorder,
`m2b-worklog recordings delete` deletes what it recorded, and `m2b-worklog run` is the curation
step. The others (`facts`, `verdict`, `collect`, `hook`) are for the curation run and the
plugin's hooks.

**How you see it runs.** The switch file `~/.local/state/m2b/worklog/recording` says `on`, and a
note titled "Worklog ... to ..." lands in the archive once a day. `ledger.csv` in
`state/addons/worklog/` grows by the period's spans. A worklog step that fails is a finding in the
review task, and the run goes on.
