#!/usr/bin/env bash
# release-artifacts.sh — 本機 release dry-run 入口。
#
# 產生 wheel + sdist，做 metadata / package-content 檢查，並在乾淨 venv 從
# artifact 安裝執行 smoke test。不建立 GitHub Release、不 push tag。
#
# 用法：
#   scripts/release-artifacts.sh              # 完整 dry-run（build + verify）
#   scripts/release-artifacts.sh --no-install # 只 build + metadata/content 檢查
#
# 環境變數：
#   PSC_BUILD_OUTDIR  artifact 輸出目錄（預設 dist/）
#   PSC_PYTHON        已建立且可安裝 build 的 Python（預設 repo .venv）
#
# 退出碼：0 通過；非零代表 build 或驗證失敗（fail-closed）。
set -euo pipefail

repo_root="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
outdir="${PSC_BUILD_OUTDIR:-$repo_root/dist}"
do_install=1

for arg in "$@"; do
  case "$arg" in
    --no-install) do_install=0 ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "未知參數：$arg" >&2
      exit 2
      ;;
  esac
done

# 選擇直譯器：優先用 PSC_PYTHON，再用 repo .venv，最後才探測系統 python3。
# 系統 Python 可能受 PEP 668 保護；正式執行仍應使用已建立的 venv。
python_bin="${PSC_PYTHON:-$repo_root/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  python_bin="$(command -v python3 || true)"
  if [[ -z "$python_bin" ]]; then
    echo "找不到可用的 python（.venv/bin/python 或系統 python3）" >&2
    exit 2
  fi
fi

echo "==> 選擇直譯器：$python_bin"
"$python_bin" -m pip install --quiet --upgrade pip >/dev/null
"$python_bin" -m pip install --quiet build >/dev/null

# 1. 版本一致性 pre-gate（不帶 --tag，只檢查 VERSION/pyproject）。
echo "==> 版本一致性 gate"
"$python_bin" "$repo_root/scripts/check-release-consistency.py" --repo-root "$repo_root"

# 2. build wheel + sdist 到 outdir。
echo "==> build wheel + sdist（輸出至 $outdir）"
rm -rf "$outdir"
mkdir -p "$outdir"
"$python_bin" -m build --outdir "$outdir" "$repo_root"

# 用 glob 陣列而非 `ls`：多於一個 artifact 時 `ls` 會回傳多行，後續會把
# 含換行的字串當成單一路徑餵給 zipfile / sha256sum 而以難解的錯誤爆掉。
shopt -s nullglob
wheels=("$outdir"/*.whl)
sdists=("$outdir"/*.tar.gz)
shopt -u nullglob
if [[ ${#wheels[@]} -ne 1 || ${#sdists[@]} -ne 1 ]]; then
  echo "FAIL: 預期恰好 1 個 wheel 與 1 個 sdist，實際 ${#wheels[@]} wheel / ${#sdists[@]} sdist" >&2
  exit 1
fi
wheel="${wheels[0]}"
sdist="${sdists[0]}"
echo "    wheel: $wheel"
echo "    sdist: $sdist"

# 3. metadata / package-content 檢查。local release 與 GitHub release
# workflow 共用同一個 stdlib-only checker，避免兩條 release 入口漂移；
# checker 同時守住 cockpit.tcss、paulshaclaw/core/commands.json 與 launcher。
echo "==> package-content 檢查"
"$python_bin" "$repo_root/scripts/check-release-artifacts.py" \
  --wheel "$wheel" \
  --sdist "$sdist" \
  --source-root "$repo_root"

# 4. 乾淨 venv 安裝 smoke test。
if [[ "$do_install" == "1" ]]; then
  echo "==> 乾淨 venv 安裝 + smoke test"
  clean_root="$(mktemp -d)"
  trap 'rm -rf "$clean_root"' EXIT
  "$python_bin" -m venv "$clean_root/venv"
  "$clean_root/venv/bin/python" -m pip install --quiet --upgrade pip >/dev/null
  "$clean_root/venv/bin/python" -m pip install --quiet "$wheel" >/dev/null
  smoke_dir="$(mktemp -d)"
  # 必須在非 repo root 執行，避免 cwd '' 污染 sys.path 載到 repo source。
  (
    cd "$smoke_dir"
    "$clean_root/venv/bin/python" -c "
import paulshaclaw
import paulsha_cortex, paulsha_hippo, paulsha_hippo.lib.lifecycle
import paulshaclaw.cost.config, paulshaclaw.cockpit, textual
from pathlib import Path
import paulshaclaw.cockpit as c
assert (Path(c.__file__).parent / 'cockpit.tcss').exists(), 'cockpit.tcss 未隨安裝'
print('import closure + tcss OK')
"
    # psc 是 dispatcher：無法辨識的子命令印 usage 到 stderr 並回 2，沒有
    # --help。smoke test 驗的是 console script 裝得起來、能載入模組並印出
    # usage，不能要求 exit 0（會讓 set -e 直接中止）。#357 起裸 `psc` 等同
    # `paulshaclaw up`（會真的啟動 operator shell），絕不可裸呼叫。
    set +e
    psc_out="$("$clean_root/venv/bin/psc" __release-smoke__ 2>&1)"
    psc_rc=$?
    set -e
    if [[ "$psc_rc" != "2" ]] || [[ "$psc_out" != *"usage: psc"* ]]; then
      echo "FAIL: psc entry point 異常（exit=$psc_rc, output=$psc_out）" >&2
      exit 1
    fi
    echo "psc entry point OK（usage + exit 2）"
    # #288：paulshaclaw 正式啟動入口 --help 必須 exit 0。
    "$clean_root/venv/bin/paulshaclaw" --help >/dev/null
    echo "paulshaclaw entry point OK（--help exit 0）"
  )
  rm -rf "$smoke_dir"
fi

# 5. SHA-256 checksums。
echo "==> SHA-256 checksums"
checksums="$outdir/checksums-sha256.txt"
( cd "$outdir" && sha256sum "$(basename "$wheel")" "$(basename "$sdist")" > "$checksums" )
echo "    $checksums"
cat "$checksums"

echo "==> release dry-run 完成"
echo "    artifacts: $outdir"
