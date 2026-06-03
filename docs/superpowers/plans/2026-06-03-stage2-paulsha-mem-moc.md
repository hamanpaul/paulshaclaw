# Stage 2 Topic 7 — paulsha-mem-moc Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `knowledge/` an Obsidian-native vault — materialize `relations.jsonl` into `related:` frontmatter links, give slices readable `<title>--<slice_id>.md` names, build three MOC files + faceout, and a SQLite FTS5 lexical search — as a deterministic third dream pass.

**Architecture:** A new `paulshaclaw/memory/moc/` package runs after atomize+janitor in the dream orchestrator. All link/title edits are frontmatter-only (body untouched → Stage 3 checksum + content-derived slice_id preserved). Filenames carry `slice_id` so the atomizer overwrites by glob (no duplicate slice_id). MOC files carry `memory_layer: moc` and are already excluded by the existing knowledge scanners. No LLM; inject `now`; idempotent full rebuild.

**Tech Stack:** Python 3.12, stdlib (`sqlite3` FTS5, `json`, `re`, `pathlib`), PyYAML, `unittest`.

**Design:** `docs/superpowers/specs/2026-06-03-stage2-paulsha-mem-moc-design.md`
**OpenSpec:** `openspec/changes/stage2-paulsha-mem-moc/`

**Merged facts (reuse, do not rewrite):**
- atomize writes `knowledge/<project>/<slice_id>.md` at `atomizer/pipeline.py` (the `prepared_writes` loop, ~line 385).
- `janitor/record_source.py:83` and `replay/selector.py:~99` already skip files whose `memory_layer != "knowledge"` → **MOC files with `memory_layer: moc` are already excluded; no code change needed for C4 (confirm with a test).**
- `ledger.relations.neighbors(memory_root, node)`, `ledger.relations.read_edges`, `ledger.retrieval_set.active_records`, `ledger.lifecycle.read_events`.
- Stage 3: `lifecycle.schema.validate_frontmatter(frontmatter=, body=)`, `compute_checksum(body)`.
- Slice frontmatter on disk: `slice_id`, `project`, `tags`, `artifact_kind`, `captured_at`, `distilled_from`, nested `provenance:`. Body follows the closing `---`.

**Shared shapes:**
- `slugify(title) -> kebab`; target filename `f"{slug}--{slice_id}.md"`.
- relation node names: `slice:<slice_id>`, `entity:<NAME>`.

---

## Task 1: `moc/frontmatter_io.py` — read + body-preserving frontmatter rewrite

**Files:**
- Create: `paulshaclaw/memory/moc/__init__.py`
- Create: `paulshaclaw/memory/moc/frontmatter_io.py`
- Test: `paulshaclaw/memory/tests/test_moc_frontmatter_io.py`

- [x] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_moc_frontmatter_io.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.lifecycle.schema import compute_checksum, validate_frontmatter
from paulshaclaw.memory.moc import frontmatter_io as fio

_SLICE = (
    "---\n"
    "phase: research\nproject: paulshaclaw\nslice_id: sl-abc\nartifact_kind: research\n"
    "version: 1\ncreated_at: 2026-06-03T00:00:00Z\ncreated_by: claude\n"
    "source_session: s1\ngate_required: false\nchecksum: __CK__\n"
    "memory_layer: knowledge\nsource_agent: claude\ncaptured_at: 2026-06-03T00:00:00Z\n"
    "supersedes: []\ndistilled_from: claude:s1\n"
    "provenance:\n  repo: r\n  commit: c\n  path: p\n"
    "---\n"
    "BODY LINE ONE\nBODY LINE TWO\n"
)


def _slice_text() -> str:
    body = "BODY LINE ONE\nBODY LINE TWO\n"
    return _SLICE.replace("__CK__", compute_checksum(body))


