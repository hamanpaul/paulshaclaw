## 1. 預設 promoter 鎖定測試（RED）

- [ ] 1.1 新增 `paulshaclaw/memory/tests/test_promoter_default.py`：(a) `load_config(override_path=None).default_promoter == "llm"`；(b) `_build_promoter(promoter=None)` 回傳 `LLMPromoter` 且非 `IdentityPromoter`；(c) `_build_promoter(promoter="identity")` 回傳 `IdentityPromoter`；(d) 缺 `promoter` key 的最小 config 經 `load_config(default_dir=...)` 解析為 `identity`（fail-safe）。
- [ ] 1.2 跑 `PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_promoter_default.py -q` 確認 (a)(b) 兩測試 RED（現值 identity）、(c)(d) GREEN。

## 2. 翻轉出貨預設 + 既有消費者顯式化（GREEN）

- [ ] 2.1 `paulshaclaw/memory/atomizer/atomizer.yaml:30` `promoter: identity` → `promoter: llm`（附一行註解：identity 僅供顯式 `--promoter identity` 測試/離線用）。
- [ ] 2.2 `paulshaclaw/memory/tests/test_atomizer_cli.py` `test_dry_run_prints_summary_and_writes_nothing`（:34-49）argv 補 `"--promoter", "identity"`（dry-run 仍會呼叫 promoter.promote，預設翻轉後會嘗試真跑 gemma4）。
- [ ] 2.3 `paulshaclaw/memory/tests/stage2_integration_check.sh:133-134` 的 `memory atomize ... --dry-run` 補 `--promoter identity`。
- [ ] 2.4 跑 `PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q` 全綠（基線 769 passed + 新增 4）。

## 3. systemd 排程範本 pin llm

- [ ] 3.1 `paulshaclaw/memory/tests/test_dream_systemd_template.py:19,:28` 斷言 `--promoter identity` → `--promoter llm`（先改測試，RED）。
- [ ] 3.2 `paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh:6` `--promoter identity` → `--promoter llm`；註解改為說明 identity 樣板輸出風險與 pin llm 的取捨（#175）。
- [ ] 3.3 `paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service:9` `--promoter identity` → `--promoter llm`；同步更新該檔 :7-8 註解。
- [ ] 3.4 跑 `PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_dream_systemd_template.py -q` GREEN。

## 4. 回歸與收尾

- [ ] 4.1 全套：`cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q` 全綠。
- [ ] 4.2 CI 等效：`python -m pytest tests/ paulshaclaw/memory/tests/ -q` 全綠。
- [ ] 4.3 確認 diff 僅觸及 boundary 白名單檔案；`.github/workflows/**`、`policy_version` 未動。

## Verification Summary

（實作完成後回填：focused 測試指令輸出、全套結果、grep 驗證兩個 systemd 範本無殘留 `--promoter identity`。）
