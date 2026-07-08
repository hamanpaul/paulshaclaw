# cortex-extraction 最終 code review

日期：2026-07-08

## 範圍

- Plan：`docs/superpowers/plans/2026-07-07-cortex-2-main-repo-knife.md`
- branch：`feature/232-cortex-extraction`
- review 範圍：main → cortex extraction 全 branch，含未提交的 Task 7 / review-fix working tree

## 已檢查重點

- `paulsha-cortex` SHA pin 與消費者 import cutover
- `psc coordinator|deck|monitor` shim 與 tombstone
- `persona/coordinator/control/deck/monitor` 五包刪除與測試/腳本遷出
- `deploy/planner.py` / `scripts/start.sh` 的 cortex cutover
- 三個 alignment tests
- import surface gate、README、agent 慣例檔同步

## review 結論

- 無剩餘 **Critical** / **Important** issue
- 當前 working tree 可視為 **ready to merge**

## review 過程中已收斂的問題

1. `scripts/start.sh` fallback 一度直接碰 cortex internal module path；已改成只走公開 CLI：
   - `python -m paulsha_cortex.cli monitor`
   - `python -m paulsha_cortex.cli tick --specs-dir ... --require-idle`
2. import surface gate 補齊後，runtime `paulsha_hippo` import 已清掉，並將檢查規則固化到 `scripts/check_import_surface.py`
3. `psc coordinator --help` smoke 與實際安裝的 cortex umbrella CLI 對齊，`coordinator` 改轉發 `rest`，`deck` / `monitor` 維持 `[sub, *rest]`

## 最終驗證摘要

- `python -m pytest tests/ -q` → `447 passed, 13 skipped, 34 subtests passed`
- `python scripts/check_import_surface.py` → `import surface OK`
- `bash -n scripts/start.sh` → `OK`
- `psc coordinator --help` → exit `0`
