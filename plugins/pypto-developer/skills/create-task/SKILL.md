---
name: create-task
description: Use when creating or updating tasks on taskboard.pypto.cloud for PyPTO, pypto-lib, serving, or simpler, including Markdown analysis, subtasks, dependencies, assignees, PRs, issues, and TODOs.
---

# Create or Update Task

Create and update development work through the taskboard HTTPS API. Store the
user's overall goal in `description` and detailed design, implementation, and
validation context in Markdown `analysis`. Follow the user's documentation
policy; no standalone design document is created by these helpers.

Never run the full system-test suite locally. Run only system-test cases
directly relevant to the changed or requested scope; use CI for the full
system-test suite.

## Project and authorization

The default service is `https://taskboard.pypto.cloud`; no SSH tunnel,
Tailscale, local server, or repository checkout is needed. Projects are
`pypto` (default), `pypto-lib`, `serving`, and `simpler`. Use the project the user
identified. Numbers are unique only within a project; do not guess another
project when a number is absent. The helpers verify a non-default project's
identity before writing and stop if the server does not confirm it.

Public reads need no credentials. Writes require the acting user's personal
API token, created under the website's **My account → API tokens**. Configure:

1. `PYPTO_TASK_API_TOKEN` through a credential manager; or
2. `PYPTO_TASK_API_TOKEN_FILE` pointing to a token file; or
3. the default `~/.config/pypto-taskboard/token` file.

On Unix, token files must have mode `600`. Do not read a token into chat, print
it, put it in task analysis, or pass it in command arguments. No token is
bundled with this plugin. Tokens can edit tasks but cannot administer accounts;
the server attributes changes to the authenticated account. Report 401/403
responses instead of substituting another account. Authenticated requests go
only to the canonical HTTPS origin or an explicitly selected HTTP loopback
service, and never follow redirects. There is no automatic local fallback.

## Create

Resolve scripts relative to this `SKILL.md`, then run
[scripts/create_task.py](scripts/create_task.py) with a JSON object on stdin:

```bash
python3 /path/to/create-task/scripts/create_task.py --project pypto-lib < /tmp/task-input.json
```

The JSON requires `title` and `topic`; fill `description` and `analysis` from
the user's actual scope. `topic` is a project-local lowercase slug used as
`creation_key: pypto:<topic>` for idempotency. `project_id` in JSON may specify
the project instead of `--project`; if both are present they must agree.
See [task fields](references/task-fields.md) for the complete input shape.

Read existing tasks before choosing parent or dependency IDs. For planned
subtasks, create prerequisites first and record actual direct dependencies;
ordering, priority, or a recommendation alone does not imply dependency. Keep
independent work parallel. Parent and dependency relationships stay within the
project, dependencies share a parent, and neither self-dependencies nor cycles
are allowed. Resolve ambiguous titles or assignee display names with stable
IDs or usernames rather than guessing.

The helper reuses an identical task with the same creation key. Different
existing content stops the operation. If a POST times out, the helper reads
once to check the creation key; it never blindly resubmits. Report uncertain
results and re-read before another write.

## Update

Read the current task first; preserve relevant analysis and unrelated fields.
Use [scripts/update_task.py](scripts/update_task.py) with a hierarchy number or
stable task UUID and a partial JSON object on stdin:

```bash
python3 /path/to/create-task/scripts/update_task.py 3.2 --project serving < /tmp/task-patch.json
```

For example, `{"status":"doing"}` updates only status. The helper reads the
current version, sends one PATCH with `expected_updated_at`, and never retries
a write automatically. A caller may supply the version it previously read;
a mismatch stops before PATCH. On 409, re-read and preserve concurrent edits.
Array fields such as TODOs, attachments, PRs, and dependencies replace their
whole arrays: read first and keep unrelated entries. Updating does not move
a task between projects or change its creation key.

The read-only [read-task skill](../read-task/SKILL.md) can retrieve the full
hierarchy and analysis. Confirm the returned task ID, project, changed fields,
and relationships after writing; report its title and stable task URL.

## Other task API operations

For an explicitly authorized operation, `api(base, method, path, payload)` in
the create helper provides the same token handling and origin restrictions.
See [task fields](references/task-fields.md) for tags, assignees, and attachments.
Do not scan or import local documents automatically, write SQLite directly,
or change service/network configuration when the API is unavailable.

Delete only on an explicit request with a confirmed scope. Read the target and
its descendants first: DELETE cascades to subtasks. Do not automatically retry
DELETE or attachment uploads after an uncertain response.
