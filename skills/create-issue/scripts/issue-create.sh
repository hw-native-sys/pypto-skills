#!/usr/bin/env bash

set -eu

LC_ALL=C
export LC_ALL

BODY_SNAPSHOT=""
CREATE_OPERATION=0
MUTATION_STARTED=0
RESPONSE_STDOUT=""
RESPONSE_STDERR=""

cleanup_snapshot() {
  if [ -n "${BODY_SNAPSHOT:-}" ]; then
    rm -f -- "$BODY_SNAPSHOT"
    BODY_SNAPSHOT=""
  fi
}

trap cleanup_snapshot EXIT

fail() {
  if [ "$CREATE_OPERATION" -eq 1 ] && [ "$MUTATION_STARTED" -eq 0 ]; then
    printf '%s\n' 'ISSUE_CREATE_OUTCOME:confirmed_not_created' >&2
  fi
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

post_write_stop() {
  local outcome=$1 status=$2 message=$3
  printf 'ISSUE_CREATE_OUTCOME:%s\n' "$outcome" >&2
  printf 'ISSUE_CREATE_RESPONSE_STDOUT:%s\n' "$RESPONSE_STDOUT" >&2
  printf 'ISSUE_CREATE_RESPONSE_STDERR:%s\n' "$RESPONSE_STDERR" >&2
  printf 'Error: %s Raw responses remain in private mode-0600 files; redact before sharing.\n' \
    "$message" >&2
  exit "$status"
}

handle_signal() {
  local status=$1 signal_name=$2
  if [ "$MUTATION_STARTED" -eq 1 ] && [ -n "$RESPONSE_STDOUT" ] &&
     [ -n "$RESPONSE_STDERR" ]; then
    post_write_stop "unknown" 31 \
      "The create request was interrupted by $signal_name; creation may have occurred."
  fi
  exit "$status"
}

trap 'handle_signal 129 HUP' HUP
trap 'handle_signal 130 INT' INT
trap 'handle_signal 143 TERM' TERM

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

has_control_character() {
  case "$1" in
    *[[:cntrl:]]*) return 0 ;;
    *) return 1 ;;
  esac
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
  if has_control_character "$title"; then
    fail "issue title contains a control character"
  fi
  [ -f "$body_file" ] && [ -r "$body_file" ] ||
    fail "issue body file is not a readable regular file"
  [ -s "$body_file" ] || fail "issue body is empty"
  for label in "$@"; do
    [ -n "$label" ] || fail "issue labels cannot be empty"
    if has_control_character "$label"; then
      fail "issue label contains a control character"
    fi
  done
}

snapshot_body() {
  local source=$1 snapshot_directory
  snapshot_directory=${TMPDIR:-/tmp}
  if has_control_character "$snapshot_directory"; then
    fail "temporary directory contains a control character"
  fi
  [ -d "$snapshot_directory" ] && [ -w "$snapshot_directory" ] ||
    fail "temporary directory is not writable: $snapshot_directory"
  BODY_SNAPSHOT=$(mktemp "$snapshot_directory/issue-create.XXXXXX") ||
    fail "unable to create a private issue body snapshot"
  chmod 600 "$BODY_SNAPSHOT" || fail "unable to protect issue body snapshot"
  cat -- "$source" >"$BODY_SNAPSHOT" || fail "unable to snapshot issue body"
  [ -s "$BODY_SNAPSHOT" ] || fail "snapshotted issue body is empty"
}

