# Stage 2 Memory Importer MVP Design

## Context

Stage 2 (`paulsha-memory`) 已有 scope、routing、janitor 規格與 sync-back gate scaffold（archive 2026-04-20），但 runtime 完全未落地：

- `paulshaclaw/memory/` 只有 `routing.md`、`paulshaclaw/janitor/` 只有 `service.md`，無 Python module。
- `~/.agents/` 目前無 `memory/` 子樹；canonical memory 仍附著於 `~/notes/`（Obsidian vault），由 `obs-auto-moc` 直接讀寫，正是 research 02 第 69 行所指「memory root 仍附著在 vault」的限制。
- 三家 agent CLI（Claude Code / Codex / Copilot CLI）都已有 first-class hook 機制，但本機 hook config 全部空白。

研究文件 `docs/research/02.obs-auto-moc-memory-dream-mode-24-7-service-notes-.md` 將 Stage 2 拆成 9 個獨立子系統（記憶基底、importer/classifier、atomizer、ledger、dream service、wake-up、retrieval、治理層、sync-back gate）。本 spec **只處理 #1 + #2**：記憶基底 + Importer MVP。dream service、atomizer、retrieval、wake-up、ledger 細節、sync-back gate 留給後續 sub-spec。

## Confirmed Scope

- 在 `~/.agents/memory/` 建立四層樹（inbox / work-centric / knowledge / runtime / archive），canonical 記憶從此處落地，**完全不混入 `~/notes/`**；obs-auto-moc 對 vault 的既有行為不在本次 scope 內。
- 三家 CLI 各掛 SessionEnd-ish hook，把 session 結尾資訊正規化後寫入 `~/.agents/memory/inbox/sessions/`。
- 共用 importer Python module 落於 `paulshaclaw/memory/importer/`，含三家 adapter 與 rule-based classifier。
- 在 `obs-auto-moc` 內新增 file-watcher daemon 作為 safety net，監看三家 session 目錄，發現新 session 時呼叫同一個 importer。Hook 與 watcher 透過冪等鍵 `<tool>:<session-id>` 保證不重覆寫入。
- 用既有的歷史 session 檔（`~/.claude/projects/`、`~/.codex/sessions/`、`~/.copilot/history-session-state/`）作為開發語料，避免 importer 開發過程要不停跑活 session。
- frontmatter contract 完全沿用 research 02 提案，不自創欄位（與 Stage 3 對齊，per workstream todo）。

## Non-Goals

- 不做 atomize、wiki/knowledge 寫入、ledger 更新邏輯（Stage 2 sub-spec #3, #4）。
- 不啟動 dream service / janitor 24x7 排程（sub-spec #5）。
- 不做 wake-up surface、retrieval（lexical/relation/embedding）（sub-spec #6, #7）。
- 不做 secret redaction / classification / external publish guard（sub-spec #8，且 `~/.agents/` local-only）。
- 不做 sync-back 到 `custom-skills/paulsha-memory` 的執行邏輯（sub-spec #9 只到 scaffold）。
- 不修改 `~/notes/` vault 任何檔案；不變更 obs-auto-moc 對 vault 的既有讀寫行為。
- 不訂閱 SessionStart / UserPromptSubmit / PreToolUse / PostToolUse / PreCompact / Notification 等其他 hook event。
- 不引入 vector DB / embedding；frontmatter 與目錄即為唯一索引。

## Goals

- 三家 CLI 任何一個 session 結束（含 `Stop`/`SubagentStop`/`sessionEnd` 對應事件）後 30 秒內，`~/.agents/memory/inbox/sessions/<tool>/<YYYY-MM-DD>/<session-id>.md` 出現一份合法 frontmatter 的紀錄。
- 同一 session 不論被 hook 或 watcher 撿到（或兩者同時），最終只產出一份 inbox 檔；後到者依完整度比較結果為 `updated` / `stale-skip` / `hash-duplicate`，**inbox 路徑唯一**。
- classifier 能依規則將 inbox 檔分流到 `sessions / plans / research / reports` 四個 bucket。
- `paulshaclaw/memory/` lint 工具可校驗 inbox 全部檔案的 frontmatter 合法。
- 整套程式碼可用歷史 corpus 重放，不依賴活 session 才能開發/測試。

## Architecture

### High-level data flow

