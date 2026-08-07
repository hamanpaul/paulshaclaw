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

# 選擇直譯器：優先用 repo .venv（含完整 runtime closure），否則用系統 python3。
python_bin="$repo_root/.venv/bin/python"
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

wheel="$(ls "$outdir"/*.whl)"
sdist="$(ls "$outdir"/*.tar.gz)"
echo "    wheel: $wheel"
echo "    sdist: $sdist"

# 3. metadata / package-content 檢查。
echo "==> package-content 檢查"
# 3a. wheel 必須含 cockpit.tcss（CSS_PATH 於 wheel 安裝時才找得到）。
if ! "$python_bin" -m zipfile -l "$wheel" | grep -q "paulshaclaw/cockpit/cockpit.tcss"; then
  echo "FAIL: wheel 未包含 cockpit/cockpit.tcss package data" >&2
  exit 1
fi
echo "    cockpit.tcss 已包含於 wheel"
# 3b. METADATA version 必須等於 VERSION。
meta_version="$("$python_bin" -m zipfile -e "$wheel" /tmp/psc-rel-extract >/dev/null 2>&1; \
  grep -m1 '^Version:' /tmp/psc-rel-extract/paulshaclaw-*.dist-info/METADATA | awk '{print $2}')"
rm -rf /tmp/psc-rel-extract
file_version="$(cat "$repo_root/VERSION")"
if [[ "$meta_version" != "$file_version" ]]; then
  echo "FAIL: wheel METADATA version($meta_version) != VERSION($file_version)" >&2
  exit 1
fi
echo "    wheel METADATA version=$meta_version 與 VERSION 一致"

# 3c. entry point psc 必須在 RECORD / entry_points。
if ! "$python_bin" -m zipfile -l "$wheel" | grep -q "entry_points.txt"; then
  echo "FAIL: wheel 缺少 entry_points.txt（psc entry point）" >&2
  exit 1
fi
echo "    entry_points.txt 已包含於 wheel"

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
    "$clean_root/venv/bin/psc" --help >/dev/null
    echo "psc --help OK"
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