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
  issue-context.sh repository
  issue-context.sh search HOST REPO QUERY
  issue-context.sh templates HOST REPO
  issue-context.sh fix-preflight HOST REPO NUMBER [--in-progress-status STATUS] [--allow-conflict --approved-envelope-json JSON]
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

url_identity() {
  local url=$1 authority path host repo
  case "$url" in
    git@*:*/*)
      host=${url#git@}
      host=${host%%:*}
      path=${url#*:}
      ;;
    ssh://*/*/* | http://*/*/* | https://*/*/*)
      path=${url#*://}
      authority=${path%%/*}
      host=${authority##*@}
      host=${host%%:*}
      path=${path#*/}
      ;;
    *) return 1 ;;
  esac
  path=${path#/}
  repo=${path%.git}
  host=$(printf '%s' "$host" | tr '[:upper:]' '[:lower:]')
  repo=$(printf '%s' "$repo" | tr '[:upper:]' '[:lower:]')
  validate_host "$host" && validate_repo "$repo" || return 1
  printf '%s\t%s\n' "$host" "$repo"
}

response_identity() {
  local expected_host=$1 expected_repo=$2 response=$3
  local full_name html_url response_host response_repo is_fork issue_repo
  local parent_url parent_host parent_repo
  full_name=$(printf '%s' "$response" | jq -er '.full_name | strings | select(length > 0)') ||
    fail "repository response has no valid full_name"
  validate_repo "$full_name" || fail "repository response has invalid full_name"
  if [[ "${full_name,,}" != "${expected_repo,,}" ]]; then
    fail "repository response does not match $expected_repo"
  fi
  html_url=$(printf '%s' "$response" | jq -er '.html_url | strings | select(length > 0)') ||
    fail "repository response has no valid html_url"
  IFS=$'\t' read -r response_host response_repo < <(url_identity "$html_url") ||
    fail "repository response has an invalid html_url"
  [ "$response_host" = "$expected_host" ] ||
    fail "repository response host does not match $expected_host"
  [[ "${response_repo,,}" = "${full_name,,}" ]] ||
    fail "repository response html_url does not match $full_name"

  is_fork=$(printf '%s' "$response" |
    jq -er '.fork | if type == "boolean" then tostring else error("invalid fork") end') ||
    fail "repository response has no valid fork flag"
  issue_repo=$full_name
  if [ "$is_fork" = "true" ]; then
    issue_repo=$(printf '%s' "$response" |
      jq -er '.parent.full_name | strings | select(length > 0)') ||
      fail "fork response has no valid parent full_name"
    validate_repo "$issue_repo" || fail "fork response has invalid parent full_name"
    parent_url=$(printf '%s' "$response" |
      jq -er '.parent.html_url | strings | select(length > 0)') ||
      fail "fork response has no valid parent html_url"
    IFS=$'\t' read -r parent_host parent_repo < <(url_identity "$parent_url") ||
      fail "fork response has an invalid parent html_url"
    [ "$parent_host" = "$expected_host" ] ||
      fail "fork parent host does not match $expected_host"
    [[ "${parent_repo,,}" = "${issue_repo,,}" ]] ||
      fail "fork parent html_url does not match $issue_repo"
  fi
  printf '%s\t%s\t%s\n' "$full_name" "$issue_repo" "$is_fork"
}

