"""What every skill that runs in the owner's session tells the model about running its commands."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "skills"
# The skills a session runs with the owner present. ingest, refresh, sort-facts, lint and
# worklog-verdict run fenced with ``dontAsk`` inside a curation run, where nothing can ask.
SESSION_SKILLS = (
    "capture",
    "search",
    "todos",
    "rediscover",
    "m2b",
    "setup",
    "worklog-setup",
)
# A skill's allowed-tools cover each command alone; a model that appends `echo "exit=$?"` or
# chains a second command falls outside them, and the owner gets a permission prompt.
OWN_CALL_RULE = "Run each `m2b` command in a Bash call of its own"
BASH_BLOCK = re.compile(r"^[ \t]*```bash\n(.*?)^[ \t]*```$", re.MULTILINE | re.DOTALL)
CHAINED = re.compile(r"&&|\|\||;|\|")


def commands_in(block: str) -> int:
    """Command lines in a bash example; a heredoc counts as the one command that opens it."""
    count = 0
    heredoc_end: str | None = None
    for line in block.splitlines():
        if heredoc_end is not None:
            if line.strip() == heredoc_end:
                heredoc_end = None
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        count += 1 + len(CHAINED.findall(line.split("<<", 1)[0]))
        opened = re.search(r"<<-?'?(\w+)'?", line)
        if opened:
            heredoc_end = opened.group(1)
    return count


class SessionSkillTest(unittest.TestCase):
    def test_each_session_skill_runs_its_commands_without_additions(self) -> None:
        for name in SESSION_SKILLS:
            with self.subTest(skill=name):
                body = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")

                self.assertIn(OWN_CALL_RULE, body)

    def test_no_example_shows_two_commands_in_one_block(self) -> None:
        for name in SESSION_SKILLS:
            body = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            for block in BASH_BLOCK.findall(body):
                with self.subTest(skill=name, block=block.splitlines()[0]):
                    self.assertEqual(commands_in(block), 1)

    def test_a_chained_line_counts_each_command(self) -> None:
        self.assertEqual(commands_in("m2b status; echo $?\n"), 2)
        self.assertEqual(commands_in("m2b doctor && m2b status\n"), 2)

    def test_a_heredoc_counts_as_one_command(self) -> None:
        block = "m2b capture --source claude - <<'CAPTURE'\nfirst line\nsecond line\nCAPTURE\n"

        self.assertEqual(commands_in(block), 1)


if __name__ == "__main__":
    unittest.main()
