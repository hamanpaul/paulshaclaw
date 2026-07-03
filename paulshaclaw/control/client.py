from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from . import constants, contract


def submit_request(req_type: str, args: dict[str, Any], requested_by: str) -> str:
    request = contract.build_request(req_type=req_type, args=args, requested_by=requested_by)
    contract.atomic_write_json(constants.requests_dir() / f"{request['req_id']}.json", request)
    return request["req_id"]


def read_status() -> dict[str, Any]:
    payload = contract.read_json(constants.status_path())
    if not isinstance(payload, dict):
        return _degraded_status("missing")
    updated_at = payload.get("updated_at")
    if _is_stale(updated_at):
        return _degraded_status("stale")
    return {
        "schema_version": payload.get("schema_version", constants.SCHEMA_VERSION),
        "updated_at": updated_at,
        "daemon": payload.get("daemon"),
        "ready": list(payload.get("ready", [])),
        "in_flight": list(payload.get("in_flight", [])),
        "recent_done": list(payload.get("recent_done", [])),
        "degraded": False,
        "degraded_reason": None,
    }


def poll_done(req_id: str, timeout: float, poll_interval: float = 0.5) -> dict[str, Any] | None:
    deadline = time.monotonic() + max(timeout, 0.0)
    done_path = constants.done_dir() / f"{req_id}.json"
    while True:
        payload = contract.read_json(done_path)
        if payload is not None:
            return payload
        if time.monotonic() >= deadline:
            return None
        if poll_interval > 0:
            time.sleep(poll_interval)


def _degraded_status(reason: str) -> dict[str, Any]:
    return {
        "schema_version": constants.SCHEMA_VERSION,
        "updated_at": None,
        "daemon": None,
        "ready": [],
        "in_flight": [],
        "recent_done": [],
        "degraded": True,
        "degraded_reason": reason,
    }


def _is_stale(updated_at: object) -> bool:
    if not isinstance(updated_at, str):
        return True
    try:
        parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return age.total_seconds() > constants.STATUS_STALE_AFTER_SECONDS
