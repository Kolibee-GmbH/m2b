---
name: band-setup
description: Turns on the m2b band above the prompt (open memory candidates to keep or drop, the open review, the state of curation in the status line) after checking that it can work on this machine - the launcher it calls and the task list it reads - and says what to fix when it cannot; "remove" turns it off. Use when the user says "set up the band", "the band is empty", "the band says could not look", "band einrichten", "das Band zeigt nichts", "turn the band off", or when the owner turns on the band add-on.
allowed-tools: Bash(~/.local/bin/m2b doctor *), Bash(~/.local/bin/m2b status *), Bash(~/.local/bin/m2b addons *)
---

# Band setup

The band calls `~/.local/bin/m2b` and nothing else, so it works once that launcher answers and the
task list can be reached. You check, explain and turn the add-on on; you install nothing.

Run each `m2b` command in a Bash call of its own, as shown: nothing chained before or after it,
no `echo $?`. This skill may run the command alone without asking, and Claude Code reports a
failing exit code by itself.

If the owner asked to turn the band off, run `~/.local/bin/m2b addons off band` and say that the
band and its status line are gone within a minute; nothing else changes.

## 1. The launcher

```bash
~/.local/bin/m2b doctor --json
```

- **No such file:** the core plugin `m2b` has not written its launcher yet. It does so at the
  start of a session; tell the owner to start a new session, or to run `/m2b:m2b setup` if m2b has
  never been set up on this machine.
- **Exit 2 with "not set up":** m2b is installed but not set up here. Point to `/m2b:m2b setup`.
- **An answer:** go on.

## 2. What the band will show

In the `doctor` answer, look at the check named `tasks`:

- `reachable`: the band can read the candidates and the review task.
- `not reachable`: say the reason it gives. With Apple Reminders this is usually the privacy
  grant: System Settings, Privacy & Security, Reminders, and allow the terminal Claude Code runs
  in. The band shows one error line until this is fixed.

Then:

```bash
~/.local/bin/m2b status --json
```

Tell the owner in one or two sentences what the status line under the prompt will say: the inbox
count, the last curation run, and any backend that cannot be reached. An empty band is normal
when there are no open memory candidates and no open review task.

## 3. Turn it on

```bash
~/.local/bin/m2b addons on band
```

The band shows within a minute, and after the next turn at the latest.

## 4. When the band stays empty although there is something to show

The band is a mod: it needs a Claude Code version that runs plugins with function hooks, and mods
turned on. Ask the owner to check in `/plugin` that m2b is enabled, and that
`~/.local/bin/m2b addons list` shows `band` as `on`. The band reloads every 60 seconds and after
each turn.
