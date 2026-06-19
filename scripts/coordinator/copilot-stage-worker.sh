#!/usr/bin/env bash
set -euo pipefail

AGENT_ID=""
TOPIC=""
JOB_ID=""
TRACE_ID=""
MODEL="gpt-5.4"
REASONING="high"
READ_SCOPE=""
WRITE_SCOPE=""
STATE_ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent) AGENT_ID="$2"; shift 2 ;;
    --topic) TOPIC="$2"; shift 2 ;;
    --job-id) JOB_ID="$2"; shift 2 ;;
    --trace-id) TRACE_ID="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --reasoning) REASONING="$2"; shift 2 ;;
    --read-scope) READ_SCOPE="$2"; shift 2 ;;
    --write-scope) WRITE_SCOPE="$2"; shift 2 ;;
    --state-root) STATE_ROOT="$2"; shift 2 ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$TOPIC" || -z "$JOB_ID" || -z "$AGENT_ID" ]]; then
  echo "Missing required args (--topic/--job-id/--agent)" >&2
  exit 2
fi

WORKSTREAM="${TOPIC%%#*}"
RUN_ID="${TOPIC#*#}"
if [[ "$RUN_ID" == "$TOPIC" ]]; then
  RUN_ID="adhoc"
fi

WS_DIR="docs/superpowers/workstreams/${WORKSTREAM}"
PLAN_PATH="${WS_DIR}/plan.md"
TASK_PATH="${WS_DIR}/task.md"
TODO_PATH="${WS_DIR}/todo.md"

for required in "$PLAN_PATH" "$TASK_PATH" "$TODO_PATH"; do
  if [[ ! -f "$required" ]]; then
    echo "Missing required workstream file: $required" >&2
    exit 2
  fi
done

TASK_TODO_COUNT="$(rg -n '^- \[ \]' "$TASK_PATH" | wc -l | tr -d ' ')"
SPRINT_TODO_COUNT="$(rg -n '^- \[ \]' "$TODO_PATH" | wc -l | tr -d ' ')"
TODO_TOTAL="$((TASK_TODO_COUNT + SPRINT_TODO_COUNT))"

read -r -d '' PROMPT <<PROMPT_EOF || true
你是 ${AGENT_ID}，負責 workstream=${WORKSTREAM}，run_id=${RUN_ID}。

必須嚴格遵守以下流程（不可跳步）：
1. executing-plans：先完整讀取
   - ${PLAN_PATH}
   - ${TASK_PATH}
   - ${TODO_PATH}
2. test-driven-development：任何實作前先寫或更新測試，必須呈現 Red -> Green -> Refactor。
3. requesting-code-review：實作完成後做自我 code review，檢查規格符合度、風險、回歸、測試完整性。
4. /opsx:archive：完成後歸檔規格文件。
   - 若 /opsx:archive 指令不可用，請建立等效歸檔文件：
     - docs/superpowers/archive/${WORKSTREAM}-${RUN_ID}.md
     - 內容至少包含：scope、實作摘要、測試證據、review 結論、未解風險。

邊界與限制：
- 僅可在當前 branch 與當前 worktree 內操作。
- 僅允許寫入以下範圍（嚴格遵守）：${WRITE_SCOPE}
- 讀取範圍：${READ_SCOPE}
- 不可修改其他 stage 的工作目錄。
- 所有文件與 commit comment 一律 zh-tw。

工作要求：
- 以最小可驗證增量完成本 workstream 的 Current Sprint + task 清單。
- 每完成一項待辦就更新 task/todo checkbox。
- 測試證據請落地到：${WS_DIR}/evidence/
- 自我 code review 結果請落地到：${WS_DIR}/review.md
- 完成後提交 commit 並 push 當前 branch（commit comment 使用 zh-tw）。

執行上下文：
- job_id=${JOB_ID}
- trace_id=${TRACE_ID}
- state_root=${STATE_ROOT}
- 初始待辦總筆數=${TODO_TOTAL}

最後回覆格式（純文字）：
1. DONE 或 BLOCKED
2. 已完成待辦數 / 總待辦數
3. 測試命令與結果摘要
4. code review 結論
5. 產生/更新檔案清單
PROMPT_EOF

copilot \
  --model "$MODEL" \
  --effort "$REASONING" \
  --allow-all-tools \
  --allow-all-paths \
  --allow-all-urls \
  --no-ask-user \
  --output-format text \
  -s \
  -p "$PROMPT"
