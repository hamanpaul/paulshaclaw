## Why

Stage 2 memory captures but does not read back: all four agents capture into the pipeline, yet the wake-up brief is never injected. The `*_session_start` / `*_precompact` hooks run `sys.path.insert(0, parents[3])`, which — at the deployed (symlinked) location — resolves to `~/notes` and shadows the real `paulshaclaw` package with the memory *data* dir (no `importer`/`wakeup` submodules), so `compute_brief`'s import fails and the brief is empty. Compounding this, 74% of atoms resolve to `_unknown` because project resolution only matches a config, while the operator works across many repos. Net effect: agents feed memory but never get it back.

## What Changes

- Fix the wake-up read-back import shadow: insert the computed repo root onto `sys.path` only when it is a real package root (contains `paulshaclaw/__init__.py`), so the deployed hooks resolve the venv-installed package instead of the data-dir namespace shadow. Factor the bootstrap into one shared helper.
- Hybrid project resolution centralized in `resolve_project` (input: `cwd`; derives git info itself, best-effort): **config canonical → git repo `owner/repo` → working-folder name → multi-repo tree path**. Populate `provenance.repo` from the detected remote. Reduces `_unknown` sharply across all the operator's repos. Existing `_unknown` atoms are fixed-forward (re-resolution is a follow-up).
- Add codex read-back: new `codex_session_start.py` wake-up hook, wired into `~/.codex/hooks.json` `SessionStart`, emitting the same `additionalContext` as claude/copilot.
- Redeploy via `install.sh` (push fixed claude/copilot hooks + new codex hook). Capture write-path behaviour is unchanged. No agent restart required.

## Capabilities

### New Capabilities
- `stage2-memory-readback`: wake-up brief injection (read-back) across claude / copilot / codex, install-independent hook bootstrap, and hybrid project resolution (repo / working-folder / multi-repo tree).

### Modified Capabilities
<!-- None: capture routing (stage2-memory-governance) requirements are unchanged; this adds read-back behaviour. -->

## Impact

- **Code:** `paulshaclaw/memory/hooks/{claude,copilot}_session_start.py`, `{claude,copilot}_precompact.py`, new `codex_session_start.py`, shared bootstrap helper; `paulshaclaw/memory/importer/project_resolver.py` (+ a small bounded `git` helper); `paulshaclaw/memory/hooks/install.sh` / `uninstall.sh`.
- **Config (deploy-time, not repo):** `~/.codex/hooks.json` gains a `paulsha-memory` `SessionStart` entry; `~/.agents/memory/hooks/` re-deployed.
- **Tests:** `paulshaclaw/memory/tests/test_session_start_hooks.py` (shadow regression), `project_resolver` units, codex hook output, git helper.
- **Unchanged:** capture write-path, dream/importer pipeline, `knowledge` layout (slugs become richer but compatible).
