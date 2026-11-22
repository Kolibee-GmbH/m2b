# m2b

A second brain for Claude Code: one store for what you know about people, agreements and your own
life, shared by all your projects and machines. Say "remember that Dana's birthday is on 3 March"
in any session; a curation run in the background files the note, and every later session starts
knowing it. "Remind me to call the plumber on Friday" also becomes a task. Your notes stay plain
Markdown files in a folder you choose.

This folder is the plugin. The project, its documentation and the setup guide are in the
[repository](https://github.com/Kolibee-GmbH/m2b).

## Install

On macOS 14 or newer or Linux, in a Claude Code session:

```
/plugin marketplace add Kolibee-GmbH/m2b
```

```
/plugin install m2b@m2b
```

```
/m2b:m2b setup
```

Setup asks a few questions; until it has run, the hooks print nothing and no run starts.

## Hooks

Every hook always exits 0.

- `SessionStart`, `m2b hook distillate`: notes the git remotes of the session's folder in a file on
  the machine and prints the distillate, a summary of your notes of at most 8 KB.
- `SessionStart`, `m2b hook start-notes`: prints m2b's notices, the routing rule and the lessons you
  kept.
- `SessionStart`, `m2b hook nudge`: starts a curation run in the background when one is due (a
  capture waits, or the last run is more than 20 hours old). The run is a `claude -p` of its own,
  with `haiku` by default, under your Claude Code login.
- `SessionStart`, `m2b hook launcher`: keeps the `m2b` command up to date.
- `SessionStart`, `m2b-worklog hook session-start`: the worklog add-on's recording switch; prints
  nothing while the add-on is off, which it is until its own setup.
- `UserPromptSubmit`, `m2b-prompt-hook`: when the prompt names a topic of the distillate, adds that
  topic's facts, at most 4 KB, once per session.
- `PreToolUse` on Bash, `m2b-tool-hook`: when the command holds the words of a lesson you kept about
  a command, stops the first such call of a session with the lesson as the reason, lets the next
  one through with it, or has Claude Code ask you first.
- The mod `register.tsx`, loaded while mods are on: draws the band and the status line, opens the
  m2b pane, and registers the note and search tools. A call of either tool runs without Claude
  Code's permission prompt; your own `permissions.ask` and `permissions.deny` rules for
  `mcp__m2b__note` and `mcp__m2b__search` come first.

## What runs and what leaves the machine

m2b opens no network connection of its own and sends no telemetry. Your notes reach a model only
through your Claude Code: the distillate and topic facts in a session, and in a curation run the
captures and memory files it reads. A curation run reads your session prompts only after you said
yes in setup, and a session hands in proposals by itself only after you turned that on. The full
table, with
how to turn each part off, is in
[What runs on your machine](https://github.com/Kolibee-GmbH/m2b#what-runs-on-your-machine); the
tools' limits are in [Security](https://github.com/Kolibee-GmbH/m2b/blob/main/SECURITY.md).

## License

MIT, see the [license](https://github.com/Kolibee-GmbH/m2b/blob/main/LICENSE).