repository_context() {
  [ "$#" -eq 0 ] || usage
  local remote_output remote_name remote_url remote_kind identity host repo
  local github_host="" candidate metadata local_repo="" issue_repo=""
  local fork_local="" nonfork_local=""
  local candidate_local candidate_issue candidate_is_fork target_metadata
  local default_branch target_full target_url target_host target_repo
  declare -A candidates=()

  git rev-parse --show-toplevel >/dev/null 2>&1 ||
    fail "the current directory is not in a Git worktree"
  remote_output=$(git remote -v) || fail "unable to enumerate Git remotes"
  [ -n "$remote_output" ] || fail "the Git worktree has no remotes"
  while read -r remote_name remote_url remote_kind; do
    case "$remote_kind" in
      "(fetch)" | "(push)") ;;
      *) continue ;;
    esac
    identity=$(url_identity "$remote_url") ||
      fail "remote $remote_name has an unsupported or invalid URL"
    IFS=$'\t' read -r host repo <<<"$identity"
    if [ -z "$github_host" ]; then
      github_host=$host
    elif [ "$github_host" != "$host" ]; then
      fail "Git remotes span unrelated hosts"
    fi
    candidates["$repo"]=1
  done <<<"$remote_output"

  [ "${#candidates[@]}" -gt 0 ] || fail "no GitHub remote identity was found"
  for candidate in "${!candidates[@]}"; do
    metadata=$(gh api --hostname "$github_host" "repos/$candidate") ||
      fail "repository metadata could not be read for $candidate"
    IFS=$'\t' read -r candidate_local candidate_issue candidate_is_fork \
      < <(response_identity "$github_host" "$candidate" "$metadata")
    if [ -z "$issue_repo" ]; then
      issue_repo=$candidate_issue
    elif [[ "${issue_repo,,}" != "${candidate_issue,,}" ]]; then
      fail "Git remotes span unrelated repositories"
    fi
    if [ "$candidate_is_fork" = "true" ]; then
      [ -z "$fork_local" ] || [[ "${fork_local,,}" = "${candidate_local,,}" ]] ||
        fail "multiple unrelated fork repositories were found"
      fork_local=$candidate_local
    elif [ -z "$nonfork_local" ]; then
      nonfork_local=$candidate_local
    fi
  done
  if [ -n "$fork_local" ]; then
    local_repo=$fork_local
  else
    local_repo=$nonfork_local
  fi

  target_metadata=$(gh api --hostname "$github_host" "repos/$issue_repo") ||
    fail "issue repository metadata could not be read for $issue_repo"
  target_full=$(printf '%s' "$target_metadata" |
    jq -er '.full_name | strings | select(length > 0)') ||
    fail "issue repository response has no valid full_name"
  validate_repo "$target_full" || fail "issue repository response has invalid full_name"
  [[ "${target_full,,}" = "${issue_repo,,}" ]] ||
    fail "issue repository response does not match $issue_repo"
  target_url=$(printf '%s' "$target_metadata" |
    jq -er '.html_url | strings | select(length > 0)') ||
    fail "issue repository response has no valid html_url"
  IFS=$'\t' read -r target_host target_repo < <(url_identity "$target_url") ||
    fail "issue repository response has an invalid html_url"
  [ "$target_host" = "$github_host" ] ||
    fail "issue repository response host does not match $github_host"
  [[ "${target_repo,,}" = "${target_full,,}" ]] ||
    fail "issue repository html_url does not match $target_full"
  default_branch=$(printf '%s' "$target_metadata" |
    jq -er '.default_branch | strings | select(length > 0)') ||
    fail "issue repository has no valid default branch"

  jq -cn \
    --arg github_host "$github_host" \
    --arg local_repo "$local_repo" \
    --arg issue_repo "$target_full" \
    --arg default_branch "$default_branch" \
    '{github_host: $github_host, local_repo: $local_repo,
      issue_repo: $issue_repo, default_branch: $default_branch}'
}

search_issues() {
  [ "$#" -eq 3 ] || usage
  local host=$1 repo=$2 query=$3 response
  validate_host "$host" || fail "invalid GitHub host: $host"
  validate_repo "$repo" || fail "repository must be an owner/name identity"
  [ -n "$query" ] || fail "issue search query is empty"
  response=$(GH_HOST="$host" gh issue list --repo "$repo" --state all --limit 1000 \
    --search "$query" --json number,title,body,state,labels,url) ||
    fail "issue search failed for $host/$repo"
  printf '%s' "$response" | jq -ce '
    if type == "array" and all(.[ ];
      type == "object" and
      (.number | type == "number" and . > 0) and
      (.title | type == "string") and
      (.body | type == "string") and
      (.state == "OPEN" or .state == "CLOSED") and
      (.labels | type == "array") and
      (.url | type == "string" and length > 0))
    then . else error("malformed issue search response") end'
}

list_templates() {
  [ "$#" -eq 2 ] || usage
  local host=$1 repo=$2 response error_file status
  validate_host "$host" || fail "invalid GitHub host: $host"
  validate_repo "$repo" || fail "repository must be an owner/name identity"
  error_file=$(mktemp) || fail "unable to create an error capture file"
  trap "rm -f '$error_file'" EXIT
  status=0
  response=$(gh api --hostname "$host" --paginate \
    "repos/$repo/contents/.github/ISSUE_TEMPLATE" 2>"$error_file") || status=$?
  if [ "$status" -ne 0 ]; then
    if grep -Eq 'Not Found|HTTP 404' "$error_file"; then
      if gh api --hostname "$host" "repos/$repo" >/dev/null 2>>"$error_file"; then
        printf '%s\n' '[]'
        return
      fi
    fi
    cat "$error_file" >&2
    fail "issue template discovery failed for $host/$repo"
  fi
  printf '%s' "$response" | jq -ce '
    if type != "array" then error("malformed issue template response") else
      [.[] |
        select(.type == "file") |
        .name as $name |
        if ($name | ascii_downcase) == "config.yml" or
           ($name | ascii_downcase) == "config.yaml" then empty
        elif ($name | ascii_downcase | endswith(".yml")) or
             ($name | ascii_downcase | endswith(".yaml")) then
          {name, path, kind: "issue_form"}
        elif ($name | ascii_downcase | endswith(".md")) then
          {name, path, kind: "legacy_template"}
        else empty end]
    end'
}

