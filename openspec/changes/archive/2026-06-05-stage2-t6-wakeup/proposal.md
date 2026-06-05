## Why

The memory system can capture (T2), atomize (T3), maintain (T4), dream (T5), index (T7), and govern (T8) — but nothing **reads memory back to the agent**. Knowledge accumulates in `~/.agents/memory/knowledge/<project>/` and is never surfaced at the moment it would help: the start of a session. Separately, context compaction summarizes away conversation detail before the importer's session-end hook ever runs, so mid-session detail is silently lost. T6 adds the read/inject side plus a pre-compaction snapshot.

## What Changes

- Add `paulshaclaw/memory/wakeup/` (code module, not a skill): `build_brief(memory_root, project, *, now, k, char_budget)` produces a per-project wake-up brief = MOC primer (T7 `knowledge/<project>-moc.md`) + the most recent K active slices as compact pointers (title + 1-line + Obsidian wikilink), bounded by a char budget. Plus `psc memory wakeup` CLI.
- Add session-start hooks (`claude_session_start.py`, `copilot_session_start.py`) that resolve the project from the hook payload `cwd` via `project_resolver` and emit the brief through each CLI's `additionalContext` channel. Codex shares Claude's SessionStart hook.
- Add PreCompact hooks (`claude_precompact.py`, `copilot_precompact.py`) that snapshot the current session into the existing importer with `capture_scope="pre_compact"` before compaction, so detail is preserved; atomization stays deferred to dream.
- Add `"pre_compact": 0` to `importer/pipeline._SCOPE_RANK` (turn-level; a later `session_end`/`watcher_final` supersedes it via existing idempotency).
- Wire `install.sh`/`uninstall.sh` for Claude `SessionStart`/`PreCompact` and Copilot `sessionStart`/`preCompact`.
- Reuse `project_resolver`, `lifecycle`/`retrieval_set`, T7 MOC output, and the importer with zero duplication. Everything is fail-open and never blocks session start or compaction.
- Defer: query-based mid-session retrieval, retrieval-event logging, immediate post-compact atomization, link-weight/frequency ranking — all Non-Goals.

## Capabilities

### New Capabilities

None. Extends `stage2-memory-governance` with wake-up injection and pre-compaction capture.

### Modified Capabilities

- `stage2-memory-governance`: Add session-start wake-up injection (project-scoped brief = MOC primer + recent-K, budget-bounded, fail-open, read-only, deterministic) and a PreCompact capture trigger reusing the importer (`capture_scope=pre_compact`).

## Impact

- New code: `paulshaclaw/memory/wakeup/{__init__,builder,cli}.py`; hooks `_wakeup_common.py`, `claude_session_start.py`, `copilot_session_start.py`, `claude_precompact.py`, `copilot_precompact.py`.
- Modified: `paulshaclaw/memory/cli.py` (register `wakeup`), `paulshaclaw/memory/importer/pipeline.py` (`_SCOPE_RANK`), `paulshaclaw/memory/hooks/install.sh` + `uninstall.sh`.
- Tests: `test_wakeup_builder.py`, `test_wakeup_cli.py`, `test_session_start_hooks.py`, `test_precompact_hooks.py`, `test_importer_scope_rank.py`.
- Config: Claude `~/.claude/settings.json` (`SessionStart`/`PreCompact`), Copilot `~/.copilot/hooks/paulsha-memory.json` (`sessionStart`/`preCompact`) — managed by `install.sh`.
- Dependencies: none new (stdlib + existing modules). Injection channels verified in the Copilot CLI distribution (`sessionStart` + `additionalContext`, `preCompact`) and Claude Code (`SessionStart`/`PreCompact`).
- Non-Goals: query-based retrieval, retrieval-event logging, immediate post-compact atomization, ranking beyond recency, T9 sync-back.
