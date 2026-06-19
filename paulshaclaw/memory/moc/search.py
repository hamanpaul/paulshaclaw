# paulshaclaw/memory/moc/search.py
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..ledger import lifecycle
from ..ledger import retrieval_set
from . import frontmatter_io as fio

INDEX_WRITE_BATCH_SIZE = 100


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
        events = lifecycle.read_events(memory_root)

        def flush_batch(rows: list[tuple[str, str, str, str, str, str]]) -> None:
            if not rows:
                return
            active = set(
                retrieval_set.active_records(
                    memory_root,
                    [row[0] for row in rows],
                    events=events,
                )
            )
            conn.executemany(
                "INSERT INTO slices_fts VALUES (?,?,?,?,?)",
                [(sid, project, title, tags, body) for sid, project, title, tags, body, _captured_at in rows],
            )
            conn.executemany(
                "INSERT INTO slice_meta VALUES (?,?,?,?,?)",
                [
                    (sid, project, captured_at, 1 if sid in active else 0, link_weights.get(sid, 0))
                    for sid, project, _title, _tags, _body, captured_at in rows
                ],
            )

        rows: list[tuple[str, str, str, str, str, str]] = []
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
                if len(rows) >= INDEX_WRITE_BATCH_SIZE:
                    flush_batch(rows)
                    rows.clear()
        flush_batch(rows)
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
