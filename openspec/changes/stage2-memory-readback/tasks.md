## 1. Hook bootstrap + import fix (Component A)

- [ ] 1.1 Add a shared bootstrap helper (in `_wakeup_common` or a new `_bootstrap`) that adds the computed repo root to `sys.path` only when `<root>/paulshaclaw/__init__.py` exists
- [ ] 1.2 Replace the `sys.path.insert(0, parents[3])` block in `claude_session_start.py`, `copilot_session_start.py`, `claude_precompact.py`, `copilot_precompact.py` to call the shared helper
- [ ] 1.3 Add a regression test in `test_session_start_hooks.py`: with a namespace `paulshaclaw` dir at the `parents[3]` position, assert the helper does not insert it, imports resolve to the real package, and the brief is non-empty

## 2. Hybrid project resolution (Component B)

- [ ] 2.1 Add a bounded best-effort git helper (`git -C cwd` toplevel + `origin` remote) that degrades (never raises) on failure
- [ ] 2.2 Extend `resolve_project` with the precedence chain: config canonical → git `owner/repo` → repo dir name → working-folder name
- [ ] 2.3 Add multi-repo tree detection (single-level sibling scan; ≥2 repos ⇒ prefix the parent-workspace name) producing a path-style slug
- [ ] 2.4 Populate `provenance.repo` from the detected remote
- [ ] 2.5 Unit tests for `resolve_project`: config match; in-repo+remote → `owner/repo`; in-repo no remote → repo name; not-in-repo → folder; multi-repo parent → tree slug; git-unavailable → folder (no raise); truly unresolvable → `_unknown`

## 3. codex wake-up hook (Component C)

- [ ] 3.1 Confirm the codex `SessionStart` injection contract (`additionalContext`) against the live codex hook protocol
- [ ] 3.2 Add `codex_session_start.py` mirroring claude/copilot (shared bootstrap + `compute_brief`), emitting the confirmed injected-context JSON; fail-safe (log + empty + exit 0)
- [ ] 3.3 Test: `codex_session_start` emits valid injected context from `compute_brief`; on failure emits empty + exit 0

## 4. Deploy wiring

- [ ] 4.1 Update `install.sh` to deploy `codex_session_start.py` and wire `~/.codex/hooks.json` `SessionStart` (`managedBy: paulsha-memory`, matcher `startup|clear|compact`) alongside existing `Stop`/`SubagentStop`
- [ ] 4.2 Update `uninstall.sh` to remove the codex `SessionStart` entry and script
- [ ] 4.3 Confirm `install.sh` is idempotent and only touches `paulsha-memory`-managed entries

## 5. Deploy + verify (acceptance)

- [ ] 5.1 Re-run `install.sh`; confirm fixed hooks + codex hook are deployed to `~/.agents/memory/hooks/` and configs
- [ ] 5.2 Start fresh claude / copilot / codex sessions in a known repo; confirm a non-empty, correct-project brief is injected and `hooks.log` shows no wake-up import WARN
- [ ] 5.3 Confirm new captures across multiple repos resolve to real projects (repo / folder / tree) and `_unknown` rate drops
- [ ] 5.4 Run the full memory test suite; confirm green
