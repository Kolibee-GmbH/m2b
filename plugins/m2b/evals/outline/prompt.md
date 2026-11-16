---
name: outline
tags: [memory]
# Without m2b the notes would not exist; reading the store from disk would measure grep, not m2b.
disallowed_tools: [Read, Grep, Glob, Bash, Agent]
runs: 3
max_turns: 6
---
Which pages of my home insurance policy cover storm damage, and what is the excess there?
