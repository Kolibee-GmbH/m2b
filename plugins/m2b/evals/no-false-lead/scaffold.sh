#!/bin/sh
# The invented store, and one archived note about someone whose name starts like the person the
# prompt asks about. A search for "Ben" matches "Bennett" too; the note is not about Ben Hart.
set -eu
sh "$(dirname "$0")/../demo-store.sh"
archive="$HOME/notes/corpus/2026/10"
mkdir -p "$archive"
cat > "$archive/20261020T080000Z-claude-7c1d.md" <<'NOTE'
---
created: 2026-10-20T10:00:00+02:00
source: claude
curated: true
---
Bennett from the rowing club wants his boathouse key back before the regatta on Sunday.
NOTE
