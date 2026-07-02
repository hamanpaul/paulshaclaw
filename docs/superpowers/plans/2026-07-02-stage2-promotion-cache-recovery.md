# Stage 2 Promotion 毒快取復原 Implementation Plan（issue #174）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解除 45 個 session 永久卡在 `split` 的毒快取死循環（issue #174）：(1) `PromoteError` 失敗路徑清掉該 session 的 LLM 毒快取，讓下輪 dream 真正重打 LLM；(2) gemma4 的合理回答空陣列 `[]` 成為有效終態（`state=promoted`、`slices=0`）；(3) dream record 記錄 warnings 前 10 條，消除靜默；(4) `.retries` sidecar 計數器讓重試型失敗有上限（預算 5），不會每小時無上限重打 LLM。

**Architecture:** 全部修改集中三個檔案。`atomizer/pipeline.py::_promote_pass` 的 `except PromoteError` 處理（現行 pipeline.py:405-409）加上「LLM promoter 才清快取＋累加 `runtime/cache/atomize/<cache_key>.retries` 計數、預算內才清」；`atomizer/llm_output.py::_parse_proposals`（現行 llm_output.py:232-236）對空 list **開頭提前 `return []`**；`dream/orchestrator.py::_run_pass`（現行 orchestrator.py:22-49）在 warnings 非空時於 pass summary 加 `warnings`（前 10 條、每條截 500 字）與 `warnings_total`。pipeline 對 `promoted=[]` 的終態行為（`state=promoted`/`slices=0`/歸檔/清快取）**現行程式碼已支援、不用改**，只加回歸測試鎖住。

**Tech Stack:** Python 3.12、pytest（repo 測試混 unittest 與 pytest 風格，一律用 pytest 跑，**勿用 `unittest discover`**——會靜默跳過 pytest 風格測試）。

**Spec:** OpenSpec change `openspec/changes/stage2-promotion-cache-recovery/`（proposal / design / specs/stage2-memory-governance / tasks）｜issue #174

## PR #179 review-fix addendum

- `.retries` 僅計 **content attempts**：只有失敗時快取 `.json` 已存在（代表 LLM 實際輸出已落盤）才累加；`AgentExecError` 類 transport 失敗不計數，warning 需明講 `transport failure / no cache written / retry budget unchanged`。
- `dry_run=True` 時 `_promote_pass` 直接停在 preview 路徑，不得 fall-through 進 live split backlog 迴圈；既有 split session 的快取、`.retries` 與底層 agent 呼叫數都必須維持不變。

---

## Boundary（可改檔案白名單）

只允許修改以下檔案，超出即停（scope violation，先回報再說）：

- `paulshaclaw/memory/atomizer/pipeline.py`
- `paulshaclaw/memory/atomizer/llm_output.py`
- `paulshaclaw/memory/dream/orchestrator.py`
- `paulshaclaw/memory/tests/test_atomizer_pipeline.py`
- `paulshaclaw/memory/tests/test_llm_output.py`
- `paulshaclaw/memory/tests/test_llm_promoter.py`
- `paulshaclaw/memory/tests/test_dream_orchestrator.py`
- `openspec/changes/stage2-promotion-cache-recovery/tasks.md`（僅勾 checkbox 與填 Verification Summary）

**明確禁止**：`agent_exec.py`（不做 validate-before-write）、`atomizer.yaml`、`.github/workflows/**`、任何 `policy_version`、hooks 腳本、`~/.agents/**` 實際 runtime 資料。

---

## File Structure

- Modify: `paulshaclaw/memory/atomizer/pipeline.py` — `_promote_pass` 的 `except PromoteError` 處理（:405-409）；新增模組層 `_LLM_PROMOTE_MAX_RETRIES` / `_retry_counter_path` / `_clear_retry_counter` / `_record_promote_failure`（放在 `_clear_cache_key`（:83-95）之後）；成功路徑（:381 與 :498）補清 `.retries` sidecar。
- Modify: `paulshaclaw/memory/atomizer/llm_output.py` — `_parse_proposals`（:232-236）空 list 提前 `return []`。
- Modify: `paulshaclaw/memory/dream/orchestrator.py` — `_run_pass`（:22-49）warnings 入 record；新增 `_WARNINGS_RECORDED_MAX = 10`、`_WARNING_TEXT_MAX_CHARS = 500`。
- Test (modify): `paulshaclaw/memory/tests/test_atomizer_pipeline.py`（新增 1 個 class + 取代 1 個既有測試）、`test_llm_output.py`（取代 1 個 + 新增 2 個）、`test_llm_promoter.py`（取代 1 個）、`test_dream_orchestrator.py`（新增 4 個）。
- 不新增任何 production 檔案。

