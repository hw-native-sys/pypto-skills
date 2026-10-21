"""Create a PyPTO cloud task. Read the task specification from stdin."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


DEFAULT_API = "https://taskboard.pypto.cloud"


class WorkflowError(Exception):
    pass


class APIError(WorkflowError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def api_origin(value):
    try:
        parsed = urlparse(value)
        port = parsed.port
        valid = (parsed.scheme == "https" and parsed.hostname == "taskboard.pypto.cloud" and port in {None, 443}) or (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"})
        if not valid or parsed.username is not None or parsed.password is not None or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise APIError("API 地址需为 https://taskboard.pypto.cloud 或显式指定的本地 HTTP 回环根地址") from None
    return value.rstrip("/")


def get_api_token():
    token = os.environ.get("PYPTO_TASK_API_TOKEN", "").strip()
    if not token:
        configured = os.environ.get("PYPTO_TASK_API_TOKEN_FILE")
        token_file = Path(configured).expanduser() if configured else Path.home() / ".config/pypto-taskboard/token"
        if not token_file.is_file():
            raise APIError("修改任务需要 API 令牌；请在网站「我的账号」创建并配置 PYPTO_TASK_API_TOKEN 或令牌文件")
        if os.name != "nt" and token_file.stat().st_mode & 0o077:
            raise APIError("API 令牌文件权限需要设为 600")
        token = token_file.read_text().strip()
    if not token or len(token) > 512 or any(ord(character) < 33 or ord(character) > 126 for character in token):
        raise APIError("API 令牌格式不正确，请检查本机令牌配置")
    return token


def api(base, method, path, payload=None):
    base = api_origin(base)
    if not isinstance(path, str) or not path.startswith("/api/") or "#" in path:
        raise APIError("API 路径需要以 /api/ 开头")
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if method not in {"GET", "HEAD"}:
        headers["Authorization"] = "Bearer " + get_api_token()
    request = Request(base + path, body, headers, method=method)
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            message = json.load(error).get("error", f"HTTP {error.code}")
        except (ValueError, AttributeError):
            message = f"HTTP {error.code}"
        raise APIError(message, error.code) from None
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise APIError(f"无法确认 API 响应：{error}") from None


def validate_spec(spec):
    if not isinstance(spec, dict):
        raise WorkflowError("输入必须是 JSON 对象")
    project_id = spec.get("project_id", "pypto")
    if project_id not in {"pypto", "pypto-lib", "serving", "simpler"}:
        raise WorkflowError("project_id 需要为 pypto、pypto-lib、serving 或 simpler")
    title, topic = spec.get("title", ""), spec.get("topic", "")
    analysis = spec.get("analysis", spec.get("document", ""))
    description = spec.get("description", "")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
        raise WorkflowError("任务标题需要 1–200 字")
    if not isinstance(topic, str) or len(topic) > 100 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", topic):
        raise WorkflowError("topic 请使用小写英文、数字和连字符")
    if not isinstance(analysis, str) or len(analysis.encode()) > 2 * 1024 * 1024:
        raise WorkflowError("详细分析需要 Markdown 文本，最多 2 MiB")
    if not isinstance(description, str) or len(description) > 10000:
        raise WorkflowError("任务描述最多 10000 字")
    actor = spec.get("actor", "")
    if not isinstance(actor, str) or len(actor.strip()) > 100 or any(ord(c) < 32 for c in actor):
        raise WorkflowError("修改署名最多 100 字，不能包含换行")
    notes = spec.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 5000:
        raise WorkflowError("备注最多 5000 字")
    status, priority = spec.get("status", "todo"), spec.get("priority", "medium")
    if status not in {"todo", "doing", "done"} or priority not in {"high", "medium", "low"}:
        raise WorkflowError("状态或优先级不正确")
    owner = spec.get("owner", "")
    if not isinstance(owner, str) or len(owner.strip()) > 100 or any(ord(c) < 32 for c in owner):
        raise WorkflowError("负责人最多 100 字，不能包含换行")
    owner_user_id = spec.get("owner_user_id")
    if "owner_user_id" in spec and owner_user_id is not None and (not isinstance(owner_user_id, str) or not re.fullmatch(r"[0-9a-f]{32}", owner_user_id)):
        raise WorkflowError("owner_user_id 需要用户账号 ID 或 null")
    subject = spec.get("subject", "")
    if not isinstance(subject, str) or len(subject.strip()) > 100 or any(ord(c) < 32 for c in subject):
        raise WorkflowError("主题最多 100 字，不能包含换行")
    attachments = spec.get("attachment_ids", [])
    if not isinstance(attachments, list) or len(attachments) > 20 or any(not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f-]{36}", identifier) for identifier in attachments):
        raise WorkflowError("attachment_ids 必须是最多 20 个已上传附件 ID 的列表")
    dependencies = spec.get("dependency_ids", [])
    if not isinstance(dependencies, list) or len(dependencies) > 200 or any(not isinstance(item, str) or not item or len(item) > 200 for item in dependencies):
        raise WorkflowError("dependency_ids 必须是最多 200 个同层前置任务 ID 的列表")
    parent = spec.get("parent_id") or None
    if parent is not None and not isinstance(parent, str):
        raise WorkflowError("parent_id 必须是上级任务 ID")
    prs = spec.get("pr_urls", [])
    if not isinstance(prs, list) or len(prs) > 20 or any(not isinstance(url, str) for url in prs):
        raise WorkflowError("pr_urls 必须是最多 20 个完整 PR 链接的列表")
    for url in prs:
        parsed = urlparse(url.strip())
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9]\d*(?:/(?:files|commits|checks))?/?", parsed.path):
            raise WorkflowError("请提供完整的 GitHub PR 链接")
    issues = spec.get("issue_urls", [])
    if not isinstance(issues, list) or len(issues) > 20:
        raise WorkflowError("issue_urls 必须是最多 20 个完整 Issue 链接的列表")
    unique_issues = {}
    for url in issues:
        canonical = github_link(url, issue_only=True)
        unique_issues.setdefault(canonical.lower(), canonical)
    issues = list(unique_issues.values())
    todos = spec.get("todos", [])
    if not isinstance(todos, list) or len(todos) > 100:
        raise WorkflowError("todos 必须是最多 100 条 TODO 的列表")
    normalized, identifiers = [], set()
    for todo in todos:
        if not isinstance(todo, dict):
            raise WorkflowError("TODO 数据格式不正确")
        todo_description, done = todo.get("description", ""), todo.get("done", False)
        if not isinstance(todo_description, str) or not 1 <= len(todo_description.strip()) <= 2000 or not isinstance(done, bool):
            raise WorkflowError("TODO 描述需要 1–2000 字，done 必须是布尔值")
        item = {"description": todo_description.strip(), "done": done, "link_url": github_link(todo.get("link_url", ""))}
        if "id" in todo:
            try:
                item["id"] = str(uuid.UUID(todo["id"]))
            except (ValueError, TypeError, AttributeError):
                raise WorkflowError("TODO ID 必须为 UUID") from None
            if item["id"] in identifiers:
                raise WorkflowError("TODO ID 不能重复")
            identifiers.add(item["id"])
        normalized.append(item)
    return {"title": title.strip(), "notes": notes, "status": status,
            "priority": priority, "owner": owner.strip(), **({"owner_user_id": owner_user_id} if "owner_user_id" in spec else {}), "subject": subject.strip(), "attachment_ids": sorted(set(attachments)), "parent_id": parent,
            "dependency_ids": sorted(set(dependencies)),
            "pr_urls": prs, "issue_urls": issues, "todos": normalized, "description": description.strip(), "analysis": analysis,
            "actor": actor.strip(), "creation_key": "pypto:" + topic}


def github_link(value, issue_only=False):
    if not isinstance(value, str) or len(value) > 2000:
        raise WorkflowError("GitHub 链接格式不正确")
    value = value.strip()
    if not value and not issue_only:
        return ""
    parsed = urlparse(value)
    kinds = "issues" if issue_only else "(?:issues|pull)"
    match = re.fullmatch(rf"/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/({kinds})/([1-9][0-9]*)(?:/(?:files|commits|checks))?/?", parsed.path)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or not match or re.search(r"\s", value):
        raise WorkflowError("请提供完整 GitHub Issue 链接" if issue_only else "TODO 需要完整 GitHub PR 或 Issue 链接")
    owner, repo, kind, number = match.groups()
    if owner in {".", ".."} or repo in {".", ".."} or kind == "issues" and parsed.path.rstrip("/").endswith(("/files", "/checks", "/commits")):
        raise WorkflowError("GitHub 链接格式不正确")
    return f"https://github.com/{owner}/{repo}/{kind}/{number}"


def same_todos(saved, requested):
    return len(saved) == len(requested) and all(
        all(current.get(name) == value for name, value in expected.items())
        for current, expected in zip(saved, requested)
    )


def matching_task(tasks, data):
    legacy_path = "pypto-" + data["creation_key"].removeprefix("pypto:") + "-plan.md"
    matches = [task for task in tasks if task.get("creation_key") == data["creation_key"] or legacy_path in task.get("doc_paths", [])]
    if not matches:
        return None
    task = matches[0]
    if len(matches) != 1 or task["title"] != data["title"] or task.get("parent_id") != data["parent_id"]:
        raise WorkflowError("此创建标识已对应其他任务，请选择新 topic 或明确编辑已有任务")
    if task.get("subject", "") != data["subject"] or task.get("attachment_ids", []) != data["attachment_ids"]:
        raise WorkflowError("任务已存在且主题或附件不同；请编辑已有任务，不会自动覆盖")
    if task.get("issue_urls", []) != data["issue_urls"] or not same_todos(task.get("todos", []), data["todos"]):
        raise WorkflowError("任务已存在且 Issue 或 TODO 内容不同，不会自动覆盖")
    if "owner_user_id" in data and task.get("owner_user_id") != data["owner_user_id"]:
        raise WorkflowError("任务已存在且负责人账号不同；请明确编辑已有任务，不会自动覆盖")
    for name in ("description", "analysis"):
        if task.get(name, "") != data[name]:
            raise WorkflowError("任务已存在且正文不同，不会自动覆盖；请编辑已有任务或选择新 topic")
    return task


def create(args, spec):
    if getattr(args,"project",None):
        if "project_id" in spec and spec["project_id"] != args.project:
            raise WorkflowError("--project 与 project_id 不一致")
        spec = {**spec,"project_id":args.project}
    data = validate_spec(spec)
    data["project_id"] = spec.get("project_id","pypto")
    task_path = "/api/tasks" + ("?project=" + data["project_id"] if data["project_id"] != "pypto" else "")
    base = api_origin(args.api_url)
    metadata = api(base, "GET", task_path)
    if data["project_id"] != "pypto" and (metadata.get("project") or {}).get("id") != data["project_id"]:
        raise WorkflowError("API 未确认所选项目空间，停止创建")
    tasks = metadata["tasks"]
    existing = matching_task(tasks, data)
    if data["parent_id"] and not any(task["id"] == data["parent_id"] for task in tasks):
        raise WorkflowError("上级任务不存在")
    by_id = {task["id"]: task for task in tasks}
    if any(not by_id.get(item) or by_id[item].get("parent_id") != data["parent_id"] for item in data["dependency_ids"]):
        raise WorkflowError("前置任务必须是同一上级下的已有任务")
    reused = existing is not None
    if not existing:
        try:
            response = api(base, "POST", task_path, data)
            existing = response["task"]
            reused = response.get("reused_existing_task", False)
        except APIError as error:
            if error.status is not None and 400 <= error.status < 500:
                raise WorkflowError(f"任务创建被拒绝：{error}") from None
            try:
                existing = matching_task(api(base, "GET", task_path)["tasks"], data)
            except WorkflowError:
                existing = None
            if not existing:
                raise WorkflowError(f"任务创建结果未确认：{error}。先读取任务列表查找 creation_key，不要直接重复 POST。") from None
            reused = True
    if existing.get("analysis") != data["analysis"] or existing.get("description") != data["description"] or existing.get("parent_id") != data["parent_id"]:
        raise WorkflowError("API 返回的任务正文与请求不一致，请核对任务")
    if existing.get("issue_urls", []) != data["issue_urls"] or not same_todos(existing.get("todos", []), data["todos"]):
        raise WorkflowError("API 返回的 Issue 或 TODO 与请求不一致，请核对任务")
    return {"task": existing, "task_url": args.website_url.rstrip("/") + "/?" + ("project=" + data["project_id"] + "&" if data["project_id"] != "pypto" else "") + "task=" + quote(existing["id"]), "reused_existing_task": reused}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", choices=["pypto","pypto-lib","serving","simpler"], help="项目空间，默认 pypto；也可在 JSON 中使用 project_id")
    parser.add_argument("--api-url", default=DEFAULT_API, help="默认公网 HTTPS API；可显式指定本地 HTTP 回环地址")
    parser.add_argument("--docs-root", help=argparse.SUPPRESS)  # Legacy flag; no files are written.
    parser.add_argument("--website-url", default="https://taskboard.pypto.cloud")
    args = parser.parse_args()
    try:
        result = create(args, json.load(sys.stdin))
    except (WorkflowError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
