# Design — Stage 2 T9 sync-back gate

Full design: `docs/superpowers/specs/2026-06-06-stage2-t9-syncback-gate-design.md`. Plan: `docs/superpowers/plans/2026-06-06-stage2-t9-syncback-gate.md`. Binding decisions below.

## Architecture

`memory/syncback/gate.py` evaluates the 5 sync-back conditions into a `GateVerdict`. Two conditions run targeted test modules via an injectable `test_runner` (default: `python3 -m unittest <modules>` subprocess); the rest are file/schema inspections. `memory/syncback/cli.py` exposes `psc memory syncback check`. Scope A: gate only — no staging copy, no external push.

## Data model
- `ConditionResult(id, name, passed, detail)`; `GateVerdict(ok, ts, conditions, sync_manifest)`.
- Condition ids: `tests`, `decay_evidence`, `evidence_present`, `review_clear`, `schema_unextended`.
- `sync_manifest` populated only when `ok` (informational list of package paths that WOULD be synced; never executed here).

## Conditions
- `tests` / `decay_evidence`: run targeted modules; runner returns False or raises → fail. `run_tests=False` → fail (governance can't skip tests).
- `evidence_present`: required files under the evidence dir exist and are non-empty.
- `review_clear`: `review.md` has a `結論`/Conclusion section that states mergeable and has no live blocking marker (`無阻斷性` is the allowed non-blocking phrasing).
- `schema_unextended`: `set(REQUIRED_FRONTMATTER_FIELDS) ⊆ {slice_id, artifact_kind, supersedes, checksum, phase}`.

## Guardrails
- Fail-closed: missing/unreadable file, runner raise, no conclusion section → that condition fails → gate fails. Never default to pass.
- Read-only: never copies into `custom-skills/paulsha-memory/` nor pushes to `hamanpaul/custom-skills`.
- Deterministic: `now` injected at the CLI boundary; `test_runner` injectable so the gate's own unit tests never invoke unittest.
- No leakage: `detail` never contains secrets or raw exception text.

## Testing
TDD with an injected fake `test_runner` (unittest never really runs): all-pass → ok + manifest; each condition's fail path; fail-closed (runner raise / missing files / no conclusion); `now` injection; CLI rc 0/1 + `--json`. A separate real-run sanity (`psc memory syncback check --repo-root .`) confirms the default runner wiring against the actual test modules.
