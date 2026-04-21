# hamanpaul Project Policy — Design (spec-1)

- Date: 2026-04-21
- Status: draft（待使用者核可後進入 writing-plans）
- Owner: @hamanpaul
- Audience profile: B（me + collaborators / AI agent），保留往 C（對外公開）演進的彈性
- Applies to: 所有 `https://github.com/hamanpaul/*` repo；工作專案（含 Broadcom 等）排除

## 0. 背景

paulshaclaw Stage 0–7 baseline 已全部 landed，但缺乏跨專案的文件 / 部署 / release / 版號 / 同步規範。本 spec 定義一套跨 `hamanpaul/*` 的 policy，讓：

- 任何新 repo 建立時自動帶入合規骨架
- CI gate 擋住不合規的 PR
- Agent 進入 session 時自動看到 checklist
- 文件與 code 強制同步更新

此 spec 只定義 **policy 本身與其擴散機制**；paulshaclaw 作為第一個參考實作的具體 user docs / deploy runbook 內容屬於 spec-2（另行 brainstorming）。

## 1. Scope 與 3-repo 架構

| Repo | 職責 | 變更頻率 |
|---|---|---|
| `hamanpaul/.github` | GitHub 社群預設：PR template / Issue template / SECURITY / CONTRIBUTING；會被所有沒自己一份的 repo 繼承 | 低 |
| `hamanpaul/paul-project-conventions` | Policy single source of truth：policy 文字、reusable workflows、audit 腳本；自身亦遵循自己的 policy | 中（policy 演進時） |
| `hamanpaul/paul-project-template` | 新專案骨架；供 `gh repo create --template` 使用 | 極低 |

### 設計取捨

- **三個 repo 而非一個 mono-repo**：職責清楚；conventions 可獨立版本化；`.github` 是 GitHub 指定名稱，沒得選。
- **conventions 自身遵循自己的 policy（dog-fooding）**：避免「policy 說要有 CHANGELOG，policy repo 自己沒有」。
- **template 保持最小**：只放指向 conventions 的 pointer 檔，不複製 policy 文字，避免漂移。

### 關係圖

```
paul-project-conventions (policy source)
         ↑
         │ uses: / 參照
         │
paul-project-template (骨架)
         │
         │ gh repo create --template
         ▼
任何 hamanpaul/<new-project>
         │
         │ workflow uses: hamanpaul/paul-project-conventions/...@v*
         ▼
CI 在每次 PR 跑 policy-check

hamanpaul/.github
         │
         │ GitHub 原生繼承機制
         ▼
所有 hamanpaul/* repo 自動帶 PR/Issue template
```

## 2. 版號、release trigger、CHANGELOG 格式

### 2.1 版號語意

格式：`MAJOR.MINOR.PATCH[-fix.N]`

| 位置 | 意義 | bump 時機 | 範例 |
|---|---|---|---|
| MAJOR | 正式 release | feature 達到對外可用 / 可發佈狀態 | `0.x.x → 1.0.0` |
| MINOR | 功能穩定 | 一組已規劃 feature 全 landed + **7 天無 `fix:` 類 PR 進 main** | `1.0.x → 1.1.0` |
| PATCH | Stage / 單位進度 | 單一 stage / feature batch 落地 | `1.1.2 → 1.1.3` |
| `-fix.N` | 落地後 bug fix | 非新 stage、非穩定、非 release | `0.0.7 → 0.0.7-fix.1` |

### 2.2 Profile

Policy 支援兩種專案型態，由 repo 自行宣告：

- **stage-driven**（如 paulshaclaw）：PATCH = 已完成的最高 stage 編號
- **flat**（一般工具 / 研究 repo）：PATCH = 累積已完成的 feature batch 計數

宣告檔 `.paul-project.yml`：

```yaml
policy_profile: stage-driven   # 或 flat
policy_version: 1.0.0
code_paths:                    # R-09 判斷 code 變動的 glob；若省略則用 profile 預設
  - "paulshaclaw/**/*.py"
  - "scripts/**"
```

