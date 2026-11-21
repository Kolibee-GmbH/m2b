#!/bin/sh
# The invented store, and a project in the run's working directory with a CLAUDE.md of its own.
# The correction the prompt makes holds in every project, so it becomes an m2b lesson, which every
# session starts with, not a line in this project's CLAUDE.md or the memory Claude Code keeps for
# this project.
set -eu
sh "$(dirname "$0")/../demo-store.sh"
project="$HOME/cwd"
mkdir -p "$project"
printf '# Leafpress\n\nA small static site generator.\n' > "$project/README.md"
printf '# Leafpress\n\n## Development\n\n- Run the tests with `make test`.\n' > "$project/CLAUDE.md"
