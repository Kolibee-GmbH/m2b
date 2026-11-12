---
name: setup
description: Sets this machine up for the owner's second brain - a new store from nothing, or joining a store another machine already uses - and leaves it ready for a first capture. Use when the user says "set up m2b", "set up my second brain", "m2b einrichten", "richte mein Second Brain ein", "connect this Mac to my second brain", or when a command answered that m2b is not set up. Running it again with the same answers changes nothing.
allowed-tools: Bash(m2b setup *), Bash(m2b doctor), Bash(m2b doctor *)
---

# Setup

You ask the owner a few questions and hand the answers to `m2b setup apply`, which writes
everything. You never write a file yourself and never edit a config by hand. Before each step, say
in one sentence what it does and what it changes on the machine, then do it.

Run each `m2b` command in a Bash call of its own, as shown: nothing chained before or after it,
no `echo $?`. This skill may run the command alone without asking, and Claude Code reports a
failing exit code by itself.

## 1. What is there already

```bash
m2b setup inspect --json
```

If `machine_config` is `null` (and `store` with it), this machine is not set up yet: offer two
ways and recommend the first:

1. **Quick start:** a new folder `~/m2b` (backend `folder`, created for the owner) with the tasks
   as Markdown files in it. Nothing to install, works on macOS and Linux; it can move to iCloud
   Drive or Reminders later. If the owner takes it, look first whether that folder holds a store:

   ```bash
   m2b setup inspect --store-backend folder --store-path "~/m2b" --json
   ```

   If `store_exists` is `true` and the answer holds a store, this machine joins it: go on as with a
   folder the owner chose (below). Otherwise (`store_exists` is `false`, or the folder is there but
   holds none of them) there is no store there yet: go to section 2 without the Tasks question, and
   in section 3 send `"store": {"backend": "folder", "path": "~/m2b", "create": true}` and `"tasks":
   {"backend": "markdown"}`. If `apply` answers that the folder holds other files, tell the owner
   and offer the second way.
2. **A folder the owner chooses**, for example in iCloud Drive
   (`~/Library/Mobile Documents/com~apple~CloudDocs/<name>`, backend `icloud`, macOS only) or any
   other folder (backend `folder`). The folder must exist. Inspect it:

```bash
m2b setup inspect --store-backend <icloud or folder> --store-path "<folder>" --json
```

If `store_path_problem` is set and this machine is to curate (a store not set up yet, or
`store_settings.curating_machine` equal to `machine_config.machine_id`), read it to the owner and
ask for another folder before anything else; a machine that only captures may keep the folder. If
`store_exists` is `false`, the folder is not there yet: ask the owner to create it, then inspect
again. The answer shows what the store holds: `store_settings` (`store.json`), `profile`, `distillate`
(whether `memory/MEMORY.md` exists) and this machine's `machine_config`. A store that holds any of
them is in use: this machine joins it, and you ask only what is missing below. Setup downloads
evicted files first; if it says a file could not be downloaded, or that the store cannot be
reached (the folder above it is missing too, a drive that is not mounted), tell the owner and stop.

## 2. Ask only what is missing

Ask in the owner's language, one short question at a time, with the choices:

- **Tasks** (only without `store_settings`): Apple Reminders with the name of a list (`apple-reminders`,
  macOS, needs `reminders-cli`), or Markdown files in the store (`markdown`).
- **Owner's name and language** (only without `profile`): `en` or `de`.
- **Calendar** for today's events and calendar entries: Apple Calendar (`apple-calendar`) or none.
  Say that calendar entries ("put it in my calendar") are experimental.
- **Does this machine curate?** One machine files the inbox. A new store: yes. A store in use:
  `store_settings.curating_machine` names that machine; the answer is usually no.
- **Model for curation** (only when this machine curates, and only when `machine_config` has no
  `curation.model`): `haiku`, the default, small and cheap; or `sonnet`, which files and condenses
  more carefully and costs more per run. Send it as `"curation_model"`.
- **May the curation runs read your sessions?** (only when this machine curates, and only when
  `machine_config` has no `curation.read_sessions`): a run then reads what the owner typed in
  Claude Code since the last reading and proposes what belongs in the memory although nobody said
  "remember this". Before asking, say what a yes means: only what the owner typed is read, never
  Claude's answers and never a pasted block; nothing is filed before the owner says keep to a
  proposal (`m2b proposals` lists them); and of a session in a folder the profile leaves out of
  the worklog (`worklog_leave_out`) or that `m2b distillate off` was run in, nothing reaches the
  model. The default is no. Send the answer as `"read_sessions"`, `true` or `false`.

Never ask for something the store already holds, unless the owner wants to change it.

## 3. Apply

Hand over the answers as one JSON object; leave out what you did not ask:

```bash
m2b setup apply --json --answers '{"store": {"backend": "icloud", "path": "<folder>"}, "tasks": {"backend": "apple-reminders", "list": "Inbox"}, "owner": "Alex", "language": "en", "calendar": "apple-calendar", "curates": true, "curation_model": "haiku", "read_sessions": false}'
```

The answer lists the files it `written` (empty when nothing changed), `take_over`, the
`missing_executables`, `problems` and `addons`. When `take_over` is set, tell the
owner exactly that: another machine curates, and `m2b curate take-over` on this machine moves
curation here. Setup did not change it. Exit 1 means everything else was written and each entry of
`problems` needs the owner (a file at `~/.local/bin/m2b` that is not this product's launcher, for
example): report each one with what to do.

## 4. Check

```bash
m2b doctor
```

Report each line whose state is `not reachable`, `missing`, `not installed`, `newer` (the store format: update m2b
on this machine), `not usable for curation` (the store path: move the store to a folder the line
allows and set `store.path` to it) or `does not answer` (the prompt hook: no topic's facts come in before a
prompt, for the reason the line gives), with what to do; `not recorded` only on
the curating machine, where the model steps need that program. The line `band` says whether the
latest session that ran m2b's hooks also started the band above the prompt. Right after setup it
can say `not seen`, because m2b's hooks only begin with the next session. Say that the band appears
in the next session, and that if `m2b doctor` still says `not seen` after one, pass on the reason
its line gives.

## 5. What the owner does by hand

List only the steps that apply, as a numbered list, each with where to click or what to type:

1. Apple Reminders: install `reminders-cli` (`brew install keith/formulae/reminders-cli`) and allow
   access when macOS asks, or in System Settings, Privacy & Security, Reminders.
2. Apple Calendar: System Settings, Privacy & Security, Calendars: full access for the terminal or
   Claude.
3. A missing executable from `missing_executables`: the line `m2b config set executables.<name> <path>`.

## 6. Add-ons

Each entry in `addons` is an add-on of m2b with a `summary` of what it does; all are off
until their own setup turns them on. For each one that is `on: false`, one at a time: say in one
line what it does, and ask whether to turn it on. The worklog needs herdr and runs only on the
curating machine; say so before asking. On a yes, run that add-on's setup skill with the Skill
tool: `m2b:worklog-setup`. Never run one unasked.

## Answer

What this machine is now (new store, or joined; curating or not), the numbered steps, and one
line for a first capture: "remember that ..." files it into the inbox.
