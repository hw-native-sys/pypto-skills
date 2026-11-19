from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.skill_assertions import ROOT

HELPER = ROOT / "skills/clean-branches/scripts/merged-pr-heads.sh"

SHA_A = "a" * 40
SHA_B = "b" * 40
HOST = "github.com"
REPO = "acme/widget"

FAKE_GH = """#!/usr/bin/env python3
import json
import os
import sys

arguments = sys.argv[1:]
with open(os.environ["GH_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(arguments) + "\\n")
if arguments[:2] == ["pr", "list"]:
    sys.stdout.write("[]")
    raise SystemExit(0)
if "--slurp" in arguments and ("--jq" in arguments or "--template" in arguments):
    sys.stderr.write("the `--slurp` option is not supported with `--jq`\\n")
    raise SystemExit(2)
exit_code = int(os.environ.get("FAKE_GH_EXIT", "0"))
if exit_code:
    sys.stderr.write("gh api failed\\n")
    raise SystemExit(exit_code)
sys.stdout.write(os.environ.get("FAKE_GH_STDOUT", "[]"))
"""


def pull_request(
    number: int = 17,
    *,
    ref: str = "topic",
    sha: str = SHA_A,
    owner: str = "forkowner",
    merged: bool = True,
    head_repo: bool = True,
) -> dict[str, Any]:
    return {
        "number": number,
        "state": "closed",
        "merged_at": "2026-01-01T00:00:00Z" if merged else None,
        "head": {
            "ref": ref,
            "sha": sha,
            "repo": (
                {"owner": {"login": owner}, "name": "widget"} if head_repo else None
            ),
        },
    }


def pages(*page_values: list[dict[str, Any]]) -> str:
    return json.dumps(list(page_values))


class MergedPrHeadsTests(unittest.TestCase):
    def setUp(self) -> None:
        if not HELPER.is_file():
            self.skipTest(f"missing production helper: {HELPER}")

        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)
        self.bin_path = self.root / "bin"
        self.bin_path.mkdir()
        self.gh_log = self.root / "gh-args.jsonl"
        fake_gh = self.bin_path / "gh"
        fake_gh.write_text(FAKE_GH, encoding="utf-8")
        fake_gh.chmod(0o755)

    def run_helper(
        self,
        *arguments: str,
        stdout: str = "[]",
        gh_exit: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        if not arguments:
            arguments = (HOST, REPO, "forkowner:", "topic")
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin_path}{os.pathsep}{environment['PATH']}",
                "GH_LOG": str(self.gh_log),
                "FAKE_GH_STDOUT": stdout,
                "FAKE_GH_EXIT": str(gh_exit),
            }
        )
        return subprocess.run(
            [str(HELPER), *arguments],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def gh_calls(self) -> list[list[str]]:
        return [
            json.loads(line)
            for line in self.gh_log.read_text(encoding="utf-8").splitlines()
        ]

    def test_forks_query_host_pinned_rest_and_print_merged_sha(self) -> None:
        result = self.run_helper(stdout=pages([pull_request()]))

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(SHA_A + "\n", result.stdout)
        self.assertEqual(
            [
                [
                    "api",
                    "--hostname",
                    HOST,
                    "--method",
                    "GET",
                    "repos/acme/widget/pulls",
                    "-f",
                    "state=closed",
                    "-f",
                    "head=forkowner:topic",
                    "-f",
                    "per_page=100",
                    "--paginate",
                    "--slurp",
                ]
            ],
            self.gh_calls(),
        )

    def test_empty_prefix_verifies_base_repository_owner(self) -> None:
        matching = self.run_helper(
            HOST,
            REPO,
            "",
            "topic",
            stdout=pages([pull_request(owner="acme")]),
        )
        outsider = self.run_helper(
            HOST,
            REPO,
            "",
            "topic",
            stdout=pages([pull_request(owner="outsider")]),
        )

        self.assertEqual(0, matching.returncode, matching.stderr)
        self.assertEqual(SHA_A + "\n", matching.stdout)
        self.assertEqual(0, outsider.returncode, outsider.stderr)
        self.assertEqual("", outsider.stdout)
        self.assertEqual(
            ["head=acme:topic", "head=acme:topic"],
            [call[9] for call in self.gh_calls()],
        )

    def test_excludes_unmerged_wrong_ref_wrong_owner_and_deleted_repo(self) -> None:
        result = self.run_helper(
            stdout=pages(
                [
                    pull_request(merged=False),
                    pull_request(ref="other"),
                    pull_request(owner="outsider"),
                    pull_request(head_repo=False),
                    pull_request(sha=SHA_B),
                ]
            )
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(SHA_B + "\n", result.stdout)

    def test_outputs_merged_pull_requests_in_number_order(self) -> None:
        result = self.run_helper(
            stdout=pages(
                [
                    pull_request(18, sha=SHA_B),
                    pull_request(17, sha=SHA_A),
                ]
            )
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(f"{SHA_A}\n{SHA_B}\n", result.stdout)

    def test_flattens_paginated_pages(self) -> None:
        result = self.run_helper(
            stdout=pages(
                [pull_request(17, sha=SHA_A)],
                [pull_request(18, sha=SHA_B)],
            )
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(f"{SHA_A}\n{SHA_B}\n", result.stdout)

    def test_empty_results_succeed_with_empty_stdout(self) -> None:
        for payload in ("[]", json.dumps([[]]), json.dumps([[], []])):
            with self.subTest(payload=payload):
                result = self.run_helper(stdout=payload)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stdout)

    def test_deleted_head_repository_yields_no_match(self) -> None:
        result = self.run_helper(stdout=pages([pull_request(head_repo=False)]))

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    def test_gh_failure_fails_closed(self) -> None:
        result = self.run_helper(gh_exit=1)

        self.assertNotEqual(0, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("lookup failed", result.stderr)

    def test_malformed_responses_fail_closed(self) -> None:
        malformed_pages = (
            "not-json",
            json.dumps({"not": "an array"}),
            pages([pull_request(sha="abc")]),
            pages([pull_request(ref="")]),
            pages([pull_request(owner="")]),
            pages([{"number": "17", "state": "closed", "head": {}}]),
        )
        for payload in malformed_pages:
            with self.subTest(payload=payload):
                result = self.run_helper(stdout=payload)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("", result.stdout)

    def test_rejects_invalid_arguments(self) -> None:
        invalid_arguments = (
            ("only-one-argument",),
            (HOST, "widget", "forkowner:", "topic"),
            ("bad/host", REPO, "forkowner:", "topic"),
            (HOST, REPO, "forkowner", "topic"),
            (HOST, REPO, "forkowner:", ""),
            (HOST, REPO, "forkowner:", "bad:name"),
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                result = self.run_helper(*arguments)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("", result.stdout)

    def test_branch_names_with_slashes_are_passed_exactly(self) -> None:
        result = self.run_helper(
            HOST,
            REPO,
            "forkowner:",
            "feature/thing",
            stdout=pages([pull_request(ref="feature/thing")]),
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(SHA_A + "\n", result.stdout)
        self.assertIn("head=forkowner:feature/thing", self.gh_calls()[0])


if __name__ == "__main__":
    unittest.main()