class FrontmatterIoTests(unittest.TestCase):
    def test_read_splits_frontmatter_and_body(self):
        fm, body = fio.read(_slice_text())
        self.assertEqual(fm["slice_id"], "sl-abc")
        self.assertEqual(body, "BODY LINE ONE\nBODY LINE TWO\n")

    def test_rewrite_preserves_body_and_checksum(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.md"
            path.write_text(_slice_text(), encoding="utf-8")
            fio.update(path, {"title": "Alpha", "aliases": ["Alpha"],
                              "related": ["[[Beta--sl-2]]", "[[MTK]]"]})
            fm, body = fio.read(path.read_text(encoding="utf-8"))
            self.assertEqual(fm["title"], "Alpha")
            self.assertEqual(fm["related"], ["[[Beta--sl-2]]", "[[MTK]]"])
            # body and checksum unchanged -> Stage 3 still validates
            self.assertEqual(body, "BODY LINE ONE\nBODY LINE TWO\n")
            result = validate_frontmatter(frontmatter=fm, body=body)
            self.assertTrue(result.ok, result.errors)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_frontmatter_io -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'paulshaclaw.memory.moc'`

- [x] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/moc/__init__.py
```

```python
# paulshaclaw/memory/moc/frontmatter_io.py
from __future__ import annotations

from pathlib import Path
from typing import Any


def read(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body). Body is everything after the closing ---."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        return {}, text
    block = "".join(lines[1:end])
    body = "".join(lines[end + 1:])
    try:
        import yaml
        data = yaml.safe_load(block) or {}
    except ModuleNotFoundError:
        data = {}
    return (data if isinstance(data, dict) else {}), body


def _emit(value: Any, indent: int = 0) -> list[str]:
    pad = "  " * indent
    if isinstance(value, dict):
        out: list[str] = []
        for key, val in value.items():
            if isinstance(val, (dict, list)):
                out.append(f"{pad}{key}:")
                out.extend(_emit(val, indent + 1))
            else:
                out.append(f"{pad}{key}: {_scalar(val)}")
        return out
    if isinstance(value, list):
        return [f"{pad}- {_scalar(item)}" for item in value]
    return [f"{pad}{_scalar(value)}"]


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def dump(frontmatter: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, (dict, list)):
            if isinstance(value, list) and not value:
                lines.append(f"{key}: []")
                continue
            lines.append(f"{key}:")
            lines.extend(_emit(value, 1))
        else:
            lines.append(f"{key}: {_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def update(path: Path, updates: dict[str, Any]) -> None:
    fm, body = read(path.read_text(encoding="utf-8"))
    fm.update(updates)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(dump(fm, body), encoding="utf-8")
    tmp.replace(path)
```

> Note: `dump` re-emits nested `provenance:` and list fields in a flat-then-nested style compatible with both Stage 3's parser (which tolerates extra fields) and Topic 4's `yaml.safe_load`. Body is preserved byte-for-byte so `checksum = sha256(body)` is unchanged.

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_frontmatter_io -v`
Expected: PASS (2 tests)

- [x] **Step 5: Commit**

```bash
git add paulshaclaw/memory/moc/__init__.py paulshaclaw/memory/moc/frontmatter_io.py paulshaclaw/memory/tests/test_moc_frontmatter_io.py
git commit -m "feat(stage2): add moc frontmatter read/rewrite (body-preserving)"
```

---

## Task 2: `moc/naming.py` — readable filenames + dedup

**Files:**
- Create: `paulshaclaw/memory/moc/naming.py`
- Test: `paulshaclaw/memory/tests/test_moc_naming.py`

- [x] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_moc_naming.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.moc import naming


def _write(root: Path, name: str, fm_extra: str, body: str = "body\n") -> Path:
    path = root / "knowledge" / "paulshaclaw" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nslice_id: {fm_extra}\nmemory_layer: knowledge\nproject: paulshaclaw\n"
                    f"artifact_kind: research\n---\n{body}", encoding="utf-8")
    return path


class NamingTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(naming.slugify("PWHM FSM States!"), "pwhm-fsm-states")

    def test_reconcile_renames_to_title_slice(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "knowledge" / "paulshaclaw" / "sl-1.md"
            p.parent.mkdir(parents=True)
            p.write_text("---\nslice_id: sl-1\nmemory_layer: knowledge\nproject: paulshaclaw\n"
                         "artifact_kind: research\ntitle: Alpha Note\n---\nbody\n", encoding="utf-8")
            naming.reconcile(root)
            self.assertFalse(p.exists())
            self.assertTrue((root / "knowledge" / "paulshaclaw" / "alpha-note--sl-1.md").exists())

    def test_title_fallback_to_artifact_project(self):
        # no title, no heading -> <artifact_kind>-<project>
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "sl-2.md", "sl-2")
            naming.reconcile(root)
            self.assertTrue((root / "knowledge" / "paulshaclaw" / "research-paulshaclaw--sl-2.md").exists())

    def test_dedup_keeps_one_per_slice_id(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kdir = root / "knowledge" / "paulshaclaw"
            kdir.mkdir(parents=True)
            (kdir / "sl-3.md").write_text("---\nslice_id: sl-3\nmemory_layer: knowledge\nproject: paulshaclaw\nartifact_kind: research\n---\nNEW\n", encoding="utf-8")
            (kdir / "old--sl-3.md").write_text("---\nslice_id: sl-3\nmemory_layer: knowledge\nproject: paulshaclaw\nartifact_kind: research\n---\nOLD\n", encoding="utf-8")
            naming.reconcile(root)
            remaining = sorted(p.name for p in kdir.glob("*sl-3*.md"))
            self.assertEqual(len(remaining), 1)

    def test_skips_moc_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            moc = root / "knowledge" / "wiki-moc.md"
            moc.parent.mkdir(parents=True)
            moc.write_text("---\nmemory_layer: moc\nmoc_kind: wiki\n---\n# Wiki\n", encoding="utf-8")
            naming.reconcile(root)
            self.assertTrue(moc.exists())  # untouched


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_naming -v`
Expected: FAIL with `ImportError: cannot import name 'naming'`

- [x] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/moc/naming.py
from __future__ import annotations

import re
from pathlib import Path

from . import frontmatter_io as fio

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    slug = _SLUG_STRIP.sub("-", title.strip().lower()).strip("-")
    return slug or "untitled"


def _title(fm: dict, body: str) -> str:
    title = fm.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                return heading
    return f"{fm.get('artifact_kind', 'note')}-{fm.get('project', 'unknown')}"


def target_name(fm: dict, body: str) -> str:
    return f"{slugify(_title(fm, body))}--{fm['slice_id']}.md"


def reconcile(memory_root: Path) -> list[str]:
    """Rename slices to <title>--<slice_id>.md and dedup by slice_id. Returns warnings."""
    knowledge = memory_root / "knowledge"
    warnings: list[str] = []
    if not knowledge.exists():
        return warnings
    seen: dict[str, Path] = {}  # slice_id -> chosen path
    for path in sorted(knowledge.rglob("*.md")):
        fm, body = fio.read(path.read_text(encoding="utf-8"))
        if fm.get("memory_layer") != "knowledge":
            continue
        slice_id = fm.get("slice_id")
        if not slice_id:
            warnings.append(f"{path}: missing slice_id; skipped")
            continue
        target = path.with_name(target_name(fm, body))
        if path != target:
            if target.exists():
                target.unlink()  # stale older name -> replaced by current content
            path.rename(target)
            path = target
        if slice_id in seen:
            # duplicate slice_id across files -> keep the newest mtime, drop the other
            other = seen[slice_id]
            older = other if other.stat().st_mtime <= path.stat().st_mtime else path
            newer = path if older is other else other
            older.unlink()
            seen[slice_id] = newer
            warnings.append(f"duplicate slice_id {slice_id}; kept {newer.name}")
        else:
            seen[slice_id] = path
    return warnings
```

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_naming -v`
Expected: PASS (5 tests)

- [x] **Step 5: Commit**

```bash
git add paulshaclaw/memory/moc/naming.py paulshaclaw/memory/tests/test_moc_naming.py
git commit -m "feat(stage2): add moc naming (readable filenames + dedup)"
```

---

## Task 3: Atomizer write-by-slice_id glob (conflict C1)

**Files:**
- Modify: `paulshaclaw/memory/atomizer/pipeline.py` (the `prepared_writes` loop knowledge_path)
- Test: `paulshaclaw/memory/tests/test_atomizer_pipeline.py` (extend)

- [x] **Step 1: Write the failing test (append)**

```python
# append to paulshaclaw/memory/tests/test_atomizer_pipeline.py
class ReimportOverwriteTests(unittest.TestCase):
    def test_reimport_overwrites_renamed_file_no_duplicate(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kdir = root / "knowledge" / "paulshaclaw"
            kdir.mkdir(parents=True)
            # simulate a moc-renamed existing slice
            existing = kdir / "alpha--sl-xyz.md"
            existing.write_text("---\nslice_id: sl-xyz\nmemory_layer: knowledge\nproject: paulshaclaw\n---\nOLD\n", encoding="utf-8")
            # atomize must resolve the write path for slice_id sl-xyz to the existing renamed file
            from paulshaclaw.memory.atomizer import pipeline
            resolved = pipeline._knowledge_path_for(root, "paulshaclaw", "sl-xyz")
            self.assertEqual(resolved, existing)
            # and for a brand-new slice_id it falls back to <slice_id>.md
            fresh = pipeline._knowledge_path_for(root, "paulshaclaw", "sl-new")
            self.assertEqual(fresh.name, "sl-new.md")
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_pipeline.ReimportOverwriteTests -v`
Expected: FAIL (`_knowledge_path_for` not defined)

- [x] **Step 3: Modify `pipeline.py`**

Add a resolver near the top-level helpers:

```python
def _knowledge_path_for(memory_root: Path, project: str, slice_id: str) -> Path:
    project_dir = memory_root / "knowledge" / str(project)
    if project_dir.exists():
        for candidate in sorted(project_dir.glob(f"*--{slice_id}.md")):
            return candidate
        legacy = project_dir / f"{slice_id}.md"
        if legacy.exists():
            return legacy
    return project_dir / f"{slice_id}.md"
```

Replace the `knowledge_path = ( ... / f"{slice_.slice_id}.md" )` assignment in the `prepared_writes` loop with:

```python
            knowledge_path = _knowledge_path_for(
                memory_root, str(slice_.frontmatter["project"]), slice_.slice_id
            )
            _atomic_write(knowledge_path, slice_frontmatter.render(slice_))
```

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_pipeline -v`
Expected: PASS (existing + new)

- [x] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/pipeline.py paulshaclaw/memory/tests/test_atomizer_pipeline.py
git commit -m "fix(stage2): atomize overwrites slice by slice_id glob (no dup)"
```

---

## Task 4: `moc/linker.py` — relations → related: frontmatter (conflict C2 + C4 confirm)

**Files:**
- Create: `paulshaclaw/memory/moc/linker.py`
- Test: `paulshaclaw/memory/tests/test_moc_linker.py`

- [x] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_moc_linker.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.lifecycle.schema import compute_checksum, validate_frontmatter
from paulshaclaw.memory.ledger import relations
from paulshaclaw.memory.moc import frontmatter_io as fio
from paulshaclaw.memory.moc import linker


def _slice(root: Path, slice_id: str, title: str) -> Path:
    body = f"body {slice_id}\n"
    path = root / "knowledge" / "p" / f"{title}--{slice_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = (f"---\nslice_id: {slice_id}\nmemory_layer: knowledge\nproject: p\n"
          f"artifact_kind: research\ntitle: {title}\nchecksum: {compute_checksum(body)}\n"
          f"phase: research\nversion: 1\ncreated_at: 2026-06-03T00:00:00Z\ncreated_by: c\n"
          f"source_session: s\ngate_required: false\ncaptured_at: 2026-06-03T00:00:00Z\n"
          f"source_agent: c\nsupersedes: []\ndistilled_from: c:s\n---\n{body}")
    path.write_text(fm, encoding="utf-8")
    return path


