#!/bin/sh
# The invented store, and a project in the run's working directory with a CLAUDE.md of its own.
# The correction the prompt makes holds in every project, so it belongs in the CLAUDE.md every
# session loads, not in this project's CLAUDE.md or the memory Claude Code keeps for this project.
# An eval sets CLAUDE_CONFIG_DIR to the config folder beside HOME, so the global CLAUDE.md Claude
# Code loads there is <config>/CLAUDE.md; a run may write that one or ~/.claude/CLAUDE.md, and both pass.
set -eu
sh "$(dirname "$0")/../demo-store.sh"
project="$HOME/cwd"
mkdir -p "$project"
printf '# Leafpress\n\nA small static site generator.\n' > "$project/README.md"
printf '# Leafpress\n\n## Development\n\n- Run the tests with `make test`.\n' > "$project/CLAUDE.md"
