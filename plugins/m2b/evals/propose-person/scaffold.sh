#!/bin/sh
# The invented store, and notes of a meeting with a customer the store does not know: who two people are stands only in this file.
set -eu
sh "$(dirname "$0")/../demo-store.sh"
project="$HOME/cwd"
mkdir -p "$project"
cat > "$project/meeting-notes.md" <<'TEXT'
# Kick-off with Contoso, 12 November

Present: Alex, Riley Chen, Jo Park

- Riley Chen is head of purchasing at Contoso and signs every order above 10,000.
- Jo Park is the project lead on their side from December.
- The warehouse scanners lose their connection in aisle 4; Jo sends the logs.
- Next meeting in two weeks, same room.
TEXT
