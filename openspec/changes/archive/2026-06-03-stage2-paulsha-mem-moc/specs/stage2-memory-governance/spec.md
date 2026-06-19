## ADDED Requirements

### Requirement: Obsidian-native relation links in slice frontmatter

Stage 2 SHALL materialize the semantic relations recorded in `runtime/ledger/relations.jsonl` into each knowledge slice as Obsidian-native links in the slice frontmatter only. Links MUST be written to a `related:` frontmatter list (and an `aliases:` entry for the readable title), and MUST NOT be written into the slice body. `relates_to` edges MUST produce bidirectional `[[<basename>]]` links between slices; `mentions` edges MUST produce `[[<entity>]]` links. The materialization MUST NOT modify the slice body, so the Stage 3 `checksum` and the content-derived `slice_id` remain unchanged. `relations.jsonl` remains the append-only source of truth; the materializer only reads it.

#### Scenario: Links never touch the body

- **WHEN** the materializer adds `related:` links to a slice
- **THEN** the slice body MUST be unchanged
- **THEN** the slice MUST still pass `paulshaclaw.lifecycle.schema.validate_frontmatter` (checksum intact) and its `slice_id` MUST be unchanged

#### Scenario: Bidirectional slice links

- **WHEN** slice A has a `relates_to` edge to slice B
- **THEN** A's `related:` MUST link B and B's `related:` MUST link A

### Requirement: Readable slice filenames keyed by slice_id

Stage 2 SHALL name knowledge slice files `<readable-title>--<slice_id>.md` so the Obsidian graph shows readable nodes while `slice_id` stays the stable identity in frontmatter. The atomizer MUST locate and overwrite an existing slice by globbing `*--<slice_id>.md` (or the legacy `<slice_id>.md`) rather than assuming a fixed filename, so re-imports overwrite in place and never create a duplicate `slice_id`. The title MUST be derived deterministically (frontmatter `title`, else first heading, else `<artifact_kind>-<project>`).

#### Scenario: Re-import overwrites, no duplicate slice_id

- **WHEN** a slice has been renamed to `<title>--<slice_id>.md` and the same session is re-imported with changed content
- **THEN** the atomizer MUST overwrite that file
- **THEN** no second file with the same `slice_id` MUST exist (the replay selector MUST NOT raise a duplicate-slice_id error)

### Requirement: Three MOC index files

Stage 2 SHALL generate three Maps-of-Content under `knowledge/` per the original memory design: a `<project>-moc.md` per project, a `common-sense-moc.md`, and a `wiki-moc.md` global index. Each MOC file MUST carry `memory_layer: moc` frontmatter. MOC files MUST list only active (non-decayed) slices in their active sections, link to them by basename, and MUST NOT themselves be treated as knowledge records.

#### Scenario: MOC files are excluded from knowledge-record scanners

- **WHEN** the janitor record source or the replay selector scans `knowledge/`
- **THEN** files with `memory_layer: moc` MUST be skipped and MUST NOT be treated as slices

#### Scenario: Wiki MOC indexes all active slices

- **WHEN** `wiki-moc.md` is generated
- **THEN** it MUST list every active slice under an active section

### Requirement: Faceout surfacing in wiki MOC

Stage 2 SHALL surface decayed (faceout) knowledge in `wiki-moc.md` under a dedicated faceout section listing the decayed slice, its decay reason, and the event time, sourced from the lifecycle ledger. Faceout MUST NOT delete the slice file and MUST NOT mutate the slice's own frontmatter; the lifecycle ledger remains the source of truth.

#### Scenario: Decayed slice is surfaced, not deleted

- **WHEN** a slice is decayed
- **THEN** `wiki-moc.md` MUST list it under the faceout section with its reason
- **THEN** the slice file MUST still exist under `knowledge/`

### Requirement: Lexical search index and query

Stage 2 SHALL build a SQLite FTS5 lexical index of knowledge slices at `runtime/indexes/retrieval.db` and expose `psc memory search`. The index MUST cover slice title, tags, body, and project, plus per-slice metadata (`captured_at`, active flag, and a bidirectional-link `link_weight`). Queries MUST support project scoping, default to the active set (excluding decayed unless `--include-decayed`), and rank by a deterministic weighted combination of BM25, recency, and `link_weight`. A missing index MUST produce an actionable error rather than silently returning nothing.

#### Scenario: Search is project-scopable and active by default

- **WHEN** `psc memory search "<q>" --project P` runs
- **THEN** results MUST be limited to project P and MUST exclude decayed slices unless `--include-decayed` is set

#### Scenario: Missing index errors clearly

- **WHEN** `psc memory search` runs with no index present
- **THEN** it MUST report that the index is not built (run the dream/moc pass) rather than return an empty result silently

### Requirement: MOC materialization runs as an isolated, deterministic dream pass

Stage 2 SHALL run the MOC materialization (rename, link, MOC build, faceout, index) as a third dream pass after atomize and janitor: `atomize → janitor → moc`. The pass MUST be deterministic (inject `now`, no LLM), idempotent (a re-run reproduces the same `related:`/MOC/index), and isolated (a failure is recorded and MUST NOT block the other passes or crash the run). It MUST only touch `knowledge/` and MUST NOT couple to or invoke `obs-auto-moc`.

#### Scenario: MOC pass runs after janitor and is isolated

- **WHEN** the dream service runs
- **THEN** the moc pass MUST run after the janitor pass
- **THEN** a failure in the moc pass MUST be recorded in the dream run record without crashing the run

#### Scenario: Re-run is idempotent

- **WHEN** the moc pass runs twice over unchanged inputs
- **THEN** the produced `related:` links, MOC files, and index MUST be identical
