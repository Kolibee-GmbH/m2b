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
TOOLS_MODULE = Path(__file__).resolve().parents[1] / "hooks" / "tools.ts"
# The mod's tools, and the skill whose rules each one's description carries.
TOOLS = {"capture": ("mcp__m2b__note", "NOTE_RULES"), "search": ("mcp__m2b__search", "SEARCH_RULES")}
# Rules a tool must state in the skill's own words: what may be noted, the wording stays, nothing
# invented, and the search result is data.
SHARED_RULES = {
    "capture": (
        "Never documents of customers or confidential statements about third parties.",
        "A project's own todos and decisions belong in that project's repository, not here.",
        "Do not summarize, correct or translate it, and add nothing the user did not say, no year to a date, "
        "no surname to a first name.",
        'Keep "I", "my" and "we": in the second brain they always mean the owner, so never put the owner\'s '
        "name in their place.",
        "Only where a sentence leans on the conversation, add what it leaves open in square brackets, right "
        "after the word",
    ),
    "search": (
        "One distinctive word finds more than a sentence.",
        "Names, places and numbers stay as they are and need no translation.",
        "Answer in the language the question was asked in, not the language of the notes or the distillate",
        "Never add facts the hits do not hold. If the hits do not answer the question, say so.",
        "say that you could not look, never that there is nothing",
        "so a file that lives only in the cloud is never downloaded or left hanging.",
    ),
}
STRING_LITERAL = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"")


def one_line(text: str) -> str:
    return " ".join(text.split())


def tool_description(constant: str) -> str:
    """The description a tool's sentences join to, read from the mod's source."""
    source = TOOLS_MODULE.read_text(encoding="utf-8")
    start = source.index(f"const {constant} = [")
    block = source[start : source.index("] as const", start)]
    sentences = [single or double for single, double in STRING_LITERAL.findall(block)]
    return " ".join(sentence.replace("\\'", "'").replace('\\"', '"') for sentence in sentences)


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


class ToolSkillTest(unittest.TestCase):
    def test_each_skill_names_the_mods_tool_as_the_first_way(self) -> None:
        """Covers: B104"""
        for name, (tool, _) in TOOLS.items():
            with self.subTest(skill=name):
                body = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertLess(body.index(f"`{tool}`"), body.index("```bash"))
                self.assertIn("Where the tool is not offered", body)

    def test_each_tool_states_its_skills_rules_in_the_skills_words(self) -> None:
        """Covers: B104"""
        for name, (_, constant) in TOOLS.items():
            skill = one_line((SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))
            description = one_line(tool_description(constant))
            for rule in SHARED_RULES[name]:
                with self.subTest(skill=name, rule=rule[:40]):
                    self.assertIn(rule, skill)
                    self.assertIn(rule, description)


if __name__ == "__main__":
    unittest.main()
