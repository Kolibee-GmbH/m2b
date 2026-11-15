#!/bin/sh
# The invented store, and notes of a visit that repeat what a topic of the store holds: the session starts with
# the topic's name only, so it has to search before it knows that nothing here is new.
set -eu
sh "$(dirname "$0")/../demo-store.sh"
project="$HOME/cwd"
mkdir -p "$project"
cat > "$project/visit.md" <<'TEXT'
# Visit at Northwind, 10 November

- Nora Lind, who runs their IT, showed us the server room.
- The contract renews in March.
- The badge reader at the side door is broken.
- The backup of the file server ran out of space last week.
TEXT
