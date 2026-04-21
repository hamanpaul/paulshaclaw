#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

require_text() {
  local label="$1"
  local file="$2"
  shift 2

  echo "[stage2] ${label}"
  test -f "$file"
  for needle in "$@"; do
    grep -Fq "$needle" "$file"
  done
}

require_text \
  "validate scope" \
  "$ROOT_DIR/openspec/specs/stage2/scope.md" \
  "inbox -> work-centric -> knowledge" \
  "decayed/reactivation"

require_text \
  "validate memory routing" \
  "$ROOT_DIR/paulshaclaw/memory/routing.md" \
  "inbox" \
  "knowledge"

require_text \
  "validate janitor service" \
  "$ROOT_DIR/paulshaclaw/janitor/service.md" \
  "systemd" \
  "reactivation"

require_text \
  "validate sync-back gate" \
  "$ROOT_DIR/custom-skills/paulsha-memory/README.md" \
  "sync-back gate" \
  "stage 測試" \
  "Stage 3 frontmatter schema"

require_text \
  "validate Stage 3 frontmatter field names named explicitly" \
  "$ROOT_DIR/openspec/specs/stage2/scope.md" \
  "slice_id" \
  "artifact_kind" \
  "supersedes" \
  "checksum"

require_text \
  "validate evidence template" \
  "$ROOT_DIR/docs/superpowers/workstreams/stage2-paulsha-memory/evidence/stage2-integration-template.md" \
  "測試命令" \
  "證據檔名"

require_text \
  "validate review result" \
  "$ROOT_DIR/docs/superpowers/workstreams/stage2-paulsha-memory/review.md" \
  "無阻斷性問題" \
  "Stage 3 frontmatter schema"

echo "[stage2] ok"
