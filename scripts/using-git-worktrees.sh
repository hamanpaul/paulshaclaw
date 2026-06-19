#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAP_FILE="${1:-$REPO_ROOT/config/worktrees/stage-worktrees.tsv}"
WT_ROOT="${2:-/home/paul_chen/prj_pri/paulshaclaw-worktrees}"
BASE_REF="${3:-main}"

if [[ ! -f "$MAP_FILE" ]]; then
  echo "map file not found: $MAP_FILE" >&2
  exit 1
fi

mkdir -p "$WT_ROOT"

has_local_branch() {
  local branch="$1"
  git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$branch"
}

has_remote_branch() {
  local branch="$1"
  git -C "$REPO_ROOT" show-ref --verify --quiet "refs/remotes/origin/$branch"
}

ensure_remote_branch() {
  local branch="$1"
  local status

  if git -C "$REPO_ROOT" ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
    git -C "$REPO_ROOT" fetch --prune origin "+refs/heads/$branch:refs/remotes/origin/$branch" >/dev/null 2>&1
    has_remote_branch "$branch"
    return $?
  fi

  status=$?
  if [[ $status -eq 2 ]]; then
    git -C "$REPO_ROOT" update-ref -d "refs/remotes/origin/$branch" >/dev/null 2>&1 || true
    return 1
  fi

  echo "failed to query origin/$branch" >&2
  return 2
}

while IFS=$'\t' read -r workstream branch dir stage; do
  [[ "$workstream" == "workstream" ]] && continue
  [[ -z "$workstream" ]] && continue

  target="$WT_ROOT/$dir"

  if git -C "$REPO_ROOT" worktree list --porcelain | awk '/^worktree /{print $2}' | grep -Fxq "$target"; then
    echo "[skip] $workstream already mounted: $target"
    continue
  fi

  if has_local_branch "$branch"; then
    echo "[add] $workstream -> existing branch $branch"
    git -C "$REPO_ROOT" worktree add "$target" "$branch"
  else
    remote_status=0
    if ensure_remote_branch "$branch"; then
      echo "[add] $workstream -> tracking origin/$branch"
      git -C "$REPO_ROOT" worktree add --track -b "$branch" "$target" "origin/$branch"
      continue
    fi
    remote_status=$?
    if [[ $remote_status -eq 2 ]]; then
      exit 1
    fi

    echo "[add] $workstream -> new branch $branch from $BASE_REF"
    git -C "$REPO_ROOT" worktree add -b "$branch" "$target" "$BASE_REF"
  fi
done < "$MAP_FILE"

echo "done: worktrees under $WT_ROOT"