```text
                    ┌─────────────────────────────────────┐
  Claude Code  ───► │ ~/.claude/settings.json hooks.SessionEnd │
                    └─────────────────────────────────────┘ ──┐
                                                              │
                    ┌─────────────────────────────────────┐   │
  Codex CLI    ───► │ ~/.codex/hooks.json Stop+SubagentStop│   │
                    └─────────────────────────────────────┘ ──┤
                                                              │
                    ┌─────────────────────────────────────┐   │
  Copilot CLI  ───► │ ~/.copilot/hooks/paulsha-memory.json│   │
                    │      sessionEnd                     │   │
                    └─────────────────────────────────────┘ ──┤
                                                              ▼
                                            ┌──────────────────────────┐
  (safety net)                              │ paulshaclaw.memory       │
                                            │  .importer.cli           │
  obs-auto-moc watcher ───────────────────► │                          │
   inotify on:                              │  adapters → normalize →  │
    ~/.claude/projects/**                   │  frontmatter + body →    │
    ~/.codex/sessions/**                    │  classifier → bucket →   │
    ~/.copilot/history-session-state/*      │  flock + idempotent write│
                                            └────────────┬─────────────┘
                                                         │
                                            ┌────────────▼─────────────┐
                                            │  ~/.agents/memory/inbox/ │
                                            │   sessions/<tool>/...    │
                                            │   plans/<tool>/...       │
                                            │   research/<tool>/...    │
                                            │   reports/<tool>/...     │
                                            └──────────────────────────┘
```

### `~/.agents/memory` 四層樹（本 spec 落地範圍）

```text
~/.agents/
├── config/
│   ├── memory.yaml              # 此次只放 inbox 路徑、保留期、idempotent 規則
│   └── projects.yaml            # 本 spec 提供初始格式與 obs-auto-moc / paulshaclaw 兩筆
├── memory/
│   ├── inbox/
│   │   ├── sessions/<tool>/<YYYY-MM-DD>/<session-id>.md
│   │   ├── plans/<tool>/<YYYY-MM-DD>/<session-id>.md
│   │   ├── research/<tool>/<YYYY-MM-DD>/<session-id>.md
│   │   └── reports/<tool>/<YYYY-MM-DD>/<session-id>.md
│   ├── work-centric/            # 本 spec 只建空樹，內容由 sub-spec #3 atomizer 寫
│   │   └── common-sense/        # ditto
│   ├── knowledge/               # 本 spec 只建空樹
│   ├── runtime/
│   │   ├── queue/<tool>__<session-id>.json          # hook / watcher 寫的 raw payload
│   │   ├── queue/_failed/<tool>__<session-id>.json  # adapter 解析失敗的 payload
│   │   ├── locks/<tool>__<session-id>.lock
│   │   ├── ledger/import.jsonl  # 每次 importer 執行的 idempotent ledger（append-only）
│   │   └── indexes/             # 本 spec 不寫，留給 sub-spec #7
│   ├── log/
│   │   ├── hooks.log            # hook script 自身例外
│   │   └── importer.log         # importer pipeline 主日誌
│   ├── hooks/
│   │   ├── claude_session_end.py
│   │   ├── codex_session_end.py
│   │   ├── copilot_session_end.py
│   │   ├── install.sh
│   │   └── uninstall.sh
│   └── archive/
│       └── queue/<YYYY-MM>/<tool>__<session-id>.json   # 寫完 inbox 後搬入
```

work-centric / knowledge / indexes 在本 spec **只建空目錄與 `.gitkeep`**，內容由後續 sub-spec 處理；importer 在本 spec 唯一會寫入的非 inbox 子樹是 `archive/queue/`（已成功搬入 inbox 的 raw payload 歸檔位置）。

### Hook 層

#### Claude Code

- 位置：`~/.claude/settings.json`，在 `hooks` 鍵下加 `SessionEnd`（與 `Stop` 區分，`Stop` 是 turn-end，每輪都會打到，不適合作為 commit 觸發點）。
- Claude hook JSON 採 `matcher` + `hooks[]` 兩層結構，命令逾時欄位為 `timeout`（秒），不是 `timeout_ms`。
- 範本：
  ```json
  {
    "hooks": {
      "SessionEnd": [
        {
          "matcher": "",
          "hooks": [
            {
              "type": "command",
              "command": "~/.agents/memory/hooks/.venv/bin/python ~/.agents/memory/hooks/claude_session_end.py",
              "timeout": 10
            }
          ]
        }
      ]
    }
  }
  ```
