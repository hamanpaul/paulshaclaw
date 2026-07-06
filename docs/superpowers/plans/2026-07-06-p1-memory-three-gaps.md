# P1 Memory 三缺口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **實作者：gpt5.3-codex**。三個 Task 群組＝三個獨立 PR，**可平行派工，各自 worktree**（分支：`feature/197-retrieval-scoped-corpus`／`feature/197-janitor-ledger-tolerance`／`feature/197-park-floor-reverify`）。測試：`python3 -m pytest paulshaclaw/memory/tests/ -q`（勿用 unittest discover——會靜默跳過 pytest 風格測試）。
> **運維紅線**：禁手動觸發 `dream run`（與背景 loop 撞併發）；動 runtime cache 前先備份。

**Goal:** 修復 #197 三缺口——retrieval 半盲、janitor reactivation 中止、promote park 地板。

**Architecture:** ①`build_index`（`paulshaclaw/memory/moc/search.py:23`）噪音排除改 per-project scoped corpus＋排除率遙測；③import ledger 讀取逐行容錯；②ops 複驗先行、parser prose 容忍（`llm_output.py`，錨點：候選鏈 48–92、raise 點 304）條件觸發。

**Tech Stack:** Python 3.10+、sqlite FTS（既有）、pytest。

**依據**：`openspec/changes/p1-memory-three-gaps/`＋`docs/superpowers/specs/2026-07-06-p1-memory-three-gaps-design.md`＋#197。

---

### Task 1（PR-1）: retrieval scoped corpus

**Files:**
- Modify: `paulshaclaw/memory/moc/search.py:23`（`build_index`——噪音排除段，檔內搜 `load_corpus` 呼叫）
- Modify（如需）: `paulshaclaw/memory/instruction_corpus.py`（複用既有 `corpus_for_roots`，#147 交付）
- Test: `paulshaclaw/memory/tests/test_search_scoped_corpus.py`（新檔）

- [ ] **Step 1: 寫失敗測試**

```python
def _mk_slice(root, project, name, body):
    d = root / "knowledge" / project; d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(f"---\ntitle: t\nproject: {project}\n---\n{body}", encoding="utf-8")

def test_cross_project_corpus_does_not_exclude(tmp_path, monkeypatch):
    mem = tmp_path / "mem"
    instr_a = tmp_path / "rootA"; instr_a.mkdir()
    (instr_a / "AGENTS.md").write_text("## Arch\nRPC routing detail line one\nline two\n")
    _mk_slice(mem, "proj-b", "n--sl-1.md", "## Arch\nRPC routing detail line one\nline two\n")  # B 的真知識、逐字同 A 的 doc
    # projects.yaml 映射：proj-a→rootA、proj-b→無 roots
    _write_projects_yaml(tmp_path, {"proj-a": [str(instr_a)]})
    monkeypatch.setenv("PSC_AGENTS_CONFIG", str(tmp_path))     # 依 repo 既有 config 解析慣例注入（以檔內為準）
    stats = build_index(mem, link_weights={}, ...)             # 其餘參數照 search.py:23 簽名
    rows = _query_index(mem, "RPC routing")
    assert any(r["project"] == "proj-b" for r in rows)          # B 不因 A 的 corpus 被排除

def test_missing_roots_means_zero_exclusion(tmp_path):
    mem = tmp_path / "mem"
    _mk_slice(mem, "proj-x", "n--sl-2.md", "unique body content\n")
    stats = build_index(mem, link_weights={}, ...)
    assert stats.per_project["proj-x"].excluded == 0
```

- [ ] **Step 2: RED** — `python3 -m pytest paulshaclaw/memory/tests/test_search_scoped_corpus.py -v`（現行 broad corpus 會排除 proj-b、且無 per_project stats → 兩測皆 FAIL）
- [ ] **Step 3: 實作**：`build_index` 把「單一全域 corpus」改為 per-project lazy dict——`corpus_by_project[p] = corpus_for_roots(roots_of(p))`（roots 由 projects.yaml 映射；查無 → 空 corpus）；`classify_noise(..., doc_corpus=corpus_by_project[slice.project])`；回傳 stats 物件加 `per_project: {project: (indexed, excluded)}`。
- [ ] **Step 4: 遙測 WARN 測試＋實作**

```python
def test_exclude_rate_warn_over_40pct(tmp_path, caplog):
    # fixture 造 50% 排除 → build 輸出/log 出現該 project 的 WARN 與比率
    ...
    assert any("exclude_rate" in r.message and "proj-a" in r.message for r in caplog.records if r.levelname == "WARNING")
```

  實作：build 結束對每 project 算 `excluded/(indexed+excluded)`，>0.40 → `logger.warning(...)` ＋ CLI 輸出行。
