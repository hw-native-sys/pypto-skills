#!/usr/bin/env bash

set -u

fail() {
  echo "Error: $*" >&2
  exit 1
}

[ "$#" -eq 2 ] ||
  fail "validation sandbox requires PREPARED_HEAD_OID and VALIDATION_COMMAND"
PREPARED_HEAD_OID=$1
VALIDATION_COMMAND=$2

case "$PREPARED_HEAD_OID" in
  ""|*[!0-9a-fA-F]*) fail "PREPARED_HEAD_OID is not a full Git object ID" ;;
esac
case "${#PREPARED_HEAD_OID}" in
  40|64) ;;
  *) fail "PREPARED_HEAD_OID is not a full Git object ID" ;;
esac
[ -n "$VALIDATION_COMMAND" ] || fail "VALIDATION_COMMAND must not be empty"

PATH=/usr/bin:/bin
export PATH
for REQUIRED_TOOL in bwrap env git mktemp mkdir rm tar chmod; do
  command -v "$REQUIRED_TOOL" >/dev/null 2>&1 ||
    fail "$REQUIRED_TOOL is required for isolated validation"
done
BWRAP=$(command -v bwrap)
ENV_TOOL=$(command -v env)

git rev-parse --show-toplevel >/dev/null 2>&1 ||
  fail "validation sandbox must run in a Git worktree"
git cat-file -e "$PREPARED_HEAD_OID^{commit}" ||
  fail "prepared validation commit is unavailable"

umask 077
SANDBOX_ROOT=$(mktemp -d /tmp/pr-validation.XXXXXXXX) ||
  fail "failed to create validation workspace"
SNAPSHOT=$SANDBOX_ROOT/workspace
ARCHIVE=$SANDBOX_ROOT/snapshot.tar
cleanup() {
  chmod -R u+w "$SANDBOX_ROOT" 2>/dev/null || :
  rm -rf -- "$SANDBOX_ROOT"
}
trap cleanup EXIT HUP INT TERM
mkdir "$SNAPSHOT" || fail "failed to create validation snapshot"
git archive --format=tar --output="$ARCHIVE" "$PREPARED_HEAD_OID" ||
  fail "failed to archive prepared validation commit"
tar -xf "$ARCHIVE" -C "$SNAPSHOT" ||
  fail "failed to extract prepared validation snapshot"
rm -- "$ARCHIVE" || fail "failed to remove temporary archive"

set -- "$BWRAP" \
  --die-with-parent \
  --new-session \
  --unshare-all \
  --unshare-net \
  --cap-drop ALL \
  --proc /proc \
  --dev /dev \
  --tmpfs /tmp \
  --dir /home \
  --dir /home/validator \
  --bind "$SNAPSHOT" /workspace \
  --chdir /workspace
for RUNTIME_PATH in /usr /bin /lib /lib64; do
  if [ -e "$RUNTIME_PATH" ]; then
    set -- "$@" --ro-bind "$RUNTIME_PATH" "$RUNTIME_PATH"
  fi
done

"$ENV_TOOL" -i \
  HOME=/home/validator \
  PATH=/usr/bin:/bin \
  LANG=C \
  LC_ALL=C \
  "$@" \
  /bin/sh -eu -c "$VALIDATION_COMMAND" ||
  fail "isolated validation failed or isolation is unavailable"
