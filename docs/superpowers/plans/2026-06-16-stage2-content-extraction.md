# Stage 2 記憶內容擷取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 Stage 2 三家 adapter 真正讀出 session 內容、import 時用本機 gemma4 為每個 session 產 ≤20 字繁中標題、並解除 atomizer 對 URL 形 project 的封鎖，使記憶從「空信封」變成「有內容＋標題」。

**Architecture:** 全部改動落在 `pip install -e` 的 `paulshaclaw.memory` 套件內（改完下次 hook 觸發即生效、不動 `~/.agents/memory/hooks/*` 部署副本）。內容擷取放 importer adapter（讀 `transcript_path`/history），標題在 importer pipeline 注入（寫入 `assistant_summary`），atomizer 以消毒函式處理斜線 project。promoter→LLM 蒸餾屬 Phase 2、不在此計畫。

**Tech Stack:** Python 3.12、pytest、本機 gemma4（`scripts/claude-gemma4`，可離線 fallback）。

**參考**：spec `docs/superpowers/specs/2026-06-16-stage2-content-extraction-design.md`；openspec `openspec/changes/stage2-content-extraction/`。

---

## File Structure

| 檔案 | 角色 | 動作 |
|---|---|---|
| `paulshaclaw/memory/importer/adapters/base.py` | 三格式 transcript reader helper＋鍵擴充 | Modify |
| `paulshaclaw/memory/importer/adapters/claude.py` | 接 `read_claude_transcript` | Modify |
| `paulshaclaw/memory/importer/adapters/codex.py` | `last_assistant_message`＋rollout prompts | Modify |
| `paulshaclaw/memory/importer/adapters/copilot.py` | history `chatMessages` | Modify |
| `paulshaclaw/memory/importer/title.py` | gemma4 標題＋fallback＋cache | Create |
| `paulshaclaw/memory/importer/pipeline.py` | 注入標題、frontmatter title | Modify |
| `paulshaclaw/memory/importer/frontmatter.py` | `title`/`title_source` 欄位 | Modify |
| `paulshaclaw/memory/importer/backfill.py` | 三家強制回填 CLI | Create |
| `paulshaclaw/memory/atomizer/config.py` | `sanitize_project_component()` | Modify |
| `paulshaclaw/memory/atomizer/pipeline.py` | 路徑改用消毒值、原值留 metadata | Modify |
| `~/.agents/config/projects.yaml` | 補登活躍專案 | Modify（設定，非 repo） |
| `paulshaclaw/memory/tests/test_adapter_content.py` | reader/adapter 測試 | Create |
| `paulshaclaw/memory/tests/test_title.py` | 標題測試（mock LLM） | Create |
| `paulshaclaw/memory/tests/test_atomizer_project_sanitize.py` | #2 測試 | Create |
| `paulshaclaw/memory/tests/test_backfill.py` | 回填測試 | Create |
| `paulshaclaw/memory/tests/fixtures/` | 三家 fixture 檔 | Create |

執行測試一律：`cd /home/paul_chen/prj_pri/paulshaclaw && python3 -m pytest <path> -v`

---

## Task 1: 共用 transcript reader（base.py）

**Files:**
- Test: `paulshaclaw/memory/tests/test_adapter_content.py`
- Create: `paulshaclaw/memory/tests/fixtures/claude_transcript.jsonl`、`fixtures/copilot_history.json`
- Modify: `paulshaclaw/memory/importer/adapters/base.py`

- [ ] **Step 1: 建立 fixtures**

`paulshaclaw/memory/tests/fixtures/claude_transcript.jsonl`：
```jsonl
{"type":"user","message":{"role":"user","content":"幫我修 UART 升級流程"}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","thinking":""},{"type":"tool_use","name":"Write","input":{"file_path":"/repo/uart.py","content":"x"}}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","name":"Edit","input":{"file_path":"/repo/uart.py"}},{"type":"text","text":"已修好 UART 升級流程並加上重試。"}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"ok"}]}}
```

`paulshaclaw/memory/tests/fixtures/copilot_history.json`：
```json
{"sessionId":"cop-1","chatMessages":[{"role":"user","content":"列出 PON HLAPI"},{"role":"assistant","content":"已整理 PON HLAPI 對照表。"}]}
```

- [ ] **Step 2: Write the failing test**

