---
name: herdr-setup
description: Turns on the experimental m2b herdr part, which lists the other agent sessions open in herdr at session start, after checking that herdr answers and whether this session runs inside it; installs nothing into herdr; "remove" turns it off. Use when the user says "set up the herdr part", "set up neighbour sessions", "the neighbours line says herdr could not be read", "Nachbar-Sessions einrichten", "turn the neighbours off", or when the owner turns on the herdr part.
allowed-tools: Bash(m2b-herdr check), Bash(m2b parts on herdr), Bash(m2b parts off herdr)
---

# herdr part setup

The part only reads herdr's session snapshot at the start of a session. There is nothing to
install, configure or register in herdr; you check, explain and turn the part on.

If the owner asked to turn it off, run `m2b parts off herdr` and say that new sessions no longer
list their neighbours; nothing else changes.

Run each `m2b` command in a Bash call of its own, as shown: nothing chained before or after it,
no `echo $?`. This skill may run the command alone without asking, and Claude Code reports a
failing exit code by itself.

## 1. Does herdr answer

```bash
m2b-herdr check
```

- **"herdr answers: N agent sessions open"**: the part can work; go on with section 2. When the next line says the session
  runs outside herdr, tell the owner the hook prints nothing in sessions started outside herdr; it
  lists neighbours in sessions started in a herdr pane.
- **"herdr could not be read: ... was not found"**: herdr is not on the PATH Claude Code sees. If
  herdr is installed somewhere else, the owner can name it in the environment variable `M2B_HERDR`
  (for example in the `env` block of their Claude Code settings).
- **"... did not answer within 2 seconds"** or **"... ended with exit ..."**: herdr is installed but
  its server does not answer; starting herdr starts it. Say the reason the check printed.

## 2. Turn it on

```bash
m2b parts on herdr
```

## 3. What the owner sees

In a session started in a herdr pane, the session-start context gets one line per other agent
session: workspace, task (the terminal title), state in plain words and the last two parts of its
folder. Idle and finished sessions stay listed. Nothing is recorded anywhere. Recording activity
is the separate worklog part and is never part of this one.
