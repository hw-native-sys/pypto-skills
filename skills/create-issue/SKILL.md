---
name: create-issue
description: Use when drafting, checking, or filing a GitHub issue, including bug reports, feature requests, documentation reports, and repository issue forms.
---

# Create Issue

Draft and create one issue against the repository proven by the current Git
checkout. Keep discovery read-only and make the exact approved payload immutable.

## Resolve issue context

Read [issue context](../../lib/github/issue-context.md) and invoke the
[issue-context helper](../../lib/github/scripts/issue-context.sh) from that
shared-library path for its `repository`, `templates`, and `search` routes.
Retain `GITHUB_HOST`, `LOCAL_REPO`, `ISSUE_REPO`, and `DEFAULT_BRANCH` from the
returned JSON. Stop on ambiguous identity; do not use an ambient `gh` repository,
a fixed remote, or a familiar organization.

Run the `templates` route, then read [template interpretation](../../lib/github/issue-templates.md).
Select only from the discovered issue forms and legacy templates. Preserve the
repository's title prefix and labels. If none fits, use the documented fallback.

## Search and classify related work

Build focused keywords from the proposed issue, then run the `search` route. It
searches open and closed issues. Deep-read plausible candidates and classify the
result as exactly one of:

- `DUPLICATE #N`: the same request or root cause.
- `RELATED #N...`: overlapping context with a different request or root cause.
- `NO_MATCH`: no material overlap.

Stop only for `DUPLICATE` and report the existing issue. For `RELATED`, continue
and insert `Related: #N` for each related issue in the body. A closed issue or a
shared component is not by itself a duplicate.

## Gather a complete issue

Enumerate every YAML field whose validation contains `required: true`, or every
required legacy-template prompt. Gather each missing user fact explicitly.
Never invent form values, reproduction steps, expected/actual behavior, labels,
project metadata, assignees, or status. Do not present placeholders as complete.

Draft a concise title with the discovered prefix, the discovered labels, and a
body that preserves all selected-template fields in order. Keep the exact body
in a temporary file. Creating that local draft is preparation, not issue
confirmation. Include related references without replacing required content.

## Preview the complete mutation

Run `scripts/issue-create.sh preview HOST REPO TITLE BODY_FILE LABEL...`, passing
`GITHUB_HOST` and `ISSUE_REPO`. Show the helper's output verbatim. It contains
the host, repository, title, labels, complete body, and `ISSUE_CREATE:<oid>`
token. The preview performs no GitHub call.

Never invent or reconstruct the preview token. A token is approval-eligible only
when the executed helper printed it together with the exact complete preview.

If any fact, field, target, label, or body byte changes, discard the token and
preview again.

## Wait for explicit confirmation

Ask whether to create exactly the previewed issue. Wait for an explicit yes
after the complete helper preview. A request to draft, inspect, or edit is not
confirmation. Do not combine confirmation with an earlier incomplete preview.

## Create exactly the approved issue

After confirmation, run `scripts/issue-create.sh create HOST REPO TITLE BODY_FILE
TOKEN LABEL...` with the unchanged values. The helper rejects changed payloads
before invoking GitHub and returns the created issue URL. Report that URL.

Treat project metadata as a separate optional mutation. Perform it only when
applicable repository instructions explicitly name the project and every field
needed for the update. Preview and confirm that separate mutation; otherwise
skip it. If it fails after issue creation, report the issue as created and the
metadata update as failed.
