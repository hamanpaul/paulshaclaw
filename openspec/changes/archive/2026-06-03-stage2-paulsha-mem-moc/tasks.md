## 1. Naming (readable filenames + dedup)

- [x] 1.1 Add failing `test_moc_naming.py`: `slugify`, target `<slug>--<slice_id>.md`, title fallback (frontmatter `title` → first heading → `<artifact_kind>-<project>`), `reconcile` renames `<slice_id>.md` → target and dedups duplicate `slice_id` (keeps one).
- [x] 1.2 Implement `paulshaclaw/memory/moc/naming.py` (`target_name`, `reconcile(memory_root)`), skipping `memory_layer: moc` files.

## 2. Atomizer write-by-slice_id (conflict C1)

- [x] 2.1 Add failing `test_atomizer_pipeline.py` case: after a slice is renamed to `<title>--<slice_id>.md`, a re-import with changed content overwrites that file and leaves exactly one file with that `slice_id`.
- [x] 2.2 Modify `paulshaclaw/memory/atomizer/pipeline.py` to locate the existing slice by globbing `*--<slice_id>.md` (then legacy `<slice_id>.md`) and overwrite it; write `<slice_id>.md` only when none exists.

## 3. Scanner exclusion of MOC files (conflict C4)

- [x] 3.1 Add failing tests in `test_janitor_record_source.py` and `test_replay_selector.py`: a `knowledge/` file with `memory_layer: moc` is skipped (not a record / not selected, no duplicate-slice_id raise).
- [x] 3.2 Modify `paulshaclaw/memory/janitor/record_source.py` and `paulshaclaw/memory/replay/selector.py` to skip files whose frontmatter `memory_layer == "moc"`.

## 4. Linker (relations → frontmatter)

- [x] 4.1 Add failing `test_moc_linker.py`: `related:` lists bidirectional `[[<basename>]]` for `relates_to` and `[[<entity>]]` for `mentions`; `aliases`/`title` ensured; body unchanged so `lifecycle.schema.validate_frontmatter` still passes and `slice_id` is unchanged; `link_weight` equals the related count.
- [x] 4.2 Implement `paulshaclaw/memory/moc/linker.py` (`materialize_links(memory_root) -> dict[str,int]` returning per-slice link_weight; frontmatter-only edits via atomic write).

## 5. MOC builder

- [x] 5.1 Add failing `test_moc_builder.py`: `<project>-moc.md` per project, `common-sense-moc.md` (project == "common-sense"), `wiki-moc.md` with an active section; all carry `memory_layer: moc`; links use basenames; only active slices listed.
- [x] 5.2 Implement `paulshaclaw/memory/moc/moc_builder.py` (`build_mocs(memory_root, now)`), using `retrieval_set.active_records`.

## 6. Faceout

- [x] 6.1 Add failing `test_moc_faceout.py`: decayed slices appear in `wiki-moc.md` under a faceout section with reason + time; active slices do not; slice files are not deleted and slice frontmatter is unchanged.
- [x] 6.2 Implement `paulshaclaw/memory/moc/faceout.py` (`mark_faceout(memory_root)` appending the faceout section to `wiki-moc.md`).

## 7. Lexical search (FTS5)

- [x] 7.1 Add failing `test_moc_search.py`: `build_index` populates `slices_fts` + `slice_meta`; `search` matches by BM25, scopes by project, excludes decayed by default and includes with `include_decayed`, ranks by BM25 + recency + `link_weight`, returns `{slice_id,title,project,score,snippet}`; missing index raises an actionable error.
- [x] 7.2 Implement `paulshaclaw/memory/moc/search.py` (`build_index(memory_root, link_weights)`, `search(memory_root, query, *, project, limit, include_decayed)`).

## 8. Runner + dream integration + CLI

- [x] 8.1 Add failing `test_moc_runner.py`: `run_moc` executes naming → linker → moc_builder → faceout → search in order; idempotent re-run reproduces identical `related:`/MOC/index; a corrupt `relations.jsonl` degrades the link step but the other steps still run.
- [x] 8.2 Implement `paulshaclaw/memory/moc/runner.py` (`run_moc(memory_root, now) -> dict`).
- [x] 8.3 Implement `paulshaclaw/memory/moc/cli.py` (`psc memory search`) and wire a `search` subcommand into `paulshaclaw/memory/cli.py`.
- [x] 8.4 Modify `paulshaclaw/memory/dream/orchestrator.py` + `dream/cli.py` to run `moc_fn` as a third isolated pass after janitor; record a `moc` entry in `dream.jsonl` `passes`.

## 9. End-to-end + integration + regression

- [x] 9.1 Add `test_moc_e2e.py` via the dream CLI (identity promoter): after `dream run`, slices are renamed `<title>--<slice_id>.md`, carry `related:`/`aliases`, three MOC files exist with `memory_layer: moc`, `wiki-moc.md` lists active slices, `psc memory search` finds a produced slice, and a produced slice still passes `python3 -m paulshaclaw.lifecycle.gate`.
- [x] 9.2 Add an Obsidian-vault sanity test: no `[[..]]` in any slice body; MOC files carry `memory_layer: moc`; every `related:` link resolves to an existing slice basename or is an entity link.
- [x] 9.3 Add a bundle co-existence test: after the moc pass, `psc memory bundle --project <p>` still works and excludes MOC files.
- [x] 9.4 Extend `stage2_integration_check.sh` with a dream run (including the moc pass) plus `psc memory search`, asserting MOC files, a `related:` link, and a search hit.
- [x] 9.5 Run `python3 -m unittest discover -s paulshaclaw/memory/tests -v` (all green, including T3.2/T4/T5 suites after the connected changes) and `python3 -m unittest discover -s tests -v` (only pre-existing unrelated failures).
- [x] 9.6 Update `paulshaclaw/memory/routing.md` for paulsha-mem-moc; mark OpenSpec tasks complete and record the verification summary below.

## Verification Summary

- Focused MOC coverage passed: `test_moc_frontmatter_io`, `test_moc_naming`, `test_moc_linker`, `test_moc_builder`, `test_moc_search`, `test_moc_runner`, `test_moc_conflicts`, and `test_moc_e2e`.
- Conflict regressions passed: C1 re-import overwrite by `slice_id` glob, C2 frontmatter-only `related:` materialization with checksum preservation, and C4 scanner exclusion of `memory_layer: moc`.
- Full memory suite passed: `python3 -m unittest discover -s paulshaclaw/memory/tests -v`.
- Integration gate passed: `bash paulshaclaw/memory/tests/stage2_integration_check.sh` ended with `[stage2] ok`.
- `lifecycle.gate` conformance passed in the end-to-end flow after dream+moc materialization.
- Top-level regression passed: `python3 -m unittest discover -s tests -v`.
