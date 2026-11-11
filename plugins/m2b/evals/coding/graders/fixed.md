---
type: regex
pattern: "\\.(lower|casefold)\\(\\)"
match: contains
target:
  source: file
  path: wordcount.py
---
The words are compared without their case.
