## Why

Stage 2 declares a sync-back gate (5 conditions governing when the project-tuned paulsha-memory package may be pushed back to `hamanpaul/custom-skills`), but it exists only as prose in the spec + `custom-skills/paulsha-memory/README.md`. Nothing enforces it: a reviewer must eyeball the conditions. T9 turns the gate into an executable, verifiable check — the last Stage 2 governance piece.

## What Changes

- Add `paulshaclaw/memory/syncback/` (code module): `evaluate_gate(repo_root, *, now, run_tests=True, test_runner=...) -> GateVerdict` evaluating the 5 conditions and aggregating a structured pass/fail verdict + an informational sync manifest.
- Conditions, executable: (1) importer/classifier/replay tests pass (runs targeted modules), (2) decayed/reactivation tests pass + evidence present, (3) evidence files present and non-empty, (4) `review.md` has a non-blocking `結論`/Conclusion, (5) `lifecycle.schema.REQUIRED_FRONTMATTER_FIELDS` ⊆ canonical `{slice_id, artifact_kind, supersedes, checksum, phase}` (Stage 2 added no required fields).
- Add `psc memory syncback check` CLI (text + `--json`; exit 0 on pass, 1 otherwise; `--no-run-tests` inspects other conditions but fails the test conditions).
- Fail-closed (any uncertainty → that condition fails → gate fails), read-only (no copy into staging, no external push), deterministic (`now` injected; `test_runner` injectable so the gate's own tests never invoke unittest).
- Sync-back entity is the installable package (memory modules + hooks + install.sh + future MCP server), not a skill — the "paulsha-memory skill" notion was retired (roadmap v0.5).
- Defer: actual staging copy, external push, package export, CI wiring — all Non-Goals.

## Capabilities

### New Capabilities

None. Extends `stage2-memory-governance` by making the existing sync-back gate executable.

### Modified Capabilities

- `stage2-memory-governance`: Add an executable sync-back gate that programmatically verifies the five conditions and returns a structured verdict, fail-closed and read-only.

## Impact

- New code: `paulshaclaw/memory/syncback/{__init__,gate,cli}.py` + `README.md`.
- Modified: `paulshaclaw/memory/cli.py` (register `syncback` subcommand).
- Tests: `paulshaclaw/memory/tests/test_syncback_gate.py`, `test_syncback_cli.py`.
- Reuse: `paulshaclaw.lifecycle.schema.REQUIRED_FRONTMATTER_FIELDS`; existing test modules; `docs/superpowers/workstreams/stage2-paulsha-memory/{evidence/,review.md}`.
- Dependencies: none new (stdlib + existing modules).
- Non-Goals: staging copy into `custom-skills/paulsha-memory/`, push to `hamanpaul/custom-skills`, package export, CI gating.
