# Configuration

m2b keeps its settings in three files. Each has one owner and is changed through commands, not
by hand: a command checks the whole file before it writes, so a typo cannot leave a file the next
run refuses.

| File | Where | Shared | Written by |
|---|---|---|---|
| `config.json` | `~/.config/m2b/` | no, one per machine | setup, `m2b config set`, `m2b addons on / off`, `m2b distillate off / on` |
| `store.json` | the store's folder | yes, every machine | setup, `m2b curate take-over` |
| `profile.json` | the store's folder | yes, every machine | setup, `m2b profile set / merge`, the worklog setup |

```bash
m2b config get --json            # the whole machine config
m2b config get store.path        # one key
m2b config set <key> <value>     # JSON, or plain text for a string
m2b profile get --json
m2b profile set <key> <value>
m2b profile merge '<JSON object>'
```

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
  "format": 2,
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
| `customers` | for the worklog: the only names its booking proposals may use |

`profile merge` merges spheres by `id` (a sphere you name replaces the one with its id) and adds
customers once; every other key replaces.

## Environment variables

For tests, development and unusual setups; none is needed in normal use.

| Variable | Effect |
|---|---|
| `M2B_HOME` | moves every machine path (`~/.config/m2b`, `~/.local/state/m2b`, `~/.local/share/m2b`, the launcher) under this folder |
| `M2B_CORE_ROOT` | the launcher runs the core from this folder (a checkout) instead of Claude Code's plugin folder |
| `M2B_INSTALLED_PLUGINS` | another `installed_plugins.json`, read by the launcher and the worklog's recorder |
| `M2B_MODEL_RUNNER` | an executable used in place of `claude` for model steps, such as `scripts/no-model` |
| `M2B_PYTHON` | the Python the plugin commands run with |
| `M2B_HERDR` | the `herdr` executable the worklog add-on calls |
| `M2B_MANAGED_SETTINGS` | another managed settings file, read by the worklog's recorder for `enabledPlugins` in place of the system one (tests) |

The core sets `M2B_CURATION_RUN` and `M2B_RUN_TOKEN` for the steps of a curation run, and
`M2B_REFRESH_ALL` for the refresh step of `m2b curate --refresh-all`; do not set them yourself.

Claude Code's own `CLAUDE_CONFIG_DIR` is honoured too: when it is set, m2b looks there instead of
`~/.claude` for the installed plugins and, with the worklog, for the session transcripts and the
`enabledPlugins` setting its recorder checks.
