# 長期藍圖：四 Plane 架構重組（roadmap）

> 日期：2026-06-10 ｜ 來源：brainstorming（整體 Stage 架構全面健檢）
> 配對文件：短期方案見 `2026-06-10-architecture-reconciliation-design.md`（方案 B）；本文件為方案 C（長期）。

## 1. 定位與啟動條件

這是一份**藍圖（roadmap），不是立即動工的工程**。

**啟動 gate**：短期方案 B 全部驗收通過、且 §5.4 對帳後「規格降級／實作補齊」兩類欠帳清零。在那之前本文件只演進、不執行。

理由：重組期間最大的風險是「兩套真相並存」，必須先有對平的帳本才能搬家。

## 2. 四個 Plane 與 Stage 對映

| Plane | 收編的 Stage | 一句話職責 |
|---|---|---|
| **runtime** | 1（daemon / bot / TUI）、3（lifecycle）、4（persona）、11（cockpit） | Operator 下指令到 agent 執行的整條路 |
| **memory** | 2（記憶中樞全部 T1–T9 + readback） | 記憶的進、整理、出 |
| **governance** | 6（security / approval）、§5.6 workflow 選擇器、R-規則／policy check | 什麼可以做、誰可以做、怎麼選流程 |
| **ops** | 5（觀測）、7（部署）、8（成本）、9（project monitor） | 裝得起來、看得見、付得起 |

特別處置：

- **Stage 0**：已完成，成為歷史，不歸入任何 plane。
- **Stage 10（protocol）**：取消獨立編號，併入 runtime plane 的 interface 層（MCP 屬此）。
- **§5.6 workflow 選擇器**：從「未動工的最高槓桿」升為 governance plane 的第一公民——這是重組真正的增量價值，不只是改名。

## 3. 遷移策略（三階段，代號不動原則）

### 階段一（文件層）

- 總覽文件改以 plane 為章節骨架，stage 編號降為 plane 內小節（保留 `Stage N` 字樣作為 legacy 索引）。
- `openspec/specs/` 新增 `<plane>/` 目錄，舊 `stageN/` 留 stub 指向新位置。
- **程式碼、測試檔名、commit 慣例完全不動。**

### 階段二（增量歸類）

- 新工作一律以 plane 命名（branch、change、design doc）；舊 stage 名只在維護既有模組時沿用。
- §5.4 進度檢查表改為 plane 視角。
- WIP 上限從「3 個 stage」改為「每 plane 至多 1 條 in-flight」。
- 明定「新功能不等重組」：plane 只是歸類標籤，不是 blocker。

### 階段三（選擇性收斂）

- 某 plane 內所有舊 stage 都到達穩定態時，才把該 plane 的測試與模組目錄重整（如 `tests/test_runtime_*`）。
- 永遠只做「已穩定的那個 plane」，不做全域 big-bang rename。

## 4. 風險與緩解

| 風險 | 緩解 |
|---|---|
| 兩套真相並存 | §1 的啟動 gate ＋ 階段一 stub 指向；任一時刻只有一份 canonical（plane 版），stage 版只是索引 |
| 記憶與外部引用失效（auto-memory、openspec archive、commit 歷史都用 stage 語彙） | 階段一產出 stage↔plane 對照表 `openspec/specs/conventions/plane-map.md`，所有舊引用查表可達 |
| 重組變成拖延實作的藉口 | 階段二明定「新功能不等重組」 |
| YAGNI 殘留疑慮 | 若 B 完成後發現 stage 視角夠用，C 可在階段一之後永久停留（只當索引重排），不強制走到階段三 |

## 5. 驗收標準（每階段）

- **階段一**：v1.0 總覽以 plane 為骨架發布；`plane-map.md` 對照表存在；`openspec validate` 全綠。
- **階段二**：連續 3 個新 change 以 plane 命名歸檔；§5.4 plane 視角運作一個月無回退。
- **階段三**：至少一個 plane 完成目錄收斂且測試全綠；其餘 plane 可無限期維持階段二。

## 6. 關鍵設計判斷（摘要）

1. **啟動 gate 綁在 B 完成之後**——先對帳、後搬家。
2. **代號不動原則**——文件先行、程式碼最後且選擇性。
3. **Stage 10 併入 runtime、選擇器升為 governance 第一公民**——重組的增量價值所在。