- payload：stdin JSON，至少含 `session_id`、`transcript_path`、`cwd`（依 Claude hooks 文件）。adapter 若任一欄缺失，以「best-effort + 空集合」處理，不噴錯。

#### Codex CLI

- 位置：`~/.codex/hooks.json`（不放 inline `[hooks]` 於 `config.toml`，避免兩處混淆）。
- **語意陷阱**：Codex 的 `Stop` 是 turn-scope，`SubagentStop` 是 subagent-scope，**兩者都會在 session 進行中多次觸發**。Codex 沒有原生「session 完結」事件。
- 本 spec 採「**hook 為遞增 nudge，watcher 為 commit 觸發**」分工：
  - Codex hook 每次觸發都把當下 session 的最新 snapshot 寫進 `runtime/queue/<key>.json`（覆寫，atomic rename）。
  - **importer 從 queue 讀進來時，跑「冪等性與更新規則」（content_hash + completeness 嚴格 tuple 比較）**，得 `hash-duplicate` / `updated` / `stale-skip` 三狀態之一，inbox 路徑唯一。
  - 真正的 session 收尾由 watcher 的 debounce（session 檔靜止 ≥ 5 秒）判定，那是最完整的版本。
- **必經 trust 流程**：第一次部署完後需在 Codex CLI 內執行 `/hooks` 審核並信任；hook script 修改後 hash 變動會自動失效，提示重審。本流程列入 onboarding 步驟。
- 範本：
  ```json
  {
    "hooks": {
      "Stop": [
        {
          "matcher": ".*",
          "hooks": [{
            "type": "command",
            "command": "~/.agents/memory/hooks/.venv/bin/python ~/.agents/memory/hooks/codex_session_end.py",
            "statusMessage": "paulsha-memory: capturing turn snapshot"
          }]
        }
      ],
      "SubagentStop": [
        {
          "matcher": ".*",
          "hooks": [{
            "type": "command",
            "command": "~/.agents/memory/hooks/.venv/bin/python ~/.agents/memory/hooks/codex_session_end.py --subagent",
            "statusMessage": "paulsha-memory: capturing subagent snapshot"
          }]
        }
      ]
    }
  }
  ```

#### Copilot CLI

- 位置：`~/.copilot/hooks/paulsha-memory.json`（使用者層；非 repo 層）。
- 訂閱 `sessionEnd`（quit / `/exit` 時觸發，每個 session 唯一一次）。`agentStop` 在每次 response 後都觸發，本 MVP 不訂閱。
- 範本同時提供 `bash` 與 `powershell` 兩 key；本機 Linux/WSL 環境下 powershell 用 stub（直接 echo「Windows path not supported in MVP」）。
- 範本：
  ```json
  {
    "version": 1,
    "hooks": {
      "sessionEnd": [
        {
          "type": "command",
          "bash": "~/.agents/memory/hooks/.venv/bin/python ~/.agents/memory/hooks/copilot_session_end.py",
          "powershell": "Write-Host 'paulsha-memory: powershell path not supported in MVP'",
          "timeoutSec": 10
        }
      ]
    }
  }
  ```

#### Hook script 共同行為

`~/.agents/memory/hooks/<tool>_session_end.py` 三個檔皆做：
1. 讀 stdin JSON / env 取得 session-id、session-path、tool name、capture_scope（`turn` / `subagent` / `session_end` / `watcher_final`）。
2. **不解析、不做分類、不寫 inbox**；只把 raw payload + meta 寫到 `~/.agents/memory/runtime/queue/<tool>__<session-id>.json`（atomic write，先寫 `.tmp` 再 rename）。
3. 呼叫 importer entry：`exec ~/.agents/memory/hooks/.venv/bin/python -m paulshaclaw.memory.importer.cli ingest --queue-item <path> &`（fire-and-forget，detach）。
4. Hook script timeout 設 10s；超時不阻塞 CLI。
5. 任何例外都不能 raise 出 hook script——一律寫 `~/.agents/memory/log/hooks.log` 並 exit 0。

**Python runtime bootstrap（消除 PYTHONPATH 隱性耦合）**：
- `install.sh` 在 `~/.agents/memory/hooks/.venv` 建一個 venv，並以**絕對路徑**執行 `.venv/bin/pip install -e <repo>/paulshaclaw` 把 `paulshaclaw.memory.importer` 套件安裝進去。`<repo>` 路徑由 `install.sh` 接收 `--repo <path>` 參數，預設為 `install.sh` 自身所在 repo（`git rev-parse --show-toplevel`）。
- 升級流程：使用者 `git pull` 後跑 `~/.agents/memory/hooks/install.sh --upgrade`，內部執行 `.venv/bin/pip install -e <repo>/paulshaclaw`（與初次安裝相同指令，路徑由 install.sh 記住，不依賴使用者當前 cwd）。
- 若 venv 缺失，hook script 偵測到後 fallback 至「只寫 queue payload、不呼叫 importer」，並寫 hooks.log WARN；watcher 後續會補抓。

