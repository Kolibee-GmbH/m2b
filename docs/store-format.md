# Store format

This page describes format 3, the current one; [Formats](#formats) lists what changed and when.

The store is a plain folder. Everything in it is a text file you can read and back up with any
tool, or a picture or a document you gave it; m2b has no database and no hidden index. `STORE.md` in the store repeats the rules an
integration needs, generated from `store.json`.

```
<store>/
├── STORE.md        the rules for integrations, generated
├── store.json      settings every machine shares
├── profile.json    the owner's profile
├── inbox/          new captures; every client only adds files here
├── corpus/YYYY/MM/ the archive, by month, no topic folders
├── memory/         MEMORY.md (the distillate), one file per fact, and lessons/ with one file
│                   per lesson you kept
├── tasks/          only with the markdown task backend: one file per task
└── state/
    ├── core/       the run record, the memory candidates, the open "Still current?" and
    │               "Still needed?" questions (lesson-questions.json), the proposals from your
    │               sessions and your answers to them, lessons kept in a session (lessons-kept/),
    │               the fixes (fixes/) and how often you corrected Claude on a lesson again
    │               (lesson-counts.json)
    ├── addons/<add-on>/
    └── integrations/<integration>/
```

## File names

`YYYYMMDDTHHMMSSZ-<source>-<4 hex>.<ext>`, for example `20261107T091500Z-cli-a1b2.md`. The time is
UTC, so names sort in capture order across time zones and daylight saving. `source` is a lowercase
token that says who captured: `claude`, `cli`, `candidate`, `proposal`, `worklog`, or an integration's
own name.
The name never changes after capture, because links point to it.

A file with any other name may be dropped into `inbox/`; the next run gives it a name of this
form and keeps the old name in the note's curation trailer. A file the run cannot file (a date it
cannot read, a text that is not UTF-8, a capture in a subfolder) stays where it is, is named in
the review task, and starts no further run until it changes. The journal of completed tasks is the
one exception in the archive: `corpus/YYYY/MM/YYYYMM-done.md`, one per month.