測試指令（本機，一律絕對路徑；若在 git worktree 執行，將 `/home/paul_chen/prj_pri/paulshaclaw` 替換為該 worktree 的絕對路徑，其餘不變）：

```bash
cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/ -q
```

CI 等效指令：`python -m pytest tests/ paulshaclaw/memory/tests/ -q`

---

## 背景（worker 必讀，5 行版）

dream loop 每小時以 `--promoter llm` 跑 atomize。`CachingAgentClient.run_cached`（agent_exec.py:83-95）在任何驗證**之前**就把 gemma4 raw 輸出寫進 `runtime/cache/atomize/<cache_key>.json`；cache key = `<agent>:<session>__<sha256(fragments)>`（llm_promoter.py:47-52），對卡住的 session 跨輪穩定。pipeline 的 `PromoteError` 路徑（pipeline.py:405-409）只 append warning 就 `continue`、從不清快取（`_clear_cache_key` 只在成功路徑 :381/:498 被呼叫；`LLMPromoter.clear_cache_for_fragments`（llm_promoter.py:66-69）目前**零呼叫者**）→ 首輪壞輸出每小時確定性重放、session 永卡 `split`。45 個積壓中 26 個是 gemma4 合理回答 `[]`，卻被 `_parse_proposals`（llm_output.py:235-236）當硬錯誤。`dream/orchestrator.py::_run_pass`（:36-49）丟棄 warnings 文字，整個失效在 dream.jsonl 完全靜默。

---

## Task 1: PromoteError 路徑清毒快取

**Files:**
- Test: `paulshaclaw/memory/tests/test_atomizer_pipeline.py`
- Modify: `paulshaclaw/memory/atomizer/pipeline.py`

- [ ] **Step 1: Write the failing tests**

在 `test_atomizer_pipeline.py` 模組層（`class PipelineTests` 之前、`ExplodingPromoter` 之後）新增：

```python
class ScriptedAgentClient(agent_exec.AgentClient):
    """依序回傳 outputs（超出後回傳最後一個），並記錄實際被呼叫次數。"""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls = 0

    def run(self, prompt: str) -> str:
        output = self._outputs[min(self.calls, len(self._outputs) - 1)]
        self.calls += 1
        return output


_VALID_ONE_SLICE = (
    '[{"title":"alpha","artifact_kind":"report","project":"paulshaclaw","tags":[],'
    '"body":"body a","source_fragment_indices":[0,1],"relations":[]}]'
)
```

在檔案尾端（`ReimportOverwriteTests` 之後、`if __name__` 之前）新增 class：

```python
class PromoteFailureCacheRecoveryTests(unittest.TestCase):
    """#174: PromoteError 路徑必須清掉毒快取，session 才不會永卡 split。"""

    def _cached_llm_promoter(self, root: Path, outputs: list[str]):
        inner = ScriptedAgentClient(outputs)
        cached = agent_exec.CachingAgentClient(
            inner, root / "runtime" / "cache" / "atomize")
        promoter = llm_promoter.LLMPromoter(
            cached, skill_text="RECOVERY-SKILL",
            known_projects=["paulshaclaw"], model="fake-llm")
        return inner, promoter

    def test_promote_error_clears_poisoned_cache(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            inner, promoter = self._cached_llm_promoter(root, ["chatter, not json"])
            result = pipeline.run(root, config=cfg, config_hash=h,
                                  now="2026-07-02T03:00:00Z", promoter=promoter)
            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            self.assertTrue(any("left in split" in w for w in result["warnings"]))
            # 核心主張：毒快取已清除，不會留給下一輪重放
            self.assertEqual(
                list((root / "runtime" / "cache" / "atomize").glob("*.json")), [])

    def test_promote_retry_reinvokes_llm_and_recovers(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            inner, promoter = self._cached_llm_promoter(
                root, ["chatter, not json", _VALID_ONE_SLICE])
            pipeline.run(root, config=cfg, config_hash=h,
                         now="2026-07-02T03:00:00Z", promoter=promoter)
            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            result2 = pipeline.run(root, config=cfg, config_hash=h,
                                   now="2026-07-02T04:00:00Z", promoter=promoter)
            # 修復前：第二輪重放毒快取（inner.calls 停在 1）、session 永卡 split
            self.assertEqual(inner.calls, 2)
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")
            self.assertEqual(result2["summary"]["slices"], 1)

    def test_non_llm_promoter_failure_does_not_touch_cache_dir(self):
        # 守門測試（實作前後皆須綠）：isinstance 守衛，identity/其他 promoter 失敗不碰快取
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            cache_dir = root / "runtime" / "cache" / "atomize"
            cache_dir.mkdir(parents=True)
            sentinel = cache_dir / "keep.json"
            sentinel.write_text("keep", encoding="utf-8")
            pipeline.run(root, config=cfg, config_hash=h,
                         now="2026-07-02T03:00:00Z",
                         promoter=ExplodingPromoter(fail_session="s1"))
            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            self.assertTrue(sentinel.exists())
            self.assertEqual(sorted(p.name for p in cache_dir.iterdir()), ["keep.json"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/test_atomizer_pipeline.py -q -k "PromoteFailureCacheRecovery"`

