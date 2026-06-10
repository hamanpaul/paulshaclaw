# 短期設計：架構對帳收斂 + WIP 治理

> 日期：2026-06-10 ｜ 來源：brainstorming（整體 Stage 架構全面健檢）
> 配對文件：長期藍圖見 `2026-06-10-plane-restructure-roadmap-design.md`（方案 C）；本文件為方案 B（短期）。

## 1. 背景：健檢發現（證據基礎）

2026-06-10 對 `docs/research/05`（v0.6）與本機實態做全面比對，發現：

### 文件與狀態 drift

1. §5.4 自稱「常駐維護、單一可信來源」，但 v0.6（2026-06-06）之後的工作（stage2 readback、cockpit PR #78/#79、footer PR #76/#77）未回填；Stage 2 標 done 卻有 readback 新 scope 進行中。
2. `openspec/changes/` 有 6 個未歸檔 change（含 2026-04-26 的 stage9），archive 欠帳成常態。

### 規格 vs 部署實態矛盾

3. §7.3 規定三個 always-on「各自 systemd unit、失敗域分離」；實態是單一 `scripts/start.sh` bash supervisor 管 5 個子服務（telegram / monitor / dream / cockpit / cost_refresh），全跑在一個 tmux pane。Operator 運維偏好明示「tmux 死＝全重啟、不做隔離」——矛盾源於規格過度設計，非部署偷懶。
4. Stage 2 驗收要求 `memory.yaml` / `projects.yaml` / `agents.yaml` 三份 config 與 `bootstrap.yaml`；實際只有 `projects.yaml`。dream 規格寫 systemd、寫沿用 obs-auto-moc 三件套，實際均為 start.sh loop。
5. 符合項：memory symlink、secret 目錄 0700、三家 agent hooks、tmux footer（session 層）、dream ledger 活動均正常。

### 可驗證性破口

6. `.venv` 未裝 pytest；以系統 pytest 跑會撞 textual 版本差，`tests/test_stage11_operator_cockpit.py` 2 例失敗（`set_interval` 屬性不存在），其餘 1032 passed。「本機重現 CI 綠燈」目前不成立。

## 2. 目標與範圍

把「文件宣稱」與「系統實態」對齊回單一可信來源，並補上三個已驗證的系統級缺口。**不動 stage 編號、不動現有 runtime 行為**（除新增 liveness 與 config 檔）。產出 `docs/research/05` 的 v0.7 版。

不在範圍：MCP memory pull 介面（維持 Stage 1 已規劃項，另案）、Stage 5 全量 supervisor、任何 plane 重組（見長期藍圖）。

## 3. 工作項（七項）

### ① 驗收表對帳

§5.4 / §8 逐條對實態標記三態：

- `符合`：實態與規格一致
- `規格降級`：改文件遷就現實（附理由）
- `實作補齊`：排程改系統（列入 backlog 並指定落點）

已知必處理條目：Stage 2 三份 config 缺項、systemd 條目、obs-auto-moc 三件套條目、readback 新 scope 未入表。

### ② ADR：always-on 部署模型拍板

寫一份決策記錄，落點 `openspec/specs/conventions/adr-001-always-on-deployment.md`，內容：

- **決定**：§7.3「三 always-on 各自 systemd unit、失敗域分離」降級為「start.sh 單 supervisor + tmux 死＝全重啟」。
- **理由**：與 Operator 運維偏好一致（單人系統，接受全重啟成本；不做多實例隔離）。
- **放棄了什麼**：部分失敗隔離（單一子服務 crash 可能連帶其餘）。
- **重審時點**：長期 plane 重組（方案 C）啟動時。
- Stage 5 supervisor 規格隨之縮小為「最小觀測」（見⑤）。

### ③ 歸檔欠帳

6 個未歸檔 openspec changes 逐一檢查：已完成的走 archive 流程；未完成的（如 `stage2-memory-readback`）標明 in-flight 留下。完成後 `openspec/changes/` 只剩 in-flight。

### ④ dev env 可驗證性

- `pyproject.toml` 加 `[project.optional-dependencies] test` extra（pytest、pin textual 等與 CI 一致的版本）。
- `.venv` 補裝 test extra。
- 新增 `scripts/test.sh` 作為唯一測試入口（處理 PYTHONPATH 與測試路徑集合）。
- 驗收條件＝本機 `scripts/test.sh` 跑出與 CI 相同的綠燈；先前 2 例 stage11 失敗須在此項中查明（版本差 vs 真回歸）並處置。

### ⑤ 最小觀測（liveness + psc status）

- start.sh 的 5 個子服務各自週期 touch `~/.agents/run/<service>.alive`。
- 新增 `psc status` 子命令，讀取並列出「誰活著、上次心跳」。
- 明確不做：supervisor 自動重啟、dashboard、metric 累積。

### ⑥ Stage 2 config 補齊

落地三份最小 schema，先求「檔案存在、schema 有驗證、現行程式讀得到」，不擴功能：

| 檔案 | 最小內容 |
|---|---|
| `memory.yaml` | 根路徑、目錄角色宣告（inbox / work-centric / knowledge / runtime） |
| `agents.yaml` | 三家 agent（claude / codex / copilot）的 hook 安裝狀態與 session 來源 |
| `bootstrap.yaml` | 啟動必讀清單：user overlay、`projects.yaml` 指標、current slice 指標 |

### ⑦ WIP 治理規則

寫進 AGENTS.md / CLAUDE.md policy 段：

- (a) 同時 in-progress 的 stage 上限 **3**，其餘標 `frozen`。
- (b) 收斂順序明文化（預設：Stage 2 readback 收尾 → Stage 1 MCP → Stage 3 pipeline；調整須留紀錄）。
- (c) PR 合併前 checklist 加一條「涉及 stage 進度者須回填 §5.4」。

## 4. 驗收標準

- [ ] `docs/research/05` v0.7 發布；§5.4 每條有三態標記，無「宣稱 done 但驗收缺項」
- [ ] ADR 檔存在於 `openspec/specs/conventions/adr-001-always-on-deployment.md`
- [ ] `openspec/changes/` 只剩 in-flight 的 change
- [ ] `scripts/test.sh` 本機全綠（含 2 例 stage11 失敗的處置結論）
- [ ] `psc status` 列出 5 個子服務心跳；殺掉 dream loop 後 status 能反映
- [ ] 三份 config 存在且被程式實際載入（各至少一個測試）
- [ ] AGENTS.md / CLAUDE.md 含 WIP 治理三條規則

## 5. 測試策略

- ④ 以「本機與 CI 同綠」為整體迴歸閘門。
- ⑤ liveness：單元測試覆蓋 alive 檔寫入與過期判定；手動驗證殺 dream loop 後 `psc status` 反映。
- ⑥ config：每份 schema 一個載入測試 + 一個缺檔 fallback 測試（符合 Stage 獨立性：缺 config 不得讓上游 crash）。
- ①②③⑦ 為文件／流程變更，以 `openspec validate` 與 policy check CI 守門。
