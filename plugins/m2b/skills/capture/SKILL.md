---
name: capture
description: Captures something into the owner's second brain - a note, a fact about a person, an idea, a task for later, a calendar entry. Use when the user says "remember this", "note that", "don't forget", "remind me to", "put it in my calendar", "merk dir das", "notier das", "denk dran", "erinnere mich an", "trag das in meinen Kalender ein", or when something personal without a home in the current repository comes up and the user wants to keep it. Only writes new notes; never curates.
allowed-tools: Bash(m2b capture *), Bash(m2b calendar *)
---

# Capture

You write what the user wants to keep into the inbox of their second brain. Curation files it
later; you only add.

## What goes in, and what does not

- Personal things without a home in a repository: facts, ideas, open questions, tasks.
- What the user learns about people and verbal agreements: who is who, which role, what was
  agreed, from work too.
- Never documents of customers or confidential statements about third parties.
- A project's own todos and decisions belong in that project's repository, not here. When
  something touches both, the repository gets the content and the capture gets a pointer.

Write the text in the user's words, as they said it after the request itself ("remember that",
"note that", "merk dir, dass"), turned into a plain sentence where the request made it a clause
("merk dir, dass ich lieber am Fenster sitze" becomes "Ich sitze lieber am Fenster."): the capture
is the original, and curation reads it later. Do not summarize, correct or translate it, and add nothing
the user did not say, no year to a date, no surname to a first name. Keep "I", "my" and "we": in
the second brain they always mean the owner, so never put the owner's name in their place.

```bash
m2b capture --source claude - <<'CAPTURE'
I prefer window seats on long train rides.
CAPTURE
```

Only where a sentence leans on the conversation, add what it leaves open in square brackets,
right after the word: "He [Sam] brings the plywood on Friday."

## Writing the capture

Pass the text on standard input, so quotes and line breaks arrive as written, as in the example
above or this one:

```bash
m2b capture --source claude - <<'CAPTURE'
Dana's birthday is on 3 March; she likes old maps.
CAPTURE
```

Run each `m2b` command in a Bash call of its own, as shown: nothing chained before or after it,
no `echo $?`. This skill may run the command alone without asking, and Claude Code reports a
failing exit code by itself.

- **A task for later** ("remind me on Thursday to call Dana"): add `--follow-up YYYY-MM-DD`. The
  command creates a task due that day that points back to the capture. If it says the task waits
  for the next curation run, tell the user the note is saved and the task follows.
- **Not to be brought up again** ("just keep it, don't remind me"): add `--quiet`.
- Exit 2 means nothing was written (for example empty text, a date that is no day, no second
  brain set up, or settings this m2b cannot read, which may need an update); say what the
  command printed and stop. Exit 3 means the store could not be
  reached; nothing was written either.
- Exit 1 after a capture with `--follow-up` means the note was saved but its task could not be
  confirmed and may already exist. Do not run the command again; tell the user to look at the
  task list.

## Calendar entries

When the user asks for a calendar entry, it goes into the calendar they name, never into a
default.

1. No calendar named: run `m2b calendar list --writable` and ask which one, listing them.
2. Then create the event:

```bash
m2b calendar add --calendar "Home" --title "Dentist" --start "2026-11-12 10:00" --end "2026-11-12 11:00"
```

For an all-day event use `--start YYYY-MM-DD --all-day`, and `--end` for the last day when it
spans several. Read back what the command reports (calendar, day and time) in one line, so the
user hears a misheard date. Exit 1 lists the calendars that can be written; ask again with those.
If the reply says the calendar is not configured, tell the user and offer a capture with a
follow-up instead.

## Answer

One line: what was kept, and the follow-up date or the calendar entry if there was one.
