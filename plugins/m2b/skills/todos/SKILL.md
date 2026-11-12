---
name: todos
description: Shows the owner's open tasks from their second brain, grouped by due date, and today's calendar events where a calendar is set up, and ticks a task the user says is done. Use when the user says "what's on today", "what is still open", "my open tasks", "what's due", "which appointments do I have", "was steht heute an", "was ist noch offen", "meine offenen Aufgaben", "was liegt an", "welche Termine habe ich", or that a task of theirs is done - "the ladder task is done", "I returned the ladder, tick it off", "mark X as done", "X ist erledigt", "hak X ab". Never invents a task or an event, and never writes a note about a task that is done.
allowed-tools: Bash(m2b todos *), Bash(m2b tasks complete *)
---

# Todos

You show the user what is open in their task list and what is in their calendar today, and you
tick a task they say is done. Moving or adding tasks is not part of this skill: a new task is a
capture.

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
- `unreadable` lists task files that could not be read (exit 1): say first that you could not
  look at those, with each `path` and its `reason`, then the rest; never say that nothing is open
  while it has an entry.
- The command fails: say that you could not look, never that nothing is open. Exit 2 means no
  second brain is set up on this machine; exit 3 means the task list or the store could not be
  reached, and the message on standard error says which and how to fix it.

Answer in the user's language, short, as a list a person can scan.

## Ticking a task

When the user says a task of theirs is done, tick it. Do not write a note about it and do not
search the notes for it: the task list is where it lives.

1. Read the list with `m2b todos --json`, as above, and find the task they mean by its title.
2. Exactly one open task fits: tick it with its `id`.

   ```bash
   m2b tasks complete <id>
   ```

   The command prints nothing and exits 0 when the task is ticked. Say in one line which task you
   ticked, with its title as it is, so the user sees it when you took the wrong one.
3. Several fit: list them with their due dates and ask which one. Never tick more than the user
   named, and never pick one by guessing.
4. None fits: say that no open task matches and name the open ones that come closest. Tick nothing
   and note nothing.

The command fails: say that the task is not ticked, with the message on standard error. The review
task of the curation run, the memory candidates and the "Still current?" questions are not in the
list and are not ticked here; the user answers them in the band or in their task list.
