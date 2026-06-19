# 2026-04-26-stage9-project-monitor

Repurpose the previously cancelled Stage 9 slot as the **Project Monitor** service. Stage 9 becomes the canonical task source consumed by Stage 1 (daemon dispatch) and Stage 3 (lifecycle), so that running projects do not need to maintain duplicated state.

Artifacts:

- `proposal.md` — why and what
- `design.md` — service shape, config, discovery, sync model
- `tasks.md` — implementation checklist
- `specs/stage9-project-monitor/spec.md` — canonical capability declaration
