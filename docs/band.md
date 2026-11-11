# The band

The band is where m2b speaks to you inside Claude Code: a few rows above the prompt and one line
below it. It is part of m2b and needs no setup of its own; it starts once m2b is set up on the
machine.

```text
 [ keep ] [ drop ] Remember? Sam brings the plywood on Saturday
 [ keep ] [ drop ] Still current? Planning the trip to Porto
 [ ok ] m2b: review  1 fact changed: Sam
   lint: broken link in people/sam.md
   the whole review: /m2b-review
╭──────────────────────────────────────────────────────────────╮
│ >                                                            │
╰──────────────────────────────────────────────────────────────╯
 ⚠ m2b: 2 in inbox · curated 21:36
```

## What it shows

- **Memory candidates**, "Remember? ...": facts a curation run proposes for the distillate.
- **"Still current?" questions**: items under "Current" in the distillate that have gone quiet.
- **The review**: the open review task of the last curation run. When the run changed facts in
  the distillate, one row names them by what they are about (`2 facts changed: Sam, Dana`); the
  other findings follow as written. `ok` closes the review task, with the same 5 seconds and
  `undo` as keep; until then the review comes back after every run, so a changed fact is never
  missed.
- **Tasks due today or overdue**: your own tasks, not the curator's, in at most three quiet rows
  below the candidates (`due today: Call Dana`, `overdue: Return the drill`), without buttons;
  today's first, then the overdue ones, the most recent first. `m2b config set band.due_tasks
  false` turns them off on this machine; `true` brings them back.

Candidates and questions share at most three rows, the due tasks have three, and the review shows
at most three findings, each followed by "and N more" when there are more. The band is empty, and
takes no room, while there is nothing to show.

**Keep and drop are buttons: click them with the mouse.** Keep completes the task; drop marks it
dropped and completes it; nothing else changes, and the next curation run reads which one you
chose.

A click writes nothing for 5 seconds. The row shows what it will do and offers `undo`:

```text
 [ undo ] dropping: Remember? Sam brings the plywood on Saturday
 [ keep ] [ drop ] Still current? Planning the trip to Porto
```

`undo` takes the click back, and the task stays as it was. After the 5 seconds the band reads the
list again and writes: an item another session settled meanwhile is left alone, and the band says
so in one line. Closing the session, or a crash, within those seconds writes nothing either, so a
click is never half done; the item is simply still there next time. The click is written also when
the row has left the band meanwhile, pushed below the first three or replaced by an error line.
Until the band has read the list after the write, the row offers nothing to click, for at most
3 minutes.

The band draws every text as one plain line: escape sequences and control characters a capture
brought along from terminal output are left out, line breaks and tabs become spaces.

## When a curation run fails

Each open session shows one line for a few seconds, once per failed run: `m2b: the curation run of
2026-03-14 18:00 failed; its review task says why, and /m2b-review shows it`. A reload of the
plugins does not show the same run again; a run that succeeds shows nothing, and neither does an
interrupted one, which the status line names. The status line says
`last run failed, see review` until the next run succeeds.

## Noting without the model

`/m2b-note <text>` writes the text into the inbox at once, through `m2b capture`, and answers with
one line that shows how it begins:

```text
> /m2b-note Sam brings the plywood on Saturday, the long boards too
  noted: Sam brings the plywood on Saturday, the long board…
