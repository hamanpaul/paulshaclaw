# Memory 消費迴路（核心）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓相關記憶在 UserPromptSubmit 依任務檢索成短清單（含可開啟絕對路徑）送達 agent，agent native Read 即以「讀取=使用」被精準歸因。

**Architecture:** 純檢索助手（`retrieval.py`，無 IO）+ hook 編排層（`_shortlist_common.py`，IO）+ 兩個 best-effort hook（UserPromptSubmit 注入短清單、PostToolUse(Read) 記 used）。檢索複用既有 `search.py` bm25；新增 `slice_meta.path` 欄位讓短清單能給絕對路徑。所有 hook 失敗即 log + exit 0，永不阻斷 session。

**Tech Stack:** Python 3.12、sqlite3 FTS5、pytest。範圍：`paulshaclaw/memory/`。

**Scope note:** 本計畫只做**核心消費迴路**（可獨立測試/上線）。SessionStart brief 瘦身、read-based telemetry CLI、noise index/pool 排除、現存噪音 prune 屬 **Plan 2（cleanup/consolidation）**，另立計畫。

**驗證指令（全程通用）：** `cd /home/paul_chen/prj_pri/paulshaclaw && python3 -m pytest paulshaclaw/memory/tests/<file> -v`（`/usr/bin/python3` 已 editable 安裝 paulshaclaw；勿用 `unittest discover`）。

---

## File Structure

- Create `paulshaclaw/memory/retrieval.py` — 純函式：`to_fts_query`、`format_shortlist`。無 IO、可單測。
- Modify `paulshaclaw/memory/moc/search.py` — `build_index` 加 `path` 欄；`search()` 回傳 `path`。
- Create `paulshaclaw/memory/hooks/_shortlist_common.py` — 編排：resolve_project→to_fts_query→search→讀摘要→組短清單→記 offered + per-session 映射。
- Create `paulshaclaw/memory/hooks/claude_user_prompt_submit.py` — UserPromptSubmit entrypoint。
- Create `paulshaclaw/memory/hooks/claude_post_tool_use.py` — PostToolUse(Read) read 歸因。
- Create tests：`test_retrieval.py`、`test_shortlist_common.py`、`test_user_prompt_submit_hook.py`、`test_post_tool_use_hook.py`；Modify `test_moc_search.py`。
- Modify `paulshaclaw/memory/hooks/install.sh`（同步新 hook）；Modify `~/.claude/settings.json`（接線，部署步驟）。

**共用資料格式（鎖定，跨 task 一致）：**
- offered ledger：append `runtime/ledger/offered.jsonl`，每行 `{"ts","session_id","tool","project","offered":[{"sl_id","path"}]}`。
- per-session 映射：`runtime/wakeup/<tool>__<sid>.offered.json`，內容 `{"by_path": {<abspath>: <sl_id>}, "by_id": {<sl_id>: <abspath>}}`，跨本 session 多次 prompt **累積**。
- used 事件：append `runtime/ledger/memory_usage.jsonl`，`{"ts","session_id","tool","project","sl_id","path","source":"read","offered":bool}`。

---

## Task 1: 純檢索助手 `retrieval.py`

**Files:**
- Create: `paulshaclaw/memory/retrieval.py`
- Test: `paulshaclaw/memory/tests/test_retrieval.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_retrieval.py
import sqlite3
from paulshaclaw.memory.retrieval import to_fts_query, format_shortlist


def test_to_fts_query_neutralizes_fts5_specials():
    q = to_fts_query('fix the "bug" (AND* core)')
    # must not raise when used as a MATCH query against an fts5 table
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(body)")
    conn.execute("INSERT INTO t VALUES ('fixing the bug in core')")
    rows = conn.execute("SELECT rowid FROM t WHERE t MATCH ?", [q]).fetchall()
    assert rows  # 'fix'/'bug'/'core' OR-match the row
    conn.close()


def test_to_fts_query_drops_short_latin_and_slashes():
    assert to_fts_query("/effort") == ""        # slash command body -> only 'effort'? see below
    assert to_fts_query("a b c") == ""           # all 1-char latin dropped
    assert to_fts_query("") == ""


def test_to_fts_query_keeps_cjk_runs():
    q = to_fts_query("記憶系統 怎麼 retitle")
    assert '"記憶系統"' in q and '"retitle"' in q


def test_format_shortlist_lines():
    out = format_shortlist([
        {"title": "SerialWrap Exec", "summary": "抽象 UART 執行層", "path": "/m/knowledge/x/a.md"},
        {"title": "P4 Split", "summary": "實體 repo 拆分", "path": "/m/knowledge/x/b.md"},
    ])
    assert "/m/knowledge/x/a.md" in out and "/m/knowledge/x/b.md" in out
    assert "Read" in out  # contains the hint
    assert out.count("\n- ") == 2


def test_format_shortlist_empty_is_empty_string():
    assert format_shortlist([]) == ""
```