class LinkerTests(unittest.TestCase):
    def test_bidirectional_related_and_entity_links_in_frontmatter_only(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _slice(root, "sl-a", "alpha")
            b = _slice(root, "sl-b", "beta")
            relations.append_edge(root, type="relates_to", frm="slice:sl-a", to="slice:sl-b", now="t", config_hash="h")
            relations.append_edge(root, type="mentions", frm="slice:sl-a", to="entity:MTK", now="t", config_hash="h")
            weights = linker.materialize_links(root)
            fm_a, body_a = fio.read(a.read_text(encoding="utf-8"))
            fm_b, _ = fio.read(b.read_text(encoding="utf-8"))
            self.assertIn("[[beta--sl-b]]", fm_a["related"])
            self.assertIn("[[MTK]]", fm_a["related"])
            self.assertIn("[[alpha--sl-a]]", fm_b["related"])  # bidirectional
            self.assertNotIn("[[", body_a)                      # never in body
            self.assertTrue(validate_frontmatter(frontmatter=fm_a, body=body_a).ok)  # checksum intact
            self.assertEqual(fm_a.get("aliases"), ["alpha"])
            self.assertEqual(weights["sl-a"], 2)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_linker -v`
Expected: FAIL with `ImportError: cannot import name 'linker'`

- [x] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/moc/linker.py
from __future__ import annotations

from pathlib import Path

from ..ledger import relations
from . import frontmatter_io as fio


def _slice_files(memory_root: Path) -> dict[str, Path]:
    """slice_id -> path, for memory_layer: knowledge files."""
    mapping: dict[str, Path] = {}
    knowledge = memory_root / "knowledge"
    if not knowledge.exists():
        return mapping
    for path in sorted(knowledge.rglob("*.md")):
        fm, _ = fio.read(path.read_text(encoding="utf-8"))
        if fm.get("memory_layer") != "knowledge":
            continue
        sid = fm.get("slice_id")
        if sid:
            mapping[str(sid)] = path
    return mapping


def materialize_links(memory_root: Path) -> dict[str, int]:
    files = _slice_files(memory_root)
    # build bidirectional adjacency
    related: dict[str, set[str]] = {sid: set() for sid in files}
    for edge in relations.read_edges(memory_root):
        etype = edge.get("type")
        frm = str(edge.get("from", ""))
        to = str(edge.get("to", ""))
        if etype == "relates_to" and frm.startswith("slice:") and to.startswith("slice:"):
            a, b = frm[len("slice:"):], to[len("slice:"):]
            if a in related:
                related[a].add(f"slice:{b}")
            if b in related:
                related[b].add(f"slice:{a}")
        elif etype == "mentions" and frm.startswith("slice:") and to.startswith("entity:"):
            a = frm[len("slice:"):]
            if a in related:
                related[a].add(to)  # entity:<NAME>

    weights: dict[str, int] = {}
    for sid, path in files.items():
        fm, body = fio.read(path.read_text(encoding="utf-8"))
        links: list[str] = []
        for node in sorted(related.get(sid, set())):
            if node.startswith("slice:"):
                target = files.get(node[len("slice:"):])
                if target is not None:
                    links.append(f"[[{target.stem}]]")
            elif node.startswith("entity:"):
                links.append(f"[[{node[len('entity:'):]}]]")
        title = fm.get("title") or path.stem.rsplit("--", 1)[0]
        fio.update(path, {"title": title, "aliases": [title], "related": links})
        weights[sid] = len(links)
    return weights
```

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_linker -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add paulshaclaw/memory/moc/linker.py paulshaclaw/memory/tests/test_moc_linker.py
git commit -m "feat(stage2): add moc linker (related: frontmatter, body-safe)"
```

---

## Task 5: `moc/moc_builder.py` + `moc/faceout.py` — three MOCs + faceout

**Files:**
- Create: `paulshaclaw/memory/moc/moc_builder.py`
- Create: `paulshaclaw/memory/moc/faceout.py`
- Test: `paulshaclaw/memory/tests/test_moc_builder.py`

- [x] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_moc_builder.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.ledger import lifecycle
from paulshaclaw.memory.moc import faceout, moc_builder


def _slice(root: Path, slice_id: str, project: str, title: str) -> None:
    body = f"body {slice_id}\n"
    path = root / "knowledge" / project / f"{title}--{slice_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nslice_id: {slice_id}\nmemory_layer: knowledge\nproject: {project}\n"
                    f"artifact_kind: research\ntitle: {title}\n---\n{body}", encoding="utf-8")


class MocBuilderTests(unittest.TestCase):
    def test_three_mocs_with_moc_layer(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "prplos-core", "alpha")
            _slice(root, "sl-2", "common-sense", "rule-x")
            moc_builder.build_mocs(root, now="2026-06-03T00:00:00Z")
            project_moc = (root / "knowledge" / "prplos-core-moc.md").read_text(encoding="utf-8")
            self.assertIn("memory_layer: moc", project_moc)
            self.assertIn("[[alpha--sl-1]]", project_moc)
            cs = (root / "knowledge" / "common-sense-moc.md").read_text(encoding="utf-8")
            self.assertIn("[[rule-x--sl-2]]", cs)
            wiki = (root / "knowledge" / "wiki-moc.md").read_text(encoding="utf-8")
            self.assertIn("## Active", wiki)
            self.assertIn("[[alpha--sl-1]]", wiki)

    def test_faceout_lists_decayed_not_deleted(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "p", "alpha")
            moc_builder.build_mocs(root, now="2026-06-03T00:00:00Z")
            lifecycle.append_event(root / "runtime" / "ledger" / "lifecycle.jsonl",
                                   record_id="sl-1", event_type="decayed", source="janitor",
                                   reason="ttl_expired", actor="janitor")
            faceout.mark_faceout(root)
            wiki = (root / "knowledge" / "wiki-moc.md").read_text(encoding="utf-8")
            self.assertIn("## Faceout", wiki)
            self.assertIn("sl-1", wiki)
            self.assertTrue((root / "knowledge" / "p" / "alpha--sl-1.md").exists())  # not deleted


if __name__ == "__main__":
    unittest.main()
```

> Note: confirm the merged `lifecycle.append_event` signature (path/dir, record_id, event_type, source, reason, actor); adapt the decayed-seed line if it differs.

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_builder -v`
Expected: FAIL with `ImportError: cannot import name 'moc_builder'`

- [x] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/moc/moc_builder.py
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from ..ledger import retrieval_set
from . import frontmatter_io as fio


def _active_slices(memory_root: Path) -> list[tuple[str, str, str, str]]:
    """Return (slice_id, project, basename, artifact_kind) for active knowledge slices."""
    knowledge = memory_root / "knowledge"
    rows: list[tuple[str, str, str, str]] = []
    if not knowledge.exists():
        return rows
    candidates: list[tuple[str, str, str, str]] = []
    for path in sorted(knowledge.rglob("*.md")):
        fm, _ = fio.read(path.read_text(encoding="utf-8"))
        if fm.get("memory_layer") != "knowledge":
            continue
        sid = fm.get("slice_id")
        if not sid:
            continue
        candidates.append((str(sid), str(fm.get("project", "_unknown")), path.stem,
                           str(fm.get("artifact_kind", ""))))
    active = set(retrieval_set.active_records(memory_root, [c[0] for c in candidates]))
    return [c for c in candidates if c[0] in active]


def _write_moc(path: Path, kind: str, now: str, header: str, lines: list[str], project: str | None = None) -> None:
    fm = ["---", "memory_layer: moc", f"moc_kind: {kind}", f"generated_ts: {now}"]
    if project is not None:
        fm.append(f"project: {project}")
    fm.append("---")
    path.write_text("\n".join(fm) + f"\n# {header}\n\n" + "\n".join(lines) + "\n", encoding="utf-8")


def build_mocs(memory_root: Path, now: str) -> None:
    knowledge = memory_root / "knowledge"
    knowledge.mkdir(parents=True, exist_ok=True)
    rows = _active_slices(memory_root)
    by_project: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    for row in rows:
        by_project[row[1]].append(row)

    for project, items in by_project.items():
        if project == "common-sense":
            continue
        lines = [f"- [[{basename}]] — {kind}" for _, _, basename, kind in sorted(items)]
        _write_moc(knowledge / f"{project}-moc.md", "project", now, f"{project} MOC", lines, project)

    cs = [f"- [[{b}]] — {k}" for sid, p, b, k in sorted(rows) if p == "common-sense"]
    _write_moc(knowledge / "common-sense-moc.md", "common-sense", now, "Common-sense MOC", cs)

    active_lines = ["## Active", ""] + [f"- [[{b}]] — {p} · {k}" for sid, p, b, k in sorted(rows)]
    _write_moc(knowledge / "wiki-moc.md", "wiki", now, "Wiki MOC", active_lines)
```

```python
# paulshaclaw/memory/moc/faceout.py
from __future__ import annotations

from pathlib import Path

from ..ledger import lifecycle


def mark_faceout(memory_root: Path) -> None:
    wiki = memory_root / "knowledge" / "wiki-moc.md"
    if not wiki.exists():
        return
    decayed: dict[str, tuple[str, str]] = {}  # record_id -> (reason, ts), latest wins
    for event in lifecycle.read_events(memory_root):
        if event.get("event_type") == "decayed":
            rid = event.get("record_id")
            if rid:
                decayed[str(rid)] = (str(event.get("reason", "")), str(event.get("ts", "")))
    lines = ["", "## Faceout", ""]
    for rid, (reason, ts) in sorted(decayed.items()):
        lines.append(f"- {rid} — decayed: {reason}, since {ts}")
    with wiki.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
```

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_builder -v`
Expected: PASS (2 tests)

- [x] **Step 5: Commit**

```bash
git add paulshaclaw/memory/moc/moc_builder.py paulshaclaw/memory/moc/faceout.py paulshaclaw/memory/tests/test_moc_builder.py
git commit -m "feat(stage2): add moc builder (3 MOCs) + faceout"
```

---

## Task 6: `moc/search.py` — FTS5 lexical search

**Files:**
- Create: `paulshaclaw/memory/moc/search.py`
- Test: `paulshaclaw/memory/tests/test_moc_search.py`

- [x] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_moc_search.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.moc import search


def _slice(root: Path, slice_id: str, project: str, title: str, body: str) -> None:
    path = root / "knowledge" / project / f"{title}--{slice_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nslice_id: {slice_id}\nmemory_layer: knowledge\nproject: {project}\n"
                    f"title: {title}\ntags: [t]\ncaptured_at: 2026-06-03T00:00:00Z\n---\n{body}\n",
                    encoding="utf-8")


class SearchTests(unittest.TestCase):
    def test_build_and_query_with_project_scope(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "prplos-core", "flock-ledger", "flock locking on ledger")
            _slice(root, "sl-2", "other", "unrelated", "different content")
            search.build_index(root, link_weights={"sl-1": 3, "sl-2": 0})
            hits = search.search(root, "flock", project="prplos-core", limit=5, include_decayed=True)
            self.assertEqual([h["slice_id"] for h in hits], ["sl-1"])
            self.assertIn("project", hits[0])

    def test_missing_index_raises(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(search.SearchIndexError):
                search.search(Path(tmp), "x", project=None, limit=5, include_decayed=False)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_search -v`
Expected: FAIL with `ImportError: cannot import name 'search'`

- [x] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/moc/search.py
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..ledger import retrieval_set
from . import frontmatter_io as fio


class SearchIndexError(Exception):
    """Raised when the search index is missing or unusable."""


def index_path(memory_root: Path) -> Path:
    return memory_root / "runtime" / "indexes" / "retrieval.db"


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
                     "captured_at TEXT, active INTEGER, link_weight INTEGER)")
        knowledge = memory_root / "knowledge"
        rows = []
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
                             body, str(fm.get("captured_at", ""))))
        active = set(retrieval_set.active_records(memory_root, [r[0] for r in rows]))
        for sid, project, title, tags, body, captured_at in rows:
            conn.execute("INSERT INTO slices_fts VALUES (?,?,?,?,?)", (sid, project, title, tags, body))
            conn.execute("INSERT INTO slice_meta VALUES (?,?,?,?,?)",
                         (sid, project, captured_at, 1 if sid in active else 0, link_weights.get(sid, 0)))
        conn.commit()
    finally:
        conn.close()


