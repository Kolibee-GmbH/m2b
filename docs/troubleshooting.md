# Troubleshooting

What to run when something looks wrong, what a healthy machine answers, and the causes met so far.

```bash
m2b doctor
m2b status
```

`doctor` checks every backend and says what to fix; `status` shows the inbox, the last run and
whether a run is due. On a healthy machine with the quick start's store, a folder with Markdown
tasks, they answer like this (the paths, the machine's name and the times are yours):

```text
$ m2b doctor
store: reachable
store-format: current (format 3)
store-git: no repository
tasks: reachable
calendar: not configured
executable claude: found (/Users/alex/.local/bin/claude)
executable python3: found (/usr/bin/python3)
claude-code: found (the launcher runs m2b from /Users/alex/.claude/plugins/cache/m2b/m2b/0.4.1)
prompt-hook: answers (topics in the distillate: 0)
band: seen (it ran in the latest session, started 2026-11-12 17:25)

$ m2b status
inbox: 0
run: succeeded on a1b2-alexsmacbook at 2026-11-12T17:26:04+01:00
due: no (the last successful run was at 2026-11-12 17:26; the next is due after 2026-11-13 13:26)
store: reachable
tasks: reachable
calendar: not configured
store format: current (format 3)
add-ons on: none
```

Three of these lines look like a problem and are none. `band: not seen (...)`, with a long reason
in brackets, is what `doctor` says from setup until the next session has started. `store-git: no
repository` only says that the store folder is not a git repository, which is optional
([A commit per run](curation.md#a-commit-per-run)). `calendar: not configured` is the answer
for a setup without a calendar.

- **`m2b: command not found`.** Add `~/.local/bin` to your `PATH`
  ([Getting started](getting-started.md#in-claude-code) has the line). Inside a
  session, `!m2b status` works without it.
- **No `python3`, or a message that m2b needs Python 3.9.** On a Mac run
  `xcode-select --install`; on Linux install `python3` from your distribution.
- **`m2b: the core plugin m2b@m2b is not installed for this user`, or `doctor` reports
  `claude-code: missing`.** m2b is not installed for your user: for one project only, or not at
  all. Remove a project install in `/plugin`, then install it for your user ([Install](../README.md#install)).
- **A step fails with a login message, or `claude` is not found.** Run `claude` in a terminal and
  log in. A schedule runs with a short `PATH`; record where `claude` is:
  `m2b config set executables.claude "$(command -v claude)"`.
- **The session start says the last run failed.** The review task in your list names the step
  and the cause. Fix it and run `m2b curate --force`.
- **A topic's facts do not come in when you name it.** The hook that brings them says nothing when
  it fails. `m2b doctor` starts it and says in its line `prompt-hook` why it does not answer.
- **`curating` for a long time.** A run is going on; each model step is stopped after
  `curation.model_timeout_minutes` (15). When it ends, its outcome is added to
  `~/.local/state/m2b/run.log`.
- **Tasks "not reachable" with Apple Reminders.** The terminal Claude Code runs in needs access:
  System Settings, Privacy & Security, Reminders.
- **"not set up".** Run `/m2b:m2b setup` on this machine. Without Claude Code, from a checkout,
  it is `m2b setup apply` ([Getting started](getting-started.md#from-the-command-line-without-claude-code)).
- **Files "not downloaded".** iCloud Drive keeps them in the cloud ("Optimize Mac Storage").
  `m2b store fetch <path>` downloads them; m2b never reads them by accident.
- **A run filed something wrong,** or the review task names a finding you do not know what to do
  with. [Correcting what a run filed](curation.md#correcting-what-a-run-filed).
- **Something else.** Open an issue with the output of `m2b doctor` and `m2b --version`, and leave
  out what your notes say and the names in them
  ([new issue](https://github.com/Kolibee-GmbH/m2b/issues/new/choose)).