> 註：`to_fts_query("/effort")` 期望為空——`/effort` 抽出 token `effort`(6字)會非空。為符合「trivial 不注入」，**slash-command 過濾在 hook 層**（Task 3 step：`prompt.lstrip().startswith("/")` → skip），`to_fts_query` 不負責。請將該斷言改為 `assert to_fts_query("/effort") == '"effort"'` 以反映純函式真實行為。

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_retrieval.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'paulshaclaw.memory.retrieval'`）

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/retrieval.py
"""Pure retrieval helpers (no IO): FTS query sanitization + shortlist formatting."""
from __future__ import annotations

import re

# alnum/underscore runs, or contiguous CJK runs
_TOKEN = re.compile(r"[0-9A-Za-z_]+|[一-鿿]+")

_SHORTLIST_HINT = "> 與當前任務相關的記憶（相關項用 Read 開啟下列絕對路徑取全文）："


def to_fts_query(prompt: str) -> str:
    """Build a safe FTS5 MATCH query from arbitrary prompt text.

    Extracts alnum/CJK tokens, drops 1-char latin tokens, quotes each token as
    an FTS5 string literal (neutralizing operators), and OR-joins them. Empty or
    token-less input returns "" (caller treats as 'do not search').
    """
    if not prompt:
        return ""
    toks = [t for t in _TOKEN.findall(prompt) if (len(t) >= 2 or not t.isascii())]
    if not toks:
        return ""
    return " OR ".join(f'"{t}"' for t in toks)


def format_shortlist(hits: list[dict]) -> str:
    """Render hits ({title, summary, path}) as an injected shortlist block. [] -> ''."""
    if not hits:
        return ""
    lines = [_SHORTLIST_HINT]
    for h in hits:
        title = (h.get("title") or "").strip() or "(untitled)"
        summary = (h.get("summary") or "").strip()
        path = h.get("path") or ""
        lines.append(f"- [{title}] — {summary} — {path}")
    return "\n".join(lines)
```

- [ ] **Step 4: Adjust the slash assertion then run to verify pass**

在 test 中將 `assert to_fts_query("/effort") == ""` 改為 `assert to_fts_query("/effort") == '"effort"'`。
Run: `python3 -m pytest paulshaclaw/memory/tests/test_retrieval.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/retrieval.py paulshaclaw/memory/tests/test_retrieval.py
git commit -m "feat(memory): retrieval.py 純函式 to_fts_query + format_shortlist"
```

---

## Task 2: `search.py` 加 `path` 欄並回傳

**Files:**
- Modify: `paulshaclaw/memory/moc/search.py`
- Test: `paulshaclaw/memory/tests/test_moc_search.py`

- [ ] **Step 1: Write the failing test**（append 到既有 test 檔）

```python
def test_build_index_and_search_return_path(tmp_path):
    from paulshaclaw.memory.moc import search as S
    mr = tmp_path
    k = mr / "knowledge" / "proj"
    k.mkdir(parents=True)
    note = k / "serialwrap.md"
    note.write_text(
        "---\nmemory_layer: knowledge\nslice_id: sl-aaaaaaaaaaaaaaaa\n"
        "project: proj\ntitle: SerialWrap\ncaptured_at: '2026-06-29T00:00:00Z'\n---\n"
        "SerialWrap 執行抽象設計\n", encoding="utf-8")
    S.build_index(mr, link_weights={})
    hits = S.search(mr, '"SerialWrap"', project="proj", limit=5, include_decayed=True)
    assert hits and hits[0]["slice_id"] == "sl-aaaaaaaaaaaaaaaa"
    assert hits[0]["path"] == str(note)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_moc_search.py::test_build_index_and_search_return_path -v`
