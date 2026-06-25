# Memory Usage Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立記憶消費端 usage 訊號管道——每 session 記 offered slice、claude session 記 used（cited+matched），落 durable ledger 並提供 `psc memory usage` 查詢。

**Architecture:** 純函式 `usage.py`（extract_offered/cited/matched）為單一真相源；SessionStart 共用 hook 記 offered + brief 帶引用前言；claude SessionEnd 掃 assistant transcript 算 used → `runtime/ledger/memory_usage.jsonl`（event 存 offered id 陣列、self-sufficient）；CLI 僅讀 ledger 聚合。

**Tech Stack:** Python 3.12、pytest（`~/.local/bin/pytest`，`.venv` 無 pytest）、現有 memory hooks。

**Spec:** `docs/superpowers/specs/2026-06-25-memory-usage-telemetry-design.md`｜OpenSpec `stage2-memory-usage-telemetry`

執行測試一律：`cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. python3 -m pytest <path> -q`

---

## File Structure

- Create: `paulshaclaw/memory/usage.py` — 三純函式 + 引用前言常數。
- Modify: `paulshaclaw/memory/hooks/_wakeup_common.py` — compute_brief 加前言 + offered 寫入。
- Modify: `paulshaclaw/memory/hooks/claude_session_end.py` — SessionEnd 加 usage 擷取。
- Modify: `paulshaclaw/memory/cli.py` — 加 `memory usage` 子命令。
- Test: `paulshaclaw/memory/tests/test_usage.py`、`test_wakeup_offered.py`、`test_session_end_usage.py`、`test_memory_usage_cli.py`。

---

## Task 1: usage.py 純函式

