"""Add one explicitly identified PR to the taskboard's pending merge list."""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
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


def origin(value):
    try:
        parsed = urlparse(value)
        allowed = (
            parsed.scheme == "https"
            and parsed.hostname == "taskboard.pypto.cloud"
            and parsed.port in {None, 443}
        ) or (
            parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        )
        if (
            not allowed
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        raise WorkflowError(
            "API 地址必须为正式 HTTPS 根地址或显式指定的 HTTP 回环根地址"
        ) from None
    return value.rstrip("/")


def canonical(value):
    match = (
        re.fullmatch(
            r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)/?",
            value.strip(),
        )
        if isinstance(value, str)
        else None
    )
    if (
        not match
        or any(part in {".", ".."} for part in match.groups()[:2])
        or len(value) > 1000
    ):
        raise WorkflowError("请提供完整的 GitHub PR 链接")
    return (
        f"https://github.com/{match[1].lower()}/{match[2].lower()}/pull/{int(match[3])}"
    )


def token():
    value = os.environ.get("PYPTO_TASK_API_TOKEN", "").strip()
    if not value:
        path = Path(
            os.environ.get("PYPTO_TASK_API_TOKEN_FILE")
            or "~/.config/pypto-taskboard/token"
        ).expanduser()
        if not path.is_file():
            raise WorkflowError("请配置任务网站的个人 API 令牌")
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise WorkflowError("令牌文件权限需要为 600")
        value = path.read_text().strip()
    if (
        not value
        or len(value) > 512
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
    ):
        raise WorkflowError("任务网站 API 令牌格式不正确")
    return value


def api(base, method="GET", payload=None, project="pypto"):
    base = origin(base)
    headers = {"Content-Type": "application/json"}
    if method == "POST":
        headers["Authorization"] = "Bearer " + token()
    request = Request(
        base + "/api/pending-prs?project=" + project,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(
            request, timeout=20
        ) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            message = json.load(error).get("error", f"HTTP {error.code}")
        except (ValueError, AttributeError):
            message = f"HTTP {error.code}"
        raise APIError(message, error.code) from None
    except (URLError, OSError, ValueError, TimeoutError):
        raise APIError("无法确认任务网站 API 响应") from None


def track(url, project="pypto", api_url=DEFAULT_API):
    url, base = canonical(url), origin(api_url)
    if project not in {"pypto", "pypto-lib", "serving", "simpler"}:
        raise WorkflowError("项目空间无效")

    def lookup():
        data = api(base, project=project)
        if not isinstance(data, dict) or not isinstance(data.get("prs"), list):
            raise WorkflowError("待合入列表响应格式不正确")
        if (data.get("project") or {}).get("id") != project or any(
            not isinstance(item, dict) or item.get("project_id") != project
            for item in data["prs"]
        ):
            raise WorkflowError("API 未确认所选项目空间，停止操作")
        return next(
            (
                item
                for item in data["prs"]
                if item.get("url", "").lower() == url.lower()
            ),
            None,
        )

    entry = lookup()
    existing = bool(entry)
    if not entry:
        try:
            result = api(
                base, "POST", {"url": url, "project_id": project}, project=project
            )
        except APIError as error:
            if error.status is not None and 400 <= error.status < 500:
                raise WorkflowError(f"添加被拒绝：{error}") from None
            result = None
        entry = lookup()
        if not entry:
            raise WorkflowError("未能确认添加结果，请重新读取列表，不要直接重复提交")
        expected = result.get("entry") if isinstance(result, dict) else None
        if expected and (
            expected.get("id") != entry.get("id")
            or expected.get("url") != entry.get("url")
        ):
            raise WorkflowError("添加结果与列表不一致，请人工核对")
        existing = isinstance(result, dict) and not result.get("created", True)
    return {
        "entry": entry,
        "already_tracked": existing,
        "tracking_url": base + "/pending-prs?project=" + project,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr_url")
    parser.add_argument(
        "--project",
        choices=["pypto", "pypto-lib", "serving", "simpler"],
        default="pypto",
    )
    parser.add_argument("--api-url", default=DEFAULT_API)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                track(args.pr_url, args.project, args.api_url),
                ensure_ascii=False,
                indent=2,
            )
        )
    except (WorkflowError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
