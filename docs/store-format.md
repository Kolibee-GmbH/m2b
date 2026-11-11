# Store format, version 2

The store is a plain folder. Everything in it is a text file you can read and back up with any
tool; m2b has no database and no hidden index. `STORE.md` in the store repeats the rules an
integration needs, generated from `store.json`.

```
<store>/
├── STORE.md        the rules for integrations, generated
├── store.json      settings every machine shares
├── profile.json    the owner's profile
├── inbox/          new captures; every client only adds files here
├── corpus/YYYY/MM/ the archive, by month, no topic folders
├── memory/         MEMORY.md (the distillate) and one file per fact
├── tasks/          only with the markdown task backend: one file per task
└── state/
    ├── core/       the run record, the memory candidates, the open "Still current?" questions,
    │               the proposals from your sessions and your answers to them
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
`kind: sidecar`. The sidecar moves last, so a bundle in the archive is always complete.

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
session start lists the topics by name and brings in a topic's facts only when one of its words is
in the project folder's path, or, before a prompt, when the prompt names one; a word matches whole
and regardless of case. A new fact that holds everywhere goes
above the first `###`, because a line added at the end of `## Facts` would land in the last topic.
A reader that knows nothing of topics reads their lines as ordinary facts. What every session
starts with aims at 2 KB, and so does each topic; lint reports more.

## Tasks

The curator's own tasks carry a marker as the first line of their notes, so they are found by
marker, never by title: `m2b:review` for the review task, `m2b:candidate` for a memory candidate,
`m2b:current` for a "Still current? ..." question about a current item, `m2b:proposals` for the
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
UTF-8) is left out of every list and named by lint until it is fixed.

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

`read_until` is the moment up to which the sessions were read. `announced_until` is when the
newest proposal was added that the task for the waiting proposals has told you of: a task you
completed or deleted comes back only for a proposal added after it. A proposal's id comes from its
session and its `quote`, your own words; `kind` is `person`, `agreement`, `commitment` or
`personal`; `day` is the day you said it, `due` the day a commitment names. `state` is `open`,
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

## Who writes what

| What | Created by | Changed by | Removed by |
|---|---|---|---|
| `inbox/` | clients, integrations, harvest (a ticked candidate, a kept proposal), the worklog | the curating machine (name, frontmatter, trailer; never the text) | ingest moves files into the archive; normalize removes conflict copies identical to their original |
| `corpus/` | ingest, the journal | the journal (appends to the month's file) | lint, only conflict copies identical to their original |
| `memory/` | ingest | ingest, refresh, the sorting step, a migration after an update, harvest (only `## Current`, from "Still current?" answers), lint (a broken link it repairs) | nobody |
| `state/core/` | the curation run; any client adds an answer to a proposal under `proposal-answers/` | the curating machine | harvest prunes settled candidates and removes the answers it settled; every curation run removes the proposals kept, dropped or expired 90 days ago or longer |
| tasks (`tasks/` with the `markdown` backend, or the Reminders list) | you, integrations, capture (a follow-up), ingest, `m2b tasks add --candidate` (a memory candidate), the curation run (review, "Still current?" questions, the task for waiting proposals) | you; the band ticks or drops a curator task; the curation run completes its review task when nothing needs you, and the task for waiting proposals when none waits | harvest and the refresh step, once a curator task is settled or its item is gone; you |
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
