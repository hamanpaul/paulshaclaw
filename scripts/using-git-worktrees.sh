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

while IFS=$'\t' read -r workstream branch dir stage; do
  [[ "$workstream" == "workstream" ]] && continue
  [[ -z "$workstream" ]] && continue

  target="$WT_ROOT/$dir"

  if git -C "$REPO_ROOT" worktree list --porcelain | awk '/^worktree /{print $2}' | grep -Fxq "$target"; then
    echo "[skip] $workstream already mounted: $target"
    continue
  fi

  if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$branch"; then
    echo "[add] $workstream -> existing branch $branch"
    git -C "$REPO_ROOT" worktree add "$target" "$branch"
  else
    echo "[add] $workstream -> new branch $branch from $BASE_REF"
    git -C "$REPO_ROOT" worktree add -b "$branch" "$target" "$BASE_REF"
  fi
done < "$MAP_FILE"

echo "done: worktrees under $WT_ROOT"
