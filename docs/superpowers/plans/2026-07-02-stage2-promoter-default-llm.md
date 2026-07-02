# Stage 2 Atomizer 預設 Promoter 改 LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 關閉 identity promoter 的「意外預設」入口（issue #175）：出貨 `atomizer.yaml` 預設 `promoter: llm`，未帶 `--promoter` 的 CLI 路徑不再落 `IdentityPromoter`；identity 保留為顯式選項；systemd 排程範本（wrapper + service）與生產一致 pin `--promoter llm`。驗收對齊 issue：config 預設值為 llm、未帶 `--promoter` 的 CLI 路徑不再走 IdentityPromoter、`pytest paulshaclaw/memory/tests/` 全綠。

**Architecture:** 純 config/範本翻轉，零程式邏輯變更。promoter 決策鏈：`memory/cli.py:70,:87`（`--promoter` `default=None`）→ `atomizer/cli.py:73` `promoter_name = args.promoter or config.default_promoter`、`:74-75` 非 `"llm"` 一律 `IdentityPromoter()`（`dream/cli.py:34` 複用同函式）→ `atomizer/config.py:297-302` 讀 yaml key `promoter`。唯一實際生效的預設來源是 packaged `atomizer/atomizer.yaml:30`（永遠帶 key，config.py 的兩個 `"identity"` fallback 對它永不觸發）。翻 yaml 這一行即翻轉整條鏈的預設。

**Tech Stack:** Python 3.12、pytest（unittest 風格 class，pytest runner 跑）、PyYAML。

**Spec:** OpenSpec change `openspec/changes/stage2-promoter-default-llm/`（proposal / design / specs / tasks）｜issue #175

---

## Boundary（可改檔案白名單）

只允許修改以下檔案，超出即停并回報：

- `paulshaclaw/memory/atomizer/atomizer.yaml`
- `paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh`
- `paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service`（boundary 延伸一檔，理由見下）
- `paulshaclaw/memory/tests/**`（新增 `test_promoter_default.py`；修改 `test_atomizer_cli.py`、`test_dream_systemd_template.py`、`stage2_integration_check.sh`）
- `paulshaclaw/memory/atomizer/config.py` —— 已確認**不需修改**（列入白名單僅備查；yaml key 讀取在 config.py:297-302、dataclass 預設在 :41，均維持現狀，理由見 Design D1）

> **`.service` 延伸理由**：issue 點名的殘餘風險入口是「systemd path 啟用即重演」。`dream/systemd/paulsha-memory-dream.service:9` 的 `ExecStart` **不經 wrapper**、直接硬 pin `--promoter identity`；只改 wrapper 關不掉這個入口，且 `test_dream_systemd_template.py:19,:28` 同時鎖兩檔。單 token 修改。

**明確不可動**：`atomizer/cli.py`、`atomizer/pipeline.py`、`memory/cli.py`、`dream/cli.py`、`scripts/start.sh`、`.github/workflows/**`、`.paul-project.yml`、任何 `policy_version`。

---

## File Structure

- Create: `paulshaclaw/memory/tests/test_promoter_default.py` — 預設 promoter 鎖定測試（4 tests）。
- Modify: `paulshaclaw/memory/atomizer/atomizer.yaml` — `:30` `promoter: identity` → `promoter: llm` + 一行註解。
- Modify: `paulshaclaw/memory/tests/test_atomizer_cli.py` — `:35-49` dry-run 測試 argv 補顯式 `--promoter identity`。
- Modify: `paulshaclaw/memory/tests/stage2_integration_check.sh` — `:133-134` atomize dry-run 補 `--promoter identity`。
- Modify: `paulshaclaw/memory/tests/test_dream_systemd_template.py` — `:19,:28` 斷言 identity → llm。
- Modify: `paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh` — `:6` pin llm + 註解。
- Modify: `paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service` — `:7-9` pin llm + 註解。

測試指令（本機，勿用 `unittest discover`——會靜默跳過 pytest 風格測試）：