這樣的設計讓 hook script 本身極輕薄，所有解析邏輯集中在 `paulshaclaw.memory.importer.cli`，並讓 watcher 走同一個 entry。

### Importer 主邏輯（`paulshaclaw/memory/importer/`）

```text
paulshaclaw/memory/
├── __init__.py
├── routing.md                  # (existing) 文件規範
├── config.py                   # 讀 ~/.agents/config/memory.yaml + projects.yaml
├── frontmatter.py              # frontmatter schema + lint
├── locks.py                    # flock advisory lock
├── importer/
│   ├── __init__.py
│   ├── cli.py                  # `python -m paulshaclaw.memory.importer.cli`
│   ├── pipeline.py             # ingest() / classify() / write()
│   ├── classifier.py           # rule-based 四 bucket 判定
│   ├── ledger.py               # import.jsonl append + idempotency check
│   └── adapters/
│       ├── __init__.py
│       ├── base.py             # Adapter 介面 + 共同正規化
│       ├── claude.py
│       ├── codex.py
│       └── copilot.py
├── lint/
│   ├── __init__.py
│   └── frontmatter_lint.py     # 給 CI 用
└── tests/
    ├── stage2_integration_check.sh   # (existing)
    ├── fixtures/
    │   ├── claude/<sid>/...           # 從 ~/.claude/projects 複製去識別化的 sample
    │   ├── codex/<sid>/...
    │   └── copilot/<sid>/...
    ├── test_adapters.py
    ├── test_classifier.py
    ├── test_idempotency.py
    └── test_e2e.py
```

#### Adapter 介面（`adapters/base.py`）

```python
class SessionAdapter(Protocol):
    tool: str  # "claude" | "codex" | "copilot"

    def can_handle(self, payload: dict) -> bool: ...

    def extract(self, payload: dict) -> NormalizedSession: ...

class NormalizedSession(TypedDict):
    session_id: str
    tool: str
    started_at: str | None       # ISO8601；None 表示來源沒給
    ended_at: str | None          # 同上；None 代表此次來源為 mid-session snapshot
    cwd: str | None
    repo: str | None              # git rev-parse --show-toplevel 推得
    commit: str | None            # git rev-parse HEAD 推得
    turn_count: int               # 必填，用於冪等性更新比較；無法計時可填 1
    user_prompts: list[str]       # best-effort；無法解析就空 list
    assistant_summary: str        # adapter 自摘要，限 2000 字以內；空字串 = 來源無內容
    touched_files: list[str]      # best-effort；無法解析就空 list
    referenced_artifacts: list[str]   # plan.md / spec.md / research/*.md
    raw_payload_pointer: str      # 指向 runtime/queue/<file>，importer 寫完 inbox 才搬到 archive
```

#### 各 CLI 的最小欄位契約（per-tool fixture contract）

| 欄位 | Claude (`SessionEnd` stdin) | Codex (`Stop` / `SubagentStop` stdin) | Copilot (`sessionEnd` stdin) |
|---|---|---|---|
| **官方 payload 主鍵命名** | snake_case：`session_id` / `transcript_path` / `cwd` | snake_case：`session_id` / `cwd`（無 transcript path 保證） | **camelCase**：`sessionId` / `timestamp` / `cwd` / `reason` |
| `session_id`（標準化後） | 直接取 `session_id` | 直接取 `session_id` | 取 `sessionId`，adapter 內 rename |
| `transcript_path` 取得 | stdin 必有，hook 直接讀 | stdin 不保證，fallback 掃 `~/.codex/sessions/<sid>/*.jsonl` 取最新 | stdin 沒有，hook 直接讀 `~/.copilot/history-session-state/session_<sid>_*.json` |
| `turn_count` | hook 自己數 transcript jsonl 行數 | hook 自己數 jsonl 行數 | hook 自己讀 session-state JSON 的 turn array |
| `capture_scope`（hook 自填） | `session_end`（SessionEnd 為唯一觸發） | `turn`（Stop）或 `subagent`（SubagentStop） | `session_end` |
| `ended_at` | hook 觸發時打 timestamp，**等於 session 真結束** | adapter 收到時設為 `None`（turn-scope 不代表 session 結束） | 取 stdin `timestamp` 或 hook 自打 |
| `user_prompts` / `touched_files` | best-effort 從 transcript 抽 | best-effort | best-effort，從 session-state JSON 抽 |
| `content_hash` | hook 寫 queue 時計算：`sha256(canonical_json(payload_subset))`，`payload_subset` = `(session_id, capture_scope, turn_count, ended_at, sorted(touched_files), len(user_prompts))`。**`capture_scope` 必入 hash**，確保同內容不同來源（如 turn snapshot vs watcher_final）為不同 hash，可走 completeness 比較而非短路成 `hash-duplicate`。 | 同 | 同 |