Expected: FAIL（`KeyError: 'path'`）

- [ ] **Step 3: Replace `build_index` and `search` in `search.py`**

`build_index` 改為（threads `path` through `rows` 與 `slice_meta`）：

```python
def build_index(memory_root: Path, link_weights: dict[str, int]) -> None:
    path = index_path(memory_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE VIRTUAL TABLE slices_fts USING fts5("
                     "slice_id UNINDEXED, project, title, tags, body, tokenize='unicode61')")
        conn.execute("CREATE TABLE slice_meta (slice_id TEXT PRIMARY KEY, project TEXT, "
                     "captured_at TEXT, active INTEGER, link_weight INTEGER, path TEXT)")
        knowledge = memory_root / "knowledge"
        events = lifecycle.read_events(memory_root)

        def flush_batch(rows: list[tuple[str, str, str, str, str, str, str]]) -> None:
            if not rows:
                return
            active = set(
                retrieval_set.active_records(
                    memory_root, [row[0] for row in rows], events=events,
                )
            )
            conn.executemany(
                "INSERT INTO slices_fts VALUES (?,?,?,?,?)",
                [(sid, project, title, tags, body)
                 for sid, project, title, tags, body, _ca, _p in rows],
            )
            conn.executemany(
                "INSERT INTO slice_meta VALUES (?,?,?,?,?,?)",
                [(sid, project, captured_at, 1 if sid in active else 0,
                  link_weights.get(sid, 0), fpath)
                 for sid, project, _title, _tags, _body, captured_at, fpath in rows],
            )

        rows: list[tuple[str, str, str, str, str, str, str]] = []
        if knowledge.exists():
            for fpath in sorted(knowledge.rglob("*.md")):
                fm, body = fio.read(fpath.read_text(encoding="utf-8"))
                if fm.get("memory_layer") != "knowledge":
                    continue
                sid = fm.get("slice_id")
                if not sid:
                    continue
                rows.append((str(sid), str(fm.get("project", "")), str(fm.get("title", "")),
                             " ".join(fm.get("tags", []) if isinstance(fm.get("tags"), list) else []),
                             body, str(fm.get("captured_at", "")), str(fpath)))
                if len(rows) >= INDEX_WRITE_BATCH_SIZE:
                    flush_batch(rows)
                    rows.clear()
        flush_batch(rows)
        conn.commit()
    finally:
        conn.close()
```

`search` 改 SELECT 與回傳含 `path`：

```python
def search(memory_root: Path, query: str, *, project: str | None, limit: int,
           include_decayed: bool) -> list[dict]:
    path = index_path(memory_root)
    if not path.exists():
        raise SearchIndexError("search index not built; run the dream/moc pass first")
    conn = sqlite3.connect(path)
    try:
        sql = ("SELECT f.slice_id, m.project, f.title, bm25(slices_fts) AS bm, "
               "m.link_weight, m.active, m.path "
               "FROM slices_fts f JOIN slice_meta m ON m.slice_id = f.slice_id "
               "WHERE slices_fts MATCH ?")
        params: list[object] = [query]
        if project:
            sql += " AND m.project = ?"
            params.append(project)
        if not include_decayed:
            sql += " AND m.active = 1"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        raise SearchIndexError(f"search failed: {exc}") from exc
    finally:
        conn.close()
    ranked = sorted(rows, key=lambda r: (r[3] - 0.1 * (r[4] or 0)))
    return [{"slice_id": r[0], "project": r[1], "title": r[2], "score": r[3], "path": r[6]}
            for r in ranked[:limit]]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_moc_search.py -v`
