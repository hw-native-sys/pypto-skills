from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import TypedDict, cast

from tests.skill_assertions import ROOT

CONTEXT_HELPER = ROOT / "lib/github/scripts/issue-context.sh"
SKILL = ROOT / "skills/fix-issue/SKILL.md"


class GHCall(TypedDict):
    argv: list[str]
    host: str
    operation: str


class FixIssuePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.temp_path = Path(temporary_directory.name)
        self.transcript_path = self.temp_path / "gh-transcript.jsonl"
        self.bin_path = self.temp_path / "bin"
        self.bin_path.mkdir()
        self.write_fake_gh()
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "PATH": f"{self.bin_path}{os.pathsep}{self.environment['PATH']}",
                "GH_TRANSCRIPT": str(self.transcript_path),
                "GH_ISSUE_STATE": "OPEN",
                "GH_ISSUE_ASSIGNEE": "maintainer",
                "GH_PROJECT_STATUS": "",
                "GH_LINKED_PR_STATE": "",
                "GH_SECOND_READ_ENABLED": "0",
            }
        )

    def write_fake_gh(self) -> None:
        fake_gh = self.bin_path / "gh"
        fake_gh.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys

argv = sys.argv[1:]
transcript_path = os.environ["GH_TRANSCRIPT"]
try:
    with open(transcript_path, encoding="utf-8") as existing_transcript:
        call_number = sum(1 for _line in existing_transcript) + 1
except FileNotFoundError:
    call_number = 1
is_write = (
    argv[:2] in (["issue", "edit"], ["issue", "create"])
    or "--method" in argv and argv[argv.index("--method") + 1] != "GET"
    or any("mutation" in argument.lower() for argument in argv)
)
with open(transcript_path, "a", encoding="utf-8") as transcript:
    transcript.write(json.dumps({
        "argv": argv,
        "host": os.environ.get("GH_HOST", ""),
        "operation": "write" if is_write else "read",
    }) + "\\n")

if argv[:2] != ["issue", "view"] or "27" not in argv:
    sys.stderr.write(f"unexpected gh invocation: {argv!r}\\n")
    raise SystemExit(91)

use_second_read = (
    call_number >= 2 and os.environ.get("GH_SECOND_READ_ENABLED") == "1"
)

def response_value(name):
    if use_second_read:
        return os.environ.get(f"GH_SECOND_{name}", os.environ.get(f"GH_{name}", ""))
    return os.environ.get(f"GH_{name}", "")

