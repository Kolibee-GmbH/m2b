---
name: worklog-verdict
description: Judges one period of the owner's work for the m2b worklog - topic, state, sphere and booking per session, and memory candidates - and hands the verdict to m2b-worklog. Runs only inside the daily worklog of a curation run, which starts it fenced; asked for it in a session ("write my worklog", "was habe ich heute gemacht"), it says that the worklog is written once a day by the curation run.
allowed-tools: Bash(m2b-worklog facts *)
---

# Worklog verdict

The worklog collected the facts of one period: the owner's sessions with their working blocks,
prompts, commits and state. You judge them; a program writes the note, the ledger and the
candidates from your verdict. You read through the commands below and the files under
`<store>/memory/` and `<store>/inbox/`, nothing else, and you write nothing yourself.

Run every command as a Bash call of its own, exactly as shown: no `&&`, `;`, `|`, `echo` or
redirection. The run allows each command by itself and denies anything chained.

## 1. The facts

```bash
m2b-worklog facts --json
```

If it fails with "no worklog is being judged", you were asked in an ordinary session. Say that
the worklog is written once a day by the curation run, before the inbox is filed, and stop.

The answer has `store` (the store's folder), `language` (write every topic, detail and candidate
in this language) and `facts`. In `facts`:

- `period`: the start and end of what you judge.
- `sources`: each source and whether it could be read. A source that could not be read means
  work may be missing, never that there was none.
- `spheres`: the owner's areas of work. Only a sphere with `billable: true` gets bookings.
- `customers`: the only customers you may name. The list is the owner's; never add to it.
- `sessions`: each with a `key`, its place (`repo`, `label`, `folder`), its `sphere` when the
  profile's rules found one (else `null`), `blocks` (each with an `id` such as `b1`, its times and
  the owner's `prompts` in it), `commits`, and `state` (`agent`: `working`, `blocked` for an agent
  waiting for an approval, `idle`, or `null`; `last_answer`: the agent's last text).
- `captures`: the notes still in the inbox from the period, by name.

## 2. What the owner knows already

Read `<store>/memory/MEMORY.md` once. Its facts lines are what the owner keeps; do not propose
any of them again. If a capture in `facts.captures` helps to understand a session, read it at
`<store>/inbox/<name>`. Look at the open candidates, so you do not propose one twice:

```bash
m2b tasks list --json
```

To place a session you cannot place from its prompts, you may search the archive:

```bash
m2b search --json -- "<two or three words>"
```

## 3. The verdict

For **every** session in `facts.sessions`, exactly once:

- `key`: the session's key, copied.
- `topic`: what the session was about, in a few words a person would use ("Invoice export
  rounding", not "Working on code").
- `state`: `done` when the work reached its end, `waiting` when it waits for the owner (an agent
  `blocked`, or a last answer that asks the owner something), else `open`.
- `state_detail` (optional): one short phrase, such as what it waits for.
- `sphere` (optional): only when the session's `sphere` is `null`, the `id` of the sphere it
  belongs to; leave it out when unsure.
- `note` (optional): one sentence worth keeping about the session's outcome.
- `blocks`: an object with each block `id` of the session. When the session's sphere is billable,
  give `{"customer": "<name from customers>", "project": "<optional>", "activity": "<what kind of
  work>"}` for a block you can attribute, and `null` for one you cannot. For any other sphere,
  `null` for every block. A booking is a proposal; the owner books.

`candidates`: facts worth keeping that the period revealed, about people, agreements or the
owner's ways of working, each as `{"text": "<one sentence>", "session": "<key>"}`. At most three,
none is fine. Never a task, never something already in memory, never a guess.

Hand in the verdict as one JSON argument, in single quotes:

```bash
m2b-worklog verdict '{"version": 1, "sessions": [...], "candidates": [...]}'
```

It answers `verdict accepted`, or lists each problem by its place, such as a customer that is not
in the list or a session left out. Fix those and hand it in again. A text that needs a single
quote gets a typographic one (’) instead.

## 4. When you cannot

If after three attempts the verdict is still refused, or the facts cannot be read, tell the run:

```bash
m2b curate report --step worklog --kind action --text "<what went wrong, in one sentence>"
```

Then stop. The worklog is written at the next run; nothing is lost.