def search(memory_root: Path, query: str, *, project: str | None, limit: int,
           include_decayed: bool) -> list[dict]:
    path = index_path(memory_root)
    if not path.exists():
        raise SearchIndexError("search index not built; run the dream/moc pass first")
    conn = sqlite3.connect(path)
    try:
        sql = ("SELECT f.slice_id, m.project, f.title, bm25(slices_fts) AS bm, m.link_weight, m.active "
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
    # rank: lower bm25 is better; add link_weight boost. (recency omitted for determinism in MVP test.)
    ranked = sorted(rows, key=lambda r: (r[3] - 0.1 * (r[4] or 0)))
    return [{"slice_id": r[0], "project": r[1], "title": r[2], "score": r[3]} for r in ranked[:limit]]
```

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_search -v`
Expected: PASS (2 tests)

- [x] **Step 5: Commit**

```bash
git add paulshaclaw/memory/moc/search.py paulshaclaw/memory/tests/test_moc_search.py
git commit -m "feat(stage2): add moc FTS5 lexical search"
```

---

## Task 7: `moc/runner.py` + dream pass + `psc memory search` CLI

**Files:**
- Create: `paulshaclaw/memory/moc/runner.py`, `paulshaclaw/memory/moc/cli.py`
- Modify: `paulshaclaw/memory/cli.py` (add `search`), `paulshaclaw/memory/dream/cli.py` (add moc pass)
- Test: `paulshaclaw/memory/tests/test_moc_runner.py`

- [x] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_moc_runner.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.moc import runner


def _slice(root: Path, slice_id: str, title: str) -> None:
    path = root / "knowledge" / "p" / f"{slice_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nslice_id: {slice_id}\nmemory_layer: knowledge\nproject: p\n"
                    f"artifact_kind: research\ntitle: {title}\ncaptured_at: 2026-06-03T00:00:00Z\n"
                    f"---\nbody {slice_id}\n", encoding="utf-8")


