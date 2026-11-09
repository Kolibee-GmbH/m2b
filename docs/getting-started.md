# Getting started

Two ways in: inside Claude Code, which is how m2b is meant to be used, and from the command
line out of a checkout, which works on any system with Python 3.9 and needs neither Claude Code
nor a model. Both end with a first capture, a curation run and a first search.

## In Claude Code

1. Add the marketplace and install m2b:

   ```
   /plugin marketplace add b33eep/m2b
   ```

   ```
   /plugin install m2b@m2b
   ```

   Until m2b is published, add the marketplace from a checkout instead:
   `/plugin marketplace add <path to the checkout>`, then the same install. A new version reaches
   you through `/plugin marketplace update m2b` and `/plugin update m2b@m2b`, see
   [Updating](../README.md#updating); installed from a checkout, run `git pull` in it first,
   because the marketplace is that folder and updating it fetches nothing.

2. Run setup in a session and answer its questions:

   ```
   /m2b:m2b setup
   ```

   Its first offer is the quick start: a new folder `~/m2b`, created for you, with tasks as
   Markdown files in it. For a store that syncs between Macs, choose a folder in iCloud Drive
   instead (backend `icloud`), or any folder you created (backend `folder`); setup creates no
   folder you name yourself, so a typo never becomes a store.

   It writes the machine config, the store's files (`store.json`, `profile.json`, `STORE.md`,
   `memory/MEMORY.md`), the folders and the launcher `~/.local/bin/m2b`, then runs `m2b doctor`
   and lists anything left for you to do by hand, such as the Reminders permission on macOS.
   Running it again with the same answers changes nothing. After the core, it offers each
   optional part, one at a time.

   Outside Claude Code, the `m2b` command is that launcher. If `~/.local/bin` is not on your
   `PATH` (it is not by default on macOS), add it, for example in `~/.zshrc`:

   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

   Inside a Claude Code session you can also run a command with a leading `!`, such as
   `!m2b status`.

3. Capture something. In any session: "remember that the spare key is under the blue pot".
   Start a new session: nothing is filed yet, the note waits in `inbox/`.

4. Curate. The run starts by itself at the next session start; to start it now:

   ```bash
   m2b curate --force
   ```

   It takes about a minute for a few captures. `m2b curate --force --detach` runs it in the
   background instead.

   The fact goes into `memory/MEMORY.md`, the capture into `corpus/YYYY/MM/`. The next session
   starts with the fact.

5. Search: "what did I note about the spare key?", or from a terminal:

   ```bash
   m2b search -- "spare key"
   ```

The optional parts (band, herdr neighbours, worklog, backup) are off until their own setup skill
turns them on; see the [README](../README.md#optional-parts).

## From the command line, without Claude Code

This path runs on Linux and macOS with the `folder` store and `markdown` tasks. It is how you try
m2b on a server, in a container, or before installing it in Claude Code.

1. Get the code and put the core's command on your `PATH`. Until m2b is published, use a checkout
   or an archive of this repository unpacked to `~/src/m2b` (not `~/m2b`, which is where setup's
   quick start puts a store). `M2B_CORE_ROOT` tells the launcher to run the core from this checkout
   instead of from Claude Code's plugin folder:

   ```bash
   git clone https://github.com/b33eep/m2b.git ~/src/m2b
   export PATH="$HOME/src/m2b/plugins/m2b/bin:$PATH"
   export M2B_CORE_ROOT="$HOME/src/m2b/plugins/m2b"
   ```

2. Create the store folder and set this machine up. `setup apply` takes the answers the setup
   skill would ask for, as one JSON object:

   ```bash
   mkdir -p ~/notes
   m2b setup apply --answers '{"store": {"backend": "folder", "path": "~/notes"}, "tasks": {"backend": "markdown"}, "owner": "Alex", "language": "en", "calendar": "none", "curates": true}'
   ```

   It prints each file it wrote: the machine's files with their full path, the store's files
   relative to `~/notes`. The line about `claude` not being found is expected here. Setup also
   writes the launcher `~/.local/bin/m2b`, which schedules call; in this walk-through keep using
   the `m2b` from the checkout on your `PATH`.

3. Capture and look:

   ```bash
   m2b capture "Alex keeps the spare key under the blue pot"
   m2b status
   ```

   `status` shows one capture in the inbox and that a run is due.

4. Run the curation. Without a model the model steps (ingest, and lint or refresh when they have
   something to read) cannot start, and the run reports that. To see every other step run, point `M2B_MODEL_RUNNER` at the stand-in
   `scripts/no-model`, which does nothing and ends well:

   ```bash
   M2B_MODEL_RUNNER="$HOME/src/m2b/scripts/no-model" m2b curate --force
   m2b status
   ```

   The run succeeds; the capture stays in the inbox, because filing it is the model's work. With
   `no-model` the model steps count as succeeded without doing anything, which is why
   `~/notes/state/core/last-run.json` lists the steps as `succeeded` (refresh as `skipped`, nothing being due) next to an unchanged inbox.
   `status` still says a run is due, for the same reason: the capture is still waiting.

5. Search:

   ```bash
   m2b search -- "spare key"
   ```

   It finds the capture in `inbox/`. Search reads the archive, memory and the inbox.

To file captures for real, install Claude Code, log in, and run `m2b curate --force` without
`M2B_MODEL_RUNNER`. If `claude` was not on your `PATH` when you ran setup, record where it is:

```bash
m2b config set executables.claude "$(command -v claude)"
```

## What is where

| Path | What |
|---|---|
| `<store>/inbox/` | new captures, one file each, never edited |
| `<store>/corpus/YYYY/MM/` | the archive, by capture month |
| `<store>/memory/MEMORY.md` | the distillate every session sees |
| `<store>/tasks/` | your tasks, with the `markdown` backend |
| `~/.config/m2b/config.json` | this machine's settings |
| `~/.local/state/m2b/` | lock, run log, temp files, the worklog's recordings |
| `~/.local/share/m2b/` | the copy of the worklog's herdr recorder, with the worklog part |
| `~/.local/bin/m2b` | the launcher scripts and schedules call |

The machine paths are the same on macOS and Linux. m2b does not read `XDG_CONFIG_HOME`,
`XDG_STATE_HOME` or `XDG_DATA_HOME`: a Shortcut, a cron job and herdr often start without the
variables your shell sets, and each of them must find the same files. To move all of them
together, set `M2B_HOME`; the folders above then sit under it instead of under your home folder.

Next: [The curation run](curation.md), [Configuration](configuration.md),
[Several machines](several-machines.md).
