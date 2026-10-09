"""Keep installed skill discovery in sync with the repository's workflows."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted(path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md"))


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_is_listed_in_agent_instructions(skill):
    instructions = (ROOT / "AGENTS.md").read_text()
    assert re.search(rf"^\| `{re.escape(skill)}` \|", instructions, re.MULTILINE), skill


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_has_a_readme_command(skill):
    readme = (ROOT / "README.md").read_text()
    assert f"`/freeagent-ai:{skill}`" in readme, skill
