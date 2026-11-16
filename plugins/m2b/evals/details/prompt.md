---
name: details
tags: [memory]
# Without m2b the notes would not exist; reading the store from disk would measure grep, not m2b.
disallowed_tools: [Read, Grep, Glob, Bash, Agent]
runs: 3
max_turns: 6
---
How many sheets of plywood does the new shed roof take, and how thick are they?
