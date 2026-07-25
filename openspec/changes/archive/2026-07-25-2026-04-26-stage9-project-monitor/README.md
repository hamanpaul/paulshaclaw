# 2026-04-26-stage9-project-monitor

> Archived 2026-07-25 as historical evidence. The monitor was implemented in this repo, then its runtime, config, tests, and capability ownership moved to `paulsha-cortex` in the 2026-07-08 Cortex extraction (`53088ad`). This archive intentionally skipped spec application so the removed capability is not reintroduced into paulshaclaw's canonical specs.

Repurpose the previously cancelled Stage 9 slot as the **Project Monitor** service. Stage 9 becomes the canonical task source consumed by Stage 1 (daemon dispatch) and Stage 3 (lifecycle), so that running projects do not need to maintain duplicated state.

Artifacts:

- `proposal.md` — why and what
- `design.md` — service shape, config, discovery, sync model
- `tasks.md` — implementation checklist
- `specs/stage9-project-monitor/spec.md` — canonical capability declaration
