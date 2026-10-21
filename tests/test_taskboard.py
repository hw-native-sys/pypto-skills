from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from tests.skill_assertions import DEVELOPER_PLUGIN

CREATE = DEVELOPER_PLUGIN / "skills/create-task/scripts/create_task.py"
READ = DEVELOPER_PLUGIN / "skills/read-task/scripts/read_task.py"
TOKEN = "isolated-taskboard-test-token"
PROJECTS = ("pypto", "pypto-lib", "serving", "simpler")


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, "dont_write_bytecode", True):
        spec.loader.exec_module(module)
    return module


@contextmanager
def task_api() -> Iterator[tuple[str, dict[str, Any]]]:
    state: dict[str, Any] = {
        "tasks": [],
        "requests": [],
        "confirm_project": True,
        "conflict": False,
        "uncertain_post": False,
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
            query = parse_qs(urlparse(self.path).query)
            project = query.get("project", ["pypto"])[0]
            state["requests"].append(
                ("GET", self.path, self.headers.get("Authorization"), None)
            )
            payload: dict[str, Any] = {
                "tasks": [
                    task for task in state["tasks"] if task["project_id"] == project
                ]
            }
            if state["confirm_project"]:
                payload["project"] = {"id": project}
            self.reply(200, payload)

        def do_POST(self) -> None:
            self.mutate("POST")

        def do_PATCH(self) -> None:
            self.mutate("PATCH")

        def mutate(self, method: str) -> None:
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            authorization = self.headers.get("Authorization")
            state["requests"].append((method, self.path, authorization, data))
            if authorization != "Bearer " + TOKEN:
                self.reply(401, {"error": "token rejected"})
                return
            if state.get("redirect_to"):
                self.send_response(302)
                self.send_header("Location", state["redirect_to"])
                self.end_headers()
                return
            project = parse_qs(urlparse(self.path).query).get("project", ["pypto"])[0]
            if method == "PATCH":
                identifier = urlparse(self.path).path.rsplit("/", 1)[1]
                task = next(task for task in state["tasks"] if task["id"] == identifier)
                if (
                    state["conflict"]
                    or data["expected_updated_at"] != task["updated_at"]
                ):
                    self.reply(409, {"error": "concurrent edit"})
                    return
                task.update(
                    {
                        key: value
                        for key, value in data.items()
                        if key != "expected_updated_at"
                    }
                )
                task["updated_at"] += "-updated"
            else:
                number = str(
                    1 + sum(task["project_id"] == project for task in state["tasks"])
                )
                task = {
                    **data,
                    "id": str(uuid.uuid4()),
                    "number": number,
                    "project_id": project,
                    "created_at": "2026-10-21T00:00:00Z",
                    "updated_at": "2026-10-21T00:00:00Z",
                }
                state["tasks"].append(task)
                if state["uncertain_post"]:
                    self.reply(503, {"error": "reply lost after commit"})
                    return
            self.reply(201 if method == "POST" else 200, {"task": task})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


class TaskboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.token_file = Path(self.temp.name) / "token"
        environment = patch.dict(
            os.environ,
            {
                "PYPTO_TASK_API_TOKEN": TOKEN,
                "PYPTO_TASK_API_TOKEN_FILE": str(self.token_file),
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.writer = load_module("taskboard_create", CREATE)
        with patch.dict(sys.modules, {"create_task": self.writer}):
            self.updater = load_module(
                "taskboard_update", CREATE.with_name("update_task.py")
            )
        self.reader = load_module("taskboard_read", READ)

    def args(
        self, base: str, project: str = "pypto", identifier: str = "1"
    ) -> SimpleNamespace:
        return SimpleNamespace(
            api_url=base, website_url=base, project=project, identifier=identifier
        )

    def specification(self) -> dict[str, Any]:
        return {
            "title": "Implement operator",
            "topic": "operator",
            "description": "Retain this goal",
            "analysis": "# Plan\n\n正文",
            "todos": [{"description": "Validate implementation", "done": False}],
        }

    def test_create_read_and_update_in_each_project(self) -> None:
        with task_api() as (base, state):
            for project in PROJECTS:
                with self.subTest(project=project):
                    args = self.args(base, project)
                    created = self.writer.create(args, self.specification())
                    task = created["task"]
                    self.assertEqual(project, task["project_id"])
                    self.assertEqual("1", task["number"])
                    self.assertEqual([task], self.reader.get_tasks(base, project))
                    context = self.reader.task_context([task], "1", base)
                    self.assertEqual(task["id"], context["task"]["id"])
                    updated = self.updater.update(args, {"status": "doing"})["task"]
                    self.assertEqual(task["id"], updated["id"])
                    self.assertEqual("doing", updated["status"])
                    for field in ["analysis", "description", "todos"]:
                        self.assertEqual(task[field], updated[field])
            for method, _, authorization, payload in state["requests"]:
                if method == "GET":
                    self.assertIsNone(authorization)
                else:
                    self.assertEqual("Bearer " + TOKEN, authorization)
                    self.assertNotIn(TOKEN, json.dumps(payload))

    def test_tokens_resolve_without_printing_and_check_file_mode(self) -> None:
        self.token_file.write_text("file-token\n")
        self.token_file.chmod(0o600)
        with patch.dict(os.environ, {"PYPTO_TASK_API_TOKEN": ""}):
            self.assertEqual("file-token", self.writer.get_api_token())
            if os.name != "nt":
                self.token_file.chmod(0o644)
                with self.assertRaises(self.writer.APIError):
                    self.writer.get_api_token()
        self.assertEqual(TOKEN, self.writer.get_api_token())
        self.token_file.unlink()
        with patch.dict(os.environ, {"PYPTO_TASK_API_TOKEN": ""}):
            with self.assertRaises(self.writer.APIError):
                self.writer.get_api_token()

    def test_bad_write_origins_fail_before_loading_credentials(self) -> None:
        for origin in [
            "http://taskboard.pypto.cloud",
            "https://taskboard.pypto.cloud.evil.test",
            "https://user:pass@taskboard.pypto.cloud",
            "https://taskboard.pypto.cloud:444",
            "https://taskboard.pypto.cloud/api/tasks",
        ]:
            with (
                self.subTest(origin=origin),
                patch.object(self.writer, "get_api_token") as token,
            ):
                with self.assertRaises(self.writer.APIError):
                    self.writer.api(origin, "POST", "/api/tasks", {})
                token.assert_not_called()

    def test_authenticated_redirect_is_not_followed(self) -> None:
        with task_api() as (destination, received), task_api() as (source, sent):
            sent["redirect_to"] = destination + "/api/tasks"
            with self.assertRaises(self.writer.APIError) as error:
                self.writer.api(source, "POST", "/api/tasks", {})
            self.assertEqual(302, error.exception.status)
            self.assertEqual([], received["requests"])
            self.assertEqual(1, len(sent["requests"]))

    def test_idempotency_and_uncertain_creation_do_not_repeat_post(self) -> None:
        with task_api() as (base, state):
            state["uncertain_post"] = True
            created = self.writer.create(self.args(base), self.specification())
            self.assertTrue(created["reused_existing_task"])
            repeated = self.writer.create(self.args(base), self.specification())
            self.assertEqual(created["task"]["id"], repeated["task"]["id"])
            self.assertEqual(1, sum(row[0] == "POST" for row in state["requests"]))
            with self.assertRaises(self.writer.WorkflowError):
                self.writer.create(
                    self.args(base), {**self.specification(), "analysis": "# Different"}
                )
            self.assertEqual(1, sum(row[0] == "POST" for row in state["requests"]))

    def test_patch_is_partial_and_conflict_is_not_retried(self) -> None:
        with task_api() as (base, state):
            original = self.writer.create(self.args(base), self.specification())["task"]
            result = self.updater.update(
                self.args(base, identifier=original["id"]), {"priority": "high"}
            )
            self.assertEqual(original["analysis"], result["task"]["analysis"])
            sent = state["requests"][-1][3]
            self.assertEqual({"priority", "expected_updated_at"}, set(sent))
            state["conflict"] = True
            with self.assertRaises(self.writer.WorkflowError):
                self.updater.update(self.args(base), {"status": "done"})
            self.assertEqual(2, sum(row[0] == "PATCH" for row in state["requests"]))
            count = len(state["requests"])
            with self.assertRaises(self.writer.WorkflowError):
                self.updater.update(
                    self.args(base), {"expected_updated_at": "stale", "status": "done"}
                )
            self.assertEqual(count + 1, len(state["requests"]))

    def test_unconfirmed_project_prevents_read_and_writes(self) -> None:
        with task_api() as (base, state):
            state["confirm_project"] = False
            for project in PROJECTS[1:]:
                with self.subTest(project=project):
                    with self.assertRaises(self.writer.WorkflowError):
                        self.writer.create(
                            self.args(base, project), self.specification()
                        )
                    with self.assertRaises(self.writer.WorkflowError):
                        self.updater.update(
                            self.args(base, project), {"status": "doing"}
                        )
                    with self.assertRaises(self.reader.ReadError):
                        self.reader.get_tasks(base, project)
            self.assertTrue(all(row[0] == "GET" for row in state["requests"]))

    def test_project_conflict_and_missing_number_do_not_write(self) -> None:
        with task_api() as (base, state):
            with self.assertRaises(self.writer.WorkflowError):
                self.writer.create(
                    self.args(base, "serving"),
                    {**self.specification(), "project_id": "pypto-lib"},
                )
            with self.assertRaises(self.writer.WorkflowError):
                self.updater.update(self.args(base), {"status": "done"})
            with self.assertRaises(self.reader.ReadError):
                self.reader.task_context([], "1", base)
            self.assertTrue(all(row[0] == "GET" for row in state["requests"]))

    def test_read_hierarchy_dependencies_and_duplicate_number_rejection(self) -> None:
        tasks = [
            dict(
                id="root", number="1", parent_id=None, title="Root", dependency_ids=[]
            ),
            dict(
                id="first",
                number="1.1",
                parent_id="root",
                title="First",
                dependency_ids=[],
            ),
            dict(
                id="second",
                number="1.2",
                parent_id="root",
                title="Second",
                dependency_ids=["first"],
                analysis="# Full analysis",
            ),
        ]
        context = self.reader.task_context(tasks, "1", "https://example.test")
        self.assertEqual(
            ["first", "second"], [task["id"] for task in context["descendants"]]
        )
        self.assertEqual("first", context["descendants"][1]["dependencies"][0]["id"])
        self.assertEqual("second", context["descendants"][0]["dependents"][0]["id"])
        self.assertEqual("# Full analysis", context["descendants"][1]["analysis"])
        child = self.reader.task_context(tasks, "1.2", "https://example.test")
        self.assertEqual(["root"], [task["id"] for task in child["ancestors"]])
        with self.assertRaises(self.reader.ReadError):
            self.reader.task_context(
                [*tasks, {**tasks[1], "id": "duplicate"}], "1.1", "https://example.test"
            )

    def test_cli_read_is_public_and_write_uses_stdin(self) -> None:
        with task_api() as (base, _):
            environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            create = subprocess.run(
                [
                    sys.executable,
                    str(CREATE),
                    "--api-url",
                    base,
                    "--website-url",
                    base,
                    "--project",
                    "serving",
                ],
                input=json.dumps(self.specification()),
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(0, create.returncode, create.stderr)
            environment["PYPTO_TASK_API_TOKEN"] = ""
            read = subprocess.run(
                [
                    sys.executable,
                    str(READ),
                    "1",
                    "--project",
                    "serving",
                    "--api-url",
                    base,
                    "--website-url",
                    base,
                ],
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(0, read.returncode, read.stderr)
            result = json.loads(read.stdout)
            self.assertEqual("serving", result["project_id"])
            self.assertIn("project=serving", result["task_url"])
            for output in [create.stdout, create.stderr, read.stdout, read.stderr]:
                self.assertNotIn(TOKEN, output)


if __name__ == "__main__":
    unittest.main()
