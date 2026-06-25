# Stage 2 Promoter 噪音治理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以單一 noise classifier 在產生端阻斷結構/空殼/placeholder slice 寫入 knowledge，並提供回溯 prune CLI 清掉既有 474 噪音。

**Architecture:** 純函式 `classify_noise(frontmatter, body)` 為判準單一真相源（僅依 body）；`atomizer/pipeline.py::_promote_pass` 寫入前過濾並計 `noise_dropped`；新 CLI `memory knowledge prune-noise` 掃 knowledge/、`--apply` hard delete + manifest + 重建 MOC。

**Tech Stack:** Python 3.12、unittest（`.venv/bin/python -m unittest`，無 pytest）、PyYAML、既有 `moc.frontmatter_io` / `moc.moc_builder`。

**Spec:** `docs/superpowers/specs/2026-06-25-stage2-promoter-noise-governance-design.md`｜OpenSpec change `stage2-promoter-noise-governance`

---

## File Structure

- Create: `paulshaclaw/memory/noise.py` — classifier（`NoiseVerdict`、`classify_noise`、常數）。
- Modify: `paulshaclaw/memory/atomizer/pipeline.py` — `_promote_pass` 過濾、`run()` summary 加 `noise_dropped`。
- Modify: `paulshaclaw/memory/cli.py` — 加 `memory knowledge prune-noise` 子命令 + `_prune_noise` handler。
- Test: `paulshaclaw/memory/tests/test_noise.py`、`test_prune_noise.py`；擴充 `test_atomizer_pipeline.py`。

執行指令一律 `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. .venv/bin/python -m unittest <module> -v`。

---

## Task 1: noise classifier

**Files:**
- Test: `paulshaclaw/memory/tests/test_noise.py`
- Create: `paulshaclaw/memory/noise.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_noise.py
from __future__ import annotations

import unittest

from paulshaclaw.memory.noise import classify_noise


class ClassifyNoiseTests(unittest.TestCase):
    def test_structural_echo_headings_are_noise(self):
        for section in ("CWD", "Source", "Prompts", "Touched files",
                        "Referenced artifacts", "Summary"):
            body = f"## {section}\nsome value here that is fairly long but still echo\n"
            verdict = classify_noise({"atom_title": section.lower()}, body)
            self.assertTrue(verdict.is_noise, section)
            self.assertEqual(verdict.reason, f"structural-echo:{section}")

    def test_empty_body_is_noise(self):
        verdict = classify_noise({"atom_title": "x"}, "tiny\n")
        self.assertTrue(verdict.is_noise)
        self.assertEqual(verdict.reason, "empty")

    def test_placeholder_phrases_are_noise(self):
        for phrase in ("由於目前尚未收到您的具體需求，請提供更多細節以便我協助您完成任務。",
                       "目前尚未收到您的具體需求或任務指令，請提供。",
                       "(無內容) 這是一個空的 session 沒有任何實際內容可供原子化處理。"):
            verdict = classify_noise({}, phrase + "\n")
            self.assertTrue(verdict.is_noise, phrase[:10])
            self.assertEqual(verdict.reason, "placeholder")

    def test_untitled_with_real_body_is_kept(self):
        body = ("## 動工前\n- [ ] 確認當前分支不是 `main`\n  - 若在 `main`，先開 "
                "`feature/<slug>` 分支\n- [ ] 跨多子項先用 `git worktree` 拆開\n")
        verdict = classify_noise({"atom_title": "untitled"}, body)
        self.assertFalse(verdict.is_noise)

    def test_real_short_fact_is_kept(self):
        body = "gh 2.45.0 的 pr checks 沒有 --json，要用 pr view --json statusCheckRollup 判 CI。\n"
        verdict = classify_noise({"atom_title": "ci-gating"}, body)
        self.assertFalse(verdict.is_noise)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m unittest paulshaclaw.memory.tests.test_noise -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'paulshaclaw.memory.noise'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/noise.py
"""Stage 2 knowledge noise classifier (#139 P2). Body-content only."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

# importer/frontmatter.render_markdown 的結構段落 heading（含順序無關）。
_STRUCTURAL_SECTIONS = (
    "CWD", "Source", "Prompts", "Touched files", "Referenced artifacts", "Summary",
)
_STRUCTURAL_FIRST_LINE = {f"## {name}": name for name in _STRUCTURAL_SECTIONS}

_EMPTY_THRESHOLD = 40

_PLACEHOLDER_PHRASES = ("(無內容)", "尚未收到您的具體需求", "目前尚未收到")
_BARE_PLACEHOLDERS = {"- (none)", "(none)", "(unknown)", "(無內容)"}


@dataclass(frozen=True)
class NoiseVerdict:
    is_noise: bool
    reason: str


def _strip_body(body: str) -> str:
    return body.strip()


def classify_noise(frontmatter: Mapping[str, object], body: str) -> NoiseVerdict:
    """Classify a knowledge slice as noise using ONLY its body content.

    frontmatter is accepted for interface symmetry but intentionally unused so
    that untitled / no-project slices with real bodies are not mis-dropped.
    """
    del frontmatter
    stripped = _strip_body(body)

    first_line = stripped.splitlines()[0].strip() if stripped else ""
    section = _STRUCTURAL_FIRST_LINE.get(first_line)
    if section is not None:
        return NoiseVerdict(True, f"structural-echo:{section}")

    if len(stripped) < _EMPTY_THRESHOLD:
        return NoiseVerdict(True, "empty")

    if stripped in _BARE_PLACEHOLDERS or any(p in stripped for p in _PLACEHOLDER_PHRASES):
        return NoiseVerdict(True, "placeholder")

    return NoiseVerdict(False, "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m unittest paulshaclaw.memory.tests.test_noise -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/noise.py paulshaclaw/memory/tests/test_noise.py
git commit -m "feat(memory): #139 noise classifier（以 body 內容判定）"
```