```bash
cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q
```

CI 等效：`python -m pytest tests/ paulshaclaw/memory/tests/ -q`。基線（2026-07-02 main）：**769 passed, 1 skipped**（輸出行另帶 `87 subtests passed`，屬 importer 測試的 subtests，計數比對時忽略即可）。

---

## 行為契約與邊界條件（worker 必讀）

1. **`load_config` 的 override 陷阱**：`atomizer/config.py:116-117` 預設 sentinel 會讀 `~/.config/paulshaclaw/atomizer.override.yaml`。所有新測試一律 `load_config(override_path=None)` 停用 override，只驗 repo 內建 yaml。
2. **`_build_promoter` 建構即安全**：llm 分支只建構 `AgentExecClient`/`CachingAgentClient`/`LLMPromoter` 物件、讀 skill 檔與 `~/.agents/config/projects.yaml`（缺檔回空 list），**不 spawn 任何子行程**——測試可安全呼叫。需要 `args.agent_command = None`（`atomizer/cli.py:78-81` 才會走 config 的 command）。
3. **dry-run 仍會呼叫 promoter**：`pipeline.py` `_promote_pass` 的 dry-run 分支（`:344-347`）照樣呼叫 `_promote_fragments(promoter, ...)`。因此任何未帶 `--promoter` 的 atomize dry-run 在預設翻轉後會嘗試真跑 `scripts/claude-gemma4`——這就是 Task 2 必須同 commit 修 `test_atomizer_cli.py` 與 `stage2_integration_check.sh` 的原因，否則 suite 在 Task 2 後不綠。注意 `stage2_integration_check.sh` **不是純手動腳本**：`test_importer_cli.py:142`（`Stage2IntegrationCheckScriptTest::test_stage2_integration_check_succeeds_outside_repo_root`）會在 pytest suite 內以 subprocess 完整執行它，所以 `.sh` 的修改同樣被本機/CI pytest 覆蓋。
4. **code-level fallback 維持 identity（fail-safe）**：`config.py:41`（dataclass 預設）與 `:297` `config_data.get("promoter", "identity")` 不改——缺 `promoter` key 的精簡 config 不得隱性升級成外呼 LLM。以測試 (d) 鎖定。
5. **mock 類測試不受影響**：`test_dream_cli.py:46,:78`、`test_dream_cli_moc_warnings.py:62` 用 `SimpleNamespace(default_promoter="identity")` mock `load_config`，與 yaml 無關，**不要改**。
6. **顯式 identity 的既有測試是特性不是回歸**：`test_dream_e2e.py:148`、`test_moc_e2e.py:37-38`、`stage2_integration_check.sh` dream 段落顯式傳 identity——保留原樣，它們證明 identity 顯式路徑仍可用。
7. **config_hash 會變**：yaml 內容變動 → `load_config` 回傳 hash 改變（`config.py:332-333`）。hash 僅入 ledger 供追溯，無 gating，無需遷移。

---

## Task 1: 預設 promoter 鎖定測試（RED）

**Files:**
- Test: `paulshaclaw/memory/tests/test_promoter_default.py`（新檔）

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_promoter_default.py
"""#175: atomizer 出貨預設 promoter 必須是 llm；identity 僅限顯式選用。"""
from __future__ import annotations

import argparse
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.atomizer import cli as atomizer_cli
from paulshaclaw.memory.atomizer import config as atomizer_config
from paulshaclaw.memory.atomizer.llm_promoter import LLMPromoter
from paulshaclaw.memory.atomizer.promoter import IdentityPromoter