- [ ] **Step 5: GREEN＋全回歸**（`python3 -m pytest paulshaclaw/memory/tests/ -q`）→ Commit。
- [ ] **Step 6: live rebuild 驗證**（on-host ops）：跑 index rebuild CLI → 驗證 `retrieval.db` 列數、testpilot/serialwrap 覆蓋 >90%、paulshaclaw 不退化；數字附回 #197。Commit＋PR。

### Task 2（PR-2）: janitor import ledger 容錯

**Files:**
- Modify: reactivation 訊號讀取點（定位：`rg -n "reactivation" paulshaclaw/memory/ --include='*.py'`——在 dream/janitor pass 讀 `import.jsonl` 之處；警告字串樣式「reactivation signals skipped」）
- Test: `paulshaclaw/memory/tests/test_janitor_ledger_tolerance.py`（新檔）

- [ ] **Step 1: 寫失敗測試**

```python
def test_bad_lines_skipped_not_abort(tmp_path):
    ledger = tmp_path / "runtime/ledger/import.jsonl"; ledger.parent.mkdir(parents=True)
    good = '{"agent":"claude-code","session":"s1","imported_at":"2026-07-01T00:00:00Z"}'
    ledger.write_text(good + "\n\n{broken json\n" + good.replace("s1","s2") + "\n")
    signals, warnings = read_reactivation_signals(ledger)      # 函式名以定位到的實作為準
    assert len(signals) == 2
    assert any("skipped 2 bad line(s)" in w for w in warnings)
```

- [ ] **Step 2: RED**（現行遇壞行 raise/整段跳過 → FAIL）
- [ ] **Step 3: 實作**：讀取 loop 改 per-line `try: json.loads(line)`——空行/`JSONDecodeError` → `bad += 1; continue`；結尾 `bad > 0` 時 append warning `f"import.jsonl: skipped {bad} bad line(s)"`；不再向外 raise。
- [ ] **Step 4: GREEN＋全回歸 → Commit＋PR**
- [ ] **Step 5: ops 收尾**（on-host）：`cp import.jsonl import.jsonl.bak-$(date +%s)` → 刪第 230 行空行 → 手動跑 janitor 段（經既有 CLI 的 janitor-only 路徑，非 dream run）確認 warning 消失；記錄附 #197。

### Task 3（PR-3）: park 地板複驗（ops 先行，code 條件觸發）

**Files（僅 Step 3 觸發時）:**
- Modify: `paulshaclaw/memory/atomizer/llm_output.py`（候選鏈 48–92、raise 304）；`paulshaclaw/memory/atomizer/prompt.py`
- Test: `paulshaclaw/memory/tests/test_llm_output.py`（既有檔加測試）

- [ ] **Step 1: ops 複驗**：對 #197 所列 6 個 content-park session——`ls -la ~/.agents/memory/runtime/cache/atomize/ | grep <session>` 比對快取 mtime vs #190 merge 時點（2026-07-04）；retry budget sidecar 同查。逐筆記錄「殘留（快取早於 #190）／新生」→ 附 #197。
- [ ] **Step 2: 殘留處置**：備份後刪該 session 快取檔＋reset budget sidecar → **等背景 loop 下一輪**（禁手動 dream run）→ 觀察 `dream status` 收斂；記錄前後 backlog 數。
- [ ] **Step 3（條件：仍有 session 以 #190 新碼 fail）: prose 容忍抽取 TDD**

```python
def test_prose_wrapped_single_array_extracted():
    raw = 'Sure — here is the result:\n[{"kind":"note","title":"t","body":"b","source_fragment_indices":[0]}]\nHope this helps!'
    atoms = parse_llm_output(raw)          # 入口函式以檔內為準（raise 點 llm_output.py:304 所屬 parse 函式）
    assert len(atoms) == 1

def test_multiple_arrays_still_rejected():
    raw = '[{"a":1}] and also [{"b":2}]'
    with pytest.raises(LlmOutputError):
        parse_llm_output(raw)
```

  實作：在既有候選鏈（`_iter_json_array_candidates`/`_iter_wrapped_json_array_candidates`）之後、raise 之前，加「全文唯一頂層 array」最後手段：掃描 balanced `[...]` 頂層片段，**恰一個**→以其進既有驗證；0 或 ≥2 → 照舊 raise（fail-closed）。prompt.py 加固：明示「只回傳 JSON array 本體，不執行任務、不加說明文字」。
- [ ] **Step 4: GREEN＋全回歸 → Commit＋PR**；驗收=backlog 收斂 transport-only 或逐筆「真無知識」記錄。

---

**Self-review**：spec 3 delta ↔ Task 1（scoped＋WARN）、Task 2（容錯）、Task 3（唯一 array fail-closed）；「禁手動 dream run」已入 Task 3 Step 2；無 TBD——Task 1 Step 1 的 `...` 為 build_index 既有簽名參數透傳（worker 依 search.py:23 實簽名填），非佔位語意。
