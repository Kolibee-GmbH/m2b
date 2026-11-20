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
  archive, and a symlink someone puts into the store is not followed
  ([Untrusted input](#untrusted-input)).
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

What goes into the store is yours to decide, also from work: a session keeps what you ask it to,
a customer's document or what someone told you in confidence among it. A file you name with its
path goes in on your yes to Claude Code's question (`m2b capture-file`, which no skill runs without
asking), unless a rule of yours such as `Bash(m2b:*)` or a permission mode that asks nothing
(auto, `bypassPermissions`) lets the call through; then the skill's rule, to copy only a file you
named, is all that stands before it. A document in the store lies in the folder that syncs to
every machine and through the sync service; its copy and its note stay in the archive, and a curation run's model,
through Claude Code on your login, reads it up to its 60th page to file facts from it. A press on
`open the file` in the pane opens a PDF or a picture of the archive in the system's viewer, and
nothing else: a page or a script someone sent is named with its path and never started.

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
name. m2b also starts git to read the remotes of the folders your sessions start in and, with the
worklog add-on, your commits there. Every git it starts is started the same way, with settings
that win over the repository's configuration and your own: the hooks folder points at nothing,
the file-system monitor is off, no signature is checked, every transport is closed and objects a
partial clone lacks are not fetched. So no hook, no monitor and no signature program that a
repository names runs, nothing reaches a remote, and no command a remote names for fetching
runs. m2b never pushes or fetches, and a store that is a partial clone is not committed into.

What does run, in the commit of a run alone, is a filter the repository's configuration or your
own names for adding a file, as with your own `git add`. The configuration of the store's
repository is therefore as trusted as your own, and where it lies decides who can write it:

- A `.git` folder in the store folder lies where everything that writes the store can write it,
  a sync service with what another device sent included: its configuration, and what it says
  about where its objects and branches are kept. Keep such a store in a folder only you write to.
- A `.git` file that points at a git directory outside the store folder
  (`git init --separate-git-dir`) keeps that configuration on this machine. The file itself is
  still in the store and can be rewritten there, to point at another repository of yours or at a
  folder made for the purpose. So m2b reads the file itself, without git, and a run commits only
  into the directory this machine's config names (`curation.git_directory`), which must lie
  outside the store folder, with no link of the store on the way to it. When the file
  points anywhere else, or the config names no directory, the run commits nothing, starts no git
  for a commit, and says so in its review task and in `m2b doctor`.

`curation.git_commit: false` in the machine config keeps a run from starting git at all.

## Untrusted input

A capture is text, or a file, from wherever it came: a share sheet, a shortcut, an integration
writing into `inbox/`, a web page someone pasted, a PDF someone sent you. m2b treats it as data, but the ingest step is a model that
reads it, and a capture can be written to steer that model. What such a capture can reach is what
ingest is allowed: the `m2b ingest`, `m2b search` and `m2b curate report` commands, reading the
inbox and `memory/`, and editing files in `memory/`. Two more steps read captures as evidence:
refresh, which may also read the whole archive and edit the distillate and the facts that are due,
and, with the worklog add-on, its daily step, whose output is a verdict on the day's sessions
that code checks, and a finding for the review when it cannot hand one in. Outside the store,
that step reads only two files of its own, in the worklog's run folder: the period's facts and
the draft of its verdict. So a capture cannot run another command, read anything else outside
the store or delete the archive, but it can:

- put lines of its choosing into `memory/MEMORY.md`, the distillate every new session starts with,
  and into the fact files beside it;
- create tasks in your task list;
- move its own and other waiting captures into the archive with misleading notes.

Reading outside the store stays out of reach for whoever can put a file there, too: an
integration, another device, a sync service. Below the store's folder m2b follows no symlink,
whatever it points at. Its commands and hooks neither list nor read one and write through no
folder that is one, so a symlink in `inbox/` is never filed and one in the place of
`memory/MEMORY.md` is never printed at a session start; lint names each symlink in the review task
until you remove it; like every listing, lint passes over hidden names and folders that are not
downloaded. A step's own Read of a symlink that leads out of the store paths its rules
name is refused by Claude Code (measured with Claude Code 2.1.325 on 2026-11-14;
[the fence](#the-fence-around-a-model-step) says what asks it again). A read opens a file so that
a symlink put in its place in that moment is not followed either; a write checks the folders on
the way just before it writes. With the worklog add-on, its reading of the inbox and the note it
writes there keep the same rule; its own state files in `state/addons/worklog/` it opens by their
path.

Code checks what the step did to `memory/` against a copy taken just before it. Each facts line
ingest removed or rewrote lands in the review task, with the captures it filed and where the copy is
kept (`~/.local/state/m2b/memory-before-run/`), and it comes back in every review until you complete
the review task, in your list or with `ok` in the m2b pane; `ok` closes nothing a run added to the
review after the pane drew it. A line holding characters that hide or reorder text, such as bidirectional controls
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

The tests contain hostile samples on purpose, to check the defences of m2b this section
describes. In `tests/unit/` and in the band's tests they are lines with characters that hide or
reorder text, text in characters that draw nothing and lines worded as instructions; the scenario
`tests/e2e/E17-planted-capture` ([CONTRIBUTING.md](CONTRIBUTING.md#end-to-end-scenarios)) sends
captures written to steer the model through a curation run. Whether a model keeps the rule of
the skills only that scenario's model level shows, with a real model. Of these tests only the
band's lie in the plugin's folder, which an install copies (`plugins/m2b/tests/band/`, where
Claude Code looks for them), so a static scanner run over the repository reports the samples,
and run over an installed copy those of the band's tests.

## The fence around a model step

A curation step that files, refreshes, sorts or lints is a headless Claude Code session,
`claude -p`, started with what its step needs and nothing more. Measured with Claude Code 2.1.322
on 2026-11-12, in a sandbox with files planted outside the store:

- Every command outside the step's list was denied, read-only ones too (`cat`, `ls`, `printenv`,
  `env`, `curl`), as was a listed command with a second one behind `;` or inside `$(...)`.
  So were reading a file outside the step's store paths, inside the store too, writing one
  outside the store or into the step's working folder, and fetching or searching the web. Reading
  a symlink in the inbox, a path the step may read, was denied when it points at a file outside
  the store (Claude Code 2.1.325, 2026-11-14).
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
  Write there and in Claude Code's memory folder, Read of a symlink in the inbox that points
  there, a tool the step does not have), with a random
  word in each file it must not get, beside a control run without the switches. The weekly
  workflow of this repository runs it with the newest Claude Code when it has an account for a
  model, so a Claude Code that drops a switch is seen there within a week. On your machine
  nothing sees it, and a step reads those files until a release of m2b answers it.
- The model can still do everything its step allows, which is the subject of the section above.

The step that reads your sessions has no tool at all ([Reading your sessions](#reading-your-sessions)).

## Reading your sessions

Off until you say yes in setup or turn `curation.read_sessions` on yourself, with
`m2b settings set` or with its switch in the m2b pane
([docs/curation.md](docs/curation.md#reading-your-sessions)). Unlike handing in, this setting is
not refused inside a Claude Code session: a session that may run `m2b` can turn it on. A
curation run then gives a model what you typed in Claude Code since the last reading, with the
folder and the day of each session: the prompts Claude Code marks as typed by you, with what you
pasted into them kept apart from what you typed, and beside each prompt the text of Claude's
answers up to your next one, without Claude's thinking, tool calls, tool results and what a plugin
or another agent sent, each prompt and each answer cut at 2,000 characters, with credentials
redacted by pattern, which stays incomplete. Pasted text may be anyone's words: a mail, a
document, an agent's answer; Claude's answers repeat what it read, a mail or a web page among it. A session you left out,
by its folder or by a git remote of its repository, does not reach it. With the prompts the model gets the distillate and, from
`state/core/proposals.json` in the store, up to 30 proposals of a reading you kept, 30 you dropped and
30 that wait, none a session handed in, each with the words it stood on, typed, pasted or Claude's;
so words of an earlier period go to the model again while such a proposal waits or until 90 days
after a run settled your answer to it.

That model can call nothing: it reads its input and answers once. Code keeps a proposal of a
reading only when the words it quotes stand in a prompt of the period, and nothing is filed before
you say keep. The
distillate and the proposals file lie in the store, so whoever can write the store can try to
steer that model through them, and so can whoever wrote a mail, a page or an agent's answer you
pasted into a prompt. What this reaches is which proposals you are shown and their text,
which is the model's wording and is not checked against the quote. Proposals are written into the
proposals file before you answer, and a dropped one stays there for 90 days, so whoever can steer
that model can have words from any prompt it was given written into the store: a proposal's quote
can be a whole prompt of the session it names, and nothing holds its text, up to 300 characters,
or its topic, up to 60, against a prompt. A proposal whose quote stands in pasted text says
`pasted on` where the others say `said on`; code finds that, the model is not asked. The line
names where the quote stands, not who led the model to the proposal: pasted text can lead it to a
proposal whose text is its own and whose quote is three words you typed, and that one says
`said on`. Read every proposal's text beside the words it stands on before you keep it;
`keep --all` keeps each as it is written. Pasted text is also where a config file or a log with a
credential most likely stands: the same patterns run over it, which stays incomplete, and a value
that begins a paste right after a name you typed goes like one typed whole.

## What a session hands in

Off until you turn it on yourself: with `m2b config set sessions.propose true` typed in a terminal
outside Claude Code, or with a press on the setting's `on` in the m2b pane
([docs/band.md](docs/band.md#handing-in-a-proposal-a-tool-you-turn-on)). Setup never writes the
setting, and the command does not turn it on where `CLAUDECODE` is set, as Claude Code sets it
for every command of a session's shell. That is a threshold, not a boundary: a session that may
run any command can write the config file, or run the command with that variable set empty.

The press in the pane is the one call of the band that sets the variable empty. It rests on the
way a press arrives: no tool of Claude Code hands the band a press. A press arrives as input on a
client that draws the session, and a model whose tools steer that input presses as you do
(below). The band then starts `m2b settings set sessions.propose true` itself; no permission
rule of yours is asked or used for it. The band does that for this one call and no other, after
the five seconds in which `undo` takes the press back. Claude Code does not say who pressed: a
press carries no mark of a person, as a prompt you typed at the terminal does. The setting's `on`
is a button where the client that draws it names itself the terminal, the desktop app or VS Code;
where it names itself the mobile app, or anything else, `on` is text and the setting names the
command to type. That name is the client's
own word: it keeps a tap in the mobile app from turning the setting on, and nothing more. So the
threshold for the press lies in the band, and it holds as far as the band and those clients are
what runs:

- Another plugin you installed can start the same command with an empty `CLAUDECODE` itself, with
  the pane or without it, and could also change what a press says, what the pane draws and the
  command the band starts. That holds without the press as well: the refusal goes by a variable,
  and a command a plugin starts carries the value that plugin gives it. A plugin with code of its
  own runs as you.
- Whatever attaches to the session as a client presses as you do. A client over Remote Control
  passes where it names itself the terminal, the desktop app or VS Code; what name the web
  client gives itself, m2b does not know. The desktop app and VS Code can also draw a session
  that runs on another machine. A process that runs as you needs no press: it can run the
  command outside Claude Code itself.
- Whatever types into your terminal or steers your screen can open the settings and press as you
  do, and that includes the model of a session, this one or another, with a tool for it: computer
  use, a browser on a page of Remote Control where that page offers the button, a shell that
  sends keys to a terminal multiplexer.
  A model that steers the keyboard could type the command into a terminal of your own as well. A
  model that can only click could not: for it the press is a lower threshold than the command.

What shows a press you did not make: while it waits, every client that draws the settings shows
it with `undo`, whichever client it was made on, and for those five seconds it can be taken back
there. Afterwards the setting marks `● on` as its value, and `m2b settings` says `on`.

With it on, the agent of a session can hand in a proposal by itself: a kind, a text it worded, and
the words that text stands on. The words can be yours, or stand in what the agent read for its
task: a file, a mail a connector returned, a web page, the output of a command. So a quote from
somebody else's text lies in the store's state and syncs with it, with the session's id, the name
of the tool and the time of the call: first as a file under `state/core/handed-in/`, and in
`state/core/proposals.json` once a curation run took it in. Nothing is filed into memory before
you say keep.

What code holds, at the call, on the machine the session runs on:

- The quote stands as whole words in one text of that session's transcript: what you typed, what
  you pasted, what a tool returned or what Claude answered. The input of a call, a subagent's
  conversation, what the model thought, a prompt without the mark of a person and a result that
  gives the memory back are no such text.
- The proposal says which of the four it is, the first that holds the quote in that order, and
  for a tool's result the tool.
- A session that worked in a folder or a repository you leave out hands nothing in, and neither
  does one whose calls name a path in such a folder.
- A credential in or around the quote, as far as the redaction's patterns reach, refuses the
  proposal. That net has holes, here as everywhere.
- No more than ten proposals of one session wait for a run, and a run takes no more than ten of
  one session. That bounds what comes between two runs, not the list: after each run the same
  session can hand in ten more, and nothing limits the number of sessions.

What it does not hold:

- That the words carry the text. A document can lead an agent to a proposal with a text of the
  document's choosing over three words you typed, and that proposal says `said on`. Every
  proposal a session handed in says so in its heading; read its text beside its words before you
  keep it. `m2b proposals keep --all` and the pane's `keep all` leave such proposals: you answer
  each by its id or with its own row. Where Claude Code cannot show a pane, `/m2b-proposals`
  answers as text in the conversation, so a model then reads the texts of the waiting proposals,
  an agent's wording among them, beside the command that keeps one.
- Which wording waits. A proposal with the words or the text of one that waits is not added. Where
  a session's proposal is there first, a reading's proposal for the same words does not come, and
  dropping the session's keeps both away for 90 days. Within one run the reading comes first.
- What a session read without a path. The rule of the folders covers what a call names by a path;
  what came through a connector, the web or a command that names no such path is covered only by
  the rule in the tool's description (from work only who is who, which role, what was agreed) and
  by your answer. A path hidden in a variable is not seen.
- Who called. `m2b proposals add` can be called from a shell by an agent you allowed
  `Bash(m2b:*)`, and such a call can name any session of this machine: a text of the caller's
  choosing over words that stand in another session. That is less than the same permission gives
  already, because with it `m2b capture` writes a note that is filed with no keep or drop.
- What another machine found. The curation run that takes a file in may run on another machine
  and reads no transcript. It checks the form again; where the words stand is what the machine
  that handed in found. Whoever can write the store can write such a file, as they can write into
  `memory/` with no proposal at all.

A call runs without a permission question, in a headless session too, so a session you started to
work through other people's text hands in without you seeing the call; your rule for the tool's
name or for `Bash(m2b proposals:*)` comes first. A line planted in a file gives a proposal in each
session that reads it, and a run adds a proposal with the same text once.

A store that is a git repository keeps every proposal a run committed in its history, a dropped
one too, beyond the 90 days the proposals file remembers it. That holds for the proposals of a
reading as well.

## The tools the model calls

Where the mod runs, the model has two tools, `mcp__m2b__note` and `mcp__m2b__search`, and where
you turned handing in on a third, `mcp__m2b__propose` (above). The first two can do
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

With a source in place of search terms, the search tool reads one fact file or one note of the
archive whole through `m2b source`, under the same line and with the same characters removed. It
takes a file name and never a path, and refuses before it lists or reads anything a name that
holds a separator or a line break, or that is neither a note's name nor the name of a fact file;
the distillate itself is refused too. So the name a model chooses, after whatever it read, reaches
only what `m2b search` reads anyway, apart from the inbox, and never the machine config, the
state or the tasks. A file that is only in the cloud is named with the command that fetches it,
and a symlink is not followed. The document behind a note is not read by the tool or the skill;
the session gets the note and its outline.

The mod lets a call of any of these tools run where Claude Code would only ask because no rule allows it,
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