Expected: `test_promote_error_clears_poisoned_cache` FAIL（毒快取 `.json` 仍存在）、`test_promote_retry_reinvokes_llm_and_recovers` FAIL（`inner.calls == 1`、state 仍 split）；`test_non_llm_promoter_failure_does_not_touch_cache_dir` PASS（守門測試，本來就該綠）。

- [ ] **Step 3: Write minimal implementation**

`paulshaclaw/memory/atomizer/pipeline.py` `_promote_pass` 的非 dry-run `except PromoteError` 處理（現行 :405-409）：

```python
        try:
            promoted = _promote_fragments(promoter, [fragment for _, fragment in fragments], config)
        except PromoteError as exc:
            if isinstance(promoter, LLMPromoter):
                # #174: 失敗路徑清毒快取——cache key = session+fragments hash 跨輪穩定，
                # 不清則每輪 dream 確定性重放同一份壞輸出、session 永卡 split。
                # clear_cache_for_fragments 已自帶「非 CachingAgentClient / 空 list 不動作」守衛。
                promoter.clear_cache_for_fragments([fragment for _, fragment in fragments])
            warnings.append(f"{session_key}: {exc}; session {session_key} left in split")
            continue
```

注意：(a) `LLMPromoter` 已在檔頭 import（:14），不需新 import；(b) dry-run 分支（:348-349）**保持不動**——dry-run 不做任何 mutation；(c) Task 4 會把這段 `isinstance` 內聯清除改為 `_record_promote_failure`，此處先落最小版。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/test_atomizer_pipeline.py -q`

Expected: 全綠（新 3 個 + 既有全部；既有 `test_llm_garbage_leaves_session_split_without_knowledge_files` 等用非 caching `FakeAgentClient`，`clear_cache_for_fragments` 對其 no-op，不受影響）。

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw && git add paulshaclaw/memory/atomizer/pipeline.py paulshaclaw/memory/tests/test_atomizer_pipeline.py && git commit -m "fix(memory): #174 PromoteError 路徑清 LLM 毒快取，下輪真正重打 LLM"
```

---

## Task 2: 空 JSON 陣列成為有效終態（promoted / slices=0）

**Files:**
- Test: `paulshaclaw/memory/tests/test_llm_output.py`、`test_llm_promoter.py`、`test_atomizer_pipeline.py`
- Modify: `paulshaclaw/memory/atomizer/llm_output.py`

- [ ] **Step 1: Write the failing tests（含取代 3 個舊測試）**

(a) `test_llm_output.py`：**刪除** `test_empty_array_raises`（現行 :29-31），原位置改為：

```python
    def test_empty_array_returns_no_proposals(self):
        # #174: gemma4 對無知識 session 的合理回答 [] 是有效結果，不是硬錯誤
        self.assertEqual(llm_output.parse("[]", PROJECTS), [])

    def test_fenced_empty_array_with_reasoning_returns_no_proposals(self):
        # 實際積壓樣態：fenced [] + reasoning 前後綴（audit 26/45 sessions）
        raw = "```json\n[]\n```\n**Reasoning:** The session contains no substantive content."
        self.assertEqual(llm_output.parse(raw, PROJECTS), [])

    def test_all_invalid_proposals_still_raise_no_salvageable(self):
        # 回歸鎖：非空陣列但全部 schema 不合法，仍必須 fail-closed
        with self.assertRaisesRegex(llm_output.LlmOutputError, "no salvageable proposals"):
            llm_output.parse('[{"bogus": 1}]', PROJECTS)
```

(b) `test_llm_promoter.py`：**刪除** `test_empty_output_fails_closed`（現行 :105-107），原位置改為：

```python
    def test_empty_output_returns_no_slices(self):
        # #174: [] 是有效「無可萃取知識」回答，promote 回傳空 list、不 raise
        self.assertEqual(_promoter("[]").promote([_frag(0)], CFG), [])
```

(c) `test_atomizer_pipeline.py`：**刪除** `test_llm_empty_output_leaves_session_split_without_archiving_fragments`（現行 :406-425，位於 `PipelineTests`），原位置改為（pipeline 端**預期不用改程式碼**即可通過——此測試鎖住 `promoted=[]` 的既有終態行為）：

