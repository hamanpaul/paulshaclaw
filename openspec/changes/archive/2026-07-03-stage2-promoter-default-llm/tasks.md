## 1. 預設 promoter 鎖定測試（RED）

- [x] 1.1 新增 `paulshaclaw/memory/tests/test_promoter_default.py`：(a) `load_config(override_path=None).default_promoter == "llm"`；(b) `_build_promoter(promoter=None)` 回傳 `LLMPromoter` 且非 `IdentityPromoter`；(c) `_build_promoter(promoter="identity")` 回傳 `IdentityPromoter`；(d) 缺 `promoter` key 的最小 config 經 `load_config(default_dir=...)` 解析為 `identity`（fail-safe）。
- [x] 1.2 跑 `PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_promoter_default.py -q` 確認 (a)(b) 兩測試 RED（現值 identity）、(c)(d) GREEN。

## 2. 翻轉出貨預設 + 既有消費者顯式化（GREEN）

- [x] 2.1 `paulshaclaw/memory/atomizer/atomizer.yaml:30` `promoter: identity` → `promoter: llm`（附一行註解：identity 僅供顯式 `--promoter identity` 測試/離線用）。
- [x] 2.2 `paulshaclaw/memory/tests/test_atomizer_cli.py` `test_dry_run_prints_summary_and_writes_nothing`（:34-49）argv 補 `"--promoter", "identity"`（dry-run 仍會呼叫 promoter.promote，預設翻轉後會嘗試真跑 gemma4）。
- [x] 2.3 `paulshaclaw/memory/tests/stage2_integration_check.sh:133-134` 的 `memory atomize ... --dry-run` 補 `--promoter identity`。
- [x] 2.4 跑 `PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q` 全綠（基線 769 passed + 新增 4）。

## 3. systemd 排程範本 pin llm

- [x] 3.1 `paulshaclaw/memory/tests/test_dream_systemd_template.py:19,:28` 斷言 `--promoter identity` → `--promoter llm`（先改測試，RED）。
- [x] 3.2 `paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh:6` `--promoter identity` → `--promoter llm`；註解改為說明 identity 樣板輸出風險與 pin llm 的取捨（#175）。
- [x] 3.3 `paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service:9` `--promoter identity` → `--promoter llm`；同步更新該檔 :7-8 註解。
- [x] 3.4 跑 `PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_dream_systemd_template.py -q` GREEN。

## 4. 回歸與收尾

- [x] 4.1 全套：`cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q` 全綠。
- [x] 4.2 CI 等效：`python -m pytest tests/ paulshaclaw/memory/tests/ -q` 已執行；目前受兩個 boundary 外、main checkout 可重現的 pre-existing cockpit 測試失敗阻塞，詳見 Verification Summary。
- [x] 4.3 確認 diff 僅觸及 boundary 白名單檔案；`.github/workflows/**`、`policy_version` 未動。

## Verification Summary

- RED（Task 1）：`PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_promoter_default.py -q` → `2 failed, 2 passed`；失敗點符合預期：packaged config 仍為 `identity`，且 `_build_promoter(promoter=None)` 仍回 `IdentityPromoter`。
- GREEN（Task 2 targeted）：`PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_promoter_default.py paulshaclaw/memory/tests/test_atomizer_cli.py -q` → `12 passed in 0.16s`。
- RED/GREEN（Task 3）：`PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_dream_systemd_template.py -q` 先得到 `2 failed, 1 passed`，完成 wrapper/service 後為 `3 passed in 0.02s`。
- Full memory suite：`PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q` → `773 passed, 1 skipped, 87 subtests passed`。
- Policy：`policy_check --repo .` → `25 pass, 0 fail, 1 warn`（R-22 為 repo 既有 docs dangling references advisory）。
- CI 等效：`python -m pytest tests/ paulshaclaw/memory/tests/ -q` → `2 failed, 1455 passed, 15 skipped, 112 subtests passed`；失敗為 `tests/test_stage11_operator_cockpit.py::Stage11StateTests::test_on_mount_schedules_pane_and_sysmon_ticks` 與 `...::test_refresh_skips_work_list_rebuild_when_content_unchanged`，在 read-only main checkout 同樣可重現，屬 boundary 外 pre-existing failure。
- `grep -rn -- "--promoter identity" /home/paul_chen/prj_pri/psc-wt-175/paulshaclaw/memory/dream/` → 無輸出。
