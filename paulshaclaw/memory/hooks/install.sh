#!/usr/bin/env bash
set -euo pipefail

memory_root="${HOME}/.agents/memory"
tree_only=false

while (($#)); do
  case "$1" in
    --tree-only)
      tree_only=true
      shift
      ;;
    --memory-root)
      if (($# < 2)); then
        echo "install.sh: --memory-root requires a path" >&2
        exit 2
      fi
      memory_root="$2"
      shift 2
      ;;
    *)
      echo "install.sh: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "$tree_only" != true ]]; then
  echo "install.sh: only --tree-only is implemented in this MVP task" >&2
  exit 2
fi

if [[ "$memory_root" =~ ^[[:space:]]*$ ]]; then
  echo "install.sh: --memory-root must not be empty" >&2
  exit 2
fi

if [[ "$memory_root" =~ ^/+$ ]]; then
  echo "install.sh: --memory-root must not be /" >&2
  exit 2
fi

dirs=(
  "inbox"
  "work-centric"
  "knowledge"
  "runtime"
  "log"
  "hooks"
  "archive"
  "inbox/sessions"
  "inbox/plans"
  "inbox/research"
  "inbox/reports"
  "work-centric/common-sense"
  "runtime/queue"
  "runtime/queue/_failed"
  "runtime/locks"
  "runtime/ledger"
  "runtime/indexes"
  "archive/queue"
)

for relative in "${dirs[@]}"; do
  path="${memory_root}/${relative}"
  install -d -m 700 -- "$path"
  touch -- "${path}/.gitkeep"
done