```python
    def test_llm_empty_output_reaches_promoted_terminal_state(self):
        # #174 回歸鎖：promoted=[] → state=promoted / slices=0 / 歸檔 / 清快取（pipeline 不需改碼）
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            cache_dir = root / "runtime" / "cache" / "atomize"
            cached_client = agent_exec.CachingAgentClient(FakeAgentClient("[]"), cache_dir)
            promoter = llm_promoter.LLMPromoter(
                cached_client, skill_text="EMPTY-SKILL",
                known_projects=["paulshaclaw"], model="fake-llm")
            result = pipeline.run(root, config=cfg, config_hash=h,
                                  now="2026-07-02T03:00:00Z", promoter=promoter)
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")
            event = processing.read_events(root)[-1]
            self.assertEqual(event["state"], "promoted")
            self.assertEqual(event["slices"], 0)
            self.assertEqual(result["summary"]["slices"], 0)
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])
            self.assertEqual(list((root / "inbox" / "_slices").rglob("*.md")), [])
            self.assertEqual(len(list((root / "archive" / "fragments").rglob("*.md"))), 2)
            self.assertEqual(list(cache_dir.glob("*.json")), [])
            self.assertFalse(any("left in split" in w for w in result["warnings"]))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/test_llm_output.py paulshaclaw/memory/tests/test_llm_promoter.py -q ; PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/test_atomizer_pipeline.py -q -k "empty_output_reaches_promoted"`

（兩段 pytest 之間刻意用 `;` 不用 `&&`——RED 階段第一段必然失敗，用 `&&` 會讓第二段永遠不執行、看不到 pipeline 測試的 RED。）

Expected: FAIL — `LlmOutputError: agent output must be a non-empty JSON array`（前兩檔）；pipeline 測試 state 為 `split` ≠ `promoted`。

- [ ] **Step 3: Write minimal implementation**

`paulshaclaw/memory/atomizer/llm_output.py` `_parse_proposals` 開頭（現行 :232-236）改為：

```python
def _parse_proposals(data: Any, known_projects: list[str]) -> list[SliceProposal]:
    if not isinstance(data, list):
        raise LlmOutputError("agent output must be a JSON array")
    if not data:
        # #174: gemma4 對 metadata-only session 的正確回答是空陣列——有效「無知識」
        # 終態，交由 pipeline 走 promoted/slices=0。必須在此提前 return：若只移除
        # non-empty 檢查，data=[] 會空跑下方迴圈後落到 "no salvageable proposals"
        # 照樣 raise（audit VERIFY correction #5）。
        return []
```

（即：刪除原 `raise LlmOutputError("agent output must be a non-empty JSON array")`，改成上述提前 return。函式其餘部分不動——`no salvageable proposals` 的 raise（:249-250）必須保留。）

**已知且接受的行為變化**（design.md 有記載，勿「順手修」）：raw 同時含空陣列與非空合法陣列時，舊行為回傳非空那個，新行為 raise `multiple valid JSON arrays`——極罕見、且 Task 1 已讓它可重試而非永卡。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/test_llm_output.py paulshaclaw/memory/tests/test_llm_promoter.py paulshaclaw/memory/tests/test_atomizer_pipeline.py -q`

Expected: 全綠。

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw && git add paulshaclaw/memory/atomizer/llm_output.py paulshaclaw/memory/tests/test_llm_output.py paulshaclaw/memory/tests/test_llm_promoter.py paulshaclaw/memory/tests/test_atomizer_pipeline.py && git commit -m "fix(memory): #174 空 JSON 陣列改為有效終態（promoted/slices=0），不再 fail-closed"
```

---

## Task 3: dream record 記錄 warnings（消除靜默）

**Files:**
- Test: `paulshaclaw/memory/tests/test_dream_orchestrator.py`
- Modify: `paulshaclaw/memory/dream/orchestrator.py`

- [ ] **Step 1: Write the failing tests**

加到 `test_dream_orchestrator.py` 的 `TestDreamOrchestrator` class 內：

