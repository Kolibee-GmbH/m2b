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
and lint read the captures and memory files; refresh reads the distillate, the fact files that are
due and any archive file; sorting reads memory. Ingest, lint, `--refresh-all` and the worklog step
also get `m2b search` results over inbox, archive and memory. The reading of your sessions sends
the distillate, up to 30 proposals you kept and 30 you dropped lately, each with your words, and,
per session, its folder, its day and the prompts you typed, redacted, to a model that can call
nothing. With the worklog add-on, its step sees the period's prompts and last
answers, commits and session folders, the inbox and memory (below). In every session:
the distillate, the routing rule and the notices at session start; before a prompt that names a
topic, that topic's facts.

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
