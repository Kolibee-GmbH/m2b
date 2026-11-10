---
name: m2b
description: The entry point of m2b, the owner's second brain - says what it is and what to type, and with an argument guides through setup, shows the status or checks the machine. Use when the user types /m2b:m2b, asks "what is m2b", "how do I use my second brain", "what can m2b do", "is my second brain working", or wants the add-ons (band, herdr, worklog, backup) explained or turned on.
argument-hint: "[setup | status | doctor | addons]"
allowed-tools: Bash(m2b status), Bash(m2b status *), Bash(m2b doctor), Bash(m2b doctor *), Bash(m2b addons *)
---

# m2b

The owner typed `/m2b:m2b $ARGUMENTS`. Answer in the owner's language.

Run each `m2b` command in a Bash call of its own, as shown: nothing chained before or after it,
no `echo $?`. This skill may run the command alone without asking, and Claude Code reports a
failing exit code by itself.

## No argument: help

Say in three or four lines what m2b does: "remember this" in any session files a note into the
inbox; at the next session start a curation run files it into an archive, tasks and a small
distillate every new session starts with; `search`, `todos` and `rediscover` answer from the notes. Then list what to
type, one line each:

- `/m2b:m2b setup` sets this machine up, step by step
- `/m2b:m2b status` shows the inbox, the last curation run and the backends
- `/m2b:m2b doctor` checks everything m2b needs on this machine
- `/m2b:m2b addons` lists the add-ons and what each does

If a command below answers that m2b is not set up, say so and offer `/m2b:m2b setup`.

## `setup`

Run the skill `m2b:setup` with the Skill tool. It sets up the core, says before each step what it
does, and then offers each add-on, one at a time.

## `addons`

```bash
m2b addons list --json
```

For each add-on, say in one line what it does (its `summary`) and whether it is on. For each
add-on that is off, ask whether to turn it on, one at a time; on a yes, run that add-on's setup
skill, `m2b:<add-on>-setup`, with the Skill tool. The worklog
needs herdr; say so before asking. Turning an add-on off is
`m2b addons off <add-on>`; its settings stay.

## `status`

```bash
m2b status
```

Say what it printed in a few lines: how many captures wait in the inbox, when the last curation
ran and how it ended, which add-ons are on, and any backend that could not be reached, with what to
do. Name the store format when it is not `current`: `newer` means this machine needs an m2b
update, `migrates` that the curating machine's next run brings the store up to date. "Could not look" is not "nothing there"; say which one it is.

## `doctor`

```bash
m2b doctor
```

Report each line whose state is `not reachable`, `missing`, `not installed`, `newer` (the store format: update
m2b on this machine) or `not usable for curation` (the store path: move the store to a folder the line
allows and set `store.path` to it), with what to do. Report `not recorded`
too, and say that it matters only on the machine that curates, where the model steps need that program. When all are fine, say so in one line.

## Any other argument

Show the help above, and say which of the four the owner may have meant.