```python
    def test_pass_warnings_are_recorded_in_dream_record(self):
        # #174: 失敗原因文字必須進 dream ledger，不能只剩 skipped 計數
        warning_text = "claude:s1: llm promote failed: x; session claude:s1 left in split"

        def atomize_fn():
            return {"summary": {"skipped": 1}, "warnings": [warning_text]}

        def janitor_fn():
            return {"summary": {"skipped": 0}, "warnings": []}

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            orchestrator.run_dream(root, atomize_fn=atomize_fn, janitor_fn=janitor_fn,
                                   now="2026-07-02T00:00:00Z", config_hash="cfg")
            record = dream.last_run(root)
            self.assertEqual(record["status"], "partial")
            atomize = record["passes"]["atomize"]
            self.assertEqual(atomize["warnings"], [warning_text])
            self.assertEqual(atomize["warnings_total"], 1)
            # 無 warnings 的 pass 不得出現新 key（鎖既有 record 形狀）
            self.assertEqual(record["passes"]["janitor"], {"skipped": 0})

    def test_pass_warnings_overflow_truncated_but_counted(self):
        all_warnings = [f"w{i}" for i in range(45)]

        def atomize_fn():
            return {"summary": {"skipped": 45}, "warnings": list(all_warnings)}

        def janitor_fn():
            return {"summary": {"skipped": 0}, "warnings": []}

        with TemporaryDirectory() as tmpdir:
            record = orchestrator.run_dream(
                Path(tmpdir), atomize_fn=atomize_fn, janitor_fn=janitor_fn,
                now="2026-07-02T00:00:00Z", config_hash="cfg")
            atomize = record["passes"]["atomize"]
            self.assertEqual(atomize["warnings"], all_warnings[:10])
            self.assertEqual(atomize["warnings_total"], 45)

    def test_long_warning_strings_are_truncated(self):
        def atomize_fn():
            return {"summary": {"skipped": 1}, "warnings": ["x" * 2000]}

        def janitor_fn():
            return {"summary": {"skipped": 0}, "warnings": []}

        with TemporaryDirectory() as tmpdir:
            record = orchestrator.run_dream(
                Path(tmpdir), atomize_fn=atomize_fn, janitor_fn=janitor_fn,
                now="2026-07-02T00:00:00Z", config_hash="cfg")
            self.assertEqual(record["passes"]["atomize"]["warnings"], ["x" * 500])

    def test_summary_dict_is_not_mutated_by_warning_recording(self):
        source_summary = {"skipped": 1}

        def atomize_fn():
            return {"summary": source_summary, "warnings": ["warn"]}

        def janitor_fn():
            return {"summary": {"skipped": 0}, "warnings": []}

        with TemporaryDirectory() as tmpdir:
            orchestrator.run_dream(
                Path(tmpdir), atomize_fn=atomize_fn, janitor_fn=janitor_fn,
                now="2026-07-02T00:00:00Z", config_hash="cfg")
            self.assertNotIn("warnings", source_summary)
            self.assertNotIn("warnings_total", source_summary)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/test_dream_orchestrator.py -q`

Expected: 新 4 個 FAIL（`KeyError: 'warnings'` / `'warnings_total'`）；既有測試綠。

- [ ] **Step 3: Write minimal implementation**

`paulshaclaw/memory/dream/orchestrator.py`：模組層（`_error_category` 之前）加常數：

```python
_WARNINGS_RECORDED_MAX = 10
_WARNING_TEXT_MAX_CHARS = 500
```

`_run_pass` 內（現行 :36-46），在 `passes[name] = summary` 之前插入：

```python
    if isinstance(warnings, list) and warnings:
        # #174: 失敗原因進 ledger（有上限，避免 record 膨脹）。warning 文字來自
        # pipeline/janitor/moc 的例外類別與 schema 訊息，不含 raw prompt / LLM 原文，
        # 維持既有 redaction 性質（test_failure_record_redacts_exception_message）。
        summary = dict(summary)
        summary["warnings"] = [
            str(warning)[:_WARNING_TEXT_MAX_CHARS]
            for warning in warnings[:_WARNINGS_RECORDED_MAX]
        ]
        summary["warnings_total"] = len(warnings)

    passes[name] = summary
```

其餘（`clean` 的計算、回傳值）不動。warnings 為空時**不加任何 key**——既有測試以 dict 完全相等斷言 clean pass 形狀。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/test_dream_orchestrator.py paulshaclaw/memory/tests/test_dream_cli.py paulshaclaw/memory/tests/test_dream_cli_moc_warnings.py paulshaclaw/memory/tests/test_dream_e2e.py -q`

Expected: 全綠（dream cli/e2e 測試只用 `assertIn` 檢查 passes，容忍新 key）。

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw && git add paulshaclaw/memory/dream/orchestrator.py paulshaclaw/memory/tests/test_dream_orchestrator.py && git commit -m "feat(memory): #174 dream record 記錄 pass warnings 前 10 條與總數"
```

---

## Task 4: bounded retry（`.retries` sidecar，預算 5）

**Files:**
- Test: `paulshaclaw/memory/tests/test_atomizer_pipeline.py`
- Modify: `paulshaclaw/memory/atomizer/pipeline.py`

- [ ] **Step 1: Write the failing tests**

加到 Task 1 的 `PromoteFailureCacheRecoveryTests` class 內：

