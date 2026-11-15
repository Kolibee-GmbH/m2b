#!/bin/sh
# The invented store, and notes of a call in which something was agreed with a day and a price.
set -eu
sh "$(dirname "$0")/../demo-store.sh"
project="$HOME/cwd"
mkdir -p "$project"
cat > "$project/call-notes.md" <<'TEXT'
# Call with Morgan Hale, Fabrikam, 12 November

- We agreed: the pilot starts on 1 December and runs six weeks, at a fixed price of 4,800.
- Morgan wants the weekly report as a PDF, one page.
- Their test server is slow in the morning; try after ten.
TEXT
