from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

Executor = Callable[[list[str], int], str]
Clock = Callable[[], datetime]


def default_tmate_executor(argv: list[str], timeout: int) -> str:
    try:
        result = subprocess.run(argv, check=True, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ValueError("tmate not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"tmate command timed out after {timeout}s") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise ValueError(stderr or f"tmate command failed with exit code {exc.returncode}") from exc

    stdout = (result.stdout or "").strip()
    return stdout


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_socket_path() -> Path:
    return Path.home() / ".agents" / "run" / "paulshaclaw-tmate.sock"


def _default_state_path() -> Path:
    return Path.home() / ".agents" / "state" / "tmate.json"


@dataclass
class TmateManager:
    executor: Executor = default_tmate_executor
    now: Clock = _default_now
    socket_path: Path = field(default_factory=_default_socket_path)
    state_path: Path = field(default_factory=_default_state_path)
    session_name: str = "paulshaclaw"
    timeout_seconds: int = 3600
    command_timeout_seconds: int = 10

    def status(self) -> dict[str, object]:
        if not self._has_session():
            self._clear_state()
            return self._public_result({"state": "stopped", "running": False})

        attached_clients = self._attached_clients()
        result = self._link_result(attached_clients)
        result["attached_clients"] = attached_clients
        result["timeout_seconds"] = self.timeout_seconds
        return result

    def start(self) -> dict[str, object]:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

        created = not self._has_session()
        if created:
            self._run("new-session", "-d", "-s", self.session_name)

        state = self._load_state()
        if not state:
            state = {}
        started_at = state.get("started_at")
        if created or not isinstance(started_at, str) or not started_at:
            started_at = self._now_iso()
        state = {
            **state,
            "socket_path": str(self.socket_path),
            "session_name": self.session_name,
            "started_at": started_at,
            "last_no_client_at": state.get("last_no_client_at", None),
            "timeout_seconds": self.timeout_seconds,
        }
        self._write_state(state)

        return self.status()

    def stop(self) -> dict[str, object]:
        if self._has_session():
            self._run("kill-session", "-t", self.session_name)
        self._clear_state()
        return self._public_result({"state": "stopped", "running": False})

    def cleanup_idle(self) -> dict[str, object]:
        if not self._has_session():
            self._clear_state()
            return self._public_result({"state": "stopped", "running": False})

        attached_clients = self._attached_clients()
        state = self._load_state()

        if attached_clients > 0:
            if state.get("last_no_client_at") is not None:
                self._write_state(self._state_with_last_no_client(state, None))
            result = self._link_result(attached_clients)
            result["attached_clients"] = attached_clients
            result["timeout_seconds"] = self.timeout_seconds
            return result

        last_no_client_at = state.get("last_no_client_at")
        if last_no_client_at is None:
            state.update(
                {
                    "socket_path": str(self.socket_path),
                    "session_name": self.session_name,
                    "started_at": state.get("started_at", self._now_iso()),
                    "last_no_client_at": self._now_iso(),
                    "timeout_seconds": self.timeout_seconds,
                }
            )
            self._write_state(state)
            result = self._link_result(attached_clients)
            result["attached_clients"] = attached_clients
            result["timeout_seconds"] = self.timeout_seconds
            return result

        last_no_client = self._parse_datetime(last_no_client_at)
        if self.now() - last_no_client >= timedelta(seconds=self.timeout_seconds):
            return self.stop()

        result = self._link_result(attached_clients)
        result["attached_clients"] = attached_clients
        result["timeout_seconds"] = self.timeout_seconds
        return result

    def _link_result(self, attached_clients: int) -> dict[str, object]:
        try:
            ssh = self._display("#{tmate_ssh}")
            web = self._display("#{tmate_web}")
            ssh_ro = self._display("#{tmate_ssh_ro}")
            web_ro = self._display("#{tmate_web_ro}")
        except ValueError as exc:
            message = str(exc)
            if message in {"tmate not found", "tmate command timed out"}:
                raise
            return self._public_result({"state": "pending", "running": True})

        if not all((ssh, web, ssh_ro, web_ro)):
            return self._public_result({"state": "pending", "running": True})

        return self._public_result({
            "state": "running",
            "running": True,
            "ssh": ssh,
            "web": web,
            "ssh_ro": ssh_ro,
            "web_ro": web_ro,
        })

    def _has_session(self) -> bool:
        try:
            self._run("has-session", "-t", self.session_name)
        except ValueError as exc:
            message = str(exc)
            if message in {"tmate not found", "tmate command timed out"}:
                raise
            return False
        return True

    def _attached_clients(self) -> int:
        value = self._display("#{session_attached}")
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"invalid session_attached value: {value}") from exc

    def _display(self, template: str) -> str:
        return self._run("display-message", "-p", template)

    def _run(self, *args: str) -> str:
        argv = ["tmate", "-S", str(self.socket_path), *args]
        return self.executor(argv, self.command_timeout_seconds)

    def _load_state(self) -> dict[str, object]:
        try:
            payload = json.loads(self.state_path.read_text())
        except FileNotFoundError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    def _write_state(self, state: dict[str, object]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))

    def _clear_state(self) -> None:
        try:
            self.state_path.unlink()
        except FileNotFoundError:
            pass

    def _state_with_last_no_client(self, state: dict[str, object], last_no_client_at: str | None) -> dict[str, object]:
        updated = dict(state)
        updated["last_no_client_at"] = last_no_client_at
        return updated

    def _now_iso(self) -> str:
        return self.now().isoformat()

    def _public_result(self, payload: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "kind": "tmate", **payload}

    def _parse_datetime(self, value: object) -> datetime:
        if not isinstance(value, str) or not value:
            return self.now()
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
