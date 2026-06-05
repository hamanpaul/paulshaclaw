## 1. pre_compact scope rank

- [ ] 1.1 Add failing `test_importer_scope_rank.py`: `_SCOPE_RANK["pre_compact"] == 0` and is below `session_end`/`watcher_final`.
- [ ] 1.2 Add `"pre_compact": 0` to `importer/pipeline._SCOPE_RANK`.

## 2. Wake-up brief builder

- [ ] 2.1 Add failing `test_wakeup_builder.py`: Map+Recent present, recent newest-first, active-only (decayed excluded), unknown/empty project → empty, char-budget truncates Map tail keeping Recent, deterministic.
- [ ] 2.2 Implement `wakeup/builder.py::build_brief(memory_root, project, *, now, k=8, char_budget=8000)` reusing `lifecycle`/`retrieval_set`/`moc.frontmatter_io` and the T7 MOC file; `wakeup/__init__.py` exports it.

## 3. Wake-up CLI + subcommand

- [ ] 3.1 Add failing `test_wakeup_cli.py`: `--project` prints brief; `--cwd` via resolver; unknown project → empty, rc 0.
- [ ] 3.2 Implement `wakeup/cli.py` (`run`/`main`, `--project|--cwd|--memory-root|--k|--char-budget|--now`).
- [ ] 3.3 Register `wakeup` subcommand + `_wakeup` handler in `memory/cli.py`.

## 4. Session-start hooks

- [ ] 4.1 Add failing `test_session_start_hooks.py`: claude/copilot emit `additionalContext` with the brief; unresolved project quiet; malformed stdin fails open (rc 0).
- [ ] 4.2 Implement `hooks/_wakeup_common.py` (`memory_root`, `read_payload`, `log_warn`, `compute_brief`) + `claude_session_start.py` (`hookSpecificOutput.additionalContext`) + `copilot_session_start.py` (`{additionalContext}`).

## 5. PreCompact hooks

- [ ] 5.1 Add failing `test_precompact_hooks.py`: claude/copilot write a `capture_scope=pre_compact` queue payload; malformed stdin fails open with no queue file.
- [ ] 5.2 Extend `_wakeup_common.py` (`sanitize_id`, `write_queue_payload`, `fire_importer`) + implement `claude_precompact.py` / `copilot_precompact.py` mirroring the session-end capture flow.

## 6. Install wiring

- [ ] 6.1 Copy the 5 new hook scripts in `install.sh`'s hook-copy loop.
- [ ] 6.2 Register Claude `SessionStart` + `PreCompact` (mirror the managed `SessionEnd` block; idempotent).
- [ ] 6.3 Extend Copilot `paulsha-memory.json` with `sessionStart` + `preCompact` arrays.
- [ ] 6.4 Mirror removals in `uninstall.sh`.
- [ ] 6.5 Verify idempotent install on a throwaway config root.

## 7. Docs, suite, gate, archive

- [ ] 7.1 Write `wakeup/README.md` (inject, precompact, fail-open, read-only, deterministic, reuse).
- [ ] 7.2 Full suite `python3 -m unittest discover -s paulshaclaw/memory/tests` green.
- [ ] 7.3 Repo policy / lint gate green.
- [ ] 7.4 openspec-archive after merge + sync spec delta into `openspec/specs/stage2-memory-governance/spec.md`.
