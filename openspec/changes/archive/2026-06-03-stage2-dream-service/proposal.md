## Why

Topic 3/3.2 (atomize) and Topic 4 (janitor) are one-shot CLI passes that must be invoked manually. The memory hub's intent is an always-on "dream mode" that runs on a workday-morning idle schedule, consolidates the day's sessions into knowledge, governs decay/reactivation, and prepares replayable bundles — without a human typing commands. Today nothing orchestrates these passes on a schedule, nothing records dream-run status, and there is no governance-compliant replay bundle (replay must read only distilled artefacts and ledger events, never raw prompts).

This change adds the Topic 5 dream service MVP: a scheduled, idle-gated orchestrator over the existing passes with a run ledger and status, a proposal-first framework for future cross-session changes, and a replay bundle assembler. It deliberately stays an orchestrator — cross-session evolution lineage (B) and the global entity graph (C) are documented as follow-up dream tasks, not implemented here.

## What Changes

- Add `paulshaclaw.memory.dream` package: `orchestrator` (atomize → janitor, isolated passes, dream run record), `idle` (testable idle probe), `proposals` (proposal-first framework skeleton + review gate), `cli` (`dream run`/`dream status`).
- Add `paulshaclaw.memory.ledger.dream` (`runtime/ledger/dream.jsonl`) run-record writer + `last_run` + backlog depth.
- Add a systemd user unit/timer template (`OnCalendar` Mon–Fri morning → `dream run --require-idle`) and an idle-check wrapper script; ship templates only (install is an ops step).
- Add `paulshaclaw.memory.replay` package: `selector` (project/tag/entity facets + active-set), `bundle` (assemble slices + ledger events, never raw), `cli` (`bundle`).
- Wire `dream` and `bundle` subcommands into `paulshaclaw/memory/cli.py` (`bundle`, not `replay`, since `replay` is the Topic 8 policy replay).
- Reuse the Topic 3.2 `agent_exec` config so the dream backend is the local model (Copilot CLI for WSL dev, gemma4/GB10 in prod) without code changes.

## Capabilities

### New Capabilities

None. This change extends `stage2-memory-governance` with the dream orchestration service and replay bundle contract.

### Modified Capabilities

- `stage2-memory-governance`: Add dream orchestration service, dream status/backlog, idle-gated scheduling template, proposal-first framework, replay-bundle (distilled+ledger only) contract, and dream determinism/log requirements.

## Impact

- Affected runtime code (new): `paulshaclaw/memory/dream/{orchestrator,idle,proposals,cli}.py`, `paulshaclaw/memory/dream/systemd/paulsha-memory-dream.{service,timer}`, `paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh`, `paulshaclaw/memory/ledger/dream.py`, `paulshaclaw/memory/replay/{selector,bundle,cli}.py`.
- Affected runtime code (modified): `paulshaclaw/memory/cli.py` (add `dream`, `bundle` subcommands).
- Affected layout (new): `runtime/ledger/dream.jsonl`, `runtime/proposals/`, replay bundle output dirs.
- Reuse (read-only or via stable entrypoints): `atomizer.pipeline.run`, `janitor.scanner.run_scan`, `ledger/{lifecycle,processing,relations,retrieval_set}`, Topic 3.2 `agent_exec` config.
- Affected tests: dream orchestrator (fake passes), idle probe, dream ledger, proposals, replay selector, replay bundle (no-raw assertion), E2E dream+bundle, systemd template lint, integration check, regression.
- Non-Goals: cross-session evolution lineage (B, follow-up dream task); global entity graph (C, follow-up dream task); wake-up bundle (Topic 6); free-text retrieval and vector/graph backend (Topic 7); coupling to `obs-auto-moc`; basing on `custom-skills/paulsha-memory` (Topic 9 sync-back scaffold); auto-installing the systemd timer.
