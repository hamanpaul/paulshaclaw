## Context

Stage 8 is the postponed cost-governance stage. The immediate need is not enforcement; it is operator visibility during active tmux work. Existing local assets already include Stage 9 monitor startup and Stage 11 cockpit, so Stage 8 should fit into the same local workflow without adding a service.

External references such as `agent-status-tmux`, `tmux-ccusage`, and the `claude-usage` gist all use a short tmux status output backed by cached provider data. Stage 8 follows that pattern but keeps the data contract explicit through a JSON snapshot CLI, avoids global `.tmux.conf` edits, and treats provider credentials as sensitive inputs that must never appear in output or process arguments.

Copilot is the hardest source. Account usage can happen outside this machine, so local Copilot session logs are only a fallback signal. The preferred sources are GitHub billing premium request usage reports or configured org/enterprise reports depending on whether the configured account is personal or company-managed.

## Goals / Non-Goals

**Goals:**

- Produce a provider-neutral Stage 8 cost snapshot via `python -m paulshaclaw.cost --once`.
- Render a tmux-safe one-line footer via `python -m paulshaclaw.cost.status`.
- Support `cdx`, `cc`, and `cpt` provider abbreviations.
- Render `cdx` and `cc` 5h/weekly usage with reset displays, including exact local-time display for 5h reset.
- Render `cpt` configured account labels and used request counts only.
- Use 120-second snapshot cache TTL and 30-second tmux refresh interval by default.
- Apply the footer through session-local tmux options in `scripts/start.sh`.

**Non-Goals:**

- No background daemon, socket server, budget enforcement, blocking, or prediction.
- No global `~/.tmux.conf` modification.
- No hardcoded Copilot account IDs in runtime behavior.
- No Copilot reset display in v1.

## Decisions

### Decision 1: Snapshot CLI plus thin footer formatter

Stage 8 uses a JSON snapshot CLI as the stable data boundary and a thin status command for tmux. A direct tmux script would be quicker, but it would couple provider fetches, cache behavior, and rendering in one place. A service would be more powerful, but Stage 8 v1 does not need lifecycle management or a socket.

### Decision 2: Config-driven Copilot accounts

Copilot account definitions live in config and may contain zero, one, or many accounts. Each account defines `id`, `label`, `kind`, and optional billing scope such as `org` or enterprise identifiers. This keeps the sample `haman` and `arc` labels out of runtime logic and supports future account changes without code edits.

### Decision 3: Online-first Copilot usage with local fallback

Copilot adapter priority is billing/report source first, local observed logs last. For personal accounts, the user billing premium request report is the preferred source. For company-managed accounts, org or enterprise billing/report sources are preferred. If local logs are used, the snapshot marks `source=local_observed` so consumers know the number is partial.

### Decision 4: Safe degraded rendering

Provider failures degrade only that provider. Missing credentials, malformed provider responses, network timeout, or cache lock contention must still let the footer command exit 0 with stale or unknown output. This keeps tmux responsive even when a provider source is unavailable.

### Decision 5: Session-local tmux integration

`scripts/start.sh` applies `status-interval 30` and appends the Stage 8 command to the current session's `status-right`. It must preserve any existing `status-right` value and must not use global `-g`, because Stage 8 is part of the paulshaclaw session rather than a machine-wide tmux plugin.

## Risks / Trade-offs

- **[Copilot billing APIs differ by account ownership]** -> Config includes account kind and billing scope; provider source is recorded per account.
- **[GitHub billing shifts from request-based to usage-based after 2026-06-01]** -> Snapshot keeps source/metric separate from footer rendering so a future adapter can change metric source without changing tmux format.
- **[Claude usage source may be unofficial or unavailable]** -> Adapter is best-effort and must render `cc 5h:-- wk:--` when no trusted source exists.
- **[Codex quota source may not expose 5h/weekly reset]** -> Adapter must not estimate quota windows; it renders unknown until a reliable source exists.
- **[tmux footer can block if provider refresh is slow]** -> Status command reads cache first, uses bounded refresh, and falls back to stale cache on lock contention or timeout.

## Migration Plan

1. Add Stage 8 package and tests without changing startup behavior.
2. Add CLI commands and verify they degrade safely without provider credentials.
3. Add session-local tmux integration to `scripts/start.sh`.
4. Run unit, cache, CLI, and start-script tests.
5. Manually smoke inside tmux and confirm Stage 11 still launches.

Rollback is limited to removing the Stage 8 `scripts/start.sh` footer setup. The snapshot package can remain installed because it is passive and does not start a service.

## Open Questions

- Which concrete GitHub token source should the implementation use first for user/org/enterprise billing reports?
- Which reliable Codex quota source, if any, exposes 5h and weekly reset windows?
