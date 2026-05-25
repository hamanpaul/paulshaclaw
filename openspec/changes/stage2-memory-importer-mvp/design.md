## Context

Stage 2 has design artifacts (`openspec/specs/stage2/scope.md`, `paulshaclaw/memory/routing.md`, `paulshaclaw/janitor/service.md`) but no runtime. This change is the first runtime sub-spec under Stage 2 and covers sub-topics #1 (memory substrate) and #2 (importer MVP) of 9 identified subsystems in research doc `docs/research/02.obs-auto-moc-memory-dream-mode-24-7-service-notes-.md`.

The full design rationale lives at `docs/superpowers/specs/2026-05-24-stage2-memory-importer-mvp-design.md`. This document references that spec by section instead of duplicating prose.

## Goals / Non-Goals

**Goals:**

- Establish `~/.agents/memory/` as the canonical, vault-disjoint memory substrate; never mix with `~/notes/`.
- Capture every Claude Code / Codex CLI / GitHub Copilot CLI session ending (or progress snapshot) into `inbox/` with stable frontmatter.
- Make ingestion idempotent: same session ID + same content produces zero or one inbox file regardless of trigger source (hook or watcher) or number of triggers.
- Provide a 24x7 safety net via `obs-auto-moc` file-watcher so a missed hook never produces silent data loss.
- Use existing historical sessions (`~/.claude/projects/`, `~/.codex/sessions/`, `~/.copilot/history-session-state/`) as dev corpus for adapter and classifier development.

**Non-Goals:**

- No secret/PII redaction in this MVP (sub-spec #8).
- No atomization, embedding, or RAG (sub-specs #3, #7).
- No `decayed` / `reactivation` ledger events beyond `written` / `updated` / `stale-skip` / `hash-duplicate` (sub-spec #6).
- No sync-back to Obsidian vault (sub-spec #9).
- No dream service / 24x7 background distillation (sub-spec #5).
- No retrieval API.
- No modification of obs-auto-moc's existing vault behavior; the watcher is purely additive.

## Decisions

### Hook is primary, watcher is safety net

All three CLIs are first-class hook integrations. Hook scripts are intentionally thin (write raw payload to `runtime/queue/`, fire-and-forget importer call). Watcher in obs-auto-moc reuses the same `paulshaclaw.memory.importer.cli ingest` entrypoint via debounced inotify on each CLI's session storage directory; its purpose is to recover from missed hooks and to deliver the highest-completeness snapshot at true session end.

### Content-hash + completeness-tuple idempotency

Skip-if-exists is unsafe because Codex `Stop` is turn-scoped (fires every turn). Instead:

- `idempotency_key = "<source_agent>:<source_session>"`
- `content_hash = sha256(canonical_json(session_id, capture_scope, turn_count, ended_at, sorted(touched_files), len(user_prompts)))` — note `capture_scope` is in the hash so watcher_final never short-circuits to hash-duplicate against an equivalent session_end hook payload.
- `completeness = (scope_rank, turn_count, len(touched_files), len(user_prompts))` with `scope_rank` mapping `{turn:0, subagent:0, session_end:1, watcher_final:2}`.
- Pipeline: same hash → `hash-duplicate` (noop); else if incoming `completeness > recorded` (strict tuple) → `updated`; else → `stale-skip`.

This guarantees Codex's per-turn snapshots progressively update the same inbox file, Claude `SessionEnd` shadows previous turn snapshots, and watcher_final delivers the final authoritative version.

### Venv-pinned Python runtime for hooks

To eliminate PYTHONPATH and `python3` ambiguity, `install.sh` creates `~/.agents/memory/hooks/.venv` and runs `.venv/bin/pip install -e <repo>/paulshaclaw`. All hook config templates invoke `~/.agents/memory/hooks/.venv/bin/python` directly. If venv is missing, hook scripts fall back to "write queue payload only" + WARN log; watcher catches up.

### Longest-prefix project resolution

`projects.yaml` lists projects with `roots` (filesystem paths) and `remotes` (git URLs). Resolver order: cwd longest-prefix → git toplevel longest-prefix → git remote string match → `_unknown`. Multiple alias hits: first definition wins, warning logged.

### Failure routing canonical location

`~/.agents/memory/runtime/queue/_failed/` is the single canonical location for adapter parse failures or importer pipeline exceptions; not `inbox/_failed/`, not `log/`. Items there are retained for human or future dream-service triage.

### Frontmatter contract is read-only from Stage 3 alignment

Frontmatter fields come from `docs/research/02.obs-auto-moc-memory-dream-mode-24-7-service-notes-.md` (lines 220–234) and are aligned with Stage 3's existing definition per the workstream todo. This change does not invent new frontmatter fields.

## Risks / Trade-offs

- **Codex per-turn hook overhead**: Each turn fires importer pipeline. Mitigation: hash short-circuit and atomic file rename keep cost ≤ 100 ms per turn. If proven too slow, future work can route through a long-lived unix socket daemon.
- **Hook script trust friction (Codex)**: Codex requires `/hooks` trust confirmation after every script change. Mitigation: `install.sh` prints clear "go run /hooks now" guidance; documentation lists this as deployment step.
- **Copilot transcript availability**: Copilot's `sessionEnd` payload does not include transcript path. Mitigation: hook reads `~/.copilot/history-session-state/session_<sid>_*.json` directly; adapter best-effort degrades missing fields to empty collections.
- **Monorepo project resolution**: Multiple `roots` may match. Mitigation: longest-prefix wins + first-definition tiebreak + log warning.
- **Watcher latency vs hook**: Watcher debounces 5s; if user starts new session within 5s in same dir, both writes may interleave. Mitigation: flock per idempotency key + per-key serialization ensures only one writer touches any given inbox file at a time.

## Migration Plan

| Step | Action |
|---|---|
| 1 | Land code in `paulshaclaw/memory/`; create empty tree skeleton via `install.sh --tree-only`. |
| 2 | Smoke test hooks one-by-one (A0); each CLI runs a hello-world session and `runtime/queue/<tool>__<sid>.json` appears. |
| 3 | Run importer over historical corpus (≥ 60 sessions across three CLIs) to backfill inbox; lint all frontmatter. |
| 4 | Enable classifier; spot-check 30 random inbox files for bucket correctness ≥ 70%. |
| 5 | Deploy obs-auto-moc watcher via systemd; verify it catches an artificially-missed session. |
| 6 | Live 24h burn-in with hook + watcher both enabled. |

Rollback: remove hook config files (or run `uninstall.sh`), stop watcher systemd unit. Inbox content is preserved; downstream sub-specs can continue from existing data.

## Open Questions

1. Should we expose a `--dry-run` CLI flag on the importer for replaying corpus without writing? (default yes; cheap to add)
2. Should `archive/queue/` retention have an upper bound to avoid disk creep before dream service exists? (defer; track in Stage 2 follow-up issue)
3. Is there value in emitting a Telegram notification on adapter parse failure? (defer to obs/notifications sub-spec)
