from __future__ import annotations

import json
import argparse
import os
import signal
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..control import constants, contract
from . import autonomy, broker_reaper, manager
from .cli import _refuse_unsafe_fanout, _resolve_launcher
from .dispatcher import Dispatcher
from .registry import JobRegistry
from .seams import ScriptWorktreeCreator, TmuxPaneSender

DEFAULT_TICK_INTERVAL = 300.0
DEFAULT_POLL_INTERVAL = 3.0
DEFAULT_PERSONA = "builder"
DEFAULT_EXECUTOR = "copilot"
DEFAULT_MAX_LOAD = 1.0
RECENT_DONE_LIMIT = 10
MANAGER_CMD_MARKER = "paulshaclaw.coordinator.manager_daemon"
USE_DEFAULT_REAPER = object()


@dataclass
class HeldLock:
    path: Path

    def release(self) -> None:
        self.path.unlink(missing_ok=True)


def acquire_lock(
    *,
    path: Path | None = None,
    pid: int | None = None,
    pid_alive: Callable[[int], bool] | None = None,
    now_fn: Callable[[], str] = contract.utcnow,
) -> HeldLock | None:
    lock_path = path or constants.lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner_pid = os.getpid() if pid is None else pid
    alive = pid_alive or _pid_alive
    payload = {
        "schema_version": constants.SCHEMA_VERSION,
        "pid": owner_pid,
        "acquired_at": now_fn(),
    }

    for _ in range(2):
        fd, temp_name = tempfile.mkstemp(
            dir=lock_path.parent,
            prefix=f".{lock_path.name}.",
            suffix=".tmp",
            text=True,
        )
        temp_path = Path(temp_name)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        try:
            os.link(temp_path, lock_path)
        except FileExistsError:
            temp_path.unlink(missing_ok=True)
            if _lock_is_live(lock_path, alive):
                return None
            lock_path.unlink(missing_ok=True)
            continue
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        temp_path.unlink(missing_ok=True)
        return HeldLock(lock_path)
    return None


def default_specs_dir() -> str:
    override = os.environ.get("PSC_MANAGER_SPECS_DIR")
    if override:
        return override
    return str(Path.home() / ".agents" / "specs")


def default_executor() -> str:
    override = os.environ.get("PSC_MANAGER_EXECUTOR")
    if override:
        return override
    return DEFAULT_EXECUTOR


def default_tick_interval() -> float:
    override = os.environ.get("PSC_MANAGER_INTERVAL_SECONDS")
    if not override:
        return DEFAULT_TICK_INTERVAL
    try:
        return float(override)
    except ValueError:
        return DEFAULT_TICK_INTERVAL


def default_reaper() -> Callable[[], dict[str, Any]]:
    return lambda: broker_reaper.reap_orphan_brokers(apply=True)


def build_status_provider(
    *,
    registry,
    ready_provider: Callable[[], list[str]],
    recent_done_provider: Callable[[], list[dict[str, Any]]],
) -> Callable[[], dict[str, Any]]:
    def provider() -> dict[str, Any]:
        in_flight = []
        for job in registry.list_jobs():
            status = job.get("status")
            if status not in manager.IN_FLIGHT_STATUSES:
                continue
            in_flight.append(
                {
                    "job_id": job.get("job_id"),
                    "slice_id": job.get("task"),
                    "state": status,
                }
            )
        return {
            "ready": list(ready_provider()),
            "in_flight": in_flight,
            "recent_done": list(recent_done_provider()),
        }

    return provider