`code_paths` 預設（profile 提供）：
- `stage-driven`：`["**/*.py", "**/*.sh", "scripts/**"]` 排除 `docs/**`、`tests/**`、`*.md`
- `flat`：同上

repo 可覆寫；R-09 使用此清單判斷本 PR 是否涉及 code 變動。

### 2.3 Tag 命名

- 格式：`v<MAJOR>.<MINOR>.<PATCH>[-<pre>]`，例 `v0.0.7`、`v0.0.7-fix.1`、`v1.0.0`
- 必須 annotated tag（`git tag -a`），訊息含 changelog 摘要
- `v` 前綴符合社群慣例，GitHub Releases UI 可辨識

### 2.4 CHANGELOG 格式

採用 [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)：

```markdown
# Changelog

All notable changes to this project will be documented in this file.
The format is based on Keep a Changelog, and this project adheres to
the `hamanpaul` project policy <policy_version>.

## [Unreleased]

### Added
- ...

### Changed
- ...

### Fixed
- ...

## [0.0.7] - 2026-04-21

### Added
- Stage 7 三分部署 baseline (#PR-link)

[Unreleased]: https://github.com/hamanpaul/<repo>/compare/v0.0.7...HEAD
[0.0.7]: https://github.com/hamanpaul/<repo>/releases/tag/v0.0.7
```

CI gate 語意檢查：
- `[Unreleased]` section 必存在
- 每個 tag 必在 CHANGELOG 有對應 heading
- PR 動到 code path，`[Unreleased]` 必有新增 entry（或 PR 帶 `skip-changelog` label + 理由）

### 2.5 Release trigger（semi-auto 經 PR label）

```
merge PR to main
    │
    │ (若 PR 標 release:patch / release:minor / release:major)
    ▼
release workflow 觸發
    │
    ├─ 讀 VERSION + CHANGELOG [Unreleased]
    ├─ 依 label 算新版號
    ├─ 更新 VERSION
    ├─ 把 [Unreleased] 搬到新版號 heading
    ├─ git commit + git tag -a v<new>
    ├─ git push origin main --tags
    └─ 建立 GitHub Release（Release note = CHANGELOG 該 entry）
```

無 label 的 PR → 只 merge、不 release（累積到 `[Unreleased]`）。

### 2.6 VERSION 檔

- 位置：repo 根目錄
- 內容：單行純文字版號（不含 `v` 前綴），例 `0.0.7`
- CI 檢查：`VERSION == 最新 tag`（去前綴與 pre-release 後綴）；release label PR 允許 `VERSION` 先於 tag 更新

## 3. Branch / PR / worktree 規則

### 3.1 分支層級

```
main                           永久；保護分支
  │
  └── feature/<request-slug>   一個請求一條；長命；merge 回 main 走 PR
         │
         └── wt/<feature-slug>/<subtask>   短命 worktree；merge 回 feature 走 ff 或 squash
```

### 3.2 命名規則

| 類型 | 格式 | 範例 |
|---|---|---|
| feature | `feature/<slug>` | `feature/docs-release-foundation` |
| worktree | `wt/<feature-slug>/<subtask>` | `wt/docs-release-foundation/policy-skeleton` |
| slug | kebab-case、ASCII、≤60 字元 | — |

舊 `wt/stage*`（paulshaclaw）視為 grandfathered，不溯及。

### 3.3 合併策略

| 路徑 | 方式 | 理由 |
|---|---|---|
| `wt/*` → `feature/*` | ff 或 squash | 個人 worktree 歷史不對外；ff 讓多 worktree 互相參考順 |
| `feature/*` → `main` | PR merge（merge commit，保留 working history） | 主幹看得到 feature 邊界 |
| direct commit to main | **禁止**（branch protection） | 見 3.4 |

### 3.4 Branch protection（`main`）