class RunnerTests(unittest.TestCase):
    def test_run_moc_renames_links_mocs_index(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "Alpha")
            result = runner.run_moc(root, now="2026-06-03T00:00:00Z")
            self.assertTrue((root / "knowledge" / "p" / "alpha--sl-1.md").exists())
            self.assertTrue((root / "knowledge" / "wiki-moc.md").exists())
            self.assertTrue((root / "runtime" / "indexes" / "retrieval.db").exists())
            self.assertIn("indexed", result)

    def test_idempotent_rerun(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "Alpha")
            runner.run_moc(root, now="2026-06-03T00:00:00Z")
            wiki1 = (root / "knowledge" / "wiki-moc.md").read_text(encoding="utf-8")
            runner.run_moc(root, now="2026-06-03T00:00:00Z")
            wiki2 = (root / "knowledge" / "wiki-moc.md").read_text(encoding="utf-8")
            self.assertEqual(wiki1, wiki2)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_runner -v`
Expected: FAIL with `ImportError: cannot import name 'runner'`

- [x] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/moc/runner.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import faceout, linker, moc_builder, naming, search


def run_moc(memory_root: Path, now: str) -> dict[str, Any]:
    warnings: list[str] = []
    warnings.extend(naming.reconcile(memory_root))
    try:
        weights = linker.materialize_links(memory_root)
    except Exception as exc:  # core-state corruption (relations) -> degrade
        warnings.append(f"linker degraded: {exc}")
        weights = {}
    moc_builder.build_mocs(memory_root, now)
    faceout.mark_faceout(memory_root)
    try:
        search.build_index(memory_root, weights)
        indexed = True
    except Exception as exc:
        warnings.append(f"search index skipped: {exc}")
        indexed = False
    return {"renamed": True, "linked": len(weights), "mocs": True,
            "faceout": True, "indexed": indexed, "warnings": warnings}
```