adapter 對任何缺欄一律降級為空集合 / `None`，不 raise；importer 寫 inbox 時 frontmatter 仍照欄位列，空值留空字串或空陣列。

**Fixture 收集規則**：A2 動工前先以本機現有 session 樣本各擷取 ≥ 3 個案例，存入 `paulshaclaw/memory/tests/fixtures/<tool>/<sid>/payload.json`（去識別化、移除絕對路徑外的個資），作為 adapter 黃金樣本。任何 adapter 改動需通過這些 fixture 的 snapshot test。Fixture 必須包含上表所有「**官方 payload 主鍵命名**」欄位的 raw 形態，adapter 負責 rename / 補欄位。

#### Frontmatter contract

完全沿用 research 02 line 220-234：

```yaml
memory_layer: inbox
project: paulshaclaw            # 從 cwd / repo / projects.yaml 解出；解不出時 = "_unknown"
source_agent: copilot-cli       # claude-code | codex | copilot-cli
source_session: 5089218f-cee0-400c-9ae1-1f7f05946fb3
source_artifact: session        # session 為 MVP 預設；classifier 可改成 plan / research / report
captured_at: 2026-05-24T20:43:10+08:00
provenance:
  repo: hamanpaul/paulshaclaw
  commit: e300b08
  path: /home/paul_chen/prj_pri/paulshaclaw
idempotency_key: copilot-cli:5089218f-...     # `<source_agent>:<source_session>`
```

> Stage 3 對齊：本 spec 不增任何 Stage 3 未提及的 frontmatter 欄位。`memory_layer` / `project` / `source_*` / `captured_at` / `provenance` 均為 research 02 / Stage 3 已既有命名。

#### 冪等性與更新規則（取代「skip-if-exists」）

- **冪等鍵**：`idempotency_key = "<source_agent>:<source_session>"`，全 session 生命週期內穩定。
- **每筆 queue payload 內含**：
  - `content_hash`：`sha256` over canonical-json 子集（見上節「per-tool fixture contract」最後一列）。
  - `capture_scope` ∈ {`turn`, `subagent`, `session_end`, `watcher_final`}。
  - `completeness`：固定四元組 `(scope_rank, turn_count, len(touched_files), len(user_prompts))`，其中 `scope_rank` = `{turn:0, subagent:0, session_end:1, watcher_final:2}`。
- 寫 inbox 前：`flock` 取 `~/.agents/memory/runtime/locks/<idempotency_key>.lock`，無法取得即 noop（不算 error，重試 hook 會再來）。
- 取得鎖後讀 `runtime/ledger/import.jsonl` 中該 key 的最後一筆 `recorded`：
  1. **若 incoming `content_hash` == recorded `content_hash`** → noop，append `status: "hash-duplicate"`。
  2. **否則做 strict-tuple 比較**：以 Python 風格 `tuple > tuple`（左到右，element-wise，遇較大就 True，相等則往下；全部相等不算大）。
     - `incoming.completeness > recorded.completeness` → 覆寫 inbox，append `status: "updated"`（記錄 `from_completeness` / `to_completeness` / `incoming_hash`）。
     - 否則 → noop，append `status: "stale-skip"`。
  3. 該 key 首次寫入 → append `status: "written"`。
- 設計意義：
  - Codex 每 turn 的 hook snapshot（`scope_rank=0`）會持續更新 inbox 直到 `turn_count` 不再成長；當 watcher 抓到靜止 session 並送入 `scope_rank=2` 時，必然勝出成為終版。
  - Claude `SessionEnd` 觸發送出 `scope_rank=1`，足以蓋過先前任何 `turn` snapshot。
  - 同內容重觸發（hash 相同）→ `hash-duplicate`，零成本。
