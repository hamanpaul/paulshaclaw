## 1. Memory Tree & Config Scaffold (A1)

- [x] 1.1 Add failing tests for tree creation (`test_tree_skeleton.py`): assert all 7 top-level dirs + 4 inbox buckets + `runtime/{queue,queue/_failed,locks,ledger}` + `log/` + `archive/queue/` exist with mode 0700 after install.
- [x] 1.2 Implement `paulshaclaw/memory/hooks/install.sh --tree-only` to create the canonical tree and `.gitkeep` files at `~/.agents/memory/`.
- [x] 1.3 Add `paulshaclaw/memory/lint/frontmatter_lint.py` with failing tests against a hand-written fixture; ensure required-fields list aligns with research doc 02 lines 220–234.

## 2. Importer Skeleton & Adapters (A2)

- [x] 2.1 Collect sanitized fixtures under `paulshaclaw/memory/tests/fixtures/<tool>/.../payload.json` for Claude SessionEnd, Codex Stop/SubagentStop, and Copilot sessionEnd/history-state shapes.
- [x] 2.2 Add failing tests `test_adapters.py` for adapter `extract()` against fixtures, verifying field rename (Copilot camelCase → snake_case), missing-field tolerance, and `NormalizedSession` shape.
- [x] 2.3 Implement `paulshaclaw/memory/importer/adapters/{base,claude,codex,copilot}.py` and the `NormalizedSession` TypedDict.
- [x] 2.4 Implement `paulshaclaw/memory/importer/frontmatter.py` with deterministic YAML serialization and stable key order.
- [x] 2.5 Implement `paulshaclaw/memory/importer/cli.py` with `ingest --queue-item <path>` subcommand and `--dry-run` flag.
- [x] 2.6 Implement `paulshaclaw/memory/importer/pipeline.py`: read queue → adapter dispatch → frontmatter render → flock + idempotency decision → write inbox / archive queue payload.

## 3. Idempotency Engine (A2 continued)

- [x] 3.1 Add failing `test_idempotency.py` covering first write / hash duplicate / update / stale skip / watcher-vs-session completeness ordering.
- [x] 3.2 Implement content-hash computation in adapter base: `sha256(canonical_json((session_id, capture_scope, turn_count, ended_at, sorted(touched_files), len(user_prompts))))`.
- [x] 3.3 Implement completeness tuple builder `(scope_rank, turn_count, len(touched_files), len(user_prompts))` with `scope_rank = {turn:0, subagent:0, session_end:1, watcher_final:2}`.
- [x] 3.4 Implement ledger append (`runtime/ledger/import.jsonl`) and `flock` over `runtime/locks/<key>.lock`.
- [x] 3.5 Implement archive move: on `written` / `updated`, move queue payload to `archive/queue/<YYYY-MM>/<key>.json`.

## 4. Project Resolver

- [x] 4.1 Add failing `test_project_resolver.py` covering cwd longest-prefix, nested monorepo (child wins over parent), git toplevel fallback, remote-URL match, `_unknown` fallback, alias collision logging, and remote normalization edge cases.
- [x] 4.2 Implement `paulshaclaw/memory/importer/project_resolver.py` and `config.py::resolve_project`.
- [x] 4.3 Ship `~/.agents/config/projects.yaml` template with `paulshaclaw` and `obs-auto-moc` entries; include alias examples.

## 5. Classifier

- [x] 5.1 Add failing `test_classifier.py` with hand-labeled fixtures across sessions / plans / research / reports.
- [x] 5.2 Implement `paulshaclaw/memory/importer/classifier.py` with rule-based dispatch (filename / touched-artifacts / keyword heuristics).
- [x] 5.3 Wire classifier into `pipeline.py` so inbox path = `inbox/<bucket>/<tool>/<YYYY-MM-DD>/<sid>.md`.

## 6. Hook Integration

- [x] 6.1 Implement `paulshaclaw/memory/hooks/install.sh` full version: create tree + venv, `pip install -e <repo>`, deploy hook scripts, write user-level config files, remember repo root, support `--upgrade`, and print Codex `/hooks` trust reminder.
- [x] 6.2 Implement `paulshaclaw/memory/hooks/uninstall.sh`.
- [x] 6.3 Implement `claude_session_end.py`: read stdin JSON, set `capture_scope="session_end"`, write atomic queue payload, fire-and-forget importer call.
- [x] 6.4 Implement `codex_session_end.py`: support `--subagent` flag; set `capture_scope` accordingly; keep `ended_at=None`; same queue write.
- [x] 6.5 Implement `copilot_session_end.py`: read stdin (camelCase), rename `sessionId`→`session_id`, supplement from `~/.copilot/history-session-state/session_<sid>_*.json`, write queue.
- [x] 6.6 Add fixture-backed hook/install/uninstall verification and record that live CLI hello-world smoke remains a manual post-archive step.

## 7. Deferred External Follow-up (obs-auto-moc repo, not archive-blocking)

- Move watcher implementation, tests, and user-level systemd unit into `obs-auto-moc`.
- Reuse the same importer contract and `watcher_final` completeness semantics from this change.
- Validate missed-hook recovery in the external watcher PR instead of this repo-local archive.

## 8. Deferred Operational Follow-up (manual/local-history validation, not archive-blocking)

- Replay larger historical corpora (≥ 20 sessions per CLI) on the local machine that owns those histories.
- Spot-check classifier accuracy across 30 random imported artifacts.
- Run live hello-world sessions for Claude / Codex / Copilot and 24h watcher burn-in once the external watcher lands.

## 9. Verification & Documentation

- [x] 9.1 Update `paulshaclaw/memory/tests/stage2_integration_check.sh` with importer dry-run on fixtures.
- [x] 9.2 Run repo-local verification and record the existing unrelated full-suite blocker instead of claiming a clean global suite.
- [x] 9.3 Update `paulshaclaw/memory/routing.md` cross-reference to point at this MVP and its boundary.
- [x] 9.4 Mark OpenSpec tasks complete and record verification summary at bottom of this file.

## Verification Summary

- `python3 -m unittest paulshaclaw.memory.tests.test_hooks -v` → 41 tests passed
- `python3 -m unittest discover -s paulshaclaw/memory/tests -v` → 95 tests passed
- `bash paulshaclaw/memory/tests/stage2_integration_check.sh` → passed
- `python3 -m unittest discover -s tests -v` → one pre-existing unrelated failure in `tests/test_stage9_project_monitor.py` because that suite assumes a specific `.worktrees/paulshaclaw` layout
- Fixture-backed hook smoke is covered by `test_hooks.py`; live CLI hello-world smoke remains deferred until post-archive manual validation on a machine with the real hook hosts enabled
