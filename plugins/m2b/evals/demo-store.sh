#!/bin/sh
# Sets m2b up in the fresh HOME of an eval run with an invented store: the owner Alex, a sister, a
# neighbour, a house, and one customer topic. Nothing here is real. The run that follows shares
# this HOME, so its hooks read this store and never the machine's own.
set -eu
plugin=$(cd "$(dirname "$0")/.." && pwd)
export M2B_CORE_ROOT="$plugin"
m2b() { "$plugin/bin/m2b" "$@"; }
store="$HOME/notes"
mkdir -p "$store"
m2b setup apply --answers "{\"store\": {\"backend\": \"folder\", \"path\": \"$store\"}, \"tasks\": {\"backend\": \"markdown\"}, \"owner\": \"Alex\", \"language\": \"en\", \"calendar\": \"none\", \"curates\": true, \"machine_id\": \"eval-machine\"}" >/dev/null
# The note and search tools call the launcher, which finds the core in Claude Code's
# installed_plugins.json. An eval loads the plugin from this folder without installing it, so the
# entry is written here. The run's config folder sits beside its HOME; this script is not told its
# path. Should that change, the note case fails with "not installed for this user" in its trace.
mkdir -p "$HOME/../config/plugins"
printf '{"version": 2, "plugins": {"m2b@m2b": [{"scope": "user", "installPath": "%s"}]}}\n' "$plugin" \
    > "$HOME/../config/plugins/installed_plugins.json"
cat > "$store/memory/MEMORY.md" <<'MEMORY'
# Memory

## Facts

- Dana, my sister: birthday 3 March, wants a fountain pen (dana.md)
- Sam repairs boats at the harbour; brings plywood for the shed roof on 14 November (sam.md)
- Spare shed key: under the blue pot by the back door (house.md)

### Northwind (Northwind, Nora Lind)
- Northwind, a customer: Nora Lind runs their IT; the contract renews in March (northwind.md)

## Current

- Rebuilding the garden shed roof before winter
MEMORY
printf '# Dana\n\nMy sister. Birthday on 3 March. Would love a good fountain pen.\n' > "$store/memory/dana.md"
printf '# Sam\n\nRepairs boats at the harbour. Brings plywood for the shed roof on 14 November.\n' > "$store/memory/sam.md"
printf '# House\n\nThe spare key for the shed is under the blue pot by the back door.\n' > "$store/memory/house.md"
printf '# Northwind\n\nA customer. Nora Lind runs their IT. The contract renews in March.\n' > "$store/memory/northwind.md"
# One run with an empty inbox needs no model; afterwards no run is due at the session start.
m2b curate --force >/dev/null
