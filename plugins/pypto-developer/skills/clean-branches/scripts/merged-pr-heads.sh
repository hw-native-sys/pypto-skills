#!/usr/bin/env bash

set -u

usage() {
  cat >&2 <<'EOF'
Usage:
  merged-pr-heads.sh HOST PR_REPO PR_HEAD_PREFIX BRANCH_NAME
EOF
  exit 2
}

fail() {
  echo "Error: $*" >&2
  exit 1
}

validate_repo_identity() {
  case "$1" in
    ""|/*|*/|*/*/*) return 1 ;;
    */*) return 0 ;;
    *) return 1 ;;
  esac
}

[ "$#" -eq 4 ] || usage
GITHUB_HOST=$1
PR_REPO=$2
PR_HEAD_PREFIX=$3
BRANCH_NAME=$4

case "$GITHUB_HOST" in
  ""|*/*|*" "*) fail "invalid GitHub host: $GITHUB_HOST" ;;
esac
validate_repo_identity "$PR_REPO" ||
  fail "PR_REPO must be an owner/name identity"
[ -n "$BRANCH_NAME" ] || fail "branch name is empty"
case "$BRANCH_NAME" in
  *:*) fail "invalid branch name: $BRANCH_NAME" ;;
esac
case "$PR_HEAD_PREFIX" in
  "") ;;
  *:) ;;
  *) fail "PR_HEAD_PREFIX must be empty or end with a colon" ;;
esac

# The head owner is the fork owner named by the prefix, or the base-repository
# owner when the checkout writes to the base repository itself.
PREFIX_OWNER=${PR_HEAD_PREFIX%:}
if [ -n "$PREFIX_OWNER" ]; then
  EXPECTED_OWNER=$PREFIX_OWNER
else
  EXPECTED_OWNER=${PR_REPO%%/*}
fi
EXPECTED_OWNER_LOWER=$(printf '%s' "$EXPECTED_OWNER" | tr '[:upper:]' '[:lower:]')
# GitHub ignores head= without an owner and returns every closed pull request,
# so always qualify the selector with the head owner.
HEAD_SELECTOR="${EXPECTED_OWNER}:${BRANCH_NAME}"

PR_PAGES=$(gh api --hostname "$GITHUB_HOST" --method GET \
  "repos/$PR_REPO/pulls" \
  -f state=closed \
  -f "head=$HEAD_SELECTOR" \
  -f per_page=100 \
  --paginate --slurp) || {
  fail "pull-request lookup failed for $PR_REPO head $HEAD_SELECTOR"
}

# Flatten the page array separately. Never combine --slurp with --jq.
PR_MATCHES=$(printf '%s' "$PR_PAGES" | jq -ce '
  if type == "array" and all(.[]; type == "array")
  then if length == 0 then [] else add end
  else error("malformed paginated response")
  end
') || fail "malformed pull-request response for $PR_REPO head $HEAD_SELECTOR"

# Reject a malformed response shape before interpreting any field. Closed but
# unmerged pull requests and deleted head repositories are valid here; they are
# filtered out below rather than treated as failures.
printf '%s' "$PR_MATCHES" | jq -e '
  type == "array" and
  all(.[];
    type == "object" and
    (.number | type == "number" and . > 0 and . == floor) and
    (.state | type == "string" and length > 0) and
    has("merged_at") and
    (.merged_at == null or
      (.merged_at | type == "string" and length > 0)) and
    (.head | type == "object") and
    (.head.ref | type == "string" and length > 0) and
    (.head.sha | type == "string" and test("^[0-9a-f]{40}$")) and
    (.head.repo == null or
      ((.head.repo | type == "object") and
       (.head.repo.owner | type == "object") and
       (.head.repo.owner.login |
         type == "string" and length > 0)))
  )
' >/dev/null 2>&1 ||
  fail "malformed pull-request response for $PR_REPO head $HEAD_SELECTOR"

# A deleted head repository cannot be owner-verified, so it is excluded and the
# branch stays protected. Use jq -r, not -e: zero output is a successful lookup.
MERGED_HEAD_SHAS=$(printf '%s' "$PR_MATCHES" | jq -r \
  --arg branch "$BRANCH_NAME" \
  --arg owner "$EXPECTED_OWNER_LOWER" '
  [ .[]
    | select(.merged_at != null)
    | select(.head.ref == $branch)
    | select(.head.repo != null)
    | select((.head.repo.owner.login | ascii_downcase) == $owner)
  ]
  | sort_by(.number)
  | .[].head.sha
') || fail "could not extract merged pull-request heads for $PR_REPO head $HEAD_SELECTOR"

[ -z "$MERGED_HEAD_SHAS" ] || printf '%s\n' "$MERGED_HEAD_SHAS"
