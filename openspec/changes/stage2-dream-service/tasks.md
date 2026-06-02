## 1. Dream run ledger

- [ ] 1.1 Add failing `test_ledger_dream.py`: `append_run`/`last_run` round-trip, `backlog_depth` counts unprocessed raw sessions, flock, corrupt line → fail-closed, `ts` uses injected `now`.
- [ ] 1.2 Implement `paulshaclaw/memory/ledger/dream.py` (`dream_path`, `append_run`, `read_runs`, `last_run`, `backlog_depth`).

## 2. Idle probe

- [ ] 2.1 Add failing `test_dream_idle.py`: `is_idle` true/false for an injected load probe; indeterminate probe (raises) → True (fail-safe-to-run).
- [ ] 2.2 Implement `paulshaclaw/memory/dream/idle.py` (`is_idle(max_load, probe=os.getloadavg)`).

## 3. Proposal framework (skeleton)

- [ ] 3.1 Add failing `test_dream_proposals.py`: `append` writes `runtime/proposals/<id>.json`; `pending()` lists pending; `requires_approval(kind)` true for `merge`/`supersede`/`contradiction`, configurable for `decay`.
- [ ] 3.2 Implement `paulshaclaw/memory/dream/proposals.py` (`Proposal`, `append`, `pending`, `requires_approval`).

## 4. Orchestrator

- [ ] 4.1 Add failing `test_dream_orchestrator.py` with injected fake atomize/janitor callables: order atomize→janitor; `status` ok/partial/failed; one pass raising → other still runs + error recorded; `dry_run` writes no `dream.jsonl`.
- [ ] 4.2 Implement `paulshaclaw/memory/dream/orchestrator.py` (`run_dream(memory_root, *, atomize_fn, janitor_fn, now, dry_run)` returning a summary and appending a run record; default `atomize_fn`/`janitor_fn` bind to the real entrypoints so tests can inject fakes).

## 5. Dream CLI + idle wrapper + systemd templates

- [ ] 5.1 Add failing `test_dream_cli.py`: `dream run --dry-run` prints summary and writes nothing; `dream run --require-idle` with an injected busy probe skips (exit 0, no record); `dream status` prints last run + backlog.
- [ ] 5.2 Implement `paulshaclaw/memory/dream/cli.py` (build atom/janitor configs + promoter via the Topic 3.2 helper; `run`/`status`; `--require-idle` gate using `idle.is_idle`).
- [ ] 5.3 Wire `dream` subcommand group into `paulshaclaw/memory/cli.py`.
- [ ] 5.4 Add `paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service` and `.timer` (`OnCalendar=Mon..Fri 05:00`, ExecStart `... memory dream run --require-idle`) and `paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh`.
- [ ] 5.5 Add `test_dream_systemd_template.py`: assert the unit/timer files exist, the timer contains `OnCalendar` Mon–Fri morning, and the service ExecStart invokes `dream run --require-idle`.

## 6. Replay selector

- [ ] 6.1 Add failing `test_replay_selector.py`: project filter; tags any-match; entity via `relations.neighbors("entity:NAME")`; facets AND-composed; active-set excludes decayed by default; `include_decayed=True` includes them; no facet → error.
- [ ] 6.2 Implement `paulshaclaw/memory/replay/selector.py` (`select(memory_root, *, project, tags, entity, include_decayed)`).

## 7. Replay bundle

- [ ] 7.1 Add failing `test_replay_bundle.py`: `build` writes `manifest.json` (`raw_excluded: true`, selection, counts), `slices/<id>.md` copies, and `ledger.jsonl` of touching lifecycle/relations/processing events; bundle contains no raw body; empty selection → empty bundle + warning, not error.
- [ ] 7.2 Implement `paulshaclaw/memory/replay/bundle.py` (`build(memory_root, slice_paths, out_dir, selection, now)`).
- [ ] 7.3 Implement `paulshaclaw/memory/replay/cli.py` (`bundle --project/--tag/--entity [--include-decayed] --out`); wire `bundle` subcommand into `paulshaclaw/memory/cli.py`.

## 8. End-to-end + integration + regression

- [ ] 8.1 Add `test_dream_e2e.py`: seed a memory root with raw sessions; `dream run` (identity promoter) → `dream.jsonl` status ok, atomize+janitor both ran; second run idempotent; `dream status` reflects it.
- [ ] 8.2 Add a bundle E2E: after `dream run`, `bundle --project <p>` over the produced knowledge → bundle has slices + ledger, manifest `raw_excluded: true`, and no raw body present.
- [ ] 8.3 Extend `paulshaclaw/memory/tests/stage2_integration_check.sh` with `dream run --dry-run` and a `bundle` over fixtures (assert a manifest/summary marker).
- [ ] 8.4 Run `python3 -m unittest discover -s paulshaclaw/memory/tests -v` (all green) and `python3 -m unittest discover -s tests -v` (only pre-existing unrelated failures).
- [ ] 8.5 Update `paulshaclaw/memory/routing.md` for the dream service + replay bundle; mark OpenSpec tasks complete and record the verification summary below.

## Verification Summary

(To be filled at end of implementation: focused dream/replay test results, full memory-suite result, integration-check output, systemd template note, opt-in manual timer-install note, and `tests/` regression status.)