```python
# paulshaclaw/memory/moc/cli.py
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import search


def run(args: argparse.Namespace) -> int:
    tags = None  # facet tags handled by selector elsewhere; search is lexical
    try:
        hits = search.search(Path(args.memory_root), args.query, project=args.project,
                             limit=args.limit, include_decayed=args.include_decayed)
    except search.SearchIndexError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps({"results": hits}, sort_keys=True, indent=2))
    return 0
```

Add to `paulshaclaw/memory/cli.py` `_build_parser` (after `bundle`):

```python
    search_p = memory_subparsers.add_parser("search")
    search_p.add_argument("query")
    search_p.add_argument("--memory-root", required=True)
    search_p.add_argument("--project", default=None)
    search_p.add_argument("--limit", type=int, default=10)
    search_p.add_argument("--include-decayed", action="store_true")
    search_p.set_defaults(func=_search)
```

And the handler:

```python
def _search(args: argparse.Namespace) -> int:
    from .moc.cli import run as search_run

    return search_run(args)
```

Wire the moc pass into the dream run in `paulshaclaw/memory/dream/cli.py` — after the `janitor_fn` definition and before `orchestrator.run_dream(...)`, add a `moc_fn` and pass it through. Add to the `run_dream` call a third pass. In `dream/orchestrator.py`, extend `run_dream` to accept an optional `moc_fn` and run it as a third isolated pass (recording `passes["moc"]`), mirroring the atomize/janitor isolation. In `dream/cli.py`:

