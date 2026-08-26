## Why

Stage 2 (`paulsha-memory`) has scope, routing, janitor specs and a sync-back gate scaffold but **zero runtime code**: `~/.agents/memory/` does not exist and nothing ingests CLI sessions today. Three CLIs (Claude Code, Codex CLI, GitHub Copilot CLI) now all expose native session-end hooks, and `obs-auto-moc` already has a `import-session-insights` pipeline that can be extended into a 24x7 file-watcher safety net. This change lands the substrate + Importer MVP so subsequent sub-specs (atomizer, ledger semantics, dream mode, retrieval, sync-back) have a real backing store to write into.

## What Changes

- Create canonical memory tree at `~/.agents/memory/{inbox,work-centric,knowledge,runtime,log,hooks,archive}` (work-centric / knowledge / indexes only built as empty placeholders).
- Add `paulshaclaw.memory.importer` package: hook scripts + adapters (claude / codex / copilot) + classifier + frontmatter writer + idempotency ledger.
- Define hook configuration for all three CLIs, with venv-pinned Python runtime to remove PYTHONPATH coupling.
- Add `obs_auto_moc.watchers.agents_inbox_watcher` (lives in the obs-auto-moc repo) as safety-net file watcher reusing the same importer entry.
- Define content-hash + completeness-tuple idempotency: incremental hook snapshots progressively upgrade the same inbox file; watcher's `watcher_final` capture scope always wins.
- Configure `~/.agents/config/projects.yaml` with longest-prefix monorepo project resolution.
- Defer secret redaction, atomizer, ledger semantics (decayed/reactivation), retrieval, sync-back — all listed as Non-Goals.

## Capabilities

### New Capabilities

None. This change extends the existing `stage2-memory-governance` capability with concrete importer / hook / watcher requirements.

### Modified Capabilities

- `stage2-memory-governance`: Add canonical memory tree layout, hook-based session ingestion, watcher safety net, content-hash + completeness idempotency, and project identity resolution requirements.

## Impact

- Affected runtime code (new): `paulshaclaw/memory/importer/` (cli.py, pipeline.py, classifier.py, adapters/{base,claude,codex,copilot}.py, frontmatter.py, project_resolver.py, config.py); `paulshaclaw/memory/hooks/{claude,codex,copilot}_session_end.py`, `install.sh`, `uninstall.sh`; `paulshaclaw/memory/lint/frontmatter_lint.py`.
- Affected runtime code (external repo): `obs-auto-moc` gains `obs_auto_moc/watchers/agents_inbox_watcher.py` + systemd unit, wired to `import-session-insights` for current vault path.
- Affected config: new `~/.agents/config/memory.yaml`, new `~/.agents/config/projects.yaml`; user-level `~/.claude/settings.json`, `~/.codex/hooks.json`, `~/.copilot/hooks/paulsha-memory.json` (managed by `install.sh`).
- Affected tests: new `paulshaclaw/memory/tests/test_adapters.py`, `test_classifier.py`, `test_idempotency.py`, `test_e2e.py`; extend `stage2_integration_check.sh`.
- Dependencies: `inotify_simple` (for watcher, optional); `PyYAML` (already in tree).
- External system: none new. Reuses CLI-native hook ABIs (Claude `SessionEnd`, Codex `Stop`/`SubagentStop`, Copilot `sessionEnd`).
- Non-Goals: secret redaction, retrieval / RAG, atomizer, decayed/reactivation ledger events, sync-back to Obsidian, dream service. These belong to subsequent sub-specs.
