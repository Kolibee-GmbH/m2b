# Add-ons

An add-on is any client outside this marketplace: a phone shortcut, a watch app, a script, a
mail filter. It works with the store directly, through the files described in
[Store format](store-format.md), or through the `m2b` command where m2b is installed. The rules
below keep the curator the only one who files, so two writers never fight over a file.

## What an add-on may do

1. **Create new files in `inbox/`**, each created exclusively (never over an existing name), in
   the format of the store, with its own `source` token and without `curated`.
2. **Create tasks** in the task list `store.json` names; with the `markdown` backend, a new file
   in `tasks/`.
3. **Read** `corpus/`, `memory/`, `STORE.md` and `profile.json`.
4. **Keep its own state** under `state/addons/<add-on>/`.
5. **Call** `m2b capture`, `m2b tasks add` and `m2b calendar add` where m2b is installed.

It never moves, renames, edits or deletes anything outside its own state folder. The core never
reads `state/addons/`. If an add-on needs more than this, it belongs in the product, or the
contract on this page grows first. m2b's own optional parts follow the same rules, with
their state under `state/parts/<part>/`.

## A capture from outside

The simplest add-on writes one file. A shell example with invented content:

```bash
store="$HOME/notes"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
suffix=$(od -An -N2 -tx1 /dev/urandom | tr -d ' \n')
file="$store/inbox/$stamp-mailfilter-$suffix.md"
set -o noclobber
printf -- '---\ncreated: %s\nsource: mailfilter\n---\n%s\n' \
    "$(date +%Y-%m-%dT%H:%M:%S%z | sed 's/\(..\)$/:\1/')" \
    "Invoice from the plumber arrived" > "$file"
```

`noclobber` makes the shell refuse an existing name; draw a new suffix and try again. Where m2b is
installed, `m2b capture --source mailfilter "Invoice from the plumber arrived"` does the same
with the collision handled.

## Reading

`corpus/` and `memory/` are meant to be read: show the distillate on a watch face, search the
archive from a phone. On iCloud Drive a file may not be downloaded yet; read it through the system
API that downloads it, and treat "not downloaded" as "could not look", never as "not there".
