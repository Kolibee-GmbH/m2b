#!/bin/sh
# The invented store, and a small script with one bug in the run's working directory. The task has
# nothing to do with the notes: m2b should neither help nor get in the way.
set -eu
sh "$(dirname "$0")/../demo-store.sh"
project="$HOME/cwd"
mkdir -p "$project"
cat > "$project/wordcount.py" <<'PY'
"""Counts how often each word appears in a text."""

import sys
from collections import Counter


def count_words(text: str) -> Counter[str]:
    return Counter(text.split())


if __name__ == "__main__":
    for word, count in count_words(sys.stdin.read()).most_common():
        print(f"{count}\t{word}")
PY