- 為避免 ledger 不斷膨脹：本 spec 不做輪替，留給 sub-spec #5 dream service 處理 garbage。

#### Classifier（rule-based）

四 bucket 路由規則（依優先序，命中即停）：

| Bucket | 觸發條件（OR） |
|---|---|
| `plans` | (a) `touched_files` 含 `plan.md` / `*-plan.md` / `docs/superpowers/plans/*.md`；(b) `user_prompts` 出現 `/plan` 或「實作計畫」「implementation plan」字眼 |
| `research` | (a) `touched_files` 含 `docs/research/*.md`；(b) `user_prompts` 出現 `/research` 或「研究」「survey」「explore」連續字眼且該 session 未進入實作（touched_files 中無 `*.py` / `*.ts` / `*.c` 等程式碼） |
| `reports` | (a) session 中有 commit / PR ref（adapter 可偵測 `referenced_artifacts`）；(b) `user_prompts` 出現「report」「summary」「postmortem」 |
| `sessions` | 兜底 |

- classifier 寫死於 `classifier.py`，**不做 ML、不做 embedding**。
- 命中後 `source_artifact` frontmatter 改寫成對應 `plan` / `research` / `report` / `session`。
- 規則命中率不要求 > 90%；只要求人工 spot check 100 筆 ≥ 70%，未來 sub-spec 可調規則。

#### 寫檔流程（pipeline.py 順序）

1. 讀 `runtime/queue/<key>.json`（hook 寫的 raw payload），或從 watcher 直接拿 path。
2. 依 `tool` 派去對應 adapter → `NormalizedSession`。
3. 跑 classifier → bucket。
4. 組 frontmatter + body（body = `## Summary` + `## Prompts` + `## Touched files` + `## Referenced artifacts` 四節）。
5. 取 flock → 查 ledger 冪等 → 若 OK 則 atomic write 至 `inbox/<bucket>/<tool>/<YYYY-MM-DD>/<session-id>.md`（`.tmp` + rename）。
6. 寫 ledger entry。
7. 將 raw queue file 搬到 `~/.agents/memory/archive/queue/<YYYY-MM>/<key>.json`。

### Safety net watcher（在 obs-auto-moc 內）

- 路徑：`obs_auto_moc/watchers/agents_inbox_watcher.py`（新檔），與 systemd unit template `obs-auto-moc/systemd/agents-inbox-watcher.service` 一同提交。
- 行為：
  - 啟動時掃一次三個目錄，把存在但 ledger 沒記錄的 session 都丟去 importer。
  - 之後用 `inotify_simple`（純標準庫依賴限制可放寬，本機已可裝）監看：
    - `~/.claude/projects/` — `IN_CLOSE_WRITE | IN_MOVED_TO`
    - `~/.codex/sessions/` 與 `~/.codex/history.jsonl`
    - `~/.copilot/history-session-state/` — `IN_CLOSE_WRITE`
  - 偵測到 session 檔靜止超過 5 秒（debounce）後，組成同樣的 queue payload，呼叫 `python -m paulshaclaw.memory.importer.cli ingest --watcher --path <p>`。
- 與 hook 的關係：兩者寫入同一個冪等鍵但 `capture_scope` 不同；watcher 用 `watcher_final`（`scope_rank=2`）必勝出，將 inbox 升級為最完整版本，ledger 紀錄為 `updated`。即便 hook 端先以 `session_end` 寫出與 watcher 結果欄位等價的 payload，因 `capture_scope` 不同 → `content_hash` 不同 → 走 completeness 比較 → watcher_final 較高 → ledger 仍記 `updated`。watcher 對 obs-auto-moc 來說是新增能力，**不修改現有 vault 流程**。
- 此 watcher 在 obs-auto-moc 倉庫內以新 sub-feature 提交；本 paulshaclaw spec 只規範介面與檔案路徑，實作 PR 在 obs-auto-moc 倉處理。

### Project identity

`~/.agents/config/projects.yaml` 初始版：

```yaml
version: 1
projects:
  paulshaclaw:
    slug: paulshaclaw
    roots:
      - /home/paul_chen/prj_pri/paulshaclaw
    remotes:
      - github.com/hamanpaul/paulshaclaw
    aliases: [paulsha, paulshia, psc]
  obs-auto-moc:
    slug: obs-auto-moc
    roots:
      - /home/paul_chen/prj_pri/custom-claw-tools/obs-auto-moc
    remotes:
      - github.com/hamanpaul/obs-auto-moc
    aliases: [auto-moc, obs-moc]
```

