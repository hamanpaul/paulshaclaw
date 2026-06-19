## Context

Full design: `docs/superpowers/specs/2026-06-10-stage2-memory-readback-design.md`. Stage 2 capture works for all four agents, but read-back (wake-up brief injection) is broken by a `sys.path` namespace-package shadow, and 74% of atoms resolve to `_unknown`. Constraint: hooks must never break an agent session; capture write-path must stay unchanged.

## Goals / Non-Goals

**Goals:**
- Wake-up brief is injected and non-empty for claude / copilot / codex sessions in a known project.
- Atoms resolve to a real project (repo / working-folder / multi-repo tree); `_unknown` drops sharply.
- Hooks remain crash-safe (catch-all → log → empty context → exit 0).

**Non-Goals:**
- Deepening atom *content* (still `touched-files`-grade).
- Re-resolving the 161 existing `_unknown` atoms.
- Tree-aware briefs that fold a parent node's context into a child's brief.
- Any change to the capture write-path.

## Decisions

- **D1 — Guard the sys.path bootstrap (not remove / not PYTHONPATH / not vendor).** Insert the computed repo root only when `<root>/paulshaclaw/__init__.py` exists. Deployed → `~/notes/paulshaclaw/__init__.py` is absent → no insert → venv-installed package resolves; repo-dev → real package present → insert. Alternatives: removing the insert breaks straight-from-repo runs; pinning `PYTHONPATH=<repo>` in each hook command hard-codes paths and breaks on move; vendoring modules into the data dir duplicates code. The guard is minimal and correct in both contexts.
- **D2 — Resolution derives git info itself from `cwd`.** `resolve_project(cwd)` runs bounded `git -C cwd` for toplevel/remote rather than requiring the capture hook to record them. Keeps the capture write-path untouched; centralizes all resolution logic in one place.
- **D3 — Tree = path-style slug.** The project slug doubles as the knowledge-layer path, so multi-repo workspaces nest naturally (`knowledge/work_prj/repo-a/`). Alternative (separate "group" metadata) adds a parallel structure for no near-term gain.
- **D4 — Precedence: config canonical → git `owner/repo` → working-folder → multi-repo tree.** A repo with a remote keeps its canonical `owner/repo` identity (remote wins over tree); the tree prefix applies to repos without a remote and to parent-level sessions. This matches "主要 repo 為 project".
- **D5 — codex read-back via a new `SessionStart` hook.** codex uses the Claude Code hook protocol (events `SessionStart`/`SessionEnd`/`Stop`; superpowers injects via codex `SessionStart`), so a `codex_session_start.py` emitting `additionalContext` works. Exact output field is confirmed during implementation.
- **D6 — Fix-forward for existing `_unknown`.** New captures resolve correctly; re-resolving old atoms is a separate, optional follow-up (feasible only if old atoms recorded `cwd`).

## Risks / Trade-offs

- codex `SessionStart` `additionalContext` contract differs subtly → verify against the codex hook protocol / superpowers example; the empty-context fallback is always safe.
- `git -C cwd` at import time may see a moved/changed cwd → best-effort; degrade to working-folder name; never throws.
- Multi-repo sibling scan adds a little I/O → single directory level, bounded, best-effort.
- Re-running `install.sh` overwrites the deployed hooks → install is idempotent and uses `managedBy: paulsha-memory` markers, so it only touches managed entries.

## Migration Plan

Re-run `paulshaclaw/memory/hooks/install.sh` to deploy the fixed claude/copilot hooks and the new codex hook (and wire `~/.codex/hooks.json`). Hooks fire per-event, so no agent restart is needed; the next new session verifies. Rollback: `uninstall.sh` (or re-deploy the previous hook revision).

## Open Questions

- Exact codex `SessionStart` injection field (`additionalContext` vs alternative) — resolve during implementation against the live codex hook protocol.
- Whether to schedule the `_unknown` re-resolution follow-up now or later.
