---
name: track-pr
description: Use when adding a specified GitHub pull request to a project’s pending merge list on taskboard.pypto.cloud or checking whether it is already tracked. This does not create, review, approve, or merge the GitHub PR.
---

# Track a Pending PR

Never run the full system-test suite locally. Run only system-test cases
directly relevant to the changed or requested scope; use CI for the full
system-test suite.

Add the PR the user identified to `https://taskboard.pypto.cloud/pending-prs`.
Use its full `https://github.com/OWNER/REPO/pull/NUMBER` URL and the identified
project (`pypto`, `pypto-lib`, `serving`, or `simpler`; default `pypto`). Ask
only if the PR itself or its project cannot be determined from context. Do not
create a task or change task analysis to track a PR.

Run [scripts/track_pr.py](scripts/track_pr.py) relative to this skill:

```bash
python3 /path/to/track-pr/scripts/track_pr.py https://github.com/OWNER/REPO/pull/123 --project pypto
```

The helper first reads the selected project’s public list. If the PR already
exists there, it reports that record without writing. The same PR can be
tracked independently in other projects; never reuse another project’s entry. Otherwise it sends one
POST; the server deduplicates canonical PR URLs within each project. The helper
reads the list again to confirm the returned stable ID and URL. If a write
response is uncertain, it only re-reads to check the result and stops if it cannot confirm it. Never
blindly retry an uncertain write or substitute another user's credentials.

Writes use the taskboard user's personal API token, in this order:
`PYPTO_TASK_API_TOKEN`, `PYPTO_TASK_API_TOKEN_FILE`, or
`~/.config/pypto-taskboard/token`. Token files must be mode `600` on Unix.
Do not print credentials, copy them into commands, or place them in PR/task
content. No GitHub credentials or authenticated GitHub operations are needed.
Only the canonical taskboard HTTPS origin or an explicitly selected HTTP
loopback test service is allowed; redirects are refused. Report 401/403 and
stop. Do not start a local server or modify network settings as a fallback.

Return the PR URL, selected project, whether it was added or already present,
and the project-scoped tracking page. GitHub CI, comments, and reviews
synchronize in the background, so adding a PR does not establish that checks
pass or it is ready to merge. Preserve cached-state timestamps and report synchronization errors.
