## Context

#125 Phase 2 拆包執行（issue #232）。權威設計：`docs/superpowers/specs/2026-07-07-cortex-extraction-design.md`（brainstorm 2026-07-07 定案 + Codex 對抗審查裁決：cutover 協議／單寫者不變量採納，control root 隔離／persona fail-close 重設計推回）。現況耦合：manager→persona 單向窄介面（gate/handoff/render/contract 四入口）；治理包對 hippo 僅兩處 lib import（`persona/contract.py:10` PHASES、`coordinator/manager.py:217` idle）；control.client 的主 repo 消費者三處（bot/listener、cockpit/app、core/daemon）；`psc coordinator` 由 cli.py lazy import 路由。

## Goals / Non-Goals

**Goals:** 治理包（persona+coordinator+control）獨立可安裝且對 hippo 零依賴、主 repo 以 SHA pin 引回、`psc coordinator` shim 無感遷移、三個對齊測試以主 repo 為契約交會點、systemd cutover 協議可回滾。

**Non-Goals:** paulsha-lib 升格、deck 搬移或拆分、G2 enforce 翻牌（#124，拆分後於 cortex repo 內做）、hippo 任何變動、PyPI 發版、control root 多實例／租戶隔離重設計。

## Decisions

| 決策 | 裁決 | 為什麼不是替代案 |
|---|---|---|
| 包數 | 一支 repo（persona+coordinator+control 同包） | 拆兩支各 800/2.5k 行太薄、repo 稅 ×2；G2 enforce 將同時動 dispatch 與 gate，同包才有 atomic PR；單向依賴留內部，真有獨立客群再二次拆分（hippo 刀法已演練） |
| 命名 | `paulsha-cortex` / package `paulsha_cortex` | 延續 hippo 腦區隱喻：前額葉皮質＝執行功能（派工決策）+ 行為抑制（persona 護欄）；`paulsha-manager` 漏 persona 語意、`paulsha-gov` 易誤讀 |
| hippo 依賴 | **A′ 零依賴**：PHASES 自帶 + idle 23 行 vendor + paths 5 函式自帶 | 掛 hippo 依賴＝為 7 字串 + 23 行拉整個 31k 行記憶產品；「三」（paulsha-lib）為此升格＝一次動四 repo，違反最小刀 |
| deck | 整包留主 repo | #186 §6：現有 deck 幾乎全是 lifecycle 定義層；persona loader fail-open 已預留缺席路徑；shadow 驗證＝warning 級 lint 非 enforcement，確定性閘門在主 repo 對齊測試 |
| 依賴方向 | 主 repo → cortex（git+SHA pin）；cortex → 無 paulsha 依賴 | 反向（cortex pin 主 repo）使 standalone 安裝不成立；tag pin 可變（hippo 審查教訓） |
| CLI | `psc coordinator` thin shim lazy import cortex CLI | 主 repo 反正保有 cortex 依賴（control.client），shim 免費；hippo 式 tombstone 破壞肌肉記憶且無必要（hippo 無主 repo 對其 CLI 依賴） |
| 對齊測試 | 主 repo 為契約交會點（PHASES 相等／paths 等價／deck↔persona） | 放 cortex 需引入 hippo 測試依賴，破壞零依賴；主 repo 同裝兩者、已有 hippo-consumer 契約測試先例 |
| cutover | 停用舊單元→enable cortex 單元；install 冪等；rollback=revert pin+重 enable；雙 daemon 鎖競爭驗證 | 僅 happy-path E2E 攔不住半套 cutover；`manager.lock` flock 單寫者已存在，明文化 + 測試平移即可，不需新鎖機制 |

## Risks / Trade-offs

- [拆分後緊接 G2 大改] → G2 全程落 cortex repo 內（dispatch 與 gate 同包），邊界不受影響。
- [PHASES 三處漂移（hippo/cortex/文件）] → 主 repo 對齊測試為強制閘；詞彙表語意已凍結（Stage 3）。
- [fresh-install 才現形的打包 bug] → Phase 3 強制 fresh-install E2E（hippo 教訓直接複用）。
- [cortex PR 引用主 repo issue 觸發 R-17] → 一律掛 `policy-exempt:issue-link`。
- [worktree 測試假失敗（test_project_resolver 等）] → 判定回歸前在無變更 worktree 交叉驗證。
- [雙 daemon 併行] → runtime 由 `control_root()/manager.lock` flock 阻斷（不變量隨包平移）；操作面由 cutover 協議阻斷。

## Migration Plan

1. **Phase 0（cortex repo 內）**：骨架——pyproject、tests CI（R-19）、policy engine pin v1.0.12、tag ruleset、R-21 shareable tier。
2. **Phase 1（cortex repo 內）**：三包程式碼與測試平移；剪三線（PHASES 自帶／idle vendor／paths 自帶）；cortex 全測試綠。
3. **Phase 2（本 change 主體）**：主 repo 遷移刀——刪三包、pin cortex SHA、import 改線（bot/cockpit/core）、`psc coordinator` shim、`deploy/planner.py` 清 manager 模板、三個對齊測試、W7 整合測試改線、grep 三包 import 清零（shim 除外）。
4. **Phase 3**：fresh-install E2E + systemd cutover 協議實走（含中斷重試與雙 daemon 鎖競爭）。
   Rollback：revert 主 repo pin commit + 重 enable 舊 manager 單元（Phase 2 merge 前舊碼仍在已安裝環境）。

## Open Questions

- cortex repo 建法沿 hippo「template 全新開始」（無歷史）或 filter-repo 帶歷史——傾向前者（deident 成本低），Phase 0 動工時定案。
- `psc coordinator` shim 於 cortex 未安裝時的錯誤訊息格式（仿 `_MEMORY_MOVED` tombstone 文案給安裝指引）。