assignee = response_value("ISSUE_ASSIGNEE")
project_status = response_value("PROJECT_STATUS")
linked_state = response_value("LINKED_PR_STATE")
print(json.dumps({
    "number": 27,
    "title": "Allocator regression",
    "body": "Allocator reuse fails.",
    "state": response_value("ISSUE_STATE") or "OPEN",
    "labels": [{"name": "bug"}],
    "assignees": [{"login": assignee}] if assignee else [],
    "url": "https://ghe.example.test/acme/widget/issues/27",
    "projectItems": ([
        {"title": f"Allocator project {index}", "status": {"name": status}}
        for index, status in enumerate(project_status.split("|"), start=1)
    ] if project_status else []),
    "closedByPullRequestsReferences": ([{
        "number": 31,
        "state": linked_state,
        "url": "https://ghe.example.test/acme/widget/pull/31",
        "headRepository": {"nameWithOwner": "contributor/widget"},
        "headRefName": "allocator-regression",
    }] if linked_state else []),
}))
""",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)

    def context(
        self, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        self.assertTrue(
            CONTEXT_HELPER.is_file(), f"missing context helper: {CONTEXT_HELPER}"
        )
        result = subprocess.run(
            [str(CONTEXT_HELPER), *arguments],
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            self.fail(f"issue-context failed:\n{result.stdout}{result.stderr}")
        return result

    def transcript(self) -> list[GHCall]:
        if not self.transcript_path.exists():
            return []
        return [
            cast(GHCall, json.loads(line))
            for line in self.transcript_path.read_text(encoding="utf-8").splitlines()
        ]

    def configure_issue(
        self,
        *,
        state: str = "OPEN",
        assignee: str = "",
        project_status: str = "",
        linked_pr_state: str = "",
    ) -> None:
        self.environment.update(
            {
                "GH_ISSUE_STATE": state,
                "GH_ISSUE_ASSIGNEE": assignee,
                "GH_PROJECT_STATUS": project_status,
                "GH_LINKED_PR_STATE": linked_pr_state,
            }
        )

    def configure_second_read(
        self,
        *,
        state: str | None = None,
        assignee: str | None = None,
        project_status: str | None = None,
        linked_pr_state: str | None = None,
    ) -> None:
        self.environment["GH_SECOND_READ_ENABLED"] = "1"
        for name, value in (
            ("ISSUE_STATE", state),
            ("ISSUE_ASSIGNEE", assignee),
            ("PROJECT_STATUS", project_status),
            ("LINKED_PR_STATE", linked_pr_state),
        ):
            if value is not None:
                self.environment[f"GH_SECOND_{name}"] = value

    def test_assigned_issue_preflight_stops_without_a_write(self) -> None:
        result = self.context(
            "fix-preflight", "ghe.example.test", "acme/widget", "27", check=False
        )
        self.assertEqual(21, result.returncode)
        calls = self.transcript()
        self.assertGreater(len(calls), 0)
        self.assertTrue(all(call["operation"] == "read" for call in calls))
        self.assertTrue(all(call["host"] == "ghe.example.test" for call in calls))
        self.assertTrue(all("acme/widget" in call["argv"] for call in calls))

    def test_closed_issue_is_not_overridden(self) -> None:
        self.configure_issue(state="CLOSED", assignee="maintainer")

        result = self.context(
            "fix-preflight",
            "ghe.example.test",
            "acme/widget",
            "27",
            "--allow-conflict",
            "--approved-conflicts-json",
            '["closed","assigned"]',
            check=False,
        )

        self.assertEqual(20, result.returncode)
        self.assertEqual(["closed", "assigned"], json.loads(result.stdout)["conflicts"])
        self.assertTrue(all(call["operation"] == "read" for call in self.transcript()))

    def test_only_configured_in_progress_status_is_a_conflict(self) -> None:
        self.configure_issue(project_status="In Progress")

        unspecified = self.context(
            "fix-preflight", "ghe.example.test", "acme/widget", "27", check=False
        )
        configured = self.context(
            "fix-preflight",
            "ghe.example.test",
            "acme/widget",
            "27",
            "--in-progress-status",
            "in progress",
            check=False,
        )

        self.assertEqual(0, unspecified.returncode, unspecified.stderr)
        self.assertEqual(22, configured.returncode)

    def test_configured_status_matches_any_project_case_insensitively(self) -> None:
        self.configure_issue(project_status="Backlog|IN PROGRESS")

        result = self.context(
            "fix-preflight",
            "ghe.example.test",
            "acme/widget",
            "27",
            "--in-progress-status",
            "In Progress",
            check=False,
        )

        self.assertEqual(22, result.returncode)
        self.assertEqual("IN PROGRESS", json.loads(result.stdout)["project_status"])

    def test_active_linked_pull_request_is_a_conflict(self) -> None:
        self.configure_issue(linked_pr_state="OPEN")

        result = self.context(
            "fix-preflight", "ghe.example.test", "acme/widget", "27", check=False
        )

        self.assertEqual(23, result.returncode)
        record = json.loads(result.stdout)
        self.assertEqual(
            {
                "number": 31,
                "state": "OPEN",
                "url": "https://ghe.example.test/acme/widget/pull/31",
                "head_repository": "contributor/widget",
                "head_branch": "allocator-regression",
            },
            record["linked_pull_requests"][0],
        )

    def test_closed_linked_pull_request_does_not_block_clean_open_issue(self) -> None:
        self.configure_issue(linked_pr_state="CLOSED")

        result = self.context("fix-preflight", "ghe.example.test", "acme/widget", "27")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            {
                "number",
                "title",
                "body",
                "state",
                "labels",
                "assignees",
                "url",
                "project_status",
                "linked_pull_requests",
                "conflicts",
            },
            set(json.loads(result.stdout)),
        )
        self.assertEqual([], json.loads(result.stdout)["conflicts"])

    def test_merged_linked_pull_request_does_not_block_clean_open_issue(self) -> None:
        self.configure_issue(linked_pr_state="MERGED")

        result = self.context("fix-preflight", "ghe.example.test", "acme/widget", "27")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            "MERGED", json.loads(result.stdout)["linked_pull_requests"][0]["state"]
        )

    def test_allow_conflict_overrides_only_active_work_conflicts(self) -> None:
        scenarios = (
            {"assignee": "maintainer"},
            {"project_status": "Doing"},
            {"linked_pr_state": "OPEN"},
        )
        options = ((), ("--in-progress-status", "doing"), ())
        approved_sets = (
            '["assigned"]',
            '["in_progress"]',
            '["active_pull_request"]',
        )

        for issue, extra_options, approved_set in zip(
            scenarios, options, approved_sets, strict=True
        ):
            with self.subTest(issue=issue):
                self.configure_issue(**issue)
                result = self.context(
                    "fix-preflight",
                    "ghe.example.test",
                    "acme/widget",
                    "27",
                    *extra_options,
                    "--allow-conflict",
                    "--approved-conflicts-json",
                    approved_set,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(all(call["operation"] == "read" for call in self.transcript()))

    def test_combined_conflicts_are_all_emitted_and_both_modes_are_read_only(
        self,
    ) -> None:
        self.configure_issue(
            assignee="maintainer",
            project_status="In Progress",
            linked_pr_state="OPEN",
        )
        arguments = (
            "fix-preflight",
            "ghe.example.test",
            "acme/widget",
            "27",
            "--in-progress-status",
            "in progress",
        )

        blocked = self.context(*arguments, check=False)
        approved_conflicts = '["assigned","in_progress","active_pull_request"]'
        allowed = self.context(
            *arguments,
            "--allow-conflict",
            "--approved-conflicts-json",
            approved_conflicts,
            check=False,
        )

        self.assertEqual(21, blocked.returncode)
        self.assertEqual(0, allowed.returncode, allowed.stderr)
        for result in (blocked, allowed):
            with self.subTest(mode=result.args):
                record = json.loads(result.stdout)
                self.assertEqual(
                    ["assigned", "in_progress", "active_pull_request"],
                    record["conflicts"],
                )
                self.assertEqual([{"login": "maintainer"}], record["assignees"])
                self.assertEqual("In Progress", record["project_status"])
                self.assertEqual("OPEN", record["linked_pull_requests"][0]["state"])

        calls = self.transcript()
        self.assertEqual(2, len(calls))
        self.assertTrue(all(call["operation"] == "read" for call in calls))
        self.assertTrue(all(call["host"] == "ghe.example.test" for call in calls))
        self.assertTrue(all("acme/widget" in call["argv"] for call in calls))

    def test_override_rejects_conflict_set_changed_after_approval(self) -> None:
        self.configure_issue(assignee="maintainer")
        self.configure_second_read(linked_pr_state="OPEN")
        arguments = (
            "fix-preflight",
            "ghe.example.test",
            "acme/widget",
            "27",
        )

        initial = self.context(*arguments, check=False)
        override = self.context(
            *arguments,
            "--allow-conflict",
            "--approved-conflicts-json",
            '["assigned"]',
            check=False,
        )

        self.assertEqual(21, initial.returncode)
        self.assertEqual(21, override.returncode)
        self.assertEqual(["assigned"], json.loads(initial.stdout)["conflicts"])
        self.assertEqual(
            ["assigned", "active_pull_request"],
            json.loads(override.stdout)["conflicts"],
        )
        calls = self.transcript()
        self.assertEqual(2, len(calls))
        self.assertTrue(all(call["operation"] == "read" for call in calls))
        self.assertTrue(all(call["host"] == "ghe.example.test" for call in calls))
        self.assertTrue(all("acme/widget" in call["argv"] for call in calls))

    def test_override_fails_safely_when_approved_conflict_disappears(self) -> None:
        self.configure_issue(assignee="maintainer")
        self.configure_second_read(assignee="")
        arguments = (
            "fix-preflight",
            "ghe.example.test",
            "acme/widget",
            "27",
        )

        initial = self.context(*arguments, check=False)
        override = self.context(
            *arguments,
            "--allow-conflict",
            "--approved-conflicts-json",
            '[ "assigned" ]',
            check=False,
        )

        self.assertEqual(21, initial.returncode)
        self.assertEqual(1, override.returncode)
        self.assertEqual([], json.loads(override.stdout)["conflicts"])
        calls = self.transcript()
        self.assertEqual(2, len(calls))
        self.assertTrue(all(call["operation"] == "read" for call in calls))
        self.assertTrue(all(call["host"] == "ghe.example.test" for call in calls))
        self.assertTrue(all("acme/widget" in call["argv"] for call in calls))

    def test_override_rejects_invalid_approved_conflict_sets_before_read(
        self,
    ) -> None:
        invalid_sets = (
            "not-json",
            '{"assigned":true}',
            "[]",
            '["assigned","assigned"]',
            '["unknown"]',
            '["active_pull_request","assigned"]',
        )

        for approved_set in invalid_sets:
            with self.subTest(approved_set=approved_set):
                result = self.context(
                    "fix-preflight",
                    "ghe.example.test",
                    "acme/widget",
                    "27",
                    "--allow-conflict",
                    "--approved-conflicts-json",
                    approved_set,
                    check=False,
                )
                self.assertNotEqual(0, result.returncode)

        self.assertEqual([], self.transcript())

    def test_approved_conflicts_option_requires_override_mode(self) -> None:
        missing_set = self.context(
            "fix-preflight",
            "ghe.example.test",
            "acme/widget",
            "27",
            "--allow-conflict",
            check=False,
        )
        without_override = self.context(
            "fix-preflight",
            "ghe.example.test",
            "acme/widget",
            "27",
            "--approved-conflicts-json",
            '["assigned"]',
            check=False,
        )

        self.assertEqual(2, missing_set.returncode)
        self.assertEqual(2, without_override.returncode)
        self.assertEqual([], self.transcript())


class FixIssueSkillContractTests(unittest.TestCase):
    def skill_text(self) -> str:
        self.assertTrue(SKILL.is_file(), f"missing skill: {SKILL}")
        return SKILL.read_text(encoding="utf-8")

    def test_workflow_orders_approval_before_every_mutation(self) -> None:
        text = self.skill_text()
        headings = (
            "## Resolve context and run preflight",
            "## Reproduce and inspect",
            "## Design the implementation",
            "## Wait for approval",
            "## Optionally claim and update status",
            "## Create the branch",
            "## Implement the approved design",
            "## Run repository-selected verification",
            "## Hand off the result",
        )
        positions = [text.find(heading) for heading in headings]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(sorted(positions), positions)

        before_approval = text[: positions[3]]
        self.assertNotIn("gh issue edit", before_approval)
        self.assertNotIn("updateProjectV2ItemFieldValue", before_approval)
        self.assertNotIn("git switch --create", before_approval)

    def test_skill_uses_shared_policy_context_and_branch_contracts(self) -> None:
        text = self.skill_text()
        for reference in (
            "../../lib/repository/policy.md",
            "../../lib/github/issue-context.md",
            "../../lib/github/scripts/issue-context.sh",
            "../../lib/github/branch-naming.md",
        ):
            with self.subTest(reference=reference):
                self.assertIn(reference, text)
        self.assertIn('GH_HOST="$GITHUB_HOST" gh issue edit "$ISSUE_NUMBER"', text)
        self.assertIn('--repo "$ISSUE_REPO" --add-assignee @me', text)
        self.assertIn("repository-local", text)

    def test_skill_requires_approval_for_the_complete_conflict_set(self) -> None:
        text = self.skill_text().lower()

        self.assertIn("primary exit is not the complete conflict set", text)
        for conflict in ("`assigned`", "`in_progress`", "`active_pull_request`"):
            with self.subTest(conflict=conflict):
                self.assertIn(conflict, text)
        self.assertIn("explicit approval for each conflict", text)
        self.assertIn("only for an exact match", text)
        self.assertIn("--approved-conflicts-json", text)
        self.assertIn("authoritative override read", text)


if __name__ == "__main__":
    unittest.main()
