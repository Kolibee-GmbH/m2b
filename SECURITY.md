# Security

In short:

- **What m2b touches.** Your notes, your task list and, with the worklog add-on, a record of when
  you work in which folder. They stay in folders you chose: the store, and `~/.config/m2b/` and
  `~/.local/state/m2b/` on each machine ([What m2b handles](#what-m2b-handles)).
- **No network connection of its own.** m2b opens none. What a curation run reads reaches a model
  through Claude Code, on your login, like the text of any session.
- **What a hostile note can do at most.** A capture written to steer the model that files it can
  put lines into your memory, create tasks in your list and move waiting captures into the archive
  with misleading notes. It cannot run another command, read outside the store or delete the
  archive ([Untrusted input](#untrusted-input)).
- **The fence is Claude Code's permission system, not a sandbox of the operating system.** A model
  step runs from an empty folder, with only the commands and store paths its step lists; m2b's
  own commands run with your rights
  ([The fence around a model step](#the-fence-around-a-model-step)).
- **Reports** go privately through the security advisory form, for the latest release
  ([Reporting a vulnerability](#reporting-a-vulnerability)).

## What m2b handles

Your notes, your task list and, with the worklog add-on, a record of when you work in which
folder. All of it stays in folders you chose: the store, `~/.config/m2b/` and `~/.local/state/m2b/`
on each machine. m2b makes no network calls of its own; the model steps go
through Claude Code like any session.

With the worklog add-on, the daily note in the store holds topics a model wrote from your prompts,
and your commit subjects. Credentials in prompts, answers and commit subjects are redacted by
pattern before the model sees them, which stays incomplete. Work that must not reach the store at
all, such as a customer's under a confidentiality agreement, can be left out by folder or by a
git remote of its repository
([docs/addons/worklog.md](docs/addons/worklog.md#leaving-work-out), with what the setting does not
cover). For that, on a machine that reads sessions (the worklog add-on on, or
`curation.read_sessions`), every session start notes the URLs of the git remotes of the folder it
starts in, without the user name or token a URL may carry, in
`~/.local/state/m2b/session-remotes/`. A note reaches neither the store nor a model, and one that
no session start renewed for 30 days is removed at the next session start on the machine.

The model runs only fenced: from an empty folder, without your settings or other plugins, with
exactly the commands and store paths its step lists, and nothing else allowed. A tool call outside
that list is denied and reported in the run's review task
([The fence around a model step](#the-fence-around-a-model-step)).

When the store folder is a git repository, a curation run starts `git` there to commit what it
changed and, before its first step, the captures in the inbox that git does not know yet
([docs/curation.md](docs/curation.md#a-commit-per-run)). git is given those files by
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
or tag characters that spell invisible ASCII, undoes the step, and the reason names the line by its
file and line number, never by its text, and no file the step added by its name. Of a failed run
the next session start says, as a notice of m2b's own, when it failed and in which steps, never
why: a reason can repeat what a model, a command or a file name said, so it stays in the run
record, where `m2b status` and the review task show it. The hooks remove these characters and
every other that draws nothing (soft hyphens, fillers, variation selectors) before the distillate
and those notices reach a session. Lines a capture adds are not flagged, because adding is
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

## The fence around a model step

A curation step that files, refreshes, sorts or lints is a headless Claude Code session,
`claude -p`, started with what its step needs and nothing more. Measured with Claude Code 2.1.322
on 2026-11-12, in a sandbox with files planted outside the store:

- Every command outside the step's list was denied, read-only ones too (`cat`, `ls`, `printenv`,
  `env`, `curl`), as was a listed command with a second one behind `;` or inside `$(...)`.
  So were reading a file outside the step's store paths, inside the store too, writing one
  outside the store or into the step's working folder, and fetching or searching the web.
- The session has only the tools its step's rules name: Bash, Read, Edit and Write for a step of
  the core. Without that list Claude Code gave the session some twenty more, and those that ask no
  permission ran: the step listed the other Claude sessions on the machine and started a subagent,
  and its call to send a session a message failed only because it was tried with a name no
  session has. Now these tools are not there.
- No MCP server is started. Without that, the connectors of your claude.ai account (mail, calendar,
  documents) were part of the step's session; the one call tried was denied.
- No `CLAUDE.md` is read and Claude Code keeps no memory for the step. Without that, every
  `CLAUDE.md` in a folder above the step's working folder was in the model's context, with the
  files under a `.claude/rules/` there; the working folder lies under your home folder, so your
  own `~/.claude/CLAUDE.md` was among them.
- A step can neither read nor change a file in the folder Claude Code keeps its own files in
  (`~/.claude`, or where `CLAUDE_CONFIG_DIR` puts it): the folder is denied by path. The two
  switches above do not do that. Claude Code allows reading and writing in the memory folder it
  keeps for a session's project without any rule, and with both switches set a step read, wrote
  and edited files there; the memory folder of another project was refused. That folder belongs
  to the step's working folder or to a git repository above it, so on a machine whose home folder
  is a git repository it is the memory of that repository: every later session started in a
  folder of the home folder that is in no repository of its own starts with it. With the deny
  rule the same calls were refused and reported.
- No transcript is kept, so what a step read from your store is not written a second time under
  `~/.claude/projects/`.

m2b does not take this on trust. Claude Code names the session's tools and MCP servers in a line
it prints before the model's first answer; a session that has more than its step's list is stopped
at that line, and the step fails with the names. A call of a tool the session does not have fails the step and is
reported like a denied call.

What the fence is not:

- It is Claude Code's permission system, not a sandbox of the operating system. The `m2b` commands
  a step may run are m2b's own code and run with your rights; a step that may run `m2b search`
  (ingest, lint, the refresh steps of `m2b curate --refresh-all`, the worklog's daily step) can
  search the whole store, whatever folders its read rules name.
- The step gets your environment, because Claude Code needs it to reach its model (a login, a
  proxy, a provider's credentials) and m2b's commands need it to find the store. The model has no
  call that reads it.
- That no `CLAUDE.md` and no memory is read rests on two switches of Claude Code
  (`CLAUDE_CODE_DISABLE_CLAUDE_MDS`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY`). A curation run does not
  check them; the tools and the MCP servers it checks at every run. `scripts/fence-probe` measures
  the switches and part of the refusals above with a real model
  ([CONTRIBUTING.md](CONTRIBUTING.md#whether-the-fence-still-holds)): a step that is asked to
  break out (`cat` of a file outside the store, alone and chained to an allowed command, Read and
  Write there and in Claude Code's memory folder, a tool the step does not have), with a random
  word in each file it must not get, beside a control run without the switches. The weekly
  workflow of this repository runs it with the newest Claude Code when it has an account for a
  model, so a Claude Code that drops a switch is seen there within a week. On your machine
  nothing sees it, and a step reads those files until a release of m2b answers it.
- The model can still do everything its step allows, which is the subject of the section above.

The step that reads your sessions has no tool at all ([Reading your sessions](#reading-your-sessions)).

## Reading your sessions

Off until you say yes in setup ([docs/curation.md](docs/curation.md#reading-your-sessions)). A
curation run then gives a model what you typed in Claude Code since the last reading, with the
folder and the day of each session: the prompts Claude Code marks as typed by you, without pasted
blocks, Claude's answers, tool results and what a plugin or another agent sent, each cut at 2,000
characters, with credentials redacted by pattern, which stays incomplete. A session you left out,
by its folder or by a git remote of its repository, does not reach it. With the prompts the model gets the distillate and, from
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
or its topic, up to 60, against a prompt. Read a proposal's text beside your words before you keep it;
`keep --all` keeps each as it is written.

## The tools the model calls

Where the mod runs, the model has two tools, `mcp__m2b__note` and `mcp__m2b__search`. They can do
what the skills' commands can: add a note to `inbox/` (with a follow-up, also a task in your task
list) and read the store through `m2b search`. A note the model writes is a capture like any other,
so text the model read elsewhere, such as a web page, can reach the inbox the way the section above
describes. A search answer goes to the model under a line saying it is data from your notes, not
instructions, with escape sequences and the invisible characters m2b knows removed (marks that
reorder text, zero-width characters, variation selectors, tag characters; the table the hooks use
for the distillate); that list cannot be complete, and a model may still follow text that looks
like an instruction. Where the tool is not offered, the `search` skill runs `m2b search` in a
shell: a hit then comes without those invisible characters too, but with its escape sequences
and without the line that marks it as data.

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
can note through the skill, and the `todos` skill runs `m2b tasks complete` without asking, so such
a model can tick an open task. Your own rules come first, those for the tools' names and those
for the skills' commands: `Bash(m2b capture:*)` in `permissions.ask` has Claude Code ask for every
note, `Bash(m2b tasks complete:*)` there has it ask before a task is ticked, and `mcp__m2b__note` together with `Bash(m2b capture:*)` in `permissions.deny` keeps the
model from noting by either way. An organization that allows only managed permission rules adds
its own rules for these names, because the mod cannot see that setting
([docs/band.md](docs/band.md#noting-and-searching-as-tools-of-the-model)).

## Reporting a vulnerability

Please do not open a public issue. Report it privately through the repository's security advisory
form ("Report a vulnerability" on the Security tab), with the steps that show it and the version
of m2b involved. You get an answer within a week. Reports are taken for the latest release: a fix
comes as a new release, and earlier versions get none.
