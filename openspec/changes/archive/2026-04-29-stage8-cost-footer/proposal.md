## Why

Stage 8 is currently postponed even though daily work already depends on understanding Codex, Claude Code, and GitHub Copilot usage before limits become disruptive. The first useful increment is visibility: a compact tmux footer plus a reusable JSON snapshot lets the operator see cost/quota pressure without introducing enforcement or a new daemon.

## What Changes

- Add a Stage 8 cost snapshot CLI that emits provider-neutral JSON for Codex (`cdx`), Claude Code (`cc`), and GitHub Copilot (`cpt`).
- Add a tmux footer formatter that renders the snapshot as a single status line with stale/unknown fallback and color thresholds.
- Add config-driven Copilot account support so runtime accounts are not hardcoded; sample accounts can map `hamanpaul -> haman` and `paulc-arc -> arc`, but production config may define zero, one, or many accounts.
- Add hybrid provider sourcing: online billing/report sources first where available, with local logs/cache only as fallback.
- Update local startup so `scripts/start.sh` applies the Stage 8 footer to the current tmux session without modifying global `~/.tmux.conf`.
- Keep Stage 8 v1 observational only: no budget enforcement, no blocking, no background service.

## Capabilities

### New Capabilities

- `stage8-cost-footer`: Defines Stage 8 usage snapshot, provider adapters, cache behavior, tmux footer format, Copilot account configuration, and startup integration.

### Modified Capabilities

- `stage7`: Local startup and deployment visibility must include the Stage 8 footer assets and session-local tmux integration without changing global tmux config.

## Impact

- New package area under `paulshaclaw/cost/` for models, config loading, provider adapters, cache, formatting, and CLI entry points.
- New tests for Stage 8 snapshot schema, Copilot account config parsing, formatter output, cache behavior, CLI contracts, and `scripts/start.sh` tmux integration.
- `scripts/start.sh` will add Stage 8 setup before Stage 11 cockpit startup while preserving existing Stage 9 and Stage 11 behavior.
- No new runtime service or socket is introduced.
- Network/API usage is bounded and cached; provider credentials must never be printed, stored in snapshots, or passed as command-line arguments.
