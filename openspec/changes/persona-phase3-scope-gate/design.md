## Context

Phase 1（archived `2026-06-18-persona-phase1-shadow-gate`）已交付可直接 reuse 的 gate 原語：
- `gate.compute_changed_paths(base, head, repo=None) -> list[str]`：`git -c core.quotepath=false diff --name-only base...head`，非零 returncode → `RuntimeError`（fail-closed）。
- `gate.build_verdict(*, role, changed_paths, manifest_ok, catalog=None) -> dict`：算 `{role, changed_paths, violations:[{path,reason}], handoff_ok, ok}`，`ok = (not violations) and manifest_ok`。
- `gate.load_manifest_ok(role, manifest_path, catalog=None) -> bool`：讀驗 manifest，fail-closed → False。
- `handoff.read_manifest(path, catalog=None) -> dict`：fail-closed 讀驗，回 payload（含 `from_role`）。
- `loader.load_catalog()`：從 `personas.yaml` 載 `dict[str, PersonaContract]`。

設計 §8 要把 ② 接成 CI 硬後盾。但 conventions 永遠做不到 in-loop pre-push 軟回饋（它只在 PR 時跑通用 rule、不認 persona scope），故必須自建 `.github/workflows/persona-scope.yml` + 一支 CI runner。Phase 3 **只到 shadow**：observe/annotate-only、恆 exit 0、非 required，先對真 PR 跑、調至零誤殺，enforce 翻牌與豁免 label 留作文件化的未來手動步驟。

## Goals / Non-Goals

**Goals:**
- `scope_ci.py`：`main(argv=None, env=None) -> int` 薄 CI runner，解析 PR base/head（env 注入）、探測最新 `runtime/handoff/*.json`、reuse `gate` 算 verdict、印 JSON、**shadow 恆 exit 0**。判定邏輯全 reuse `gate.py`，**不重寫 scope 邏輯**。
- **無 manifest 乾淨跳過**：找不到 manifest → 印 `no manifest, skipped (shadow)` 通知並 return 0，**絕不報錯**（常態路徑，含本 PR 自身與其他 repo PR）。
- `persona-scope.yml`：`on: pull_request`、`fetch-depth: 0`、Python 3.12、`pip install pytest -r requirements-stage9.txt`、跑 `python -m paulshaclaw.persona.scope_ci`。**non-blocking、非 required、恆 exit 0**。
- 測試以注入 `env` ＋ monkeypatch `gate.compute_changed_paths` 驗三情境（無 manifest／in-scope／out-of-scope），**不依賴真 GitHub 環境**。
- **additive only**：不改 `tests.yml`／`policy-check.yml`，不動 branch protection。

**Non-Goals:**
- ❌ 啟用 enforce（shadow→enforce 翻牌）。本階段恆 shadow；enforce 機制與決策為文件化未來手動步驟（proposal「文件化」段 + 本 design D5）。
- ❌ 把 `persona-scope` 設為 required status check／任何 branch-protection 變更。明確文件化為 repo 管理事務、手動執行、非本 PR。
- ❌ 讀／實作豁免 label `policy-exempt:persona-scope`。shadow 不需要；僅文件化其 enforce 後語義。
- ❌ ② 角色不變式（reviewer diff 不可含 code、builder 須帶測試）——沿用 Phase 1 Non-Goal，留待 enforce 強化。
- ❌ 修改 `gate.py` / `handoff.py` / `loader.py` 既有判定邏輯（純 reuse）。

## Decisions

