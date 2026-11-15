#!/bin/sh
# The invented store, and a list of contacts at a customer the store does not know.
set -eu
sh "$(dirname "$0")/../demo-store.sh"
project="$HOME/cwd"
mkdir -p "$project"
cat > "$project/contacts.md" <<'TEXT'
# Contoso, contacts

- Riley Chen is head of purchasing at Contoso.
- Front desk: weekdays 8 to 17.
TEXT