---

## Task 2: 產生端過濾（_promote_pass）

**Files:**
- Test: `paulshaclaw/memory/tests/test_atomizer_pipeline.py`（新增 1 test）
- Modify: `paulshaclaw/memory/atomizer/pipeline.py`（`_promote_pass` 過濾、`run()` summary）

- [ ] **Step 1: Write the failing test**

加到 `test_atomizer_pipeline.py`（沿用該檔既有 `_seed_raw` / `atomizer_config.load_config` helper）。在 `PipelineTests` class 內新增：

```python
    def test_structural_echo_slice_is_dropped_as_noise(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "inbox" / "sessions" / "claude" / "2026-06-25" / "s9.md"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(
                "---\nmemory_layer: inbox\nproject: paulshaclaw\nsource_agent: claude\n"
                "source_session: s9\nsource_artifact: session\n"
                'captured_at: "2026-06-25T00:00:00Z"\n'
                "provenance:\n  repo: r\n  commit: c\n  path: p\n---\n"
                "## Summary\n使用者招呼與啟動 session\n"
                "## Real Topic\n這是一段足夠長的真實技術內容，描述某個具體結論與其理由說明。\n",
                encoding="utf-8")
            cfg, h = atomizer_config.load_config(override_path=None)
            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-06-25T03:00:00Z")
            self.assertEqual(result["summary"]["noise_dropped"], 1)
            names = [p.name for p in (root / "knowledge").rglob("*.md")]
            self.assertFalse(any(n.startswith("summary--") for n in names))
            self.assertTrue(any("real-topic" in n.lower() or "real" in n.lower() for n in names))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m unittest paulshaclaw.memory.tests.test_atomizer_pipeline.PipelineTests.test_structural_echo_slice_is_dropped_as_noise -v`
Expected: FAIL — `KeyError: 'noise_dropped'`（summary 尚無此 key）。

- [ ] **Step 3a: 在 pipeline.py 匯入 classifier**

`paulshaclaw/memory/atomizer/pipeline.py` 頂部 import 區加：

```python
from ..noise import classify_noise
```

- [ ] **Step 3b: `_promote_pass` 寫入迴圈過濾**

把 `_promote_pass` 簽名回傳改為 tuple，並在寫入迴圈過濾。`def _promote_pass(...) -> int:` 改 `-> tuple[int, int]:`，函式開頭 `slices_written = 0` 後加 `noise_dropped = 0`。

dry-run 分支（`if dry_run and dry_run_fragments:` 內），在 `slices_written += len(promoted)` 之前改為逐 slice 過濾：

