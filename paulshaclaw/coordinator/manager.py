from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from ..persona import gate, handoff
from . import autonomy

IN_FLIGHT_STATUSES = frozenset({"dispatched", "running"})
TERMINAL_STATUSES = frozenset({"done", "failed"})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class GateRunner(Protocol):
    def __call__(self, job: dict) -> dict | None: ...


def _default_gate_runner(job: dict) -> dict | None:
    """shadow diff gate（觀測用）。取不到 base/head 或 git 失敗 → None（不阻釋放）。"""
    branch = job.get("branch")
    base = job.get("dispatch_head")
    if not (isinstance(branch, str) and branch and isinstance(base, str) and base):
        return None
    role = job.get("persona") if isinstance(job.get("persona"), str) else "builder"
    try:
        changed = gate.compute_changed_paths(base, branch)
    except Exception:
        return None
    return gate.build_verdict(role=role, changed_paths=changed, manifest_ok=False)


def _satisfied_pred(handoff_dir: str):
    return lambda slice_id: autonomy.default_is_satisfied(slice_id, handoff_dir=handoff_dir)


def complete_tick(
    dispatcher,
    *,
    gate_runner: GateRunner | None = None,
    handoff_dir: str = autonomy.DEFAULT_HANDOFF_DIR,
    metas: list[dict] | None = None,
    clock: Callable[[], str] = _utcnow,
) -> dict:
    registry = dispatcher._registry
    runner = gate_runner if gate_runner is not None else _default_gate_runner
    hdir = Path(handoff_dir)

    polled: list[str] = []
    completed: list[dict] = []
    errors: list[dict] = []

    before_ready: set[str] = set()
    if metas is not None:
        before_ready = {
            m["slice_id"] for m in autonomy.ready_units(metas, _satisfied_pred(handoff_dir))
        }

    for snapshot in registry.list_jobs():
        job_id = snapshot["job_id"]
        try:
            job = snapshot
            status = job.get("status")
            if status in IN_FLIGHT_STATUSES:
                job = dispatcher.poll_headless_done(job_id)
                polled.append(job_id)
                status = job.get("status")

            if status not in TERMINAL_STATUSES:
                continue

            slice_id = job.get("task")
            manifest_path = hdir / f"{slice_id}.json"
            if manifest_path.is_file():
                continue  # 冪等：已寫過

            gate_status = "passed" if status == "done" else "failed"
            try:
                verdict = runner(job)
            except Exception:
                verdict = None

            handoff.write_manifest(
                manifest_path,
                {
                    "slice_id": slice_id,
                    "gate_status": gate_status,
                    "completion": status,
                    "exit_code": job.get("exit_code"),
                    "branch": job.get("branch"),
                    "gate_verdict": verdict,
                    "completed_at": clock(),
                },
            )
            completed.append({"slice_id": slice_id, "gate_status": gate_status})
        except Exception as exc:
            errors.append({"job_id": job_id, "error": str(exc)})

    summary: dict = {"polled": polled, "completed": completed, "errors": errors}
    if metas is not None:
        after_ready = {
            m["slice_id"] for m in autonomy.ready_units(metas, _satisfied_pred(handoff_dir))
        }
        summary["released"] = sorted(after_ready - before_ready)
    return summary
