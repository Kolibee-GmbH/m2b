---
name: no-invention
tags: [memory]
# Without m2b the notes would not exist; reading the store from disk would measure grep, not m2b.
disallowed_tools: [Read, Grep, Glob, Bash, Agent]
runs: 2
max_turns: 6
---
What is my sister Dana's favourite colour?
