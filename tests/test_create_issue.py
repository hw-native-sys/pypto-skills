from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import TypedDict, cast

from tests.skill_assertions import ROOT

CONTEXT_HELPER = ROOT / "lib/github/scripts/issue-context.sh"
CREATE_HELPER = ROOT / "skills/create-issue/scripts/issue-create.sh"
SKILL = ROOT / "skills/create-issue/SKILL.md"


class GHCall(TypedDict):
    argv: list[str]
    host: str
    body: str
    body_file: str


class CreateIssueBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.temp_path = Path(temporary_directory.name)
        self.work = self.temp_path / "work"
        self.work.mkdir()
        subprocess.run(
            ["git", "init", "--initial-branch=trunk"],
            cwd=self.work,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "enterprise",
                "ssh://git@ghe.example.test/acme/widget.git",
            ],
            cwd=self.work,
            check=True,
            capture_output=True,
            text=True,
        )

        self.transcript_path = self.temp_path / "gh-transcript.jsonl"
        self.bin_path = self.temp_path / "bin"
        self.bin_path.mkdir()
        self.write_fake_gh()
        self.write_fake_git()
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        assert real_git is not None
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "PATH": f"{self.bin_path}{os.pathsep}{self.environment['PATH']}",
                "GH_TRANSCRIPT": str(self.transcript_path),
                "TEST_REAL_GIT": real_git,
            }
        )
        self.body_file = self.temp_path / "issue.md"
        self.body_file.write_text(
            """### Component

allocator

### Reproduction

Run the allocator regression case.

### Expected

The allocation succeeds.

### Actual

The allocation fails.

Related: #18
""",
            encoding="utf-8",
        )
        self.title = "[Regression] allocator fails after reuse"

    def write_fake_gh(self) -> None:
        fake_gh = self.bin_path / "gh"
        fake_gh.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys

argv = sys.argv[1:]
body = ""
body_file = ""
if argv[:2] == ["issue", "create"]:
    body_file = argv[argv.index("--body-file") + 1]
    with open(body_file, encoding="utf-8") as approved_body:
        body = approved_body.read()
with open(os.environ["GH_TRANSCRIPT"], "a", encoding="utf-8") as transcript:
    transcript.write(json.dumps({
        "argv": argv,
        "host": os.environ.get("GH_HOST", ""),
        "body": body,
        "body_file": body_file,
    }) + "\\n")

if argv[:2] == ["issue", "list"]:
    print(json.dumps([
        {
            "number": 7,
            "title": "Open allocator cleanup",
            "body": "Related cleanup",
            "state": "OPEN",
            "labels": [{"name": "maintenance"}],
            "url": "https://ghe.example.test/acme/widget/issues/7",
        },
        {
            "number": 18,
            "title": "Closed allocator regression",
            "body": "Different root cause",
            "state": "CLOSED",
            "labels": [{"name": "bug"}],
            "url": "https://ghe.example.test/acme/widget/issues/18",
        },
    ]))
elif argv and argv[0] == "api":
    endpoint = argv[-1]
    if endpoint.endswith("contents/.github/ISSUE_TEMPLATE"):
        if os.environ.get("GH_TEMPLATE_MISSING") == "1":
            sys.stderr.write("gh: Not Found (HTTP 404)\\n")
            raise SystemExit(1)
        if os.environ.get("GH_TEMPLATE_FAILURE") == "1":
            sys.stderr.write("gh: authentication failed (HTTP 401)\\n")
            raise SystemExit(1)
        print(json.dumps([
            {"name": "regression.yml", "path": ".github/ISSUE_TEMPLATE/regression.yml", "type": "file"},
            {"name": "legacy.md", "path": ".github/ISSUE_TEMPLATE/legacy.md", "type": "file"},
            {"name": "config.yml", "path": ".github/ISSUE_TEMPLATE/config.yml", "type": "file"},
        ]))
    elif endpoint == "repos/contributor/widget":
        print(json.dumps({
            "full_name": "contributor/widget",
            "fork": True,
            "default_branch": "work",
            "html_url": "https://ghe.example.test/contributor/widget",
            "parent": {
                "full_name": "acme/widget",
                "html_url": "https://ghe.example.test/acme/widget",
            },
        }))
    elif endpoint == "repos/acme/widget":
        if os.environ.get("GH_REPO_FAILURE") == "1":
            sys.stderr.write("gh: repository not found (HTTP 404)\\n")
            raise SystemExit(1)
        html_url = "https://ghe.example.test/acme/widget"
        if os.environ.get("GH_CONTRADICTORY_URL") == "1":
            html_url = "https://ghe.example.test/attacker/widget"
        print(json.dumps({
            "full_name": "acme/widget",
            "fork": False,
            "default_branch": "trunk",
            "html_url": html_url,
        }))
    else:
        sys.stderr.write(f"unexpected api endpoint: {endpoint}\\n")
        raise SystemExit(92)
