# The curation run

A curation run files the inbox. It runs on one machine per store, the curating machine that
`store.json` names, and nowhere else.

## When it runs

At session start on the curating machine, in the background, when a run is due: the inbox holds
a capture, or the last successful run is more than 20 hours old. So after a capture the next
session start files it. After a failed run the next attempt waits 1 hour, then 4, then 20; a run
in which only a step failed that does not fail the run ([The steps](#the-steps)) counts as
succeeded and starts no wait. A
schedule can start it too, for days without a session ([On a schedule](#on-a-schedule)), and
`m2b curate --force` starts it now; add `--detach` to get your terminal back while it runs.
On a machine you paused, a run starts only when you ask for one, with `--force`, `--refresh-all`
or `--sort-facts` ([Pausing](#pausing)).

## The steps

```mermaid
flowchart LR
  pre[Preflight] --> migrate[Migrate] --> harvest[Harvest] --> glean[Glean] --> before[before_ingest] --> ingest[Ingest] --> afteri[after_ingest] --> refresh[Refresh] --> sort[Sort] --> lint[Lint] --> journal[Journal] --> after[after_journal] --> proposals[Proposals task] --> review[Review task] --> commit[Commit]
```

| Step | Done by | What it does |
|---|---|---|
| Preflight | code | removes leftover temp files, downloads the files the run reads, loads the profile |
| Migrate | code, only when the store's format is older than this m2b | brings `memory/` up to the rules of this m2b, one format at a time, each checked in code; a failing one puts `memory/` back, keeps the format and ends the run with the review |
| Harvest | code | settles the memory candidates and "Still current? ..." questions you ticked or dropped, and the proposals you kept or dropped |
| Glean | code and one model call without tools, only with `curation.read_sessions` | reads what you typed in Claude Code since the last reading and keeps what the model proposes for your memory ([Reading your sessions](#reading-your-sessions)) |
| Ingest | model, only with captures in the inbox | files facts and what is going on into memory, under its topic what concerns one subject only, tasks into your list, each capture into `corpus/YYYY/MM/` |
| Refresh | model, only when a fact is past its day | rewrites the facts whose `until` has passed |
| Sort | model, only with `m2b curate --sort-facts` | moves facts lines of an older distillate into topics; code puts the file back if a statement changed |
| Lint | code; the model only to repair a broken memory link with exactly one candidate | checks names, links, conflict copies and the distillate's size |
| Journal | code | adds the tasks you completed to the month's `corpus/YYYY/MM/YYYYMM-done.md` |
| Proposals task | code | one task in your list while proposals from your sessions wait for your answer, completed once none waits |
| Review task | code | one task in your list when something needs you |
| Commit | code, only when the store folder is a git repository | one git commit of what changed in the store while the run ran ([A commit per run](#a-commit-per-run)) |

`before_ingest`, `after_ingest` and `after_journal` are where an add-on can hook in; the worklog
runs before ingest. A step that fails is reported in the review task and the run goes on. When
only an add-on's step, the reading of the sessions, the proposals task or the commit failed, the
run still counts as succeeded: the inbox is filed and the next run is due at the usual time, so neither an
add-on that keeps failing nor a transcript m2b cannot read holds back the core.

Each model step runs fenced: `claude -p` from an empty folder, with `--setting-sources project`,
m2b alone as plugin, `--permission-mode dontAsk`, and allowed only the commands and paths of its
step. Its session has only the tools those rules name and no MCP server, reads no `CLAUDE.md`,
yours included, keeps no transcript and can neither read nor change a file in Claude Code's own
folder; a session that starts with more is stopped, and the step
fails ([SECURITY.md](../SECURITY.md#the-fence-around-a-model-step) says what was measured). It uses `curation.model` (`haiku` by default) and stops after `curation.max_turns` tool
calls or `curation.model_timeout_minutes`. The reading of the sessions asks the same model in
another form: the instruction as the prompt, the text on standard input, no tool at all and one
turn, so whatever a prompt says, the model can call nothing.

After each model step that may edit `memory/`, code compares it with a copy taken just before the
step:

- **Refresh** may change only the facts that are due: their fact files and their lines in
  `MEMORY.md`. Any other change puts `memory/` back and fails the step.
- **Ingest and lint** keep their edits. Each facts line they removed or rewrote, and each fact file
  they emptied or removed, is listed in the review task, and again in every later review until you
  complete the task, in your task list or with `ok` in [the band](band.md), where `/m2b-review`
  shows each change with the added and removed words marked. `memory/` as it was before the run is
  kept in
  `~/.local/state/m2b/memory-before-run/<time of the run>/` as long as such a finding names it, so a
  line can be copied back from there.
- **Any model step**, sorting included, that writes a line holding characters that hide or reorder
  text (bidirectional controls, zero-width spaces, tag characters) is undone and fails; a capture
  still in the inbox is marked so the next run files its facts again. The failure names the file,
  the line number and the characters, not the line's text, and not a file the step added. The
  session-start and prompt hooks
  remove these characters and every other that draws nothing (soft hyphens, fillers, variation
  selectors) before the distillate reaches a session.

## A commit per run

A run rewrites `memory/` and moves captures by itself. If you keep the store in a git repository,
each run ends with one commit, and `git revert <commit>` takes that run back. m2b does this when
the store folder itself is the top of a git work tree (you ran `git init` in the store folder) and
git is on the curating machine. It never makes the repository for you; without one nothing changes
and nothing is reported.

What the commit holds:

- every visible file that changed in the store while the run ran: the facts it wrote, the captures
  it moved, task files, the finished run record. A run keeps no list of its own writes, so a
  capture you took in those minutes is in it too;
- nothing else. What you left uncommitted or staged stays as it is, hidden files stay out, and so
  does a file git ignores, unless the repository tracks it already. An edit of yours in a file the
  run also wrote goes in with that file.

A run that changed nothing but its own record makes no commit; the record goes in with the next
one. A run stopped at preflight or before its end makes none either, and what it changed stays in
the work tree for you to look at.

The commit is m2b's own. Author and committer are `m2b <m2b@localhost>`, so `git log --author=m2b`
lists the runs, and the message says when the run started and how its steps ended. m2b writes no
git configuration, never pushes, runs no hook and signs nothing, because a run has nobody to
answer a prompt; the filters your repository sets for adding a file (encryption, line endings) do
run. It commits onto HEAD as it is, whatever branch that is. In the middle of a merge, rebase,
cherry-pick, revert or bisect of yours, or when HEAD moved while it worked, it does not commit.

A commit that fails never fails the run: it is the failed step `commit` in the review task and in
the run record. The next run commits what changes while it runs, not what the uncommitted one left.

In a synced folder git is handed only files that are on this machine. A changed file that is not
downloaded is left out, and a `.gitignore` or `.gitattributes` that is not downloaded stops the
commit and names the command that fetches it. Keep the repository's own files out of a synced
folder: `git init --separate-git-dir <a folder outside>` in the store folder leaves only a small
`.git` file there. A sync service that evicts or duplicates files inside `.git` breaks a
repository, whoever commits into it; m2b's git never downloads such a file, it fails, and the
review says so.

`m2b config set curation.git_commit false` on the curating machine turns the commit off.

`m2b doctor` says in its line `store-git` whether a run on this machine commits: `no repository`
without a `.git` in the store folder; `found` with the git directory and the git that named it
when a run here commits; `found` with the reason when this machine does not curate or has the
commit off; or `cannot commit` with the reason. A machine without git is such a reason, and
doctor is the only place you learn of it, because a run there commits nothing and says nothing.
Doctor looks for git on the `PATH` it is started with; a run started by a schedule looks on the
`PATH` the schedule gives it.

## Reading your sessions

Much of what belongs in a second brain is said in passing: who runs what at a customer, what was
agreed on the phone, what you promised by Friday. With `curation.read_sessions` set to `true` in
the machine config, a curation run looks for it in what you typed in Claude Code and proposes it;
nothing is filed before you say keep. It is off by default. Setup asks on the machine that
curates, and `m2b config set curation.read_sessions true` or `false` changes the answer later.

**What is read.** Claude Code's transcripts on this machine, and of them only the prompts Claude
Code marks as typed by a human, in the terminal or the desktop app. Left out: Claude's answers and
tool results, a pasted block with what it holds, what a plugin, a finished task or another agent
sent, a suggested prompt you only accepted, and the blocks Claude Code writes into a prompt.
Credentials are redacted, and a prompt ends after 2,000 characters. A session that started in or
below a folder of `worklog_leave_out` in the profile, or one where you ran `m2b distillate off`,
does not reach the model, and neither does a headless run such as a curation run itself. The same
setting names work by a git remote of its repository
([Leaving work out](addons/worklog.md#by-git-remote)): a session in such a repository does not
reach the model, and while you name a remote, neither does one whose repository nobody can tell,
because its folder is gone and nothing was noted for it or git does not answer. The run's
information counts both.

**When.** The step `glean` runs after harvest and before ingest, so what you captured yourself is
in the store by then. It covers the time since the last reading ended: the last 24 hours at the
first reading and never more than 7 days; what lies before is named as not read. Without a typed
prompt in that time no model starts.

**What is kept.** The model gets the distillate, so it can leave out what is known, the proposals
you kept and dropped lately (below), and per session its folder, its day and its prompts. It answers with proposals of four kinds, a person, an
agreement, a commitment and something personal, each with the words of yours it stands on. Code
keeps a proposal only when those words stand in one prompt of the session it names, with at least
three words, and when you did not capture the same thing in that time. A proposal like one that
waits, or like one you kept or dropped or that expired within 90 days, is not kept a second time,
so reading a period again adds nothing.

**Your answer.** `m2b proposals` lists what waits, each with its id, its kind, the text, your words
and the day you said them:

```bash
m2b proposals                 # what waits for an answer
m2b proposals keep <id>...    # or: m2b proposals keep --all
m2b proposals drop <id>...
```

With the band, one row above the prompt says how many wait, and `/m2b-proposals` opens them in a
pane where keep, drop and keep all are buttons ([the band](band.md#the-proposals-from-your-sessions-in-the-pane));
they add the same answers as the commands.

An answer is filed by the next curation run: harvest writes a capture with the proposal's text
(source `proposal`, `from_proposal` in its frontmatter), and ingest files it like any capture. A
commitment that names its day gets its task with the capture. A dropped proposal is remembered for
90 days and not proposed again. Where a keep and a drop for one proposal meet, from two machines,
keep stands.

While proposals wait, your task list holds one task for them, "m2b: proposals from your sessions",
however many there are; its notes say how many wait, so a phone shows that something does. The
task is no answer: completing or deleting it keeps and drops nothing. Every curation run brings
the number up to date, whether or not it reads the sessions, and completes the task once nothing
waits. A task you completed or deleted comes back only when a proposal was added since.

**Without an answer.** A proposal you did not answer within 14 days expires: it leaves the
listing, the task and the band's row, and is not proposed again for 90 days. It does not count as
dropped. While it is remembered, `m2b proposals keep <id>` still keeps it. Every curation run lets
proposals expire and removes those kept, dropped or expired 90 days ago, whether or not it reads
the sessions.

**What your answers change.** The next reading shows the model what you answered: up to 30
proposals you kept and up to 30 you dropped, of each those a run settled last, with the kind, the
text and your words. The model is told to leave out what is like something you dropped, also where
it would otherwise propose it, and in doubt to propose what is like something you kept; the four
kinds and what is never proposed stay as they are. So dropping the time of a call a few times is
how you say that such things do not belong in your memory. It is a rule a model follows, not a
check in code. An expired proposal is not shown: you did not look at it, which says nothing about
it. A proposal is no example any more 90 days after a run settled your answer to it. The model is
also told never to propose an example itself, and code would refuse one: its words stand in no
prompt of the period.

**How much you keep.** `m2b status` says what share you kept of the proposals you answered in the
last 30 days, and how many expired in that time:

```text
proposals: kept 7 of 10 answered in the last 30 days (70%), 2 expired without an answer
```

Expired proposals are not part of the share, and without an answer in the 30 days the line says
so instead of 0%. `m2b status --json` holds the same under `proposal_answers`, and with it the
counts per kind since the first reading: how many were proposed, kept, dropped and expired, and how
many were refused because the words they quote do not stand, with at least three words, in a
prompt of the session they name. m2b does nothing with these numbers: they are there for you to
see whether the reading proposes what you want, and `curation.read_sessions` stays your switch.

**When it fails.** A transcripts folder m2b cannot look at, a model without an answer or an answer
it cannot read fails the step alone: the review says so, nothing is saved, and the next run reads
the same time again. A period with texts of which none carries Claude Code's mark of who sent it
fails the same way, so a Claude Code too old to write the mark never passes for a day on which
nothing was typed.

## What runs when

| | After install, before setup | After its setup |
|---|---|---|
| core | nothing: the session-start hooks print nothing and no run starts until `/m2b:m2b setup` | the distillate at session start, a curation run at the next session start after a capture on the curating machine |
| band | draws nothing and starts nothing while there is no launcher | the band and the status line, while mods are on in Claude Code |
| `worklog` | prints nothing, records nothing | herdr events recorded on the curating machine, a daily worklog note |

## After an update

When a new m2b changes a rule for content already in the store, it raises the store's format
(`format` in `store.json`, see [Store format](store-format.md#formats)), and the curating
machine's next run migrates the store before anything else: you run nothing. `m2b status` and
`m2b doctor` show `store format: migrates` until then. Update the curating machine first: an m2b
that knows an older format reads a newer store and captures into it, but does not curate it
([Several machines](several-machines.md#machines-on-different-versions)).

## Moving over an older distillate

Two one-off runs bring a `memory/` written by another tool, or by m2b before 0.1.0, up to date:

```bash
m2b curate --refresh-all   # dates the memory lines written without dates
m2b curate --sort-facts    # sorts the facts of an older distillate into topics
```

`--refresh-all` reads the evidence of every undated line and sets `until` or `since` only where a
capture names the day. `--sort-facts` moves the lines that matter for one subject under its topic;
code then compares the file and puts the old one back if any statement changed. It leaves
`## Current` as it is: an item above the topics there moves under its topic when ingest files a
capture about the same thing, or when you move it by hand.

## Pausing

To keep a machine from starting runs by itself, for example while a subscription's limit is
nearly used up or while you look at what the last run did:

```bash
m2b config set curation.paused true
```

From then on no session start on this machine starts a run, and a scheduled `m2b curate` does
nothing and exits 0. Everything else goes on: captures reach the inbox, sessions get the
distillate, and `m2b curate --force` files the inbox when you ask for it, as do the one-off runs
`--refresh-all` and `--sort-facts`. `m2b status` has a line
`paused` while the setting is on, and shows a scheduled attempt as `last attempt: paused at ...`.
`m2b config set curation.paused false` ends the pause; the next session start then starts the run
that is due.

The setting is this machine's. It does not move curation: while the curating machine is paused,
no other machine files the inbox ([Several machines](several-machines.md)).

## On a schedule

Most setups need no schedule: the next session start on the curating machine files what waits. A
schedule helps when captures reach the inbox while that machine starts no Claude Code session for
days, for example captures from a second machine, or an integration such as a Shortcut that
writes into the inbox. A scheduled `m2b curate` that is not due does nothing and exits 0, so it
is safe to run daily; on a paused machine ([Pausing](#pausing)) it does nothing either.

A schedule calls the launcher `~/.local/bin/m2b`, which setup wrote with the absolute path of
`python3`; the model steps use the absolute paths of `claude` and `reminders` that setup recorded,
because a scheduled job runs with a short `PATH`. Check them with:

```bash
m2b config get executables --json
```

### macOS: a Shortcuts automation

A launchd job is not given access to iCloud Drive and Reminders the way an app is; a personal
automation in Shortcuts runs as Shortcuts, and macOS asks once for access to the folder and to
Reminders.

1. Open **Shortcuts**, then **Automation**, then **New Automation**.
2. Choose **Time of Day**, set a time such as 06:30, **Daily**, and **Run Immediately**.
3. Add the action **Run Shell Script**. Shell: `zsh`. Script:

   ```bash
   "$HOME/.local/bin/m2b" curate
   ```

4. Save, then run the automation once by hand and allow the access macOS asks for.

### Linux: cron

```cron
30 6 * * * /home/alex/.local/bin/m2b curate >> /home/alex/.local/state/m2b/cron.log 2>&1
```

Use your own home folder; cron does not expand `~`. If the store is a synced folder, schedule the
run after the sync client has started. The launcher finds the core through Claude Code's plugin
list; on a machine that runs m2b from a checkout instead of the installed plugin (the `claude`
command is still needed for the model steps), name the checkout in the line:

```cron
30 6 * * * M2B_CORE_ROOT=/home/alex/src/m2b/plugins/m2b /home/alex/.local/bin/m2b curate >> /home/alex/.local/state/m2b/cron.log 2>&1
```

### Checking a scheduled run

`m2b status` shows when the last run started and how it ended; a run that found nothing due shows
as `last attempt: not due at ...`, so you can see the schedule reached m2b. The machine's run log
is `~/.local/state/m2b/run.log`; a run that could not even write its record leaves its cause there.

A run m2b starts in the background, at a session start or with `m2b curate --detach`, has no
terminal and no log of yours to print to. What it writes on standard error is kept in
`~/.local/state/m2b/detached-run.err`, replaced each time such a run starts; look there when a
run left neither a record nor a line in the run log.

## The status line

While [the band](band.md) runs, one line below the prompt sums up the brain. It is refreshed about
once a minute and after each of your turns. Normally it reads `0 in inbox · curated 17:07`: the
captures waiting for the next run, and when the last successful run ended (the time today, the date
on an earlier day), or `not curated yet` while no curation run has succeeded. Claude Code draws a
⚠ in front of every plugin's status line; it is not a warning. In place of the pair it can say:

| Status line says | Meaning |
|---|---|
| `curating` | a curation run is going on now |
| `last run failed, see review` | the last run failed; the review task in your list names the step and the cause |
| `last run interrupted` | the last run ended without finishing, for example because the computer shut down or its process was killed |
| `could not read the last run` or `could not read the inbox` | that part of the store could not be read |

A problem is added after it, such as `could not read store.json` or `tasks not reachable` (likewise
for the store and the calendar); the task list, store and calendar are checked every 5 minutes, so
such a problem can show up or clear that much later. `could not look` means `m2b status` gave no answer at all;
run it in a terminal to see why.
