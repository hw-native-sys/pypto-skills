# Task Fields and Related APIs

`GET /api/tasks?project=<id>` returns that project's tasks, assignee account
summaries (`owner_users`), and reusable tags. The implicit project is `pypto`.
`GET /api/projects` returns project statistics; `?project=all` is for explicitly
requested cross-project reads and exports. Task URLs use a stable UUID.

A creation input may look like:

```json
{
  "title": "Implement a library operator",
  "topic": "library-operator",
  "description": "Overall objective and scope",
  "analysis": "## Background\n\nImplementation and validation details.",
  "status": "todo",
  "priority": "medium",
  "subject": "Operators",
  "parent_id": null,
  "dependency_ids": [],
  "pr_urls": [],
  "issue_urls": [],
  "todos": [{"description": "Validate the implementation", "done": false, "link_url": ""}],
  "attachment_ids": []
}
```

| Field | Behavior |
| --- | --- |
| `title` | Required when creating; 1–200 characters. |
| `topic` | Creation-only lowercase letters/digits with hyphens; at most 100 characters. |
| `project_id` | Optional creation project; defaults to `pypto`. |
| `description` | Overall introduction; at most 10,000 characters. |
| `analysis` | Markdown text; at most 2 MiB in UTF-8. |
| `status` | `todo`, `doing`, or `done`; default `todo`. |
| `priority` | `high`, `medium`, or `low`; default `medium`. |
| `subject` | Reusable project-local theme tag; at most 100 characters. |
| `owner`, `owner_user_id` | Assignee text and/or stable account ID; see below. |
| `parent_id` | Stable task ID in the same project, or `null`. |
| `dependency_ids` | Up to 200 existing sibling IDs; no cycles. |
| `pr_urls`, `issue_urls` | Up to 20 full GitHub PR/issue URLs per field. |
| `todos` | Up to 100 items, each with description, boolean `done`, and optional PR/issue `link_url`. |
| `attachment_ids` | Up to 20 uploaded attachment IDs; total attachment size at most 100 MiB. |
| `notes` | At most 5,000 characters. |
| `expected_updated_at` | Update version; filled by the update helper or supplied from a prior read. |

TODO descriptions contain 1–2,000 characters. The server assigns stable TODO
UUIDs when omitted; retain existing IDs, order, content, and unrelated entries
when replacing a checklist. TODO completion, task status, and GitHub PR/issue
state are independent. Do not infer task completion from checked TODOs or a
merged PR. The legacy `actor` input does not override server-side attribution.

## Assignees and tags

Select `owner_user_id` by exact username in `owner_users`; do not guess between
duplicate display names. Inactive users cannot receive new assignments.
`owner` alone binds to a uniquely matching username or display name, otherwise
it remains text. An unbound name displays `*`, but that marker is not stored in
`owner`. `owner_user` is the account summary and `owner_label` is the display
label. Account renames retain the stable binding. Preserve `owner_user_id`
when changing other fields; clear with `owner: ""` and `owner_user_id: null`.

Themes and custom assignee tags are project-local; accounts are shared. Tags
are stored automatically when used. Deleting a saved tag does not clear task
values; perform such deletion only when requested.

## Attachments

Only upload a file when requested. Use
`POST /api/attachments?name=<URL-encoded-filename>` with raw bytes,
`Content-Type: application/octet-stream`, and a Bearer token handled without
logging it. Each attachment is at most 20 MiB. Bind the returned `attachment.id`
through `attachment_ids`; a filesystem path is not an attachment ID. Uploading
does not insert file content into `analysis`.

Unbind a saved file by PATCHing the remaining `attachment_ids`. An abandoned,
unbound upload can be removed with `DELETE /api/attachments/<id>`. Confirm an
uncertain result before repeating a request. Preserve legacy `doc_paths` when
updating other fields; do not automatically create document files or imports.
