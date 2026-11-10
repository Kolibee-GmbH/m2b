# The band add-on

One of the [add-ons](../addons.md) of m2b, off until its setup turns it on.

## What it does

A band above the prompt shows the open memory candidates ("Remember? ...") and "Still current?"
questions, each with keep and drop, and the open review task with its findings. Keep completes the
task; drop marks it dropped and completes it; nothing else changes. Below the prompt, a status line
sums up the brain, such as `brain: 3 in inbox · curated 18:02`; what each of its states means is in
[The curation run](../curation.md#the-status-line).

## What it needs

Mods turned on in Claude Code, and the launcher `~/.local/bin/m2b`, which the core writes at the
first session start after setup. With Apple Reminders, the terminal Claude Code runs in needs access
to Reminders, or the band shows one error line instead of the tasks.

## Set up and turn off

`/m2b:band-setup` checks the launcher and the task list and turns the band on; `/m2b:band-setup
remove`, or `m2b addons off band`, turns it off. The band and the status line are gone after your
next turn, or within two minutes without one.

## What it reads and writes

It calls `m2b addons list`, `m2b status` and `m2b tasks list` and nothing else; keep and drop call
`m2b tasks complete` and `m2b tasks drop`. Every open session asks about once a minute, so the
answers are shared between sessions for 55 seconds in `~/.local/state/m2b/band-addons.json`,
`band-snapshot.json` and `band-status.json`. Apart from keep and drop, which change that one task in
your task list (with the `markdown` backend, its file in `tasks/` of the store), it writes nothing
in the store.

## Its commands

None of its own; it is the mod in `plugins/m2b/hooks/`.

## How you see it runs

The status line under the prompt. When m2b cannot answer, it says `brain: could not look` instead of
an old state. An empty band is normal while there is no candidate, no question and no open review.