A symlink is never content, anywhere in the store. m2b does not list or read one, whatever it
points at, enters no folder that is one and writes through none; lint names it in the review task
until the file or folder itself is in its place or the link is gone
([Security](../SECURITY.md#untrusted-input) says why).

## A note

```markdown
---
created: 2026-11-07T10:15:00+01:00
source: cli
---
Dana's birthday is on 3 March
```

The frontmatter is a block between `---` lines, one `key: value` per line, lists inline as
`[a, b]`. It is a small fixed subset, not YAML.

| Key | Set by | Meaning |
|---|---|---|
| `created` | the client, required | capture time with its offset |
| `source` | the client, required | who captured |
| `quiet: true` | the client | keep the note out of everything proactive (rediscover, `## Current`); search still finds it |
| `follow_up` | the client | a due date whose task is still to be created |
| `kind` | the writer | `worklog`, `journal` or `sidecar`; absent on a plain capture |
| `tasks` | capture, ingest | ids of the tasks created from this note |
| `refs` | ingest | archive file names or URLs; merged, never replaced |
| `from_candidate` | harvest | the candidate task a capture came from |
| `from_proposal` | harvest | the proposal a capture came from, by its id |
| `facts_filed: true`, `curated: true` | the curator | how far ingest got; a client never writes these |

**The captured text is never rewritten.** The curator appends its notes after a last line
`<!-- m2b:curation -->` and sets `curated: true`.

**Photos and other binary files** become a bundle: the original under the schema name, a reading
copy when the format needs one (HEIC as JPEG on macOS), and a sidecar `<stem>.md` with
`kind: sidecar`. The sidecar moves last, so a bundle in the archive is always complete. A file a
session captures with `m2b capture-file` reaches the inbox as such a bundle: the sidecar is written
first, with the words that came with the file below the line that names it and the original file
name in the trailer, then the file. A sidecar whose file has not synced to the curating machine
yet stays in the inbox until a run finds the file beside it. For a PDF
of more than one page the curator writes the document's outline into the sidecar's trailer, one
line per page or run of pages (`p. 3: ...`, `pp. 6-9: ...`) and, where it stopped before the last
page, `outline: pages 1-60 of 75`.

## Memory

`memory/MEMORY.md` has two sections:

```markdown
# Memory

## Facts

- Dana's birthday is on 3 March (dana.md)

### Acme Ltd (Acme, Kim Lee)
- Kim Lee leads Acme's IT (kim-lee.md)

## Current

- Planning the trip to Porto (since 2026-10-02)

### Acme Ltd (Acme, Kim Lee)
- Building the export for Acme (since 2026-11-02)
```

A facts line is `- <statement> (<fact file>)`. A fact file such as `memory/dana.md` holds the
current truth and, under `## Evidence`, `[[corpus file]]` links, the first being the capture the
fact came from. A capture is linked once per fact file, which makes filing a fact safe to repeat. A
fact that stops being true on a known day has that day in the fact file's frontmatter, `until:
2026-11-14`, and a file of its own (`sam-plywood.md` beside `sam.md`), because `until` holds for the
whole file; a lasting fact has none. When a capture changes a fact, its old value stays in the fact
file under `## Earlier`, above `## Evidence`, one line each, `- Lived in Zurich (until 2026-11-07)`,
the day being the last one it held; lint reports a line in another form. Earlier values never go
into `MEMORY.md`. A current item ends in `(since YYYY-MM-DD)`, the day the
latest capture about it was made or the owner last confirmed it still holds. Both are optional for a
reader, and lint reports one that is no date.

Facts before the first `###` heading hold everywhere: every session starts with them. A topic is a
group inside `## Facts`, headed `### <name> (<word>, <word>)`; the words are the last
parenthesised group, two to five of them, each 3 to 40 characters, and the name at most 60. A
session start lists the topics by name and brings in a topic's facts and current items only when one of its words is
in the project folder's path, or, before a prompt, when the prompt names one; a word matches whole
and regardless of case. A new fact that holds everywhere goes
above the first `###`, because a line added at the end of `## Facts` would land in the last topic.
A reader that knows nothing of topics reads their lines as ordinary facts. What every session
starts with aims at 2 KB, and so does each topic; lint reports more. A topic over 4 KB comes in
with no prompt, because a prompt brings whole topics only: lint reports it as something to act on,
to shorten the topic or split it in two.

A topic about a project may name the project's repository in one line of its own,
`- Repository: github.com/acme/portal (acme-portal.md)`: the address of its git remote, host and
path, which is the same on every machine. The store never names a folder on a machine. Where the
topic comes into a session, the line comes with one more below it, `  on this machine:` and the
folder the repository lies in here, or `  not cloned on this machine`; the folder is found in the
notes the session start keeps in this machine's state of the remotes of every folder a session
starts in, the one seen last that is still there.

Its other lines can point into the repository: a sentence, `→` and a path in the repository, with a
heading where it helps; the path follows the last `→` and is one word with a `/` or a `.`,
`- Login moves to the customer's identity provider in March →
docs/records/014-login.md (acme-portal.md)`. The content stays in the repository; the line says that
it exists and where. Where such a topic has a clone on the machine, its place line ends with
`; the paths after → lie in it`. Lint on the curating machine reports a pointer whose file that
clone does not hold, a pointer that leaves the repository, and, as information, a repository no
folder there was opened in for 30 days; a project topic is measured against the 4 KB with its place
line.

A lesson you kept is a file of its own under `memory/lessons/`, written by a curation run:

```markdown
---
kind: knowledge
target: every project
kept: 2026-11-20
---
# The checks a change touches

Run only the checks the change touches; the whole proof only when the change gives a reason.

## Evidence

- [[20261120T101500Z-claude-a1b2.md]]
```

An action lesson names the words a command holds when it applies, `words: [scripts/check]`, and
those that keep it silent, `unless: [--quick]`; `ask: true` has Claude Code ask you before the
call. A lesson you keep in a session waits in `state/core/lessons-kept/` until the next run files it.
`kind` is `knowledge` (how to name or judge a thing) or `action` (about a command), `target` is
`every project` or a repository's address, and `kept_at` names the source that states it now,
such as `~/.claude/CLAUDE.md`, written when the lesson is kept or when a later reading finds the
source stating it. Every session starts with the knowledge lessons for every project
that no source states, in an output of their own beside the distillate, which keeps its 8 KB.

`## Current` holds topics under the same headings: a current item above its first `###` heading
reaches every session, one under a topic comes in with that topic, below its facts under
`#### Current`. Headings with the same name, in either section, are one topic, and a word of any of
them names it; a topic may stand under `## Current` alone. Ingest puts a new item as it puts a
fact: one that holds everywhere above the first `###` there, one about a single subject under that
subject's heading, which it copies from `## Facts` when the topic has one there. An item above the
topics that is about one subject moves under its topic when ingest files a capture about the same
thing, and at every run, in code, when it names a word of exactly one topic, as a prompt would; an
item under a topic stays there, and no other step moves an item. When a "Still current?" answer takes a topic's last item out,
its heading under `## Current` goes with it, unless another line is left below it; ingest is told
to remove the heading with the last item it takes out.

## Tasks

The curator's own tasks carry a marker as the first line of their notes, so they are found by
marker, never by title: `m2b:review` for the review task, `m2b:candidate` for a memory candidate,
`m2b:current` for a "Still current? ..." question about a current item, `m2b:lesson <key>` for a
"Still needed? ..." question about a lesson, `m2b:proposals` for the
one task that says proposals from your sessions wait for an answer, and
`m2b:capture <file> <key>` for a task ingest made from a capture. On Apple Reminders, which has
no dropped state, a dropped curator task carries the line `m2b:dropped` in its notes.

With the `markdown` backend each task is `tasks/<id>.md`, the id twelve random hex characters:

```markdown
---
status: open
created: 2026-11-07T10:15:00+01:00
due: 2026-11-20
---
Call the plumber about the shed
m2b:capture 20261107T091500Z-cli-a1b2.md plumber
```

`status` is `open`, `done` or `dropped`; a finished task also has `done`. A file you add by hand
gets its name as id. A task file m2b cannot read (another status, a date it cannot read, not
UTF-8) is left out of every list and named by lint until it is fixed. A conflict copy of a task
file, which the sync service makes when two machines changed the task, is no second task: lint
names it, and `m2b lint fix` removes it when it equals the task byte for byte.

## Proposals from your sessions

A curation run that reads your sessions ([Curation](curation.md#reading-your-sessions)) keeps what
it proposes in `state/core/proposals.json`:

```json
{
  "format": 1,
  "read_until": "2026-11-07T07:30:00+01:00",
  "announced_until": "2026-11-07T07:30:01+01:00",
  "counts": {
    "person": {"proposed": 9, "kept": 5, "dropped": 2, "expired": 1, "not_quoted": 0},
    "agreement": {"proposed": 3, "kept": 3, "dropped": 0, "expired": 0, "not_quoted": 1},
    "commitment": {"proposed": 0, "kept": 0, "dropped": 0, "expired": 0, "not_quoted": 0},
    "personal": {"proposed": 0, "kept": 0, "dropped": 0, "expired": 0, "not_quoted": 0}
  },
  "proposals": {
    "c501eff5fc0e": {
      "kind": "person",
      "text": "Dana is head of IT at Northwind.",
      "quote": "Dana runs IT at Northwind",
      "topic": null,
      "due": null,
      "day": "2026-11-06",
      "state": "open",
      "since": "2026-11-07T07:30:01+01:00"
    }
  }
}
```

A proposal whose `quote` stands in text you pasted into a prompt has one more field,
`"source": "pasted"`; one without `source` stands on words you typed. While the file holds an
entry with a `source`, its `format` is 2, and an m2b that knows only format 1 answers "update m2b
on this machine" where it would show such a proposal as said and write the file back without the
field; without such an entry the format is 1.

`read_until` is the moment up to which the sessions were read. `announced_until` is when the
newest proposal was added that the task for the waiting proposals has told you of: a task you
completed or deleted comes back only for a proposal added after it. A proposal's id comes from its
session and its `quote`, the words of the session it stands on; `kind` is `person`, `agreement`, `commitment`,
`personal`, `lesson`, `pointer` or `project`; `day` is the day those words were sent, `due` the day a commitment names. A
`project` stands on no words: its `quote` is the addresses of the repository's remotes, its
`"source": "worked"`, its id comes from the addresses alone, and `day` is the last day a session
worked in it. A `pointer` has `"pointer": {"path": "docs/records/014-login.md", "repositories":
["github.com/acme/portal"]}`, the file in its repository and that repository's addresses, and its
`text` is the line it becomes. `state` is `open`,
`kept`, `dropped` or `expired`, and `since` the moment it got that state. An open proposal that
has no answer 14 days after it was added expires. A kept, dropped or expired proposal stays for 90
days, so the same one is not proposed again; the first curation run after that removes it. The
kept and the dropped ones are also what the next reading shows the model, the last 30 of each.

`counts` says per kind how many proposals were added (`proposed`), how many of them ended `kept`,
`dropped` or `expired`, and how many more were refused because the words they quote do not stand,
with at least three words, in a prompt of the session they name (`not_quoted`). A proposal kept
after it expired counts as kept. The counts stay when a proposal is removed: they go back to the
first reading.

Only the curation run writes the file. A file whose
`format` this m2b does not know is left as it is: the reading fails alone, and the review says so.

Your answer is an empty file a client adds: `state/core/proposal-answers/<id>.keep` or
`<id>.drop`. The name is the answer; the file is never opened and never changed. The next run's
harvest writes the capture of a kept proposal, sets the state in `proposals.json` and removes the
answer file.

A proposal a session hands in by itself ([Curation](curation.md#what-a-session-hands-in)) is one
file a client adds, `state/core/handed-in/<session id>.<proposal id>.json`:

```json
{
 "format": 1,
 "kind": "person",
 "text": "Dana Whitfield runs purchasing at Acme.",
 "quote": "Dana Whitfield runs purchasing at Acme",
 "due": null,
 "session": "0a1b2c3d-1111-4222-8333-444455556666",
 "day": "2026-11-15",
 "source": "tool",
 "tool": "Read",
 "at": "2026-11-15T09:44:12.665303+01:00"
}
```

`source` is where the quote stands in the session: `typed`, `pasted`, `tool` or `agent`, an
answer of Claude; `tool` names the tool for a tool's result where its name has the form of one,
and is null otherwise; `at` is the time of the call. The file holds no folder. The next curation run takes it in and removes it. In
`proposals.json` such a proposal has two more fields, `"by": "session"` and, for a tool's result,
`"tool"`, and its `source` can be `tool` or `agent`. While the file holds such an entry its
`format` is 3, and an m2b that knows format 2 answers "update m2b on this machine" where it would
show the proposal as said or under a source it does not know and write it back without the fields.

A proposed lesson, a correction of how Claude works, has one more field:

```json
"lesson": {
  "kind": "action",
  "target": "github.com/acme/portal",
  "words": ["scripts/check"],
  "quote": "no full check without a reason",
  "session": "0a1b2c3d-1111-4222-8333-444455556666"
}
```

`kind` is `knowledge` or `action`, as in a [lesson](using.md#lessons); `target` is `every project` or the
address of the repository its sessions worked in; `words` are, for an action, the words a command
holds when the lesson applies; `quote` and `session` are the same correction in a second session, and
both are empty for a lesson on one correction.
While the file holds a lesson, a project or a pointer its `format` is 4, and an m2b that knows format
3 answers "update m2b on this machine" where it would leave them out and write the file back without
them.

## Fixes for the files Claude reads

A fix you keep is one file a client adds, `state/core/fixes/<name>.json`:

```json
{
  "version": 1,
  "name": "fix-3f9c2a71b0de",
  "file": {"repositories": ["github.com/acme/portal"], "path": "CLAUDE.md"},
  "line": "- Run the whole proof before every commit.",
  "wording": "- Run the checks the change touches; the whole proof only before a release.",
  "why": "The whole proof takes twenty minutes and a small change does not need it.",
  "kept": "2026-11-20"
}
```

A repository is named by the addresses of its remotes, host and path in lower case, and the file
by its path in the repository; a file under `~/.claude/` by `{"home": "~/.claude/CLAUDE.md",
"machine": "<machine id>"}`. `line` is null for a fix that only adds. The name is `fix-` and twelve
letters and digits drawn from the file, the line and the wording. A fix a curation run kept from a
lesson also holds the lesson's sentence, `"lesson": "..."`, under which the reading of your sessions
goes on counting corrections. What became of a fix is an empty
file a client adds beside it, `<name>.done` or `<name>.dropped`; where both are there, done stands.
The session start only reads the fixes.

## Who writes what

| What | Created by | Changed by | Removed by |
|---|---|---|---|
| `inbox/` | clients, integrations, harvest (a ticked candidate, a kept proposal), the worklog | the curating machine (name, frontmatter, trailer; never the text) | ingest moves files into the archive; normalize removes conflict copies identical to their original |
| `corpus/` | ingest, the journal | the journal (appends to the month's file) | lint, only conflict copies identical to their original |
| `memory/` | ingest; harvest (a lesson under `memory/lessons/`) | ingest, refresh, the sorting step, a migration after an update, harvest (only `## Current`, from "Still current?" answers), lint (a broken link it repairs, a current item it moves under its topic), the reading of your sessions (`kept_at` of a lesson a source states) | harvest (a lesson a kept one replaces) and the curation run (a lesson whose "Still needed?" you dropped) |
| `state/core/` | the curation run; any client adds an answer to a proposal under `proposal-answers/`, a proposal a session hands in under `handed-in/`, and a fix and what became of it under `fixes/` | the curating machine | harvest prunes settled candidates and removes the answers it settled; the run removes the handed-in proposals it took in; every curation run removes the proposals kept, dropped or expired 90 days ago or longer |
| tasks (`tasks/` with the `markdown` backend, or the Reminders list) | you, integrations, capture (a follow-up), ingest, `m2b tasks add --candidate` (a memory candidate), the curation run (review, "Still current?" and "Still needed?" questions, the task for waiting proposals) | you, also through the todos skill, which ticks a task you say is done, and through the m2b pane, which ticks one of your tasks with `done` and ticks or drops a curator task with keep, drop or `ok`; the curation run completes its review task when nothing needs you, and the task for waiting proposals when none waits | harvest and the refresh step, once a curator task is settled or its item is gone; lint, with the `markdown` backend, only conflict copies of task files identical to their original; you |
| `state/addons/<a>/`, `state/integrations/<i>/` | that add-on or integration | the same | the same |

Nothing captured is ever deleted by m2b.

## Formats

`format` in `store.json` counts the rules for curated content and the keys of `store.json`. It
goes up when a new m2b changes a rule that content already in a store has to follow, or that an
older m2b must not curate under, and when `store.json` gets a new key: an m2b refuses a key it does
not know in a format it knows, so that a typo is caught, checks a store against the keys of the
store's own format, so that a new key is written only once the store is at the new format, and
reads a newer format leniently.
The curating machine then migrates the store at the start of its next run
([Curation](curation.md#after-an-update)). The inbox is not part of the format: its file names and
the frontmatter `created` and `source` stay the same, so a machine on an older m2b keeps
capturing into a newer store.

| Format | Since | What it holds |
|---|---|---|
| 1 | builds before 0.1.0 | dated facts and current items, topics in the distillate, a fact that ends on a day in a file of its own |
| 2 | 0.1.0 | a changed fact's old value under `## Earlier` in its fact file; the migration changes nothing, so an m2b that knows only format 1 stops curating |
| 3 | 0.4.0 | current items under topics in `## Current`; the migration changes nothing, so an m2b that knows only format 2, whose lint reports such a heading, stops curating |
