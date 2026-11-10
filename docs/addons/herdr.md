# The herdr add-on

One of the [add-ons](../addons.md) of m2b, off until its setup turns it on.

## What it does

At session start, the session gets one line for each other agent session open in
[herdr](https://herdr.dev), the terminal workspace manager for agents: workspace, task (the terminal
title), state in plain words and the last two parts of its folder. Overlapping work is noticed
before it starts. With invented names:

```
- garden-plan · Order the raised beds · working · projects/garden-plan
- invoices · Claude Code · idle · worktrees/invoices
```

## What it needs

herdr 0.9 or later, on the `PATH` Claude Code sees or named in the environment variable `M2B_HERDR`,
and a session started in a herdr pane. In a session started outside herdr it prints nothing.

## Set up and turn off

`/m2b:herdr-setup` checks that herdr answers and turns the add-on on; `m2b addons off herdr` turns
it off. There is nothing to install or register in herdr.

## What it reads and writes

It reads herdr's session snapshot (`herdr api snapshot`) with a 2 second limit, and only at session
start, never inside a curation run. It writes nothing, on the machine or in the store. When herdr
cannot be read, the line says so, so "herdr could not be read" never looks like "no other sessions".

## Its commands

`m2b-herdr check` says whether herdr answers and how many agent sessions are open, and changes
nothing. `m2b-herdr neighbours` is the session-start hook.

## How you see it runs

The lines at the start of a session in a herdr pane, under the distillate. Recording what you do is
the worklog's job, never this one's.