```python
    def _split_and_cache_key(self, root: Path, cfg, h) -> str:
        split_warnings: list[str] = []
        pipeline._split_pass(root, cfg, h, "2026-07-02T02:00:00Z", False, split_warnings)
        fragments = [pipeline._read_fragment(p)
                     for p in sorted((root / "inbox" / "_slices").rglob("*.md"))]
        fragments = [f for f in fragments if f is not None]
        return llm_promoter.LLMPromoter.cache_key_for_fragments(fragments)

    def test_retry_counter_increments_and_cache_cleared_within_budget(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            inner, promoter = self._cached_llm_promoter(root, ["chatter, not json"])
            pipeline.run(root, config=cfg, config_hash=h,
                         now="2026-07-02T03:00:00Z", promoter=promoter)
            cache_dir = root / "runtime" / "cache" / "atomize"
            retries = list(cache_dir.glob("*.retries"))
            self.assertEqual(len(retries), 1)
            self.assertEqual(retries[0].read_text(encoding="utf-8").strip(), "1")
            # 預算內：毒快取仍要清（下一輪重打 LLM）
            self.assertEqual(list(cache_dir.glob("*.json")), [])

    def test_exhausted_budget_retains_poisoned_cache_and_stops_llm_calls(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            cache_dir = root / "runtime" / "cache" / "atomize"
            cache_dir.mkdir(parents=True)
            cache_key = self._split_and_cache_key(root, cfg, h)
            (cache_dir / f"{cache_key}.retries").write_text("5", encoding="utf-8")
            inner, promoter = self._cached_llm_promoter(root, ["chatter, not json"])

            result = pipeline.run(root, config=cfg, config_hash=h,
                                  now="2026-07-02T04:00:00Z", promoter=promoter)
            # 第 6 次失敗：超出預算 → 計數 6、毒快取保留（parking）
            self.assertEqual(inner.calls, 1)
            self.assertEqual(
                (cache_dir / f"{cache_key}.retries").read_text(encoding="utf-8").strip(), "6")
            self.assertEqual(len(list(cache_dir.glob("*.json"))), 1)
            self.assertTrue(any("retry budget exhausted" in w for w in result["warnings"]))

            # 下一輪：重放快取失敗、不再打 LLM，仍有 warning（可觀測、便宜）
            result2 = pipeline.run(root, config=cfg, config_hash=h,
                                   now="2026-07-02T05:00:00Z", promoter=promoter)
            self.assertEqual(inner.calls, 1)
            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            self.assertTrue(any("left in split" in w for w in result2["warnings"]))

    def test_successful_promotion_removes_retry_sidecar(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            cache_dir = root / "runtime" / "cache" / "atomize"
            cache_dir.mkdir(parents=True)
            cache_key = self._split_and_cache_key(root, cfg, h)
            sidecar = cache_dir / f"{cache_key}.retries"
            sidecar.write_text("3", encoding="utf-8")
            inner, promoter = self._cached_llm_promoter(root, [_VALID_ONE_SLICE])
            result = pipeline.run(root, config=cfg, config_hash=h,
                                  now="2026-07-02T04:00:00Z", promoter=promoter)
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")
            self.assertEqual(result["summary"]["slices"], 1)
            self.assertFalse(sidecar.exists())
            self.assertEqual(list(cache_dir.glob("*.json")), [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/test_atomizer_pipeline.py -q -k "PromoteFailureCacheRecovery"`

Expected: `test_retry_counter_increments...` FAIL（無 `.retries` 檔）；`test_exhausted_budget...` FAIL（Task 1 版無條件清快取 → `*.json` 為 0、run2 的 `inner.calls` 變 2、無 exhausted warning）；`test_successful_promotion_removes_retry_sidecar` FAIL（sidecar 殘留）。

- [ ] **Step 3: Write minimal implementation**

(a) `pipeline.py` 在 `_clear_cache_key`（:83-95）之後新增：

```python
_LLM_PROMOTE_MAX_RETRIES = 5


def _retry_counter_path(memory_root: Path, cache_key: str) -> Path | None:
    """`.retries` sidecar 路徑；沿用 _clear_cache_key 的 cache key 驗證與目錄圈禁。"""
    if not LLMPromoter.is_valid_cache_key(cache_key):
        return None
    cache_root = (memory_root / "runtime" / "cache" / "atomize").resolve()
    candidate = (cache_root / f"{cache_key}.retries").resolve()
    if candidate.parent != cache_root:
        return None
    return candidate


def _clear_retry_counter(memory_root: Path, cache_key: str | None) -> None:
    if not cache_key:
        return
    counter = _retry_counter_path(memory_root, cache_key)
    if counter is None:
        return
    try:
        counter.unlink()
    except FileNotFoundError:
        return


def _record_promote_failure(memory_root: Path, promoter: Promoter,
                            fragments: list[Fragment]) -> str:
    """PromoteError 路徑（#174）：累加重試計數；預算內清毒快取讓下輪重打 LLM，
    超出預算則刻意保留毒快取當便宜 parking（重放 parse 失敗、不再耗 LLM）。
    回傳附註字串（併入 warning 文字）。"""
    if not isinstance(promoter, LLMPromoter) or not fragments:
        return ""
    cache_key = promoter.cache_key_for_fragments(fragments)
    counter = _retry_counter_path(memory_root, cache_key)
    if counter is None:
        return ""
    try:
        attempts = int(counter.read_text(encoding="utf-8").strip() or "0")
    except (FileNotFoundError, ValueError, OSError):
        attempts = 0
    attempts += 1
    counter.parent.mkdir(parents=True, exist_ok=True)
    counter.write_text(str(attempts), encoding="utf-8")
    if attempts <= _LLM_PROMOTE_MAX_RETRIES:
        promoter.clear_cache_for_fragments(fragments)
        return f" (cache cleared; retry {attempts}/{_LLM_PROMOTE_MAX_RETRIES})"
    return f" (retry budget exhausted after {attempts} failures; poisoned cache retained)"
```

