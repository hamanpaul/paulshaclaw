# Stage 2 Offer Shortlist 品質 Implementation Plan（#178）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復 offer shortlist 供給品質（issue #178，audit wf_2bd0b606-6e4 offer-read-conversion，CONFIRMED）：(1) generic 標題 artifact（`report-*`/`task-*`/`todo-*`/`overview`/`problem`/`untitled`/`review-summary`，佔 49~55% impressions、零 read）出檢索池；(2) 同 session 已 offer 的 slice 不重複注入（現況同筆最多 32 次）；(3) 注入摘要行不再是標題重複（「[overview] — Overview」）；(4) retitle 掃描擴到 generic 標題，形成「出池→重生標題→回池」閉環。

**Architecture:** title 級純函式 `noise.is_generic_title` 為單一真相源；`pool_exclude_reason`（非刪除級池排除，`moc/search.py:71` 的 `build_index` 既有呼叫點自動生效，**search.py 不改**）新增 `generic-title` 分支；`hooks/_shortlist_common.py` 讀回既有 per-session offered map（`runtime/wakeup/<tool>__<sid>.offered.json` 之 `by_id`，`_record_offered` 本來就在維護）過濾已 offer sl_id、檢索過取（`SHORTLIST_FETCH_K=12`）補位次佳；`_summary(path, title)` 正規化跳過 title echo 行；`retitle.py::_is_untitled` 追加 `is_generic_title` 判定。

**Tech Stack:** Python 3.12、pytest（`~/.local/bin/pytest`；**勿用 `unittest discover`——會靜默跳過 pytest 風格函式測試**）、sqlite FTS5（既有）、既有 `moc.search` / `retrieval` / `noise` 模組。

**Spec:** OpenSpec change `openspec/changes/stage2-offer-shortlist-quality/`（proposal / design / specs / tasks 四件套；design.md D1 記錄「pool_exclude vs link_weight 重罰」取捨）｜Issue: https://github.com/hamanpaul/paulshaclaw/issues/178

---

## Boundary（可改檔案白名單）

實作**只能**修改下列檔案，超出即停手回報（scope violation）：

- `paulshaclaw/memory/noise.py`
- `paulshaclaw/memory/hooks/_shortlist_common.py`
- `paulshaclaw/memory/retitle.py`
- `paulshaclaw/memory/tests/test_noise.py`
- `paulshaclaw/memory/tests/test_moc_search.py`
- `paulshaclaw/memory/tests/test_shortlist_common.py`
- `paulshaclaw/memory/tests/test_retitle.py`
- `openspec/changes/stage2-offer-shortlist-quality/tasks.md`（僅勾選進度）
- `docs/superpowers/plans/2026-07-02-stage2-offer-shortlist-quality.md`（僅勾選進度）

明確**禁改**：`paulshaclaw/memory/moc/search.py`（本方案不需要）、`paulshaclaw/memory/cli.py`、`.github/workflows/**`、`.paul-project.yml`（policy_version）。#177 同批動 memory 模組：`noise.py` 的新增一律放**檔尾獨立區塊**、`pool_exclude_reason` 內只有單一插入點，控制 diff 區塊避免衝突。

## File Structure

- Modify: `paulshaclaw/memory/noise.py` — 檔尾新增 `_GENERIC_EXACT_TITLES` / `_GENERIC_TITLE_PREFIX` / `is_generic_title`；`pool_exclude_reason`（現 :202-216）`return None` 前插一個 if。
- Modify: `paulshaclaw/memory/hooks/_shortlist_common.py` — 加 `import re`、`SHORTLIST_FETCH_K`、`_norm_title_key`、`_offered_map_path`、`_load_offered_ids`；改 `_summary` 簽名與邏輯（現 :16-31）；`build_shortlist_and_record`（現 :84-115）search→過濾→取 K；`_record_offered`（現 :53-81）改用 `_offered_map_path`。
- Modify: `paulshaclaw/memory/retitle.py` — import 行（現 :23）加 `is_generic_title`；`_is_untitled`（現 :28-30）追加 generic 判定；模組 docstring 補一行。
- Test: `paulshaclaw/memory/tests/test_noise.py`、`test_moc_search.py`、`test_shortlist_common.py`、`test_retitle.py`（皆為**追加**，不改既有案例）。

測試指令一律：`cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest <files> -q`（CI 等效：`python -m pytest tests/ paulshaclaw/memory/tests/ -q`）。

---

## Task 1: generic 標題判定 + 池排除（noise.py，含 index 整合驗證）

**Files:**
- Test: `paulshaclaw/memory/tests/test_noise.py`（檔尾追加，`if __name__` 區塊之前）
- Test: `paulshaclaw/memory/tests/test_moc_search.py`（檔尾追加，`if __name__` 區塊之前）
- Modify: `paulshaclaw/memory/noise.py`

- [x] **Step 1: Write the failing tests**

追加到 `paulshaclaw/memory/tests/test_noise.py`（模組層級 pytest 函式，與既有 `test_pool_exclude_reason_review_and_canary` 同風格）：

```python
def test_is_generic_title_hits_and_misses():
    from paulshaclaw.memory.noise import is_generic_title
    # 命中：issue #178 清單（exact；正規化涵蓋大小寫/空白/底線）
    for t in ("overview", "problem", "untitled", "review-summary", "Review Summary",
              "report", "task", "todo", "TODO"):
        assert is_generic_title(t), t
    # 命中：prefix report-/task-/todo-（空白/底線正規化為 -）
    for t in ("report-testpilot", "task-cockpit-swap", "todo_cleanup", "TODO list",
              "Report Testpilot"):
        assert is_generic_title(t), t
    # 不命中：具體標題、僅「包含」generic 詞者、空值
    for t in ("", None, "單一-com0-死因未解", "wi-fi-llapi-test-execution-workflow",
              "overview-of-uart-pinmux", "problem-with-dma-burst",
              "release-v0-2-0-preparation-execution", "todos", "subtask-routing"):
        assert not is_generic_title(t), t


def test_pool_exclude_reason_generic_title():
    from paulshaclaw.memory.noise import pool_exclude_reason
    # title / atom_title 命中 → generic-title（非刪除級出池）
    assert pool_exclude_reason(
        {"artifact_kind": "report", "title": "report-testpilot"}) == "generic-title"
    assert pool_exclude_reason(
        {"artifact_kind": "report", "atom_title": "Overview"}) == "generic-title"
    assert pool_exclude_reason(
        {"artifact_kind": "report", "title": "untitled"}) == "generic-title"
    # session_title generic 不觸發（session 標題非 slice 標題）
    assert pool_exclude_reason(
        {"artifact_kind": "report", "title": "uart2-除錯重點",
         "session_title": "report-testpilot"}) is None
    # 具體標題不出池
    assert pool_exclude_reason(
        {"artifact_kind": "report", "title": "單一-com0-死因未解"}) is None
    # 既有規則優先序不變
    assert pool_exclude_reason(
        {"artifact_kind": "review", "title": "report-x"}) == "review-record"
```

追加到 `paulshaclaw/memory/tests/test_moc_search.py`（模組層級 pytest 函式，與既有 `test_build_index_excludes_noise_and_pool` 同風格）：

```python
def test_build_index_excludes_generic_title(tmp_path):
    from paulshaclaw.memory.moc import search as S
    mr = tmp_path
    k = mr / "knowledge" / "proj"
    k.mkdir(parents=True)
    generic = k / "report-testpilot--sl-gen0000000000.md"
    generic.write_text(
        "---\nmemory_layer: knowledge\nslice_id: sl-gen0000000000\nproject: proj\n"
        "title: report-testpilot\nartifact_kind: report\n"
        "captured_at: '2026-07-01T00:00:00Z'\n---\ntestpilot 測試 報告 內容\n",
        encoding="utf-8")
    (k / "specific.md").write_text(
        "---\nmemory_layer: knowledge\nslice_id: sl-spec000000000\nproject: proj\n"
        "title: com0-斷線根因\nartifact_kind: report\n"
        "captured_at: '2026-07-01T00:00:00Z'\n---\ntestpilot COM0 斷線根因是 udev 權限。\n",
        encoding="utf-8")
    S.build_index(mr, link_weights={})
    ids = {h["slice_id"] for h in S.search(mr, '"testpilot"', project="proj",
                                           limit=10, include_decayed=True)}
    assert "sl-spec000000000" in ids
    assert "sl-gen0000000000" not in ids   # generic-title 出池
    assert generic.exists()                 # 非刪除級：檔案保留、未修改
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_noise.py paulshaclaw/memory/tests/test_moc_search.py -q`
Expected: FAIL — `test_is_generic_title_hits_and_misses` 以 `ImportError: cannot import name 'is_generic_title' from 'paulshaclaw.memory.noise'` 失敗；`test_pool_exclude_reason_generic_title` 因 `pool_exclude_reason` 回傳 `None` 而非 `"generic-title"` 而 assert 失敗（該函式已存在，import 不會失敗）；`test_build_index_excludes_generic_title` 因 `sl-gen0000000000` 出現在檢索結果而 assert 失敗。既有測試全綠。

- [x] **Step 3: Write minimal implementation**

3a. `paulshaclaw/memory/noise.py` 的 `pool_exclude_reason`（現 :202-216）在 `return None` 之前插入單一分支——改後全函式如下：

```python
def pool_exclude_reason(frontmatter: Mapping[str, object]) -> str | None:
    """Frontmatter-level, NON-deletion pool exclusion (canary/review). Returns a
    reason string to keep a slice out of the retrieval pool, or None to keep it.

    Distinct from classify_noise (body-based, deletion-grade): this only hides a
    slice from search/shortlist; the file is never deleted, so the bar is looser.
    """
    kind = str(frontmatter.get("artifact_kind") or "").strip().lower()
    if kind == "review":
        return "review-record"
    blob = " ".join(str(frontmatter.get(k, "")) for k in
                    ("atom_title", "title", "session_title")).lower()
    if kind == "task" and ("canary" in blob or "smoke" in blob):
        return "canary-fixture"
    if any(is_generic_title(frontmatter.get(k)) for k in ("atom_title", "title")):
        return "generic-title"
    return None
```

3b. `paulshaclaw/memory/noise.py` **檔尾**（`pool_exclude_reason` 之後）新增獨立區塊（`re` 已在檔頭 import，勿重複 import）：

```python
# --- generic-title pool exclusion (#178) -------------------------------------
# offer shortlist 品質：generic 標題的 session 產物型 slice（report-*/task-*/todo-*/
# overview/problem/untitled/review-summary）佔 offer impressions 近半數且從未被
# read（audit wf_2bd0b606）。title 級、非刪除級判定：僅出檢索池，檔案保留；
# retitle 重生具體標題後，下次重建 index 自然回池。
_GENERIC_EXACT_TITLES = frozenset({
    "overview", "problem", "untitled", "review-summary", "report", "task", "todo",
})
_GENERIC_TITLE_PREFIX = re.compile(r"^(?:report|task|todo)-")


def is_generic_title(title: object) -> bool:
    """True iff the title is a generic session-artifact label, not a knowledge atom.

    Title-level, NON-deletion signal shared by pool_exclude_reason (retrieval-pool
    exclusion) and the retitle scan (#178). Normalizes case and separators
    (whitespace/underscore -> '-') before matching exact names or report-/task-/
    todo- prefixes; titles that merely CONTAIN these words (e.g.
    'overview-of-uart-pinmux', 'problem-with-dma-burst') are NOT generic.
    Empty/missing titles return False (untitled governance handles those).
    """
    s = str(title or "").strip().lower()
    if not s:
        return False
    s = re.sub(r"[\s_]+", "-", s)
    return s in _GENERIC_EXACT_TITLES or bool(_GENERIC_TITLE_PREFIX.match(s))
```

（`moc/search.py:71` 的 `build_index` 已對每檔呼叫 `pool_exclude_reason`，整合測試不需要改 search.py。）

- [x] **Step 4: Run tests to verify they pass**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_noise.py paulshaclaw/memory/tests/test_moc_search.py -q`
Expected: PASS（新增 3 個測試 + 既有全部）。

- [x] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/noise.py paulshaclaw/memory/tests/test_noise.py paulshaclaw/memory/tests/test_moc_search.py
git commit -m "feat(memory): #178 generic 標題判定與非刪除級池排除（is_generic_title + pool_exclude_reason）"
```

---

## Task 2: session 內去重（hooks/_shortlist_common.py）

**Files:**
- Test: `paulshaclaw/memory/tests/test_shortlist_common.py`（檔尾追加）
- Modify: `paulshaclaw/memory/hooks/_shortlist_common.py`

行為契約：注入前讀回 `runtime/wakeup/<tool>__<sanitize_id(sid)>.offered.json` 的 `by_id` 鍵集合，過濾已 offer 的 `sl_id`；檢索改過取 `SHORTLIST_FETCH_K=12` 筆使過濾後仍能補位到 `SHORTLIST_K`；過濾後為空 → 回 `""`、不注入、**不**追加 offered 記錄（維持既有「未注入不記錄」不變量，`test_shortlist_fails_closed_when_redaction_raises` 已鎖）；map 缺失/損毀 → fail-open 視為空集合（對比：redaction 是 fail-closed，語意不同勿混）。

- [x] **Step 1: Write the failing tests**

追加到 `paulshaclaw/memory/tests/test_shortlist_common.py`：

```python
def _seed_two(mr: Path):
    k = mr / "knowledge" / "proj"
    k.mkdir(parents=True)
    (k / "a.md").write_text(
        "---\nmemory_layer: knowledge\nslice_id: sl-aaaaaaaaaaaaaaaa\nproject: proj\n"
        "title: SerialWrap\ncaptured_at: '2026-06-29T00:00:00Z'\n---\n抽象 UART 執行層\n",
        encoding="utf-8")
    (k / "b.md").write_text(
        "---\nmemory_layer: knowledge\nslice_id: sl-bbbbbbbbbbbbbbbb\nproject: proj\n"
        "title: SerialWrap 重試\ncaptured_at: '2026-06-28T00:00:00Z'\n---\n"
        "SerialWrap 重試機制的 backoff 上限是 5 次。\n",
        encoding="utf-8")
    S.build_index(mr, link_weights={})


def _offered_events(mr: Path) -> list[dict]:
    p = mr / "runtime" / "ledger" / "offered.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_shortlist_session_dedup_next_best_then_exhausted(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "resolve_project", lambda cwd, memory_root: "proj")
    monkeypatch.setattr(SC, "SHORTLIST_K", 1)   # 每次只注入 1 筆，逼出補位行為
    _seed_two(tmp_path)
    out1 = SC.build_shortlist_and_record(tmp_path, "claude-code", "sidD", cwd="/x",
                                         prompt="SerialWrap 執行")
    out2 = SC.build_shortlist_and_record(tmp_path, "claude-code", "sidD", cwd="/x",
                                         prompt="SerialWrap 執行")
    out3 = SC.build_shortlist_and_record(tmp_path, "claude-code", "sidD", cwd="/x",
                                         prompt="SerialWrap 執行")
    assert out1 and out2                        # 前兩次都有注入
    assert out3 == ""                           # 候選枯竭：不注入
    events = _offered_events(tmp_path)
    assert len(events) == 2                     # 第三次不記 offered（分母不灌水）
    ids1 = {o["sl_id"] for o in events[0]["offered"]}
    ids2 = {o["sl_id"] for o in events[1]["offered"]}
    assert len(ids1) == 1 and len(ids2) == 1
    assert ids1 != ids2                         # 第二次補位次佳、不重複
    assert ids1 | ids2 == {"sl-aaaaaaaaaaaaaaaa", "sl-bbbbbbbbbbbbbbbb"}


def test_shortlist_dedup_scoped_to_session(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "resolve_project", lambda cwd, memory_root: "proj")
    monkeypatch.setattr(SC, "SHORTLIST_K", 1)
    _seed_two(tmp_path)
    SC.build_shortlist_and_record(tmp_path, "claude-code", "sidE", cwd="/x",
                                  prompt="SerialWrap 執行")
    out = SC.build_shortlist_and_record(tmp_path, "claude-code", "sidF", cwd="/x",
                                        prompt="SerialWrap 執行")
    assert out                                  # 新 session 不受 sidE 已 offer 影響


def test_shortlist_dedup_fail_open_on_corrupt_map(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "resolve_project", lambda cwd, memory_root: "proj")
    _seed_two(tmp_path)
    wk = tmp_path / "runtime" / "wakeup"
    wk.mkdir(parents=True)
    (wk / "claude-code__sidG.offered.json").write_text("{not-json", encoding="utf-8")
    out = SC.build_shortlist_and_record(tmp_path, "claude-code", "sidG", cwd="/x",
                                        prompt="SerialWrap 執行")
    assert out                                  # 損毀映射 → 視為空集合照常 offer
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_shortlist_common.py -q`
Expected: FAIL — `test_shortlist_session_dedup_next_best_then_exhausted` 於首個失敗斷言 `assert out3 == ""` 失敗（現行每次都重 offer 同一筆最佳命中，`ids1 != ids2` 亦不成立）。`test_shortlist_dedup_scoped_to_session` 與 `fail_open` 可能先過（現行本來就 offer），屬防回歸鎖。既有 5 個測試全綠。

- [x] **Step 3: Write minimal implementation**

3a. `paulshaclaw/memory/hooks/_shortlist_common.py` 的 `SHORTLIST_K = 3`（現 :13）之後加（`import re` 留到 Task 3 才需要，本 task 勿加）：

```python
# 過取候選數：session 內已 offer 的 sl_id 過濾後仍能補位至 K（#178 去重）。
SHORTLIST_FETCH_K = 12
```

3b. 在 `_record_offered` 之前新增兩個 helper：

```python
def _offered_map_path(root: Path, tool: str, session_id: str) -> Path:
    """Single source of truth for the per-session offered map path (writer+reader)."""
    return root / "runtime" / "wakeup" / f"{tool}__{sanitize_id(session_id)}.offered.json"


def _load_offered_ids(root: Path, tool: str, session_id: str) -> set[str]:
    """sl_ids already offered in this session (reads back the map _record_offered keeps).

    Best-effort fail-open: missing/corrupt map -> empty set（寧可重複 offer，不可因
    讀檔失敗而完全不 offer）。對比 _redact 的 fail-closed：安全性質不同。
    """
    try:
        cur = json.loads(_offered_map_path(root, tool, session_id).read_text(encoding="utf-8"))
        by_id = cur.get("by_id", {})
        return set(by_id) if isinstance(by_id, dict) else set()
    except Exception:
        return set()
```

3c. `_record_offered`（現 :53-81）內：

```python
        mpath = wk_dir / f"{tool}__{sanitize_id(session_id)}.offered.json"
```

改為：

```python
        mpath = _offered_map_path(root, tool, session_id)
```

（`wk_dir.mkdir(...)` 保留不動。）

3d. `build_shortlist_and_record`（現 :84-115）內，把：

```python
        try:
            hits = search_mod.search(root, query, project=project,
                                     limit=SHORTLIST_K, include_decayed=False)
        except search_mod.SearchIndexError:
            return ""
        if not hits:
            return ""
```

改為：

```python
        try:
            hits = search_mod.search(root, query, project=project,
                                     limit=SHORTLIST_FETCH_K, include_decayed=False)
        except search_mod.SearchIndexError:
            return ""
        # session 內去重（#178）：過濾本 session 已 offer 過的 sl_id，以次佳補位。
        seen = _load_offered_ids(root, tool, session_id)
        hits = [h for h in hits if h.get("slice_id") and h["slice_id"] not in seen]
        hits = hits[:SHORTLIST_K]
        if not hits:
            return ""
```

其餘（`_summary` 迴圈、`_redact` fail-closed、`_record_offered` 呼叫）不動。

- [x] **Step 4: Run tests to verify they pass**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_shortlist_common.py -q`
Expected: PASS（新增 3 個 + 既有 5 個）。

- [x] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/hooks/_shortlist_common.py paulshaclaw/memory/tests/test_shortlist_common.py
git commit -m "feat(memory): #178 shortlist session 內去重（讀回 offered map + 過取補位）"
```