由 conventions 的 setup script 套用到每個 `hamanpaul/*`：

- ✅ Require a pull request before merging
- ✅ Require status check `policy-check` to pass
- ✅ Require conversation resolution before merging
- ⛔ Allow force push（關）
- ⛔ Allow deletions（關）
- ⛔ Require linear history（關；保留 merge commit）
- ✅ Allow admin bypass（保留；緊急處理用）

### 3.5 PR 規則

- 目標：只能是 `main` 或 `feature/<slug>`
- 標題：conventional-commit 格式，例 `feat(stage3): ...`
- Body：必用 `.github/pull_request_template.md`
- 生命週期 label：`wip` / `ready-for-review` / `blocked`
- Release label：`release:patch` / `release:minor` / `release:major`
- 豁免 label：`skip-changelog` / `policy-exempt:<rule>`（白名單見 §4.2）

### 3.6 Pending / Postponed / Cancelled 歸屬

- 不在當前 feature 的子任務一律不帶進此 feature
- 另開 feature 分支或寫 `docs/deferred.md`
- PR body 若提到未完成事項，必須顯式標「本 PR 不處理」

### 3.7 Worktree 清理

- `feature/*` 合併回 main 後，對應 `wt/*` 分支與 worktree 由 dev 自行清理
- Conventions repo 提供 `scripts/worktree-cleanup.sh` helper

## 4. CI gate 檢查項 + Agent checklist

### 4.1 Reusable workflow 結構

`hamanpaul/paul-project-conventions/.github/workflows/policy-check.yml`：

```yaml
name: policy-check
on:
  workflow_call:
    inputs:
      policy_profile:
        type: string
        required: true
      policy_version:
        type: string
        required: true

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hamanpaul/paul-project-conventions/.github/actions/policy-check@v1
        with:
          profile: ${{ inputs.policy_profile }}
          version: ${{ inputs.policy_version }}
```

下游 repo caller：

```yaml
# .github/workflows/policy-check.yml
on: [pull_request]
jobs:
  policy:
    uses: hamanpaul/paul-project-conventions/.github/workflows/policy-check.yml@v1
    with:
      policy_profile: stage-driven
      policy_version: 1.0.0
```

### 4.2 檢查項清單（結構性 + 關聯性）

| ID | 檢查 | 失敗條件 | 豁免 label |
|---|---|---|---|
| R-01 | 根目錄 `README.md` 存在 | 缺檔或 <100 byte | — |
| R-02 | `README.md` 含必備段落 | 缺 `## Install` / `## Usage` / `## Version` | `policy-exempt:readme-sections` |
| R-03 | 根目錄 `CHANGELOG.md` 存在 | 缺檔 | — |
| R-04 | `CHANGELOG.md` 格式合規 | 非 Keep-a-Changelog 1.1.0 schema / 缺 `[Unreleased]` | `policy-exempt:changelog-format` |
| R-05 | 根目錄 `VERSION` 存在 | 缺檔 | — |
| R-06 | `VERSION` 符合語意 | 不匹配 `<MAJOR>.<MINOR>.<PATCH>(-fix\.\d+)?` | — |
| R-07 | `VERSION` 與最新 tag 一致 | `VERSION != latest_tag` 且無 `release:*` label | — |
| R-08 | `.paul-project.yml` 存在且完整 | 缺檔或缺 `policy_profile` / `policy_version` | — |
| R-09 | Code 變動必有 CHANGELOG entry | code path 有變動但 `[Unreleased]` 未動 | `skip-changelog` |
| R-10 | PR title 符合 conventional-commit | regex 不匹配 | `policy-exempt:pr-title` |
| R-11 | PR body checkbox 全勾 | 必勾項未勾滿 | 帶 `wip` 時自動通過 |
| R-12 | 分支來源正確 | 目標=main 時來源非 `feature/*`；目標=`feature/*` 時來源非 `wt/<feature>/*` | `policy-exempt:branch-name` |
| R-13 | Agent convention files 存在 | 缺 `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `.github/copilot-instructions.md` | `policy-exempt:agent-files` |
| R-14 | Agent files policy 版本一致 | 內容 `policy_version` 與 `.paul-project.yml` 不符 | — |
| R-15 | Caller workflow 用 tag / SHA 鎖定 | `uses:` 指向 branch ref（`@main`、`@master`、`@develop` 等）或無 ref；允許 tag 與 40-char SHA，包含浮動 major tag 如 `@v1` | — |

豁免 label 白名單即上表所有 `policy-exempt:*` 值；gate 只認這些，其他一律視同未豁免。

### 4.3 Agent checklist（`CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `.github/copilot-instructions.md`）

