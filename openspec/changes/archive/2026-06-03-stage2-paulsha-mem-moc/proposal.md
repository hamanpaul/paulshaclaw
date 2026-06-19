## Why

The original memory design (`docs/research/00`) always intended `~/.agents/memory` to be Obsidian-native: every knowledge file linked into `{{project}}-moc.md` / `common-sense-moc.md` / `wiki-moc.md`, with Obsidian associations and a faceout mechanism, so a human and the agents can co-govern the vault in Obsidian. Stage 2 built the markdown substrate (inbox/knowledge slices) and the runtime ledgers, but the relations live only in `relations.jsonl`, slice filenames are opaque hashes, there are no MOC files, and `knowledge/` is not openable as an Obsidian vault. The plan drifted from "memory in Obsidian" — Obsidian's graph, backlinks, and Dataview cannot see any of the semantic structure.

This change adds `paulsha-mem-moc` (the dream-mode core organizer, the self-built equivalent of the reference-only `obs-auto-moc`, renamed to avoid confusion): a deterministic dream pass that materializes the existing relations into Obsidian-native links, gives slices readable filenames, generates the three MOC index files, surfaces faceout, and builds a lexical search index. It stays purely deterministic — semantic cross-session work (entity-graph normalization T5-C, evolution lineage T5-B) is explicitly out of scope.

## What Changes

- Add `paulshaclaw.memory.moc` package: `naming` (readable `<title>--<slice_id>.md`), `linker` (relations → `related:`/`aliases:` frontmatter, bidirectional, body untouched), `moc_builder` (three MOC files), `faceout` (decayed → wiki-moc), `search` (FTS5 index + query), `runner` (the moc pass), `cli` (`psc memory search`).
- Run the moc pass as a third, isolated, deterministic dream pass after atomize and janitor.
- Resolve four conflicts with existing topics: links go in frontmatter only (preserve Stage 3 checksum + content-derived slice_id); slices are addressed by `*--<slice_id>.md` glob (no duplicate slice_id on re-import); MOC files carry `memory_layer: moc` and are excluded from the janitor record source and replay selector; the moc pass always runs after atomize so materialized links are regenerated each pass.
- Connected changes: `atomizer/pipeline.py` (glob-by-slice_id write), `janitor/record_source.py` + `replay/selector.py` (skip `memory_layer: moc`), `dream/orchestrator.py` + `dream/cli.py` (add moc pass).

## Capabilities

### New Capabilities

None. This change extends `stage2-memory-governance` with the Obsidian-native MOC / linking / lexical-search contract.

### Modified Capabilities

- `stage2-memory-governance`: Add Obsidian-native relation links, readable slice filenames, three MOC files, faceout surfacing, lexical search, and the isolated/idempotent MOC dream pass.

## Impact

- Affected runtime code (new): `paulshaclaw/memory/moc/{naming,linker,moc_builder,faceout,search,runner,cli}.py`.
- Affected runtime code (modified, conflict resolutions): `paulshaclaw/memory/atomizer/pipeline.py`, `paulshaclaw/memory/janitor/record_source.py`, `paulshaclaw/memory/replay/selector.py`, `paulshaclaw/memory/dream/orchestrator.py`, `paulshaclaw/memory/dream/cli.py`.
- Affected layout (new): `knowledge/<project>-moc.md`, `knowledge/common-sense-moc.md`, `knowledge/wiki-moc.md`, `runtime/indexes/retrieval.db`; slice filenames become `<title>--<slice_id>.md`; slice frontmatter gains `title`/`aliases`/`related`.
- Reuse (read-only / stable entrypoints): `ledger/relations`, `ledger/retrieval_set`, `ledger/lifecycle`, `lifecycle.schema`.
- Affected tests: moc naming/linker/moc_builder/faceout/search/runner, the four conflict-regression tests, the connected-change tests, e2e via dream, Obsidian-vault sanity, integration check, and T3.2/T4/T5 regression after the connected changes.
- Non-Goals: any LLM / semantic understanding in T7; cross-session entity-graph normalization (T5-C); evolution lineage (T5-B); SkillOpt (evolve follow-up); coupling to or use of `obs-auto-moc`; wake-up bundle (Topic 6).
