#!/usr/bin/env bash

set -eu

LC_ALL=C
export LC_ALL

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat >&2 <<'EOF'
Usage:
  issue-create.sh preview HOST REPO TITLE BODY_FILE [LABEL...]
  issue-create.sh create HOST REPO TITLE BODY_FILE TOKEN [LABEL...]
EOF
  exit 2
}

validate_host() {
  case "$1" in
    "" | .* | -* | *[!A-Za-z0-9.-]*) return 1 ;;
    *) return 0 ;;
  esac
}

validate_repo() {
  [[ "$1" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]
}

emit_text() {
  local value=$1 length
  length=$(printf '%s' "$value" | wc -c | tr -d '[:space:]')
  printf '%s:' "$length"
  printf '%s' "$value"
}

emit_file() {
  local path=$1 length
  length=$(wc -c <"$path" | tr -d '[:space:]')
  printf '%s:' "$length"
  cat -- "$path"
}

payload_token() {
  local host=$1 repo=$2 title=$3 body_file=$4
  shift 4
  {
    emit_text "$host"
    emit_text "$repo"
    emit_text "$title"
    for label in "$@"; do
      emit_text "$label"
    done
    emit_file "$body_file"
  } | git hash-object --stdin
}

validate_payload() {
  local host=$1 repo=$2 title=$3 body_file=$4
  shift 4
  validate_host "$host" || fail "invalid GitHub host: $host"
  validate_repo "$repo" || fail "repository must be an owner/name identity"
  [ -n "$title" ] || fail "issue title is empty"
  [ -f "$body_file" ] && [ -r "$body_file" ] ||
    fail "issue body file is not a readable regular file"
  [ -s "$body_file" ] || fail "issue body is empty"
  for label in "$@"; do
    [ -n "$label" ] || fail "issue labels cannot be empty"
  done
}

preview_issue() {
  [ "$#" -ge 4 ] || usage
  local host=$1 repo=$2 title=$3 body_file=$4 token labels
  shift 4
  validate_payload "$host" "$repo" "$title" "$body_file" "$@"
  token=$(payload_token "$host" "$repo" "$title" "$body_file" "$@") ||
    fail "unable to compute issue preview token"
  labels=""
  for label in "$@"; do
    if [ -z "$labels" ]; then
      labels=$label
    else
      labels="$labels, $label"
    fi
  done
  [ -n "$labels" ] || labels="(none)"
  printf 'Host: %s\n' "$host"
  printf 'Repository: %s\n' "$repo"
  printf 'Title: %s\n' "$title"
  printf 'Labels: %s\n' "$labels"
  printf 'Body:\n'
  cat -- "$body_file"
  case "$(tail -c 1 "$body_file" | wc -l | tr -d '[:space:]')" in
    0) printf '\n' ;;
  esac
  printf 'ISSUE_CREATE:%s\n' "$token"
}

create_issue() {
  [ "$#" -ge 5 ] || usage
  local host=$1 repo=$2 title=$3 body_file=$4 approved_token=$5
  local current_token issue_url issue_number
  shift 5
  validate_payload "$host" "$repo" "$title" "$body_file" "$@"
  current_token=$(payload_token "$host" "$repo" "$title" "$body_file" "$@") ||
    fail "unable to recompute issue preview token"
  [ "$approved_token" = "$current_token" ] ||
    fail "issue payload changed after preview; preview it again"

  local arguments=(issue create --repo "$repo" --title "$title" --body-file "$body_file")
  for label in "$@"; do
    arguments+=(--label "$label")
  done
  issue_url=$(GH_HOST="$host" gh "${arguments[@]}") ||
    fail "issue creation failed for $host/$repo"
  case "$issue_url" in
    "https://$host/$repo/issues/"*) ;;
    *) fail "GitHub returned an unexpected issue URL" ;;
  esac
  issue_number=${issue_url##*/}
  case "$issue_number" in
    "" | 0* | *[!0-9]*) fail "GitHub returned an invalid issue URL" ;;
  esac
  printf '%s\n' "$issue_url"
}

[ "$#" -ge 1 ] || usage
command=$1
shift
case "$command" in
  preview) preview_issue "$@" ;;
  create) create_issue "$@" ;;
  *) usage ;;
esac