- **D1 — base/head 解析（env 注入、CI 慣例對齊）**：base = `origin/{GITHUB_BASE_REF}`，`GITHUB_BASE_REF` 缺省 `'main'`（GitHub Actions `pull_request` 事件會設 `GITHUB_BASE_REF`=PR 目標分支）。head = `GITHUB_SHA`（缺省 `'HEAD'`）。`origin/` 前綴對齊 `actions/checkout@v4` + `fetch-depth: 0` 後 base 分支以 remote-tracking ref 存在的事實。解析純由 `env` 字典推導，`main(argv, env)` 的 `env` 預設 `os.environ` 但可注入 → 測試完全不碰真環境。
- **D2 — manifest 探測（最新、無則乾淨跳過）**：`glob('runtime/handoff/*.json')` 取 mtime 最大者；空集合 → 印 `no manifest, skipped (shadow)`、`return 0`。**這是硬安全邊界**：multi-PR 共用同 workflow，絕大多數 PR 無 manifest（Phase 3 PR 自身、其他 repo PR 皆然），無 manifest **必須安靜放行而非報錯**。探測根目錄可由 `--repo`/`env` 覆寫以利測試（temp dir）。
- **D3 — 全 reuse gate，shadow 恆放行**：有 manifest 時 `from_role = handoff.read_manifest(manifest)['from_role']` → `changed = gate.compute_changed_paths(base, head)` → `manifest_ok = gate.load_manifest_ok(from_role, manifest)` → `verdict = gate.build_verdict(role=from_role, changed_paths=changed, manifest_ok=manifest_ok)`。`verdict['mode']='shadow'`，`print(json.dumps(verdict))`。**不論 `ok` 真假恆 `return 0`**。scope 判定（`evaluate_filesystem`）完全在 `gate`/`guardrail`，runner 不複製任何規則。
- **D4 — diff 取得失敗 fail-closed 但 shadow 放行**：`compute_changed_paths` 在無共同祖先／淺 clone／base ref 不存在時 raise `RuntimeError`。runner catch → verdict 記 `diff_error` 並標 `ok=False`（fail-closed 語義保留供日後 enforce），但 **shadow 仍 `return 0`**（與 Phase 1 gate `main` 對 `diff_error` 的處理一致：印出、標 false、shadow 不擋）。read_manifest 對非法 manifest raise `ValueError`——runner 視為「manifest 存在但不可信」：印 verdict（`handoff_ok=False`、`ok=False`）、shadow `return 0`；**唯一觸發 skip 的條件是「完全找不到 manifest 檔」**，已存在但壞掉者照跑 verdict（暴露問題、shadow 不擋）。
- **D5 — enforce / required / label 全為文件化未來手動步驟**：runner 預留 enforce 路徑的「形狀」（verdict 已含 `ok`），但本 change **不接 `--enforce`、workflow 不設 required、不讀 label**。翻牌步驟（改 runner 吃 enforce + branch protection 設 required + 啟用 label 判讀）寫進 proposal「文件化」段。理由：branch-protection 是 repo 管理事務（非 code），且 enforce 前必須 shadow 觀測零誤殺——硬安全約束「絕不在本 PR 啟用強制」。
- **D6 — workflow 依賴最小化**：`pip install pytest -r requirements-stage9.txt`——`PyYAML` 在 `requirements-stage9.txt`，是 `loader.load_catalog()` 載 `personas.yaml` 的硬需求（無它 import 即炸）；`pytest` 對齊 house `tests.yml` 安裝慣例（即使 runner 不直接用 pytest，保持安裝面一致、低驚訝）。**不**安裝 `requirements-stage11.txt`（textual 與本 runner 無關）。

## Risks / Trade-offs

- [shadow 恆 exit 0 掩蓋真違規] → 正是設計意圖（先觀測、調零誤殺再翻 enforce）；verdict JSON 完整印出供人/log/PR annotation 檢視。enforce 為獨立的文件化手動決策（D5）。
- [`origin/<BASE>` 在某些 checkout 模式不存在 → diff 失敗] → D4 fail-closed catch + shadow 放行；`fetch-depth: 0` 已最大化共同祖先可得性。enforce 階段再決定是否對 `diff_error` 強制 fail（屆時需更穩健的 base 解析，例如 `git merge-base`）。
- [惡意/誤植 manifest 降權（改 from_role 成寬 scope 的 manager）] → 沿用設計 §6/§13 緩解：`runtime/handoff/**` 屬 manager write scope，改它本身即越界、會被 diff gate 抓到；shadow 階段先觀測此類模式。
- [多 PR 共用 workflow，無 manifest 是常態] → D2 明確「無 manifest 乾淨跳過 return 0」為一等公民路徑並有測試覆蓋；這是最關鍵的非破壞性保證（避免拖垮所有無 manifest 的 PR）。
- [workflow 被誤設為 required] → 本 change 文件 + proposal 明確「非 required、branch-protection 不動」；翻 required 為獨立手動步驟，需配合 enforce 同時進行。
