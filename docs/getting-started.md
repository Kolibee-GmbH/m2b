# Getting started

Two ways in: inside Claude Code, which is how m2b is meant to be used, and from the command
line out of a checkout, which works on any system with Python 3.9 and needs neither Claude Code
nor a model. Both end with a first capture, a curation run and a first search.

## In Claude Code

1. Add the marketplace and install m2b:

   ```
   /plugin marketplace add Kolibee-GmbH/m2b
   ```

   ```
   /plugin install m2b@m2b
   ```

   A new version reaches you through `/plugin marketplace update m2b` and
   `/plugin update m2b@m2b`, see [Updating](../README.md#updating). To install from a checkout
   instead, for example to try a branch, add it as the marketplace:
   `/plugin marketplace add <path to the checkout>`, then the same install; before an update run
   `git pull` in it, because the marketplace is that folder and updating it fetches nothing.

   **You should see** the install end with `Plugin is now active.`, or with
   `Run /reload-plugins to apply.`, which Claude Code then runs by itself. Type `/`: `/m2b:m2b` is
   in the list. **If not:** run `/reload-plugins`, or start a new session.

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
   Running it again with the same answers changes nothing. After the core, it offers the one
   add-on, the worklog.

   **You should see** setup end with the lines of `m2b doctor`, one per part, among them
   `store: reachable` and `tasks: reachable`. Started as `/m2b:setup` with every answer in the same
   prompt, setup took 15 seconds (2026-11-12, with the model `sonnet`); answered one by one it
   takes as long as your answers do. **If not:** a line that says `not reachable`, `missing` or `not installed` comes
   with what to do, and `/m2b:m2b doctor` repeats the check at any time.

   Outside Claude Code, the `m2b` command is that launcher. If `~/.local/bin` is not on your
   `PATH` (it is not by default on macOS), add it, for example in `~/.zshrc`:

   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

   Inside a Claude Code session you can also run a command with a leading `!`, such as
   `!m2b status`.

3. Capture something. In any session:

   ```
   remember that the spare key is under the blue pot
   ```

   **You should see** a short confirmation; its words are the model's. What does not vary: the
   note is one new file in the store's `inbox/`, `!m2b status` begins with `inbox: 1`, and with
   the band the status line below the prompt reads `1 in inbox`. Nothing is filed yet.
   **If not:** when Claude answered without noting anything, say that you want it kept
   ("remember ...", "note ..."), or type `/m2b-note the spare key is under the blue pot`, which
   asks no model. When the answer is that m2b is not set up, go back to step 2.

4. Start a new session. Its start is what starts the curation run, in the background and on your
   Claude Code login; you type nothing. The run took 13 seconds for this one capture and 26 for
   three (2026-11-12, with the model `haiku`).

   **You should see** nothing in the conversation: the run is silent. `!m2b status` says
   `run: running ...` while it goes on, then `run: succeeded ...` and `inbox: 0`; the status line
   reads `curating`, then `0 in inbox · curated 17:26` with the time the run ended. The note has
   moved from `inbox/` to `corpus/YYYY/MM/`, and `memory/MEMORY.md` has a line with the fact.

   This session started before the run ended, so the fact is not among what it was given at its
   start. Asked for the spare key, it still answers, by searching: search reads the inbox too.

   **If not:** `!m2b status` says in its line `due` whether a run is due and why not, and in a
   line `paused` when you paused this machine. `!m2b curate --force` runs it now, in front of you,
   and says in two lines how it ended and what it did to the inbox, such as
   `the curation run succeeded` and `inbox: 1 capture filed, 0 waiting`; add `--detach` to run it
   in the background instead. After a run that
   failed, the review task in your list names the step and the cause
   ([Troubleshooting](../README.md#troubleshooting)).

5. Start one more session and ask:

   ```
   where is the spare key?
   ```

   **You should see** the answer without a tool call before it: this session was given the fact
   at its start, in the distillate. From a terminal, the same store answers a search:

   ```bash
   m2b search -- "spare key"
   ```

   It prints each line that matches with its file: the fact in `memory/`, the note in `corpus/`.
   **If not:** look for the line in `memory/MEMORY.md`. When it is missing, the run filed the
   note another way, which `!m2b todos` and the files under `memory/` show; a sentence that names
   a day can become a task instead of a fact. When the line stands under a `###` heading, the run
   filed it under a topic: the session started with the topic's name only and answers by
   searching, or without a search once your prompt names one of the words in the heading's
   brackets ([Correcting what a run filed](curation.md#correcting-what-a-run-filed) says how to
   move it). When the line is there, above every `###` heading, and the session does not
   know it, `m2b doctor` says in its line `band` whether the latest session ran m2b's hooks, and
   `m2b distillate on` turns the distillate back on in a folder where it was turned off.

From the next session on, [the band](band.md) above the prompt shows what curation asks you to
keep or drop. It is a mod, a module Claude Code loads with the plugin, and runs only while mods are
on in Claude Code: `m2b doctor` says in its line `band` whether it ran, and
[What it needs](band.md#what-it-needs) what to do when it did not. With it come
`/m2b-note <text>`, which notes a text at once without a model turn, `/m2b-review`,
`/m2b-proposals` and `/m2b-search <text>`, which show the last curation run, the proposals from
your sessions and search hits in a pane, and two tools through which the model notes and searches
without a shell call. The worklog add-on is off until its own setup skill turns it on;
[Add-ons](addons.md) describes it.

Setup asked, on the machine that curates, whether curation runs may read your sessions. It is off
until you say yes there, or later with `m2b config set curation.read_sessions true`. With a yes, a
run reads what you typed in Claude Code since the last reading, and only that: no answer of Claude,
no tool result, no pasted block, nothing a plugin or another agent sent. A model proposes from it what belongs in your memory
although you never said "remember this", each proposal with your own words, and nothing is filed
before you keep it: `/m2b-proposals` in a session, or from a terminal:

```bash
m2b proposals
m2b proposals keep <id>
m2b proposals drop <id>
```

[Reading your sessions](curation.md#reading-your-sessions) says what is read and where it goes.

## From the command line, without Claude Code

This path runs on Linux and macOS with the `folder` store and `markdown` tasks. It is how you try
m2b on a server, in a container, or before installing it in Claude Code.

1. Get the code and put the core's command on your `PATH`. Clone the repository to `~/src/m2b`
   (not `~/m2b`, which is where setup's quick start puts a store). `M2B_CORE_ROOT` tells the launcher to run the core from this checkout
   instead of from Claude Code's plugin folder:

   ```bash
   git clone https://github.com/Kolibee-GmbH/m2b.git ~/src/m2b
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

   The run succeeds and says so, with `inbox: 0 captures filed, 1 waiting` as its second line: the
   capture stays in the inbox, because filing it is the model's work. With
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
| `~/.local/state/m2b/` | lock, run log, temp files, the worklog's recordings, and while sessions are read the git remotes of the folders they start in |
| `~/.local/state/m2b/memory-before-run/` | copies of `memory/` from before a run's model steps: the latest run's copy until the next run, and an older one while a review task still names it for a facts line a run removed or rewrote ([The curation run](curation.md)). They hold what your facts say, outside the store folder |
| `~/.local/share/m2b/` | the copy of the worklog's herdr recorder, with the worklog add-on |
| `~/.local/bin/m2b` | the launcher scripts and schedules call |

The machine paths are the same on macOS and Linux. m2b does not read `XDG_CONFIG_HOME`,
`XDG_STATE_HOME` or `XDG_DATA_HOME`: a Shortcut, a cron job and herdr often start without the
variables your shell sets, and each of them must find the same files. To move all of them
together, set `M2B_HOME`; the folders above then sit under it instead of under your home folder.

Next: [The curation run](curation.md), [Configuration](configuration.md),
[Several machines](several-machines.md).
