---
name: todos
description: Shows the owner's open tasks from their second brain, grouped by due date, and today's calendar events where a calendar is set up. Use when the user says "what's on today", "what is still open", "my open tasks", "what's due", "which appointments do I have", "was steht heute an", "was ist noch offen", "meine offenen Aufgaben", "was liegt an", "welche Termine habe ich". Only reads; never invents a task or an event.
allowed-tools: Bash(m2b todos *)
---

# Todos

You show the user what is open in their task list and what is in their calendar today. You only
read; completing, moving or adding tasks is not part of this skill.

## Reading

```bash
m2b todos --json
```

Run each `m2b` command in a Bash call of its own, as shown: nothing chained before or after it,
no `echo $?`. This skill may run the command alone without asking, and Claude Code reports a
failing exit code by itself.

The JSON has `today`, four groups of tasks (`overdue`, `due_within_7_days`, `later`,
`without_date`; each task with `id`, `title`, `notes` and `due`) and `events`:

- `"configured": false`: no calendar is set up on this machine.
- `"reachable": false`: the calendar could not be read; `message` says why.
- Otherwise `events` lists today's events, each with `title`, `start`, `end` and `all_day`.

The review task of the curation run, the memory candidates and the "Still current?" questions are not
in the groups; they are handled elsewhere.

## Answer

- Start with what needs the user first: overdue tasks, with how long they are overdue, then today's
  events in time order, then what is due within the next seven days with its weekday.
- Tasks without a date: list them briefly; when there are many, give the count and the first few.
- `later`: mention only how many there are, unless the user asked for everything.
- Use the titles as they are. Never add a task, an event, a time or a detail that is not in the
  JSON. A task's `notes` may say where it came from; mention it only when it helps.
- Empty groups and no events: say there is nothing open and nothing in the calendar today. If the
  calendar is not configured, say that instead of "no events"; if it could not be read, say so
  with the reason from `message`.
- The command fails: say that you could not look, never that nothing is open. Exit 2 means no
  second brain is set up on this machine; exit 3 means the task list or the store could not be
  reached, and the message on standard error says which and how to fix it.

Answer in the user's language, short, as a list a person can scan.