**Files:**
- Create: `paulshaclaw/memory/usage.py`
- Test: `paulshaclaw/memory/tests/test_usage.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_usage.py
from __future__ import annotations

import unittest

from paulshaclaw.memory.usage import extract_offered, extract_cited, extract_matched


_BRIEF = (
    "# Memory wake-up\n\n"
    "- [[llm-atomizer-core--sl-7be63668250fff95|LLM Atomizer Technical Specification]] — spec\n"
    "- [[phase-2a--sl-c1e80dbdadedb8cf|Phase 2a Promoter Integration]] — ship\n"
)


class ExtractOfferedTests(unittest.TestCase):
    def test_extracts_id_and_title_pairs(self):
        offered = extract_offered(_BRIEF)
        self.assertIn(("sl-7be63668250fff95", "LLM Atomizer Technical Specification"), offered)
        self.assertIn(("sl-c1e80dbdadedb8cf", "Phase 2a Promoter Integration"), offered)

    def test_malformed_brief_returns_empty(self):
        self.assertEqual(extract_offered("no wikilinks here"), [])


class ExtractCitedTests(unittest.TestCase):
    def test_cites_offered_ids_only(self):
        offered_ids = {"sl-7be63668250fff95", "sl-c1e80dbdadedb8cf"}
        text = "我參考了 [[sl-7be63668250fff95]] 與不存在的 sl-aaaaaaaaaaaaaaaa。"
        self.assertEqual(extract_cited(text, offered_ids), {"sl-7be63668250fff95"})

    def test_bare_id_also_counts(self):
        offered_ids = {"sl-c1e80dbdadedb8cf"}
        self.assertEqual(extract_cited("見 sl-c1e80dbdadedb8cf", offered_ids), {"sl-c1e80dbdadedb8cf"})


class ExtractMatchedTests(unittest.TestCase):
    def test_title_match_excludes_short_and_cited(self):
        offered = [
            ("sl-7be63668250fff95", "LLM Atomizer Technical Specification"),  # long
            ("sl-c1e80dbdadedb8cf", "Phase 2a Promoter Integration"),          # long
            ("sl-1111111111111111", "spec"),                                   # < 8 chars
        ]
        text = "本次用到 LLM Atomizer Technical Specification 與 Phase 2a Promoter Integration；spec 是巧合。"
        matched = extract_matched(text, offered, exclude={"sl-c1e80dbdadedb8cf"})
        self.assertEqual(matched, {"sl-7be63668250fff95"})  # short excluded, cited excluded


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python3 -m pytest paulshaclaw/memory/tests/test_usage.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'paulshaclaw.memory.usage'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/usage.py
"""Memory consumption telemetry helpers (#148). Pure functions, no IO."""

from __future__ import annotations

import re

# Prepended to a non-empty wake-up brief so agents can mark which memories they used.
CITATION_PREAMBLE = (
    "> 記憶使用追蹤：若你在本次工作中參考了下列任一條記憶，請在回覆中標註其 "
    "`[[sl-xxxxxxxxxxxxxxxx]]`（16-hex id），以便評估記憶實際效用。\n\n"
)

_SLICE_ID = re.compile(r"sl-[0-9a-f]{16}")
_WIKILINK = re.compile(r"\[\[([^\]|]+)\|([^\]]*)\]\]")
_MATCH_MIN_TITLE = 8


def extract_offered(brief: str) -> list[tuple[str, str]]:
    """Extract (slice_id, title) pairs from a brief's [[stem--sl-id|title]] wikilinks."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for target, title in _WIKILINK.findall(brief):
        m = _SLICE_ID.search(target)
        if not m or m.group(0) in seen:
            continue
        seen.add(m.group(0))
        out.append((m.group(0), title.strip()))
    return out


def extract_cited(assistant_text: str, offered_ids) -> set[str]:
    """Slice ids the agent explicitly referenced (in [[..]] or bare) that were offered."""
    offered = set(offered_ids)
    return {sid for sid in _SLICE_ID.findall(assistant_text or "") if sid in offered}


def extract_matched(assistant_text: str, offered, *, exclude=()) -> set[str]:
    """Offered ids whose (>=8 char) title appears verbatim in assistant text, minus exclude."""
    text = assistant_text or ""
    skip = set(exclude)
    out: set[str] = set()
    for sid, title in offered:
        t = (title or "").strip()
        if sid in skip or len(t) < _MATCH_MIN_TITLE:
            continue
        if t in text:
            out.add(sid)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python3 -m pytest paulshaclaw/memory/tests/test_usage.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/usage.py paulshaclaw/memory/tests/test_usage.py
git commit -m "feat(memory): #148 usage 純函式 extract_offered/cited/matched

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: SessionStart offered + 引用前言

**Files:**
- Modify: `paulshaclaw/memory/hooks/_wakeup_common.py`
- Test: `paulshaclaw/memory/tests/test_wakeup_offered.py`

讀現有 `_wakeup_common.py` 的 `compute_brief`（接受 `root, cwd`，回 brief 字串）。新增一個 `compute_brief_and_record(root, tool, session_id, cwd)`：算 brief、非空時前置 `CITATION_PREAMBLE`、抽 offered 寫 `runtime/wakeup/<tool>__<sid>.json`，回（可能帶前言的）brief。各 `*_session_start.py` 不在本任務改（保持 `compute_brief` 相容；hook 串接於部署時另行，超出本資料管線任務——本任務只交付可測的 record 函式）。

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_wakeup_offered.py
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from paulshaclaw.memory.hooks import _wakeup_common as wc


class WakeupOfferedTests(unittest.TestCase):
    def test_non_empty_brief_gets_preamble_and_writes_offered(self):
        brief = "# wake\n- [[foo--sl-1234567890abcdef|Some Title]] — spec\n"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(wc, "compute_brief", return_value=brief):
                out = wc.compute_brief_and_record(root, "claude-code", "sess1", cwd="/x")
            self.assertTrue(out.startswith("> 記憶使用追蹤"))
            offered_file = root / "runtime" / "wakeup" / "claude-code__sess1.json"
            self.assertTrue(offered_file.exists())
            data = json.loads(offered_file.read_text(encoding="utf-8"))
            self.assertEqual(data["offered"], [{"id": "sl-1234567890abcdef", "title": "Some Title"}])

    def test_empty_brief_no_preamble_no_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(wc, "compute_brief", return_value=""):
                out = wc.compute_brief_and_record(root, "claude-code", "sess2", cwd="/x")
            self.assertEqual(out, "")
            self.assertFalse((root / "runtime" / "wakeup" / "claude-code__sess2.json").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python3 -m pytest paulshaclaw/memory/tests/test_wakeup_offered.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'compute_brief_and_record'`

- [ ] **Step 3: Write minimal implementation**