fix_preflight() {
  [ "$#" -ge 3 ] || usage
  local host=$1 repo=$2 number=$3
  local in_progress_status="" allow_conflict=0 response record conflict=0
  local approved_envelope_json="" approved_envelope_canonical=""
  local approved_envelope_set=0 current_envelope
  shift 3

  validate_host "$host" || fail "invalid GitHub host: $host"
  validate_repo "$repo" || fail "repository must be an owner/name identity"
  [[ "$number" =~ ^[1-9][0-9]*$ ]] || fail "issue number must be a positive integer"

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --in-progress-status)
        [ "$#" -ge 2 ] || usage
        [ -z "$in_progress_status" ] || usage
        in_progress_status=$2
        [ -n "$in_progress_status" ] || fail "in-progress status is empty"
        shift 2
        ;;
      --allow-conflict)
        [ "$allow_conflict" -eq 0 ] || usage
        allow_conflict=1
        shift
        ;;
      --approved-envelope-json)
        [ "$#" -ge 2 ] || usage
        [ "$approved_envelope_set" -eq 0 ] || usage
        approved_envelope_json=$2
        approved_envelope_set=1
        shift 2
        ;;
      *) usage ;;
    esac
  done

  if [ "$allow_conflict" -eq 1 ]; then
    [ "$approved_envelope_set" -eq 1 ] || usage
  else
    [ "$approved_envelope_set" -eq 0 ] || usage
  fi
  if [ "$approved_envelope_set" -eq 1 ]; then
    approved_envelope_canonical=$(printf '%s' "$approved_envelope_json" |
      jq -cSe '
        def conflict_rank:
          if . == "closed" then 0
          elif . == "assigned" then 1
          elif . == "in_progress" then 2
          elif . == "active_pull_request" then 3
          else 99 end;
        if type == "object" and .version == 1 and
           (.issue | type == "object" and
             (.host | type == "string" and length > 0) and
             (.repository | type == "string" and length > 0) and
             (.number | type == "number" and . > 0) and
             (.state == "OPEN" or .state == "CLOSED")) and
           (.configured_in_progress_status | type == "string") and
           (.conflicts | type == "array" and length > 0 and
             all(.[]; type == "string") and
             all(.[]; . as $conflict |
             (["closed", "assigned", "in_progress", "active_pull_request"] |
              index($conflict)) != null) and
             length == (unique | length) and
             . == sort_by(conflict_rank)) and
           (.evidence | type == "object" and
             (.assignee_logins | type == "array" and
               all(.[]; type == "string" and length > 0)) and
             (.in_progress_project_items | type == "array" and
               all(.[]; type == "object" and
                 (.title | type == "string" and length > 0) and
                 (.status | type == "string" and length > 0))) and
             (.active_pull_requests | type == "array" and
               all(.[]; type == "object" and
                 (.number | type == "number" and . > 0) and
                 (.state == "OPEN") and
                 (.head_repository | type == "string" and length > 0) and
                 (.head_branch | type == "string" and length > 0))))
        then . else error("invalid approval envelope") end') ||
      fail "approved envelope must be a canonical fix-issue approval object"
  fi

  response=$(GH_HOST="$host" gh issue view "$number" --repo "$repo" \
    --json number,title,body,state,labels,assignees,url,projectItems,closedByPullRequestsReferences) ||
    fail "issue preflight failed for $host/$repo#$number"
  record=$(printf '%s' "$response" | jq -ce \
    --arg host "$host" \
    --arg repo "$repo" \
    --argjson issue_number "$number" \
    --arg configured_status "$in_progress_status" '
    if type == "object" and
       (.number == $issue_number) and
       (.title | type == "string") and
       (.body | type == "string") and
       (.state == "OPEN" or .state == "CLOSED") and
       (.labels | type == "array") and
       (.assignees | type == "array" and all(.[];
          type == "object" and (.login | type == "string" and length > 0))) and
       (.url == ("https://" + $host + "/" + $repo + "/issues/" +
         ($issue_number | tostring))) and
       (.projectItems | type == "array" and all(.[];
         type == "object" and
         (.title | type == "string" and length > 0) and
         ((.status? // null) == null or
           (.status | type == "object" and
             (.name | type == "string" and length > 0))))) and
       (.closedByPullRequestsReferences | type == "array")
    then {
      number,
      title,
      body,
      state,
      labels,
      assignees,
      url,
      project_items: [
        .projectItems[] | {
          title,
          status: ((.status? // null) | if . == null then null else .name end)
        }
      ],
      project_status: (
        ([
          .projectItems[]? |
          .status? |
          if type == "object" then .name else . end |
          select(type == "string" and length > 0)
        ]) as $statuses |
        ((if $configured_status == "" then
            ($statuses | first)
          else
            (($statuses | map(select(
              (. | ascii_downcase) == ($configured_status | ascii_downcase)
            ))) | first) // ($statuses | first)
          end) // null)
      ),
      linked_pull_requests: [
        .closedByPullRequestsReferences[] |
        if type == "object" and
           (.number | type == "number" and . > 0) and
           (.state == "OPEN" or .state == "CLOSED" or .state == "MERGED") and
           (.url == ("https://" + $host + "/" + $repo + "/pull/" +
             (.number | tostring))) and
           (.headRefName | type == "string" and length > 0) and
           (.headRepository.nameWithOwner | type == "string" and length > 0)
        then {
          number,
          state,
          url,
          head_repository: .headRepository.nameWithOwner,
          head_branch: .headRefName
        }
        else error("malformed linked pull request") end
      ]
    }
    else error("malformed issue preflight response") end') ||
    fail "issue preflight returned malformed data for $host/$repo#$number"
  record=$(printf '%s' "$record" | jq -ce \
    --arg host "$host" \
    --arg repo "$repo" \
    --arg configured_status "$in_progress_status" '
    (.assignees | map(.login) | unique | sort) as $assignee_logins |
    (.project_items | map(select(
      $configured_status != "" and .status != null and
      (.status | ascii_downcase) == ($configured_status | ascii_downcase)
    )) | unique | sort_by(.title, .status)) as $in_progress_items |
    (.linked_pull_requests | map(select(.state == "OPEN")) |
      unique | sort_by(.number, .head_repository, .head_branch, .state))
      as $active_pull_requests |
    [
      (if .state == "CLOSED" then "closed" else empty end),
      (if ($assignee_logins | length) > 0 then "assigned" else empty end),
      (if ($in_progress_items | length) > 0 then "in_progress" else empty end),
      (if ($active_pull_requests | length) > 0
       then "active_pull_request" else empty end)
    ] as $conflicts |
    . + {
      conflicts: $conflicts,
      approval_envelope: {
        version: 1,
        issue: {
          host: $host,
          repository: $repo,
          number: .number,
          state: .state
        },
        configured_in_progress_status: ($configured_status | ascii_downcase),
        conflicts: $conflicts,
        evidence: {
          assignee_logins: $assignee_logins,
          in_progress_project_items: $in_progress_items,
          active_pull_requests: $active_pull_requests
        }
      }
    }') ||
    fail "issue preflight conflict classification failed for $host/$repo#$number"

  printf '%s\n' "$record"
  conflict=$(printf '%s' "$record" | jq -er '
    if (.conflicts | index("closed")) != null then 20
    elif (.conflicts | index("assigned")) != null then 21
    elif (.conflicts | index("in_progress")) != null then 22
    elif (.conflicts | index("active_pull_request")) != null then 23
    else 0 end') ||
    fail "issue preflight primary classification failed for $host/$repo#$number"

  if [ "$allow_conflict" -eq 1 ]; then
    current_envelope=$(printf '%s' "$record" | jq -cS '.approval_envelope') ||
      fail "issue preflight approval envelope could not be compared"
    if [ "$current_envelope" != "$approved_envelope_canonical" ]; then
      if [ "$conflict" -eq 0 ]; then
        fail "approved envelope no longer matches the current clean issue"
      fi
      return "$conflict"
    fi
    if [ "$conflict" -ge 21 ] && [ "$conflict" -le 23 ]; then
      return 0
    fi
  fi
  return "$conflict"
}

[ "$#" -ge 1 ] || usage
command=$1
shift
case "$command" in
  repository) repository_context "$@" ;;
  search) search_issues "$@" ;;
  templates) list_templates "$@" ;;
  fix-preflight) fix_preflight "$@" ;;
  *) usage ;;
esac
