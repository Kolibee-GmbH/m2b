#!/bin/sh
# The invented store, and a small project in the run's working directory that keeps its todos in
# TODO.md. The todo the prompt names belongs there, not in the owner's notes.
set -eu
sh "$(dirname "$0")/../demo-store.sh"
project="$HOME/cwd"
mkdir -p "$project"
printf '# Leafpress\n\nA small static site generator.\n' > "$project/README.md"
printf '# Todo\n\n- [ ] Support a config file next to the content folder\n- [ ] Warn about broken internal links\n' > "$project/TODO.md"
