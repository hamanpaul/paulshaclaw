## 1. Ledger primitives

- [x] 1.1 Add failing `test_ledger_processing.py`: append/read, `fold_states` (latest state per `<agent>:<session>`), `split`/`promoted` query, no-entry → not-processed, flock, corrupt line → fail-closed, `ts` uses injected `now`.
- [x] 1.2 Implement `paulshaclaw/memory/ledger/processing.py` (`append_state`, `read_events`, `fold_states`, `state_of`).
- [x] 1.3 Add failing `test_ledger_relations.py`: append/read edges, `neighbors(node)`, `(type,from,to)` dedup-on-read, flock, corrupt line → fail-closed, `ts` injected.
- [x] 1.4 Implement `paulshaclaw/memory/ledger/relations.py` (`append_edge`, `read_edges`, `neighbors`).

## 2. Config

- [x] 2.1 Add failing `test_atomizer_config.py`: load defaults, override merge, deterministic `atomizer_config_hash`, unsupported `schema_version` → fail-closed.
- [x] 2.2 Add `paulshaclaw/memory/atomizer/atomizer.yaml` (split boundaries, `max_fragment_chars`, `artifact_kind_map`, `phase_map`, defaults).
- [x] 2.3 Implement `paulshaclaw/memory/atomizer/config.py` (loader + hash, sentinel default override path).

## 3. Deterministic splitter

- [x] 3.1 Add failing `test_atomizer_splitter.py`: turn/heading/artifact boundaries, boundary precedence, `max_fragment_chars` re-split, empty/whitespace → 0 fragments, `fragment_index`/`parent_session_ref`, determinism.
- [x] 3.2 Implement `paulshaclaw/memory/atomizer/splitter.py` (`split(body, config) -> list[Fragment]`, pure).

## 4. Slice frontmatter (union + dual validation)

- [x] 4.1 Add failing `test_slice_frontmatter.py`: union frontmatter complete (Stage 3 required ∪ Topic 4 contract), `slice_id` deterministic, `checksum == sha256(body)`, `artifact_kind`/`phase` mapping incl. defaults, passes `lifecycle.schema.validate_frontmatter`, passes Topic 4 field-presence check, missing field → errors.
- [x] 4.2 Implement `paulshaclaw/memory/atomizer/slice_frontmatter.py` (`build_slice_frontmatter`, `validate`).

## 5. Promoter

- [x] 5.1 Add failing `test_atomizer_promoter.py`: `IdentityPromoter` 1:1, slice carries `distilled_from`/`fragment_ref`.
- [x] 5.2 Implement `paulshaclaw/memory/atomizer/promoter.py` (`Promoter` interface + `IdentityPromoter`).

## 6. Pipeline (two passes)

- [x] 6.1 Add failing `test_atomizer_scanner.py` (unit): `split_pass` writes fragments + `fragment_of` edges + `state=split` + archives raw; `promote_pass` writes slices + edges + `state=promoted` + archives fragments; dry-run writes nothing.
- [x] 6.2 Implement `paulshaclaw/memory/atomizer/pipeline.py` (`run` = `split_pass` + `promote_pass`, step order product→ledger→archive, fail-closed/degrade per design §5).

## 7. CLI

- [x] 7.1 Add failing `test_atomizer_cli.py`: `psc memory atomize --memory-root … [--raw-root] [--now] [--dry-run]` prints JSON summary; dry-run writes nothing.
- [x] 7.2 Implement `paulshaclaw/memory/atomizer/cli.py` and wire a `atomize` group into `paulshaclaw/memory/cli.py`.

## 8. End-to-end + cross-stage conformance

- [x] 8.1 Add fixtures `paulshaclaw/memory/tests/fixtures/atomizer/raw/<…>.md` (importer-shaped frontmatter, body with structural boundaries).
- [x] 8.2 Add `test_atomizer_e2e.py` scenarios: A split_pass, B promote_pass, C 1:1 count, D idempotent re-run, E crash-resume, F flow-through (working layers empty, archive holds both), G re-import overwrite, H validation fail-closed (stays `split`), I dry-run.
- [x] 8.3 Add cross-stage conformance: a produced knowledge slice passes `python3 -m paulshaclaw.lifecycle.gate`.
- [x] 8.4 Assert ledgers contain no raw record body content.

## 9. Integration + regression + docs

- [x] 9.1 Extend `paulshaclaw/memory/tests/stage2_integration_check.sh` with an `atomize --dry-run` guard over fixtures.
- [x] 9.2 Run `python3 -m unittest discover -s paulshaclaw/memory/tests -v` (all green).
- [x] 9.3 Run `python3 -m unittest discover -s tests -v` and record any pre-existing unrelated failures (e.g. flaky `test_start_sh`, stage9 snapshot) — no new T3 regressions.
- [x] 9.4 Update `paulshaclaw/memory/routing.md` to point at the atomizer promotion path and ledgers.
- [x] 9.5 Mark OpenSpec tasks complete and record verification summary at the bottom of this file.

## Verification Summary

- `python3 -m unittest discover -s paulshaclaw/memory/tests -v`: 269 tests OK.
- `bash paulshaclaw/memory/tests/stage2_integration_check.sh`: exits 0, ends with `[stage2] ok`.
- `python3 -m unittest discover -s tests -v`: 368 tests OK on isolated full-suite rerun.
- Final chained rerun exposed an unrelated timing-sensitive Stage 9 socket permission race; the Stage 9 test passes in isolation and the full `tests/` suite passes when run directly. No T3 regression found.
