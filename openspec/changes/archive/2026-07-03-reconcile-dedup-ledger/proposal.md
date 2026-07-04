## Why

PR #183's 2nd adversarial review (wf_dd36c7b6) found a latent data-loss risk: the MOC naming pass `moc/naming.py::reconcile` — run on every 24x7 dream tick — dedups duplicate `slice_id`s by `older.unlink()` (`naming.py:66-73`), a **silent deletion** that only returns a warning string and writes **no lifecycle ledger event**.

This is inconsistent with the memory system's own governance:
- the **janitor** logs every `decayed`/`superseded` transition to `runtime/ledger/lifecycle.jsonl` (governed decay — "刪必留痕");
- **noise-governance** requires that no deletion be unrecorded (`prune-noise` persists a manifest before any `unlink`, `stage2-noise-governance` spec).

Concretely (the #177/#183 rekey case): `rekey --apply` parks a same-`slice_id` conflict source "for manual resolution," but the next reconcile tick silently `older.unlink()`s that parked (older-mtime) file before a human can act, so the "preserved for manual handling" promise fails in the deployed environment.

**Chosen fix**: bring reconcile's dedup deletions under the same "no unrecorded deletion" governance — emit a lifecycle ledger event on every dedup `unlink` — rather than special-casing rekey (issue options 1/3) or adding an exemption inside the shared reconcile logic (option 2, high moc-regression risk). The deletion *decision* is unchanged (low regression); the deletion becomes traceable/auditable, consistent with janitor decay.

## What Changes

- `moc/naming.py::reconcile`: before each dedup/overwrite `unlink` (`:61`, `:63`, `:71`), append a lifecycle event via `ledger/lifecycle.py::append_event` — `event_type="superseded"`, `record_id=<slice_id>`, `source`/`actor="moc-reconcile"`, `reason` naming the moc dedup, `metadata={deleted_path, kept_path, schema_version}`. `reconcile` already receives `memory_root`, so **no signature change**.
- A lifecycle-ledger write failure MUST NOT abort the moc pass — wrap the append so it degrades to the existing warning path and the pass continues (per-file resilience).
- **The deletion decision (which file survives) is UNCHANGED** — only tracing is added.

## Capabilities

### New Capabilities

None. This change extends the existing `stage2-memory-governance` capability.

### Modified Capabilities

- `stage2-memory-governance`: require MOC reconcile `slice_id` dedup deletions to emit a lifecycle ledger event (no unrecorded deletion), consistent with janitor decay and the noise-governance manifest principle.

## Impact

- **Affected code**: `paulshaclaw/memory/moc/naming.py` (`reconcile`: `append_event` before dedup/overwrite unlink); reuses `paulshaclaw/memory/ledger/lifecycle.py::append_event` (mirrors `janitor/scanner.py::_persist_event`).
- **Affected tests**: `paulshaclaw/memory/tests/test_moc_naming.py` (dedup now emits a lifecycle event; kept file identical to before), plus a test that a ledger-write failure does not abort the pass.
- **Non-goal**: does NOT change WHICH file the dedup deletes (reconcile selection unchanged); does NOT special-case rekey; does NOT modify the janitor.
- **Relates**: #177, PR #183 (2nd adversarial-review finding); consistent with `stage2-noise-governance` "no unrecorded deletion".
