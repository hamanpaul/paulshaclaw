#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/paul_chen/prj_pri/paulshaclaw"
WORKTREE_BASE="/home/paul_chen/prj_pri/paulshaclaw-worktrees"
STATE_ROOT="/home/paul_chen/.agents/state/coordinator"
COORDINATOR_SH="/home/paul_chen/prj_pri/custom-skills/coordinator/scripts/coordinator.sh"
WORKER_SCRIPT="${ROOT}/scripts/coordinator/copilot-stage-worker.sh"
NOTIFIER_PY="${ROOT}/scripts/coordinator/coordinator_telegram_notifier.py"
API_TOKEN_PATH="${HOME}/.max/api-token"
RUN_ID="$(date +%Y%m%dT%H%M%S%z | tr -d '+')"

WORKSTREAMS=(
  "stage0-tooling-foundation"
  "stage1-core-daemon-tui-bot"
  "stage2-paulsha-memory"
  "stage6-ops-companion-security"
)

DISPATCH_DIR="${STATE_ROOT}/dispatch/${RUN_ID}"
mkdir -p "${DISPATCH_DIR}"
META_FILE="${DISPATCH_DIR}/tasks.tsv"
: > "${META_FILE}"

count_unchecked() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo 0
    return
  fi
  rg -n '^- \[ \]' "$path" | wc -l | tr -d ' '
}

send_notify() {
  local text="$1"
  local token
  token="$(cat "${API_TOKEN_PATH}")"
  curl -s -X POST http://127.0.0.1:7777/notify \
    -H "Authorization: Bearer ${token}" \
    -H 'Content-Type: application/json' \
    -d "$(python3 - <<'PY' "$text"
import json,sys
print(json.dumps({"text": sys.argv[1]}, ensure_ascii=False))
PY
)" >/dev/null
}

total_tasks="${#WORKSTREAMS[@]}"
start_line="任務開始，共拆分${total_tasks} 個任務，每個任務的待辦總筆數："

for ws in "${WORKSTREAMS[@]}"; do
  worktree="${WORKTREE_BASE}/${ws}"
  task_file="${worktree}/docs/superpowers/workstreams/${ws}/task.md"
  todo_file="${worktree}/docs/superpowers/workstreams/${ws}/todo.md"

  if [[ ! -d "$worktree" ]]; then
    echo "Missing worktree: ${worktree}" >&2
    exit 2
  fi

  task_count="$(count_unchecked "$task_file")"
  todo_count="$(count_unchecked "$todo_file")"
  todo_total="$((task_count + todo_count))"

  topic="${ws}#${RUN_ID}"
  agent_id="agent-${ws}"

  printf '%s\t%s\t%s\t%s\n' "$ws" "$topic" "$worktree" "$todo_total" >> "${META_FILE}"

  start_line+="${ws}=${todo_total}；"

  cmd=(
    bash "${COORDINATOR_SH}" --state-root "${STATE_ROOT}" run
    --topic "${topic}"
    --from-agent manager
    --to-agents "${agent_id}"
    --provider copilot
    --model gpt-5.4
    --reasoning high
    --read-scope "${worktree}/**"
    --write-scope "${worktree}/**"
    --worker-mode template
    --worker-cmd-template "${WORKER_SCRIPT} --agent {agent_id} --topic {topic} --job-id {job_id} --trace-id {trace_id} --model {model} --reasoning {reasoning} --read-scope {read_scope} --write-scope {write_scope} --state-root {state_root}"
    --worker-timeout-sec 7200
    --worker-cwd "${worktree}"
  )

  cmd_text="$(printf '%q ' "${cmd[@]}")"
  {
    printf 'CMD: %s\n' "${cmd_text}"
    printf 'LAUNCHED_AT: %s\n' "$(date -Iseconds)"
  } >>"${DISPATCH_DIR}/${ws}.run.log"

  setsid -f bash -lc "${cmd_text} >>${DISPATCH_DIR}/${ws}.run.log 2>&1"
done

send_notify "${start_line}"

setsid -f python3 "${NOTIFIER_PY}" \
  --run-id "${RUN_ID}" \
  --meta-file "${META_FILE}" \
  --state-root "${STATE_ROOT}" \
  --interval-sec 1800 \
  --api-token-path "${API_TOKEN_PATH}" \
  >>"${DISPATCH_DIR}/notifier.log" 2>&1

echo "RUN_ID=${RUN_ID}"
echo "META_FILE=${META_FILE}"
echo "DISPATCH_DIR=${DISPATCH_DIR}"
echo "NOTIFIER_PID=$(pgrep -f -- \"coordinator_telegram_notifier.py --run-id ${RUN_ID}\" | tr '\n' ',' | sed 's/,$//')"