Expected: PASS（含新測試；既有 search 測試仍綠）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/moc/search.py paulshaclaw/memory/tests/test_moc_search.py
git commit -m "feat(memory): search index 加 path 欄並於 search() 回傳"
```

---

## Task 3: 短清單編排 + offered 記錄 `_shortlist_common.py`

**Files:**
- Create: `paulshaclaw/memory/hooks/_shortlist_common.py`
- Test: `paulshaclaw/memory/tests/test_shortlist_common.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_shortlist_common.py
import json
from pathlib import Path
from paulshaclaw.memory.moc import search as S
from paulshaclaw.memory.hooks import _shortlist_common as SC


def _seed(mr: Path):
    k = mr / "knowledge" / "proj"
    k.mkdir(parents=True)
    (k / "a.md").write_text(
        "---\nmemory_layer: knowledge\nslice_id: sl-aaaaaaaaaaaaaaaa\nproject: proj\n"
        "title: SerialWrap\ncaptured_at: '2026-06-29T00:00:00Z'\n---\n抽象 UART 執行層\n",
        encoding="utf-8")
    S.build_index(mr, link_weights={})


def test_shortlist_injects_and_records_offered(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "resolve_project", lambda cwd, memory_root: "proj")
    _seed(tmp_path)
    out = SC.build_shortlist_and_record(tmp_path, "claude-code", "sid1", cwd="/x", prompt="SerialWrap 執行")
    note = str(tmp_path / "knowledge" / "proj" / "a.md")
    assert note in out and "Read" in out
    # offered ledger
    led = (tmp_path / "runtime" / "ledger" / "offered.jsonl").read_text(encoding="utf-8")
    assert "sl-aaaaaaaaaaaaaaaa" in led and note in led
    # per-session map accumulates both directions
    m = json.loads((tmp_path / "runtime" / "wakeup" / "claude-code__sid1.offered.json").read_text())
    assert m["by_path"][note] == "sl-aaaaaaaaaaaaaaaa"
    assert m["by_id"]["sl-aaaaaaaaaaaaaaaa"] == note


def test_shortlist_skips_slash_command(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "resolve_project", lambda cwd, memory_root: "proj")
    _seed(tmp_path)
    assert SC.build_shortlist_and_record(tmp_path, "claude-code", "s", cwd="/x", prompt="/effort ultra") == ""


def test_shortlist_unknown_project_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "resolve_project", lambda cwd, memory_root: "_unknown")
    assert SC.build_shortlist_and_record(tmp_path, "claude-code", "s", cwd="/x", prompt="anything") == ""


def test_shortlist_no_match_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(SC, "resolve_project", lambda cwd, memory_root: "proj")
    _seed(tmp_path)
    assert SC.build_shortlist_and_record(tmp_path, "claude-code", "s", cwd="/x", prompt="zzzznomatch") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_shortlist_common.py -v`
Expected: FAIL（`ModuleNotFoundError ... _shortlist_common`）

- [ ] **Step 3: Write implementation**

```python
# paulshaclaw/memory/hooks/_shortlist_common.py
"""Prompt-time shortlist: bm25 search -> shortlist injection + offered recording. Best-effort IO."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from paulshaclaw.memory.importer.project_resolver import resolve_project
from paulshaclaw.memory.moc import search as search_mod
from paulshaclaw.memory.retrieval import format_shortlist, to_fts_query
from paulshaclaw.memory.hooks._wakeup_common import log_warn, sanitize_id

SHORTLIST_K = 3


def _summary(path: str) -> str:
    """First meaningful (non-frontmatter, non-empty) body line, for the shortlist."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    lines = text.splitlines()
    # skip YAML frontmatter if present
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
        lines = lines[end + 1:]
    for ln in lines:
        s = ln.strip()
        if s:
            return s.lstrip("# ").strip()
    return ""