四份內容完全一致，由 template 同時產生；由 audit 保證同步。

```markdown
<!-- managed-by: hamanpaul/paul-project-conventions@v1.0.0 -->
<!-- 若修改此檔，同步更新 CLAUDE.md / AGENTS.md / GEMINI.md / .github/copilot-instructions.md 四份 -->

# Agent Policy Checklist

本 repo 受 hamanpaul project policy v1.0.0 管轄。
所有 agent 進入 session 時，必須依下列 checklist 行動。

## 本 repo 的 profile
- policy_profile: stage-driven | flat  ← 見 `.paul-project.yml`
- policy_version: 1.0.0

## 動工前
- [ ] 確認當前分支不是 main
  - 若在 main，先開 `feature/<slug>` 分支
  - 若在 `feature/*`，可直接工作，或再開 `wt/<feature>/<subtask>`
- [ ] 若本任務跨多個子項，先建議用 git worktree 拆開

## 改 code 時
- [ ] 同一 PR 必須同步更新 `CHANGELOG.md [Unreleased]`
- [ ] 除非可明確標示為 docs-only / test-only / chore，否則不得省略 CHANGELOG

## 改版號時（release 觸發時）
- [ ] 嚴格遵循 `<MAJOR>.<MINOR>.<PATCH>[-fix.N]`
- [ ] PATCH bump 對應 profile：
  - stage-driven：一個 stage 落地
  - flat：一個 feature batch 完成
- [ ] MINOR bump 需滿足：feature 群組全 landed + 7 天無 hotfix
- [ ] MAJOR bump 需使用者明確核可

## 完成任務（claim done）前
- [ ] `CHANGELOG.md [Unreleased]` 有對應 entry
- [ ] `VERSION` 內容與意圖一致（release label PR 才可偏離 latest tag）
- [ ] `.github/pull_request_template.md` checklist 全勾
- [ ] 測試全綠（profile 決定指令）
- [ ] 若跳過任何檢查，PR 必須帶對應 `policy-exempt:<rule>` 或 `skip-changelog` label + 理由

## 禁止
- 直接 commit 到 main
- 建立不符合命名規則的分支
- 發明新 `policy-exempt:*` label（只能用 policy 列舉的）
- 修改本檔而不同步其他三份 agent convention 檔
```

### 4.4 `.github/pull_request_template.md`（住在 `hamanpaul/.github`，全 repo 繼承）

```markdown
## 變更摘要
<!-- 1-3 句 why + what -->

## 本 PR 所屬
- feature 分支: `feature/<slug>`
- 相關 spec / issue: <!-- link -->

## Policy Checklist
- [ ] 本 PR 來自 `feature/<slug>` 或 `wt/<feature>/<subtask>` 分支
- [ ] `CHANGELOG.md [Unreleased]` 已更新（或本 PR 標 `skip-changelog` 並在下方說明）
- [ ] `VERSION` 正確（或本 PR 標 `release:*` 由 workflow 處理）
- [ ] 使用者文件已同步（README / docs/）
- [ ] 測試全綠
- [ ] CI `policy-check` 綠燈

## 例外說明（若有任何 `policy-exempt:*` 或 `skip-changelog`）
<!-- 必填理由 -->
```

### 4.5 豁免治理

- 每次 `policy-exempt:*` 使用由 audit 收集（未來升級路徑啟用）
- 高豁免率視為規則需調整的訊號，不是鼓勵濫用豁免

## 5. Bootstrap、migration、policy 本身的測試與演進

### 5.1 `paul-project-template` 內容

```
paul-project-template/
├── .paul-project.yml                  (建立者填 profile / version)
├── README.md                          (Install / Usage / Version 空段落骨架)
├── CHANGELOG.md                       (Keep-a-Changelog 骨架 + [Unreleased])
├── VERSION                            (0.0.0)
├── CLAUDE.md                          (agent checklist，managed-by 註記)
├── AGENTS.md                          (同 CLAUDE.md，完整複製)
├── GEMINI.md                          (同上)
├── .github/
│   ├── copilot-instructions.md        (同上)
│   └── workflows/
│       └── policy-check.yml           (uses: conventions reusable workflow)
└── .gitignore                         (最小通用集)
```

Template **不含**：LICENSE（B 階段略過）、CODE_OF_CONDUCT / SECURITY（由 `hamanpaul/.github` 繼承）、具體語言的 build config。

### 5.2 建立新 repo 的標準動作

```bash
gh repo create hamanpaul/<name> \
  --template hamanpaul/paul-project-template \
  --private --clone

cd <name>
$EDITOR .paul-project.yml                                 # 填 profile / version

git add .paul-project.yml
git commit -m "chore: claim policy v1.0.0 with <profile> profile"

curl -sSL https://raw.githubusercontent.com/hamanpaul/paul-project-conventions/v1/scripts/apply-branch-protection.sh | bash
```

後續走 `feature/<slug>` → `wt/<feature>/<subtask>` → PR。

### 5.3 既有 repo 的 migration（paulshaclaw 等）

Policy 不自動溯及既往；每個 repo 自行 opt-in。入會 8 步：

1. 新增 `.paul-project.yml`（宣告 profile + policy 版本）
2. 補 `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `.github/copilot-instructions.md`
3. 補 `VERSION`（paulshaclaw 目前應填 `0.0.7`）
4. 補 `CHANGELOG.md`（paulshaclaw 可由 git log 回溯 Stage 0–7 entry）
5. 新增 `.github/workflows/policy-check.yml` caller
6. 補必備 README 段落
7. 套 branch protection
8. 跑一次 PR 驗證 gate 通過

這 8 步即 spec-2（paulshaclaw local）要做的事，spec-2 同時驗證 policy 可行。

### 5.4 Policy 本身的測試（meta-testing）

```
paul-project-conventions/
├── tests/
│   ├── fixtures/                      (故意違規 / 合規 / 豁免的迷你 repo 快照)
│   │   ├── missing-changelog/
│   │   ├── version-mismatch/
│   │   ├── wrong-branch-name/
│   │   └── valid-minimal/
│   └── test_policy_check.py           (對每個 rule 驗違規偵測 + 合規不誤殺)
└── .github/workflows/
    ├── self-test.yml                  (跑上面測試)
    └── policy-check.yml               (dog-food：conventions 自己也跑 policy-check)
```

每個 rule `R-01 ~ R-15` 必有：
- 至少一個違規 fixture（gate 必擋）
- 至少一個合規 fixture（gate 必放行）
- 至少一個豁免 fixture（帶 label 時 gate 必放行；僅對有豁免 label 的 rule）

### 5.5 Policy 版號與下游 repo 的鎖定關係

Conventions 自身版號規則同 §2，tag 格式 `v<MAJOR>.<MINOR>.<PATCH>`：

| 下游寫法 | 行為 | 用於 |
|---|---|---|
| `@v1`（浮動 major tag） | 跟 v1.x 最新；由 conventions release 流程維護此 tag 始終指向最新 v1.y.z | 預設；小版自動跟 |
| `@v1.0.0`（精確 tag） | 完全鎖死 | 嚴格場景 |
| `@<40-char-SHA>` | 鎖 commit | 供應鏈嚴格場景 |
| `@main` / `@master`（branch） | 跟 branch HEAD | 禁止（R-15 擋） |

### 5.6 Policy 演進（breaking change 擴散）

**MAJOR bump（v1 → v2）**：

1. conventions 發 v2.0.0 release + migration guide
2. 新案透過 template 拿 v2；既有案保持 v1
3. 既有案自挑時機升級：改 caller `@v1` → `@v2`、對齊 `.paul-project.yml` 的 `policy_version`
4. conventions 維護 v1 安全補丁 ≥ 6 個月

**MINOR / PATCH**：

- 下游用 `@v1` 自動跟上
- MINOR 引入新 rule 時，新 rule 預設 `warning` 不 `error`，3 個月後或下次 MAJOR 升 error

### 5.7 Memory entry（跨 session 持續）

```
type: reference
name: hamanpaul project policy
description: 所有 hamanpaul/* repo 遵循的跨專案 policy
---
- Policy source: https://github.com/hamanpaul/paul-project-conventions
- Template: https://github.com/hamanpaul/paul-project-template
- 應用範圍: 所有 hamanpaul/* repo；工作專案除外
- Agent 行為: 進入 hamanpaul/* repo session 時必讀 repo 內 CLAUDE.md checklist
- 版號: <MAJOR>.<MINOR>.<PATCH>[-fix.N]；語意依 profile 而定
- Profile: stage-driven | flat（宣告於 `.paul-project.yml`）
```

### 5.8 Out of scope（本 spec 不做）

- paulshaclaw 自身的 user docs 內容（→ spec-2）
- paulshaclaw 的 deploy runbook（→ spec-2）
- audit script 的自動化排程 / auto-fix PR（→ 未來升級）
- 除 `hamanpaul/*` 以外的 repo（policy 天然不觸碰）
- LICENSE 選定（受眾從 B 演進到 C 時再議）

## 6. 驗證與 Acceptance criteria

spec-1 落地後必須滿足：

1. `hamanpaul/.github`、`hamanpaul/paul-project-conventions`、`hamanpaul/paul-project-template` 三個 repo 建立完成並 public-ish（private 可，但能被 Actions 存取）
2. conventions 自身 `policy-check` 綠燈（self-dog-food）
3. 從 template 建出新 test-repo，policy-check 首次即綠燈
4. 故意違規的 fixture repo 可被 gate 擋下（每個 rule 至少一例）
5. Memory entry 已寫入 `~/.claude/.../memory/`
6. paulshaclaw 作為 spec-2 第一個參考實作，走完 §5.3 migration 8 步

## 7. 風險與緩解

| 風險 | 影響 | 緩解 |
|---|---|---|
| Policy 過嚴導致日常 friction | 實際拖慢開發 | 每條 rule 都有豁免 label；高豁免率視為調整訊號 |
| 同步 4 份 agent convention file | 人工易漏同步 | audit 檢查 R-14；未來可做自動同步 |
| conventions 自身 breaking change | 下游全炸 | 嚴守 §5.6 演進節奏；6 個月 v-1 維護 |
| 既有 repo migration 成本 | 拖延採用 | 只要求新案；既有案自挑時機 |
| GitHub Actions 配額 | reusable workflow 每 repo 都跑 | 公開 repo 免費；私有 repo 用量可控 |

## 8. 後續（spec-2 與之後）

- **spec-2（paulshaclaw local）**：把 paulshaclaw 走一次 §5.3 8 步；補 user docs（Install / Quickstart / Usage / Ops）；補 deploy runbook；成為 policy 的第一個參考實作。
- **未來升級**：audit scheduled job（把 enforcement 從 Q5-B 升到 Q5-C）；PR auto-fix（Q5-D）；LICENSE 決策（受眾 B → C 時）。