於 `paulshaclaw/memory/tests/test_adapter_content.py`：
```python
from pathlib import Path
from paulshaclaw.memory.importer.adapters import base

FIX = Path(__file__).parent / "fixtures"


def test_read_claude_transcript_extracts_prompts_summary_touched():
    out = base.read_claude_transcript(FIX / "claude_transcript.jsonl")
    assert out["user_prompts"] == ["幫我修 UART 升級流程"]
    assert out["assistant_summary"] == "已修好 UART 升級流程並加上重試。"
    assert out["touched_files"] == ["/repo/uart.py"]  # deduped, order-preserved


def test_read_claude_transcript_missing_file_is_empty():
    out = base.read_claude_transcript(FIX / "does_not_exist.jsonl")
    assert out == {"user_prompts": [], "assistant_summary": "", "touched_files": []}


def test_read_copilot_history_extracts_from_chatmessages(tmp_path):
    d = tmp_path / ".copilot" / "history-session-state"
    d.mkdir(parents=True)
    (d / "session_cop-1_123.json").write_text((FIX / "copilot_history.json").read_text(), encoding="utf-8")
    out = base.read_copilot_history(tmp_path, "cop-1")
    assert out["user_prompts"] == ["列出 PON HLAPI"]
    assert out["assistant_summary"] == "已整理 PON HLAPI 對照表。"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_adapter_content.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'read_claude_transcript'`

- [ ] **Step 4: Implement readers in `base.py`**

於 `paulshaclaw/memory/importer/adapters/base.py` 末端加入（檔首已有 `import json`、`from pathlib import Path`）：
```python
def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [x for x in items if not (x in seen or seen.add(x))]


def read_claude_transcript(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    empty = {"user_prompts": [], "assistant_summary": "", "touched_files": []}
    if not p.exists():
        return empty
    prompts: list[str] = []
    touched: list[str] = []
    last_assistant = ""
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = d.get("type")
        message = d.get("message") if isinstance(d.get("message"), dict) else {}
        content = message.get("content")
        if kind == "user" and isinstance(content, str) and content.strip():
            prompts.append(content)
        elif kind == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and isinstance(block.get("text"), str) and block["text"].strip():
                    last_assistant = block["text"]
                elif block.get("type") == "tool_use" and block.get("name") in ("Write", "Edit"):
                    fp = (block.get("input") or {}).get("file_path")
                    if isinstance(fp, str) and fp:
                        touched.append(fp)
    return {"user_prompts": prompts, "assistant_summary": last_assistant, "touched_files": _dedupe(touched)}


def read_copilot_history(config_root: str | Path, session_id: str) -> dict[str, Any]:
    base_dir = Path(config_root) / ".copilot" / "history-session-state"
    matches = sorted(base_dir.glob(f"session_{session_id}_*.json")) if base_dir.is_dir() else []
    if not matches:
        return {"user_prompts": [], "assistant_summary": ""}
    try:
        data = json.loads(matches[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"user_prompts": [], "assistant_summary": ""}
    prompts: list[str] = []
    last_assistant = ""
    for m in data.get("chatMessages", []) if isinstance(data, dict) else []:
        if not isinstance(m, dict) or not isinstance(m.get("content"), str):
            continue
        if m.get("role") == "user":
            prompts.append(m["content"])
        elif m.get("role") == "assistant":
            last_assistant = m["content"]
    return {"user_prompts": prompts, "assistant_summary": last_assistant}


def read_codex_rollout(path: str | Path) -> dict[str, Any]:
    """Best-effort: extract user message text from a codex rollout .jsonl.
    Codex stores turns as 'response_item' records; user turns carry role=='user'
    with a content list of {type:'input_text'|'text', text:str}. Missing/unknown
    shape yields empty prompts (graceful — title still comes from last_assistant_message)."""
    p = Path(path)
    if not p.exists():
        return {"user_prompts": []}
    prompts: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = d.get("payload") if isinstance(d.get("payload"), dict) else d
        if payload.get("role") != "user":
            continue
        content = payload.get("content")
        if isinstance(content, str) and content.strip():
            prompts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str) and block["text"].strip():
                    prompts.append(block["text"])
    return {"user_prompts": prompts}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_adapter_content.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add paulshaclaw/memory/importer/adapters/base.py paulshaclaw/memory/tests/test_adapter_content.py paulshaclaw/memory/tests/fixtures/
git commit -m "feat(stage2): 三格式 transcript reader helper（claude/codex/copilot）"
```

---

