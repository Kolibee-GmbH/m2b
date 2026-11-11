---
name: worklog-setup
description: Sets up the m2b worklog on the curating machine - the owner's spheres of work, how each is recognized and which are billable, the customer list, the activity recorder in herdr, and turns the worklog add-on on - or turns it off with "remove". Use when the user says "set up the worklog", "worklog einrichten", "record my work in herdr", "add a customer to the worklog", "remove the worklog", "Worklog entfernen", or when the owner turns on the worklog add-on. Running it again with the same answers changes nothing.
allowed-tools: Bash(m2b-worklog machine *), Bash(m2b-worklog recorder *), Bash(m2b-worklog hook *), Bash(m2b-worklog recordings *), Bash(m2b profile *), Bash(m2b addons on worklog), Bash(m2b addons off worklog)
---

# Worklog setup

The worklog is the only add-on of m2b that records what the owner does. Once a day it writes a
note about the sessions of the last period, with time spans per sphere of work and booking proposals
for billable spheres; the owner books by hand. You ask, and the commands below write everything.

Run each `m2b` command in a Bash call of its own, as shown: nothing chained before or after it,
no `echo $?`. This skill may run the command alone without asking, and Claude Code reports a
failing exit code by itself.

If the owner asked to remove the worklog, go to section 7.

## 1. herdr first

The worklog sees work through herdr, so ask before anything else:

```bash
m2b-worklog recorder check --json
```

- `ready: true`: go on.
- `ready: false`: tell the owner the worklog needs herdr 0.9 or later, running, and pass on
  `problem` in its own words (herdr missing, too old, or not running). Stop here, before any
  question: a profile with spheres is of no use without herdr. Running this setup again once herdr
  runs finishes it.

## 2. Only on the curating machine

```bash
m2b-worklog machine --json
```

- `set_up: false`: m2b is not set up here. Point to `/m2b:m2b setup` and stop.
- `this_machine_curates: false`: refuse, and explain: only the machine that curates the store
  records and collects the worklog, so one day is never counted on two machines. To have the
  worklog here, this machine first takes over curation (`m2b curate take-over`, which stops it on
  the other machine), then this setup runs again. Stop.
- `this_machine_curates: true`: go on.

## 3. What the profile holds

```bash
m2b profile get --json
```

Show the owner the `spheres` and `customers` it holds, if any. A sphere looks like this:

```json
{"id": "acme", "label": "Acme Ltd", "billable": true, "match": {"git_remote_contains": ["github.com/acme-ltd/"], "path_under": ["~/code/acme"]}}
```

## 4. Ask

Ask, one question at a time, and only what is missing or what the owner wants to change:

1. **Spheres**: the areas the owner's work falls into, such as an employer, a company of their
   own, private projects. For each: a short `id` in lowercase, a `label`, and whether time there
   is `billable` (only billable spheres get booking proposals).
2. **How each sphere is recognized**: parts of git remote URLs (`git_remote_contains`) and folders
   under the home folder (`path_under`, written with `~/`). A session matching none falls to the
   default sphere. A sphere other than the default with neither is never matched, so its time
   lands in the default sphere: when you see one, in the profile or in the answers, say so and
   ask how its work can be recognized.
3. **The default sphere**: one sphere gets `"default": true`.
4. **Customers**: the names booking proposals may use, as the owner writes them on a timesheet.
   The worklog only reads this list; it never adds to it.

## 5. Write

All answers in one object. A sphere replaces the one with its `id` and a sphere not named stays
as it is, so send a changed sphere whole; customers are added, and a name already there stays
once:

```bash
m2b profile merge '{"spheres": [...], "customers": [...]}'
```

Only to take a customer off the list, set the complete list instead:

```bash
m2b profile set customers '["<name>", "<name>"]'
```

Then the recorder, a plugin it hooks into herdr: it copies itself to
`~/.local/share/m2b/worklog-recorder/` and links that copy in herdr:

```bash
m2b-worklog recorder install
```

If it fails, pass the one line on and stop here; running this setup again finishes it. Then turn
the add-on on, so each
curation run writes the daily worklog before it files the inbox:

```bash
m2b addons on worklog
```

And turn recording on now instead of at the next session:

```bash
m2b-worklog hook session-start
```

## 6. Tell the owner

In three or four sentences: herdr now records when agents work and which workspace has focus,
into `~/.local/state/m2b/worklog/` on this machine only, through the plugin
`m2b.worklog-recorder` this setup hooked into herdr; `/m2b:worklog-setup remove` takes it out
again. A timer of the operating system runs the recorder every five minutes; while herdr runs it
writes a sign of life, so a stretch it did not record shows in the note as not recorded instead of
as a time without work. If the install line says the timer could not be set up, pass that on. The first worklog is written by the next
curation run, covering at most the last three days, and then once a day. The note lands in the
archive like any capture; the time spans are in `state/addons/worklog/ledger.csv` and
`ledger.xlsx` in the store, regenerated every day and not for editing.

## 7. Remove

One command after the other:

```bash
m2b addons off worklog
```

```bash
m2b-worklog recorder remove
```

```bash
m2b-worklog hook session-start
```

The last command turns the recording switch off at once.

Then ask whether the recorded events on this machine should be deleted too. Only on a clear yes:

```bash
m2b-worklog recordings delete
```

The worklog notes, the ledger and the exports in the store stay; they are the owner's records.
