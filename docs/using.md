# Using m2b

What you can say in a session and what happens then, in detail. The [README](../README.md) has
the short table; [Commands](commands.md) lists every command for a terminal or a script, and
[The curation run](curation.md) every step of a run.

## Capture

In any session, say what you want kept: "remember that Dana's birthday is on 3 March", "note
this", "remind me to call the plumber on Friday". You type no command: the model's note tool,
or the `capture` skill where the band does not run, writes a note into `inbox/` in your own words,
without the request around them ("remember that", "remind me to"). With a date it also creates a
task that points back to the note, and the day stands in the task. Typed in a terminal, `m2b capture "<text>"` keeps the text character for character.
Say that you want it
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

![Asked to remember that the shed roof needs 40 screws and to be reminded on a weekday, Claude calls the m2b note tool with a follow-up date, which writes one inbox file and a task due that day; below the answer the band is one row, "m2b 1 waits for you" with the button "open", and one task due today and one overdue below it](images/capture.png)

From a terminal or a script, without a Claude session, the same goes through the command:

```bash
m2b capture "Dana's birthday is on 3 March"
m2b capture --follow-up 2026-11-20 "Call the plumber about the shed"
```

A file goes in two ways. Drop it into `inbox/` in the store, from the Finder or a phone's share
sheet, and the next curation run makes a note beside it. Or, in a session, name it with its path:
"keep this contract, ~/Documents/lease.pdf, it runs until March". The `capture` skill copies it
into the inbox with your words through `m2b capture-file`, and Claude Code asks you before every
such copy, since the file goes into a folder that syncs to every machine. A file over 25 MB, a
folder, a link and a text file are refused; `capture.file_limit_mb` sets the size. A PDF is read
up to its 60th page, and a picture as a picture ([A document in the inbox](curation.md#a-document-in-the-inbox)).

## The distillate at session start

A session-start hook prints the distillate, at most 8 KB: lasting facts, each pointing to its
fact file, and what is going on right now. Facts that matter only for one subject sit under a
topic; a session sees the topic's name, and its facts come in when a prompt or the project
folder's path names it. The hook also prints one line when something needs you: the last
curation run failed, the curating machine has not run for three days, or the store cannot be
found. The distillate is marked as data from your notes, not instructions. In a project where it
should not appear, such as a screen share or a customer's repository, `m2b distillate off` in
that folder turns it off for every session there and below, on this machine; the m2b pane has a
button for it ([The band](band.md#turning-m2b-off-in-a-folder)).

Sessions capture what you learn about people and verbal agreements, at work too: who is who,
which role, what was agreed. What else goes in is yours to decide, a customer's document among it
([SECURITY.md](../SECURITY.md#what-m2b-handles) says where it then lies and who reads it). A customer's people land under that customer's topic, so their facts reach a
session only when it is about that customer. What you are working on for that customer lands under
the same topic in Current; what goes on in your own life stays above the topics there and reaches
every session.

## Lessons

A correction you kept, such as "run only the checks the change touches", is a lesson. Every
session starts with the lessons for every project in a block of their own after the distillate,
written as corrections you made and kept, not as notes. A lesson that `~/.claude/CLAUDE.md` or
another source states now is left out, and `m2b status` says where it is kept. When distillate and
lessons together pass the 2 KB target, lint says so with both sizes.

A lesson about a command, such as "run the whole proof only when the change gives a reason, when
you start scripts/check", comes right before Claude runs that command: a hook adds it before each
Bash call whose command holds its words, and stays silent where the command holds a word you named
to keep it quiet (`--quick`). Say "keep this as a lesson" in a session and the next curation run
files it. A lesson can ask you before the call instead of only reminding.

## A project

Say "remember this project" in a session in a clone, and the session captures it with
`m2b capture --project`: your words and the address of the repository's git remote, which is the
same on every machine. The next curation run makes it a topic with a line
`- Repository: github.com/acme/portal (acme-portal.md)`. When a prompt or the project folder's path
names the topic, it comes into the session with the folder that repository lies in on that
machine, or `not cloned on this machine`. A folder without a remote is not kept, and a project
that already has a topic is not kept twice.

## Fixes for the files Claude reads

When a `CLAUDE.md` or a rule file says something wrongly, say so in a session: "keep this as a
fix: CLAUDE.md, the line about the whole proof is out of date, it should say: run the checks the
change touches". The session keeps it with `m2b fix add`. m2b never writes that file, which is
yours and often committed. The next session that starts in a clone of that repository, on any of
your machines, gets one line before the distillate: a fix waits for this file, with its name. A
fix for a file under `~/.claude/` waits in every session on the machine it was kept on. The
session reads the fix with `m2b fix show`, applies it with you, and marks it done once you confirm
it. Where the file in that checkout holds neither the line the fix replaces nor its new wording,
the session tells you: the checkout may be on another branch, so the fix waits on until you give it
up with `m2b fix drop`. `m2b fix list` shows every fix you kept.

## Search, todos, rediscover

"What did I note about the shed?", "what's open?", "show me something old": the `search`,
`todos` and `rediscover` skills answer from the store. Search is full text over archive, memory
and inbox; hits from memory come first, then the archive, then the inbox, in both the newest note
first. The skill searches a word together with its translation, so a note written in German
answers a question asked in English. Asked for a detail the fact does not hold, "what exactly
does the rowing club's handbook say about lockers?", the session reads the fact's file whole, and
from there the note of the document behind it, which says what stands on which page. It never
reads the document itself: where the note and its outline do not hold the answer, it says so. Todos lists overdue, this week and undated tasks, ticks a task you say is done, and shows today's events when a calendar
is set up. Rediscover brings one or a few old notes back, each with its reason, also for "what
did I note last spring?". A file iCloud Drive has not downloaded is named, never read and never
counted as missing.

!["What's on my list?" runs the todos skill: one overdue task, one due today, the screws captured just before within the next seven days, one without a date, and a note that no calendar is set up on this machine; the band below counts 1 that waits and names the two due tasks](images/todos.png)

## The curation run

It starts by itself at session start on the curating machine when a capture waits in the inbox
or the last successful run is more than 20 hours old. A schedule is optional; it helps when captures arrive
while the curating machine has no session for days ([On a schedule](curation.md#on-a-schedule)).
To start one yourself, press `curate now` in the m2b pane or run `m2b curate --force` in a terminal.
The model reads only when there is something to read: new captures, or a fact past the day it
was true until, such as an appointment. A step that fails is reported and the run goes on; the
review task in your list says what needs you. If the store folder is a git repository, each run
ends with one commit, and reverting it puts back what the run changed, the captures it filed included ([Taking a run back](curation.md#taking-a-run-back) names the exceptions). [The curation run](curation.md) lists its
steps, the one-off runs for a distillate moved over from another tool, and the status line.

A note can be several things at once, a fact and a task for one, and a sentence that reads two
ways is filed one way: "Sam brings the ladder back on Saturday" became a task in one run and a
fact until that Saturday in another. The last line of the archived note says what was filed.

## What a run asks you

A line under Current that no capture has touched for a month comes back as a task "Still
current? ...": tick it and it stays; drop it in the m2b pane, or delete the task, and it leaves the
distillate.

**Proposals from your sessions.** Much of what belongs in a second brain you say in passing,
without "remember this": who runs what at a customer, what was agreed, what you promised by
Friday. A curation run can read what you typed in Claude Code since the last reading and propose
it, each proposal with the words it stands on beside it, said or pasted. It is off until you say yes in setup
(`curation.read_sessions` in the machine config), and nothing is filed before you say keep: in
the m2b pane, which `/m2b-proposals` turns to them, or with `m2b proposals`, `m2b proposals keep <id>`
and `m2b proposals drop <id>`. Once you have answered every proposal in the pane and kept at least
one, a curation run starts in the background on the machine that curates and files what you kept,
so the next session knows it; on another machine, or with `curation.run_after_answers` off, your
answers wait for the next run. Only the prompts you typed are read, with what you pasted into them
and with credentials redacted, and beside each one the end of Claude's answer before it and the
shell commands of that turn; nothing else of Claude's answers, no tool's output, nothing a plugin or another
agent sent, and no session you left out by its folder or its git remote ([Reading your sessions](curation.md#reading-your-sessions)).

A session can also hand in a proposal by itself, with words from what its agent read for you, a
mail or a document. That is off until you turn `sessions.propose` on, and such a proposal says in
the list that a session handed it in and where its words stand
([What a session hands in](curation.md#what-a-session-hands-in)). It reaches that list with the
next curation run; until then `m2b status` and the overview of the m2b pane say how many were
handed in and wait for it.

**Memory candidates.** `m2b tasks add --candidate "<a fact>"` proposes one fact as a task
"Remember? ...", for a script or an integration of yours: tick it and the next run files it; drop
it in the m2b pane, or delete the task, and it does not come back for 90 days.

**Ticking a task.** Say in a session that a task is done, "I returned Sam's ladder, tick it
off", and the `todos` skill ticks it: it finds the task in your list and asks when more than one
fits. In the m2b pane, the tab `Tasks` lists every open task of yours, each with `done`
([The band](band.md#all-your-open-tasks)). With Apple Reminders you can also tick in the Reminders app. In a terminal with Markdown
tasks, `m2b tasks list` shows every open task with its id, the review task and these questions
among them; `m2b tasks complete <id>` ticks one and `m2b tasks drop <id>` drops one. Keep and
drop in the m2b pane call the same two commands.

## Who it is for

You work in Claude Code on more than one project and want what you learn about people,
agreements and your own life to outlast a session and a repository. A project's own decisions
belong in its repository and its `CLAUDE.md`; m2b is for what has no repository.

| | Holds | Where it lives | Who writes it |
|---|---|---|---|
| `CLAUDE.md` | instructions and facts for one project | in the repository | you, by hand |
| Claude Code's memory | short notes Claude keeps for itself | Claude Code's own files, per repository, on one machine | Claude, in the session |
| m2b | your notes, facts and tasks across all projects, as plain files you own | a folder you choose, synced as you like | you capture; a curation run files |

## m2b or Claude Code's auto memory

Claude Code keeps its own memory: short notes it writes for itself during a session, in files
under `~/.claude` for each project. It stays on beside m2b, and a first "remember this" may land
in either. The rule every session gets with the distillate keeps them apart: how Claude should
work stays with Claude Code, in its memory or in a `CLAUDE.md`; what concerns your life and world
across projects goes to m2b. A correction that holds in every project goes to `~/.claude/CLAUDE.md`,
not into the memory of the project you made it in, where no other project would see it; and where
a `CLAUDE.md` already says the matter wrongly, the session keeps a fix for it
([Fixes](#fixes-for-the-files-claude-reads)) instead of a second rule beside it.

What m2b has that Claude Code's memory does not:

- your words kept as you said them, in the archive, with every fact pointing back to them;
- facts that end on a known day (`until`) and are rewritten once it has passed;
- tasks, in Apple Reminders or Markdown files, from the same "remind me";
- filing in a separate run, so your session never spends turns on it;
- topics, so a customer's facts reach only the sessions about that customer;
- one store across all projects and machines, in a folder you choose and sync as you like, as
  plain Markdown you can read, back up and move without m2b.

## Words used here

| Word | Meaning |
|---|---|
| store | the folder that holds your notes: `inbox/`, `corpus/` (the archive), `memory/` |
| capture | one note as you said it, one file in `inbox/`; for a file you gave m2b, the file and a note beside it |
| inbox | `inbox/` in the store: the captures no run has filed yet |
| archive | `corpus/` in the store: every filed capture, by the month it was captured in |
| curation run | the background run that files the inbox, on one machine per store, the curating machine |
| distillate | `memory/MEMORY.md`: lasting facts, each pointing to its fact file in `memory/`, and under "Current" what is going on now |
| fact file | one file in `memory/` for one subject, such as `dana.md`: its facts, and under "Evidence" links to the captures they came from |
| topic | a heading in the distillate for one subject, such as a customer or a club, whose facts come in only when a session is about it |
| review task | the one task m2b keeps in your task list for what a run needs you to look at: a step that failed, a finding, a facts line it removed or rewrote. Ticking it, or `ok` in the m2b pane, closes it |
| proposal | a fact a curation run suggests from what you typed and pasted in your sessions, or a session hands in by itself, with the words it stands on beside it. Each way is off until you turn it on, the reading in setup and handing in with `m2b config set sessions.propose true` in a terminal of your own or a press on its `on` in the pane's settings, and nothing is filed before you keep it |
| memory candidate | a task "Remember? ..." that proposes one fact, put into your list by a script or an integration of yours: tick it and the next run files it |
| band | m2b's row in a session, below the prompt in a terminal and above it in the desktop app unless `band.place` moves it: it counts what waits for your answer and has `open` for the m2b pane, where you keep or drop what curation proposes, tick a task and see your facts with what they rest on; below the prompt, a status line while something is wrong with m2b |
| mod | a module Claude Code loads with a plugin. m2b's mod is the band, with its `/m2b-...` commands and the tools of the model: note, search and, where you turn it on, handing in a proposal |
| add-on | an optional piece of m2b, off until its own setup: `worklog` |
| herdr | an [agent runtime](https://herdr.dev), a product of its own. Only the worklog add-on needs it; the rest of m2b runs without it |
