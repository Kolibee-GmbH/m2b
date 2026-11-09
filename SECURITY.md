# Security

## What m2b handles

Your notes, your task list and, with the worklog part, a record of when you work in which
folder. All of it stays in folders you chose: the store, `~/.config/m2b/` and `~/.local/state/m2b/`
on each machine, and the backup target. m2b makes no network calls of its own; the model steps go
through Claude Code like any session.

The model runs only fenced: from an empty folder, without your settings or other plugins, with
exactly the commands and store paths its step lists, and nothing else allowed. A tool call outside
that list is denied and reported in the run's review task.

## Untrusted input

A capture is text from wherever it came: a share sheet, a shortcut, an integration writing into
`inbox/`, a web page someone pasted. m2b treats it as data, but the ingest step is a model that
reads it, and a capture can be written to steer that model. What such a capture can reach is what
ingest is allowed: the `m2b ingest`, `m2b search` and `m2b curate report` commands, reading the
inbox and `memory/`, and editing files in `memory/`. Two more steps read captures as evidence:
refresh, which may also read the whole archive and edit the distillate and the facts that are due,
and, with the worklog part, its daily step, which may also read the task list and propose memory
candidates. So a capture cannot run another command, read outside the store or delete the archive,
but it can:

- put lines of its choosing into `memory/MEMORY.md`, the distillate every new session starts with,
  and into the fact files beside it;
- create tasks in your task list;
- move its own and other waiting captures into the archive with misleading notes.

Code checks what the step did to `memory/` against a copy taken just before it. Each facts line
ingest removed or rewrote lands in the review task, with the captures it filed and where the copy is
kept (`~/.local/state/m2b/memory-before-run/`), and it comes back in every review until you complete
the review task. A line holding characters that hide or reorder text, such as bidirectional controls
or tag characters that spell invisible ASCII, undoes the step; the hooks remove the same characters
before the distillate reaches a session. Lines a capture adds are not flagged, because adding is
what ingest is for.

The distillate is printed at session start under a header saying it is data from your notes, not
instructions, and it is cut at 8 KB; a model reading it is still a model and may follow text that
looks like an instruction. So:

- let only clients you trust write into `inbox/`; integrations follow the contract in
  [docs/integrations.md](docs/integrations.md) and are your choice to install;
- read `memory/MEMORY.md` now and then, or keep the store in a folder whose changes you see (a git
  repository, a backup with history);
- `m2b distillate off` keeps the distillate out of projects where it must not appear, on the
  machine you run it on.

## Reporting a vulnerability

Please do not open a public issue. Report it privately through the repository's security advisory
form ("Report a vulnerability" on the Security tab), with the steps that show it and the version
of m2b involved. You get an answer within a week.
