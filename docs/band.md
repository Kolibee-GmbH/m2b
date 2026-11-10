# The band

The band is where m2b speaks to you inside Claude Code: a few rows above the prompt and one line
below it. It is part of m2b and needs no setup of its own; it starts once m2b is set up on the
machine.

```text
 [ keep ] [ drop ] Remember? Sam brings the plywood on Saturday
 [ keep ] [ drop ] Still current? Planning the trip to Porto
 m2b: review
   lint: broken link in people/sam.md
╭──────────────────────────────────────────────────────────────╮
│ >                                                            │
╰──────────────────────────────────────────────────────────────╯
 ⚠ m2b: 2 in inbox · curated 21:36
```

## What it shows

- **Memory candidates**, "Remember? ...": facts a curation run proposes for the distillate.
- **"Still current?" questions**: items under "Current" in the distillate that have gone quiet.
- **The review**: the open review task of the last curation run, with its first findings.

Candidates and questions share at most three rows, and the review shows at most three findings,
each followed by "and N more" when there are more. The band is empty, and takes no room, while
there is nothing to show.

**Keep and drop are buttons: click them with the mouse.** Keep completes the task; drop marks it
dropped and completes it; nothing else changes, and the next curation run reads which one you
chose.

A click writes nothing for 5 seconds. The row shows what it will do and offers `undo`:

```text
 [ undo ] dropping: Remember? Sam brings the plywood on Saturday
 [ keep ] [ drop ] Still current? Planning the trip to Porto
```

`undo` takes the click back, and the task stays as it was. After the 5 seconds the band reads the
list again and writes: an item another session settled meanwhile is left alone, and the band says
so in one line. Closing the session, or a crash, within those seconds writes nothing either, so a
click is never half done; the item is simply still there next time. The click is written also when
the row has left the band meanwhile, pushed below the first three or replaced by an error line.
Until the band has read the list after the write, the row offers nothing to click, for at most
3 minutes.

The band draws every text as one plain line: escape sequences and control characters a capture
brought along from terminal output are left out, line breaks and tabs become spaces.

## The status line

Below the prompt, one line sums up the brain, such as `2 in inbox · curated 21:36`: the captures
waiting for the next run, and when the last successful run ended. Claude Code puts the plugin's
name and a ⚠ in front of every plugin's status line; the ⚠ is not a warning (Claude Code 2.1.322
offers plugins no way to leave it out). Every state the line can show is in
[The curation run](curation.md#the-status-line).

## After an update

A session keeps the band it started with, while `m2b` itself is always the installed version. When
the session's band is the older one, it says so in one line:

```text
 this session runs the band of m2b 0.3.0 while m2b 0.3.1 is installed: run /reload-plugins
```

`/reload-plugins` in that session, or a new session, loads the installed band. A band newer than
the installed m2b, as when Claude Code runs it from a checkout, says nothing. A session started
before m2b 0.3.0 cannot say this yet; its band shows an error line or nothing until it is started
again.

## What it needs

- m2b set up on the machine, and the launcher `~/.local/bin/m2b`, which m2b writes at the first
  session start after setup.
- Mods on in Claude Code. The band is a mod, a module Claude Code loads with the plugin. Two
  different things can keep it out:
  - **Mods off, hooks on.** A session that started without network access can save Claude Code's
    rollout switch for mods as off. Then only the band and the status line are missing; the
    distillate at session start, capture, search, tasks and curation work as before. Start `claude`
    once with network access, then a new session.
  - **No plugin hooks at all.** Under `claude --bare`, or with `allowManagedHooksOnly` or
    `disableAllHooks` in managed settings, Claude Code runs none of m2b's hooks: no band, and no
    distillate at session start either. Capture, search and tasks still work through the skills,
    and curation runs where it is scheduled.
- With Apple Reminders, access to Reminders for the terminal Claude Code runs in, or the band shows
  one error line instead of the tasks.

`m2b doctor` tells the two apart. m2b's own session-start hook and the band each note when a
session started them, and the line `band` compares the two: `seen` when the latest session ran the
band, `not seen` with the first case when that session ran m2b's hooks but not the band, `not seen`
with the second case when no session has run m2b's hooks since setup. Right after setup it can say
`not seen` until the next session starts.

## What it reads and writes

It runs only while `~/.config/m2b/config.json` and the launcher exist. Each refresh is one `m2b`
call, `m2b band --json`; keep and drop call `m2b tasks complete` and `m2b tasks drop`, after
reading the list again with `m2b band --json --tasks-only`. Every open session asks about once a
minute and after each of your turns, so the answer is shared between sessions for 55 seconds in
`~/.local/state/m2b/band-view.json`; an answer of a shape the band does not know, or stamped later
than now, is not used. However many turns end while `m2b` is slow, at most one more refresh waits.
That folder holds titles and findings, so m2b keeps it readable by you only. At each session start
it writes `~/.local/state/m2b/band-seen.json`, which `m2b doctor` reads. Apart from keep and drop, which
change that one task in your task list (with the `markdown` backend, its file in `tasks/` of the
store), it writes nothing in the store.

`m2b band --json` reaches and reads the task list once (with Apple Reminders, two calls to
`reminders`) and sorts the open tasks by their marker, and adds the answer of `m2b status --json`,
reusing that one look at the task list for its check of the backends. With invented tasks:

```json
{
  "version": "0.3.0",
  "tasks": {
    "candidates": [{"id": "c1", "title": "Remember? Sam brings the plywood", "notes": "m2b:candidate", "due": null, "completed": false, "completed_at": null, "dropped": false, "marker": "candidate"}],
    "questions": [],
    "reviews": []
  },
  "status": {"machine_id": "alex-laptop", "inbox": {"count": 2, "evicted": 0}, "run": {"state": "succeeded", "last_succeeded_at": "2026-03-14T21:36:00+01:00"}, "backends": {"store": {"state": "reachable", "detail": ""}, "tasks": {"state": "reachable", "detail": ""}, "calendar": {"state": "not configured", "detail": ""}}}
}
```

`version` is the installed core's, which the band compares with its own. `status` holds more
fields than shown, as `m2b status --json` does. When the task list cannot be
read, `tasks` is `{"error": "<why>"}` and `status` still answers. The checks of the backends are
kept for five minutes, so at most every five minutes the answer waits for the calendar too, here
for at most 10 seconds whatever `calendar.timeout_seconds` says; a calendar that does not answer
by then is reported as not reachable. `--tasks-only` leaves `status` out.

## Where it lives

In `plugins/m2b/hooks/`: `register.tsx` and its helpers, loaded through `"modules"` in
`hooks/hooks.json`. Its tests are in `plugins/m2b/tests/band/` and run with
`scripts/check --quick band`.

## Upgrading from m2b 0.2.0

The band was an add-on there, off until `/m2b:band-setup` turned it on. Now it runs wherever m2b is
set up, also on a machine where it was turned off: an entry `addons.band` in `config.json` is
ignored, and `m2b addons off band` removes it. Sessions open during the update keep the old band
until they are started again.

## How you see it runs

The status line under the prompt. When m2b cannot answer, or the band's own refresh fails, it says
`could not look` instead of an old state. An empty band is normal while there is no candidate, no
question and no open review.