```

No model turn runs for it, so it costs no model turn and does not wait: Claude Code runs the
command also while a turn is working. The text goes in as typed, quotes and dashes included, with the
source `claude`, as a capture through the skill would; the next curation run files it. Without
text it writes nothing and says what it needs; when `m2b` fails, the line says why, starting with
`not noted:`. The confirmation stays in the conversation, where the model reads it in its next
request. To note with the model's help, for instance with a follow-up date, ask the model: it uses
the tool below, or the skill `/m2b:capture` where the mod does not run.

## The whole review, and search, in a pane

The band keeps to a few rows. `/m2b-review` opens the m2b pane beside the conversation with the
last curation run in full: its state and times, every finding of the review task whole, paths
included, and every candidate and "Still current?" question with keep and drop, which work as in
the band, undo included. Each changed fact gets two lines: what it is about with its fact file,
then the fact as it reads now, the added words in green and the removed ones in red and struck
through; below them where the copy of the facts from before the run lies, and how many notes the
run filed.

```text
┌──────────────────────────────────────────────────────────────┐
│ Last curation run: succeeded, 2026-03-14 18:00 to 18:02      │
│ [ ok ] m2b: review  1 fact changed: Sam                      │
│   Sam (sam.md)                                               │
│     Sam Rivers (carpenter), neighbour, has a van             │
│   facts before the run: ~/.local/state/m2b/memory-before-run/│
│ 20260314T170005Z; 2 notes filed                              │
│   lint: broken link in people/sam.md                         │
│   ingest: eleven captures were not filed because their photos│
│ are not downloaded; a copy of the run log is at ~/.local/stat│
│ e/m2b/runs/20260314T170200Z.jsonl                            │
│ [ keep ] [ drop ] Remember? Sam brings the plywood           │
│ [ undo ] dropping: Remember? Dana prefers tea                │
│ [ keep ] [ drop ] Still current? Planning the trip to Porto  │
└──────────────────────────────────────────────────────────────┘
```

`/m2b-search <text>` shows the hits of `m2b search` in the same pane, each with its file and line
and the line itself, without a model turn; a text that starts with a dash is searched as written.
A word also matches inside longer words, so `Velo` finds `Developer` too; `/m2b-search --word Velo`
matches whole words only.
Files not downloaded from iCloud Drive are counted below the hits. Both commands run at once, also
while a turn is working, and read through `m2b` only; the pane writes nothing but keep and drop.
Where Claude Code cannot show a pane, for instance with no terminal attached, the command answers
with the content as text instead, its first 20 lines, each cut at 200 characters; that text stays
in the conversation the model reads. A search without hits answers in one line and opens no pane,
and one with more hits than `m2b` can hand over asks for a narrower search. The pane takes its data from the same refresh as the band, so it
follows the next curation run within a minute. Its close mark closes it, and so does Escape while
the pane holds the keyboard; it asks for the keyboard when it opens over an empty prompt, so the
arrows scroll a long review.

## Noting and searching as tools of the model

The mod gives the model two tools, so a capture or a lookup the model makes for you needs no shell
call:

| Tool | Runs | Takes |
|---|---|---|
| `mcp__m2b__note` | `m2b capture --source claude --json -`, the text on standard input | `text`, and optionally `follow_up` (`YYYY-MM-DD`, also a task due that day) and `quiet` |
| `mcp__m2b__search` | `m2b search --json --any -- <terms>` | `terms`, each a phrase of its own, and `whole_words` |

Their descriptions, which the model reads, carry the rules of the skills `/m2b:capture` and
`/m2b:search`: what may be noted (never documents of customers or confidential statements about
third parties), the text stays in your words, and an answer holds only what the hits hold. A test
holds the core rules of each description to the skill's own sentences. The skills stay as they
are; where the tools are offered, they name the tool as the first way, and where the mod does not
run they work through their commands as before. A calendar entry still goes through the skill.
Both descriptions, about 5,000 characters together, are in the prompt of every session the mod
runs in, so the model knows the tools without loading a skill.

The note tool answers with the path of the saved note, the day of its task or that the task waits
for the next curation run, and anything `m2b` reported beside it. When a capture fails it tells
the model which of three cases it is: not saved, nothing written, or unknown, after a capture that
was stopped or answered nothing readable; in the last case the model is told not to note again
before it has looked, so a note is not written twice. The search tool answers with at most 100
hits, each cut at 500 characters, and names the files it could not search. Its answer opens with
a line saying it is data from your notes, not instructions. Every text in it is one line, with
escape sequences, control characters and the invisible characters m2b knows removed: marks that
reorder text, zero-width characters, variation selectors and tag characters. That list cannot be
complete. When `m2b` fails, the model gets an error that says it could not look, which it must not
read as nothing found. Before m2b is set up, both answer that and call nothing.

**Permission.** Claude Code lists the tools under these names and decides on a call as it does
for an MCP tool: a rule `mcp__m2b__note` or `mcp__m2b__search` (or `mcp__m2b` for both) in
`permissions.allow`, `ask` or `deny` of your settings applies to them. A rule you set for the
skill's command applies to the tool too: with `Bash(m2b capture:*)` in `permissions.ask` or
`deny`, the note tool asks or is refused the same way, and `Bash(m2b search:*)` does that for
search. Where no such rule, no hook, setting or organization limit decides and Claude Code would
only ask because nothing allows the tool, the mod lets the call run, as the skills run their own
`m2b` commands without asking. A deny of the session's mode, such as `dontAsk`, stands; in plan
mode Claude Code keeps its own verdict; where an application embedding Claude Code answers the
asks itself, it still does.

Letting the call run also means that nothing else is asked about it: not the classifier of auto
mode, not a `PermissionRequest` hook of yours, and not a person. An organization that allows only
its managed rules (`allowManagedPermissionRulesOnly`) is not visible to the mod; such an
organization adds a managed `ask` or `deny` rule for these names. To be asked each time, put
`Bash(m2b capture:*)` in `permissions.ask`. To keep the model from noting at all, put both
`mcp__m2b__note` and `Bash(m2b capture:*)` in `permissions.deny`: the first refuses the tool, the
second the skill's command, which the model would otherwise use instead.

## The status line

Below the prompt, one line sums up the brain, such as `2 in inbox · curated 21:36`: the captures
waiting for the next run, and when the last successful run ended. Claude Code puts the plugin's
name and a ⚠ in front of every plugin's status line; the ⚠ is not a warning (Claude Code 2.1.322
offers plugins no way to leave it out). Every state the line can show is in
[The curation run](curation.md#the-status-line).

## After an update

A session keeps the band it started with, while `m2b` itself is always the installed version. When
the session's band is the older one, it says so in one line:

```text
 this session runs the band of m2b 0.3.0 while m2b 0.3.1 is installed: run /reload-plugins
