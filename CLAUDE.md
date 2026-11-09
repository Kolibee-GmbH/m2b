# m2b

## About

An open-source second brain for Claude Code: capture notes, curate them into an archive and a
small distillate every session sees, tasks in Apple Reminders or Markdown files, add-ons
(band mod, herdr neighbours, worklog, backup), all in one plugin. [Architecture](docs/architecture.md)
is the tour of the code; [Behavior](docs/behavior.md) lists the rules the tests cover.

## Tech Stack

Python 3.9+ (standard library only, unittest), TypeScript for the band mod, shell scripts
for `scripts/`. macOS 14+ for the Apple backends (iCloud Drive, Reminders via `reminders-cli`,
Calendar via JavaScript for Automation); Linux with the folder store and Markdown tasks.

## Current Status

0.1.1 is the current release, written up in [CHANGELOG.md](CHANGELOG.md); the repository is not
published yet. New changes go under `## [Unreleased]`; how a release is made is in
[CONTRIBUTING.md](CONTRIBUTING.md#releasing).

## Project Instructions

- Code, tests, docs and commit messages in English. No personal data anywhere: this
  repository is public. Test data is invented (Alex, Dana, Acme).
- Never test against a real store, a real Reminders list or real calendars; test resources
  start with `sb-test-`. Headless model tests run fenced: from an empty folder with
  `--setting-sources project`, `--plugin-dir plugins/m2b`, `--permission-mode dontAsk` and their own
  `M2B_HOME`; the launcher only with `M2B_CORE_ROOT` pointing at this checkout.
- On a machine where m2b is installed for real use, test this checkout only through `--plugin-dir`
  and its own `M2B_HOME`, never against that machine's config, state or store.
- A decision a later reader needs is written where the code makes it: in a comment, a docstring
  or the docs.
- Code, comments, tests and docs never point to design records, findings or a work queue; they
  state the reason themselves. The design history is kept outside this repository.

## Development

```bash
scripts/check --quick m2b        # the core's unit tests (or worklog, backup, herdr, band)
scripts/check                    # the full proof
scripts/e2e --level stub         # end-to-end scenarios with the scripted model
```

## Recent Decisions

None kept here: each decision is stated where the code makes it.