resolver 規則（`config.py::resolve_project`），順序執行，先命中先回傳：
1. 取 `cwd`，與所有 project 的 `roots` 比對，採 **longest-prefix wins**（monorepo / 子 worktree 場景下子目錄優先於上層 root）。
2. 否則 `git -C <cwd> rev-parse --show-toplevel` 取 repo root，與 `roots` 做 longest-prefix。
3. 否則 `git -C <cwd> remote get-url origin` 與 `remotes` 字串比對（normalize 掉 `.git` 後綴與 `git@` / `https://` 前綴）。
4. 都不中 → `project: _unknown`，importer 仍寫 inbox（不阻塞）。
5. 多筆 alias 命中：以 `projects` 順序定義最早者為主，警告寫 importer.log。

### MVP done definition（A 切片 6 個 sub-slice）

| sub-slice | Done 條件 |
|---|---|
| **A0 Hook smoke** | 三家 CLI 各跑一次 hello-world session，`~/.agents/memory/runtime/queue/<tool>__<sid>.json` 出現非空 payload；hooks.log 無 ERROR |
| **A1 樹 + frontmatter** | `~/.agents/memory/` 四層樹建妥；`frontmatter_lint.py` 對一份手寫 fixture 通過 |
| **A2 Importer** | 將歷史 corpus（≥ 20 個 Claude session、≥ 20 個 Codex session、≥ 20 個 Copilot session）跑過 importer，輸出 inbox 檔 frontmatter 全部 lint pass；冪等性測試（同一 session 跑兩次只產一檔）通過 |
| **A3 Classifier** | 同樣歷史 corpus 跑分類，人工 spot check 30 筆，分類正確 ≥ 70% |
| **A4 projects.yaml + watcher** | watcher daemon 可啟動，啟動掃描將遺漏 session 補進 inbox；新建一個假 session 檔放入 `~/.claude/projects/test-sid/` 5 秒後 inbox 出現對應 markdown |
| **A5 E2E live** | Claude / Codex / Copilot 各跑一個真實短 session，hook 路徑與 watcher 路徑同時觸發但 inbox 各只一份；ledger 顯示後到者 `stale-skip` 或 `updated`（取決於完整度比較） |

## Data Layout Summary

| 路徑 | 內容 | 寫者 | 讀者 |
|---|---|---|---|
| `~/.agents/config/memory.yaml` | inbox 路徑、保留期 | 人工 | importer / watcher |
| `~/.agents/config/projects.yaml` | project identity | 人工 | importer |
| `~/.agents/memory/inbox/<bucket>/<tool>/<date>/<sid>.md` | 標準化 session 紀錄 | importer | 未來 atomizer / RAG（sub-spec） |
| `~/.agents/memory/runtime/queue/<key>.json` | raw payload 暫存 | hook / watcher | importer |
| `~/.agents/memory/runtime/queue/_failed/<key>.json` | adapter 解析失敗的 payload | importer | 人工除錯 |
| `~/.agents/memory/runtime/locks/<key>.lock` | flock | importer | importer |
| `~/.agents/memory/runtime/ledger/import.jsonl` | 冪等 ledger | importer | importer / 人工除錯 |
| `~/.agents/memory/archive/queue/<YYYY-MM>/<key>.json` | 寫完搬走的 payload | importer | 人工除錯 |
| `~/.agents/memory/log/hooks.log` | hook 例外日誌 | hook | 人工除錯 |
| `~/.agents/memory/log/importer.log` | importer 主日誌 | importer | 人工除錯 |
| `~/.agents/memory/hooks/<tool>_session_end.py` | hook entry scripts | 人工部署 | hook runtime |

## Testing

- `paulshaclaw/memory/tests/test_adapters.py`：對 fixtures 跑 adapter → `NormalizedSession` 結構檢查。
- `paulshaclaw/memory/tests/test_classifier.py`：人工標註 fixture 對應 bucket，跑 classifier 確認。
- `paulshaclaw/memory/tests/test_idempotency.py`：同一 session 多次注入不同完整度的 payload，斷言低完整度為 `stale-skip`、高完整度為 `updated`，最終 inbox 反映最高完整度版本。
- `paulshaclaw/memory/tests/test_e2e.py`：以 fake hook payload 走完整 pipeline，斷言 inbox 檔內容、ledger、archive 三處皆正確。
- `paulshaclaw/memory/tests/stage2_integration_check.sh` 更新：除原有 guardrail，新增「執行 importer dry-run on fixtures」。
- 不引入 live network；fixture 全部 local。