def build_runtime_status_provider(
    *,
    registry,
    specs_dir: str,
    handoff_dir: str,
    scan_specs_fn: Callable[[str], list[dict[str, Any]]] = autonomy.scan_specs,
    ready_units_fn: Callable[[list[dict[str, Any]], Callable[[str], bool]], list[dict[str, Any]]] = autonomy.ready_units,
    recent_done_limit: int = RECENT_DONE_LIMIT,
) -> Callable[[], dict[str, Any]]:
    def ready_provider() -> list[str]:
        metas = scan_specs_fn(specs_dir)
        predicate = lambda slice_id: autonomy.default_is_satisfied(slice_id, handoff_dir=handoff_dir)
        return [meta["slice_id"] for meta in ready_units_fn(metas, predicate)]

    def recent_done_provider() -> list[dict[str, Any]]:
        manifests: list[tuple[str, dict[str, Any]]] = []
        handoff_path = Path(handoff_dir)
        if not handoff_path.is_dir():
            return []
        for path in handoff_path.glob("*.json"):
            payload = contract.read_json(path)
            if not isinstance(payload, dict):
                continue
            manifests.append(
                (
                    str(payload.get("completed_at") or ""),
                    {
                        "slice_id": payload.get("slice_id"),
                        "gate_status": payload.get("gate_status"),
                        "at": payload.get("completed_at"),
                    },
                )
            )
        manifests.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in manifests[:recent_done_limit]]

    return build_status_provider(
        registry=registry,
        ready_provider=ready_provider,
        recent_done_provider=recent_done_provider,
    )


