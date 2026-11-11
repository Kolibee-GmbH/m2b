---
name: topic
tags: [memory]
# Without m2b the notes would not exist; reading the store from disk would measure grep, not m2b.
disallowed_tools: [Read, Grep, Glob, Bash, Agent]
runs: 3
max_turns: 4
---
Who runs IT at Northwind, and when does their contract renew?