## Security / Privacy（本 spec 範圍內）

- `~/.agents/memory/` 全 local，目錄權限 700。
- 不做 secret redaction（留給 sub-spec #8）；importer 對 raw payload 不主動上傳。
- hook script 失敗一律靜默，不會 leak 訊息回 CLI 對話。
- Codex trust 流程：列入 deployment runbook，hook hash 改變後必須在 Codex CLI 內重新 `/hooks` trust。

## Operational Considerations

- 三家 hook script 部署透過 `paulshaclaw/memory/hooks/install.sh`，並提供 `uninstall.sh` 還原。
- 安裝會檢查 `~/.claude/settings.json` 既有 `hooks` 鍵，merge 而非覆蓋；若使用者已自設衝突 hook，提示並中止。
- watcher 不啟動時：hook 路徑仍可獨立運作。
- 全部 importer 對 inbox 寫入失敗時：raw payload 留在 `runtime/queue/_failed/`，由人工或 dream service 後處理。

## Migration / Rollout

| 階段 | 動作 |
|---|---|
| 部署 1 | A0 hook scripts 安裝 + smoke test |
| 部署 2 | A1 樹結構 + frontmatter lint |
| 部署 3 | A2 importer 對歷史 corpus 重放，建立首批 inbox |
| 部署 4 | A3 classifier 上線；對已寫 inbox 跑 reclassify（依 ledger） |
| 部署 5 | A4 projects.yaml + obs-auto-moc watcher service |
| 部署 6 | A5 live 驗收；之後 hook + watcher 24x7 並行 |

Rollback：移除 hook config 檔即可（watcher daemon 用 systemd 停掉）。inbox 內容保留不刪。

## Open Questions

1. **hook script 用 Python 直接呼叫 importer，會不會啟動成本太高？** 啟動 100 ms 級別，30s timeout 容許，先這樣；若實測太慢可改成 `nc` / unix socket 把 payload 丟到常駐 importer daemon。
2. **Codex `Stop` / `SubagentStop` 為 turn-scope** — 已解決：本 spec 採「hook 為遞增 nudge，watcher debounce 為事實上的 commit 觸發」，importer 用完整度比較做更新規則（見「冪等性與更新規則」）。不再需要心跳偵測。
3. **`~/.agents/memory/log/` 與 `~/.agents/log/` 是否合併？** 現況 `~/.agents/log/` 已存在，本 spec 建議用 `~/.agents/memory/log/` 隔離，避免污染舊 log。
4. **Copilot session-state JSON 結構** 在 `~/.copilot/history-session-state/session_*.json`，adapter 細節需 A2 階段以實際樣本驗證；本 spec 不寫死 schema 假設。

## Acceptance Criteria

- [ ] 三家 hook config 部署後執行 hello-world session，產出對應 `runtime/queue/<key>.json`。
- [ ] `paulshaclaw/memory/lint/frontmatter_lint.py` 跑 inbox 全檔通過。
- [ ] importer 對 ≥ 60 個歷史 session 跑過，inbox 檔數量 = 唯一 session 數量。
- [ ] 冪等性測試 pass。
- [ ] classifier spot check 30 筆 ≥ 70% 正確。
- [ ] obs-auto-moc watcher 跑 systemd 24h 無 crash；補抓遺漏 session ≥ 1 次（可手工觸發證明）。
- [ ] 與 OpenSpec change 對應的 `openspec/specs/stage2/` 新增 / 修改 spec delta（透過 openspec-propose 流程）。
- [ ] 對 `docs/superpowers/workstreams/stage2-paulsha-memory/` 不再勾起新的 blocker；workstream 文件補充本 sub-spec link。

## References

- `docs/research/02.obs-auto-moc-memory-dream-mode-24-7-service-notes-.md`
- `docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md`
- `openspec/specs/stage2/scope.md`
- `paulshaclaw/memory/routing.md`
- `paulshaclaw/janitor/service.md`
- `docs/superpowers/archive/stage2-paulsha-memory-20260420T1855570800.md`
- Claude Code hooks: https://docs.claude.com/en/docs/claude-code/hooks
- Codex CLI hooks: https://developers.openai.com/codex/hooks
- Copilot CLI hooks: https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks
