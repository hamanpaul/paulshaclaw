# Memory 消費迴路（Cleanup/Consolidation）Implementation Plan — Plan 2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 收束消費迴路周邊：SessionStart brief 瘦成 orientation、退役逐字 cited/matched 改 read-based usage CLI、檢索 index 防禦性排除噪音、清除現存噪音殘留。

**Architecture:** 沿用既有 `noise.classify_noise` + `instruction_corpus`（doc-fragment 已具備，不重造）；新增 frontmatter 級 `pool_exclude_reason`（canary/review 非刪除級排除）並於 `build_index` 套用；`build_orientation` 取代 SessionStart 的 MOC dump；usage CLI 與 SessionEnd 改 read-based。

**Tech Stack:** Python 3.12、sqlite3 FTS5、pytest。範圍：`paulshaclaw/memory/`。

**前置：** 本計畫銜接 **Plan 1**（`docs/superpowers/plans/2026-06-29-memory-consumption-loop-core.md`）——Plan 1 已將 `slice_meta` 加 `path` 欄並改 `build_index`；本計畫的 `build_index` 改動建立於 Plan 1 版本之上。**先完成 Plan 1 再做 Plan 2。**

**驗證指令：** `cd /home/paul_chen/prj_pri/paulshaclaw && python3 -m pytest paulshaclaw/memory/tests/<file> -v`

---

## File Structure

- Modify `paulshaclaw/memory/noise.py` — 新增 `pool_exclude_reason(frontmatter)`（frontmatter 級、canary/review）。
- Modify `paulshaclaw/memory/moc/search.py` — `build_index` 加 `doc_corpus` 參數，納入前排除 `classify_noise` 命中 + `pool_exclude_reason`。
- Modify `paulshaclaw/memory/moc/runner.py` — 傳入 `instruction_corpus.load_corpus()`。
- Modify `paulshaclaw/memory/wakeup/builder.py` — 新增 `build_orientation(memory_root, project)`。
- Modify `paulshaclaw/memory/hooks/_wakeup_common.py` — `compute_brief_and_record` 改用 orientation、移除 CITATION_PREAMBLE 與 SessionStart offered 寫入。
- Modify `paulshaclaw/memory/hooks/claude_session_end.py` — 移除 `record_session_usage` 區塊。
- Modify `paulshaclaw/memory/cli.py` — `_memory_usage` 改 read-based（讀 `offered.jsonl` + `memory_usage.jsonl` 的 `source:"read"`）。
- Tests：`test_noise.py`、`test_moc_search.py`、`test_wakeup_builder.py`/新 orientation 測試、`test_wakeup_offered.py`、`test_memory_usage_cli.py`。

---

## Task 1: frontmatter 級池排除 `pool_exclude_reason`

**Files:**
- Modify: `paulshaclaw/memory/noise.py`
- Test: `paulshaclaw/memory/tests/test_noise.py`

- [ ] **Step 1: Write the failing test**（append）

```python
def test_pool_exclude_reason_review_and_canary():
    from paulshaclaw.memory.noise import pool_exclude_reason
    assert pool_exclude_reason({"artifact_kind": "review"}) == "review-record"
    assert pool_exclude_reason(
        {"artifact_kind": "task", "atom_title": "canary-claude task context"}) == "canary-fixture"
    assert pool_exclude_reason(
        {"artifact_kind": "task", "session_title": "smoke test execution"}) == "canary-fixture"
    # real knowledge is not excluded
    assert pool_exclude_reason({"artifact_kind": "spec", "atom_title": "LLM Atomizer"}) is None
    assert pool_exclude_reason({"artifact_kind": "task", "atom_title": "build P4 split"}) is None
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_noise.py::test_pool_exclude_reason_review_and_canary -v`
Expected: FAIL（`ImportError: cannot import name 'pool_exclude_reason'`）

- [ ] **Step 3: Implement in `noise.py`**（append at module end）

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
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_noise.py -v`
Expected: PASS（含既有 noise 測試）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/noise.py paulshaclaw/memory/tests/test_noise.py
git commit -m "feat(memory): noise.pool_exclude_reason（canary/review 非刪除級池排除）"
```

---

## Task 2: `build_index` 防禦性排除噪音

**Files:**
- Modify: `paulshaclaw/memory/moc/search.py`（Plan 1 已加 `path` 欄）
- Modify: `paulshaclaw/memory/moc/runner.py`
- Test: `paulshaclaw/memory/tests/test_moc_search.py`

- [ ] **Step 1: Write the failing test**（append）

```python
def test_build_index_excludes_noise_and_pool(tmp_path):
    from paulshaclaw.memory.moc import search as S
    from paulshaclaw.memory.noise import build_corpus
    mr = tmp_path
    k = mr / "knowledge" / "proj"; k.mkdir(parents=True)
    # clean note
    (k / "good.md").write_text(
        "---\nmemory_layer: knowledge\nslice_id: sl-good00000000000\nproject: proj\n"
        "title: Good\nartifact_kind: spec\ncaptured_at: '2026-06-29T00:00:00Z'\n---\n真實知識內容\n",
        encoding="utf-8")
    # review-record (pool-excluded)
    (k / "rev.md").write_text(
        "---\nmemory_layer: knowledge\nslice_id: sl-rev000000000000\nproject: proj\n"
        "title: PR Review\nartifact_kind: review\ncaptured_at: '2026-06-29T00:00:00Z'\n---\nreview body\n",
        encoding="utf-8")
    # structural-echo noise (classify_noise)
    (k / "echo.md").write_text(
        "---\nmemory_layer: knowledge\nslice_id: sl-echo00000000000\nproject: proj\n"
        "title: X\nartifact_kind: report\ncaptured_at: '2026-06-29T00:00:00Z'\n---\n## CWD\n/tmp\n",
        encoding="utf-8")
    S.build_index(mr, link_weights={}, doc_corpus=build_corpus([]))
    ids = {h["slice_id"] for h in S.search(mr, '"知識" OR "review" OR "CWD"',
                                           project="proj", limit=10, include_decayed=True)}
    assert "sl-good00000000000" in ids
    assert "sl-rev000000000000" not in ids   # pool-excluded
    assert "sl-echo00000000000" not in ids    # classify_noise
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_moc_search.py::test_build_index_excludes_noise_and_pool -v`
Expected: FAIL（`build_index() got unexpected keyword 'doc_corpus'`）

- [ ] **Step 3: Modify `build_index`**（在 Plan 1 版本基礎上：加參數 + 迴圈內排除）

簽章改為：

```python
def build_index(memory_root: Path, link_weights: dict[str, int],
                doc_corpus: "object | None" = None) -> None:
```

於檔頭 import：

```python
from ..noise import classify_noise, pool_exclude_reason
```

在 `for fpath in sorted(knowledge.rglob("*.md")):` 迴圈內、現有 `if fm.get("memory_layer") != "knowledge": continue` 與 `sid` 檢查**之後**，加入排除：

```python
                if pool_exclude_reason(fm) is not None:
                    continue
                if classify_noise(fm, body, doc_corpus=doc_corpus).is_noise:
                    continue
```

（其餘 build_index 主體沿用 Plan 1 版本不變。）

- [ ] **Step 4: Update `runner.py` 傳 corpus**

`paulshaclaw/memory/moc/runner.py` 第 6 行 import 加 `instruction_corpus`，第 20 行改：

```python
from ..import instruction_corpus  # 置於檔頭 import 區
...
        search.build_index(memory_root, weights, doc_corpus=instruction_corpus.load_corpus())
```

> 正確 import 寫法：於 runner.py 檔頭 `from .. import instruction_corpus`。

- [ ] **Step 5: Run tests to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_moc_search.py -v`
Expected: PASS（含 Plan 1 的 path 測試與本測試）

- [ ] **Step 6: Commit**

```bash
git add paulshaclaw/memory/moc/search.py paulshaclaw/memory/moc/runner.py paulshaclaw/memory/tests/test_moc_search.py
git commit -m "feat(memory): build_index 防禦性排除 classify_noise + pool_exclude"
```

---

## Task 3: SessionStart brief 瘦成 orientation

**Files:**
- Modify: `paulshaclaw/memory/wakeup/builder.py`（新增 `build_orientation`）
- Modify: `paulshaclaw/memory/hooks/_wakeup_common.py`
- Test: `paulshaclaw/memory/tests/test_wakeup_builder.py`、`test_wakeup_offered.py`

- [ ] **Step 1: Write the failing test**（`test_wakeup_builder.py` append）

```python
def test_build_orientation_concise(tmp_path):
    from paulshaclaw.memory.wakeup.builder import build_orientation
    k = tmp_path / "knowledge" / "proj"; k.mkdir(parents=True)
    (k / "a.md").write_text("---\nmemory_layer: knowledge\nslice_id: sl-a\n---\nx\n", encoding="utf-8")
    (k / "b.md").write_text("---\nmemory_layer: knowledge\nslice_id: sl-b\n---\ny\n", encoding="utf-8")
    (k / "proj-moc.md").write_text("# moc\n", encoding="utf-8")  # excluded from count
    out = build_orientation(tmp_path, "proj")
    assert "Read" in out and "2" in out
    assert "## Map" not in out and "[[" not in out  # no MOC dump, no wikilinks


def test_build_orientation_empty_when_no_notes(tmp_path):
    from paulshaclaw.memory.wakeup.builder import build_orientation
    assert build_orientation(tmp_path, "proj") == ""
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_wakeup_builder.py::test_build_orientation_concise -v`
Expected: FAIL（`ImportError: cannot import name 'build_orientation'`）

- [ ] **Step 3: Implement `build_orientation`**（append to `builder.py`）

```python
def build_orientation(memory_root, project: str) -> str:
    """Concise SessionStart orientation (no MOC dump). '' when project has no notes."""
    from pathlib import Path as _Path
    from ..atomizer.config import sanitize_project_component
    safe = sanitize_project_component(project)
    pdir = _Path(memory_root) / "knowledge" / safe
    n = 0
    if pdir.exists():
        n = sum(1 for p in pdir.glob("*.md") if not p.name.endswith("-moc.md"))
    if n == 0:
        return ""
    return (f"# 記憶 — {project}\n\n"
            f"記憶系統已啟用（本專案約 {n} 筆 knowledge）。與當前任務相關的記憶會在每次 "
            f"prompt 後以短清單浮現；用 Read 開啟清單中列出的絕對路徑即取全文。")
```

- [ ] **Step 4: Rewire `compute_brief_and_record` in `_wakeup_common.py`**

移除檔頭 `from paulshaclaw.memory.usage import CITATION_PREAMBLE, extract_offered`（不再使用）。將 `compute_brief_and_record` 整段換為：

```python
def compute_brief_and_record(root: Path, tool: str, session_id: str, cwd: str | None) -> str:
    """SessionStart 極簡 orientation；不再前置引用前言、不再寫 session-wide offered。"""
    try:
        from paulshaclaw.memory.importer.project_resolver import resolve_project
        from paulshaclaw.memory.wakeup.builder import build_orientation
    except ImportError as exc:
        log_warn(root, tool, f"failed to import resolver or builder: {exc}")
        return ""
    try:
        project = resolve_project(cwd=cwd, memory_root=str(root))
        if project in ("_unknown", ""):
            return ""
        return build_orientation(root, project)
    except Exception as exc:
        log_warn(root, tool, f"failed to build orientation: {exc}")
        return ""
```

> `compute_brief`（舊 build_brief 路徑）與 `build_brief` 本身**保留**（`memory wakeup` CLI 仍用）；僅 SessionStart hook 路徑改走 orientation。

- [ ] **Step 5: 更新受影響測試**

`test_wakeup_offered.py` 斷言「SessionStart 寫 offered 檔 + brief 含 CITATION_PREAMBLE」者已不成立 → 改為斷言 `compute_brief_and_record` 回傳 orientation（含 "Read"）、`runtime/wakeup/<tool>__<sid>.json` **不再被 SessionStart 寫入**（offered 改由 Plan 1 prompt-retrieval 寫 `.offered.json`）。`test_session_start_*` 中檢查 brief 含 MOC/Recent 者改為檢查 orientation 字樣。

Run: `python3 -m pytest paulshaclaw/memory/tests/test_wakeup_builder.py paulshaclaw/memory/tests/test_wakeup_offered.py paulshaclaw/memory/tests/test_session_start_hooks.py paulshaclaw/memory/tests/test_session_start_wiring.py -v`
Expected: PASS（更新後）

- [ ] **Step 6: Commit**

```bash
git add paulshaclaw/memory/wakeup/builder.py paulshaclaw/memory/hooks/_wakeup_common.py paulshaclaw/memory/tests/
git commit -m "feat(memory): SessionStart brief 瘦成 orientation；移除 16-hex 引用前言"
```

---

## Task 4: 退役 SessionEnd cited/matched + usage CLI 改 read-based

**Files:**
- Modify: `paulshaclaw/memory/hooks/claude_session_end.py`
- Modify: `paulshaclaw/memory/cli.py`（`_memory_usage`）
- Test: `paulshaclaw/memory/tests/test_memory_usage_cli.py`、`test_session_end_usage.py`

- [ ] **Step 1: Write the failing test**（`test_memory_usage_cli.py` 改/新增 read-based）

```python
def test_memory_usage_read_based(tmp_path, capsys):
    import argparse, json
    from paulshaclaw.memory.cli import _memory_usage
    led = tmp_path / "runtime" / "ledger"; led.mkdir(parents=True)
    (led / "offered.jsonl").write_text(
        json.dumps({"ts": "2026-06-29T01:00:00Z", "session_id": "s", "tool": "claude-code",
                    "project": "p", "offered": [{"sl_id": "sl-a", "path": "/k/a.md"},
                                                {"sl_id": "sl-b", "path": "/k/b.md"}]}) + "\n",
        encoding="utf-8")
    (led / "memory_usage.jsonl").write_text(
        json.dumps({"ts": "2026-06-29T01:05:00Z", "session_id": "s", "tool": "claude-code",
                    "project": "p", "sl_id": "sl-a", "path": "/k/a.md",
                    "source": "read", "offered": True}) + "\n",
        encoding="utf-8")
    args = argparse.Namespace(memory_root=str(tmp_path), since=None, json=True)
    assert _memory_usage(args) == 0
    rep = json.loads(capsys.readouterr().out)
    by = {s["slice_id"]: s for s in rep["slices"]}
    assert by["sl-a"]["offered_count"] == 1 and by["sl-a"]["read_count"] == 1
    assert by["sl-b"]["offered_count"] == 1 and by["sl-b"]["read_count"] == 0
    assert rep["summary"]["never_read"] == 1  # sl-b offered but never read
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_memory_usage_cli.py::test_memory_usage_read_based -v`
Expected: FAIL（舊版讀 cited/matched、無 read_count/never_read）

- [ ] **Step 3: Rewrite `_memory_usage` in `cli.py`**

```python
def _memory_usage(args: argparse.Namespace) -> int:
    from collections import defaultdict

    root = Path(args.memory_root)
    led = root / "runtime" / "ledger"

    def _read_jsonl(p):
        out = []
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if args.since and str(e.get("ts", "")) < args.since:
                    continue
                out.append(e)
        return out

    offered_rows = _read_jsonl(led / "offered.jsonl")
    used_rows = [e for e in _read_jsonl(led / "memory_usage.jsonl") if e.get("source") == "read"]

    agg = defaultdict(lambda: {"offered_count": 0, "read_count": 0, "last_read": ""})
    sessions = set()
    for e in offered_rows:
        sessions.add(e.get("session_id"))
        for o in e.get("offered", []):
            sid = o.get("sl_id") if isinstance(o, dict) else o
            if sid:
                agg[sid]["offered_count"] += 1
    for e in used_rows:
        sid = e.get("sl_id")
        if not sid:
            continue
        ts = str(e.get("ts", ""))
        agg[sid]["read_count"] += 1
        if ts > agg[sid]["last_read"]:
            agg[sid]["last_read"] = ts

    slices = [{"slice_id": sid, **v} for sid, v in agg.items()]
    slices.sort(key=lambda s: (s["read_count"], s["offered_count"]), reverse=True)
    never_read = sum(1 for s in slices if s["offered_count"] > 0 and s["read_count"] == 0)
    n = len(sessions)
    total_reads = len(used_rows)
    summary = {
        "sessions": n, "slices": len(slices), "never_read": never_read,
        "total_reads": total_reads,
        "avg_reads_per_session": round(total_reads / n, 3) if n else 0.0,
    }
    report = {"summary": summary, "slices": slices}

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"sessions={summary['sessions']} slices={summary['slices']} "
              f"never_read={summary['never_read']} total_reads={summary['total_reads']} "
              f"avg_reads/session={summary['avg_reads_per_session']}")
        for s in slices[:30]:
            print(f"  {s['slice_id']}  offered={s['offered_count']} "
                  f"read={s['read_count']} last_read={s['last_read']}")
    return 0
```

- [ ] **Step 4: 退役 SessionEnd usage 記錄**

`claude_session_end.py` 移除 `record_session_usage` 區塊（現第 107-115 行的 try/except import + 呼叫）。`usage_ledger.record_session_usage` 函式保留但不再被呼叫（後續另案移除）。
更新 `test_session_end_usage.py`：移除/改寫「SessionEnd 寫 cited/matched event」之斷言為「SessionEnd 不再寫 memory_usage cited/matched」。

- [ ] **Step 5: Run tests to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_memory_usage_cli.py paulshaclaw/memory/tests/test_session_end_usage.py -v`
Expected: PASS（更新後）

- [ ] **Step 6: Commit**

```bash
git add paulshaclaw/memory/cli.py paulshaclaw/memory/hooks/claude_session_end.py paulshaclaw/memory/tests/
git commit -m "feat(memory): usage CLI 改 read-based；退役 SessionEnd cited/matched"
```

---

## Task 5: 部署同步 + 全套件回歸

**Files:** （部署 + 驗證）

- [ ] **Step 1: 重新同步 hooks**（session_end 已改）

Run: `bash paulshaclaw/memory/hooks/install.sh`
Verify: `grep -L record_session_usage ~/.agents/memory/hooks/claude_session_end.py`（應列出該檔＝已不含該字串）

- [ ] **Step 2: 重建檢索 index（noise 排除生效）**

Run: `~/.agents/memory/hooks/.venv/bin/python -c "from pathlib import Path; from paulshaclaw.memory.moc import runner; print(runner.run_moc(Path('/home/paul_chen/.agents/memory'), '2026-06-29T00:00:00Z'))"`
Expected: dict `indexed: True`、`warnings` 不含 index 失敗。

- [ ] **Step 3: 全套件回歸**

Run: `python3 -m pytest paulshaclaw/memory/tests/ -q`
Expected: 全綠（含 Plan 1 + Plan 2 新測試；既有測試更新後通過）。

- [ ] **Step 4: Commit**（install.sh 若有改）

```bash
git add -A paulshaclaw/memory/hooks/install.sh
git commit -m "chore(memory): 同步 session_end 退役改動" || echo "no install.sh change"
```

---

## Task 6: 現存噪音 prune（操作面、gated、destructive）

**Files:** （操作，無程式變更）

- [ ] **Step 1: 備份 knowledge**

Run: `cp -a /home/paul_chen/.agents/memory/knowledge /tmp/claude-1000/-home-paul-chen-prj-pri-paulshaclaw/0bf7677e-b2a2-47c6-8876-add29d70c907/scratchpad/knowledge-backup-20260629`
Verify: 備份目錄存在且 `*.md` 數量與來源一致。

- [ ] **Step 2: dry-run（scoped corpus）**

Run: `python3 -m paulshaclaw.memory.cli memory knowledge prune-noise --memory-root /home/paul_chen/.agents/memory --instruction-root /home/paul_chen/prj_pri/paulshaclaw --dry-run`
（`--instruction-root` 指向本 repo 以組 scoped doc_corpus，避免 broad corpus 過刪——見記憶 `project_doc_fragment_corpus_scoping`）
Expected: 列出將刪 slice 與 reason 統計（doc-fragment / structural-echo / empty / placeholder）。

- [ ] **Step 3: 人核 manifest（gate）**

人工核對 dry-run 數字：預期量級 ~100-130（含 doc-fragment）。**若數字明顯超出（例如逼近全量），停下回報、勿 apply**（broad corpus 過刪風險）。

- [ ] **Step 4: apply（確認後）**

Run: `python3 -m paulshaclaw.memory.cli memory knowledge prune-noise --memory-root /home/paul_chen/.agents/memory --instruction-root /home/paul_chen/prj_pri/paulshaclaw --apply`
Expected: hard delete 命中檔、重建 MOC、manifest 落 `runtime/ledger/prune-<now>.jsonl`。

- [ ] **Step 5: 驗證短清單不再含噪音**

Run: 重建 index（Task 5 Step 2），於真實 session 送相關 prompt → 短清單只含 actionable knowledge（無 `# AGENTS.md instruct` 片段）。
回滾：如需還原，從 Step 1 備份覆寫 `knowledge/` 後重建 MOC/index。

---

## Self-Review

- **Spec 覆蓋**：`stage2-noise-governance`(ADDED：index/pool 排除=Task 2；canary/review=Task 1)；`stage2-memory-readback`(MODIFIED：orientation=Task 3)；`stage2-memory-usage-telemetry`(REMOVED SessionStart offered/preamble=Task 3、REMOVED SessionEnd cited/matched=Task 4、MODIFIED usage CLI=Task 4)。現存噪音清除=Task 6（重用既有 prune-noise）。
- **Placeholder**：新程式（pool_exclude_reason / build_orientation / build_index 排除 / _memory_usage）均給完整碼；既有測試更新以「明確的新預期行為」描述（實作者讀現檔調整斷言）。
- **型別/命名一致**：`pool_exclude_reason(frontmatter)`、`build_index(memory_root, link_weights, doc_corpus=None)`、`build_orientation(memory_root, project)`、usage 欄位 `offered_count/read_count/last_read/never_read`、offered 來源 `offered.jsonl`、used 來源 `memory_usage.jsonl`(source==read)——與 Plan 1 共用格式一致。
- **依賴 Plan 1**：Task 2 build_index 建立於 Plan 1 的 path 欄版本；usage CLI 讀 Plan 1 寫的 `offered.jsonl` 與 read 事件。先 Plan 1 後 Plan 2。
- **取捨**：canary 辨識為 title/session 啟發式（artifact_kind=task + canary/smoke 字樣），可能漏判罕見命名；review 用 artifact_kind=review 精準。prune 為 gated 人工關卡。
