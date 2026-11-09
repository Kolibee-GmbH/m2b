---
name: rediscover
description: Brings one or a few old notes from the owner's second brain back into view, each with the reason it was picked. Use when the user says "rediscover", "show me an old note", "what did I write back then", "remind me of something I noted", "surprise me from my notes", "what did I note last spring", "what did I write in May", "zeig mir eine alte Notiz", "was habe ich früher notiert", "was habe ich letzten Frühling notiert", "hol was Altes hervor". Only reads; never invents a note or a reason.
allowed-tools: Bash(m2b rediscover *)
---

# Rediscover

You bring old notes back to the user's attention, so that what they once wrote down is not
forgotten. You only read.

## Reading

```bash
m2b rediscover --json
```

Run each `m2b` command in a Bash call of its own, as shown: nothing chained before or after it,
no `echo $?`. This skill may run the command alone without asking, and Claude Code reports a
failing exit code by itself.

Add `--count N` when the user wants more or fewer than three. When the user names a time ("last
spring", "in May", "im Sommer 2025"), add `--month YYYY-MM` for one month or
`--month YYYY-MM..YYYY-MM` for several, counted from today's date: "last spring" in November 2026
is `--month 2026-03..2026-05`. A season or a month without a year is the most recent one that has
passed. The JSON has `picks`, each with
`path`, `reason`, `text` (the note as captured, without the curator's additions; `truncated` says
whether it was cut), and for a pick that shares a word with what is going on now also `word` and
`current_item`. `evicted` lists notes not downloaded to this machine, each with its `fetch`
command; `unreadable` lists notes that could not be read.

Notes the user marked to keep quiet never come back here, and journals, worklogs and photo
descriptions are not offered either.

## Answer

- For each pick, say why it came up first (from `reason`, in the user's language: "a random pick
  from May 2026", "it mentions the shed you are working on"), then the note in its own words or a
  faithful short summary, and its date if the note shows it.
- Never add details the text does not hold, and never make up a reason.
- Offer one next step at most, such as keeping it in mind or capturing a follow-up; do not act on
  it without being asked.
- No picks and nothing evicted: say there is no old note to bring back yet, or, with `--month`,
  that there is no note from that time. If `evicted` is not
  empty, say that some notes are not on this machine and give the commands from `fetch`.
- The command fails: say that you could not look. Exit 2 means no second brain is set up on this
  machine; exit 3 means the store could not be reached.
