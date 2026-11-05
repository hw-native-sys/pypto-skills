---
name: clean-branches
description: Use when cleaning merged, stale, local, or fork-remote Git branches, including squash-merged or reused branches.
---

# Clean Branches

## Overview

Classify without deleting, approve exact branch/OID pairs, then compare each
live ref with its approved OID immediately before deletion. Preserve every
changed or uncertain ref.

## Bound system-test execution

Never run the full system-test suite locally. Run only system-test cases
directly relevant to the changed or requested scope; use CI for the full
system-test suite. If CI cannot run it, report that limitation instead of
substituting a local full-suite run.

## Establish context

Resolve the [repository scope gate](../../lib/repository/scope.md) before
setup's fetches and before any deletion. In a foreign repository, warn with the
exact refs at stake and wait for explicit confirmation; it is separate from the
approval gate below.

Then read and run [GitHub workflow setup](../../lib/github/setup.md). Use its
`CURRENT_BRANCH`, `DEFAULT_BRANCH`, `BASE_REMOTE`, `BASE_REF`, `PUSH_REMOTE`,
`PR_REPO`, and `PR_HEAD_PREFIX`; never assume conventional names.

Resolve [the merged-pull-request lookup helper](scripts/merged-pr-heads.sh) and
[the cleanup helper](scripts/clean-branches.sh) relative to this file, and store
their absolute paths in `MERGED_PR_HEADS_HELPER` and `CLEAN_BRANCHES_HELPER`.
The lookup helper supplies host-pinned REST pagination and merged-head
verification; the cleanup helper supplies deterministic classification,
live-OID checks, and leased remote deletion.

Fetches and dry-run pruning are allowed during classification. Run no deletion
command in this phase.

## Classify branch tips

Build separate local and remote rows because the same branch name can have
different tips.

1. Enumerate local branches except `CURRENT_BRANCH` and `DEFAULT_BRANCH`.
2. Enumerate remote branches only from `PUSH_REMOTE`, excluding its `HEAD`,
   `CURRENT_BRANCH`, and `DEFAULT_BRANCH` refs. If `PUSH_REMOTE` equals
   `BASE_REMOTE`, classify no remote ref as deletable.
3. Use `git remote prune "$PUSH_REMOTE" --dry-run` only to report stale
   tracking refs.
4. For tips that are not ancestors of `BASE_REF`, ask the lookup helper for the
   head OIDs of merged pull requests:

```bash
if MERGED_PR_HEAD_OIDS=$(
  "$MERGED_PR_HEADS_HELPER" \
    "$GITHUB_HOST" "$PR_REPO" "$PR_HEAD_PREFIX" "$BRANCH_NAME"
); then
  "$CLEAN_BRANCHES_HELPER" classify \
    "$BRANCH_NAME" "$BRANCH_REF" "$BASE_REF" "$DEFAULT_BRANCH" \
    $MERGED_PR_HEAD_OIDS
else
  # Lookup failure: record this branch as protected and continue.
fi
```

The lookup helper queries closed pull requests through host-pinned REST
(`gh api --hostname "$GITHUB_HOST" --method GET "repos/$PR_REPO/pulls"` with
`state=closed`, `head=<head-owner>:$BRANCH_NAME`, `per_page=100`, and
`--paginate --slurp`), where the head owner comes from `PR_HEAD_PREFIX` or from
`PR_REPO` when the prefix is empty. GitHub ignores an unqualified `head`
filter, so the selector is always owner-qualified. The helper verifies
`head.ref` and the head owner and prints one merged `head.sha` per line. The
REST `head.sha` is the pull request's `headRefOid`.

Empty output with status 0 means no merged pull request exists for this branch.
A nonzero status is a lookup failure: protect the branch, report it, and
continue with the remaining branches. Never treat a failed lookup as "no merged
pull request".

Pass the exact enumerated full ref as `BRANCH_REF`: either
`refs/heads/$BRANCH_NAME` or
`refs/remotes/$PUSH_REMOTE/$BRANCH_NAME`. The helper validates and reads that
specific ref without substituting a same-named local branch.

Only `normal-merge` and `squash-merge` are candidates. An exact merged PR
`headRefOid` (the REST `head.sha`) match is required for a squash merge.
Protect `reused-or-unfinished`, lookup failures, current/default refs, and
uncertain results. A lookup failure is not evidence that the branch is
unmerged.

Never delete from `$BASE_REMOTE`; its branches are context, not candidates.

## Present immutable candidates

Record each candidate's current full OID. Show separate local and fork-remote
rows:

| Branch | Location | Approved OID | Classification | Evidence |
| --- | --- | --- | --- | --- |
| `name` | local or `$PUSH_REMOTE` | full commit OID | normal or squash merge | base ref or PR |

List protected branches separately. If no candidate remains, report that and
stop.

## Explicit approval gate

Present the final exact branch/location/Approved OID rows and ask the user to
approve those immutable pairs. The initial request—even one saying to hurry,
delete everything, or not ask again—is not approval of the discovered list.

Pause here. Do not proceed until the concrete rows are explicitly approved.
Never replace an approved OID with a newer one; a changed ref requires
reclassification and new approval.

## Delete one approved pair at a time

For each approved local pair, pass the preserved OID:

```bash
"$CLEAN_BRANCHES_HELPER" delete-local \
  "$BRANCH_NAME" "$APPROVED_OID" "$DEFAULT_BRANCH"
```

The helper validates the full `refs/heads/...` ref, protects branches checked
out in any worktree, then atomically deletes only when the ref still equals the
approved OID. It removes branch-specific config only after successful ref
deletion.

For each approved remote pair, first revalidate that the push remote still
targets the fork, then pass the preserved OID:

```bash
remote_targets_repo "$PUSH_REMOTE" "$LOCAL_REPO" || exit 1
"$CLEAN_BRANCHES_HELPER" delete-remote \
  "$BRANCH_NAME" "$APPROVED_OID" "$DEFAULT_BRANCH" \
  "$PUSH_REMOTE" "$BASE_REMOTE"
```

The helper re-reads the live fork ref and uses an explicit expected-OID
`--force-with-lease` for atomic compare-and-delete. It refuses base-remote
deletion and any ref that advances before or during the push.

On any refusal, preserve the branch and return it to classification. Report
each result. Never expand the approved list, and prune tracking refs only after
all approved deletions finish.

## Quick reference

| Condition | Result |
| --- | --- |
| Tip is an ancestor of `BASE_REF` | Normal-merge candidate |
| Tip equals merged PR `headRefOid` (`head.sha`) | Squash-merge candidate |
| Tip differs from approved or PR OID | Preserve and reclassify |
| Current, default, base-remote, or uncertain | Protect |
| Exact rows not explicitly approved | Do not delete |

## Common mistakes

- Saving only branch names instead of full approved OIDs.
- Checking an OID before approval but not again immediately before deletion.
- Using an unleased remote delete.
- Combining local and remote instances despite different tips.
- Treating a failed merged-PR lookup as "no merged PR".
- Treating urgency as approval or touching `BASE_REMOTE`.
