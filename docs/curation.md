# The curation run

A curation run files the inbox. It runs on one machine per store, the curating machine that
`store.json` names, and nowhere else.

## When it runs

At session start on the curating machine, in the background, when a run is due: the inbox holds
a capture, or the last successful run is more than 20 hours old. So after a capture the next
session start files it. After a failed run the next attempt waits 1 hour, then 4, then 20; a run
in which only a step failed that does not fail the run ([The steps](#the-steps)) counts as
succeeded and starts no wait. A
schedule can start it too, for days without a session ([On a schedule](#on-a-schedule)), and
`m2b curate --force` starts it now; add `--detach` to get your terminal back while it runs.
Started in front of you it answers in two lines: how the run ended, and what it did to the inbox,
such as `inbox: 3 captures filed, 0 waiting`, with a pointer to the review task when a run that
ended well left something there for you.
With `--detach` it answers at once, in one line, whether a run started and, where none did, why.
`--json` beside `--detach` gives that answer as data and exits 0: `message` is the line, and
`kind` is `started`, `running` (a run is under way on this machine), `not-curating` (another
machine curates the store), `not-downloaded` (`store.json` is not on this machine) or, without
`--force`, `paused` or `not-due`.
In a session, the button `curate now` in the m2b pane starts a run in the background on the
curating machine ([The band](band.md#this-session-what-waits-and-today-in-the-pane)).
There a run also starts by itself once you have answered every proposal that waits and kept at
least one, so what you kept is filed without a second step
([Your answer](#reading-your-sessions)). The band asks for it with
`m2b curate --detach --after-answers`, which starts a run where no proposal waits for its answer
any more and a keep waits for a run, whatever the inbox holds and whenever the last run was. It
decides that from the store, so an answer from another session or machine counts like the
caller's. Where it starts none, `kind` is `off` (`curation.run_after_answers` is `false` on this
machine), `paused`, `proposals-wait` (a proposal still waits for its answer), `nothing-kept`
(drops alone, which change nothing a session sees), or `running`, `not-curating` and
`not-downloaded` as above. It goes with `--detach` alone.
On a machine you paused, a run starts only when you ask for one, with `--force`, `--refresh-all`
or `--sort-facts`, or with `curate now` ([Pausing](#pausing)).

## The steps

```mermaid
flowchart LR
  pre[Preflight] --> migrate[Migrate] --> harvest[Harvest] --> glean[Glean] --> before[before_ingest] --> ingest[Ingest] --> afteri[after_ingest] --> refresh[Refresh] --> sort[Sort] --> lint[Lint] --> journal[Journal] --> after[after_journal] --> proposals[Proposals task] --> review[Review task] --> commit[Commit]
```

| Step | Done by | What it does |
|---|---|---|
| Preflight | code | removes leftover temp files, downloads the files the run reads, loads the profile |
| Migrate | code, only when the store's format is older than this m2b | brings `memory/` up to the rules of this m2b, one format at a time, each checked in code; a failing one puts `memory/` back, keeps the format and ends the run with the review |
| Harvest | code | settles the memory candidates, the "Still current? ..." and "Still needed? ..." questions you ticked or dropped, and the proposals you kept or dropped; writes the lessons you kept into `memory/lessons/` and keeps the fixes |
| Glean | code and up to three model calls without tools, only with `curation.read_sessions` | reads what you typed in Claude Code since the last reading and keeps what the model proposes for your memory ([Reading your sessions](#reading-your-sessions)) |
| Ingest | model, only with captures in the inbox | files facts and what is going on into memory, under its topic what concerns one subject only, tasks into your list, each capture into `corpus/YYYY/MM/`; reads a PDF whole up to its 60th page and writes what stands on which page into the note beside it ([A document in the inbox](#a-document-in-the-inbox)) |
| Refresh | model, only when a fact is past its day | rewrites the facts whose `until` has passed |
| Sort | model, only with `m2b curate --sort-facts` | moves facts lines of an older distillate into topics; code puts the file back if a statement changed |
| Lint | code; the model only to repair a broken memory link with exactly one candidate | moves a current item above the topics that names exactly one topic under it, then checks names, links, conflict copies and the distillate's size |
| Journal | code | adds the tasks you completed to the month's `corpus/YYYY/MM/YYYYMM-done.md` |
| Proposals task | code | takes in what sessions handed in ([What a session hands in](#what-a-session-hands-in)), lets unanswered proposals expire, and keeps one task in your list while proposals wait for your answer, completed once none waits |
| Review task | code | one task in your list when something needs you |
| Commit | code, only when the store folder is a git repository | one git commit of what changed in the store while the run ran, and before the first step one of the captures git does not know yet ([A commit per run](#a-commit-per-run)) |

`before_ingest`, `after_ingest` and `after_journal` are where an add-on can hook in; the worklog
runs before ingest. A step that fails is reported in the review task and the run goes on. When
only an add-on's step, the reading of the sessions, the proposals task or the commit failed, the
run still counts as succeeded: the inbox is filed and the next run is due at the usual time, so neither an
add-on that keeps failing nor a transcript m2b cannot read holds back the core.

Each model step runs fenced: `claude -p` from an empty folder, with `--setting-sources project`,
m2b alone as plugin, `--permission-mode dontAsk`, and allowed only the commands and paths of its
step. Its session has only the tools those rules name and no MCP server, reads no `CLAUDE.md`,
yours included, keeps no transcript and can neither read nor change a file in Claude Code's own
folder; a session that starts with more is stopped, and the step
fails ([SECURITY.md](../SECURITY.md#the-fence-around-a-model-step) says what was measured). It uses `curation.model` (`haiku` by default) and stops after `curation.max_turns` tool
calls or `curation.model_timeout_minutes`. The reading of the sessions asks the same model in
another form: the instruction as the prompt, the text on standard input, no tool at all and one
turn, so whatever a prompt says, the model can call nothing.

After each model step that may edit `memory/`, code compares it with a copy taken just before the
step:

- **No step** may add, change or remove a file under `memory/lessons/`: a lesson reaches every
  session as a correction you kept, and a model step reads captures, which can claim to be one. Such
  a change puts `memory/` back and fails the step.
- **Refresh** may change only the facts that are due: their fact files and their lines in
  `MEMORY.md`. Any other change puts `memory/` back and fails the step.
- **Ingest and lint** keep their edits. Each facts line they removed or rewrote, and each fact file
  they emptied or removed, is listed in the review task, and again in every later review until you
  complete the task, in your task list or with `ok` in [the m2b pane](band.md), where `/m2b-review`
  shows each change with the added and removed words marked. `memory/` as it was before the run is
  kept in
  `~/.local/state/m2b/memory-before-run/<time of the run>/` as long as such a finding names it, so a
  line can be copied back from there.
- **Any model step**, sorting included, that writes a line holding characters that hide or reorder
  text (bidirectional controls, zero-width spaces, tag characters) is undone and fails; a capture
  still in the inbox is marked so the next run files its facts again. The failure names the file,
  the line number and the characters, not the line's text, and not a file the step added. The
  session-start and prompt hooks
  remove these characters and every other that draws nothing (soft hyphens, fillers, variation
  selectors) before the distillate reaches a session.

## A document in the inbox

A file that is no text note, dropped into `inbox/` (from the Finder, or synced from a phone),
becomes a bundle at the next run: the file under the name the store gives it, a note beside it
that names the original file name, and a JPEG copy of a HEIC picture. A file a session copied in
with `m2b capture-file` ([Capture](using.md#capture)) is such a bundle from the start, with your
words in its note. Where that note has reached the curating machine and its file has not synced
there yet, the run leaves the note in the inbox and reports it; the first run that finds the file
beside it files both. The ingest step reads the bundle and
files its facts like those of any capture. A PDF of more than one page is read whole up to its
60th page, and its note gets an outline, one line per page or run of pages, with the names, numbers
and days that stand there:

```text
original name: club-handbook.pdf
pp. 4-5: fees 240 full and 160 weekend, due 31 January, locker 30 more; Alex Example locker 37
pp. 6-9: the boathouse: opening hours, boat bays A B C, cleaning, repairs by Sam on Tuesdays
outline: pages 1-60 of 75
filed: facts alex.md, rowing-club.md
```

`m2b search` finds a word of the outline as of any note, so what did not become a fact is still
found, with the note that leads to the file. A session reads the note with its outline when a
question goes beyond the fact, never the document itself, and the m2b pane shows both one press
below the fact's file, with `open the file` for a PDF or a picture
([What m2b knows](band.md#what-m2b-knows)). The last line above says the run stopped at page 60
of 75. A file the step cannot read gets a line saying so, and the run goes on. A longer document
makes the ingest step longer: every 20 pages are a read of their own, up to three per document.

## A commit per run

A run rewrites `memory/` and moves captures by itself. If you keep the store in a git repository,
each run ends with one commit, and `git revert <commit>` takes that run back. m2b does this when
the store folder itself is the top of a git work tree (you ran `git init` in the store folder) and
git is on the curating machine. It never makes the repository for you; without one nothing changes
and nothing is reported.

Commit the store once yourself before the first run commits into it, in the store folder:

```bash
cd ~/m2b
git init
git add -A
git commit -m "the store before m2b's commits"
```

In a synced folder (iCloud Drive, Dropbox, Syncthing) keep the repository's own files outside
the folder, for the reason given further down, and tell this machine where they are:

```bash
cd ~/m2b
git init --separate-git-dir ~/.local/share/m2b/store.git
git add -A
git commit -m "the store before m2b's commits"
m2b config set curation.git_directory ~/.local/share/m2b/store.git
```

`git init --separate-git-dir` leaves a `.git` file of one line in the store folder, which names
the directory. That line is synced like everything in the store, so another device, or anything
else that writes the store, can rewrite it. m2b therefore does not take the directory from the
file: a run follows it only to the directory that `curation.git_directory` in this machine's
config names. The last line above does that, once on
each machine that curates. Without it, or when the file points somewhere else than the config
says, a run commits nothing and starts no git for a commit, and its review task and `m2b doctor`
say why. The directory must lie outside the store folder, and so must every link on the way to
it: inside the store, or reached through a link there, the repository's configuration would be as
open to everything that writes the store as the `.git` file is, and a run does not commit there. A `.git` folder in the
store folder, which plain `git init` makes, needs no such line. Know also that `git add -A` reads every file: in iCloud Drive it downloads
those that are not on this machine.

A run commits only what it changed. A file git has never seen, `memory/MEMORY.md` for one, would
enter the repository whole with the first run that touches it, and reverting that run would delete
the file, with every fact earlier runs wrote into it.

What the commit holds:

- every visible file that changed in the store while the run ran: the facts it wrote, the captures
  it moved, task files, the finished run record. A run keeps no list of its own writes, so an
  edit you made in those minutes is in it too;
- with one exception: a capture that came into `inbox/` while the run ran and still waits there
  when it ends. That is a capture you took in those minutes, one a sync service brought, or one
  the run wrote itself and did not file. It stays a file git does not know, `git status` shows it
  as untracked, and the next run commits it before its first step. What the run adds to a capture
  that was there when it began is in the commit: the new name it gave the capture, and the note
  and the reading copy it put beside a picture or a PDF;
- nothing else. What you left uncommitted or staged stays as it is, hidden files stay out, and so
  does a file git ignores, unless the repository tracks it already. An edit of yours in a file the
  run also wrote goes in with that file.

A capture that reached the inbox after your last commit is a file git does not know yet. Before
its first step a run commits such captures where they wait, in a commit of their own
(`m2b: captures before the curation run <start>`). The run's commit then holds the move out of the
inbox, and reverting it puts the capture back there. That first commit holds only files in
`inbox/` that git does not know and that were there when the run began: no capture you staged,
none you changed after committing it, nothing outside `inbox/`, no hidden or ignored file, and no
capture that is not downloaded. With no such capture in the inbox, a run is one commit.

A run that changed nothing but its own record makes no commit; the record goes in with the next
one. A run stopped at preflight makes none either. A run stopped later leaves the commit of the
waiting captures, if there were any, and what its steps changed stays in the work tree for you to
look at.

Both commits are m2b's own. Author and committer are `m2b <m2b@localhost>`, so `git log --author=m2b`
lists them, and the run's message says when the run started and how its steps ended. m2b writes no
git configuration, never pushes, runs no hook and signs nothing, because a run has nobody to
answer a prompt; the filters your repository sets for adding a file (encryption, line endings) do
run. Nothing a run starts reaches a remote. A repository that is a partial clone would have git
fetch the objects it lacks, so a run does not commit into one. It commits onto HEAD as it is,
whatever branch that is. In the middle of a merge, rebase,
cherry-pick, revert or bisect of yours, or when HEAD moved while it worked, it does not commit.

A commit that fails never fails the run: it is the failed step `commit` in the review task and in
the run record. The next run commits what changes while it runs, not what the uncommitted one left.
When the commit of the waiting captures failed, the review and the record say so, in the run's
commit too, because reverting that commit would then remove the captures the run filed instead of
putting them back.

### Taking a run back

`git revert <the run's commit>` puts back what the run changed: the captures it filed are in
`inbox/` again, with the exceptions below, and `memory/`, the task files and the run record are as
they were before it. The
next run files those captures again. Revert the commit named `m2b: curation run ...`, not the one
of the captures before it. Tasks in Apple Reminders are not in the store, so they stay as the run
left them.

- A file that was in no commit before the run is deleted by the revert, not put back as it was:
  `memory/MEMORY.md`, a fact file or a task file in a store you never committed yourself. The
  facts are not lost, `git revert` on the revert brings the file back; committing the store once
  before the first run avoids it ([A commit per run](#a-commit-per-run)).
- git refuses the revert while `state/core/last-run.json` holds a change that is not committed.
  That is the case after a later run that had nothing to do: it wrote its record and made no
  commit. `git restore state/core/last-run.json` drops that record; then revert.
- A capture you changed after committing it comes back as you committed it. The text the run
  filed is in the run's commit: `git show <commit>:corpus/YYYY/MM/<file>`.
- A capture that came in while the run was already under way and that no step filed stays where
  it is: it was never in the run's commit, so the revert does not touch it, and it waits in
  `inbox/` for the next run. It keeps what the run wrote into it. When the run filed its facts
  and then could not file the capture, its front matter still says `facts_filed: true`, and the
  next run would skip those facts although the revert took them out of `memory/`: delete that
  line from the capture first.
- A capture that came in while the run was already under way, and that the run still filed, is
  not put back: git did not know it when the run began. `git show` has it in the same way.
- A capture you staged and did not commit is not put back either. m2b commits nothing you staged,
  so the run's commit has that capture only where it was filed; `git show` has it there.

In a synced folder git is handed only files that are on this machine. A changed file that is not
downloaded is left out, and a `.gitignore` or `.gitattributes` that is not downloaded stops the
commit and names the command that fetches it. Keep the repository's own files out of a synced
folder: `git init --separate-git-dir <a folder outside>` in the store folder leaves only a small
`.git` file there, and `curation.git_directory` names the folder outside
([above](#a-commit-per-run)). A sync service that evicts or duplicates files inside `.git` breaks a
repository, whoever commits into it; m2b's git never downloads such a file, it fails, and the
review says so.

`m2b config set curation.git_commit false` on the curating machine turns the commit off.

`m2b doctor` says in its line `store-git` whether a run on this machine commits: `no repository`
without a `.git` in the store folder; `found` with the git directory and the git that named it
when a run here commits; `found` with the reason when this machine does not curate or has the
commit off; or `cannot commit` with the reason. A machine without git is such a reason, and
doctor is the only place you learn of it, because a run there commits nothing and says nothing.
A `.git` file that points at a directory the config does not name is another; a run says that
one in its review task too.
Doctor looks for git on the `PATH` it is started with; a run started by a schedule looks on the
`PATH` the schedule gives it.

## Correcting what a run filed

A model files your notes, and it can file one wrong. The files in `memory/` are yours to edit, and
nothing a run filed is final:

- **A fact is wrong.** Say the right one, "remember that Dana's birthday is on 4 March". The next
  run rewrites the line; a correction leaves no old value behind, while a fact that changed, such
  as a new address, keeps its old value under `## Earlier` in the fact file. Or edit the line in
  `memory/MEMORY.md` and in its fact file yourself.
- **A fact stands under a topic and every session should start with it.** Move its line in
  `memory/MEMORY.md` above the first `###` heading. The other way round, a line moved under a
  `### <name> (<word>, <word>)` heading reaches a session only when it is about that topic
  ([Store format](store-format.md)). A current item you move above the topics goes back under its
  topic at the next run while it names a word of exactly that one topic; say it without the word.
- **The review task names a finding of lint,** such as "in memory/MEMORY.md, the topic Mill Lane
  has 1 word in the brackets of its heading; it needs 2 to 5". Change the file the finding names,
  here by adding a word a prompt about the topic would use, as in
  `### Mill Lane (mill lane, bike shop)`, and tick the review task; the next run reports the
  finding again if it still holds.
- **A note should never have been kept,** a password or something told in confidence. While no
  run has filed it, delete its file in `inbox/`. After a run, read the `filed:` line at the end of
  its file in `corpus/<year>/<month>/` first: it names every fact file and task the run made from
  the note. Delete each of those facts in its fact file, with the link to the note under
  `## Evidence` there, and its line in `memory/MEMORY.md`; any line under `## Current` about it,
  which `m2b search` finds; and the tasks, in your task list. Then delete the note's file. What
  m2b does not reach: a copy of `memory/` from
  before a run under `~/.local/state/m2b/memory-before-run/` on the curating machine, earlier
  commits when the store is a git repository, and whatever your sync service or backup keeps.

## Reading your sessions

Much of what belongs in a second brain is said in passing: who runs what at a customer, what was
agreed on the phone, what you promised by Friday. With `curation.read_sessions` set to `true` in
the machine config, a curation run looks for it in what you typed in Claude Code and proposes it;
nothing is filed before you say keep. It is off by default. Setup asks on the machine that
curates, and `m2b config set curation.read_sessions true` or `false` changes the answer later.

**What is read.** Claude Code's transcripts on this machine, and of them only the prompts Claude
Code marks as typed by a human, in the terminal or the desktop app, also a message you send while
Claude is working, with what you pasted into one kept apart from what you typed. Beside each prompt,
never as your words, goes the turn it answers: the last 500 characters of what Claude wrote before
it and the shell commands Claude ran in that turn, so a correction can be told by what it corrects.
Left out: the rest of Claude's answers, what a tool printed, what a plugin, a finished task or
another agent sent, a suggested prompt you only accepted, and the blocks Claude Code writes into a
prompt. Credentials are redacted, and a
prompt ends after 2,000 characters, what you typed first and what you pasted in the room that is
left. A longer text you wrote elsewhere reaches a prompt as pasted text, and so does a mail or a
piece of an agent's answer, so a proposal says which of the two it stands on (below). A session
that started in or below a folder of `worklog_leave_out` in the profile, or one where you ran `m2b
distillate off`, does not reach the model, and neither does a headless run such as a curation run
itself. The same setting names work by a git remote of its repository ([Leaving work
out](addons/worklog.md#by-git-remote)): a session in such a repository does not reach the model,
and while you name a remote, neither does one whose repository nobody can tell, because its folder
is gone and nothing was noted for it or git does not answer. The run's information counts both.

**When.** The step `glean` runs after harvest and before ingest, so what you captured yourself is
in the store by then. It covers the time since the last reading ended: the last 24 hours at the
first reading and never more than 7 days; what lies before is named as not read. Without a prompt
of yours in that time the reading starts no model; the check of your lessons against the files
every session loads (below) still asks one when those lessons or files changed.

**What is kept.** The model gets the distillate, so it can leave out what is known, the proposals
you kept and dropped lately (below), per session its folder, its day and its prompts, and the
lessons you kept, each with the day it was kept. Beside its proposals it names the prompts that
correct Claude on a kept lesson again; code counts such a correction only where its words, at
least three, stand in what you typed after that day. It answers with proposals of six kinds, a person, an
agreement, a commitment, something personal, a lesson and a pointer, each with the words it stands on. A
lesson is a correction of how Claude works that holds beyond the task at hand, such as "only the
quick round" after Claude ran the whole proof. Once is enough; where you said the same in another
session too, the lesson stands on both. Code keeps it only when your sentence stands in what you
typed, a second one in its own session, and for a command when its words stand in a command Claude
ran there. One for a single project names that project's repository, where the folders of its
sessions name the same one by a git remote; without one it is left out. A correction where the
model cannot tell whether it holds beyond the task at hand is no lesson: the model names it apart,
with what it is about, and code remembers it on this machine for 30 days, at most 300 of them, in
`~/.local/state/m2b/remembered-corrections.json`, with your words, the shell commands of the turn
they answer and the repository's address, never in the store. Nothing is proposed from it; `m2b
status` says how many are remembered. Before a lesson is proposed, a second
model run without tools reads it with the files a session in its folders loads (the `CLAUDE.md`
files, the rules, the output style, Claude Code's memory, the list `m2b status` measures), each
line numbered. Where a line says the matter wrongly, the lesson becomes a fix of that line, with
the new wording; where a line says it rightly, a pointer to that line, without text of its own; a
lesson for one project that no file states becomes a fix that adds it to that project's
`CLAUDE.md`. Code keeps a verdict only for a line that stands in a file it showed, and a fix only
for a file under `~/.claude/` or in a repository. A fix you keep waits in the store until the next
session where the file lies applies it with you ([Fixes](using.md#fixes-for-the-files-claude-reads)),
and the reading goes on counting corrections of its lesson under the fix's name until you give the
fix up; a pointer is kept as a lesson that names its file and stays out of the block every session gets.
The files change after that, so every reading asks again, before it reads the sessions, whether a
file every session on this machine loads (`~/.claude/CLAUDE.md`, its rules without `paths`, the
output style chosen there) states a lesson of the block now. The model is asked only when those
lessons or files changed since its last answer; a lesson it finds stated, at a line code finds in
the file, keeps that file as its source and leaves the block, and the run says so. Code keeps a
proposal only when those words stand in one prompt of the session it names, typed or pasted, with
at least three words, and when you did not capture the same thing in that time. A proposal like one that
waits, or like one you kept or dropped or that expired within 90 days, is not kept a second time,
so reading a period again adds nothing.

A pointer is a decision, an agreement, a person or a deadline of a project you stated in a session
that Claude wrote into a file of the repository, such as `docs/records/014-login.md`. The model
sees the files a session wrote only where its repository has a project topic, by their path in
the repository; code keeps a pointer only to a file its session wrote. Kept, it becomes a line of
that project's topic, `- <sentence> → <path>`, so the decision stays in the repository and the
second brain knows where.

Code proposes one more kind by itself, with no model and on no words: a `project`, a repository
whose remote the session start noted and that you typed in on two days, in this reading or in one
of the last 30 days, while no topic names it and no capture of it waits in the inbox
([A project](using.md#a-project)). A session in a folder that is left out counts for none.

**Your answer.** `m2b proposals` lists what waits, each with its id, its kind, the text, the words
it stands on and their day: `said on <day>` before words you typed, `pasted on <day>` before words
that stood in text you pasted, which may be someone else's:

```bash
m2b proposals                 # what waits for an answer
m2b proposals keep <id>...    # or: m2b proposals keep --all
m2b proposals drop <id>...
```

`keep --all` and the pane's keep all keep every proposal a reading found that waits, as it is written. Text you
pasted can try to lead the model, also to a proposal that quotes words you typed, so read each
proposal's text before you keep it.

With the band, its row counts them among what waits for you, and
`/m2b-proposals` or the tab `Proposals` shows them in the m2b pane, where keep, drop and keep all
are buttons ([the band](band.md#the-proposals-from-your-sessions-in-the-pane));
they add the same answers as the commands.

An answer is filed by the next curation run: harvest writes a capture with the proposal's text
(source `proposal`, `from_proposal` in its frontmatter), and ingest files it like any capture.
After answers given in the m2b pane on the machine that curates, that run starts by itself, once
no proposal waits any more and one is kept ([When it runs](#when-it-runs));
`curation.run_after_answers` set to `false` turns that off, and the answers then wait for the
next run that is due or for `curate now`. Answers given on a machine that does not curate wait
for the curating machine's next run.
Answers given with `m2b proposals keep` in a terminal start no run by themselves:
`m2b curate --detach --after-answers` starts it. A
commitment that names its day gets its task with the capture. A dropped proposal is remembered for
90 days and not proposed again. Where a keep and a drop for one proposal meet, from two machines,
keep stands.

While proposals wait, your task list holds one task for them, "m2b: proposals from your sessions",
however many there are; its notes say how many wait, so a phone shows that something does. The
task is no answer: completing or deleting it keeps and drops nothing. Every curation run brings
the number up to date, whether or not it reads the sessions, and completes the task once nothing
waits. A task you completed or deleted comes back only when a proposal was added since.

**Without an answer.** A proposal you did not answer within 14 days expires: it leaves the
listing, the task and the band's count, and is not proposed again for 90 days. It does not count as
dropped. While it is remembered, `m2b proposals keep <id>` still keeps it. Every curation run lets
proposals expire and removes those kept, dropped or expired 90 days ago, whether or not it reads
the sessions.

**What your answers change.** The next reading shows the model what you answered: up to 30
proposals you kept and up to 30 you dropped, of each those a run settled last, with the kind, the
text and the words it stood on. The model is told to leave out what is like something you dropped, also where
it would otherwise propose it, and in doubt to propose what is like something you kept; the kinds
and what is never proposed stay as they are. So dropping the time of a call a few times is
how you say that such things do not belong in your memory. It is a rule a model follows, not a
check in code. An expired proposal is not shown: you did not look at it, which says nothing about
it. A proposal is no example any more 90 days after a run settled your answer to it. The model is
also told never to propose an example itself, and code would refuse one: its words stand in no
prompt of the period. The model is shown what a reading found that still waits for your answer too,
up to 30 proposals, and told not to propose any of them again in other words.

**How much you keep.** `m2b status` says what share you kept of the proposals you answered in the
last 30 days, and how many expired in that time:

```text
proposals: kept 7 of 10 answered in the last 30 days (70%), 2 expired without an answer
```

Expired proposals are not part of the share, and without an answer in the 30 days the line says
so instead of 0%. `m2b status --json` holds the same under `proposal_answers`, and with it the
counts per kind since the first reading: how many were proposed, kept, dropped and expired, and how
many were refused because the words they quote do not stand, with at least three words, in a
prompt of the session they name. m2b does nothing with these numbers: they are there for you to
see whether the reading proposes what you want, and `curation.read_sessions` stays your switch.

**When it fails.** A transcripts folder m2b cannot look at, a model without an answer or an answer
it cannot read fails the step alone: the review says so, nothing is saved, and the next run reads
the same time again. A period with texts of which none carries Claude Code's mark of who sent it
fails the same way, so a Claude Code too old to write the mark never passes for a day on which
nothing was typed.

## What a session hands in

A second way to a proposal, beside the reading and independent of it: with `sessions.propose` on
([Configuration](configuration.md#configjson-this-machine)), the agent of a session hands a
proposal in by itself when the session states who someone is, an agreement, a commitment of yours
or something about your own life, also where the words stand in what it read for you, a mail or a
document ([The band](band.md#handing-in-a-proposal-a-tool-you-turn-on)). The call is checked
against that session's transcript on the machine it runs on, and what passes is one file under
`state/core/handed-in/`.

Every curation run that gets to its step for the proposals takes these files in, whether or not
it reads your sessions: each becomes a proposal that waits, like one a reading found, and its file is
removed. The run reads no transcript, the session may have run on another machine. It checks
again what needs none (the form, hidden characters, credentials by pattern, the tool's name) and
leaves out what you captured yourself since the day before that day, as far as a month back, and
what is like a proposal that waits, was answered or expired. So a fact a session hands in and a
reading proposes too waits once, and so does one that several sessions hand in. Where both come
in one run, the reading's proposal is the one that waits: it is worded from what you typed and
pasted alone. Where the session's came first, it stands in the reading's way, and dropping it
keeps both from coming back for 90 days. Of one session a run takes ten; the session can hand in
ten more after each run. The run's information says how
many it added and how many not, by reason; a file that is not downloaded waits for the next run,
and one a newer m2b wrote stays until this machine is updated.

Such a proposal says where its words stand and that a session handed it in:

```text
38d8f71e327f  person, handed in by a session
  Dana Whitfield runs purchasing at Acme.
  in a result of Read on 2026-11-15: "Dana Whitfield runs purchasing at Acme"
```

The line reads `said on`, `pasted on`, `in a result of <tool> on` or `Claude wrote on`. The mark
in the heading stands also where the words were typed: an agent worded the text, and it had read
more than your words. Code found the words in the session; it never shows that they carry the
text. Read a proposal before you keep it. `m2b proposals keep --all` and the pane's `keep all`
leave the proposals sessions handed in, and the command says how many; you keep or drop each by
its id, or with its own row in the pane.

A proposal a session handed in is no example for the reading's model, and it expires and is
remembered like any other. `m2b status` counts both ways apart, per source of the words:

```text
proposals a reading found in typed words: 2 waiting, 5 kept, 1 dropped, 0 expired in the last 30 days
proposals sessions handed in from a tool's result: 1 waiting, 3 kept, 2 dropped, 0 expired in the last 30 days
```

`waiting` counts the proposals without an answer. One you answered since the last curation run is
counted apart until that run files it: `1 waiting, 2 answered for the next run, 3 kept, ...`.

What a session handed in is one of these proposals only once a run took it in. Until then
`m2b status` says how many wait, and nothing of what they say:

```text
handed in: 2 waiting for the next curation run
```

`m2b proposals` says the same below its listing, the band's row counts them (`1 handed in`), and
the overview of the m2b pane says it above `curate now`, so you see that a session proposed
something and that a run is worth starting.

Where the store is a git repository, a handed-in file is committed with the waiting captures
before a run's first step, and the run takes in only what a commit holds, so taking that run back
puts the file where the next run takes it in again; a file that came in later, or was not
downloaded yet, waits for the next run ([A commit per run](#a-commit-per-run)).

## What runs when

| | After install, before setup | After its setup |
|---|---|---|
| core | nothing: the session-start hooks print nothing and no run starts until `/m2b:m2b setup` | the distillate at session start, a curation run at the next session start after a capture on the curating machine |
| band | draws nothing and starts nothing while there is no launcher | the band and the status line, while mods are on in Claude Code |
| `worklog` | prints nothing, records nothing | herdr events recorded on the curating machine, a daily worklog note |

## After an update

When a new m2b changes a rule for content already in the store, it raises the store's format
(`format` in `store.json`, see [Store format](store-format.md#formats)), and the curating
machine's next run migrates the store before anything else: you run nothing. `m2b status` and
`m2b doctor` show `store format: migrates` until then. Update the curating machine first: an m2b
that knows an older format reads a newer store and captures into it, but does not curate it
([Several machines](several-machines.md#machines-on-different-versions)).

## Moving over an older distillate

Two one-off runs bring a `memory/` written by another tool, or by m2b before 0.1.0, up to date:

```bash
m2b curate --refresh-all   # dates the memory lines written without dates
m2b curate --sort-facts    # sorts the facts of an older distillate into topics
```

`--refresh-all` reads the evidence of every undated line and sets `until` or `since` only where a
capture names the day. `--sort-facts` moves the lines that matter for one subject under its topic;
code then compares the file and puts the old one back if any statement changed. It leaves
`## Current` as it is: an item above the topics there moves under its topic when ingest files a
capture about the same thing, and at every run's lint when it names a word of exactly one topic.
One that names two topics, or none, stays until you move it by hand.

## Pausing

To keep a machine from starting runs by itself, for example while a subscription's limit is
nearly used up or while you look at what the last run did:

```bash
m2b config set curation.paused true
```

From then on no session start on this machine starts a run, none starts after your answers to
proposals, and a scheduled `m2b curate` does nothing and exits 0. Everything else goes on: captures reach the inbox, sessions get the
distillate, and `m2b curate --force` files the inbox when you ask for it, as do `curate now` in
the m2b pane and the one-off runs `--refresh-all` and `--sort-facts`. `m2b status` has a line
`paused` while the setting is on, and shows a scheduled attempt as `last attempt: paused at ...`.
`m2b config set curation.paused false` ends the pause; the next session start then starts the run
that is due.

The setting is this machine's. It does not move curation: while the curating machine is paused,
no other machine files the inbox ([Several machines](several-machines.md)).

## On a schedule

Most setups need no schedule: the next session start on the curating machine files what waits. A
schedule helps when captures reach the inbox while that machine starts no Claude Code session for
days, for example captures from a second machine, or an integration such as a Shortcut that
writes into the inbox. A scheduled `m2b curate` that is not due does nothing and exits 0, so it
is safe to run daily; on a paused machine ([Pausing](#pausing)) it does nothing either.

A schedule calls the launcher `~/.local/bin/m2b`, which setup wrote with the absolute path of
`python3`; the model steps use the absolute paths of `claude` and `reminders` that setup recorded,
because a scheduled job runs with a short `PATH`. Check them with:

```bash
m2b config get executables --json
```

### macOS: a Shortcuts automation

A launchd job is not given access to iCloud Drive and Reminders the way an app is; a personal
automation in Shortcuts runs as Shortcuts, and macOS asks once for access to the folder and to
Reminders.

1. Open **Shortcuts**, then **Automation**, then **New Automation**.
2. Choose **Time of Day**, set a time such as 06:30, **Daily**, and **Run Immediately**.
3. Add the action **Run Shell Script**. Shell: `zsh`. Script:

   ```bash
   "$HOME/.local/bin/m2b" curate
   ```

4. Save, then run the automation once by hand and allow the access macOS asks for.

### Linux: cron

```cron
30 6 * * * /home/alex/.local/bin/m2b curate >> /home/alex/.local/state/m2b/cron.log 2>&1
```

Use your own home folder; cron does not expand `~`. If the store is a synced folder, schedule the
run after the sync client has started. The launcher finds the core through Claude Code's plugin
list; on a machine that runs m2b from a checkout instead of the installed plugin (the `claude`
command is still needed for the model steps), name the checkout in the line:

```cron
30 6 * * * M2B_CORE_ROOT=/home/alex/src/m2b/plugins/m2b /home/alex/.local/bin/m2b curate >> /home/alex/.local/state/m2b/cron.log 2>&1
```

### Checking a scheduled run

`m2b status` shows when the last run started and how it ended; a run that found nothing due shows
as `last attempt: not due at ...`, so you can see the schedule reached m2b. The machine's run log
is `~/.local/state/m2b/run.log`; a run that could not even write its record leaves its cause there.

A run m2b starts in the background, at a session start, with `m2b curate --detach` or with
`curate now` in the m2b pane, has no terminal and no log of yours to print to. What it writes on standard error is kept in
`~/.local/state/m2b/detached-run.err`, replaced each time such a run starts; look there when a
run left neither a record nor a line in the run log.

## The status line

While [the band](band.md) runs, one line below the prompt says what is wrong with m2b, and there
is no line while nothing is: Claude Code draws every plugin's status line with a ⚠ and in the
color of a warning. It is refreshed about once a minute and after each of your turns.

| Status line says | Meaning |
|---|---|
| `last curation run failed` | the last run failed; the review task in your list names the step and the cause, and `/m2b-review` shows it |
| `last curation run interrupted` | the last run ended without finishing, for example because the computer shut down or its process was killed |
| `could not read the last curation run`, `could not read the inbox` or `could not read the lessons` | that part of the store could not be read |
| `could not read store.json`, `tasks not reachable` (likewise for the store and the calendar) | that file or backend; the task list, store and calendar are checked every 5 minutes, so such a problem can show up or clear that much later |
| `could not look` | `m2b status` gave no answer at all; run it in a terminal to see why |

Several are joined with ` · `. When m2b last curated, whether a run is going on and how many
captures wait in the inbox is what the part "m2b" of the pane's overview says, and `m2b status`
in a terminal.