```python
            kept = 0
            for slice_ in promoted:
                verdict = classify_noise(slice_.frontmatter, slice_.body)
                if verdict.is_noise:
                    noise_dropped += 1
                    warnings.append(f"{session_key}: dropped noise slice {slice_.slice_id} ({verdict.reason})")
                    continue
                kept += 1
            slices_written += kept
        return slices_written, noise_dropped
```

真實寫入迴圈 `for slice_, referenced_fragments in prepared_writes:`（pipeline.py:438）開頭、`knowledge_path = ...` 之前插入：

```python
            verdict = classify_noise(slice_.frontmatter, slice_.body)
            if verdict.is_noise:
                noise_dropped += 1
                warnings.append(f"session {session_key}: dropped noise slice {slice_.slice_id} ({verdict.reason})")
                continue
```

函式結尾 `return slices_written` 改 `return slices_written, noise_dropped`。

- [ ] **Step 3c: `run()` 串接 summary**

`run()` 內 `slices = _promote_pass(...)` 改：

```python
    slices, noise_dropped = _promote_pass(memory_root, config, config_hash, now, dry_run, promoter, warnings, dry_run_fragments)
    return {
        "summary": {"split_sessions": split, "slices": slices, "skipped": len(warnings),
                    "noise_dropped": noise_dropped,
                    "config_hash": config_hash, "dry_run": dry_run},
        "warnings": warnings,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m unittest paulshaclaw.memory.tests.test_atomizer_pipeline -v`
Expected: PASS（新 test + 既有全部）。

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/pipeline.py paulshaclaw/memory/tests/test_atomizer_pipeline.py
git commit -m "feat(memory): #139 產生端過濾 noise slice + summary.noise_dropped"
```

---

## Task 3: 回溯 prune CLI

**Files:**
- Test: `paulshaclaw/memory/tests/test_prune_noise.py`
- Modify: `paulshaclaw/memory/cli.py`（加 `knowledge prune-noise` + `_prune_noise`）

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_prune_noise.py
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.cli import main


def _slice(root: Path, project: str, name: str, body: str) -> Path:
    p = root / "knowledge" / project / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\nslice_id: {name.split('--')[-1].replace('.md','')}\nmemory_layer: knowledge\n"
        f"project: {project}\nartifact_kind: report\n---\n{body}\n", encoding="utf-8")
    return p


class PruneNoiseTests(unittest.TestCase):
    def _seed(self, root: Path):
        noise = _slice(root, "p", "cwd--sl-n1.md", "## CWD\n/home/paul_chen")
        good = _slice(root, "p", "versioning-and-release-policy--sl-g1.md",
                      "本 repo 採 conventional commit；tag 必須等於 VERSION，里程碑改用 marker branch。")
        return noise, good

    def test_dry_run_does_not_delete(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            noise, good = self._seed(root)
            rc = main(["memory", "knowledge", "prune-noise", "--memory-root", str(root),
                       "--now", "2026-06-25T00:00:00Z", "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertTrue(noise.exists())
            self.assertTrue(good.exists())

    def test_apply_deletes_noise_keeps_good_and_writes_manifest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            noise, good = self._seed(root)
            rc = main(["memory", "knowledge", "prune-noise", "--memory-root", str(root),
                       "--now", "2026-06-25T00:00:00Z", "--apply"])
            self.assertEqual(rc, 0)
            self.assertFalse(noise.exists())
            self.assertTrue(good.exists())
            manifests = list((root / "runtime" / "ledger").glob("prune-*.jsonl"))
            self.assertEqual(len(manifests), 1)
            rows = [json.loads(l) for l in manifests[0].read_text().splitlines() if l.strip()]
            self.assertTrue(any(r["reason"].startswith("structural-echo") for r in rows))
            self.assertTrue((root / "knowledge" / "p-moc.md").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/python -m unittest paulshaclaw.memory.tests.test_prune_noise -v`
Expected: FAIL — argparse error（`invalid choice: 'knowledge'`），SystemExit。

- [ ] **Step 3a: cli.py 加 subparser**

`paulshaclaw/memory/cli.py` 的 `build` 區（`syncback` 之後、`parser.parse_args` 之前）加：

