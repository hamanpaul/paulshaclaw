## 1. 上游引擎（paulsha-conventions，跨 repo 前置）

- [ ] 1.1 於 paulsha-conventions 依 #45 實作：R-21 visibility 綁定（PUBLIC repo 一律掃描，tier 僅豁免 private）＋ 逃逸不得回綠燈
- [ ] 1.2 嚴重度分層：結構/憑證類 public 一律 FAIL；字面 marker 類 public+work 為 WARN
- [ ] 1.3 marker env 擴充點：`resolve_markers` 疊加 secret env 來源（extend-only），公開 yml 零字面新增
- [ ] 1.4 輸出遮蔽：命中值不印入 CI log／stdout（fixture 驗證含遮蔽斷言）
- [ ] 1.5 新增 #45 驗收 fixture（public+work 植入結構樣式 → FAIL；private+work → WARN）並 release 新版（RELEASES.md 記 SHA）

## 2. 本 repo dry-run（先私下盤點）

- [ ] 2.1 以目標引擎版本本機實跑 policy_check（dry-run），輸出遮蔽模式
- [ ] 2.2 核對 dry-run 命中 == #201 逐檔清單（多出的先補回 #201，不多不少才續行）

## 3. Stage A 清理（paulshaclaw）

- [ ] 3.1 `memory/instruction_corpus.py` 第 2 corpus root 改 `PSC_EXTRA_CORPUS_ROOT` env 供給（未設 = 不含該 root），含行為測試
- [ ] 3.2 `scripts/start.sh` dream loop `--instruction-root` 對應改 env 帶入
- [ ] 3.3 兩個 test fixture 字面值換中性名（測試語意不變）
- [ ] 3.4 docs plans／openspec archive 8 檔字面值換中性佔位（內容其餘逐字不動）
- [ ] 3.5 實作安全驗證器（scripts/，讀 secret 字面表＋結構 regex；輸出僅計數/遮蔽代號/路徑）並以其確認全樹歸零

## 4. gate 上線與 hook

- [ ] 4.1 policy-check.yml pin bump 至修復版引擎（uses 與 policy_engine_ref 同 SHA；本機零 fail 才推）
- [ ] 4.2 CI secret 設定字面 marker env（repo settings，值不落任何檔案）
- [ ] 4.3 authoring warn hook：PostToolUse(Write|Edit) 腳本＋settings 接線＋install.sh 同步（沿既有 hooks 模式），字面表缺席降級測試

## 5. 驗證與收尾

- [ ] 5.1 全套件測試綠；Policy Check 綠且 R-21 實掃（非 not-applicable）
- [ ] 5.2 #201 Stage A checklist 勾銷、附安全驗證器輸出（遮蔽版）為證據
