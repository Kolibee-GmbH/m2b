# Contributing

Start with [Architecture](docs/architecture.md): where the code is and the three rules it keeps.

## Ground rules

- Python 3.9 or newer, standard library only, in the core and every add-on. Every file starts with
  `from __future__ import annotations`; no `match` statements.
- Tests use `unittest`. Fixtures are invented and built in temporary folders.
- Code, docs and commit messages are in English. Commit messages follow
  `<type>(<scope>): <description>`, for example `fix(capture): keep trailing spaces`.
- No personal data anywhere: no real names, customers, hosts or paths in code, tests,
  fixtures or commit messages.

## Checks

```bash
scripts/check --quick <suite>    # fast: m2b (the core), worklog, backup, herdr or band
scripts/check                    # before every commit: everything, must end with "check: passed"
```

`scripts/check` needs [uv](https://docs.astral.sh/uv/) for the pinned versions of ruff
and mypy, or both tools on your PATH. `shellcheck` and `claude` are used when installed; with
`CI=true` a missing `claude` ends the run at once, because the manifest and band checks need it.
The workflow installs the Claude Code version the README names as the minimum.

## Behavior coverage

Each behavior the product promises has an ID (B1 and up, X1 and up) in the behavior
catalog, [`docs/behavior.md`](docs/behavior.md). A test names the behaviors it
pins in its docstring:

```python
def test_a_name_collision_draws_a_new_suffix(self) -> None:
    """Covers: B2"""
```

`scripts/check` lists every behavior that no test names yet.

## Store format

A change that content already in a store must follow, or a new key in `store.json`, raises
`KNOWN_STORE_FORMAT` and ships a migration (`plugins/m2b/src/m2b/curate/migrations.py`); an
additive change gets one that changes nothing. A key added without it would make every machine on
the m2b before refuse the store, capture included. The keys of each format are in `KEYS_BY_FORMAT`
(`plugins/m2b/src/m2b/config/store_settings.py`), and a store is checked against its own format's
keys, so a new key can only be written once the store is at the new format.
`plugins/m2b/tests/test_store_settings.py` holds a copy of each released entry: a released entry
never changes, a new format gets its own. [Store format](docs/store-format.md#formats) lists what
each number added.

## End-to-end scenarios

A scenario is a folder in `tests/e2e/` with `given/` (the store before), `steps.json`
(the commands to run), `expect.json` (the store after) and, for the model level, `model.json`. `scripts/e2e --level stub`
runs each one with its own `M2B_HOME` and a test config, so it never touches
your own setup.

A scenario with a `model.json` also runs at the model level, with the real `claude` and your own
login, and checks invariants instead of exact files, because a model words things its own way. It
costs model runs, so it is not part of `scripts/check`; run it on purpose:

```bash
scripts/e2e --level model                                   # every scenario with a model.json
scripts/e2e --level model E18-remember-beside-auto-memory   # after each Claude Code minor update
```

`E18-remember-beside-auto-memory` starts a session with m2b and Claude Code's own memory both on
and checks that "remember that ..." about a person lands in m2b's inbox and not in Claude Code's
memory. Claude Code's memory needs your login, so this scenario leaves one session folder under
`~/.claude/projects/`, as every model run does.

## Releasing

Claude Code installs a plugin by its version number. `/plugin update` compares the installed
version with the one in the marketplace and reports "already at the latest version" while they
match, however many commits came since. A change reaches users only with a release:

1. Pick the new version by [semantic versioning](https://semver.org/) and write it into
   `version` in `plugins/m2b/.claude-plugin/plugin.json`.
2. In `CHANGELOG.md`, turn the entries under `## [Unreleased]` into a section
   `## [X.Y.Z] - YYYY-MM-DD` with the day of the release, and leave an empty `## [Unreleased]`
   above it. Entries sit under `### Added`, `### Changed` or `### Fixed`, one sentence or two each
   on what changes for the user, ending in the pull request that made it, as
   `([#12](https://github.com/Kolibee-GmbH/m2b/pull/12))`.
3. Run `scripts/check`; it must end with `check: passed`.
4. Commit both files as `chore(release): m2b X.Y.Z`, open a pull request to `main` and merge it;
   a squash merge is fine. The marketplace reads `plugins/m2b` from `main`, not from a tag, so
   until the merge `/plugin update` keeps reporting the old version.
5. On `main`, at the merged release, tag and push the tag:

   ```bash
   git switch main && git pull --ff-only
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```

   The tag starts `.github/workflows/release.yml`. It checks that the tag names the version in
   `plugin.json` and sits on `main`, and publishes a GitHub release with that version's section
   of the changelog as its notes.

## README images

The screenshots in `docs/images/` come from real Claude Code sessions against a demo store with
invented data. After a change the README pictures show, record them again:

```bash
scripts/readme-images                # all three
scripts/readme-images --only todos   # one
```

It needs `claude` logged in, `node` and `npm`, Chrome or Chromium, ImageMagick and `git`, and each
picture costs one model turn. Claude Code runs with `--setting-sources project`, m2b from this
checkout and its own `M2B_HOME` under `/tmp/sb-test-m2b-demo`, so your settings, plugins and store
stay out of the pictures. The answers are the model's: look at each picture before you commit it.
