from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import unittest
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from tests.skill_assertions import DEVELOPER_PLUGIN
from tests.test_taskboard import PROJECTS, TOKEN, load_module

SCRIPT = DEVELOPER_PLUGIN / "skills/track-pr/scripts/track_pr.py"
PR_URL = "https://github.com/example/compiler/pull/123"


@contextmanager
def queue_api() -> Iterator[tuple[str, dict[str, Any]]]:
    state: dict[str, Any] = {
        "entries": [],
        "requests": [],
        "confirm_project": True,
        "response_lost": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def reply(self, code: int, payload: Any) -> None:
            content = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            project = parse_qs(urlparse(self.path).query).get("project", ["pypto"])[0]
            state["requests"].append(
                ("GET", self.path, self.headers.get("Authorization"), None)
            )
            entries = [
                entry for entry in state["entries"] if entry["project_id"] == project
            ]
            payload: dict[str, Any] = {"prs": entries}
            if state["confirm_project"]:
                payload["project"] = {"id": state.get("response_project", project)}
            self.reply(200, payload)

        def do_POST(self) -> None:
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            authorization = self.headers.get("Authorization")
            state["requests"].append(("POST", self.path, authorization, data))
            if state.get("redirect_to"):
                self.send_response(307)
                self.send_header("Location", state["redirect_to"])
                self.end_headers()
                return
            if authorization != "Bearer " + TOKEN or state.get("forbidden"):
                self.reply(403, {"error": "token rejected"})
                return
            if state.get("unavailable"):
                self.reply(503, {"error": "unavailable before commit"})
                return
            project = parse_qs(urlparse(self.path).query).get("project", ["pypto"])[0]
            if project != data["project_id"]:
                self.reply(400, {"error": "project mismatch"})
                return
            entry = {
                **data,
                "id": str(uuid.uuid4()),
                "added_by": "test-account",
                "status": "unknown",
            }
            state["entries"].append(entry)
            if state["response_lost"]:
                self.reply(503, {"error": "response lost after commit"})
                return
            self.reply(201, {"entry": entry, "created": True})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


class TrackPRTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helper = load_module("taskboard_track_pr", SCRIPT)
        self.environment = patch.dict(os.environ, {"PYPTO_TASK_API_TOKEN": TOKEN})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_projects_have_independent_entries_and_idempotent_reads(self) -> None:
        with queue_api() as (base, state):
            ids = []
            for project in PROJECTS:
                with self.subTest(project=project):
                    added = self.helper.track(PR_URL, project=project, api_url=base)
                    ids.append(added["entry"]["id"])
                    self.assertFalse(added["already_tracked"])
                    self.assertEqual(added["entry"]["project_id"], project)
                    self.assertEqual(
                        added["tracking_url"], base + "/pending-prs?project=" + project
                    )
                    with patch.object(
                        self.helper, "token", side_effect=AssertionError("no write")
                    ):
                        existing = self.helper.track(
                            PR_URL, project=project, api_url=base
                        )
                    self.assertTrue(existing["already_tracked"])
                    self.assertEqual(existing["entry"]["id"], added["entry"]["id"])
            self.assertEqual(len(set(ids)), len(PROJECTS))
            writes = [row for row in state["requests"] if row[0] == "POST"]
            self.assertEqual(len(writes), len(PROJECTS))
            self.assertTrue(all(row[2] == "Bearer " + TOKEN for row in writes))
            self.assertTrue(
                all(row[2] is None for row in state["requests"] if row[0] == "GET")
            )

    def test_existing_entry_normalizes_url_and_does_not_load_token(self) -> None:
        with queue_api() as (base, state):
            entry = {"id": "stable", "url": PR_URL, "project_id": "serving"}
            state["entries"].append(entry)
            with patch.object(
                self.helper, "token", side_effect=AssertionError("no token")
            ):
                result = self.helper.track(
                    PR_URL.replace("example/compiler", "EXAMPLE/COMPILER") + "/",
                    project="serving",
                    api_url=base,
                )
            self.assertEqual(result["entry"], entry)
            self.assertEqual(len(state["requests"]), 1)

    def test_project_confirmation_failure_stops_before_post(self) -> None:
        with queue_api() as (base, state):
            for configuration in [
                {"confirm_project": False},
                {"confirm_project": True, "response_project": "serving"},
            ]:
                state.update(configuration)
                with self.assertRaises(self.helper.WorkflowError):
                    self.helper.track(PR_URL, project="pypto", api_url=base)
            self.assertTrue(all(row[0] == "GET" for row in state["requests"]))

    def test_bad_pr_origin_or_project_fail_before_network_or_token(self) -> None:
        requests = [
            {"url": "http://127.0.0.1/admin"},
            {"url": PR_URL + "?token=untrusted"},
            {"url": "https://github.com/../repo/pull/1"},
            {"url": PR_URL, "api_url": "https://untrusted.example"},
            {"url": PR_URL, "api_url": "https://taskboard.pypto.cloud/path"},
            {"url": PR_URL, "project": "missing"},
        ]
        for options in requests:
            with self.subTest(options=options):
                with (
                    patch.object(self.helper, "api") as api,
                    patch.object(self.helper, "token") as token,
                    self.assertRaises(self.helper.WorkflowError),
                ):
                    self.helper.track(**options)
                api.assert_not_called()
                token.assert_not_called()

    def test_lost_response_recovers_by_reading_without_repeated_post(self) -> None:
        with queue_api() as (base, state):
            state["response_lost"] = True
            result = self.helper.track(PR_URL, api_url=base)
            self.assertEqual(result["entry"], state["entries"][0])
            self.assertEqual(
                [row[0] for row in state["requests"]], ["GET", "POST", "GET"]
            )

    def test_forbidden_and_uncertain_writes_are_not_retried(self) -> None:
        for flag, expected in [
            ("forbidden", ["GET", "POST"]),
            ("unavailable", ["GET", "POST", "GET"]),
        ]:
            with self.subTest(flag=flag), queue_api() as (base, state):
                state[flag] = True
                with self.assertRaises(self.helper.WorkflowError):
                    self.helper.track(PR_URL, api_url=base)
                self.assertEqual([row[0] for row in state["requests"]], expected)

    def test_authenticated_redirect_is_never_followed(self) -> None:
        with queue_api() as (base, state):
            state["redirect_to"] = base + "/unexpected-target"
            with self.assertRaises(self.helper.WorkflowError):
                self.helper.track(PR_URL, api_url=base)
            self.assertTrue(
                all(
                    urlparse(row[1]).path == "/api/pending-prs"
                    for row in state["requests"]
                )
            )
            self.assertEqual(
                len([row for row in state["requests"] if row[0] == "POST"]), 1
            )

    def test_token_file_permissions_and_environment_precedence(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as folder, queue_api() as (base, state):
            token_path = Path(folder) / "token"
            token_path.write_text(TOKEN)
            token_path.chmod(0o644)
            with patch.dict(
                os.environ,
                {
                    "PYPTO_TASK_API_TOKEN": "",
                    "PYPTO_TASK_API_TOKEN_FILE": str(token_path),
                },
            ):
                if os.name != "nt":
                    with self.assertRaises(self.helper.WorkflowError):
                        self.helper.track(PR_URL, api_url=base)
                    self.assertFalse(any(row[0] == "POST" for row in state["requests"]))
                token_path.chmod(0o600)
                self.assertFalse(
                    self.helper.track(PR_URL, api_url=base)["already_tracked"]
                )
                token_path.chmod(0o644)
                with patch.dict(os.environ, {"PYPTO_TASK_API_TOKEN": TOKEN}):
                    result = self.helper.track(PR_URL, project="serving", api_url=base)
                self.assertEqual(result["entry"]["project_id"], "serving")

    def test_cli_reports_project_link_and_does_not_print_token(self) -> None:
        with queue_api() as (base, _state):
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    PR_URL,
                    "--project",
                    "pypto-lib",
                    "--api-url",
                    base,
                ],
                capture_output=True,
                text=True,
                check=False,
                env=os.environ.copy(),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout)["entry"]["project_id"], "pypto-lib"
            )
            self.assertIn("/pending-prs?project=pypto-lib", result.stdout)
            self.assertNotIn(TOKEN, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
