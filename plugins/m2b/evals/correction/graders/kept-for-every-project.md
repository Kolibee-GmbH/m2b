---
type: tool_used
tool: Write
# The CLAUDE.md every project loads: ~/.claude/CLAUDE.md as the rule names it, or the one in the
# run's config folder, where Claude Code reads it while CLAUDE_CONFIG_DIR is set. Not one in the
# project's own folder, which loads for this project only.
input_match: "\"file_path\"\\s*:\\s*\"(?![^\"]*/cwd/)[^\"]*(/\\.claude|/config)/CLAUDE\\.md\""
---
The correction went into the CLAUDE.md that every project loads.
