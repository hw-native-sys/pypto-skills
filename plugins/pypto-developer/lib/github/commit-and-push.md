# Single-Use Pull-Request Push Transaction

Push only through one capture → mutate/commit → prepare → validate → push
transaction. Resolve these trusted files relative to this reference, never the
consuming repository:

- [`scripts/prepare-and-push.sh`](scripts/prepare-and-push.sh) as the absolute
  executable `PREPARE_PUSH_HELPER`;
- [`scripts/push-transaction.sh`](scripts/push-transaction.sh) as
  `PUSH_TRANSACTION_HELPER`, then source it;
- [`scripts/validation-sandbox.sh`](scripts/validation-sandbox.sh) as the
  absolute executable `VALIDATION_SANDBOX`.

The transaction function runs in a subshell. Authority becomes readonly only
inside that invocation and disappears on return. It stores no checkpoint.

## Select base and head identities

Run only after the final local branch is checked out. The base authority is
always the discovered PR destination; the head authority depends on role:

```bash
for REQUIRED_NAME in REPO_ROOT GITHUB_HOST PR_REPO CURRENT_BRANCH \
  DEFAULT_BRANCH BASE_REMOTE PUSH_REMOTE ROLE; do
  [ -n "${!REQUIRED_NAME:-}" ] || {
    echo "Error: required context variable $REQUIRED_NAME is unset" >&2
    exit 1
  }
done
EXPECTED_BASE_HOST="$GITHUB_HOST"
EXPECTED_BASE_REPO="$PR_REPO"
EXPECTED_HEAD_HOST="$GITHUB_HOST"

case "$ROLE" in
  owner|fork)
    EXPECTED_PUSH_REPO="$LOCAL_REPO"
    if [ -n "${PR_HEAD_BRANCH:-}" ]; then
      [ "$PR_HEAD_BRANCH" = "$CURRENT_BRANCH" ] &&
        [ "${HEAD_REPO:-}" = "$LOCAL_REPO" ] || {
        echo "Error: author checkout does not match the verified PR head" >&2
        exit 1
      }
    fi
    PUSH_BRANCH="$CURRENT_BRANCH"
    ;;
  maintainer)
    [ -n "${PR_HEAD_BRANCH:-}" ] && [ -n "${HEAD_REPO:-}" ] || {
      echo "Error: maintainer push requires verified PR head context" >&2
      exit 1
    }
    EXPECTED_PUSH_REPO="$HEAD_REPO"
    PUSH_BRANCH="$PR_HEAD_BRANCH"
    if [ "$PR_HEAD_BRANCH" != "$CURRENT_BRANCH" ]; then
      [ "${MAINTAINER_CHECKOUT_VERIFIED:-}" = "true" ] &&
        [ "${WORK_BRANCH:-}" = "$CURRENT_BRANCH" ] || {
        echo "Error: differing maintainer push requires verified checkout" >&2
        exit 1
      }
    fi
    ;;
  *) echo "Error: unsupported repository role: $ROLE" >&2; exit 1 ;;
esac

remote_targets_repo "$BASE_REMOTE" "$EXPECTED_BASE_REPO" || {
  echo "Error: base remote identity changed" >&2
  exit 1
}
remote_targets_repo "$PUSH_REMOTE" "$EXPECTED_PUSH_REPO" || {
  echo "Error: push remote identity changed" >&2
  exit 1
}

source "$PUSH_TRANSACTION_HELPER" || exit 1

apply_transaction_changes() {
  # Apply/stage/commit/fold with trusted Git built-ins only. The transaction
  # disables repository-configured hooks. Never execute repository code here.
  :
}
VALIDATION_RUNNER="$VALIDATION_SANDBOX"
VALIDATION_COMMAND='run repository-defined focused and broader checks'

pr_push_transaction "$PREPARE_PUSH_HELPER" \
  apply_transaction_changes "$VALIDATION_RUNNER" \
  "$EXPECTED_BASE_HOST" "$EXPECTED_BASE_REPO" \
  "$EXPECTED_HEAD_HOST" "$EXPECTED_PUSH_REPO" \
  "$BASE_REMOTE" "$DEFAULT_BRANCH" "$PUSH_REMOTE" \
  "$CURRENT_BRANCH" "$PUSH_BRANCH" || exit 1
```

Replace the mutation body and validation command, not the transaction
mechanics. The mutation runs after remote-head capture, may set
`HISTORY_REWRITTEN=true`, and must leave a clean commit. The transaction
exports a readonly `core.hooksPath=/dev/null` override; run hook policy and all
other repository code only as validation.

The bundled runner archives exactly `PREPARED_HEAD_OID`, extracts it without
Git metadata, then uses bubblewrap with a new user/PID/network namespace, an
empty environment and home, read-only system runtime, and only the snapshot
writable. It passes no Git remote, token, SSH agent, host home, or network.
Bubblewrap or a required runtime being unavailable is a validation failure.
Never fall back to credentialed execution. If validation needs Git metadata,
hardware, network, or another unavailable runtime, stop and require an
explicitly trusted project runner that enforces the same credential-free,
network-denied boundary; never select a runner from the worktree.

## Identity and push guarantees

Both `prepare` and `push` receive explicit expected base host/repository and
head host/repository arguments. Before fetching/rebasing, `prepare` requires
the base remote's sole fetch URL to map to the expected base and requires every
head fetch URL plus the sole push URL to map to the expected head. `push`
repeats both identity checks, verifies local/base/head OIDs, then repeats the
URL checks immediately before its only write.

A non-rewrite uses a normal push. For a published branch, `prepare` preserves
an explicit rewrite signal and also derives rewrite state by checking whether
the freshly captured remote OID is an ancestor of the prepared head. Rewritten
history uses explicit `git push --force-with-lease` against that OID. An
unpublished branch is never a rewrite. The helper rejects a same-repository
base/default target.

## Retry and iteration rule

The transaction is single-use whether it succeeds or fails. If mutation,
prepare, or validation fails—or validation changes the prepared state—let the
subshell return without pushing. Fix the local issue, then call
`pr_push_transaction` again. The new invocation recaptures base/head state and
starts with fresh rewrite state; never retry an old prepared result.

After a successful push, any later fix-pr iteration also calls a new
transaction. It therefore captures the just-pushed head as its new remote OID.
Do not wrap multiple pushes in one function call or move readonly variables to
the parent shell.