class PromoterDefaultTests(unittest.TestCase):
    def test_shipped_config_default_promoter_is_llm(self):
        # override_path=None 停用 ~/.config/paulshaclaw/atomizer.override.yaml，
        # 只驗 repo 內建 atomizer.yaml（唯一實際生效的預設來源）。
        cfg, _ = atomizer_config.load_config(override_path=None)
        self.assertEqual(cfg.default_promoter, "llm")

    def test_build_promoter_without_flag_is_llm(self):
        # 鎖 atomizer/cli.py:73 `args.promoter or config.default_promoter`：
        # 未帶 --promoter（None）不得再落 IdentityPromoter。
        cfg, _ = atomizer_config.load_config(override_path=None)
        args = argparse.Namespace(promoter=None, agent_command=None)
        with TemporaryDirectory() as tmp:
            promoter = atomizer_cli._build_promoter(args, cfg, Path(tmp))
        self.assertIsInstance(promoter, LLMPromoter)
        self.assertNotIsInstance(promoter, IdentityPromoter)

    def test_explicit_identity_flag_still_honored(self):
        # identity 保留為顯式選項（測試/離線 deterministic 用）。
        cfg, _ = atomizer_config.load_config(override_path=None)
        args = argparse.Namespace(promoter="identity", agent_command=None)
        with TemporaryDirectory() as tmp:
            promoter = atomizer_cli._build_promoter(args, cfg, Path(tmp))
        self.assertIsInstance(promoter, IdentityPromoter)

    def test_config_without_promoter_key_fails_safe_to_identity(self):
        # code-level fallback（config.py:297 get("promoter", "identity")）維持
        # identity：缺 key 的精簡 config 不得隱性升級成外呼 LLM（fail-safe）。
        with TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            (config_dir / "atomizer.yaml").write_text(
                "schema_version: 1\n", encoding="utf-8"
            )
            cfg, _ = atomizer_config.load_config(
                default_dir=config_dir, override_path=None
            )
        self.assertEqual(cfg.default_promoter, "identity")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_promoter_default.py -q`
Expected: **2 failed, 2 passed** —— `test_shipped_config_default_promoter_is_llm`（`'identity' != 'llm'`）與 `test_build_promoter_without_flag_is_llm`（拿到 `IdentityPromoter`）失敗；explicit-identity 與 fail-safe 兩測試通過。

- [ ] **Step 3: Commit（RED 測試先入庫，方便 reviewer 對照）**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/tests/test_promoter_default.py
git commit -m "test(memory): #175 鎖定 atomizer 預設 promoter 契約（現階段 RED）"
```

---

## Task 2: 翻轉出貨預設 + 既有消費者顯式化（GREEN）

**Files:**
- Modify: `paulshaclaw/memory/atomizer/atomizer.yaml`
- Modify: `paulshaclaw/memory/tests/test_atomizer_cli.py`
- Modify: `paulshaclaw/memory/tests/stage2_integration_check.sh`

> 三檔必須同一 commit：yaml 翻轉後，任何未帶 `--promoter` 的 dry-run 都會嘗試真跑 gemma4（見行為契約 3），單改 yaml 會讓 `test_atomizer_cli.py::test_dry_run_prints_summary_and_writes_nothing` 變紅。

- [ ] **Step 1: atomizer.yaml 翻轉預設**

`paulshaclaw/memory/atomizer/atomizer.yaml:30`，將：

```yaml
promoter: identity
```

改為：

```yaml
# #175: 預設 llm 蒸餾。identity 會把 importer 樣板 fragments 1:1 複製成
# knowledge slices（樣板噪音），僅保留為顯式 --promoter identity（測試/離線）。
promoter: llm
```

- [ ] **Step 2: test_atomizer_cli.py dry-run 測試改顯式 identity**

`paulshaclaw/memory/tests/test_atomizer_cli.py` 的 `AtomizeCliTests.test_dry_run_prints_summary_and_writes_nothing`（:43-44），將：

```python
                rc = cli.main(["memory", "atomize", "--memory-root", str(root),
                               "--now", "2026-05-31T03:00:00Z", "--dry-run"])
```

改為：

```python
                # #175 後預設 promoter=llm 會真跑 agent；本測試標的是 dry-run
                # 摘要行為，顯式改用 deterministic 的 identity。
                rc = cli.main(["memory", "atomize", "--memory-root", str(root),
                               "--now", "2026-05-31T03:00:00Z", "--dry-run",
                               "--promoter", "identity"])
```

