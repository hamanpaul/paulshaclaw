## 1. Memory Tree & Config Scaffold (A1)

- [ ] 1.1 Add failing tests for tree creation (`test_tree_skeleton.py`): assert all 7 top-level dirs + 4 inbox buckets + `runtime/{queue,queue/_failed,locks,ledger}` + `log/` + `archive/queue/` exist with mode 0700 after install.
- [ ] 1.2 Implement `paulshaclaw/memory/hooks/install.sh --tree-only` to create the canonical tree and `.gitkeep` files at `~/.agents/memory/`.
- [ ] 1.3 Add `paulshaclaw/memory/lint/frontmatter_lint.py` with failing tests against a hand-written fixture; ensure required-fields list aligns with research doc 02 lines 220–234.

## 2. Importer Skeleton & Adapters (A2)

- [ ] 2.1 Collect ≥ 3 sanitized fixtures per CLI under `paulshaclaw/memory/tests/fixtures/<tool>/<sid>/payload.json` (Claude SessionEnd stdin shape, Codex Stop/SubagentStop, Copilot sessionEnd camelCase shape).
- [ ] 2.2 Add failing tests `test_adapters.py` for adapter `extract()` against fixtures, verifying field rename (Copilot camelCase → snake_case), missing-field tolerance, and `NormalizedSession` shape.
- [ ] 2.3 Implement `paulshaclaw/memory/importer/adapters/{base,claude,codex,copilot}.py` and the `NormalizedSession` TypedDict.
- [ ] 2.4 Implement `paulshaclaw/memory/importer/frontmatter.py` with deterministic YAML serialization and stable key order.
- [ ] 2.5 Implement `paulshaclaw/memory/importer/cli.py` with `ingest --queue-item <path>` subcommand and `--dry-run` flag.
- [ ] 2.6 Implement `paulshaclaw/memory/importer/pipeline.py`: read queue → adapter dispatch → frontmatter render → flock + idempotency decision → write inbox / archive queue payload.

## 3. Idempotency Engine (A2 continued)

- [ ] 3.1 Add failing `test_idempotency.py` covering: first write → `written`; identical hash retry → `hash-duplicate`; higher completeness → `updated`; lower completeness → `stale-skip`; watcher_final after session_end → `updated` (because capture_scope differs in hash and scope_rank=2 > 1).
- [ ] 3.2 Implement content-hash computation in adapter base: `sha256(canonical_json((session_id, capture_scope, turn_count, ended_at, sorted(touched_files), len(user_prompts))))`.
- [ ] 3.3 Implement completeness tuple builder `(scope_rank, turn_count, len(touched_files), len(user_prompts))` with `scope_rank = {turn:0, subagent:0, session_end:1, watcher_final:2}`.
- [ ] 3.4 Implement ledger append (`runtime/ledger/import.jsonl`) and `flock` over `runtime/locks/<key>.lock`.
- [ ] 3.5 Implement archive move: on `written` / `updated`, move queue payload to `archive/queue/<YYYY-MM>/<key>.json`.

## 4. Project Resolver (A4 prerequisite)

- [ ] 4.1 Add failing `test_project_resolver.py` covering: cwd longest-prefix, nested monorepo (child wins over parent), git toplevel fallback, remote-URL match, `_unknown` fallback, alias collision logging.
- [ ] 4.2 Implement `paulshaclaw/memory/importer/project_resolver.py` and `config.py::resolve_project`.
- [ ] 4.3 Ship `~/.agents/config/projects.yaml` initial template with `paulshaclaw` and `obs-auto-moc` entries; include alias examples.

## 5. Classifier (A3)

- [ ] 5.1 Add failing `test_classifier.py` with 12 hand-labeled fixtures (3 per bucket: sessions / plans / research / reports).
- [ ] 5.2 Implement `paulshaclaw/memory/importer/classifier.py` with rule-based dispatch (filename / touched-artifacts / keyword heuristics).
- [ ] 5.3 Wire classifier into `pipeline.py` so inbox path = `inbox/<bucket>/<tool>/<YYYY-MM-DD>/<sid>.md`.

## 6. Hook Integration (A0 + A5)

- [ ] 6.1 Implement `paulshaclaw/memory/hooks/install.sh` full version: create venv, `pip install -e <repo>/paulshaclaw`, deploy hook scripts, write user-level config files (Claude `settings.json` merge, Codex `hooks.json` write, Copilot `hooks/paulsha-memory.json` write), print Codex `/hooks` trust reminder.
- [ ] 6.2 Implement `paulshaclaw/memory/hooks/uninstall.sh`.
- [ ] 6.3 Implement `claude_session_end.py`: read stdin JSON, set `capture_scope="session_end"`, compute hash, write atomic queue payload, fire-and-forget importer call.
- [ ] 6.4 Implement `codex_session_end.py`: support `--subagent` flag; set `capture_scope` accordingly; set `ended_at=None`; same queue write.
- [ ] 6.5 Implement `copilot_session_end.py`: read stdin (camelCase), rename `sessionId`→`session_id`, supplement from `~/.copilot/history-session-state/session_<sid>_*.json`, write queue.
- [ ] 6.6 A0 smoke test: each CLI hello-world session produces a non-empty `runtime/queue/<tool>__<sid>.json` and `hooks.log` is ERROR-free.

## 7. Watcher Safety Net (A4)

- [ ] 7.1 (In obs-auto-moc repo) Add failing tests for `agents_inbox_watcher.py`: debounce timing, queue payload format, capture_scope = `watcher_final`.
- [ ] 7.2 (In obs-auto-moc repo) Implement `obs_auto_moc/watchers/agents_inbox_watcher.py` using `inotify_simple`, watching `~/.claude/projects/`, `~/.codex/sessions/`, `~/.copilot/history-session-state/`.
- [ ] 7.3 (In obs-auto-moc repo) Add systemd unit template `obs-auto-moc-agents-watcher.service` (user unit).
- [ ] 7.4 Wire watcher to import via the same `paulshaclaw.memory.importer.cli ingest --watcher --path <p>` entry.

## 8. Corpus Backfill & E2E (A5)

- [ ] 8.1 Run importer over historical corpus: ≥ 20 Claude, ≥ 20 Codex, ≥ 20 Copilot sessions from local history; assert inbox count == unique session count.
- [ ] 8.2 Spot-check 30 random inbox files for classifier accuracy ≥ 70%.
- [ ] 8.3 Run hook + watcher in parallel for one live session per CLI; assert ledger contains both events and final inbox reflects `watcher_final` state.
- [ ] 8.4 24h burn-in: leave watcher enabled, no crashes, no leaked queue files.

## 9. Verification & Documentation

- [ ] 9.1 Update `paulshaclaw/memory/tests/stage2_integration_check.sh` with importer dry-run on fixtures.
- [ ] 9.2 Run full `python3 -m unittest discover -s tests -v` (existing suite still green).
- [ ] 9.3 Update `paulshaclaw/memory/routing.md` cross-reference to point at this MVP.
- [ ] 9.4 Mark OpenSpec tasks complete and record verification summary at bottom of this file.

## Verification Summary

(To be filled at end of implementation: focused test invocation, full suite result, manual hook smoke test command, watcher systemd status.)
