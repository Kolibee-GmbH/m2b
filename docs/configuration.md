# Configuration

m2b keeps its settings in three files. Each has one owner and is changed through commands, not
by hand: a command checks the whole file before it writes, so a typo cannot leave a file the next
run refuses.

| File | Where | Shared | Written by |
|---|---|---|---|
| `config.json` | `~/.config/m2b/` | no, one per machine | setup, `m2b config set`, `m2b settings set`, `m2b addons on / off`, `m2b distillate off / on` |
| `store.json` | the store's folder | yes, every machine | setup, `m2b curate take-over` |
| `profile.json` | the store's folder | yes, every machine | setup, `m2b profile set / merge`, `m2b settings set language`, the worklog setup |

```bash
m2b settings                     # every setting of the three files, with what changes it
m2b settings set <switch> <value>
m2b config get --json            # the whole machine config
m2b config get store.path        # one key
m2b config set <key> <value>     # JSON, or plain text for a string
m2b profile get --json
m2b profile set <key> <value>
m2b profile merge '<JSON object>'
```

## Every setting in one list

`m2b settings` lists every setting of the three files under its file: its value, what it does and
what changes it, and its default where the value differs. `--json` gives the same for a program,
and also names four `groups` by what a person wants from m2b and, for each setting, its `group`
and its `place` there: the order [the pane's settings](band.md#every-setting-in-the-pane) are
drawn in.

```text
This machine (config.json)
  calendar.timeout_seconds: 45 (default 20)
      How many seconds a call to the calendar may take.
      change: m2b config set calendar.timeout_seconds <seconds>
  curation.paused: off
      This machine starts no curation run by itself, none at a session start and none from a schedule. m2b curate --force still runs one, and captures keep reaching the inbox.
      switch: m2b settings set curation.paused true|false
```

Each setting is one of three kinds:

| Kind | What it is | How it changes |
|---|---|---|
| switch | on or off, or one of a few named values: `curation.read_sessions`, `curation.paused`, `curation.git_commit`, `band.topics`, `sessions.propose`, `band.due_tasks` (`off`, `count`, `list`), `curation.model` (`haiku`, `sonnet`) and the profile's `language` | `m2b settings set <key> <value>` |
| shown | a value the list shows as it is: a path, a time limit, a name | the command or the setup skill the list names; `machine_id`, `format`, both `version`s and `journal_since` are never changed by hand, and `tasks.timeout_seconds`, which no command writes, only by hand in `store.json` |
| named | a list, the paths of programs or an add-on: `executables`, `distillate.skip_under`, `addons.<add-on>`, `spheres`, `customers`, `worklog_leave_out` | the command or the setup skill the list names |

A named setting comes as a count (`2 customers`, `1 folder`) or as on and off, never with what it
holds: the answer of a command can end up in what a session reads, and these hold customers' names
and the folders of their work. `m2b config get` and `m2b profile get` print them whole. A shown
setting does come with its value: this machine's name, the store folder, your name, the name of
the Reminders list.

The store's files can be written from your other devices. A text from them is listed on one line:
a line break, an escape sequence or a character that draws nothing is written out as `<U+XXXX>`.

`m2b settings set` changes a switch and nothing else. It takes the values the list names for it and
refuses any other key with one line that says what changes that setting, so a caller that offers
switches to press cannot write a path or a program through it. `m2b config set` stays the command
for every other key of the machine config, and for a `curation.model` other than the two the
switch offers. Both refuse the same changes in the same words; `sessions.propose` is turned on by
neither where `CLAUDECODE` is set, as it is in the shell of a Claude Code session. A press on that
setting's `on` in the m2b pane runs the command with the variable empty
([The band](band.md#every-setting-in-the-pane)).

A file that cannot be read, a store out of reach or one without a profile yet, leaves its settings
in the list as `not read`, with the reason under the file's heading. Of a file that does not follow
its format the list says only that: `m2b status` names what is wrong in `store.json`, and
`m2b profile get` in `profile.json`.

## config.json, this machine

An example with invented values:

```json
{
  "version": 1,
  "machine_id": "b41c-tower",
  "store": {"backend": "icloud", "path": "~/Library/Mobile Documents/com~apple~CloudDocs/Notes"},
  "calendar": {"backend": "apple-calendar", "timeout_seconds": 20},
  "executables": {"python3": "/usr/bin/python3", "claude": "/opt/homebrew/bin/claude", "reminders": "/opt/homebrew/bin/reminders"},
  "curation": {"model_timeout_minutes": 15},
  "addons": {
    "worklog": {"on": true}
  }
}
```

| Key | Meaning | Default |
|---|---|---|
| `machine_id` | this machine's name in `store.json`; setup makes one up from the host name and a random part | |
| `store.backend` | `icloud` (macOS, iCloud Drive) or `folder` (any folder) | |
| `store.path` | the store's folder, absolute or starting with `~/` | |
| `calendar.backend` | `none` or `apple-calendar` (macOS) | `none` |
| `calendar.timeout_seconds` | how long a calendar call may take | 20 |
| `executables` | absolute paths of `python3`, `claude`, `reminders` and `osascript`, for runs outside a terminal, whose `PATH` is short | what setup found |
| `curation.model_timeout_minutes` | how long one model step may run before it is stopped | 15 |
| `curation.model` | the model of each fenced model step, any name `claude --model` takes | `haiku` |
| `curation.max_budget_usd` | a spending cap per model step, from Claude Code's own estimate of API cost; it can differ from the bill and says little on a subscription | none |
| `curation.max_turns` | the turns one model step may take before it stops and is reported | 100 |
| `curation.read_sessions` | whether a curation run on this machine reads what you typed in Claude Code since the last reading and keeps what a model proposes from it for your memory; of a session the profile's `worklog_leave_out` names, by its folder or by a git remote of its repository, or in a folder of `distillate.skip_under`, nothing reaches the model | `false` |
| `curation.git_commit` | whether a curation run on this machine ends with a git commit of what it changed, and first commits the captures git does not know yet, when the store folder is the top of a git work tree ([A commit per run](curation.md#a-commit-per-run)); without a repository there the setting does nothing | `true` |
| `curation.git_directory` | the git directory a curation run on this machine commits into when the store folder holds a `.git` file that points at one kept outside the folder (`git init --separate-git-dir`): a path, absolute or starting with `~/`. A run commits there only when the file points at this directory; pointed elsewhere, or with nothing named here, it commits nothing and says why ([A commit per run](curation.md#a-commit-per-run)). The directory lies outside the store folder; one inside it or reached through a link in it, other than the store's own `.git` folder, is refused. A `.git` folder in the store folder needs no entry | none |
| `curation.paused` | whether this machine starts no curation run by itself: none at a session start, none from a schedule. `m2b curate --force` still runs one, captures keep reaching the inbox, and `m2b status` says `paused` ([Pausing](curation.md#pausing)) | `false` |
| `band.due_tasks` | how the band shows your tasks due today or overdue: `off` shows none there, `count` says how many, `list` names the first three. The pane lists them whatever this says. A config that holds `true` reads as `list`, `false` as `off` | `count` |
| `band.topics` | whether the band says how many topics m2b gave the session; the pane names them whatever this says | `false` |
| `sessions.propose` | whether a session on this machine may hand in a proposal for your memory by itself, with words from what its agent read for the task: a mail, a document, a tool's result. A session that worked in a folder or repository the profile's `worklog_leave_out` names, or with the distillate off, hands nothing in. You turn it on yourself: with `m2b settings set sessions.propose true` or `m2b config set sessions.propose true` typed in a terminal of your own, or with a press on its `on` in the m2b pane's settings, where the pane is drawn in a terminal, the desktop app or VS Code. Setup never does, and in the shell of a Claude Code session either command refuses | `false` |
| `distillate.skip_under` | folders, absolute or starting with `~/`, in and below which sessions get no distillate; `m2b distillate off` and `on` change it | none |
| `addons.<add-on>.on` | whether an add-on runs on this machine: `worklog` | off |
| `addons.<add-on>.*` | the add-on's own settings; kept when the add-on is turned off. An entry for `band`, `herdr` or `backup`, which are no longer add-ons, is ignored, and `m2b addons off <name>` removes it | |

An add-on's setup skill turns it on once it is set up; by hand:

```bash
m2b addons list
m2b addons on worklog
m2b addons off worklog
```

The worklog adds a step to each curation run while it is on, before the inbox is filed. It runs
from the plugin's own folder, so an update needs no step, and while it is off it has no step and
leaves nothing to clean up.

## store.json, the store

```json
{
  "format": 3,
  "tasks": {"backend": "apple-reminders", "list": "Inbox"},
  "curating_machine": "b41c-tower",
  "journal_since": "2026-11-01"
}
```

| Key | Meaning |
|---|---|
| `format` | the store format, which counts the rules for curated content; a machine with an older m2b reads a newer format and captures into it, but does not curate it ([Store format](store-format.md#formats)) |
| `tasks.backend` | `apple-reminders` (macOS) or `markdown` (one file per task in `tasks/`) |
| `tasks.list` | the Reminders list; required for `apple-reminders` |
| `tasks.timeout_seconds` | how long a tasks call may take, 20 by default |
| `curating_machine` | the one machine that curates; change it with `m2b curate take-over` |
| `journal_since` | the first day the journal of completed tasks covers |

The task backend lives in the store, not on the machine, so every machine uses the same list.

## profile.json, the owner

```json
{
  "version": 1,
  "owner": "Alex",
  "language": "en",
  "spheres": [
    {"id": "acme", "label": "Acme Ltd", "billable": true, "match": {"git_remote_contains": ["github.com/acme-ltd/"], "path_under": ["~/code/acme"]}},
    {"id": "private", "default": true}
  ],
  "customers": ["Globex", "Initech"]
}
```

| Key | Meaning |
|---|---|
| `owner` | your name, as the curator writes about you |
| `language` | `en` or `de`: task titles, notes and the worklog are written in it |
| `spheres` | for the worklog: areas of work, how each is recognized, which are billable, one default |
| `worklog_leave_out` | work that reaches no worklog and no reading of your sessions: folders under your home folder (`path_under`) and parts of the URLs of git remotes (`git_remote_contains`); see [Leaving work out](addons/worklog.md#leaving-work-out). A profile with it is written as version 2 |
| `customers` | for the worklog: the only names its booking proposals may use |

`profile merge` merges spheres by `id` (a sphere you name replaces the one with its id) and adds
customers once; every other key replaces.

## Environment variables

For tests, development and unusual setups; none is needed in normal use.

| Variable | Effect |
|---|---|
| `M2B_HOME` | moves every machine path (`~/.config/m2b`, `~/.local/state/m2b`, `~/.local/share/m2b`, the launcher) under this folder; a leading `~` stands for your home folder |
| `M2B_CORE_ROOT` | the launcher runs the core from this folder (a checkout) instead of Claude Code's plugin folder |
| `M2B_INSTALLED_PLUGINS` | another `installed_plugins.json`, read by the launcher and the worklog's recorder |
| `M2B_MODEL_RUNNER` | an executable used in place of `claude` for model steps, such as `scripts/no-model`; like `claude`, it has to print the line that names its session's tools and MCP servers before its result |
| `M2B_PYTHON` | the Python the plugin commands run with |
| `M2B_HERDR` | the `herdr` executable the worklog add-on calls |
| `M2B_MANAGED_SETTINGS` | another managed settings file, read by the worklog's recorder for `enabledPlugins` in place of the system one (tests) |

The core sets `M2B_CURATION_RUN` and `M2B_RUN_TOKEN` for the steps of a curation run, and
`M2B_REFRESH_ALL` for the refresh step of `m2b curate --refresh-all`; do not set them yourself.

Claude Code's own `CLAUDE_CONFIG_DIR` is honoured too: when it is set, m2b looks there instead of
`~/.claude` for the installed plugins and, with the worklog, for the session transcripts and the
`enabledPlugins` setting its recorder checks.