## Task 2: 三家 adapter 接線

**Files:**
- Modify: `adapters/claude.py`、`adapters/codex.py`、`adapters/copilot.py`
- Test: append to `test_adapter_content.py`

- [ ] **Step 1: Write the failing test** （append）

```python
import json
from paulshaclaw.memory.importer.adapters import claude as claude_adapter
from paulshaclaw.memory.importer.adapters import copilot as copilot_adapter


def test_claude_adapter_enriches_from_transcript(tmp_path):
    payload = {"tool": "claude-code", "session_id": "s1", "cwd": "/repo",
               "transcript_path": str(FIX / "claude_transcript.jsonl")}
    qp = tmp_path / "q.json"
    qp.write_text(json.dumps(payload), encoding="utf-8")
    result = claude_adapter.extract(qp)
    assert result.session["user_prompts"] == ["幫我修 UART 升級流程"]
    assert result.session["touched_files"] == ["/repo/uart.py"]
    assert result.session["assistant_summary"] == "已修好 UART 升級流程並加上重試。"


def test_copilot_adapter_enriches_from_history(tmp_path):
    hist = tmp_path / ".copilot" / "history-session-state"
    hist.mkdir(parents=True)
    (hist / "session_cop-1_9.json").write_text((FIX / "copilot_history.json").read_text(), encoding="utf-8")
    payload = {"tool": "copilot-cli", "sessionId": "cop-1", "cwd": "/repo",
               "psc_config_root": str(tmp_path)}
    qp = tmp_path / "q.json"
    qp.write_text(json.dumps(payload), encoding="utf-8")
    result = copilot_adapter.extract(qp)
    assert result.session["user_prompts"] == ["列出 PON HLAPI"]
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_adapter_content.py -k adapter_enriches -v`
Expected: FAIL — prompts empty (adapters not yet wired)

- [ ] **Step 3: Wire `claude.py`**

`adapters/claude.py` 的 `extract()` 改為（保留既有 import，新增 `read_claude_transcript`、`string_or_none`）：
```python
def extract(queue_path: str | Path) -> AdapterResult:
    payload = read_payload(queue_path)
    tp = payload.get("transcript_path")
    if isinstance(tp, str) and tp:
        content = read_claude_transcript(tp)
        payload = {**payload, **content}
    return build_session(
        payload=payload,
        queue_path=queue_path,
        tool="claude-code",
        session_id=string_or_empty(payload.get("session_id")),
        default_capture_scope="session_end",
        ended_at=string_or_none(payload.get("ended_at")) or string_or_none(payload.get("timestamp")),
    )
```
（`read_claude_transcript` 加進 `from .base import (...)` 清單。）

- [ ] **Step 4: Wire `codex.py`**

`adapters/codex.py` 的 `extract()`：
```python
def extract(queue_path: str | Path) -> AdapterResult:
    payload = read_payload(queue_path)
    enrich: dict = {}
    last = payload.get("last_assistant_message")
    if isinstance(last, str) and last.strip():
        enrich["assistant_summary"] = last
    tp = payload.get("transcript_path")
    if isinstance(tp, str) and tp:
        enrich.update(read_codex_rollout(tp))  # user_prompts (best-effort)
    if enrich:
        payload = {**payload, **enrich}
    return build_session(
        payload=payload,
        queue_path=queue_path,
        tool="codex",
        session_id=string_or_empty(payload.get("session_id")),
        default_capture_scope="turn",
        ended_at=string_or_none(payload.get("ended_at")),
    )
```
（import 加 `read_codex_rollout`、`string_or_none`。）

- [ ] **Step 5: Wire `copilot.py`**

`adapters/copilot.py` 的 `extract()`：在 `session_id` 解析後加：
```python
    config_root = payload.get("psc_config_root") or payload.get("PSC_CONFIG_ROOT") or str(Path.home())
    content = read_copilot_history(config_root, session_id)
    if content.get("user_prompts") or content.get("assistant_summary"):
        payload = {**payload, **content}
```
（import 加 `read_copilot_history`、`from pathlib import Path`。`build_session` 呼叫不變。）

> 注意：copilot hook 端傳的 `PSC_CONFIG_ROOT` env 目前未寫進 payload；本計畫讓 adapter fallback 到 `Path.home()`（實機 config_root 即 `/home/paul_chen`）。

