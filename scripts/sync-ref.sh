#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_PATH="${1:-$ROOT_DIR/openspec/specs/stage0/ref-manifest.yaml}"
REF_ROOT="$ROOT_DIR/ref"

if [[ ! -f "$MANIFEST_PATH" ]]; then
  echo "manifest not found: $MANIFEST_PATH" >&2
  exit 1
fi

mkdir -p "$REF_ROOT"

parse_manifest() {
  awk '
    /^repos:/ { in_repos=1; next }
    /^excluded:/ { in_repos=0; next }
    !in_repos { next }
    $1 == "-" && $2 == "name:" {
      if (name != "") {
        print name "|" github "|" path "|" pin "|" status
      }
      name=$3; github=""; path=""; pin=""; status=""
      next
    }
    $1 == "github:" { github=$2; next }
    $1 == "path:"   { path=$2; next }
    $1 == "pin:"    { pin=$2; next }
    $1 == "status:" { status=$2; next }
    END {
      if (name != "") {
        print name "|" github "|" path "|" pin "|" status
      }
    }
  ' "$MANIFEST_PATH"
}

while IFS='|' read -r name github path pin status; do
  [[ -n "$name" ]] || continue
  if [[ -z "$github" || -z "$path" ]]; then
    echo "[skip] $name (missing github/path in manifest)"
    continue
  fi
  if [[ "$status" == "repo_not_found" || "$pin" == "unresolved" ]]; then
    echo "[skip] $name ($status)"
    continue
  fi

  repo_url="https://github.com/${github}.git"
  abs_path="$ROOT_DIR/$path"
  mkdir -p "$(dirname "$abs_path")"

  if [[ -d "$abs_path/.git" ]]; then
    echo "[update] $name"
    git -C "$abs_path" fetch --depth 1 origin
  else
    echo "[clone] $name"
    git clone --depth 1 "$repo_url" "$abs_path"
  fi

  if [[ "$pin" != "HEAD" ]]; then
    git -C "$abs_path" fetch --depth 1 origin "$pin" || true
    git -C "$abs_path" checkout --detach "$pin"
  fi
done < <(parse_manifest)

manifest_md="$REF_ROOT/MANIFEST.md"
{
  echo "# ref/MANIFEST"
  echo
  echo "- generated_at: $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "- source: \`$MANIFEST_PATH\`"
  echo "- policy: \`ref/\` 僅供閱讀/比對，不作 runtime 載入"
  echo "- sync-back gate: \`ops-companion 回寫 custom-skills/ops-companion 前，必須先通過 Stage 6 測試並保留證據\`"
  echo
  echo "| Name | Repo | Path | Pin | Status |"
  echo "|---|---|---|---|---|"
  parse_manifest | while IFS='|' read -r name github path pin status; do
    echo "| \`$name\` | \`$github\` | \`$path\` | \`$pin\` | \`$status\` |"
  done
} > "$manifest_md"

echo "generated: $manifest_md"
