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
chose. Before writing, the band reads the list again: an item another session settled meanwhile is
left alone, and the band says so in one line.

## The status line

Below the prompt, one line sums up the brain, such as `2 in inbox · curated 21:36`: the captures
waiting for the next run, and when the last successful run ended. Claude Code puts the plugin's
name and a ⚠ in front of every plugin's status line; the ⚠ is not a warning (Claude Code 2.1.322
offers plugins no way to leave it out). Every state the line can show is in
[The curation run](curation.md#the-status-line).

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

It runs only while `~/.config/m2b/config.json` and the launcher exist, and then calls `m2b status`
and `m2b tasks list` and nothing else; keep and drop call `m2b tasks complete` and `m2b tasks drop`.
Every open session asks about once a minute and after each of your turns, so the answers are shared
between sessions for 55 seconds in `~/.local/state/m2b/band-snapshot.json` and `band-status.json`.
At each session start it writes `~/.local/state/m2b/band-seen.json`, which `m2b doctor` reads. Apart from keep and drop, which change that one task in your task list (with the
`markdown` backend, its file in `tasks/` of the store), it writes nothing in the store.

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

The status line under the prompt. When m2b cannot answer, it says `could not look` instead of an old
state. An empty band is normal while there is no candidate, no question and no open review.
