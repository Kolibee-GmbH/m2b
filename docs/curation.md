# The curation run

A curation run files the inbox. It runs on one machine per store, the curating machine that
`store.json` names, and nowhere else.

## When it runs

At session start on the curating machine, in the background, when a run is due: the inbox holds
a capture, or the last successful run is more than 20 hours old. So after a capture the next
session start files it. After a failed run the next attempt waits 1 hour, then 4, then 20; a run
in which only an add-on's step failed counts as succeeded and starts no wait. A
schedule can start it too, for days without a session ([On a schedule](#on-a-schedule)), and
`m2b curate --force` starts it now; add `--detach` to get your terminal back while it runs.

## The steps

```mermaid
flowchart LR
  pre[Preflight] --> migrate[Migrate] --> harvest[Harvest] --> before[before_ingest] --> ingest[Ingest] --> afteri[after_ingest] --> refresh[Refresh] --> sort[Sort] --> lint[Lint] --> journal[Journal] --> after[after_journal] --> review[Review task]
```

| Step | Done by | What it does |
|---|---|---|
| Preflight | code | removes leftover temp files, downloads the files the run reads, loads the profile |
| Migrate | code, only when the store's format is older than this m2b | brings `memory/` up to the rules of this m2b, one format at a time, each checked in code; a failing one puts `memory/` back, keeps the format and ends the run with the review |
| Harvest | code | settles the memory candidates and "Still current? ..." questions you ticked or dropped |
| Ingest | model, only with captures in the inbox | files facts into memory, tasks into your list, each capture into `corpus/YYYY/MM/` |
| Refresh | model, only when a fact is past its day | rewrites the facts whose `until` has passed |
| Sort | model, only with `m2b curate --sort-facts` | moves facts lines of an older distillate into topics; code puts the file back if a statement changed |
| Lint | code; the model only to repair a broken memory link with exactly one candidate | checks names, links, conflict copies and the distillate's size |
| Journal | code | adds the tasks you completed to the month's `corpus/YYYY/MM/YYYYMM-done.md` |
| Review task | code | one task in your list when something needs you |

`before_ingest`, `after_ingest` and `after_journal` are where an add-on can hook in; the worklog
runs before ingest. A step that fails is reported in the review task and the run goes on. When
only an add-on's step failed, the run still counts as succeeded: the inbox is filed and the next run
is due at the usual time, so an add-on that keeps failing never holds back the core.

Each model step runs fenced: `claude -p` from an empty folder, with `--setting-sources project`,
m2b alone as plugin, `--permission-mode dontAsk`, and allowed only the commands and paths of its
step. It uses `curation.model` (`haiku` by default) and stops after `curation.max_turns` tool
calls or `curation.model_timeout_minutes`.

After each model step that may edit `memory/`, code compares it with a copy taken just before the
step:

- **Refresh** may change only the facts that are due: their fact files and their lines in
  `MEMORY.md`. Any other change puts `memory/` back and fails the step.
- **Ingest and lint** keep their edits. Each facts line they removed or rewrote, and each fact file
  they emptied or removed, is listed in the review task, and again in every later review until you
  complete the task, in your task list or with `ok` in [the band](band.md), where `/m2b-review`
  shows each change with the added and removed words marked. `memory/` as it was before the run is
  kept in
  `~/.local/state/m2b/memory-before-run/<time of the run>/` as long as such a finding names it, so a
  line can be copied back from there.
- **Any model step**, sorting included, that writes a line holding characters that hide or reorder
  text (bidirectional controls, zero-width spaces, tag characters) is undone and fails; a capture
  still in the inbox is marked so the next run files its facts again. The session-start and prompt
  hooks remove the same characters before the distillate reaches a session.

## What runs when

| | After install, before setup | After its setup |
|---|---|---|
| core | nothing: the session-start hooks print nothing and no run starts until `/m2b:m2b setup` | the distillate at session start, a curation run at the next session start after a capture on the curating machine |
| band | draws nothing and starts nothing while there is no launcher | the band and the status line, while mods are on in Claude Code |
| `worklog` | prints nothing, records nothing | herdr events recorded on the curating machine, a daily worklog note |

## After an update

When a new m2b changes a rule for content already in the store, it raises the store's format
(`format` in `store.json`, see [Store format](store-format.md#formats)), and the curating
machine's next run migrates the store before anything else: you run nothing. `m2b status` and
`m2b doctor` show `store format: migrates` until then. Update the curating machine first: an m2b
that knows an older format reads a newer store and captures into it, but does not curate it
([Several machines](several-machines.md#machines-on-different-versions)).

## Moving over an older distillate

Two one-off runs bring a `memory/` written by another tool, or by m2b before 0.1.0, up to date:

```bash
m2b curate --refresh-all   # dates the memory lines written without dates
m2b curate --sort-facts    # sorts the facts of an older distillate into topics
```

`--refresh-all` reads the evidence of every undated line and sets `until` or `since` only where a
capture names the day. `--sort-facts` moves the lines that matter for one subject under its topic;
code then compares the file and puts the old one back if any statement changed.

## On a schedule

Most setups need no schedule: the next session start on the curating machine files what waits. A
schedule helps when captures reach the inbox while that machine starts no Claude Code session for
days, for example captures from a second machine, or an integration such as a Shortcut that
writes into the inbox. A scheduled `m2b curate` that is not due does nothing and exits 0, so it
is safe to run daily.

A schedule calls the launcher `~/.local/bin/m2b`, which setup wrote with the absolute path of
`python3`; the model steps use the absolute paths of `claude` and `reminders` that setup recorded,
because a scheduled job runs with a short `PATH`. Check them with:

```bash
m2b config get executables --json
```

### macOS: a Shortcuts automation

A launchd job is not given access to iCloud Drive and Reminders the way an app is; a personal
automation in Shortcuts runs as Shortcuts, and macOS asks once for access to the folder and to
Reminders.

1. Open **Shortcuts**, then **Automation**, then **New Automation**.
2. Choose **Time of Day**, set a time such as 06:30, **Daily**, and **Run Immediately**.
3. Add the action **Run Shell Script**. Shell: `zsh`. Script:

   ```bash
   "$HOME/.local/bin/m2b" curate
   ```

4. Save, then run the automation once by hand and allow the access macOS asks for.

### Linux: cron

```cron
30 6 * * * /home/alex/.local/bin/m2b curate >> /home/alex/.local/state/m2b/cron.log 2>&1
```

Use your own home folder; cron does not expand `~`. If the store is a synced folder, schedule the
run after the sync client has started. The launcher finds the core through Claude Code's plugin
list; on a machine that runs m2b from a checkout instead of the installed plugin (the `claude`
command is still needed for the model steps), name the checkout in the line:

```cron
30 6 * * * M2B_CORE_ROOT=/home/alex/src/m2b/plugins/m2b /home/alex/.local/bin/m2b curate >> /home/alex/.local/state/m2b/cron.log 2>&1
```

### Checking a scheduled run

`m2b status` shows when the last run started and how it ended; a run that found nothing due shows
as `last attempt: not due at ...`, so you can see the schedule reached m2b. The machine's run log
is `~/.local/state/m2b/run.log`; a run that could not even write its record leaves its cause there.

## The status line

While [the band](band.md) runs, one line below the prompt sums up the brain. It is refreshed about
once a minute and after each of your turns. Normally it reads `0 in inbox · curated 17:07`: the
captures waiting for the next run, and when the last successful run ended (the time today, the date
on an earlier day), or `not curated yet` while no curation run has succeeded. Claude Code draws a
⚠ in front of every plugin's status line; it is not a warning. In place of the pair it can say:

| Status line says | Meaning |
|---|---|
| `curating` | a curation run is going on now |
| `last run failed, see review` | the last run failed; the review task in your list names the step and the cause |
| `last run interrupted` | the last run ended without finishing, for example because the computer shut down or its process was killed |
| `could not read the last run` or `could not read the inbox` | that part of the store could not be read |

A problem is added after it, such as `could not read store.json` or `tasks not reachable` (likewise
for the store and the calendar); the task list, store and calendar are checked every 5 minutes, so
such a problem can show up or clear that much later. `could not look` means `m2b status` gave no answer at all;
run it in a terminal to see why.