def build_request_executor(
    *,
    dispatcher,
    specs_dir: str,
    handoff_dir: str,
    launcher=None,
    default_persona: str = DEFAULT_PERSONA,
    default_executor: str = DEFAULT_EXECUTOR,
    default_max_load: float = DEFAULT_MAX_LOAD,
    reaper=None,
    scan_specs_fn: Callable[[str], list[dict[str, Any]]] = autonomy.scan_specs,
    run_tick_fn: Callable[..., dict[str, Any]] = manager.run_tick,
    dispatch_ready_fn: Callable[..., list[dict[str, Any]]] = autonomy.dispatch_ready,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    predicate = lambda slice_id: autonomy.default_is_satisfied(slice_id, handoff_dir=handoff_dir)

    def execute(request: dict[str, Any]) -> dict[str, Any]:
        args = request.get("args", {})
        request_specs_dir = args.get("specs_dir") or specs_dir
        metas = scan_specs_fn(request_specs_dir)
        allow_unsafe = bool(args.get("allow_unsafe", False))
        _refuse_unsafe_fanout(metas, predicate, allow_unsafe=allow_unsafe)
        active_launcher = _resolve_launcher(
            args.get("executor", default_executor),
            launcher,
            allow_unsafe=allow_unsafe,
            model=args.get("model"),
        )
        persona = args.get("persona", default_persona)
        if request["type"] == "fanout":
            jobs = dispatch_ready_fn(
                metas,
                predicate,
                dispatcher,
                persona=persona,
                launcher=active_launcher,
            )
            return {
                "dispatch_skipped": False,
                "dispatched": jobs,
                "completed": [],
                "errors": [],
                "reaped": None,
            }
        return run_tick_fn(
            dispatcher,
            metas=metas,
            launcher=active_launcher,
            persona=persona,
            is_satisfied=predicate,
            handoff_dir=handoff_dir,
            require_idle=bool(args.get("require_idle", False)),
            max_load=float(args.get("max_load", default_max_load)),
            reaper=reaper,
        )

    return execute


def build_periodic_tick_runner(
    *,
    dispatcher,
    specs_dir: str,
    handoff_dir: str,
    launcher=None,
    default_persona: str = DEFAULT_PERSONA,
    default_executor: str = DEFAULT_EXECUTOR,
    default_allow_unsafe: bool = False,
    default_max_load: float = DEFAULT_MAX_LOAD,
    require_idle: bool = True,
    reaper=None,
    scan_specs_fn: Callable[[str], list[dict[str, Any]]] = autonomy.scan_specs,
    run_tick_fn: Callable[..., dict[str, Any]] = manager.run_tick,
) -> Callable[[], dict[str, Any]]:
    predicate = lambda slice_id: autonomy.default_is_satisfied(slice_id, handoff_dir=handoff_dir)

    def execute() -> dict[str, Any]:
        metas = scan_specs_fn(specs_dir)
        _refuse_unsafe_fanout(metas, predicate, allow_unsafe=default_allow_unsafe)
        active_launcher = _resolve_launcher(
            default_executor,
            launcher,
            allow_unsafe=default_allow_unsafe,
            model=None,
        )
        return run_tick_fn(
            dispatcher,
            metas=metas,
            launcher=active_launcher,
            persona=default_persona,
            is_satisfied=predicate,
            handoff_dir=handoff_dir,
            require_idle=require_idle,
            max_load=default_max_load,
            reaper=reaper,
        )

    return execute


def run_loop(
    *,
    request_executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    status_provider: Callable[[], dict[str, Any]] | None = None,
    periodic_tick_runner: Callable[[], dict[str, Any]] | None = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    tick_interval: float = DEFAULT_TICK_INTERVAL,
    now_fn: Callable[[], str] = contract.utcnow,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
    pid: int | None = None,
    pid_alive: Callable[[int], bool] | None = None,
    max_rounds: int | None = None,
    specs_dir: str | None = None,
    handoff_dir: str = autonomy.DEFAULT_HANDOFF_DIR,
    registry: JobRegistry | None = None,
    dispatcher: Dispatcher | None = None,
    launcher=None,
    require_idle: bool = True,
    default_executor: str | None = None,
    reaper: Callable[[], dict[str, Any]] | None | object = USE_DEFAULT_REAPER,
) -> bool:
    runtime_pid = os.getpid() if pid is None else pid
    held_lock = acquire_lock(pid=runtime_pid, pid_alive=pid_alive, now_fn=now_fn)
    if held_lock is None:
        return False

    reg = registry if registry is not None else JobRegistry()
    disp = dispatcher
    if disp is None:
        disp = Dispatcher(reg, TmuxPaneSender(), ScriptWorktreeCreator())
    resolved_specs_dir = specs_dir or default_specs_dir()
    resolved_default_executor = default_executor or DEFAULT_EXECUTOR
    resolved_reaper = default_reaper() if reaper is USE_DEFAULT_REAPER else reaper

    executor = request_executor or build_request_executor(
        dispatcher=disp,
        specs_dir=resolved_specs_dir,
        handoff_dir=handoff_dir,
        launcher=launcher,
        default_executor=resolved_default_executor,
        reaper=resolved_reaper,
    )
    provider = status_provider or build_runtime_status_provider(
        registry=reg,
        specs_dir=resolved_specs_dir,
        handoff_dir=handoff_dir,
    )
    periodic_runner = periodic_tick_runner or build_periodic_tick_runner(
        dispatcher=disp,
        specs_dir=resolved_specs_dir,
        handoff_dir=handoff_dir,
        launcher=launcher,
        require_idle=require_idle,
        default_executor=resolved_default_executor,
        reaper=resolved_reaper,
    )

    constants.requests_dir().mkdir(parents=True, exist_ok=True)
    constants.done_dir().mkdir(parents=True, exist_ok=True)

    last_tick_at: str | None = None
    daemon_idle = True
    last_tick_monotonic = monotonic_fn()
    rounds = 0

    try:
        while max_rounds is None or rounds < max_rounds:
            tick_ran_this_round = False
            request_drain_interrupted = False
            request_paths = sorted(constants.requests_dir().glob("*.json"), key=_request_sort_key)
            for request_path in request_paths:
                if not request_path.exists():
                    continue
                request_id = request_path.stem
                done_path = constants.done_dir() / f"{request_id}.json"
                if done_path.exists():
                    try:
                        request_path.unlink(missing_ok=True)
                    except Exception as exc:  # noqa: BLE001
                        _log_error(exc)
                        request_drain_interrupted = True
                        break
                    continue

                started_at = now_fn()
                try:
                    try:
                        request = _load_request(request_path)
                    except FileNotFoundError:
                        continue
                    summary = executor(request)
                    done_payload = contract.build_done(
                        req_id=request["req_id"],
                        status="ok",
                        result=summary,
                        started_at=started_at,
                    )
                    skipped = isinstance(summary, dict) and summary.get("dispatch_skipped") == "not-idle"
                    daemon_idle = not skipped
                    if request["type"] == "tick" and not skipped:
                        last_tick_at = now_fn()
                        last_tick_monotonic = monotonic_fn()
                        tick_ran_this_round = True
                except Exception as exc:  # noqa: BLE001
                    done_payload = contract.build_done(
                        req_id=request_id,
                        status="error",
                        error=f"{type(exc).__name__}: {exc}",
                        started_at=started_at,
                    )
                    _log_error(exc)
                try:
                    _persist_done(done_payload)
                    request_path.unlink(missing_ok=True)
                except Exception as exc:  # noqa: BLE001
                    _log_error(exc)
                    request_drain_interrupted = True
                    break

            if (
                not request_drain_interrupted
                and not tick_ran_this_round
                and monotonic_fn() - last_tick_monotonic >= tick_interval
            ):
                try:
                    summary = periodic_runner()
                    skipped = isinstance(summary, dict) and summary.get("dispatch_skipped") == "not-idle"
                    daemon_idle = not skipped
                    if not skipped:
                        last_tick_at = now_fn()
                        last_tick_monotonic = monotonic_fn()
                except Exception as exc:  # noqa: BLE001
                    _log_error(exc)

            try:
                snapshot = provider()
                status_payload = contract.build_status(
                    ready=list(snapshot.get("ready", [])),
                    in_flight=list(snapshot.get("in_flight", [])),
                    recent_done=list(snapshot.get("recent_done", [])),
                    daemon={
                        "pid": runtime_pid,
                        "last_tick_at": last_tick_at,
                        "idle": daemon_idle,
                    },
                    updated_at=now_fn(),
                )
                contract.atomic_write_json(constants.status_path(), status_payload)
            except Exception as exc:  # noqa: BLE001
                _log_error(exc)

            rounds += 1
            if max_rounds is not None and rounds >= max_rounds:
                break
            if poll_interval > 0:
                sleep_fn(poll_interval)
    finally:
        held_lock.release()

    return True


def _load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("request payload must be an object")
    return contract.validate_request(payload)


def _persist_done(payload: dict[str, Any]) -> dict[str, Any]:
    done_path = constants.done_dir() / f"{payload['req_id']}.json"
    existing = contract.read_json(done_path)
    if existing is not None:
        return existing
    contract.atomic_write_json(done_path, payload)
    return payload


def _request_sort_key(path: Path) -> tuple[int, str]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return (sys.maxsize, path.name)
    return (stat.st_mtime_ns, path.name)


def _lock_is_live(path: Path, pid_alive: Callable[[int], bool]) -> bool:
    payload = contract.read_json(path)
    if not isinstance(payload, dict):
        return False
    owner_pid = payload.get("pid")
    if not isinstance(owner_pid, int):
        return False
    return pid_alive(owner_pid)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    try:
        raw_cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    argv = [part.decode("utf-8", errors="ignore") for part in raw_cmdline if part]
    return any(
        argv[index] == "-m" and argv[index + 1] == MANAGER_CMD_MARKER
        for index in range(len(argv) - 1)
    )


def _handle_termination(_signum: int, _frame: object) -> None:
    raise SystemExit(0)


def _install_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, _handle_termination)
    signal.signal(signal.SIGINT, _handle_termination)


