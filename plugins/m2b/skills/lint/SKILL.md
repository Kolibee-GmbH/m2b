---
name: lint
description: Checks the owner's second brain for broken links, misnamed or misplaced notes, conflict copies and an oversized distillate, removes what is safe to remove, repairs unambiguous broken links in memory, and hands the rest to the curation run's review. Runs only inside a curation run, which starts it fenced; asked for it by name in a session ("lint my second brain", "lint mein Second Brain"), it does not lint there and starts a curation run in the background instead.
allowed-tools: Bash(m2b lint scan *), Bash(m2b curate --force --detach)
---

# Lint

The code finds the problems; you repair the one kind that needs reading, broken links in
`memory/`, and only when the answer is unambiguous. Everything else goes to the owner through
the run's review.

Run every command as a Bash call of its own, exactly as shown: no `&&`, `;`, `|`, `echo` or
redirection. The run allows each `m2b` command by itself and denies anything chained.

## 1. Only inside a curation run

```bash
m2b lint scan --json
```

If `curation_run` is `false`, you were asked in an ordinary session. Do not lint here. Start a
curation run in the background, which checks the store fenced:

```bash
m2b curate --force --detach
```

Tell the owner, with the number of findings, exactly what it printed: either that a run started
(and that `m2b status` shows how it goes, the review task what needs them) or why none did. Do
not say more than it printed. Then stop.

The answer gives `store` (the store's folder) and `findings`, each with `code`, `kind`, `path`,
`text`, and for a broken link `link` and `candidates`.

## 2. The safe fixes

```bash
m2b lint fix
```

It removes conflict copies that equal their original and this product's old temp files, nothing
else.

## 3. Broken links in memory

For each finding with `code` `broken-link`:

- **Exactly one candidate:** read `<store>/<path>`, then edit it: replace `[[<link>]]` with
  `[[<candidate>]]`, every occurrence in that file. If the file already links `[[<candidate>]]`,
  remove the list line with the broken link instead, because a fact file links a capture only
  once. Change nothing else in the file.
- **No candidate, or more than one:** leave it. The owner decides.

A repair in `MEMORY.md` changes the link only and never moves a line: a line above the first `###`
heading is printed in every session, one under a topic only when that topic is named.

Never repair anything else, never create a file, never delete one.

## 4. Hand the rest to the run

```bash
m2b lint scan --report
```

It scans again and hands every finding that is left to the run's review, so a link you repaired
is not reported. Report nothing yourself.

## Answer

One line: how many links you repaired, what `lint fix` removed, and how many findings went to the
review.
