# The backup add-on

One of the [add-ons](../addons.md) of m2b, off until its setup turns it on.

## What it does

After each curation run, it makes a local snapshot of the store in a folder you choose:

```
<target>/mirror/            the store's visible files as of the last backup
<target>/attic/YYYY-MM-DD/  each mirror file a backup replaced or removed, under that day
<target>/tasks.json         the task list with completed tasks
```

iCloud Drive and other synced folders copy a mistake to every machine within minutes, so the store
alone is no backup.

## What it needs

A folder outside the store and outside any synced folder, which exists already, and the curating
machine: the backup runs as a step of the curation run.

## Set up and turn off

`/m2b:backup-setup` asks for the folder and the days, writes both, turns the backup on and makes the
first backup at once. By hand:

```bash
m2b config set addons.backup.target ~/Backups/m2b
m2b config set addons.backup.attic_days 30
m2b addons on backup
```

`m2b addons off backup` turns it off; the settings and the snapshot stay.

## What it reads and writes

It reads the store's visible files, the task list through `m2b tasks list` and its own settings
through `m2b config get addons`. Hidden files, Excel lock files (`~$<name>`) and files iCloud Drive
has not downloaded are not copied: a file that is not downloaded keeps the copy the mirror has, and
the backup counts it. It writes only in the target folder, and removes there only attic folders
older than `attic_days` (30 by default), folders in the mirror that became empty, and its own
leftover temporary files. In a curation run it reports what it could not copy, such as files not
downloaded, in the review task. A target on a disk that is not connected makes the backup fail
instead of writing somewhere else.

## Its commands

`m2b-backup run` makes one backup now, the same as the curation step.

## How you see it runs

`m2b-backup run` prints how many files it copied and how many tasks it dumped. In a curation run, a
backup that fails is a finding in the review task, and the run goes on.
