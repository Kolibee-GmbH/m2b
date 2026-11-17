# Cost and privacy

What a curation run costs, which steps call a model, and what each of them hands it.
[What runs on your machine](../README.md#what-runs-on-your-machine) is the overview of what m2b
starts and when; [SECURITY.md](../SECURITY.md) says what a hostile note can do and how a model
step is fenced.

## What a run costs

A curation run uses your Claude Code login, with Haiku by default. Measured on
2026-11-08 with Claude Code 2.1.319: a run over five captures took 48 seconds and 31 turns,
read about 365,000 input tokens (338,000 of them from Claude Code's prompt cache) and wrote 8,000;
Claude Code put it at US$0.013 at API prices. A run with nothing to read (an empty inbox, nothing
expiring, no memory link to repair) uses no model. m2b does not record what a run used:
`curation.max_turns` and `curation.max_budget_usd` cap a model step, and `curation.paused` stops
the runs that start by themselves ([Configuration](configuration.md)).

## Which steps call a model, and what reaches it

**The model.** Only a curation run calls a model, and only for a step with something to read:
ingest for new captures, refresh for a fact past its day, lint for a broken link in memory with
exactly one candidate, the reading of your sessions once in a run while it is on and you typed
something since the last reading, and the worklog's verdict once a day while that add-on is on,
unless the day had no sessions. Each step runs with `curation.model` (`haiku` by default; setup offers `sonnet`
for more careful filing at a higher cost) and stops after `curation.max_turns` turns;
`curation.max_budget_usd`, unset by default, caps its spending. It runs on your Claude Code login
and is billed like your sessions.

**What reaches the model.** In a curation step: what the step's rules allow, nothing else. Ingest
and lint read the captures and memory files, ingest also a picture or a document in the inbox, a
PDF up to its 60th page; refresh reads the distillate, the fact files that are
due and any archive file; sorting reads memory. Ingest, lint, `--refresh-all` and the worklog step
also get `m2b search` results over inbox, archive and memory. The reading of your sessions sends
the distillate, up to 30 proposals you kept and 30 you dropped lately, each with the words it
stood on, and, per session, its folder, its day and the prompts you typed, with what you pasted
into them, redacted, to a model that can call
nothing. With the worklog add-on, its step sees the period's prompts and last
answers, commits and session folders, the inbox and memory (below). In every session:
the distillate, the routing rule and the notices at session start; before a prompt that names a
topic, that topic's facts; and what you ask it to look up, search hits or a fact's file or a note
read whole. Of a document in the archive, m2b's search tool and skill hand a session the note and
the outline in it, never the document.

**What a session writes into the store when it hands in.** Off until you turn `sessions.propose`
on. Then the agent of a session can hand in a proposal with words from what it read for you: a
quote of up to 500 characters from a mail, a document, a page or a command's output lies in the
store's state and syncs with it, with the session's id, the tool's name and the time, until you
answer the proposal and for 90 days after. No model is called for it: the check at the call and
the run that takes the proposal in are code. The tool's description, about 3,200 characters, is
part of every session that has the tool. A session in a folder or repository you leave out hands
nothing in; what a session read through a connector or the web is not covered by that rule
([Security](../SECURITY.md#what-a-session-hands-in)).

**What the worklog reads** (only while on, only on the curating machine): the herdr events its
recorder writes to `~/.local/state/m2b/worklog/`, the prompts and the end of each session's last
answer from your Claude Code transcripts for the period (with credentials and long tokens
redacted, and without a prompt a plugin, a finished task or another session sent), your own git commits (their subjects redacted the same way), and the inbox. Of the
work you tell it to leave out, by folder or by git remote, it keeps nothing; its model step may also search the archive. Its
ledger with time spans and booking proposals lands in the store under `state/addons/worklog/`.
A time span is when a workspace was in use: an agent at work (up to 30 minutes past its last sign
of life, so a machine asleep does not count), the workspace in focus (up to 10 minutes after each of
its own events, because herdr cannot tell typing from looking), or messages in its transcript at most
15 minutes apart, merged across gaps of up to 15 minutes; waiting for an approval does not count.
The same minutes count once, also when a workspace is closed and opened again. An agent left working
on its own, a loop through the night for one, counts as well, so check a booking proposal before you
enter it. A stretch the recorder did not record, because herdr was not running or the machine slept,
is named in the note as not recorded, never read as a time without work. The
[worklog page](addons/worklog.md#time-spans) has the rules.