- [ ] **Step 3: stage2_integration_check.sh 補顯式 identity**

`paulshaclaw/memory/tests/stage2_integration_check.sh:133-134`，將：

```bash
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory atomize \
  --memory-root "$ATOMIZE_ROOT" --now "2026-05-31T03:00:00Z" --dry-run | grep -Fq '"slices":'
```

改為：

```bash
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory atomize \
  --memory-root "$ATOMIZE_ROOT" --now "2026-05-31T03:00:00Z" --dry-run \
  --promoter identity | grep -Fq '"slices":'
```

（同檔 `:155-160` 的 llm stub 呼叫與 dream 段落本已顯式，勿動。）

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_promoter_default.py paulshaclaw/memory/tests/test_atomizer_cli.py -q`
Expected: PASS（`test_promoter_default.py` 4/4 轉綠、`test_atomizer_cli.py` 全綠）。

再跑全套：`PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q`
Expected: **773 passed, 1 skipped**（基線 769 + 新增 4）。

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/atomizer/atomizer.yaml \
        paulshaclaw/memory/tests/test_atomizer_cli.py \
        paulshaclaw/memory/tests/stage2_integration_check.sh
git commit -m "feat(memory): #175 atomizer 出貨預設 promoter 改 llm，identity 僅限顯式選用"
```

---

## Task 3: systemd 排程範本 pin llm

**Files:**
- Test: `paulshaclaw/memory/tests/test_dream_systemd_template.py`（改斷言）
- Modify: `paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh`
- Modify: `paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service`

- [ ] **Step 1: Write the failing test（改既有斷言）**

`paulshaclaw/memory/tests/test_dream_systemd_template.py`：

`:19`（`test_service_invokes_require_idle` 內）：

```python
        self.assertIn("--promoter llm", service)
```

`:28`（`test_wrapper_script_exists` 內）：

```python
        self.assertIn("--promoter llm", text)
```

（兩行原為 `self.assertIn("--promoter identity", ...)`。）

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_dream_systemd_template.py -q`
Expected: **2 failed, 1 passed**（wrapper 與 service 尚為 identity）。

- [ ] **Step 3: 改 wrapper**

`paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh` 全檔改為：

```bash
#!/usr/bin/env bash
# 排程（systemd）dream 路徑的薄 wrapper。
# #175: 顯式 pin --promoter llm，與生產 dream loop（scripts/start.sh）一致，
# 且本地 atomizer override 無法翻轉 promoter 選擇。
# 注意：identity promoter 僅保留為顯式測試/離線選項——它會把 importer 樣板
# fragments（## Source / ## CWD / (none) 清單等）1:1 複製成 knowledge slices，
# noise gate 只能擋掉其中一部分樣板。
set -euo pipefail
MEMORY_ROOT="${PSC_MEMORY_ROOT:-$HOME/.agents/memory}"
exec python3 -m paulshaclaw.memory.cli memory dream run --memory-root "$MEMORY_ROOT" --require-idle --promoter llm
```

- [ ] **Step 4: 改 service**

`paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service` 的 `:6-9`（原註解兩行 + ExecStart）改為：

```ini
# %h = user home; adjust MEMORY_ROOT/PYTHONPATH at install time.
# #175: 排程路徑顯式 pin --promoter llm，與生產（scripts/start.sh）一致；
# identity 僅為顯式測試選項（會 1:1 複製 importer 樣板成 knowledge slices）。
ExecStart=/usr/bin/env python3 -m paulshaclaw.memory.cli memory dream run --memory-root %h/.agents/memory --require-idle --promoter llm
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_dream_systemd_template.py -q`
Expected: PASS（3 tests）。

殘留檢查：

```bash
grep -rn -- "--promoter identity" /home/paul_chen/prj_pri/paulshaclaw/paulshaclaw/memory/dream/
```

Expected: 無輸出。

- [ ] **Step 6: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/tests/test_dream_systemd_template.py \
        paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh \
        paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service
git commit -m "fix(memory): #175 dream systemd 範本改 pin --promoter llm 並註記 identity 樣板風險"
```

