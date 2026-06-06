## 1. Gate types + manifest + schema condition

- [ ] 1.1 Add failing `test_syncback_gate.py`: `_check_schema_unextended` passes for canonical fields; `SYNC_MANIFEST` non-empty tuple of strings.
- [ ] 1.2 Implement `syncback/gate.py` types (`ConditionResult`, `GateVerdict`), `SYNC_MANIFEST`, `_CANONICAL_REQUIRED`, `_check_schema_unextended`; `__init__.py` exports.

## 2. File-inspection conditions (fail-closed)

- [ ] 2.1 Add failing tests: evidence present passes; missing/empty evidence fails; review mergeable passes; blocking/missing-section/missing-file fails.
- [ ] 2.2 Implement `_check_evidence_present` (required files exist + non-empty) and `_check_review_clear` (parse `結論` section; mergeable + no live blocking marker), both fail-closed.

## 3. Test-running conditions + aggregation

- [ ] 3.1 Add failing tests: all-pass → ok + manifest; failing runner → fail + empty manifest; runner raise → fail-closed; `run_tests=False` → test conditions fail.
- [ ] 3.2 Implement `_default_test_runner` (subprocess `unittest`), `_check_tests`, `_check_decay_evidence`, and `evaluate_gate(repo_root, *, now, run_tests=True, test_runner=...)` aggregating 5 conditions; manifest only when ok.

## 4. CLI + subcommand

- [ ] 4.1 Add failing `test_syncback_cli.py`: all-pass rc 0; blocking review rc 1; `--json` emits verdict (inject fake runner via `main(..., _test_runner=...)`).
- [ ] 4.2 Implement `syncback/cli.py` (`run`/`main`, `check --repo-root --no-run-tests --json --now`); register `syncback` subcommand + `_syncback` handler in `memory/cli.py`.

## 5. Docs, suite, real-run, gate, archive

- [x] 5.1 Write `syncback/README.md` (fail-closed, read-only, deterministic, 5 conditions, installable-package entity).
- [x] 5.2 Full suite `python3 -m unittest discover -s paulshaclaw/memory/tests` green.
- [x] 5.3 Real-run sanity: `python3 -m paulshaclaw.memory.cli memory syncback check --repo-root .` runs the real modules and prints per-condition status (adjust `TESTS_*` tuples if any module name differs).
- [x] 5.4 Repo policy / lint gate green.
- [ ] 5.5 openspec-archive after merge + sync spec delta into `openspec/specs/stage2-memory-governance/spec.md`; tick T9 in roadmap §5.4.