preview_issue() {
  [ "$#" -ge 4 ] || usage
  local host=$1 repo=$2 title=$3 body_file=$4 token label label_length
  shift 4
  validate_payload "$host" "$repo" "$title" "$body_file" "$@"
  snapshot_body "$body_file"
  token=$(payload_token "$host" "$repo" "$title" "$BODY_SNAPSHOT" "$@") ||
    fail "unable to compute issue preview token"
  printf 'Host: %s\n' "$host"
  printf 'Repository: %s\n' "$repo"
  printf 'Title: %s\n' "$title"
  printf 'Labels (%s):\n' "$#"
  for label in "$@"; do
    label_length=$(printf '%s' "$label" | wc -c | tr -d '[:space:]')
    printf -- '- %s:' "$label_length"
    printf '%s\n' "$label"
  done
  printf 'Body:\n'
  cat -- "$BODY_SNAPSHOT"
  case "$(tail -c 1 "$BODY_SNAPSHOT" | wc -l | tr -d '[:space:]')" in
    0) printf '\n' ;;
  esac
  printf 'ISSUE_CREATE:%s\n' "$token"
}

create_issue() {
  [ "$#" -ge 5 ] || usage
  local host=$1 repo=$2 title=$3 body_file=$4 approved_token=$5
  local current_token issue_url issue_number capture_directory gh_status
  shift 5
  CREATE_OPERATION=1
  validate_payload "$host" "$repo" "$title" "$body_file" "$@"
  snapshot_body "$body_file"
  current_token=$(payload_token "$host" "$repo" "$title" "$BODY_SNAPSHOT" "$@") ||
    fail "unable to recompute issue preview token"
  [ "$approved_token" = "$current_token" ] ||
    fail "issue payload changed after preview; preview it again"
  command -v gh >/dev/null 2>&1 || fail "GitHub CLI is unavailable"

  capture_directory=${TMPDIR:-/tmp}
  RESPONSE_STDOUT=$(mktemp "$capture_directory/issue-create-response.stdout.XXXXXX") ||
    fail "unable to create a private GitHub stdout capture"
  chmod 600 "$RESPONSE_STDOUT" || {
    rm -f -- "$RESPONSE_STDOUT"
    RESPONSE_STDOUT=""
    fail "unable to protect GitHub stdout capture"
  }
  RESPONSE_STDERR=$(mktemp "$capture_directory/issue-create-response.stderr.XXXXXX") || {
    rm -f -- "$RESPONSE_STDOUT"
    RESPONSE_STDOUT=""
    fail "unable to create a private GitHub stderr capture"
  }
  chmod 600 "$RESPONSE_STDERR" || {
    rm -f -- "$RESPONSE_STDOUT" "$RESPONSE_STDERR"
    RESPONSE_STDOUT=""
    RESPONSE_STDERR=""
    fail "unable to protect GitHub stderr capture"
  }

  local arguments=(issue create --repo "$repo" --title "$title" --body-file "$BODY_SNAPSHOT")
  for label in "$@"; do
    arguments+=(--label "$label")
  done
  gh_status=0
  MUTATION_STARTED=1
  GH_HOST="$host" gh "${arguments[@]}" >"$RESPONSE_STDOUT" 2>"$RESPONSE_STDERR" ||
    gh_status=$?
  if [ "$gh_status" -ne 0 ]; then
    post_write_stop "unknown" 31 \
      "GitHub CLI returned nonzero after the create request; creation may have occurred."
  fi
  issue_url=$(cat -- "$RESPONSE_STDOUT") ||
    post_write_stop "created_response_unvalidated" 30 \
      "GitHub CLI reported success but its stdout could not be read."
  if has_control_character "$issue_url"; then
    post_write_stop "created_response_unvalidated" 30 \
      "GitHub CLI reported success but returned an unsafe issue URL."
  fi
  case "$issue_url" in
    "https://$host/$repo/issues/"*) ;;
    *) post_write_stop "created_response_unvalidated" 30 \
         "GitHub CLI reported success but returned an unexpected issue URL." ;;
  esac
  issue_number=${issue_url##*/}
  case "$issue_number" in
    "" | 0* | *[!0-9]*) post_write_stop "created_response_unvalidated" 30 \
      "GitHub CLI reported success but returned an invalid issue URL." ;;
  esac
  rm -f -- "$RESPONSE_STDOUT" "$RESPONSE_STDERR"
  RESPONSE_STDOUT=""
  RESPONSE_STDERR=""
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
