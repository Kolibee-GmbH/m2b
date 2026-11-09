---
name: ingest
description: Files the inbox of the owner's second brain - facts into memory, tasks, refs - and moves each capture into the archive. Runs only inside a curation run, which starts it fenced; asked for it in a session ("curate now", "file my inbox", "räum die Inbox auf"), it does not curate there and starts a curation run in the background instead.
allowed-tools: Bash(m2b ingest list *), Bash(m2b curate --force --detach)
---

# Ingest

You file what the owner captured. In a capture, "I", "my" and "we" are the owner, whose name
`m2b ingest list --json` gives as `owner`: a fact about them goes into the fact file of that name
and its facts line names them, "Alex prefers window seats", never "I". Each capture in
the inbox may hold facts (things that stay true: about the owner, people, agreements), tasks
(things to do), refs (links), something going on right now, or nothing to file at all. You change
captures only through `m2b ingest`, you write only into `memory/`, and you read the archive only
through `m2b search`. Nothing else is allowed, and the run would deny it.

Run every command as a Bash call of its own, exactly as shown: no `&&`, `;`, `|`, `echo` or
redirection. The run allows each `m2b` command by itself and denies anything chained. The exit
code comes back with the call's result.

Read every file with the Read tool, one file per call, also when many captures wait: never with
`cat`, `cd`, `ls` or a loop in Bash. The run denies those, and one denied call fails the whole
step.

## 1. Only inside a curation run

```bash
m2b ingest list --json
```

If `curation_run` is `false`, you were asked in an ordinary session. Do not curate here. Start a
curation run in the background, which files the inbox fenced and takes some minutes:

```bash
m2b curate --force --detach
```

Tell the owner, with the number of captures waiting, exactly what it printed: either that a run
started (and that `m2b status` shows how it goes) or why none did. Do not say more than it
printed; it cannot know yet how the run ends. Then stop.