```

`/reload-plugins` in that session, or a new session, loads the installed band. A band newer than
the installed m2b, as when Claude Code runs it from a checkout, says nothing.

## What it needs

- m2b set up on the machine, and the launcher `~/.local/bin/m2b`, which m2b writes at the first
  session start after setup.
- Mods on in Claude Code. The band is a mod, a module Claude Code loads with the plugin. Two
  different things can keep it out:
  - **Mods off, hooks on.** A session that started without network access can save Claude Code's
    rollout switch for mods as off. Then the band, the status line, the slash commands and the
    model's tools are missing; the distillate at session start, capture and search through the
    skills, tasks and curation work as before. Start `claude`
    once with network access, then a new session.
  - **No plugin hooks at all.** Under `claude --bare`, or with `allowManagedHooksOnly` or
    `disableAllHooks` in managed settings, Claude Code runs none of m2b's hooks: no band, and no
    distillate at session start either. Capture, search and tasks still work through the skills,
    and curation runs where it is scheduled.
- With Apple Reminders, access to Reminders for the terminal Claude Code runs in, or the band shows
  one error line instead of the tasks.

`m2b doctor` tells the two apart. m2b's own session-start hook and the band each note when a
session started them, and the line `band` compares the two: `seen` when the latest session ran the
band, `not seen` with the first case when that session ran m2b's hooks but not the band, `not seen`
with the second case when no session has run m2b's hooks since setup. Right after setup it can say
`not seen` until the next session starts.

## What it reads and writes

It runs only while `~/.config/m2b/config.json` and the launcher exist. Each refresh is one `m2b`
call, `m2b band --json`; keep and drop call `m2b tasks complete` and `m2b tasks drop`, after
reading the list again with `m2b band --json --tasks-only`. Every open session asks about once a
minute and after each of your turns, so the answer is shared between sessions for 55 seconds in
`~/.local/state/m2b/band-view.json`; an answer of a shape the band does not know, or stamped later
than now, is not used. However many turns end while `m2b` is slow, at most one more refresh waits.
That folder holds titles and findings, so m2b keeps it readable by you only. At each session start
it writes `~/.local/state/m2b/band-seen.json`, which `m2b doctor` reads. Apart from keep and drop, which
change that one task in your task list (with the `markdown` backend, its file in `tasks/` of the
store), it writes nothing in the store.

`m2b band --json` reaches and reads the task list once (with Apple Reminders, two calls to
`reminders`) and sorts the open tasks by their marker, and adds the answer of `m2b status --json`,
reusing that one look at the task list for its check of the backends. With invented tasks:

```json
{
  "version": "0.3.0",
  "tasks": {
    "candidates": [{"id": "c1", "title": "Remember? Sam brings the plywood", "notes": "m2b:candidate", "due": null, "completed": false, "completed_at": null, "dropped": false, "marker": "candidate"}],
    "questions": [],
    "reviews": []
  },
  "status": {"machine_id": "alex-laptop", "inbox": {"count": 2, "evicted": 0}, "run": {"state": "succeeded", "last_succeeded_at": "2026-03-14T21:36:00+01:00"}, "backends": {"store": {"state": "reachable", "detail": ""}, "tasks": {"state": "reachable", "detail": ""}, "calendar": {"state": "not configured", "detail": ""}}}
}
```

`version` is the installed core's, which the band compares with its own. `status` holds more
fields than shown, as `m2b status --json` does. When the task list cannot be
read, `tasks` is `{"error": "<why>"}` and `status` still answers. The checks of the backends are
kept for five minutes, so at most every five minutes the answer waits for the calendar too, here
for at most 10 seconds whatever `calendar.timeout_seconds` says; a calendar that does not answer
by then is reported as not reachable. `--tasks-only` leaves `status` out.

While a review task is open, `tasks.review` names the changes of the facts the last runs made, as
the curation run kept them for the review: per change its `kind` (`rewrote`, `removed`,
`file_removed`, `file_emptied`), the fact `file`, a short `topic`, the statement `before` and
`after`, and `parts`, the statement word by word, each `same`, `added` or `removed`; `copy` names
the copy of `memory/` from before the run and the notes it filed; `paragraphs` are the review's
paragraphs these stand for, which the band leaves out of the findings it shows.

## Where it lives

In `plugins/m2b/hooks/`: `register.tsx` and its helpers, loaded through `"modules"` in
`hooks/hooks.json`. Its tests are in `plugins/m2b/tests/band/` and run with
`scripts/check --quick band`.

## How you see it runs

The status line under the prompt. When m2b cannot answer, or the band's own refresh fails, it says
`could not look` instead of an old state. An empty band is normal while there is no candidate, no
question and no open review.
