---
name: sort-facts
description: Sorts the facts of an existing distillate in the owner's second brain into topics, once, so a customer's or a club's facts reach a session only when it is about them. Runs only inside a curation run started with `m2b curate --sort-facts`, fenced; asked for it in a session ("sort my facts into topics", "sortier mein Gedächtnis in Themen"), it does not sort there and starts that run in the background instead.
allowed-tools: Bash(m2b refresh due *), Bash(m2b curate --sort-facts --detach)
---

# Sort facts

A distillate written before topics existed has every fact above the first `###` heading, so every
session gets every fact. You move the lines that matter only for one subject under that subject's
topic. You only move lines and write topic headings: the code compares the file afterwards, and if
any statement, any line outside `## Facts` or any other text changed, it puts the old file back and
the step fails.

Run every command as a Bash call of its own, exactly as shown: no `&&`, `;`, `|`, `echo` or
redirection. Read files with the Read tool, one file per call, never with `cat`, `cd` or a loop in
Bash: a denied call fails the step.

## 1. Only inside a curation run

```bash
m2b refresh due --json
```

It tells you the store's folder (`store`; every path below starts with it) and whether this is a
curation run. If `curation_run` is `false`, you were asked in an ordinary session. Do not sort
here. Start the run in the background:

```bash
m2b curate --sort-facts --detach
```

Tell the owner exactly what it printed, and stop.

## 2. Read the distillate

Read `<store>/memory/MEMORY.md`. Lines before the first `###` heading of `## Facts` are printed at
the start of every session. A `###` heading starts a topic: its name, then in parentheses the words
that bring it in; its lines are printed only when one of those words is in the owner's prompt or the
project folder's path, as a whole word, ignoring case. Where a line alone does not tell you its
subject, read its fact file, `<store>/memory/<file>`.

## 3. Sort

For each facts line, ask whether Claude needs it in any session (the owner, family and close
people, the owner's employer or firm, lasting preferences, ongoing commitments) or only when one
subject comes up (a customer, an organisation, a project, a group of people such as a club).

- In any session: it stays above the first `###` heading.
- Only for one subject: it goes under that subject's topic, unchanged, character for character. A
  topic without a heading under `## Facts` gets one at the end of `## Facts`. A topic that stands
  under `## Current` keeps its heading, copied character for character, because headings with the
  same name are one topic; a new topic gets `### <name> (<word>, <word>)`, the name at most 60
  characters, with two to five words that name it unambiguously, each 3 to 40 characters: the
  organisation's name and the short form the owner uses ("Globex AG" and "Globex"), full names of
  its people, a project's name. Never a first name or a common word alone ("Kim", "Chor",
  "export").
- A line already under a topic stays there.
- A `###` heading that is no topic (no words in parentheses) may become one, keeping its lines.

Write the whole file once, with Edit, when you have decided every line. Change nothing under
`## Current` and no other file. When unsure about a line, leave it where it is: in every session
is the safe place.

## Answer

One line: how many lines moved into how many topics, and how many stayed for every session.