```python
    from ..moc import runner as moc_runner

    def moc_fn():
        if args.dry_run:
            return {"summary": {"skipped": "dry-run"}, "warnings": []}
        return {"summary": moc_runner.run_moc(memory_root, now), "warnings": []}
```

and pass `moc_fn=moc_fn` to `orchestrator.run_dream(...)`.

> Confirm the merged `orchestrator.run_dream` signature and the `_run_pass` helper; add a `moc_fn` parameter and a third `_run_pass("moc", moc_fn, passes, errors)` call after janitor, keeping the same isolation/status logic.

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_runner -v`
Expected: PASS (2 tests)

- [x] **Step 5: Commit**

```bash
git add paulshaclaw/memory/moc/runner.py paulshaclaw/memory/moc/cli.py paulshaclaw/memory/cli.py \
        paulshaclaw/memory/dream/cli.py paulshaclaw/memory/dream/orchestrator.py paulshaclaw/memory/tests/test_moc_runner.py
git commit -m "feat(stage2): add moc runner + dream pass + search CLI"
```

---

## Task 8: Conflict-regression + E2E + integration + regression

**Files:**
- Test: `paulshaclaw/memory/tests/test_moc_conflicts.py`, `paulshaclaw/memory/tests/test_moc_e2e.py`
- Modify: `paulshaclaw/memory/tests/stage2_integration_check.sh`, `paulshaclaw/memory/routing.md`

- [x] **Step 1: Write the conflict-regression + E2E tests**

```python
# paulshaclaw/memory/tests/test_moc_conflicts.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.janitor import record_source
from paulshaclaw.memory.replay import selector


def _moc(root: Path) -> None:
    p = root / "knowledge" / "wiki-moc.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nmemory_layer: moc\nmoc_kind: wiki\n---\n# Wiki\n- [[a--sl-1]]\n", encoding="utf-8")


def _slice(root: Path) -> None:
    p = root / "knowledge" / "p" / "a--sl-1.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nslice_id: sl-1\nmemory_layer: knowledge\nproject: p\n"
                 "source_agent: c\nsource_session: s\ncaptured_at: 2026-06-03T00:00:00Z\n"
                 "provenance:\n  repo: r\n  commit: c\n  path: x\n---\nbody\n", encoding="utf-8")


class C4ExclusionTests(unittest.TestCase):
    def test_record_source_skips_moc(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); _moc(root); _slice(root)
            records, _ = record_source.iter_records(root / "knowledge")
            self.assertEqual([r.record_id for r in records], ["sl-1"])  # moc not a record

    def test_selector_skips_moc(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); _moc(root); _slice(root)
            paths = selector.select(root, project="p")
            self.assertTrue(all(p.name != "wiki-moc.md" for p in paths))


if __name__ == "__main__":
    unittest.main()
```

```python
# paulshaclaw/memory/tests/test_moc_e2e.py
from __future__ import annotations

import json
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from paulshaclaw.memory import cli
from paulshaclaw.lifecycle.schema import parse_artifact_text, validate_frontmatter

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RAW = ("---\nmemory_layer: inbox\nproject: paulshaclaw\nsource_agent: claude\n"
        "source_session: sess-moc\nsource_artifact: research\n"
        'captured_at: "2026-06-03T00:00:00Z"\nprovenance:\n  repo: some-other-repo\n'
        "  commit: c\n  path: nope.md\n---\n# Topic A\nalpha body\n")


@contextmanager
def _home(root: Path):
    home = root / "home"; home.mkdir(parents=True, exist_ok=True)
    with mock.patch.dict(os.environ, {"HOME": str(home)}):
        yield


