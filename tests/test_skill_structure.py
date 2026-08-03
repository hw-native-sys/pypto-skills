from __future__ import annotations

import unittest

from tests.skill_assertions import SKILLS, frontmatter, markdown_links, skill_dirs

EXPECTED_SKILLS: tuple[str, ...] = (
    "clean-branches",
    "fix-pr",
    "git-commit",
    "github-pr",
)


class SkillStructureTests(unittest.TestCase):
    def test_expected_skill_directories_exist(self) -> None:
        available = {path.name for path in skill_dirs()}

        for name in EXPECTED_SKILLS:
            with self.subTest(skill=name):
                self.assertIn(name, available)

    def test_expected_skills_have_skill_markdown(self) -> None:
        for name in EXPECTED_SKILLS:
            with self.subTest(skill=name):
                self.assertTrue((SKILLS / name / "SKILL.md").is_file())

    def test_expected_skills_have_valid_frontmatter(self) -> None:
        for name in EXPECTED_SKILLS:
            with self.subTest(skill=name):
                skill_markdown = SKILLS / name / "SKILL.md"
                self.assertTrue(skill_markdown.is_file())
                metadata = frontmatter(skill_markdown)
                self.assertEqual({"name", "description"}, set(metadata))
                self.assertEqual(name, metadata["name"])
                self.assertTrue(metadata["description"].startswith("Use when"))

    def test_expected_skills_have_openai_metadata(self) -> None:
        for name in EXPECTED_SKILLS:
            with self.subTest(skill=name):
                self.assertTrue((SKILLS / name / "agents" / "openai.yaml").is_file())

    def test_expected_skills_have_resolvable_local_markdown_links(self) -> None:
        for name in EXPECTED_SKILLS:
            with self.subTest(skill=name):
                skill_markdown = SKILLS / name / "SKILL.md"
                self.assertTrue(skill_markdown.is_file())
                for target in markdown_links(skill_markdown):
                    self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
