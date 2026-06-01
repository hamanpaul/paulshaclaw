#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf -- "$TMP_DIR"' EXIT

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

require_hook_dry_run() {
  local label="$1"
  local hook_script="$2"
  local fixture="$3"
  local queue_pattern="$4"
  local output
  local queue_item
  local -a queue_matches=()

  echo "[stage2] ${label}"
  PSC_MEMORY_ROOT="$TMP_DIR/memory" \
    PSC_CONFIG_ROOT="$TMP_DIR/config-root" \
    python3 "$ROOT_DIR/paulshaclaw/memory/hooks/${hook_script}" <"$fixture"
  while IFS= read -r match; do
    queue_matches+=("$match")
  done < <(find "$TMP_DIR/memory/runtime/queue" -maxdepth 1 -type f -name "$queue_pattern" | sort)
  test "${#queue_matches[@]}" -eq 1
  queue_item="${queue_matches[0]}"
  test -s "$queue_item"
  output="$(
    PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.importer.cli ingest \
      --queue-item "$queue_item" \
      --memory-root "$TMP_DIR/memory" \
      --dry-run
  )"
  grep -Fq '"status": "written"' <<<"$output"
  grep -Fq '"dry_run": true' <<<"$output"
  grep -Fq '"classifier_bucket"' <<<"$output"
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

echo "[stage2] validate memory policy consumer lint"
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.lint.policy_consumer_lint "$ROOT_DIR/paulshaclaw"

require_hook_dry_run \
  "fixture dry-run claude" \
  "claude_session_end.py" \
  "$ROOT_DIR/paulshaclaw/memory/tests/fixtures/claude/session_end/payload.json" \
  "claude-code__claude-session-end-001.json"

require_hook_dry_run \
  "fixture dry-run codex" \
  "codex_session_end.py" \
  "$ROOT_DIR/paulshaclaw/memory/tests/fixtures/codex/stop/payload.json" \
  "codex__codex-stop-001*.json"

require_hook_dry_run \
  "fixture dry-run copilot" \
  "copilot_session_end.py" \
  "$ROOT_DIR/paulshaclaw/memory/tests/fixtures/copilot/session_end/payload.json" \
  "copilot-cli__copilot-session-end-001.json"

echo "[stage2] janitor dry-run over fixtures"
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory janitor scan \
  --memory-root "$(mktemp -d)" \
  --knowledge-root "$ROOT_DIR/paulshaclaw/memory/tests/fixtures/knowledge/ttl" \
  --now "2026-05-31T00:00:00Z" \
  --dry-run | grep -Fq '"decayed": 1'

echo "[stage2] atomizer dry-run over fixtures"
ATOMIZE_ROOT="$(mktemp -d)"
mkdir -p "$ATOMIZE_ROOT/inbox/research/claude/2026-05-31"
cp "$ROOT_DIR/paulshaclaw/memory/tests/fixtures/atomizer/raw/s1.md" \
   "$ATOMIZE_ROOT/inbox/research/claude/2026-05-31/s1.md"
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory atomize \
  --memory-root "$ATOMIZE_ROOT" --now "2026-05-31T03:00:00Z" --dry-run | grep -Fq '"slices":'

echo "[stage2] ok"
