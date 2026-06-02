# Design — Stage 2 Topic 5 Dream Service (orchestrator + replay bundle)

> Canonical design: `docs/superpowers/specs/2026-06-02-stage2-dream-service-design.md`. This file captures the change-scoped architecture and key decisions.

## Context

- Topic 3/3.2 atomize (`atomizer.pipeline.run`) and Topic 4 janitor (`janitor.scanner.run_scan`) are one-shot, deterministic, keyword-arg entrypoints.
- Cross-session ledgers exist: `lifecycle.jsonl`, `processing.jsonl`, `relations.jsonl` (incl. `mentions` entity edges), plus `retrieval_set.active_records()`.
- Topic 8 already owns `psc memory replay` (policy replay) — the new replay bundle command is `bundle`.
- WSL `systemctl --user` is available (`running`, `Linger=no`); the LLM backend is the configurable Topic 3.2 `agent_exec`.

## Key Decisions

1. **Orchestrate, don't reimplement.** The dream service calls the existing pass entrypoints in order (atomize → janitor) and records a run; it never reimplements their logic.
2. **Pass isolation.** Each pass runs in its own try; one failing pass is recorded and does not block the other or crash the run. Status = `ok`/`partial`/`failed`.
3. **Idle in Python, schedule in systemd.** `--require-idle` does the idle decision in a testable Python probe (fail-safe-to-run on indeterminate); the timer template only sets the schedule (Mon–Fri morning). Templates ship; install (enable-linger + enable timer) is an ops step.
4. **Proposal-first, framework-only in MVP.** `runtime/proposals/` + `requires_approval()` exist as the gate for future cross-session changes (B/C); the MVP generates no proposals and has no auto-apply path.
5. **Replay reads only distilled + ledger.** `bundle` selects via project/tag/entity facets (AND) + active-set (Topic 4), requires at least one facet, and emits `manifest.json` (`raw_excluded: true`) + `slices/` + `ledger.jsonl`. Never touches raw queue/inbox/archive.
6. **Determinism + privacy.** Inject `now`; append-only + flock for `dream.jsonl`; logs and records carry no slice body or raw content; corrupt `dream.jsonl` fails closed on read.
7. **Backend via config.** Dream uses the Topic 3.2 `agent_exec` config, so the model is a config value (Copilot CLI for WSL dev, gemma4/GB10 in prod).

## Component Boundaries

- `dream/orchestrator.py` — `run_dream(...)`: build promoter from config → atomize → janitor → append run record.
- `dream/idle.py` — `is_idle(max_load)` over an injectable probe.
- `dream/proposals.py` — `append`/`pending`/`requires_approval`.
- `dream/cli.py` — `dream run [--dry-run] [--require-idle]`, `dream status`.
- `dream/systemd/*`, `dream/scripts/dream-idle-wrapper.sh` — schedule templates.
- `ledger/dream.py` — `append_run`/`last_run`/`backlog_depth`.
- `replay/selector.py` — `select(...)`; `replay/bundle.py` — `build(...)`; `replay/cli.py` — `bundle`.

## Error / Guardrail Posture

Pass failures degrade (recorded, isolated); LLM-down degrades atomize per-session (retry next day); `dream.jsonl` write failure exits non-zero but pass ledgers remain authoritative; idle indeterminate proceeds; bundle requires a facet and fails loud on corrupt ledgers; bundle and logs never expose raw content.

## Out of Scope

Cross-session lineage (B) and entity graph (C) as follow-up dream tasks; wake-up bundle (Topic 6); free-text/vector retrieval (Topic 7); auto-install of the timer; coupling to `obs-auto-moc`; basing on `paulsha-memory` (Topic 9).