在 `paulshaclaw/memory/hooks/_wakeup_common.py` 末尾加（頂部 import 區補 `from paulshaclaw.memory.usage import CITATION_PREAMBLE, extract_offered`）：

```python
def compute_brief_and_record(root: Path, tool: str, session_id: str, cwd: str | None) -> str:
    """Compute brief, prepend citation preamble, record offered slices. Best-effort."""
    brief = compute_brief(root, cwd)
    if not brief:
        return ""
    try:
        offered = extract_offered(brief)
        wakeup_dir = root / "runtime" / "wakeup"
        wakeup_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id": session_id, "tool": tool,
            "ts": datetime.now(timezone.utc).isoformat(),
            "offered": [{"id": sid, "title": title} for sid, title in offered],
        }
        path = wakeup_dir / f"{tool}__{sanitize_id(session_id)}.json"
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:  # best-effort: never break the brief
        log_warn(root, tool, f"failed to record offered: {exc}")
    return CITATION_PREAMBLE + brief
```

（`datetime`/`timezone`/`json`/`sanitize_id`/`log_warn` 皆已在該檔可用。）

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python3 -m pytest paulshaclaw/memory/tests/test_wakeup_offered.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/hooks/_wakeup_common.py paulshaclaw/memory/tests/test_wakeup_offered.py
git commit -m "feat(memory): #148 SessionStart 記 offered + brief 引用前言

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: claude SessionEnd used + ledger

**Files:**
- Create: `paulshaclaw/memory/usage_ledger.py` — transcript 解析 + event 寫入（IO，與純函式分離）
- Test: `paulshaclaw/memory/tests/test_session_end_usage.py`

把「讀 offered + 掃 transcript + 算 used + append ledger」做成可測的 `record_session_usage(root, tool, session_id, project, transcript_path)`，claude_session_end.py 之後只呼叫它（避免在 hook 進入點塞邏輯、難測）。

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_session_end_usage.py
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.usage_ledger import record_session_usage


def _offered(root: Path, tool: str, sid: str):
    d = root / "runtime" / "wakeup"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{tool}__{sid}.json").write_text(json.dumps({
        "session_id": sid, "tool": tool, "ts": "2026-06-25T00:00:00Z",
        "offered": [{"id": "sl-1234567890abcdef", "title": "Some Long Title Here"},
                    {"id": "sl-fedcba0987654321", "title": "Another Long Title Here"}],
    }, ensure_ascii=False), encoding="utf-8")


def _transcript(root: Path, lines: list[dict]) -> Path:
    p = root / "t.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    return p


