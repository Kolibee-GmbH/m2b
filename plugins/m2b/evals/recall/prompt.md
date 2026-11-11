---
name: recall
tags: [memory]
# Without m2b the notes would not exist; reading the store from disk would measure grep, not m2b.
disallowed_tools: [Read, Grep, Glob, Bash, Agent]
runs: 2
max_turns: 4
---
When does Sam bring the plywood, and where is the spare key for the shed?