- [ ] **Step 6: Run to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_adapter_content.py -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add paulshaclaw/memory/importer/adapters/
git commit -m "feat(stage2): 三家 adapter 接 transcript/history 擷取內容"
```

---

## Task 3: Per-session 標題（title.py）

**Files:**
- Create: `importer/title.py`
- Test: `paulshaclaw/memory/tests/test_title.py`

- [ ] **Step 1: Write the failing test**

`paulshaclaw/memory/tests/test_title.py`：
```python
from paulshaclaw.memory.importer import title


def test_generate_uses_runner_and_truncates_to_20():
    long = "這是一個非常長的標題會超過二十個中文字所以一定要被截斷對吧真的很長"
    out, source = title.generate_title(
        {"user_prompts": ["問題"], "assistant_summary": "答案"},
        runner=lambda text, cmd, timeout: long,
    )
    assert source == "gemma4"
    assert len(out) <= 20


def test_generate_falls_back_when_runner_raises():
    out, source = title.generate_title(
        {"user_prompts": ["幫我修 UART 升級流程很長很長很長很長很長很長很長"], "assistant_summary": "x"},
        runner=lambda text, cmd, timeout: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    assert source == "fallback"
    assert len(out) <= 20
    assert out.startswith("幫我修")


def test_generate_falls_back_on_empty_llm_output():
    out, source = title.generate_title(
        {"user_prompts": ["主題"], "assistant_summary": "y"},
        runner=lambda text, cmd, timeout: "   ",
    )
    assert source == "fallback"


def test_apply_caches_and_sets_fields(tmp_path):
    calls = []
    def runner(text, cmd, timeout):
        calls.append(1); return "簡短標題"
    sess = {"session_id": "s9", "user_prompts": ["a"], "assistant_summary": "b"}
    s1 = title.apply(dict(sess), memory_root=tmp_path, runner=runner)
    s2 = title.apply(dict(sess), memory_root=tmp_path, runner=runner)
    assert s1["assistant_summary"] == "簡短標題"
    assert s1["title_source"] == "gemma4"
    assert len(calls) == 1  # second call hit cache
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_title.py -v`
Expected: FAIL — module `title` not found

- [ ] **Step 3: Implement `importer/title.py`**

```python
"""Per-session ≤20-char zh-TW title generation via local gemma4, with offline fallback."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

_MAX = 20
_DEFAULT_COMMAND = ("scripts/claude-gemma4",)
_PROMPT = (
    "請用繁體中文為以下工作 session 下一個標題，**最多 20 個字、單行、不要標點或引號**：\n\n"
    "使用者需求：{prompt}\n\n助理結論：{summary}\n\n標題："
)


def _truncate(text: str, limit: int = _MAX) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())[:limit]


def _default_runner(text: str, command: tuple[str, ...], timeout: int) -> str:
    proc = subprocess.run(list(command), input=text, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"gemma4 exit {proc.returncode}: {proc.stderr[:200]}")
    return proc.stdout


def generate_title(
    session: dict[str, Any],
    *,
    command: tuple[str, ...] = _DEFAULT_COMMAND,
    timeout: int = 60,
    runner: Callable[[str, tuple[str, ...], int], str] | None = None,
) -> tuple[str, str]:
    prompts = session.get("user_prompts") or []
    first_prompt = prompts[0] if prompts else ""
    runner = runner or _default_runner
    text = _PROMPT.format(prompt=first_prompt[:500], summary=(session.get("assistant_summary") or "")[:500])
    try:
        title = _truncate(runner(text, command, timeout))
        if title:
            return title, "gemma4"
    except Exception:
        pass
    return _truncate(first_prompt), "fallback"


def _cache_path(memory_root: str | Path, session_id: str) -> Path:
    safe = re.sub(r"[\\/]+", "__", (session_id or "_unknown"))
    return Path(memory_root) / "runtime" / "cache" / "title" / f"{safe}.json"


def apply(session: dict[str, Any], *, memory_root: str | Path, **kwargs) -> dict[str, Any]:
    cache = _cache_path(memory_root, session.get("session_id") or "")
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            session["assistant_summary"] = cached["title"]
            session["title_source"] = cached["source"]
            return session
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    title, source = generate_title(session, **kwargs)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_name(f".{cache.name}.tmp")
    tmp.write_text(json.dumps({"title": title, "source": source}), encoding="utf-8")
    tmp.replace(cache)
    session["assistant_summary"] = title
    session["title_source"] = source
    return session
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_title.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/importer/title.py paulshaclaw/memory/tests/test_title.py
git commit -m "feat(stage2): per-session gemma4 ≤20 字標題＋離線 fallback＋cache"
```

---

## Task 4: 標題注入 pipeline + frontmatter

**Files:**
- Modify: `importer/adapters/base.py`（`NormalizedSession` 加 `title_source`）
- Modify: `importer/frontmatter.py`（`title`/`title_source` 欄位）
- Modify: `importer/pipeline.py`（呼叫 `title.apply`）
- Test: `paulshaclaw/memory/tests/test_title.py`（append 整合）

- [ ] **Step 1: Write the failing test** （append to test_title.py）

```python
import json as _json
from paulshaclaw.memory.importer import pipeline


def test_pipeline_injects_title_into_inbox(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "paulshaclaw.memory.importer.title._default_runner",
        lambda text, cmd, timeout: "UART 升級修復",
    )
    fix = Path(__file__).parent / "fixtures" / "claude_transcript.jsonl"
    qdir = tmp_path / "inbox-queue"; qdir.mkdir()
    qp = qdir / "q.json"
    qp.write_text(_json.dumps({"tool": "claude-code", "session_id": "s1", "cwd": "/repo",
                               "transcript_path": str(fix)}), encoding="utf-8")
    decision = pipeline.ingest_queue_item(qp, memory_root=tmp_path, dry_run=True)
    rendered = decision["rendered"]
    assert "title: UART 升級修復" in rendered
    assert "title_source: gemma4" in rendered
    assert "## Summary\nUART 升級修復" in rendered
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_title.py::test_pipeline_injects_title_into_inbox -v`
Expected: FAIL — no `title:` in frontmatter

- [ ] **Step 3: Add `title_source` to `NormalizedSession`**

`adapters/base.py`：在 `class NormalizedSession(TypedDict)` 內 `assistant_summary` 之後加：
```python
    title_source: str
```
並在 `build_session` 的 `session: NormalizedSession = {...}` dict 內加一行（緊接 `"assistant_summary": ...`）：
```python
        "title_source": string_or_empty(payload.get("title_source")),
```

- [ ] **Step 4: Render `title`/`title_source`**

`frontmatter.py` 的 `render_markdown` lines 84-96，在 `source_artifact:` 行後、`captured_at:` 行前插入：
```python
        f"title: {_frontmatter_value(session.get('assistant_summary'))}",
        f"title_source: {_frontmatter_value(session.get('title_source') or 'fallback')}",
```

- [ ] **Step 5: Call `title.apply` in pipeline**

`pipeline.py`：檔首 import 區加 `from . import title`。在 `_preview_queue_item_unlocked` 內，`session = result.session`（line 239）之後緊接一行：
```python
    session = title.apply(dict(session), memory_root=root)
```

- [ ] **Step 6: Run to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_title.py -v`
Expected: all passed

- [ ] **Step 7: Regression — full importer test suite**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_frontmatter.py paulshaclaw/memory/tests/test_classifier.py -v`
Expected: all passed（若 frontmatter 既有測試斷言固定行序，依實際失敗調整既有測試的期望行序——title 兩行為新增）

- [ ] **Step 8: Commit**

```bash
git add paulshaclaw/memory/importer/
git commit -m "feat(stage2): import 注入 per-session 標題至 inbox frontmatter 與 Summary"
```

---

## Task 5: 解 atomize 斜線封鎖（#2）

**Files:**
- Modify: `atomizer/config.py`、`atomizer/pipeline.py`
- Test: `paulshaclaw/memory/tests/test_atomizer_project_sanitize.py`

- [ ] **Step 1: Write the failing test**

```python
from paulshaclaw.memory.atomizer.config import sanitize_project_component, is_safe_path_component


def test_sanitize_url_project_is_path_safe():
    out = sanitize_project_component("github.com/hamanpaul/serialwrap")
    assert is_safe_path_component(out)
    assert "/" not in out
    assert out == "github.com__hamanpaul__serialwrap"


def test_sanitize_plain_slug_unchanged():
    assert sanitize_project_component("paulshaclaw") == "paulshaclaw"


def test_sanitize_rejects_traversal():
    assert ".." not in sanitize_project_component("../etc/passwd")
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_atomizer_project_sanitize.py -v`
Expected: FAIL — `sanitize_project_component` not defined

- [ ] **Step 3: Implement `sanitize_project_component` in `config.py`**

於 `atomizer/config.py` 的 `is_safe_path_component` 之後加：
```python
def sanitize_project_component(value: str) -> str:
    """Map any project identifier (incl. URL form with '/') to a path-safe component.
    Original value should be preserved separately in metadata."""
    text = (value or "").strip().replace("\\", "/")
    text = text.strip("/").replace("..", "__")
    text = text.replace("/", "__")
    text = "".join(ch for ch in text if ch not in '*?[]\x00')
    return text or "_unknown"
```

- [ ] **Step 4: Use sanitized value for paths in `atomizer/pipeline.py`**

在 `_split_pass`：
- 移除把 `project` 列入 `unsafe_fields` 檢查（line 251-257 的 tuple 改為只檢 `source_agent`、`source_session`）：
```python
        unsafe_fields = [
            field for field, value in (("source_agent", agent), ("source_session", session))
            if not is_safe_path_component(value)
        ]
```
- 在計算 `session_key` 前加一行（保留 rich 原值）：
```python
        project_path = sanitize_project_component(project)
```
- fragment 寫檔路徑（line 278）`/ project` 改為 `/ project_path`：
```python
            frag_path = (memory_root / "inbox" / "_slices" / project_path
                         / f"{agent}__{session}__{index:03d}.md")
```
- `_render_fragment(...)` 仍傳原 `project`（frontmatter 保留 rich 值，已是現狀）。
- import `sanitize_project_component`：檔首 `from .config import AtomizerConfig, is_safe_path_component` 改為 `from .config import AtomizerConfig, is_safe_path_component, sanitize_project_component`。

在 `_knowledge_path_for`（line 137）：`project_dir = memory_root / "knowledge" / str(project)` 改為對傳入 project 先消毒。最小改法——呼叫端（`_promote_pass` line 425-426）已用 `str(slice_.frontmatter["project"])`；改為：
```python
            knowledge_path = _knowledge_path_for(
                memory_root, sanitize_project_component(str(slice_.frontmatter["project"])), slice_.slice_id
            )
```

- [ ] **Step 5: Add atomize integration test（斜線 project 不再 skip）**

append 至 `test_atomizer_project_sanitize.py`：
```python
from pathlib import Path
from paulshaclaw.memory.atomizer import pipeline as apipe
from paulshaclaw.memory.atomizer.config import load_config


def test_url_project_session_is_split_not_skipped(tmp_path):
    inbox = tmp_path / "inbox" / "sessions" / "claude-code" / "2026-06-16"
    inbox.mkdir(parents=True)
    (inbox / "s1.md").write_text(
        "---\nmemory_layer: inbox\nproject: github.com/hamanpaul/serialwrap\n"
        "source_agent: claude-code\nsource_session: s1\ncaptured_at: 2026-06-16\n---\n"
        "## Summary\nUART 修復\n## Prompts\n1. 修 UART\n", encoding="utf-8")
    cfg, h = load_config()
    out = apipe.run(tmp_path, config=cfg, config_hash=h, now="2026-06-16T00:00:00Z")
    assert out["summary"]["split_sessions"] >= 1
    frags = list((tmp_path / "inbox" / "_slices").rglob("claude-code__s1__*.md"))
    assert frags  # fragments written under sanitized project dir
    assert all("/" not in p.parent.name for p in frags)
```

- [ ] **Step 6: Run to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_atomizer_project_sanitize.py -v`
Expected: all passed

- [ ] **Step 7: Regression — atomizer suite**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_atomizer_splitter.py paulshaclaw/memory/tests/test_dream_e2e.py -v`
Expected: all passed

- [ ] **Step 8: Commit**

```bash
git add paulshaclaw/memory/atomizer/ paulshaclaw/memory/tests/test_atomizer_project_sanitize.py
git commit -m "fix(stage2): atomizer 消毒斜線 project，不再 skip URL 形專案"
```

---

## Task 6: projects.yaml 補登（#2 輔）

**Files:**
- Modify: `~/.agents/config/projects.yaml`（設定檔，非 repo）

- [ ] **Step 1: 補登活躍專案**

在 `~/.agents/config/projects.yaml` 的 `projects:` 下，依既有格式（slug/roots/remotes/aliases）加入實機活躍專案。先確認 root 路徑：
```bash
ls -d /home/paul_chen/prj_pri/serialwrap /home/paul_chen/work_prj /home/build20/PROJECT-0602 2>/dev/null
```
依存在者加入，例如：
```yaml
  serialwrap:
    slug: serialwrap
    roots: [/home/paul_chen/prj_pri/serialwrap]
    remotes: [github.com/hamanpaul/serialwrap]
    aliases: [serial-wrap, swrap]
```

- [ ] **Step 2: 驗證 resolver 回乾淨 slug**

Run:
```bash
python3 -c "from paulshaclaw.memory.importer.project_resolver import resolve_project; print(resolve_project(cwd='/home/paul_chen/prj_pri/serialwrap', git_toplevel=None, remote_url=None, memory_root='/home/paul_chen/.agents/memory'))"
```
Expected: `serialwrap`（無斜線）

> 註：此為設定檔，不進 repo commit；於 PR 描述記錄已補登的清單即可。

---

## Task 7: 回填（backfill.py）

**Files:**
- Create: `importer/backfill.py`
- Test: `paulshaclaw/memory/tests/test_backfill.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path
from paulshaclaw.memory.importer import backfill


def _seed_queue(root: Path, fix: Path):
    q = root / "archive" / "queue" / "2026-06"
    q.mkdir(parents=True)
    (q / "claude-code__s1--written--abc.json").write_text(
        json.dumps({"tool": "claude-code", "session_id": "s1", "cwd": "/repo",
                    "transcript_path": str(fix)}), encoding="utf-8")


def test_dry_run_does_not_write_inbox(tmp_path, monkeypatch):
    monkeypatch.setattr("paulshaclaw.memory.importer.title._default_runner",
                        lambda t, c, to: "標題")
    _seed_queue(tmp_path, Path(__file__).parent / "fixtures" / "claude_transcript.jsonl")
    res = backfill.run(tmp_path, dry_run=True)
    assert res["count"] == 1
    assert not list((tmp_path / "inbox").rglob("*.md"))


def test_backfill_writes_content_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("paulshaclaw.memory.importer.title._default_runner",
                        lambda t, c, to: "標題")
    _seed_queue(tmp_path, Path(__file__).parent / "fixtures" / "claude_transcript.jsonl")
    backfill.run(tmp_path, dry_run=False)
    mds = list((tmp_path / "inbox").rglob("*.md"))
    assert len(mds) == 1
    body = mds[0].read_text(encoding="utf-8")
    assert "1. 幫我修 UART 升級流程" in body
    assert "title: 標題" in body
    backfill.run(tmp_path, dry_run=False)  # re-run
    assert len(list((tmp_path / "inbox").rglob("*.md"))) == 1  # idempotent


def test_backfill_dead_pointer_leaves_empty(tmp_path):
    q = tmp_path / "archive" / "queue" / "2026-06"; q.mkdir(parents=True)
    (q / "claude-code__d1--written--x.json").write_text(
        json.dumps({"tool": "claude-code", "session_id": "d1", "cwd": "/r",
                    "transcript_path": "/nonexistent.jsonl"}), encoding="utf-8")
    res = backfill.run(tmp_path, dry_run=False)
    assert res["count"] == 1  # processed, content empty, no crash
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_backfill.py -v`
Expected: FAIL — module `backfill` not found

- [ ] **Step 3: Implement `importer/backfill.py`**

```python
"""Force re-extract existing archived session payloads back into inbox (content + title)."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from . import _git, title
from .classifier import classify_session
from .frontmatter import render_markdown
from .pipeline import _extract, _date_parts, safe_key
from .project_resolver import normalize_remote, resolve_project


def _reextract_one(payload_path: Path, root: Path, *, dry_run: bool) -> dict[str, Any]:
    result = _extract(payload_path)
    session = result.session
    session = title.apply(dict(session), memory_root=root)
    remote = result.raw_payload.get("remote_url") or result.raw_payload.get("remote") or session.get("repo")
    captured_at, day, _ = _date_parts(session)
    bucket = classify_session(session)
    project = resolve_project(cwd=session.get("cwd"), git_toplevel=session.get("repo"),
                              remote_url=remote if isinstance(remote, str) else None, memory_root=str(root))
    inbox_path = root / "inbox" / bucket / session["tool"] / day / f"{safe_key(session['session_id'])}.md"
    session["raw_payload_pointer"] = str(payload_path)
    provenance_repo = normalize_remote(_git.git_remote(_git.git_toplevel(session.get("cwd")))) or "_unknown"
    rendered = render_markdown(session, project=project, classifier_bucket=bucket,
                              captured_at=captured_at, provenance_repo=provenance_repo)
    if not dry_run:
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = inbox_path.with_name(f".{inbox_path.name}.tmp")
        tmp.write_text(rendered, encoding="utf-8")
        tmp.replace(inbox_path)
    return {"session": session["session_id"], "inbox_path": str(inbox_path)}


def run(memory_root: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    root = Path(memory_root)
    queue = root / "archive" / "queue"
    items: list[dict[str, Any]] = []
    for payload in sorted(queue.rglob("*.json")) if queue.is_dir() else []:
        try:
            items.append(_reextract_one(payload, root, dry_run=dry_run))
        except Exception as exc:  # noqa: BLE001 - backfill boundary, keep going
            items.append({"payload": str(payload), "error": type(exc).__name__})
    return {"count": len(items), "dry_run": dry_run, "items": items}


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill Stage 2 inbox content+title from archived payloads")
    ap.add_argument("--memory-root", default="/home/paul_chen/.agents/memory")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    res = run(args.memory_root, dry_run=args.dry_run)
    print(f"{'DRY-RUN ' if res['dry_run'] else ''}backfilled {res['count']} session(s)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_backfill.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/importer/backfill.py paulshaclaw/memory/tests/test_backfill.py
git commit -m "feat(stage2): backfill.py 三家強制回填（繞 checksum、可 dry-run）"
```

---

## Task 8: 整合與全套件驗證

- [ ] **Step 1: 端到端整合測試**

`paulshaclaw/memory/tests/test_adapter_content.py` append：
```python
def test_end_to_end_inbox_has_content_and_title(tmp_path, monkeypatch):
    import json as J
    monkeypatch.setattr("paulshaclaw.memory.importer.title._default_runner", lambda t, c, to: "端到端標題")
    from paulshaclaw.memory.importer import pipeline
    q = tmp_path / "q.json"
    q.write_text(J.dumps({"tool": "claude-code", "session_id": "e2e", "cwd": "/repo",
                          "transcript_path": str(FIX / "claude_transcript.jsonl")}), encoding="utf-8")
    pipeline.ingest_queue_item(q, memory_root=tmp_path, dry_run=False)
    md = list((tmp_path / "inbox").rglob("*.md"))[0].read_text(encoding="utf-8")
    assert "title: 端到端標題" in md
    assert "1. 幫我修 UART 升級流程" in md
    assert "- /repo/uart.py" in md
```

- [ ] **Step 2: Run full memory test suite**

Run: `python3 -m pytest paulshaclaw/memory/tests/ -q`
Expected: all passed（`test_atomizer_llm_live` 維持 skip——其 marker 需實機 gemma4）

- [ ] **Step 3: Commit**

```bash
git add paulshaclaw/memory/tests/
git commit -m "test(stage2): 內容擷取＋標題端到端整合測試"
```

- [ ] **Step 4: 實機驗證（手動，非 CI）**

```bash
# 1) 回填預檢
python3 -m paulshaclaw.memory.importer.backfill --dry-run
# 2) 正式回填三家
python3 -m paulshaclaw.memory.importer.backfill
# 3) 抽查一筆 inbox 是否有內容＋標題
find /home/paul_chen/.agents/memory/inbox -name '*.md' | head -1 | xargs grep -E "title:|^1\.|^- /"
# 4) 下一輪 dream 後確認 atomize 產出 slice
grep -o '"slices":[0-9]*' /home/paul_chen/.agents/memory/runtime/ledger/dream.jsonl | tail -1
```
Expected：inbox 有非空 `title:`/Prompts/Touched；dream `slices` > 0。

---

## Self-Review 對照（spec 覆蓋）

- R「Session content extraction」→ Task 1-2（三家 reader + adapter；缺檔 graceful 測試於 Task 2/7）。
- R「Per-session title」→ Task 3-4（gemma4 + fallback + 注入；`title_source` 標記）。
- R「Atomizer robustness」→ Task 5（消毒 + 不再 skip 整合測試）。
- R「Backfill」→ Task 7（dry-run/冪等/dead-pointer 三測試）。
- 型別一致：`read_*` 回傳 dict 鍵 `user_prompts`/`assistant_summary`/`touched_files`；`title.apply` 設 `assistant_summary`/`title_source`；`sanitize_project_component` 全程同名。