```python
    knowledge = memory_subparsers.add_parser("knowledge")
    knowledge_subparsers = knowledge.add_subparsers(dest="knowledge_command", required=True)
    prune = knowledge_subparsers.add_parser("prune-noise")
    prune.add_argument("--memory-root", required=True)
    prune.add_argument("--now", default=None)
    group = prune.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    prune.set_defaults(func=_prune_noise)
```

- [ ] **Step 3b: cli.py 加 handler**

import 區補：

```python
import json as _json
from datetime import datetime, timezone
from .noise import classify_noise
from .moc import frontmatter_io as _fio
from .moc import moc_builder as _moc_builder
```

新增 handler（放在其他 `_xxx(args)` handler 旁）：

```python
def _prune_noise(args) -> int:
    root = Path(args.memory_root)
    now = args.now or datetime.now(timezone.utc).isoformat()
    apply = bool(getattr(args, "apply", False))
    knowledge = root / "knowledge"
    rows: list[dict] = []
    for path in sorted(knowledge.rglob("*.md")):
        if path.name.endswith("-moc.md"):
            continue
        fm, body = _fio.read(path.read_text(encoding="utf-8"))
        if fm.get("memory_layer") != "knowledge":
            continue
        verdict = classify_noise(fm, body)
        if not verdict.is_noise:
            continue
        row = {"slice_id": str(fm.get("slice_id", "")), "project": str(fm.get("project", "")),
               "path": str(path), "reason": verdict.reason, "status": "dry-run"}
        if apply:
            try:
                path.unlink()
                row["status"] = "deleted"
            except OSError as exc:
                row["status"] = "error"
                row["error"] = str(exc)
        rows.append(row)

    ledger_dir = root / "runtime" / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    safe_now = now.replace(":", "").replace("+", "_")
    manifest = ledger_dir / f"prune-{safe_now}.jsonl"
    manifest.write_text("".join(_json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    if apply and any(r["status"] == "deleted" for r in rows):
        _moc_builder.build_mocs(root, now=now)

    from collections import Counter
    stats = Counter(r["reason"] for r in rows)
    print(_json.dumps({"scanned_noise": len(rows), "applied": apply, "by_reason": dict(stats),
                       "manifest": str(manifest)}, ensure_ascii=False))
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/python -m unittest paulshaclaw.memory.tests.test_prune_noise -v`
Expected: PASS（2 tests）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/cli.py paulshaclaw/memory/tests/test_prune_noise.py
git commit -m "feat(memory): #139 knowledge prune-noise CLI（dry-run/apply + manifest）"
```

---

## Task 4: 回歸與收尾

- [ ] **Step 1: 跑 memory 相關套件**

Run:
```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  paulshaclaw.memory.tests.test_noise \
  paulshaclaw.memory.tests.test_prune_noise \
  paulshaclaw.memory.tests.test_atomizer_pipeline \
  paulshaclaw.memory.tests.test_atomizer_e2e \
  paulshaclaw.memory.tests.test_moc_builder \
  paulshaclaw.memory.tests.test_dream_cli_moc_warnings 2>&1 | grep -E "^Ran|^OK|^FAILED"
```
Expected: OK，無回歸。

- [ ] **Step 2: 全 memory discover sanity**

Run: `PYTHONPATH=. .venv/bin/python -m unittest discover -s paulshaclaw/memory/tests -p "test_*.py" 2>&1 | grep -E "^Ran|^OK|^FAILED"`
Expected: 僅既有 `test_idempotency` lock 失敗（非本變更），其餘綠。

- [ ] **Step 3: requesting-code-review → 修 → re-review；archive；commit/push/PR**（pipeline Phase 7-10）

---

## Self-Review

- **Spec coverage**：Requirement「以 body 判定」→ Task 1；「產生端過濾」→ Task 2；「回溯 prune」→ Task 3。三 requirement 全覆蓋。
- **Placeholder scan**：各 step 均含實際 code/指令/預期輸出，無 TODO/TBD。
- **Type consistency**：`NoiseVerdict(is_noise, reason)`、`classify_noise(frontmatter, body)`、`_promote_pass -> tuple[int,int]`、`summary["noise_dropped"]`、`_prune_noise(args)` 全文一致。