(b) 把 Task 1 在 `except PromoteError` 內的 `isinstance` 清除段改為：

```python
        except PromoteError as exc:
            note = _record_promote_failure(
                memory_root, promoter, [fragment for _, fragment in fragments])
            warnings.append(f"{session_key}: {exc}; session {session_key} left in split{note}")
            continue
```

（既有測試斷言皆用 `"left in split" in w` 子字串比對，附註後綴不影響。）

(c) 成功路徑補清 sidecar——兩處各加一行：

- `state == "promoted"` resume 清理（現行 :380-381）：

```python
            cache_key = event.get("cache_key")
            _clear_cache_key(memory_root, cache_key if isinstance(cache_key, str) else None)
            _clear_retry_counter(memory_root, cache_key if isinstance(cache_key, str) else None)
```

- 促升成功尾段（現行 :497-498）：

```python
        _archive_fragments(memory_root, [frag_path for frag_path, _ in fragments], now)
        _clear_cache_key(memory_root, cache_key)
        _clear_retry_counter(memory_root, cache_key)
```

（identity promoter 時 `cache_key` 為 `None`，`_clear_retry_counter` 已守衛。）

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/test_atomizer_pipeline.py -q`

Expected: 全綠（含 Task 1 的三個測試——預算內行為與 Task 1 相同）。

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw && git add paulshaclaw/memory/atomizer/pipeline.py paulshaclaw/memory/tests/test_atomizer_pipeline.py && git commit -m "feat(memory): #174 promote 失敗 bounded retry（.retries sidecar，預算 5，超限保留毒快取 parking）"
```

---

## Task 5: 回歸與收尾

- [ ] **Step 1: 全套本機回歸**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/ -q`

Expected: 全綠、無 error。**勿用 `unittest discover`**（會靜默跳過 pytest 風格函式測試）。

- [ ] **Step 2: CI 等效檢查**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. python -m pytest tests/ paulshaclaw/memory/tests/ -q`

Expected: `paulshaclaw/memory/tests/` 全綠（與 `.github/workflows/tests.yml` 同口徑）。**已知本機環境雜訊（與本 change 無關、動工前的 main 就存在）**：`tests/test_stage11_operator_cockpit.py` 有 2 個測試（`test_on_mount_schedules_pane_and_sysmon_ticks`、`test_refresh_skips_work_list_rebuild_when_content_unchanged`）因本機 textual 版本漂移而失敗——**不要碰它們**（cockpit 檔案不在 Boundary 內），行為以 CI 為準；只要失敗清單完全等於這 2 個既有項目即視為通過本步驟，最終以 PR 的 CI 綠燈裁決。

- [ ] **Step 3: 勾 OpenSpec tasks 與 Verification Summary**

把 `openspec/changes/stage2-promotion-cache-recovery/tasks.md` 各項勾為 `- [x]`，並在檔尾 Verification Summary 填入 Step 1/2 的實際指令與結果摘要。

```bash
cd /home/paul_chen/prj_pri/paulshaclaw && git add openspec/changes/stage2-promotion-cache-recovery/tasks.md && git commit -m "docs(openspec): #174 stage2-promotion-cache-recovery tasks 完成勾選與驗證摘要"
```

- [ ] **Step 4: 依下方 Delivery 段落 push + 開 PR（不 merge）**

---

## Self-Review