elif argv[:2] == ["issue", "create"]:
    print("https://ghe.example.test/acme/widget/issues/42")
else:
    sys.stderr.write(f"unexpected gh invocation: {argv!r}\\n")
    raise SystemExit(91)
""",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)

    def write_fake_git(self) -> None:
        fake_git = self.bin_path / "git"
        fake_git.write_text(
            """#!/usr/bin/env python3
import os
import subprocess
import sys

real_git = os.environ["TEST_REAL_GIT"]
argv = sys.argv[1:]
if argv and argv[0] == "hash-object" and os.environ.get("RACE_BODY_FILE"):
    result = subprocess.run(
        [real_git, *argv],
        input=sys.stdin.buffer.read(),
        check=False,
        capture_output=True,
    )
    with open(os.environ["RACE_BODY_FILE"], "w", encoding="utf-8") as body:
        body.write(os.environ["RACE_REPLACEMENT"])
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    raise SystemExit(result.returncode)
os.execv(real_git, [real_git, *argv])
""",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)

    def transcript(self) -> list[GHCall]:
        if not self.transcript_path.exists():
            return []
        return [
            cast(GHCall, json.loads(line))
            for line in self.transcript_path.read_text(encoding="utf-8").splitlines()
        ]

    def context(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        self.assertTrue(
            CONTEXT_HELPER.is_file(), f"missing context helper: {CONTEXT_HELPER}"
        )
        return subprocess.run(
            [str(CONTEXT_HELPER), *arguments],
            cwd=self.work,
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def issue_create(
        self,
        mode: str,
        body_file: Path,
        *labels: str,
        token: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        self.assertTrue(
            CREATE_HELPER.is_file(), f"missing create helper: {CREATE_HELPER}"
        )
        arguments = [
            str(CREATE_HELPER),
            mode,
            "ghe.example.test",
            "acme/widget",
            self.title,
            str(body_file),
        ]
        if token is not None:
            arguments.append(token)
        arguments.extend(labels)
        result = subprocess.run(
            arguments,
            cwd=self.work,
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            self.fail(f"issue-create failed:\n{result.stdout}{result.stderr}")
        return result

    def preview_token(self, *labels: str) -> str:
        result = self.issue_create("preview", self.body_file, *labels)
        match = re.search(r"ISSUE_CREATE:([0-9a-f]{40,64})", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        assert match is not None
        return match.group(1)

    def test_repository_context_bootstraps_from_git_without_ambient_repo(self) -> None:
        result = self.context("repository")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            {
                "github_host": "ghe.example.test",
                "local_repo": "acme/widget",
                "issue_repo": "acme/widget",
                "default_branch": "trunk",
            },
            json.loads(result.stdout),
        )
        calls = self.transcript()
        self.assertTrue(calls)
        self.assertTrue(all(call["argv"][:2] != ["repo", "view"] for call in calls))
        self.assertTrue(all(call["host"] == "" for call in calls))
        self.assertTrue(all("--hostname" in call["argv"] for call in calls), calls)

    def test_context_reads_pin_enterprise_host_and_repository(self) -> None:
        result = self.context(
            "search", "ghe.example.test", "acme/widget", "allocator regression"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        calls = self.transcript()
        self.assertTrue(
            any(
                "--repo" in call["argv"] and "acme/widget" in call["argv"]
                for call in calls
            )
        )
        self.assertTrue(all(call["host"] == "ghe.example.test" for call in calls))
        search_call = calls[0]["argv"]
        self.assertIn("--state", search_call)
        self.assertIn("all", search_call)
        self.assertIn("--limit", search_call)
        self.assertIn("1000", search_call)
        states = {issue["state"] for issue in json.loads(result.stdout)}
        self.assertEqual({"OPEN", "CLOSED"}, states)

    def test_repository_context_selects_fork_parent_with_both_remotes(self) -> None:
        subprocess.run(
            ["git", "remote", "remove", "enterprise"],
            cwd=self.work,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "fork",
                "ssh://git@ghe.example.test/contributor/widget.git",
            ],
            cwd=self.work,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "parent",
                "https://ghe.example.test/acme/widget.git",
            ],
            cwd=self.work,
            check=True,
            capture_output=True,
            text=True,
        )

        result = self.context("repository")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            {
                "github_host": "ghe.example.test",
                "local_repo": "contributor/widget",
                "issue_repo": "acme/widget",
                "default_branch": "trunk",
            },
            json.loads(result.stdout),
        )

    def test_repository_context_rejects_full_name_url_repository_conflict(self) -> None:
        self.environment["GH_CONTRADICTORY_URL"] = "1"

        result = self.context("repository")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("does not match", result.stderr)

    def test_template_discovery_is_host_pinned_and_lists_forms_and_legacy(self) -> None:
        result = self.context("templates", "ghe.example.test", "acme/widget")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            {"regression.yml", "legacy.md"},
            {entry["name"] for entry in json.loads(result.stdout)},
        )
        self.assertEqual(
            [
                "api",
                "--hostname",
                "ghe.example.test",
                "--paginate",
                "repos/acme/widget/contents/.github/ISSUE_TEMPLATE",
            ],
            self.transcript()[0]["argv"],
        )

    def test_missing_template_directory_is_empty_but_other_failures_are_fatal(
        self,
    ) -> None:
        missing_environment = self.environment.copy()
        missing_environment["GH_TEMPLATE_MISSING"] = "1"
        missing = subprocess.run(
            [
                str(CONTEXT_HELPER),
                "templates",
                "ghe.example.test",
                "acme/widget",
            ],
            cwd=self.work,
            env=missing_environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, missing.returncode, missing.stderr)
        self.assertEqual([], json.loads(missing.stdout))

        failure_environment = self.environment.copy()
        failure_environment["GH_TEMPLATE_FAILURE"] = "1"
        failed = subprocess.run(
            [
                str(CONTEXT_HELPER),
                "templates",
                "ghe.example.test",
                "acme/widget",
            ],
            cwd=self.work,
            env=failure_environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, failed.returncode)

        repository_failure_environment = missing_environment.copy()
        repository_failure_environment["GH_REPO_FAILURE"] = "1"
        missing_repository = subprocess.run(
            [
                str(CONTEXT_HELPER),
                "templates",
                "ghe.example.test",
                "acme/widget",
            ],
            cwd=self.work,
            env=repository_failure_environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, missing_repository.returncode)

    def test_preview_renders_every_field_without_writing(self) -> None:
        result = self.issue_create("preview", self.body_file, "bug")
        self.assertIn("Host: ghe.example.test", result.stdout)
        self.assertIn("Repository: acme/widget", result.stdout)
        self.assertIn(f"Title: {self.title}", result.stdout)
        self.assertIn("Labels: bug", result.stdout)
        self.assertIn(self.body_file.read_text(encoding="utf-8"), result.stdout)
        self.assertRegex(result.stdout, r"ISSUE_CREATE:[0-9a-f]{40,64}")
        self.assertEqual([], self.transcript())

    def test_preview_renders_multiple_labels_unambiguously(self) -> None:
        result = self.issue_create("preview", self.body_file, "bug", "regression")

        self.assertIn("Labels: bug, regression", result.stdout)
        self.assertEqual([], self.transcript())

    def test_preview_displays_snapshot_when_source_changes_after_hash(self) -> None:
        approved_body = self.body_file.read_text(encoding="utf-8")
        replacement = "MUTATED AFTER PREVIEW SNAPSHOT\n"
        self.environment["RACE_BODY_FILE"] = str(self.body_file)
        self.environment["RACE_REPLACEMENT"] = replacement

        result = self.issue_create("preview", self.body_file, "bug")

        self.assertEqual(replacement, self.body_file.read_text(encoding="utf-8"))
        self.assertIn(approved_body, result.stdout)
        self.assertNotIn(replacement, result.stdout)
        self.assertEqual([], self.transcript())

    def test_create_rejects_changed_payload_before_gh_write(self) -> None:
        token = self.preview_token("bug")
        self.body_file.write_text("changed after approval\n", encoding="utf-8")
        result = self.issue_create(
            "create", self.body_file, "bug", token=token, check=False
        )
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], self.transcript())

    def test_successful_create_uses_exact_confirmed_payload_without_project_call(
        self,
    ) -> None:
        approved_body = self.body_file.read_text(encoding="utf-8")
        token = self.preview_token("bug", "regression")
        result = self.issue_create(
            "create", self.body_file, "bug", "regression", token=token
        )

        self.assertEqual(
            "https://ghe.example.test/acme/widget/issues/42", result.stdout.strip()
        )
        calls = self.transcript()
        self.assertEqual(1, len(calls))
        call = calls[0]
        snapshot_path = call["body_file"]
        self.assertEqual(
            [
                "issue",
                "create",
                "--repo",
                "acme/widget",
                "--title",
                self.title,
                "--body-file",
                snapshot_path,
                "--label",
                "bug",
                "--label",
                "regression",
            ],
            call["argv"],
        )
        self.assertEqual("ghe.example.test", call["host"])
        self.assertEqual(approved_body, call["body"])
        self.assertNotEqual(str(self.body_file), snapshot_path)
        self.assertFalse(Path(snapshot_path).exists())

    def test_create_publishes_snapshot_when_source_changes_after_hash(self) -> None:
        approved_body = self.body_file.read_text(encoding="utf-8")
        token = self.preview_token("bug")
        replacement = "MUTATED AFTER CREATE SNAPSHOT\n"
        self.environment["RACE_BODY_FILE"] = str(self.body_file)
        self.environment["RACE_REPLACEMENT"] = replacement

        result = self.issue_create("create", self.body_file, "bug", token=token)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(replacement, self.body_file.read_text(encoding="utf-8"))
        calls = self.transcript()
        self.assertEqual(1, len(calls))
        self.assertEqual(approved_body, calls[0]["body"])
        snapshot_path = calls[0]["body_file"]
        self.assertNotEqual(str(self.body_file), snapshot_path)
        self.assertFalse(Path(snapshot_path).exists())


class CreateIssueSkillContractTests(unittest.TestCase):
    def test_skill_resolves_repository_policy_before_issue_context(self) -> None:
        self.assertTrue(SKILL.is_file(), f"missing skill: {SKILL}")
        text = SKILL.read_text(encoding="utf-8")

        policy = text.find("../../lib/repository/policy.md")
        context = text.find("../../lib/github/issue-context.md")
        self.assertGreaterEqual(policy, 0)
        self.assertGreater(context, policy)
        policy_block = text[policy:context]
        self.assertIn("applicable repository instructions", policy_block)
        self.assertIn("missing or conflicting required policy", policy_block)

    def test_skill_orders_complete_preview_confirmation_and_create(self) -> None:
        self.assertTrue(SKILL.is_file(), f"missing skill: {SKILL}")
        text = SKILL.read_text(encoding="utf-8")

        preview = text.find("## Preview the complete mutation")
        confirmation = text.find("## Wait for explicit confirmation")
        create = text.find("## Create exactly the approved issue")
        self.assertGreaterEqual(preview, 0)
        self.assertGreater(confirmation, preview)
        self.assertGreater(create, confirmation)
        preview_block = text[preview:confirmation]
        for field in ("host", "repository", "title", "labels", "complete body"):
            with self.subTest(field=field):
                self.assertIn(field, preview_block.lower())

    def test_skill_requires_discovered_fields_and_open_closed_deduplication(
        self,
    ) -> None:
        self.assertTrue(SKILL.is_file(), f"missing skill: {SKILL}")
        text = SKILL.read_text(encoding="utf-8")

        self.assertIn("required: true", text)
        self.assertIn("DUPLICATE", text)
        self.assertIn("RELATED", text)
        self.assertIn("NO_MATCH", text)
        self.assertIn("open and closed", text.lower())
        self.assertIn("Related: #N", text)
        self.assertIn("stop only for `duplicate`", text.lower())
        self.assertIn("Never invent or reconstruct the preview token", text)
        self.assertIn("../../lib/github/scripts/issue-context.sh", text)


if __name__ == "__main__":
    unittest.main()