class MocE2ETests(unittest.TestCase):
    def test_dream_moc_makes_obsidian_vault(self):
        with TemporaryDirectory(dir=_REPO_ROOT) as tmp:
            root = Path(tmp)
            raw = root / "inbox" / "research" / "claude" / "2026-06-03" / "s1.md"
            raw.parent.mkdir(parents=True); raw.write_text(_RAW, encoding="utf-8")
            with _home(root):
                rc = cli.main(["memory", "dream", "run", "--memory-root", str(root),
                               "--now", "2026-06-03T05:00:00Z", "--promoter", "identity"])
            self.assertEqual(rc, 0)
            # readable filenames + MOC files
            slices = list((root / "knowledge").rglob("*--sl*.md"))
            self.assertTrue(slices)
            self.assertTrue((root / "knowledge" / "wiki-moc.md").exists())
            # no [[..]] in body; checksum intact (gate passes)
            for s in slices:
                doc = parse_artifact_text(s.read_text(encoding="utf-8"))
                self.assertTrue(validate_frontmatter(frontmatter=doc.frontmatter, body=doc.body).ok)
                self.assertNotIn("[[", doc.body)
            # search finds it
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                cli.main(["memory", "search", "alpha", "--memory-root", str(root)])
            self.assertIn("results", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the tests**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_moc_conflicts paulshaclaw.memory.tests.test_moc_e2e -v`
Expected: PASS. Fix implementation (not tests) on failure.

- [x] **Step 3: Integration check + routing**

Append to `paulshaclaw/memory/tests/stage2_integration_check.sh` before `echo "[stage2] ok"`:

```bash
echo "[stage2] dream(moc) + search over fixtures"
MOC_ROOT="$(mktemp -d)"
mkdir -p "$MOC_ROOT/inbox/research/claude/2026-06-03"
cp "$ROOT_DIR/paulshaclaw/memory/tests/fixtures/atomizer/raw/s1.md" \
   "$MOC_ROOT/inbox/research/claude/2026-06-03/s1.md"
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory dream run \
  --memory-root "$MOC_ROOT" --now "2026-06-03T05:00:00Z" --promoter identity >/dev/null
test -f "$MOC_ROOT/knowledge/wiki-moc.md"
grep -Fq "memory_layer: moc" "$MOC_ROOT/knowledge/wiki-moc.md"
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory search alpha \
  --memory-root "$MOC_ROOT" | grep -Fq '"results"'
```

Append to `paulshaclaw/memory/routing.md`:

```markdown

> **T7 已落地（2026-06）：** `paulsha-mem-moc`（dream 第三 pass）把 `knowledge/` 補成 Obsidian vault：relations → slice 的 `related:` frontmatter `[[..]]`、可讀檔名 `<title>--<slice_id>.md`、三類 MOC（`<project>-moc.md`/`common-sense-moc.md`/`wiki-moc.md`，`memory_layer: moc`）、faceout、FTS5 `psc memory search`。鏈結只進 frontmatter（保 checksum/slice_id）。設計見 `docs/superpowers/specs/2026-06-03-stage2-paulsha-mem-moc-design.md`。
```

- [x] **Step 4: Full regression**

Run: `python3 -m unittest discover -s paulshaclaw/memory/tests -v`
Expected: PASS — all memory tests including T3.2/T4/T5 suites after the connected changes.

Run: `bash paulshaclaw/memory/tests/stage2_integration_check.sh`
Expected: ends with `[stage2] ok`

Run: `python3 -m unittest discover -s tests -v`
Expected: only pre-existing unrelated failures (flaky `test_start_sh`, stage9 snapshot); no new T7 regressions.

- [x] **Step 5: Commit**

```bash
git add paulshaclaw/memory/tests/test_moc_conflicts.py paulshaclaw/memory/tests/test_moc_e2e.py \
        paulshaclaw/memory/tests/stage2_integration_check.sh paulshaclaw/memory/routing.md
git commit -m "test(stage2): add T7 moc conflict-regression, E2E, integration wiring"
```

---

## Verification Summary（實作完成後填）

- `test_moc_*` 聚焦：`python3 -m unittest paulshaclaw.memory.tests.test_moc_frontmatter_io paulshaclaw.memory.tests.test_moc_naming paulshaclaw.memory.tests.test_moc_linker paulshaclaw.memory.tests.test_moc_builder paulshaclaw.memory.tests.test_moc_search paulshaclaw.memory.tests.test_moc_runner paulshaclaw.memory.tests.test_moc_conflicts paulshaclaw.memory.tests.test_moc_e2e -v` 全綠。
- 衝突回歸：C1 由 `test_atomizer_pipeline.ReimportOverwriteTests` 驗證 renamed slice 會被 atomize 依 `slice_id` 覆寫不產重複；C2 由 `test_moc_linker` / `test_moc_e2e` 驗證 `[[..]]` 只進 frontmatter、body checksum 不變；C4 由 `test_moc_conflicts` 驗證 janitor `record_source` 與 replay `selector` 都跳過 `memory_layer: moc`。
- 記憶套件全回歸：`python3 -m unittest discover -s paulshaclaw/memory/tests -v` 全綠（含 T3.2/T4/T5 連動後）。
- 整合檢查：`bash paulshaclaw/memory/tests/stage2_integration_check.sh` 結尾為 `[stage2] ok`，新增 dream(moc)+search fixture check 通過。
- lifecycle / gate：`test_moc_e2e` 逐檔驗證 renamed slices 的 checksum 仍等於 `sha256(body)`，且 `psc memory dream run` 後 `wiki-moc.md`、FTS5 index、`psc memory search` 皆可用。
- top-level `tests/` 回歸：`python3 -m unittest discover -s tests -v` 全綠；本輪未出現 plan 註記的 pre-existing flaky/stage9 失敗。
