# Security

## What m2b handles

Your notes, your task list and, with the worklog add-on, a record of when you work in which
folder. All of it stays in folders you chose: the store, `~/.config/m2b/` and `~/.local/state/m2b/`
on each machine. m2b makes no network calls of its own; the model steps go
through Claude Code like any session.

With the worklog add-on, the daily note in the store holds topics a model wrote from your prompts,
and your commit subjects. Credentials in prompts, answers and commit subjects are redacted by
pattern before the model sees them, which stays incomplete. Work that must not reach the store at
all, such as a customer's under a confidentiality agreement, can be left out by folder
([docs/addons/worklog.md](docs/addons/worklog.md#leaving-work-out), with what the setting does not
cover).

The model runs only fenced: from an empty folder, without your settings or other plugins, with
exactly the commands and store paths its step lists, and nothing else allowed. A tool call outside
that list is denied and reported in the run's review task.

When the store folder is a git repository, a curation run starts `git` there to commit what it
changed ([docs/curation.md](docs/curation.md#a-commit-per-run)). git is given the changed files by
name and is asked for nothing that reaches a remote: m2b never pushes or fetches. For these calls
it points git's hooks folder at nothing and turns the file-system monitor off, so neither a hook
nor a monitor program of the repository runs. What does run is a filter the repository's configuration or your own names
for adding a file, as with your own `git add`. The configuration in the store's `.git` is
therefore as trusted as your own: keep the store in a repository only you write to, and
`curation.git_commit: false` in the machine config keeps m2b from starting git at all.

## Untrusted input

A capture is text from wherever it came: a share sheet, a shortcut, an integration writing into
`inbox/`, a web page someone pasted. m2b treats it as data, but the ingest step is a model that
reads it, and a capture can be written to steer that model. What such a capture can reach is what
ingest is allowed: the `m2b ingest`, `m2b search` and `m2b curate report` commands, reading the
inbox and `memory/`, and editing files in `memory/`. Two more steps read captures as evidence:
refresh, which may also read the whole archive and edit the distillate and the facts that are due,
and, with the worklog add-on, its daily step, whose output is a verdict on the day's sessions
that code checks, and a finding for the review when it cannot hand one in. So a capture cannot
run another command, read outside the store or delete the archive, but it can:

- put lines of its choosing into `memory/MEMORY.md`, the distillate every new session starts with,
  and into the fact files beside it;
- create tasks in your task list;
- move its own and other waiting captures into the archive with misleading notes.

Code checks what the step did to `memory/` against a copy taken just before it. Each facts line
ingest removed or rewrote lands in the review task, with the captures it filed and where the copy is
kept (`~/.local/state/m2b/memory-before-run/`), and it comes back in every review until you complete
the review task, in your list or with `ok` in the band; `ok` closes nothing a run added to the
review after the band drew it. A line holding characters that hide or reorder text, such as bidirectional controls
or tag characters that spell invisible ASCII, undoes the step; the hooks remove the same characters
before the distillate reaches a session. Lines a capture adds are not flagged, because adding is
what ingest is for.

The skills of the run tell the model that captured text is data: a capture that gives instructions
to whoever files it (to replace or delete facts, to write a given line or rule, to run a command)
is filed without any fact, current line, task or ref, kept in the archive as written and named in
the review task; only a follow-up the capture already carried from its capture still becomes its
task. That is a rule a model follows, not a check in code: a capture worded as an ordinary fact
("Dana moved to Lisbon") or as your own wish is filed as one, whoever wrote it.

The distillate is printed at session start under a header saying it is data from your notes, not
instructions, and it is cut at 8 KB; a model reading it is still a model and may follow text that
looks like an instruction. So:

- let only clients you trust write into `inbox/`; integrations follow the contract in
  [docs/integrations.md](docs/integrations.md) and are your choice to install;
- read `memory/MEMORY.md` now and then, or keep the store in a folder whose changes you see (a git
  repository, a backup with history);
- `m2b distillate off` keeps the distillate out of projects where it must not appear, on the
  machine you run it on.

## Reading your sessions

Off until you say yes in setup ([docs/curation.md](docs/curation.md#reading-your-sessions)). A
curation run then gives a model what you typed in Claude Code since the last reading, with the
folder and the day of each session: the prompts Claude Code marks as typed by you, without pasted
blocks, Claude's answers, tool results and what a plugin or another agent sent, each cut at 2,000
characters, with credentials redacted by pattern, which stays incomplete. A session in a folder
you left out does not reach it. With the prompts the model gets the distillate and, from
`state/core/proposals.json` in the store, up to 30 proposals you kept and 30 you dropped, each
with the words of yours it stood on; so words you typed in an earlier period go to the model again
while such a proposal is among them, until 90 days after a run settled your answer to it.

That model can call nothing: it reads its input and answers once. Code keeps a proposal only when
the words it quotes stand in a prompt of the period, and nothing is filed before you say keep. The
distillate and the proposals file lie in the store, so whoever can write the store can try to
steer that model through them. What this reaches is which proposals you are shown and their text,
which is the model's wording and is not checked against the quote. Proposals are written into the
proposals file before you answer, and a dropped one stays there for 90 days, so whoever can steer
that model can have words from any prompt it was given written into the store: a proposal's quote
can be a whole prompt of the session it names, and nothing holds its text, up to 300 characters,
or its topic against a prompt. Read a proposal's text beside your words before you keep it;
`keep --all` keeps each as it is written.

## The tools the model calls

Where the mod runs, the model has two tools, `mcp__m2b__note` and `mcp__m2b__search`. They can do
what the skills' commands can: add a note to `inbox/` (with a follow-up, also a task in your task
list) and read the store through `m2b search`. A note the model writes is a capture like any other,
so text the model read elsewhere, such as a web page, can reach the inbox the way the section above
describes. A search answer goes to the model under a line saying it is data from your notes, not
instructions, with escape sequences and the invisible characters m2b knows removed (marks that
reorder text, zero-width characters, variation selectors, tag characters); that list cannot be
complete, and a model may still follow text that looks like an instruction.

The mod lets a call of either tool run where Claude Code would only ask because no rule allows it,
as the skills run their commands without asking; then neither the classifier of auto mode nor a
`PermissionRequest` hook is asked. For the note tool this holds only for a note in your own words:
every word of it stands in one prompt you submitted in the session (typed, sent over Remote Control,
or the prompt a headless run was started with), apart from additions of up to four words in square
brackets, which together hold fewer words than the rest has different ones, and it holds no
invisible format characters. For any other note Claude Code's ask stands, so
text the model read elsewhere does not reach the inbox through the tool unseen. Two limits: text you
paste into a prompt is part of that prompt, and the check covers the tool only. The `capture` skill
still runs `m2b capture` without asking, whatever the text, so a model that follows text it read
can note through the skill. Your own rules come first, those for the tools' names and those
for the skills' commands: `Bash(m2b capture:*)` in `permissions.ask` has Claude Code ask for every
note, and `mcp__m2b__note` together with `Bash(m2b capture:*)` in `permissions.deny` keeps the
model from noting by either way. An organization that allows only managed permission rules adds
its own rules for these names, because the mod cannot see that setting
([docs/band.md](docs/band.md#noting-and-searching-as-tools-of-the-model)).

## Reporting a vulnerability

Please do not open a public issue. Report it privately through the repository's security advisory
form ("Report a vulnerability" on the Security tab), with the steps that show it and the version
of m2b involved. You get an answer within a week.