---

## Task 3: 摘要行跳過 title echo（hooks/_shortlist_common.py）

**Files:**
- Test: `paulshaclaw/memory/tests/test_shortlist_common.py`（檔尾追加）
- Modify: `paulshaclaw/memory/hooks/_shortlist_common.py`（`_summary` + 呼叫點）

- [x] **Step 1: Write the failing tests**

追加到 `paulshaclaw/memory/tests/test_shortlist_common.py`：

```python
def test_summary_skips_title_echo_first_line(tmp_path):
    p = tmp_path / "n.md"
    p.write_text("---\ntitle: overview\n---\n# Overview\n\nUART2 pinmux 設錯會靜默失效。\n",
                 encoding="utf-8")
    assert SC._summary(str(p), "overview") == "UART2 pinmux 設錯會靜默失效。"


def test_summary_all_title_echo_returns_empty(tmp_path):
    # 「Review Summary」與 title「review-summary」正規化後相同 → 近同也要跳過
    p = tmp_path / "n.md"
    p.write_text("---\ntitle: review-summary\n---\n# Review Summary\n", encoding="utf-8")
    assert SC._summary(str(p), "review-summary") == ""


def test_summary_first_line_kept_when_not_echo(tmp_path):
    p = tmp_path / "n.md"
    p.write_text("---\ntitle: x\n---\n具體結論第一行。\n", encoding="utf-8")
    assert SC._summary(str(p), "x") == "具體結論第一行。"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_shortlist_common.py -q`
Expected: FAIL — `TypeError: _summary() takes 1 positional argument but 2 were given`（3 個新測試）。

- [x] **Step 3: Write minimal implementation**

3a. 檔頭 import 區加 `import re`（放在 `import json` 旁；`_norm_title_key` 需要），並在 `_summary` 之前加正規化 helper：

```python
def _norm_title_key(s: str) -> str:
    """Normalize for title/line near-equality: lowercase + drop non-word chars
    （大小寫、空白、標點、底線差異一律忽略，CJK 保留）。"""
    return re.sub(r"[\W_]+", "", s).lower()
```

3b. `_summary`（現 :16-31）整個函式替換為：

```python
def _summary(path: str, title: str = "") -> str:
    """First informative body line for the shortlist.

    Skips YAML frontmatter, blank lines, and lines that (normalized) duplicate the
    slice title — a title-echo line ("[overview] — Overview") carries zero decision
    info for the agent (#178). Returns "" when no informative line exists（誠實給
    空摘要，注入列仍含標題與路徑，不硬湊重複資訊）。"""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    lines = text.splitlines()
    # skip YAML frontmatter if present
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
        lines = lines[end + 1:]
    tkey = _norm_title_key(title)
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        s = s.lstrip("# ").strip()
        if not s:
            continue
        if tkey and _norm_title_key(s) == tkey:
            continue
        return s
    return ""
```

3c. `build_shortlist_and_record` 內呼叫點（Task 2 改完後位於 `hits = hits[:SHORTLIST_K]` 之後）：

```python
        for h in hits:
            h["summary"] = _summary(h.get("path", ""))
```

改為：

```python
        for h in hits:
            h["summary"] = _summary(h.get("path", ""), str(h.get("title") or ""))
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_shortlist_common.py -q`
Expected: PASS（Task 2+3 新增 6 個 + 既有 5 個）。