---

## Task 4: 回歸與收尾

- [ ] **Step 1: 全套本機回歸**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q`
Expected: **773 passed, 1 skipped**，無 failed。

- [ ] **Step 2: CI 等效指令**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && python -m pytest tests/ paulshaclaw/memory/tests/ -q`
Expected: 全綠（含 repo 頂層 `tests/`）。

- [ ] **Step 3: boundary 自查**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && git diff --name-only main...HEAD`
Expected: 僅出現 Boundary 白名單檔案（+ openspec change 目錄與本 plan 若由同分支攜帶）；**不得**出現 `.github/workflows/**`、`scripts/start.sh`、`atomizer/config.py`、`atomizer/cli.py`、`pipeline.py`。

- [ ] **Step 4: 回填 OpenSpec tasks**

勾選 `openspec/changes/stage2-promoter-default-llm/tasks.md` 全部項目並回填 Verification Summary（測試輸出、grep 殘留檢查結果）。

---

## Deployment/Ops notes（不屬本 PR 的動作）

- **無部署動作**：`dream-idle-wrapper.sh` 與 `paulsha-memory-dream.service` 是 repo 內範本；systemd dream timer **現未安裝**（`systemctl --user list-timers` 無 dream 單元），merge 後不需要任何主機操作。
- **生產不受影響**：現行 dream loop 由 `scripts/start.sh:195-196` 以顯式 `--promoter llm` 跑，無需重啟 daemon。
- **Ops 認知**：merge 後任何人手動跑 `memory atomize` / `memory dream run` 未帶 `--promoter`，會實際呼叫 `scripts/claude-gemma4`（本機 vLLM :8001）；backend 離線時走 fail-closed（PromoteError → session left in split，`pipeline.py:407-409`），可重試、不寫壞資料。若要 deterministic 離線跑，顯式 `--promoter identity`。
- 本 change **不含** hooks/*，不涉及 install.sh 複製部署。

## Delivery（分支 / commit / PR 政策）

- 分支：`feature/175-stage2-promoter-default-llm`（自 `main` 切出；R-12：head 必須 `feature/<slug>`）。
- Commit：conventional、zh-TW（如上各 Task 的 commit 訊息）。
- PR title：conventional（R-10），例：`feat(memory): atomizer 預設 promoter 改 llm，關閉 identity 樣板入口`。
- PR body：zh-TW，必含 `Closes #175`（R-17 closing keyword）；**不得有未勾選 checkbox**（R-11）——不要把 tasks checklist 原樣貼進 body。
- 不碰 `.github/workflows/**` 與任何 `policy_version`（R-20）。
- 完成後 push 並開 PR，**不 merge**（等 CI 綠與人工審）。
- R-18（docs 對齊，WARN 不擋 merge）：`paulshaclaw/memory/routing.md:58` 描述的是顯式 `--promoter llm` 路徑，預設翻轉後仍正確，無需同步；若 Policy Check 出 WARN 屬純 config 預設切換，可上 `policy-exempt:docs-sync`。

---

## Self-Review

- **Spec coverage**：Requirement「出貨預設 llm / 未帶旗標不落 identity / 顯式 identity 保留 / 缺 key fail-safe」→ Task 1+2；「排程範本 pin llm + 註記風險」→ Task 3。全覆蓋。
- **Issue 驗收對齊**：#175 驗收「config 預設值為 llm」「未帶 --promoter 的 CLI 路徑不再走 IdentityPromoter」「pytest 全綠」→ Task 1/2/4。
- **Placeholder scan**：各 step 均含完整 code/指令/預期輸出，無 TODO/TBD。
- **一致性**：`load_config(override_path=None)`、`_build_promoter(args, cfg, memory_root)`、`Namespace(promoter=..., agent_command=None)`、期望數字 769→773 全文一致。
