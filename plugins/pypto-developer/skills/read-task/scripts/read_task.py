#!/usr/bin/env python3
"""Read a PyPTO task and its context by exact hierarchical number (GET only)."""

import argparse
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

NUMBER = re.compile(r"[1-9][0-9]*(?:\.[1-9][0-9]*)*")
DEFAULT_WEBSITE = "https://taskboard.pypto.cloud"


class ReadError(Exception):
    pass


def origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ReadError("地址必须是 HTTP(S) 网站根地址，不含账户、路径、查询或片段")
    # Validate the port before making a request.
    parsed.port
    return value.rstrip("/")


def get_tasks(base, project="pypto"):
    request = Request(base + "/api/tasks" + ("?project=" + project if project != "pypto" else ""), headers={
        "Accept": "application/json", "Cache-Control": "no-cache",
    }, method="GET")
    try:
        # Read the public task API directly; no credentials or SSH tunnel are needed.
        with build_opener(ProxyHandler({})).open(request, timeout=15) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise ReadError(f"读取任务失败：HTTP {error.code}") from None
    except (URLError, TimeoutError, OSError) as error:
        raise ReadError(f"无法访问任务 API：{error}") from None
    except (ValueError, UnicodeError):
        raise ReadError("任务 API 未返回有效 JSON") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
        raise ReadError("任务 API 响应缺少 tasks 数组")
    if project != "pypto" and (payload.get("project") or {}).get("id") != project:
        raise ReadError("API 未确认所选项目空间，停止读取")
    return payload["tasks"]


def number_key(task):
    return tuple(int(part) for part in task["number"].split("."))


def task_context(tasks, number, website):
    if not NUMBER.fullmatch(number):
        raise ReadError("任务编号格式应为 3 或 3.2.1，各段为不带前导零的正整数")
    by_id = {}
    children = {}
    dependents = {}
    for task in tasks:
        if (not isinstance(task, dict) or not isinstance(task.get("id"), str)
                or not task["id"] or task["id"] in by_id
                or not isinstance(task.get("number"), str)
                or not NUMBER.fullmatch(task["number"])
                or not isinstance(task.get("dependency_ids", []), list)
                or any(not isinstance(item, str) for item in task.get("dependency_ids", []))
                or (task.get("parent_id") is not None and not isinstance(task["parent_id"], str))):
            raise ReadError("任务 API 返回了无效的 ID、编号或关系数据")
        by_id[task["id"]] = task
        children.setdefault(task.get("parent_id"), []).append(task)
        for identifier in task.get("dependency_ids", []):
            dependents.setdefault(identifier, []).append(task)
    matches = [task for task in tasks if task["number"] == number]
    if not matches:
        raise ReadError(f"任务编号 {number} 不存在；可能已删除或调整层级，请确认当前编号")
    if len(matches) != 1:
        raise ReadError(f"任务编号 {number} 对应多个任务，无法唯一定位")
    target = matches[0]

    def summary(task):
        fields = ("id", "number", "title", "parent_id", "status", "priority", "owner", "owner_user_id", "owner_user", "owner_label", "subject")
        return {name: task.get(name) for name in fields}

    def complete(task):
        return {**task,
                "dependencies": [summary(by_id[item]) if item in by_id else {"id": item, "missing": True}
                                 for item in task.get("dependency_ids", [])],
                "dependents": [summary(item) for item in sorted(dependents.get(task["id"], []), key=number_key)]}

    ancestors = []
    visited = {target["id"]}
    parent = target.get("parent_id")
    while parent is not None:
        if parent in visited or parent not in by_id:
            raise ReadError("任务上级关系存在环或缺失")
        visited.add(parent)
        ancestors.append(summary(by_id[parent]))
        parent = by_id[parent].get("parent_id")
    ancestors.reverse()

    descendants = []
    pending = list(reversed(sorted(children.get(target["id"], []), key=number_key)))
    visited = {target["id"]}
    while pending:
        child = pending.pop()
        if child["id"] in visited:
            raise ReadError("任务下层关系存在环")
        visited.add(child["id"])
        descendants.append(complete(child))
        pending.extend(reversed(sorted(children.get(child["id"], []), key=number_key)))
    return {"task": complete(target), "ancestors": ancestors, "descendants": descendants,
            "task_url": website + "/?task=" + quote(target["id"], safe="")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("number", help="完整任务编号，例如 3.2")
    parser.add_argument("--project", choices=["pypto","pypto-lib","serving","simpler"], default="pypto", help="任务所在项目空间，默认 pypto")
    parser.add_argument("--api-url", default=DEFAULT_WEBSITE, help="默认公网 HTTPS 网站根地址，不含 /api/tasks")
    parser.add_argument("--website-url", default=DEFAULT_WEBSITE, help="生成任务链接使用的网站根地址")
    args = parser.parse_args()
    try:
        number = args.number.strip()
        if not NUMBER.fullmatch(number):
            raise ReadError("任务编号格式应为 3 或 3.2.1，各段为不带前导零的正整数")
        base, website = origin(args.api_url), origin(args.website_url)
        result = task_context(get_tasks(base) if args.project == "pypto" else get_tasks(base,args.project), number, website)
        if args.project != "pypto":
            result["task_url"] = result["task_url"].replace("/?task=", "/?project="+args.project+"&task=")
        result["project_id"] = args.project
    except (ReadError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