- [x] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/hooks/_shortlist_common.py paulshaclaw/memory/tests/test_shortlist_common.py
git commit -m "feat(memory): #178 shortlist 摘要跳過 title echo 首行改取有資訊行"
```

---

## Task 4: retitle 掃描條件擴到 generic 標題（retitle.py）

**Files:**
- Test: `paulshaclaw/memory/tests/test_retitle.py`（檔尾追加，`if __name__` 區塊之前；沿用該檔既有模組層級 `_slice(root, project, name, body, *, title=...)` helper）
- Modify: `paulshaclaw/memory/retitle.py`

- [x] **Step 1: Write the failing test**

追加到 `paulshaclaw/memory/tests/test_retitle.py`（unittest class，與既有同風格）：

```python
class RetitleGenericTitleTests(unittest.TestCase):
    def test_generic_title_slice_is_retitled(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = "COM0 斷線根因是 udev 權限規則沒套用，重插後 ttyUSB 編號漂移。"
            p = _slice(root, "testpilot", "report-testpilot--sl-r1.md", body,
                       title="report-testpilot")
            summary = retitle.retitle_untitled(
                root, now="2026-07-02T00:00:00Z", apply=True,
                distill=lambda b: "COM0 斷線根因")
            self.assertFalse(p.exists())
            target = root / "knowledge" / "testpilot" / "com0-斷線根因--sl-r1.md"
            self.assertTrue(target.exists(),
                            list((root / "knowledge" / "testpilot").iterdir()))
            self.assertEqual(summary["retitled"], 1)

    def test_specific_title_slice_not_scanned(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = _slice(root, "testpilot", "uart2-tips--sl-s1.md",
                       "UART2 在 pinmux 設錯時靜默失效。", title="UART2 除錯重點")
            summary = retitle.retitle_untitled(
                root, now="2026-07-02T00:00:00Z", apply=True,
                distill=lambda b: "不該被呼叫")
            self.assertTrue(p.exists())
            self.assertEqual(summary["candidates"], 0)
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_retitle.py -q`
Expected: FAIL — `test_generic_title_slice_is_retitled` 於首個斷言 `self.assertFalse(p.exists())` 失敗（現行掃描條件只認 `untitled`，generic 標題不進候選：candidates=0、原檔未改名仍在）。`test_specific_title_slice_not_scanned` 先過（防回歸鎖）。

- [x] **Step 3: Write minimal implementation**

3a. `paulshaclaw/memory/retitle.py` import 行（現 :23）：

```python
from .noise import DocCorpus, classify_noise
```

改為：

```python
from .noise import DocCorpus, classify_noise, is_generic_title
```

3b. `_is_untitled`（現 :28-30）改為：

```python
def _is_untitled(frontmatter: dict, path: Path) -> bool:
    title = str(frontmatter.get("title", "")).strip()
    return (title == "untitled" or path.name.startswith("untitled--")
            or is_generic_title(title))
```

3c. 模組 docstring（現 :1-11）末段補一行（`so the migration never invents a junk title and never fails as a whole.` 之後）：

```
Since #178 the scan also covers generic titles (``noise.is_generic_title``:
report-*/task-*/todo-*/overview/problem/review-summary) so pool-excluded
generic artifacts can regain a specific title and re-enter the retrieval pool.
```

既有防護不動：doc-fragment guard（:76-77，`classify_noise` 命中即 skip 留給 prune-noise）、distill 失敗 skip、預設 dry-run、manifest。

- [x] **Step 4: Run test to verify it passes**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_retitle.py -q`
Expected: PASS（新增 2 個 + 既有全部）。

- [x] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/retitle.py paulshaclaw/memory/tests/test_retitle.py
git commit -m "feat(memory): #178 retitle 掃描條件擴到 generic 標題（共用 is_generic_title）"
```

---

## Task 5: 回歸與收尾

- [x] **Step 1: 全套件回歸**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q`
Expected: 全綠、零失敗（CI 等效命令：`python -m pytest tests/ paulshaclaw/memory/tests/ -q`，亦須綠）。

- [x] **Step 2: Boundary 自查**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && git diff --name-only main...HEAD`
Expected: 只出現 Boundary 白名單內檔案；特別確認 `paulshaclaw/memory/moc/search.py`、`paulshaclaw/memory/cli.py`、`.github/workflows/**` **零 diff**。

- [x] **Step 3: 勾選 openspec tasks 與本 plan checkbox 並 commit（例：`docs(openspec): #178 勾選 tasks 進度`），確認工作樹乾淨後依 Delivery 段 push + 開 PR（不 merge）**

---

## Deployment/Ops notes（不屬 PR 實作範圍）

以下為 merge 後的部署/營運動作，**不得寫成 implementation task、不得在 PR 內執行**：

1. **hooks 部署是複製、非 symlink**：`paulshaclaw/memory/hooks/_shortlist_common.py` 由 `paulshaclaw/memory/hooks/install.sh` 複製部署到 `~/.agents/memory/hooks/`（install.sh:171 的檔案清單已含 `_shortlist_common.py`）。**merge 後 git pull 不等於部署**——須在本機重跑 `bash /home/paul_chen/prj_pri/paulshaclaw/paulshaclaw/memory/hooks/install.sh` 同步副本（entry hooks 以 package import 走 editable install，repo 版可能已生效，但部署副本仍須同步以免 drift）。
2. **存量 index 出池時點**：`generic-title` 排除在下次 `build_index`（dream loop 的 moc pass，每小時）重建 `retrieval.db` 才生效；如需立即生效可手動觸發 moc 重建（ops 決定，非 PR）。
3. **live retitle 執行**：對現存 generic 標題 slice 跑 `retitle-untitled` 屬 ops：先 `--dry-run` 核 manifest（逐筆確認非誤掃）再 `--apply`；工具就緒後另議，本 PR 只交付掃描能力。
4. **PostToolUse Bash matcher（read 歸因漏記，issue 修法 4）**：屬使用者 `~/.claude/settings.json` 的 hook matcher 設定，**不入 PR**；若使用者要補 Bash 直讀 knowledge 的歸因，於 settings 的 PostToolUse matcher 加 `Bash` 並由 hook 內 regex 抓 command 中的 knowledge 路徑——另開票處理，本 change 不涉及。

## Delivery（repo 分支/PR 政策）

- **Branch**：自 `main` 開 `feature/178-stage2-offer-shortlist-quality`（R-12：進 main 的 PR head 必須 `feature/<slug>`）。
- **Commit**：conventional commit、zh-TW（如各 Task Step 5 所示；R-10）。
- **PR**：title conventional（建議 `feat(memory): offer shortlist 品質——generic 標題出池 + session 內去重 + 摘要資訊量`）；body 全 zh-TW，**必含 `Closes #178`**（R-17 closing-keyword）；body **不得有未勾選 checkbox**（R-11——勿把本 plan 的 checkbox 原樣貼進 PR body）。
- **禁區**：不碰 `.github/workflows/**` 與任何 `policy_version` 字面值（R-20）。
- **CI**：push 後確認 `Policy Check` 與 `tests.yml` 全綠（`gh pr view --json statusCheckRollup` 判定，勿依賴 `pr checks` exit code）。
- **完成定義**：push + 開 PR 即止，**不得 merge**（等待人工與對抗性驗證）。

---

## Self-Review

- **Spec coverage**：`stage2-noise-governance`「generic 標題池排除」→ Task 1；`stage2-memory-prompt-retrieval`「session 內去重」→ Task 2、「摘要行資訊量」→ Task 3；`stage2-knowledge-retitle`「掃描擴充」→ Task 4。四條 delta 全覆蓋。
- **VERIFY corrections 對齊**：本項 audit verdict=CONFIRMED、corrections 僅數字微調（generic 佔比 49→55%、Bash 漏記 1→2 次），無被推翻的修法；issue #178 修法 1-3 全數落地、修法 4（PostToolUse）依規劃留在 Ops notes。
- **取捨已記錄**：pool_exclude vs link_weight 重罰之二選一，讀碼後選前者，理由在 openspec design.md D1。
- **Placeholder scan**：各 step 均含完整測試碼/實作碼/指令/預期輸出，無 TODO/TBD。
- **Type consistency**：`is_generic_title(title: object) -> bool`、`pool_exclude_reason -> str | None`（新 reason `"generic-title"`）、`_summary(path: str, title: str = "") -> str`、`_load_offered_ids -> set[str]`、`SHORTLIST_FETCH_K=12` 全文一致。
- **既有不變量未破壞**：未注入不記 offered（fail-closed redaction 測試仍鎖）、`_record_offered` 只寫格式不變（`by_path`/`by_id`）、retitle doc-fragment guard 不動、`classify_noise` 完全不動。