The answer also gives `store` (the store's folder; every path below starts with it) and
`language` (write every task title, facts line and note in this language).

## 2. Normalize, then list again

```bash
m2b ingest normalize --json
m2b ingest list --json
```

Normalize names foreign files by the schema and turns photos into bundles; the second list shows
the result. Work through `captures` in the order given, which is the order they were captured.

## 3. Read memory once

Read `<store>/memory/MEMORY.md`. It has two sections:

```markdown
# Memory

## Facts

- Dana's birthday is on 3 March (dana.md)
- Alex prefers green tea in the morning (alex.md)

### Acme Ltd (Acme Ltd, Acme, Kim Lee)
- Kim Lee leads Acme's IT and wants a status mail every Friday (kim-lee.md)

## Current

- Planning the trip to Porto (since 2026-10-02)
```

A facts line is exactly `- <statement> (<fact-file>.md)`. The lines before the first `###` are
printed at the start of every session. A `###` heading starts a topic: its name, then in
parentheses the words that bring it in; its lines are printed only when one of those words is in
the owner's prompt or the project folder's path, as a whole word, ignoring case. Current is a short
list of what is going on; each line ends in `(since YYYY-MM-DD)`. Keep statements short, one line
per fact, and remove old current items when they are over.

## 4. Each capture

Read `<store>/inbox/<file>`. A capture with `kind: sidecar` stands for a photo or other file;
read its members too (the `.jpg` reading copy where there is one). Then, in this order:

**Facts**, unless `facts_filed` is `true` (then they are filed already; skip to tasks).

1. Choose the fact file. A subject that already has one (see the facts lines) keeps it. A new
   subject gets a new name in lowercase with hyphens, `dana.md`, `passport.md`; read
   `<store>/memory/<name>.md` first, and if it exists for someone or something else, take
   `<name>-2.md`, then `-3`.

   A fact that stops being true on a known day (see `until` below) always gets a fact file of its
   own, named after the subject and the matter, `sam-plywood.md`, even when the subject already has
   one: `until` holds for a whole file, and a lasting fact about Sam must not be rewritten when the
   plywood day has passed. Its facts line is a line of its own too.
2. Write the fact file. It holds the current truth, then the evidence, the first link being the
   capture that brought the fact:

   ```markdown
   # Dana

   - Birthday on 3 March.
   - Likes old maps.

   ## Evidence

   - [[20261107T091500Z-cli-a1b2.md]]
   ```

   Links name archive files with their extension. A capture is linked once per fact file: if its
   link is already in the evidence list, do not add it again. When a new capture changes a fact,
   change the line and add the link, and keep the old value under `## Earlier`, above
   `## Evidence`, with the last day it held, the day of the capture that changed it:

   ```markdown
   # Dana

   - Lives in Bern.

   ## Earlier

   - Lived in Zurich (until 2026-11-07)

   ## Evidence
   ```

   A capture that only adds to a fact, or corrects a mistake in it, changes nothing that was
   true, so it leaves `## Earlier` alone. Earlier values never go into `MEMORY.md`.

   A fact that stops being true on a known day (an appointment, a deadline, someone away until
   the end of the month, an offer valid for two weeks) gets that last day in the fact file's
   frontmatter, so a later run can rewrite it once the day is past:

   ```markdown
   ---
   until: 2026-11-14
   ---
   # Sam
   ```

   Work the day out from the capture's `created`, not from today: a weekday is the next such day
   after it, "end of the month" its last day, a season its last day (spring ends on 31 May). A
   lasting fact (a birthday, where something is kept, a preference) gets no `until` and never goes
   into a file that has one. When a new capture changes the fact, set `until` anew or remove it.
3. Add or change the facts line in `MEMORY.md`. Never two lines with the same statement. Where
   the line goes:

   - Ask whether Claude needs the fact in any session (the owner, family and close people, the
     owner's employer or firm, lasting preferences, ongoing commitments) or only when one subject
     comes up (a customer, an organisation, a project, a group of people such as a club).
   - In any session: above the first `###` heading, never at the end of `## Facts`, where it
     would land in the last topic.
   - Only for one subject: under that subject's topic. If there is none yet, start one at the end
     of `## Facts`: `### <name> (<word>, <word>)`, the name at most 60 characters, with two to
     five words that name it unambiguously, each 3 to 40 characters: the organisation's name and the short form the
     owner uses ("Globex AG" and "Globex"), full names of its people, a project's name. Never a
     first name or a common word alone ("Kim", "Chor", "export"); a heading without words never
     brings the topic in.
   - A fact that introduces a person of an existing topic may add that person's full name to its
     words, up to five.
   - A line that is already in a topic stays there; change it in place.
4. Mark it:

   ```bash
   m2b ingest facts-filed <file>
   ```

A capture with `source: candidate` is a fact the owner already confirmed: file its text as a
fact as it stands, without weighing it again.

A capture with `kind: worklog` is the day's worklog, written by the worklog add-on from the
owner's sessions. It holds no facts and no tasks to file: its proposals for memory are candidates
already. Use its topics only for `## Current` (what the owner is working on now; replace a line
about the same work instead of adding one), then note and move it like any capture.

**Current.** Something going on right now (a trip being planned, a job being started) becomes a
line under `## Current`, unless the capture has `quiet: true`; a quiet capture is filed, but
never brought up. The line ends in `(since YYYY-MM-DD)`, the day of the capture's `created`; a
later capture about the same thing moves that day, so a run can ask the owner about a line no
capture has touched for a month.

**Tasks.** Each thing to do becomes one task. The key is one word that tells it apart from the
capture's other tasks:

```bash
m2b ingest task <file> --key plumber --title "Call the plumber" --due 2026-11-13
```

`--due` only when the capture names a day (`YYYY-MM-DD` or `YYYY-MM-DD HH:MM`). A capture with
`follow_up` gets its task with `m2b ingest task <file> --follow-up` and no other options.

**Refs.** Each URL in the text:

```bash
m2b ingest ref <file> https://example.org/passport-office
```

Where an older note is clearly about the same thing, find it with `m2b search <words>` and add
its archive file name the same way. At most two searches per capture.

**Note and move.** One line saying what you filed, then the move:

```bash
m2b ingest note <file> "filed: fact dana.md, task plumber"
m2b ingest finish <file>
```

Exit 1 from any of these means this capture has a problem: report it (step 5) and go on with
the next capture; it stays in the inbox. Exit 3 means the store or the tasks could not be
reached: report it and stop.

## 5. Report

Hand everything the owner should know to the run, one finding each:

```bash
m2b curate report --step ingest --kind action --text "20261107T091500Z-cli-a1b2.md stays in the inbox: ..."
m2b curate report --step ingest --kind info --text "2 captures not downloaded, left for the next run"
```

`action` when the owner must do something (a problem from `list` or from a command, a conflict
copy normalize kept); `info` for the rest (evicted files). Nothing to report: report nothing.

## Never

- Change a capture's text, or any file outside `<store>/memory/`.
- Delete a file.
- Guess a fact the capture does not state.

## Answer

One line: how many captures were filed, how many facts, tasks and refs, and how many stayed.
