---
name: no-false-lead
tags: [memory, no-harm]
# Without m2b the notes would not exist; reading the store from disk would measure grep, not m2b.
disallowed_tools: [Read, Grep, Glob, Bash, Agent]
runs: 3
max_turns: 6
---
Tomorrow is my first call with Ben Hart. Check my notes and tell me what I should bring up with him.