def _log_error(exc: Exception) -> None:
    print(f"manager_daemon error: {type(exc).__name__}: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PaulShiaBro manager daemon")
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL)
    parser.add_argument("--tick-interval", type=float, default=default_tick_interval())
    parser.add_argument("--executor", default=default_executor())
    parser.add_argument("--specs-dir")
    parser.add_argument("--handoff-dir", default=autonomy.DEFAULT_HANDOFF_DIR)
    parser.add_argument("--max-rounds", type=int)
    parser.add_argument("--no-require-idle", action="store_true")
    parser.add_argument(
        "--no-reap",
        dest="reap",
        action="store_false",
        default=True,
        help="關閉收尾孤兒 codex broker 回收（預設開；issue #161）",
    )
    args = parser.parse_args(argv)
    _install_signal_handlers()
    active_reaper = default_reaper() if args.reap else None

    started = run_loop(
        poll_interval=args.poll_interval,
        tick_interval=args.tick_interval,
        specs_dir=args.specs_dir,
        handoff_dir=args.handoff_dir,
        max_rounds=args.max_rounds,
        require_idle=not args.no_require_idle,
        default_executor=args.executor,
        reaper=active_reaper,
    )
    return 0 if started else 1


if __name__ == "__main__":
    raise SystemExit(main())
