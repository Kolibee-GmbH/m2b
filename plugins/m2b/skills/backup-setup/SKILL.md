---
name: backup-setup
description: Sets up the m2b backup on this machine - the folder that holds the snapshot and how many days replaced files are kept - and turns the backup part on so it runs after each curation run, or turns it off with "remove". Use when the user says "set up the backup", "back up my second brain", "Backup einrichten", "change the backup folder", "remove the backup", "Backup entfernen", or when the owner turns on the backup part. Running it again with the same answers changes nothing.
allowed-tools: Bash(m2b config get *), Bash(m2b config set parts.backup.target *), Bash(m2b config set parts.backup.attic_days *), Bash(m2b parts on backup), Bash(m2b parts off backup), Bash(m2b-backup run), Bash(m2b-backup run *), Bash(m2b status), Bash(m2b status *)
---

# Backup setup

iCloud Drive and other synced folders copy a mistake to every machine within minutes, so they are
no backup. This part of m2b keeps a local snapshot of the store after each curation run: a mirror of
its files, the older versions of what changed in an attic folder per day, and a dump of the task
list. You ask, and the commands below write everything.

Run each `m2b` command in a Bash call of its own, as shown: nothing chained before or after it,
no `echo $?`. This skill may run the command alone without asking, and Claude Code reports a
failing exit code by itself.

If the owner asked to remove the backup, go to section 4.

## 1. What is set already

```bash
m2b config get parts --json
```

If it holds `backup` with a `target`, show the owner its `target`, its `attic_days` and whether
`on` is `true`, and ask what to change.

## 2. Ask

1. **The folder**: where the snapshot goes, outside the store and outside any synced folder, for
   example `~/Backups/m2b` or a folder on an external disk. It must exist already; if it does
   not, ask the owner to create it. A folder on a disk that is not connected makes the backup
   fail and say so in the review, instead of writing somewhere else.
2. **The days**: how long older versions stay in the attic, 30 unless the owner wants another
   number of whole days.

## 3. Write and try

One command after the other:

```bash
m2b config set parts.backup.target '<folder>'
```

```bash
m2b config set parts.backup.attic_days 30
```

```bash
m2b parts on backup
```

```bash
m2b-backup run
```

The last command makes the first backup now. Tell the owner what it printed: how many files it
copied and how many tasks it dumped. A line starting with `action:` or `info:` is something to
pass on as it stands, for example files iCloud Drive has not downloaded, which the next backup
copies once they are back.

Then say in one sentence that the backup runs after each curation run on the machine that
curates; this command tells whether that is this one:

```bash
m2b status --json
```

If `this_machine_curates` is `false`, add that this machine backs up only after it takes over
curation; a second backup set up on the curating machine covers the store meanwhile.

## 4. Remove

```bash
m2b parts off backup
```

The settings stay in `config.json`, so turning the part on again with this skill keeps the folder.
The snapshot in the folder stays too; it is the owner's to delete.
