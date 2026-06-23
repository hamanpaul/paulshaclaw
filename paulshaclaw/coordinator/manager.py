from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from ..persona import gate, handoff
from ..memory.dream import idle
from . import autonomy

IN_FLIGHT_STATUSES = frozenset({"dispatched", "running"})
TERMINAL_STATUSES = frozenset({"done", "failed"})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_safe_slice_id(slice_id) -> bool:
    """slice_id 用作單一檔名；拒絕路徑分隔/相對跳脫/絕對路徑（fail-closed 防越界寫）。"""
    return (
        isinstance(slice_id, str)
        and bool(slice_id)
        and slice_id not in (".", "..")
        and re.fullmatch(r"[A-Za-z0-9._-]+", slice_id) is not None
    )


class GateRunner(Protocol):
    def __call__(self, job: dict) -> dict | None: ...


def _default_gate_runner(job: dict) -> dict | None:
    """shadow diff gate（觀測用）。取不到 base/head 或 git 失敗 → None（不阻釋放）。"""
    branch = job.get("branch")
    base = job.get("dispatch_head")
    if not (isinstance(branch, str) and branch and isinstance(base, str) and base):
        return None
    role = job.get("persona") if isinstance(job.get("persona"), str) else "builder"
    # branch 為 ref 名（非 commit sha）是刻意的：git 在 eval 當下把 base...branch
    # 解析成該 branch 的 HEAD。shadow-only，任何失敗皆降級為 None（不阻釋放）。
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
    registry = getattr(dispatcher, "_registry", None)
    if registry is None:
        raise RuntimeError("complete_tick 需 dispatcher._registry（fail-closed）")
    runner = gate_runner if gate_runner is not None else _default_gate_runner
    hdir = Path(handoff_dir)

    polled: list[str] = []
    completed: list[dict] = []
    errors: list[dict] = []

    def _ready_ids() -> set[str]:
        return {m["slice_id"] for m in autonomy.ready_units(metas, _satisfied_pred(handoff_dir))}

    released_ok = metas is not None
    before_ready: set[str] = set()
    if released_ok:
        try:
            before_ready = _ready_ids()
        except ValueError:
            released_ok = False  # metas 有環/重複 → released 觀測停用，不擋完成側

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
            if not _is_safe_slice_id(slice_id):
                errors.append({"job_id": job_id, "error": f"job 缺合法/安全 task/slice_id: {slice_id!r}"})
                continue
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
    if released_ok:
        try:
            summary["released"] = sorted(_ready_ids() - before_ready)
        except ValueError:
            pass
    return summary


def run_tick(
    dispatcher,
    *,
    metas: list[dict],
    launcher=None,
    persona: str = "builder",
    is_satisfied=None,
    gate_runner: GateRunner | None = None,
    handoff_dir: str = autonomy.DEFAULT_HANDOFF_DIR,
    require_idle: bool = False,
    max_load: float = 1.0,
    idle_probe: Callable[[], tuple] = os.getloadavg,
    clock: Callable[[], str] = _utcnow,
) -> dict:
    """跑完整 manager tick：fanout（dispatch_ready）→ complete_tick。

    require_idle 時以 1-min load average gate（reuse memory.dream.idle，可注入 probe）。
    fanout 例外（DispatchReadyError / RequiresLauncher / ValueError 環）收進 errors，
    MUST 仍跑 complete（派工側失敗不阻完成側）。
    """
    if require_idle and not idle.is_idle(max_load=max_load, probe=idle_probe):
        return {"skipped": "not-idle", "dispatched": [], "completed": [], "errors": []}
    satisfied = is_satisfied if is_satisfied is not None else _satisfied_pred(handoff_dir)
    dispatched: list = []
    errors: list = []
    try:
        dispatched = autonomy.dispatch_ready(
            metas, satisfied, dispatcher, persona=persona, launcher=launcher
        )
    except (
        autonomy.DispatchReadyError,
        autonomy.DispatchReadyRequiresLauncherError,
        ValueError,
    ) as exc:
        errors.append({"stage": "fanout", "error": str(exc)})
    complete = complete_tick(
        dispatcher, gate_runner=gate_runner, handoff_dir=handoff_dir, metas=metas, clock=clock
    )
    return {
        "skipped": False,
        "dispatched": dispatched,
        "completed": complete["completed"],
        "errors": errors + complete["errors"],
    }