def _record_offered(root: Path, tool: str, session_id: str, project: str,
                    offered: list[tuple[str, str]]) -> None:
    """Append offered ledger + accumulate per-session sl_id<->path map. Best-effort."""
    try:
        led_dir = root / "runtime" / "ledger"
        led_dir.mkdir(parents=True, exist_ok=True)
        ev = {"ts": datetime.now(timezone.utc).isoformat(), "session_id": session_id,
              "tool": tool, "project": project,
              "offered": [{"sl_id": sid, "path": p} for sid, p in offered]}
        with (led_dir / "offered.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

        wk_dir = root / "runtime" / "wakeup"
        wk_dir.mkdir(parents=True, exist_ok=True)
        mpath = wk_dir / f"{tool}__{sanitize_id(session_id)}.offered.json"
        cur = {"by_path": {}, "by_id": {}}
        if mpath.exists():
            try:
                cur = json.loads(mpath.read_text(encoding="utf-8"))
            except Exception:
                cur = {"by_path": {}, "by_id": {}}
        for sid, p in offered:
            cur["by_path"][p] = sid
            cur["by_id"][sid] = p
        tmp = mpath.with_name(f".{mpath.name}.tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        tmp.replace(mpath)
    except Exception as exc:
        log_warn(root, tool, f"failed to record offered: {exc}")


def build_shortlist_and_record(root: Path, tool: str, session_id: str,
                               cwd: str | None, prompt: str) -> str:
    """Resolve project, search by prompt, build shortlist, record offered. Returns '' if nothing."""
    try:
        if not prompt or prompt.lstrip().startswith("/"):
            return ""
        project = resolve_project(cwd=cwd, memory_root=str(root))
        if project in ("_unknown", ""):
            return ""
        query = to_fts_query(prompt)
        if not query:
            return ""
        try:
            hits = search_mod.search(root, query, project=project,
                                     limit=SHORTLIST_K, include_decayed=False)
        except search_mod.SearchIndexError:
            return ""
        if not hits:
            return ""
        for h in hits:
            h["summary"] = _summary(h.get("path", ""))
        block = format_shortlist(hits)
        offered = [(h["slice_id"], h["path"]) for h in hits if h.get("path")]
        _record_offered(root, tool, session_id, project, offered)
        return block
    except Exception as exc:
        log_warn(root, tool, f"shortlist failed: {exc}")
        return ""
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_shortlist_common.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/hooks/_shortlist_common.py paulshaclaw/memory/tests/test_shortlist_common.py
git commit -m "feat(memory): _shortlist_common 任務檢索短清單 + offered 記錄"
```

---

## Task 4: UserPromptSubmit hook entrypoint

**Files:**
- Create: `paulshaclaw/memory/hooks/claude_user_prompt_submit.py`
- Test: `paulshaclaw/memory/tests/test_user_prompt_submit_hook.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_user_prompt_submit_hook.py
import json, subprocess, sys
from pathlib import Path

HOOK = Path("paulshaclaw/memory/hooks/claude_user_prompt_submit.py").resolve()


def _seed(mr: Path):
    from paulshaclaw.memory.moc import search as S
    k = mr / "knowledge" / "proj"; k.mkdir(parents=True)
    (k / "a.md").write_text(
        "---\nmemory_layer: knowledge\nslice_id: sl-aaaaaaaaaaaaaaaa\nproject: proj\n"
        "title: SerialWrap\ncaptured_at: '2026-06-29T00:00:00Z'\n---\n抽象 UART 執行層\n",
        encoding="utf-8")
    S.build_index(mr, link_weights={})


def _run(mr: Path, payload: dict) -> dict:
    env = {"PSC_MEMORY_ROOT": str(mr), "PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path.cwd())}
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else {}


def test_relevant_prompt_injects_shortlist(tmp_path, monkeypatch):
    _seed(tmp_path)
    # resolve_project depends on cwd; point cwd at a dir whose folder name == 'proj'
    proj_cwd = tmp_path / "proj"; proj_cwd.mkdir(exist_ok=True)
    out = _run(tmp_path, {"hook_event_name": "UserPromptSubmit", "session_id": "s1",
                          "cwd": str(proj_cwd), "prompt": "SerialWrap 執行"})
    ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "a.md" in ctx and "Read" in ctx


def test_error_or_unknown_emits_empty_and_exit0(tmp_path):
    out = _run(tmp_path, {"hook_event_name": "UserPromptSubmit", "session_id": "s2",
                          "cwd": "/nonexistent", "prompt": "anything"})
    assert out.get("hookSpecificOutput", {}).get("additionalContext", "") == ""
```

> 註：`resolve_project` 對「無 git、資料夾名」會回 folder name；測試用 cwd 結尾 `proj` 使其解析為 `proj`。若 `resolve_project` 行為與此不符，改用 `monkeypatch` 注入（如 Task 3）或設定 project root。

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_user_prompt_submit_hook.py -v`
Expected: FAIL（hook 檔不存在）

- [ ] **Step 3: Write implementation**（鏡像既有 `claude_session_start.py` 結構）

```python
#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook: inject task-relevant memory shortlist.

Reads stdin JSON (UserPromptSubmit payload), resolves project from cwd, searches
the prompt against the project's bm25 index, and emits a top-k shortlist (title ·
summary · absolute path) as additionalContext. Any error -> empty context, exit 0.
"""
from __future__ import annotations

import json
import sys

import _bootstrap  # sibling module; hooks dir is on sys.path[0]

_bootstrap.ensure_repo_on_path()

TOOL = "claude-code"


def main() -> int:
    from paulshaclaw.memory.hooks._shortlist_common import build_shortlist_and_record
    from paulshaclaw.memory.hooks._wakeup_common import log_warn, memory_root, read_payload

    root = memory_root()
    payload = read_payload(root, TOOL)
    context = ""
    try:
        cwd = payload.get("cwd")
        session_id = str(payload.get("session_id") or "unknown")
        prompt = str(payload.get("prompt") or "")
        context = build_shortlist_and_record(root, TOOL, session_id, cwd, prompt)
    except Exception as exc:
        log_warn(root, TOOL, f"user_prompt_submit failed: {exc}")
        context = ""

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_user_prompt_submit_hook.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/hooks/claude_user_prompt_submit.py paulshaclaw/memory/tests/test_user_prompt_submit_hook.py
git commit -m "feat(memory): claude UserPromptSubmit hook 注入任務短清單"
```

---

## Task 5: PostToolUse(Read) 讀取歸因 hook

**Files:**
- Create: `paulshaclaw/memory/hooks/claude_post_tool_use.py`
- Test: `paulshaclaw/memory/tests/test_post_tool_use_hook.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_post_tool_use_hook.py
import json, subprocess, sys
from pathlib import Path

HOOK = Path("paulshaclaw/memory/hooks/claude_post_tool_use.py").resolve()


def _map(mr: Path, sid: str, path: str, slid: str):
    wk = mr / "runtime" / "wakeup"; wk.mkdir(parents=True, exist_ok=True)
    (wk / f"claude-code__{sid}.offered.json").write_text(
        json.dumps({"by_path": {path: slid}, "by_id": {slid: path}}), encoding="utf-8")


def _run(mr: Path, payload: dict):
    env = {"PSC_MEMORY_ROOT": str(mr), "PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path.cwd())}
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr


def _events(mr: Path):
    f = mr / "runtime" / "ledger" / "memory_usage.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def test_read_offered_knowledge_path_records_used(tmp_path):
    note = tmp_path / "knowledge" / "proj" / "a.md"; note.parent.mkdir(parents=True)
    note.write_text("---\nslice_id: sl-aaaaaaaaaaaaaaaa\n---\nx\n", encoding="utf-8")
    _map(tmp_path, "s1", str(note), "sl-aaaaaaaaaaaaaaaa")
    _run(tmp_path, {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Read",
                    "tool_input": {"file_path": str(note)}, "cwd": "/x"})
    ev = _events(tmp_path)
    assert len(ev) == 1 and ev[0]["source"] == "read" and ev[0]["offered"] is True
    assert ev[0]["sl_id"] == "sl-aaaaaaaaaaaaaaaa"


def test_read_non_offered_knowledge_records_offered_false(tmp_path):
    note = tmp_path / "knowledge" / "proj" / "b.md"; note.parent.mkdir(parents=True)
    note.write_text("---\nslice_id: sl-bbbbbbbbbbbbbbbb\n---\nx\n", encoding="utf-8")
    _run(tmp_path, {"hook_event_name": "PostToolUse", "session_id": "s9", "tool_name": "Read",
                    "tool_input": {"file_path": str(note)}, "cwd": "/x"})
    ev = _events(tmp_path)
    assert len(ev) == 1 and ev[0]["offered"] is False and ev[0]["sl_id"] == "sl-bbbbbbbbbbbbbbbb"


def test_read_non_knowledge_path_no_event(tmp_path):
    other = tmp_path / "elsewhere.md"; other.write_text("hi", encoding="utf-8")
    _run(tmp_path, {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Read",
                    "tool_input": {"file_path": str(other)}, "cwd": "/x"})
    assert _events(tmp_path) == []


def test_non_read_tool_no_event(tmp_path):
    _run(tmp_path, {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Bash",
                    "tool_input": {"command": "ls"}, "cwd": "/x"})
    assert _events(tmp_path) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_post_tool_use_hook.py -v`
Expected: FAIL（hook 檔不存在）

- [ ] **Step 3: Write implementation**

```python
#!/usr/bin/env python3
"""Claude Code PostToolUse(Read) hook: record read-based memory usage attribution.

When a Read targets a path under <memory_root>/knowledge/, append a `used` event
(source="read", offered=bool) to memory_usage.jsonl. Any error -> no event, exit 0.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # sibling module; hooks dir is on sys.path[0]

_bootstrap.ensure_repo_on_path()

TOOL = "claude-code"
_SLICE_FM = re.compile(r"^slice_id:\s*(\S+)", re.MULTILINE)
_PROJECT_FM = re.compile(r"^project:\s*(\S+)", re.MULTILINE)


def _frontmatter_field(path: Path, pattern: re.Pattern) -> str:
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:2000]
    except Exception:
        return ""
    m = pattern.search(head)
    return m.group(1).strip().strip("'\"") if m else ""


def main() -> int:
    from paulshaclaw.memory.hooks._wakeup_common import (
        log_warn, memory_root, read_payload, sanitize_id,
    )

    root = memory_root()
    payload = read_payload(root, TOOL)
    try:
        if payload.get("tool_name") != "Read":
            return 0
        fp = (payload.get("tool_input") or {}).get("file_path")
        if not fp:
            return 0
        p = Path(fp).resolve()
        knowledge = (root / "knowledge").resolve()
        if knowledge not in p.parents:
            return 0

        session_id = str(payload.get("session_id") or "unknown")
        mpath = root / "runtime" / "wakeup" / f"{TOOL}__{sanitize_id(session_id)}.offered.json"
        by_path = {}
        if mpath.exists():
            try:
                by_path = json.loads(mpath.read_text(encoding="utf-8")).get("by_path", {})
            except Exception:
                by_path = {}

        sl_id = by_path.get(str(p)) or _frontmatter_field(p, _SLICE_FM)
        offered = str(p) in by_path
        project = _frontmatter_field(p, _PROJECT_FM)

        ev = {"ts": datetime.now(timezone.utc).isoformat(), "session_id": session_id,
              "tool": TOOL, "project": project, "sl_id": sl_id, "path": str(p),
              "source": "read", "offered": offered}
        led_dir = root / "runtime" / "ledger"
        led_dir.mkdir(parents=True, exist_ok=True)
        with (led_dir / "memory_usage.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception as exc:
        log_warn(root, TOOL, f"post_tool_use failed: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_post_tool_use_hook.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/hooks/claude_post_tool_use.py paulshaclaw/memory/tests/test_post_tool_use_hook.py
git commit -m "feat(memory): claude PostToolUse(Read) 讀取歸因 hook"
```

---

## Task 6: 部署接線（install.sh + settings.json）

**Files:**
- Modify: `paulshaclaw/memory/hooks/install.sh`
- Modify (deploy): `~/.claude/settings.json`

- [ ] **Step 1: install.sh 納入新 hook**

在 `install.sh` 複製 `*_session_*.py` 的清單處，加入 `claude_user_prompt_submit.py` 與 `claude_post_tool_use.py`（與既有 hook 同樣 `chmod 700` 複製到 `~/.agents/memory/hooks/`）。定位：搜尋 `claude_session_start.py` 出現處，於同一複製清單/迴圈加入兩個新檔名。

- [ ] **Step 2: 重新同步 hooks**

Run: `bash paulshaclaw/memory/hooks/install.sh`
Expected: `~/.agents/memory/hooks/claude_user_prompt_submit.py` 與 `claude_post_tool_use.py` 存在。
Verify: `ls -1 ~/.agents/memory/hooks/claude_user_prompt_submit.py ~/.agents/memory/hooks/claude_post_tool_use.py`

- [ ] **Step 3: settings.json 接線**（與 codegraph 並存）

於 `~/.claude/settings.json` 的 `hooks.UserPromptSubmit` 陣列**新增**一個 entry（不動既有 `codegraph prompt-hook`）：

```json
{ "hooks": [ { "type": "command", "command": "PSC_MEMORY_ROOT=/home/paul_chen/.agents/memory PSC_CONFIG_ROOT=/home/paul_chen /home/paul_chen/.agents/memory/hooks/.venv/bin/python /home/paul_chen/.agents/memory/hooks/claude_user_prompt_submit.py", "timeout": 10 } ] }
```

於 `hooks.PostToolUse` 新增（matcher 限 `Read`）：

```json
{ "matcher": "Read", "hooks": [ { "type": "command", "command": "PSC_MEMORY_ROOT=/home/paul_chen/.agents/memory PSC_CONFIG_ROOT=/home/paul_chen /home/paul_chen/.agents/memory/hooks/.venv/bin/python /home/paul_chen/.agents/memory/hooks/claude_post_tool_use.py", "timeout": 10 } ] }
```

- [ ] **Step 4: 重建檢索 index（新 schema 需重建一次）**

Run: `~/.agents/memory/hooks/.venv/bin/python -c "from pathlib import Path; from paulshaclaw.memory.moc import search; search.build_index(Path('/home/paul_chen/.agents/memory'), {})"`
Expected: 無輸出、`retrieval.db` 重建（含 `path` 欄）。
> 或等下一輪 hourly dream 自動重建。

- [ ] **Step 5: Commit**（install.sh；settings.json 在 `~/.claude` 不在 repo，不 commit）

```bash
git add paulshaclaw/memory/hooks/install.sh
git commit -m "chore(memory): install.sh 同步 UserPromptSubmit/PostToolUse hook"
```

---

## Task 7: 回歸與端到端驗證

**Files:** （無新檔，驗證用）

- [ ] **Step 1: 全套件回歸**

Run: `python3 -m pytest paulshaclaw/memory/tests/ -q`
Expected: 既有 747 + 新增測試全綠（PASS）。

- [ ] **Step 2: 端到端手測（真實 session）**

開新 claude session（cwd 在某有 knowledge 的 project），送一個與某筆 knowledge 相關的 prompt。
Expected：context 出現「與當前任務相關的記憶」短清單（含絕對路徑）。
接著對清單中的某絕對路徑用 Read。
Verify: `tail -1 ~/.agents/memory/runtime/ledger/memory_usage.jsonl` → 一筆 `"source":"read","offered":true` 事件。

- [ ] **Step 3: trivial prompt 不注入**

於同 session 送 `/effort` 或純標點。
Expected：無短清單注入（context 空）。

- [ ] **Step 4: 主流程未受影響**

Verify：`~/.agents/memory/runtime/ledger/dream.jsonl` 最新一筆 `errors:[]`；SessionStart brief 仍正常（本計畫未動 brief）。

---

## Self-Review

- **Spec 覆蓋**（對 `stage2-memory-prompt-retrieval` / `stage2-memory-read-attribution`）：任務短清單注入=Task 3+4；to_fts_query 淨化=Task 1；per-prompt offered + 映射=Task 3；read-based 歸因 + path/sl_id 對齊=Task 5。`stage2-memory-readback` / `usage-telemetry` / `noise-governance` 的 delta 屬 **Plan 2**，本計畫不涵蓋（已於 Scope note 標明）。
- **Placeholder**：無 TODO/TBD；每步含完整碼與指令。
- **型別/命名一致**：`build_shortlist_and_record(root,tool,session_id,cwd,prompt)`、`search()` 回傳含 `path`、offered 映射檔 `<tool>__<sid>.offered.json` 的 `by_path`/`by_id`、used 事件欄位 `sl_id/path/source/offered`——跨 Task 1-7 一致。
- **已知取捨**（spec A2/A4/A5）：CJK 以 unicode61 整段為 token（recall 受限、不報錯）；relevance gate MVP=「有命中 + k=3」無分數門檻；歸因 Claude-only。