- **Spec coverage**：Requirement「Promotion failure clears the poisoned LLM cache」→ Task 1；「Empty proposal output is a terminal promoted state」→ Task 2；「Bounded LLM retry budget」→ Task 4；「Dream record surfaces pass warnings」→ Task 3。四 requirement 全覆蓋，scenario 與測試一一對應。
- **VERIFY corrections 遵循**：空陣列修法採「`_parse_proposals` 開頭提前 `return []`」而非移除 non-empty 檢查（correction #5）；pipeline 對 `promoted=[]` 不改碼、只加回歸鎖（Task 2 測試 c）。
- **Placeholder scan**：每個 Step 均含完整測試碼／實作碼／絕對路徑指令／預期輸出，無 TODO/TBD。
- **Type / naming consistency**：`_record_promote_failure(memory_root, promoter, fragments) -> str`、`_retry_counter_path(...) -> Path | None`、`_clear_retry_counter(...)`、常數 `_LLM_PROMOTE_MAX_RETRIES=5`、`_WARNINGS_RECORDED_MAX=10`、`_WARNING_TEXT_MAX_CHARS=500` 全文一致。
- **既有測試相容性**：orchestrator 只在 warnings 非空時加 key（既有 exact-equality 測試不破）；warning 文字追加後綴不破 `"left in split"` 子字串斷言；非 caching `FakeAgentClient` 路徑 `clear_cache_for_fragments` no-op。

---

## Deployment/Ops notes（不屬於本 PR，實作 task 禁止執行）

**部署**：三個修改檔皆為 package 模組（非 hooks/*），dream loop 以 `PYTHONPATH` 指向 repo working tree 執行（`scripts/start.sh:184-196`）——merge 後在 runtime checkout `git pull --ff-only` 即生效，**不需**重跑 `install.sh`、不需重裝 hooks。

**一次性積壓復原（ops，由使用者或 master agent 於 merge 部署後另行執行）**：修法本身可自癒——部署後第一輪 dream 重放毒快取失敗即清快取（計為 attempt 1），第二輪起真正重打 LLM；其中 26 個空陣列 session 甚至不需清快取（重放 `[]` 直接 parse 成功 → promoted/slices=0）。手動刪快取只是省掉一輪重放。若要加速，先 dry-run 再實刪：

```bash
python3 - <<'PY'
import json
from pathlib import Path
DRY_RUN = True  # 核對清單無誤後改 False 重跑
root = Path.home() / ".agents/memory"
state = {}
for line in (root / "runtime/ledger/processing.jsonl").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue  # ledger 內已知有 1 行損毀 JSON
    state[event["session_key"]] = event.get("state")
stuck = {key for key, value in state.items() if value == "split"}
cache = root / "runtime/cache/atomize"
targets = [f for f in cache.glob("*.json") if f.name.rsplit("__", 1)[0] in stuck]
for f in targets:
    print(("DRY-RUN " if DRY_RUN else "DELETE ") + f.name)
    if not DRY_RUN:
        f.unlink()
print(f"{'would remove' if DRY_RUN else 'removed'} {len(targets)} cache files (expect ~45)")
PY
```

數字明顯偏離預估（~45）就停下回報，不要硬刪（比照 #147 教訓）。

**耗盡預算後的手動重驅**：某 session `.retries` 超過 5 而快取被 parking 後，若想再給機會，刪除該 session 的 `<cache_key>.json` 與 `<cache_key>.retries` 兩檔即可（下輪重打 LLM、預算歸零）。

**觀測**：部署後看 `~/.agents/memory/runtime/ledger/dream.jsonl` 尾筆——`passes.atomize.skipped` 應從 45 下降；`passes.atomize.warnings` 開始出現失敗原因文字；空陣列 session 對應 `processing.jsonl` 出現 `state=promoted, slices=0`。31 個非積壓殘留快取檔的清理屬 janitor follow-up，不在本次範圍。

---

## Delivery（repo 分支/PR 政策）

- **分支**：自 `main` 開 `feature/174-stage2-promotion-cache-recovery`（R-12：head 必須 `feature/<slug>`）。動工前先 `git pull --ff-only`。
- **Commit**：conventional commit、zh-TW 描述（本 plan 各 Task Step 5 已給定文案）。
- **PR**：title conventional（建議 `fix(memory): promotion 毒快取失敗路徑清 cache + 空陣列終態 + dream warnings（#174）`）；body 一律 zh-TW，必含 closing keyword 一行 **`Closes #174`**（R-17）；body **不得有未勾選 checkbox**（R-11，驗收清單請寫成純條列或已勾 `- [x]`）。
- **禁區**：不碰 `.github/workflows/**`、不碰任何 `policy_version`（R-20）、不打 tag（R-07）。
- **完成定義**：CI 綠（`gh pr view --json statusCheckRollup` 全 SUCCESS 判讀）＋ push ＋ 開 PR 為止；**不得自行 merge**（等使用者明確指示）。
- **docs 對齊（R-18, WARN）**：本次為內部 runtime 行為修復，無使用者面 docs 需同步；若 CI 提醒可上 `policy-exempt:docs-sync`。
