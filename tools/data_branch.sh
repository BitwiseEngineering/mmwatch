#!/usr/bin/env bash
#
# Keep data/meetings.json -- the site's memory -- on a dedicated, unprotected
# `data` branch.
#
# Why: `main` requires pull requests, so the workflow's `git push` of the
# refreshed store to `main` is rejected with GH006, the build job fails, and the
# deploy is skipped. And it is EVERY run, not just days with new meetings:
# store.save() stamps generated_at each time, so the file always differs. See
# issue #4 (and civic-watch issue #25, the same failure one repo over). Branch
# protection covers `main` only, so a separate branch is writable with the stock
# GITHUB_TOKEN.
#
#   tools/data_branch.sh restore   # before the build: overlay the branch's store
#   tools/data_branch.sh persist   # after the build: push it back if the MEETINGS changed
#
# The copy of data/meetings.json committed on `main` stays the SEED: `restore`
# falls back to it when the data branch does not exist yet, and CI never writes
# to it. Deleting the `data` branch resets the site's memory to that seed.
#
# `persist` builds its commit with plumbing (hash-object/mktree/commit-tree), so
# it never checks anything out and never touches the working tree. It compares
# content with generated_at stripped, so a quiet day pushes nothing.
set -euo pipefail

BRANCH="${DATA_BRANCH:-data}"
REMOTE="${DATA_REMOTE:-origin}"
FILE="data/meetings.json"

# shellcheck disable=SC2016  # deliberately literal prose, not a template.
BRANCH_README='# mmwatch data branch

Machine-written. `.github/workflows/build.yml` pushes `data/meetings.json` here
after each build via `tools/data_branch.sh`; nothing else lives on this branch
and no human should commit to it. It exists because `main` is PR-protected and
the workflow cannot push there (issue #4). Deleting this branch resets the
meeting store to the seed committed on `main`.
'

log() { echo "data-branch: $*"; }

# Fetch the data branch into its remote-tracking ref. Non-zero if absent.
fetch_data() {
  git ls-remote --exit-code --heads "$REMOTE" "$BRANCH" >/dev/null 2>&1 || return 1
  git fetch --quiet --depth=1 "$REMOTE" "+refs/heads/$BRANCH:refs/remotes/$REMOTE/$BRANCH"
}

# Blob sha of $FILE as of the data branch; empty if the branch or file is absent.
data_blob() {
  git rev-parse --verify --quiet "refs/remotes/$REMOTE/$BRANCH:$FILE" || true
}

# Sha of the content on stdin with the generated_at line removed. store.save()
# writes indent=1, sort_keys=True, so the key sits alone on its own line.
content_sha() {
  grep -v '"generated_at"' | git hash-object --stdin
}

restore() {
  if ! fetch_data; then
    log "no '$BRANCH' branch yet; using the seed $FILE committed on this branch"
    return 0
  fi
  local blob
  blob="$(data_blob)"
  if [ -z "$blob" ]; then
    log "'$BRANCH' branch has no $FILE; using the committed seed"
    return 0
  fi
  mkdir -p "$(dirname "$FILE")"
  git cat-file blob "$blob" >"$FILE"
  log "restored $FILE from '$BRANCH' (blob ${blob:0:9})"
}

persist() {
  # build.py always writes the store on a real run; a missing file is a bug,
  # not a quiet day -- fail loudly rather than silently skipping persistence.
  if [ ! -f "$FILE" ]; then
    log "ERROR: $FILE is missing after the build; refusing to persist"
    return 1
  fi
  fetch_data || true

  local prev
  prev="$(data_blob)"
  if [ -n "$prev" ] && [ "$(git cat-file blob "$prev" | content_sha)" = "$(content_sha <"$FILE")" ]; then
    log "no data change (only generated_at moved)"
    return 0
  fi

  export GIT_AUTHOR_NAME="${DATA_COMMIT_NAME:-mmwatch-bot}"
  export GIT_AUTHOR_EMAIL="${DATA_COMMIT_EMAIL:-mmwatch-bot@users.noreply.github.com}"
  export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
  export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

  local blob readme sub tree parent commit msg
  blob="$(git hash-object -w "$FILE")"
  readme="$(printf '%s' "$BRANCH_README" | git hash-object -w --stdin)"
  sub="$(printf '100644 blob %s\t%s\n' "$blob" "$(basename "$FILE")" | git mktree)"
  # Tree entries in git's order: "README.md" sorts before "data".
  tree="$(printf '100644 blob %s\tREADME.md\n040000 tree %s\t%s\n' \
    "$readme" "$sub" "$(dirname "$FILE")" | git mktree)"

  parent="$(git rev-parse --verify --quiet "refs/remotes/$REMOTE/$BRANCH" || true)"
  msg="data: refresh meeting store ($(date -u +%Y-%m-%d))"
  if [ -n "$parent" ]; then
    commit="$(git commit-tree "$tree" -p "$parent" -m "$msg")"
  else
    commit="$(git commit-tree "$tree" -m "$msg")"
  fi

  git push --quiet "$REMOTE" "$commit:refs/heads/$BRANCH"
  log "pushed $FILE to '$BRANCH' (${commit:0:9})"
}

case "${1:-}" in
  restore) restore ;;
  persist) persist ;;
  *) echo "usage: $0 {restore|persist}" >&2; exit 2 ;;
esac
