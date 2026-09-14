#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -P "$script_dir/.." && pwd)"

# shellcheck source=/dev/null
source "$script_dir/start.sh" --source-only

# Manager shells may carry PSC_REPO_ROOT for a different checkout (for example
# the cortex runtime).  This gate validates the current checkout; retaining
# that override makes paths.repo_root() escape the worktree even though the
# test PYTHONPATH is correct.
unset PSC_REPO_ROOT

if ! python_bin="$(resolve_preflight_python "$repo_root")"; then
  echo "找不到可執行 preflight 的 Python（需 import ${PREFLIGHT_RUNTIME_MODULES[*]}，缺模組與試過的路徑見上方）：請設 VIRTUAL_ENV 或 PSC_PYTHON 指向含完整 runtime 的 Python" >&2
  exit 2
fi

# policy-preflight 會以 deterministic C locale 啟動 repo gate；tmux 在該
# locale 下會把 format 內的 tab 轉成 underscore，破壞 pane parser。
# 回復 runner 保留的 UTF-8 LANG，讓測試與實際 operator runtime 一致。
if [[ "${LC_ALL:-}" == "C" && "${LANG:-C}" != "C" ]]; then
  export LC_ALL="$LANG"
fi

# custom-skills 的測試不在 tests/ 底下，得明確列出。漏掉它等於讓
# reply_bridge 的 facade 漂移把關（#90）永遠不會執行。
# deploy package acceptance tests invoke `python -m build`; use the same
# operator runtime, but do not mutate it when the frontend is already present.
if ! env PYTHONPATH="$repo_root" "$python_bin" -c 'import build' >/dev/null 2>&1; then
  if ! env PYTHONPATH="$repo_root" "$python_bin" -m pip install --quiet build; then
    echo "operator runtime 缺少 build 且無法安裝；請先在該 runtime 執行 '$python_bin -m pip install build' 後重跑 preflight" >&2
    exit 2
  fi
  if ! env PYTHONPATH="$repo_root" "$python_bin" -c 'import build' >/dev/null 2>&1; then
    echo "build 安裝後仍無法 import；請確認 '$python_bin' 指向可用的 operator runtime 後重跑 preflight" >&2
    exit 2
  fi
fi
exec env PYTHONPATH="$repo_root" "$python_bin" -m pytest \
  "$repo_root/tests/" "$repo_root/custom-skills/bro/tests/" -q
