#!/bin/sh
# The invented store, and a file about a product's versions: no person, no agreement, nothing of the owner's life.
set -eu
sh "$(dirname "$0")/../demo-store.sh"
project="$HOME/cwd"
mkdir -p "$project"
cat > "$project/CHANGES.md" <<'TEXT'
# Changes

## 2.4.1

- The CSV export no longer drops the last row.

## 2.4.0

- New: labels in two sizes.
- The search is case-insensitive.

## 2.3.2

- Faster start on slow disks.
TEXT
