#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$repo_root/.venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  echo "找不到 repo operator runtime：請先依 README 建立並安裝 .venv" >&2
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
exec "$python_bin" -m pytest "$repo_root/tests/" "$repo_root/custom-skills/bro/tests/" -q