class RecordUsageTests(unittest.TestCase):
    def test_writes_event_with_offered_id_array(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _offered(root, "claude-code", "s1")
            tp = _transcript(root, [
                {"type": "assistant", "message": {"role": "assistant",
                 "content": [{"type": "text", "text": "我用了 [[sl-1234567890abcdef]] 來解決。"}]}},
                {"type": "user", "message": {"role": "user",
                 "content": [{"type": "text", "text": "Another Long Title Here"}]}},  # user 不算
            ])
            record_session_usage(root, "claude-code", "s1", "paulshaclaw", str(tp))
            rows = [json.loads(l) for l in (root / "runtime" / "ledger" / "memory_usage.jsonl").read_text().splitlines() if l.strip()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["offered"], ["sl-1234567890abcdef", "sl-fedcba0987654321"])
            self.assertEqual(rows[0]["cited"], ["sl-1234567890abcdef"])
            self.assertEqual(rows[0]["matched"], [])  # title only in user turn, not assistant

    def test_missing_offered_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tp = _transcript(root, [{"type": "assistant", "message": {"role": "assistant",
                                     "content": [{"type": "text", "text": "x"}]}}])
            record_session_usage(root, "claude-code", "nope", "p", str(tp))
            self.assertFalse((root / "runtime" / "ledger" / "memory_usage.jsonl").exists())

    def test_missing_transcript_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _offered(root, "claude-code", "s3")
            record_session_usage(root, "claude-code", "s3", "p", str(root / "nope.jsonl"))
            self.assertFalse((root / "runtime" / "ledger" / "memory_usage.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python3 -m pytest paulshaclaw/memory/tests/test_session_end_usage.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'paulshaclaw.memory.usage_ledger'`

- [ ] **Step 3: Write minimal implementation**

建立 `paulshaclaw/memory/usage_ledger.py`，完整內容如下：

```python
# paulshaclaw/memory/usage_ledger.py
"""Read offered + assistant transcript → memory_usage.jsonl event. Best-effort IO (#148)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .usage import extract_cited, extract_matched

_SANITIZE = re.compile(r"[/\\:]+")


def _assistant_text(transcript_path: Path) -> str:
    chunks: list[str] = []
    for line in transcript_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else rec
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    chunks.append(str(block.get("text", "")))
    return "\n".join(chunks)


def record_session_usage(root: Path, tool: str, session_id: str, project: str,
                         transcript_path: str | None) -> None:
    try:
        sid = _SANITIZE.sub("__", session_id)
        offered_file = root / "runtime" / "wakeup" / f"{tool}__{sid}.json"
        if not offered_file.exists() or not transcript_path:
            return
        tp = Path(transcript_path)
        if not tp.exists():
            return
        offered = [(o["id"], o.get("title", ""))
                   for o in json.loads(offered_file.read_text(encoding="utf-8")).get("offered", [])]
        offered_ids = [oid for oid, _ in offered]
        text = _assistant_text(tp)
        cited = extract_cited(text, set(offered_ids))
        matched = extract_matched(text, offered, exclude=cited)
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id, "tool": tool, "project": project,
            "offered": offered_ids, "cited": sorted(cited), "matched": sorted(matched),
        }
        ledger_dir = root / "runtime" / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        with (ledger_dir / "memory_usage.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        return  # best-effort: never break the hook
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python3 -m pytest paulshaclaw/memory/tests/test_session_end_usage.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire into claude_session_end.py**

在 `paulshaclaw/memory/hooks/claude_session_end.py` 的 `main()` 寫完 queue/fire importer 後加（best-effort，包 try/except）：

```python
    try:
        from paulshaclaw.memory.usage_ledger import record_session_usage
        record_session_usage(
            root, TOOL, session_id,
            str(payload.get("project") or payload.get("cwd") or ""),
            payload.get("transcript_path"),
        )
    except Exception:
        pass
```

- [ ] **Step 6: Commit**

```bash
git add paulshaclaw/memory/usage_ledger.py paulshaclaw/memory/tests/test_session_end_usage.py paulshaclaw/memory/hooks/claude_session_end.py
git commit -m "feat(memory): #148 claude SessionEnd 擷取 used → memory_usage.jsonl

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: usage 查詢 CLI

**Files:**
- Modify: `paulshaclaw/memory/cli.py`
- Test: `paulshaclaw/memory/tests/test_memory_usage_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_memory_usage_cli.py
from __future__ import annotations

import json
import unittest
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.cli import main


def _ledger(root: Path, events: list[dict]):
    d = root / "runtime" / "ledger"
    d.mkdir(parents=True, exist_ok=True)
    (d / "memory_usage.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events), encoding="utf-8")


class UsageCliTests(unittest.TestCase):
    def test_aggregates_and_counts_never_used(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ledger(root, [
                {"ts": "2026-06-25T01:00:00Z", "session_id": "a", "offered": ["sl-aaa", "sl-bbb"],
                 "cited": ["sl-aaa"], "matched": []},
                {"ts": "2026-06-25T02:00:00Z", "session_id": "b", "offered": ["sl-bbb"],
                 "cited": [], "matched": []},
            ])
            buf = StringIO()
            with redirect_stdout(buf):
                rc = main(["memory", "usage", "--memory-root", str(root), "--json"])
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            by = {s["slice_id"]: s for s in out["slices"]}
            self.assertEqual(by["sl-aaa"]["cited_count"], 1)
            self.assertEqual(by["sl-bbb"]["offered_count"], 2)
            self.assertEqual(by["sl-bbb"]["cited_count"], 0)
            self.assertEqual(out["summary"]["never_used"], 1)   # sl-bbb offered twice, never used

    def test_works_without_wakeup_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ledger(root, [{"ts": "2026-06-25T01:00:00Z", "session_id": "a",
                            "offered": ["sl-aaa"], "cited": [], "matched": ["sl-aaa"]}])
            # no runtime/wakeup dir at all → report still correct (ledger self-sufficient)
            buf = StringIO()
            with redirect_stdout(buf):
                rc = main(["memory", "usage", "--memory-root", str(root), "--json"])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue())["summary"]["never_used"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python3 -m pytest paulshaclaw/memory/tests/test_memory_usage_cli.py -q`
Expected: FAIL — argparse `invalid choice: 'usage'`（SystemExit 2）

- [ ] **Step 3: Implement in cli.py**

在 `memory_subparsers` 區（其他 `add_parser` 旁）加：

```python
    usage_p = memory_subparsers.add_parser("usage")
    usage_p.add_argument("--memory-root", required=True)
    usage_p.add_argument("--since", default=None)
    usage_p.add_argument("--json", action="store_true")
    usage_p.set_defaults(func=_memory_usage)
```

新增 handler（與其他 `_xxx(args)` 並列；import 區若無 `json`/`Counter` 則補）：

```python
def _memory_usage(args) -> int:
    import json as _json
    from collections import defaultdict
    ledger = Path(args.memory_root) / "runtime" / "ledger" / "memory_usage.jsonl"
    rows = []
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            if args.since and str(e.get("ts", "")) < args.since:
                continue
            rows.append(e)

    agg = defaultdict(lambda: {"offered_count": 0, "cited_count": 0, "matched_count": 0, "last_used": ""})
    for e in rows:
        ts = str(e.get("ts", ""))
        for sid in e.get("offered", []):
            agg[sid]["offered_count"] += 1
        for sid in e.get("cited", []):
            agg[sid]["cited_count"] += 1
            if ts > agg[sid]["last_used"]:
                agg[sid]["last_used"] = ts
        for sid in e.get("matched", []):
            agg[sid]["matched_count"] += 1
            if ts > agg[sid]["last_used"]:
                agg[sid]["last_used"] = ts

    slices = [{"slice_id": sid, **v} for sid, v in agg.items()]
    slices.sort(key=lambda s: (s["cited_count"], s["matched_count"]), reverse=True)
    never_used = sum(1 for s in slices if s["offered_count"] > 0 and s["cited_count"] == 0 and s["matched_count"] == 0)
    summary = {"sessions": len(rows), "slices": len(slices), "never_used": never_used}
    report = {"summary": summary, "slices": slices}

    if args.json:
        print(_json.dumps(report, ensure_ascii=False))
    else:
        print(f"sessions={summary['sessions']} slices={summary['slices']} never_used={summary['never_used']}")
        for s in slices[:30]:
            print(f"  {s['slice_id']}  offered={s['offered_count']} cited={s['cited_count']} "
                  f"matched={s['matched_count']} last_used={s['last_used']}")
    return 0
```

確認 `Path` 已在 cli.py import（既有；prune-noise 已用）。

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python3 -m pytest paulshaclaw/memory/tests/test_memory_usage_cli.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/cli.py paulshaclaw/memory/tests/test_memory_usage_cli.py
git commit -m "feat(memory): #148 memory usage 查詢 CLI（僅讀 ledger 聚合）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 回歸與收尾

- [ ] **Step 1: 跑 memory 全套 pytest**

Run: `PYTHONPATH=. python3 -m pytest paulshaclaw/memory/tests/ -q -p no:cacheprovider`
Expected: 全綠（含新增四組），無回歸。

- [ ] **Step 2: requesting-code-review → 修 → re-review；archive；commit/push/PR**（pipeline Phase 7-10）

---

## Self-Review

- **Spec coverage**：Req「usage 純函式」→ Task 1；「SessionStart offered+前言」→ Task 2；「claude SessionEnd used+ledger」→ Task 3；「usage CLI」→ Task 4。四 requirement 全覆蓋。
- **Placeholder scan**：各 step 均含完整 code/指令/預期輸出，無 TODO/TBD/壞 stub。
- **Type consistency**：`extract_offered→list[(id,title)]`、`extract_cited(text,ids)→set`、`extract_matched(text,offered,exclude=)→set`、`compute_brief_and_record`、`record_session_usage`、event `offered` 為 id 陣列、CLI `slices/summary.never_used` 全文一致。
