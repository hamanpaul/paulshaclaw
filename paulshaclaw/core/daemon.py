from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from paulshaclaw.control import client as control_client
from paulshaclaw.core.config import AppConfig, load_config
from paulshaclaw.core.command_dispatcher import CommandDispatcher
from paulshaclaw.core.command_registry import CommandRegistry, CommandSpec, load_default_command_registry
from paulshaclaw.memory.atomizer import config as atomizer_config
from paulshaclaw.core.tmate import TmateManager


# Foreground commands that mark a tmux pane as an idle shell `/agent start` may
# reuse. Anything else (claude, minicom, vim, …) means the pane is occupied.
_IDLE_SHELL_COMMANDS = frozenset(
    {"bash", "sh", "zsh", "fish", "dash", "ash", "ksh", "tcsh", "csh", "login"}
)


class CoordinatorClient(Protocol):
    def create_job(self, *, phase: str, scope: str, payload: dict[str, object]) -> dict[str, object]:
        """Create a minimal coordinator job."""


class ManagerClient(Protocol):
    def read_status(self) -> dict[str, object]:
        """Read the current manager status snapshot."""

    def submit_request(self, req_type: str, args: dict[str, object], requested_by: str) -> str:
        """Submit a manager request and return its request id."""

    def poll_done(self, req_id: str, timeout: float, poll_interval: float = 0.5) -> dict[str, object] | None:
        """Wait briefly for a done record and return it when present."""


@dataclass
class LocalCoordinator:
    """Test-only fallback coordinator for direct daemon and unit-test wiring."""

    counter: int = 0

    def create_job(self, *, phase: str, scope: str, payload: dict[str, object]) -> dict[str, object]:
        self.counter += 1
        return {
            "job_id": f"local-{self.counter}",
            "phase": phase,
            "scope": scope,
            "payload": payload,
        }


class PaulShiaBroDaemon:
    MANAGER_TICK_TIMEOUT_SECONDS = 15.0
    MANAGER_TICK_POLL_INTERVAL_SECONDS = 0.5

    def __init__(
        self,
        config: AppConfig,
        coordinator: CoordinatorClient | None = None,
        command_registry: CommandRegistry | None = None,
        tmate_manager: TmateManager | None = None,
        manager_client: ManagerClient | None = None,
    ) -> None:
        self.config = config
        self.coordinator = coordinator or LocalCoordinator()
        self.command_registry = command_registry or load_default_command_registry()
        tmate_timeout = self.command_registry.get("/tmate").func_call.timeout_seconds or 3600
        self.tmate_manager = tmate_manager or TmateManager(timeout_seconds=tmate_timeout)
        self.manager_client = manager_client or control_client
        self._cockpit_pane_id = next((pane.pane_id for pane in self.config.pane_assignments if pane.title == "cockpit"), None)
        self._agent_pane_id: str | None = None
        self.command_dispatcher = CommandDispatcher(
            registry=self.command_registry,
            python_handlers={
                "help": self._handle_help_command,
                "status": self._handle_status_command,
                "dispatch": self._handle_dispatch_command,
                "tmate": self._handle_tmate_command,
                "manager": self._handle_manager_command,
                "agent": self._handle_agent_command,
            },
        )

    def _list_panes_text(self) -> str:
        try:
            result = subprocess.run(
                ["tmux", "list-panes", "-a", "-F",
                 "#{session_name}:#{window_index} #{pane_id} #{pane_title}"],
                check=True, capture_output=True, text=True,
            )
            return result.stdout.strip() or "(no panes)"
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "(tmux unavailable)"

    def _send_to_pane(self, pane_id: str, message: str) -> dict[str, object]:
        try:
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, "-l", message],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, "Enter"],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"tmux send-keys failed: {exc.stderr.decode().strip()}") from exc
        except FileNotFoundError as exc:
            raise ValueError("tmux not found") from exc
        return {"ok": True, "pane_id": pane_id, "sent": message}

    def _pane_current_command(self, pane_id: str) -> str | None:
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "-t", pane_id, "#{pane_current_command}"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        return result.stdout.strip() or None

    def _assert_pane_is_idle_shell(self, pane_id: str) -> None:
        """Reject a target pane that is missing or busy with a non-shell program.

        Guards `/agent start` so it never types the launch command into a pane
        already running claude, minicom, an editor, …—where it would either be
        swallowed or clobber the running program.
        """
        command = self._pane_current_command(pane_id)
        if command is None:
            raise ValueError(f"pane {pane_id} 不存在或無法存取，請確認 agent_pane_id")
        if command.lstrip("-").lower() not in _IDLE_SHELL_COMMANDS:
            raise ValueError(
                f"pane {pane_id} 正在執行 {command}（非 idle shell），請先釋放或改用其他 pane"
            )

    def _is_agent_command(self, command: str) -> bool:
        if not command:
            return False
        try:
            argv = shlex.split(command)
        except ValueError:
            argv = command.split()

        basenames = [Path(token).name for token in argv]
        if "claude-gemma4-proxy" in basenames:
            return False

        use_legacy_wrapper_detection = True
        try:
            configured_launch = self._agent_launch_argv()
        except ValueError:
            configured_launch = []
        else:
            use_legacy_wrapper_detection = (
                bool(configured_launch)
                and Path(configured_launch[0]).name == "claude-gemma4"
            )
        if configured_launch:
            if argv[: len(configured_launch)] == configured_launch:
                return True
            if argv[: len(configured_launch) + 1] == [*configured_launch, "-f"]:
                return True
        if use_legacy_wrapper_detection and "claude-gemma4" in basenames:
            return True
        return (
            use_legacy_wrapper_detection
            and basenames[:1] in (["claude"], ["claude.exe"])
            and ".claude-gemma4/settings.json" in command
        )

    def _command_for_pid(self, pid: int) -> str | None:
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "args="],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        return result.stdout.strip() or None

    def _find_process_in_tree(self, root_pid: int) -> int | None:
        pending = [root_pid]
        visited: set[int] = set()

        while pending:
            parent_pid = pending.pop()
            if parent_pid in visited:
                continue
            visited.add(parent_pid)

            if self._is_agent_command(self._command_for_pid(parent_pid) or ""):
                return parent_pid

            try:
                result = subprocess.run(
                    ["pgrep", "-P", str(parent_pid), "-a"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError:
                return None
            except subprocess.CalledProcessError as exc:
                if exc.returncode == 1:
                    continue
                return None

            for line in result.stdout.splitlines():
                parts = line.strip().split(maxsplit=1)
                if not parts:
                    continue
                try:
                    child_pid = int(parts[0])
                except ValueError:
                    continue
                command = parts[1] if len(parts) > 1 else ""
                if self._is_agent_command(command):
                    return child_pid
                pending.append(child_pid)

        return None

    def _detect_agent_process(self) -> tuple[str, int] | None:
        try:
            result = subprocess.run(
                ["tmux", "list-panes", "-a", "-F", "#{pane_id} #{pane_pid}"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

        for line in result.stdout.splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) != 2:
                continue
            pane_id, pane_pid_text = parts
            try:
                pane_pid = int(pane_pid_text)
            except ValueError:
                continue

            agent_pid = self._find_process_in_tree(pane_pid)
            if agent_pid is not None:
                return pane_id, agent_pid

        return None

    def _agent_launch_argv(self) -> list[str]:
        try:
            config, _config_hash = atomizer_config.load_config()
        except atomizer_config.AtomizerConfigError as exc:
            raise ValueError(f"agent command unavailable: {exc}") from exc
        return list(atomizer_config.resolve_command_argv(config.agent_exec_command))

    def _agent_status_payload(self, *, pane_id: str | None = None, pid: int | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": True,
            "kind": "agent",
            "state": "running" if pane_id is not None else "stopped",
            "running": pane_id is not None,
        }
        if pane_id is not None:
            payload["pane_id"] = pane_id
        if pid is not None:
            payload["pid"] = pid
        return payload

    def route_to_agent(self, *, user_id: int, text: str) -> str:
        detected = self._detect_agent_process()
        if detected is None:
            self._agent_pane_id = None
            return "agent 未啟用，請使用 /agent start"

        pane_id, _pid = detected
        self._agent_pane_id = pane_id
        # Lean tag only; the gemma4 bro hooks (UserPromptSubmit/Stop) handle the
        # Telegram reply deterministically, so no in-prompt directive is needed.
        self._send_to_pane(pane_id, f"[bro:{user_id}] {text}")
        return "…"
    def status_snapshot(self) -> dict[str, object]:
        return {
            "ok": True,
            "daemon": self.config.daemon_name,
            "project": self.config.default_project,
            "pane_count": len(self.config.pane_assignments),
            "allowed_user_count": len(self.config.allowed_user_ids),
            "panes": self._list_panes_text(),
        }

    def dispatch(self, task_id: str) -> dict[str, object]:
        payload = dict(self.config.coordinator.default_payload)
        payload["task_id"] = task_id
        job = self.coordinator.create_job(
            phase=self.config.coordinator.phase,
            scope=task_id,
            payload=payload,
        )
        return {
            "ok": True,
            "job_id": job["job_id"],
            "phase": job["phase"],
            "scope": job["scope"],
        }

    def _handle_help_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        if len(args) > 1:
            raise ValueError("/help 最多接受一個 command")
        text = self.command_registry.render_help(args[0] if args else None)
        return {"ok": True, "kind": "help", "text": text}

    def _handle_status_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        if args:
            raise ValueError("/status 不接受參數")
        return self.status_snapshot()

    def _handle_dispatch_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        if not args:
            raise ValueError("/dispatch 需要 task_id")
        pane_idx = next((i for i, token in enumerate(args) if token.startswith("%")), None)
        if pane_idx is not None:
            pane_id = args[pane_idx]
            message = " ".join(args[pane_idx + 1:]).strip()
            if not message:
                raise ValueError(f"/dispatch {pane_id} 需要訊息內容")
            return self._send_to_pane(pane_id, message)
        return self.dispatch(" ".join(args))

    def _handle_tmate_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        if len(args) > 1:
            raise ValueError("/tmate 只接受 status/start/stop")

        action = args[0] if args else "status"
        if action == "status":
            return self.tmate_manager.status()
        if action == "start":
            return self.tmate_manager.start()
        if action == "stop":
            return self.tmate_manager.stop()
        raise ValueError("/tmate 只接受 status/start/stop")

    def _handle_manager_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        if len(args) > 1:
            raise ValueError("/manager 只接受 status/tick")

        action = args[0] if args else "status"
        if action == "status":
            return {
                "ok": True,
                "kind": "manager",
                "action": "status",
                "text": self._format_manager_status(self.manager_client.read_status()),
            }
        if action == "tick":
            req_id = self.manager_client.submit_request("tick", {}, "telegram")
            done = self.manager_client.poll_done(
                req_id,
                timeout=self.MANAGER_TICK_TIMEOUT_SECONDS,
                poll_interval=self.MANAGER_TICK_POLL_INTERVAL_SECONDS,
            )
            return {
                "ok": True,
                "kind": "manager",
                "action": "tick",
                "req_id": req_id,
                "text": self._format_manager_tick_result(req_id, done),
            }
        raise ValueError("/manager 只接受 status/tick")

    def _handle_agent_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        action = args[0] if args else "status"
        extra = args[1:]
        if action in {"status", "stop"} and extra:
            raise ValueError(f"/agent {action} 不接受參數")
        if action in {"start", "startf"} and len(extra) > 1:
            raise ValueError("/agent start 只接受一個 pane id（例如 /agent start %7）")
        if action == "status":
            detected = self._detect_agent_process()
            if detected is None:
                self._agent_pane_id = None
                return self._agent_status_payload()
            pane_id, pid = detected
            self._agent_pane_id = pane_id
            return self._agent_status_payload(pane_id=pane_id, pid=pid)

        if action in {"start", "startf"}:
            detected = self._detect_agent_process()
            if detected is not None:
                pane_id, pid = detected
                self._agent_pane_id = pane_id
                payload = self._agent_status_payload(pane_id=pane_id, pid=pid)
                payload["already_running"] = True
                return payload

            target_pane_id = extra[0] if extra else None
            if not target_pane_id:
                raise ValueError("請指定要啟動 agent 的 pane id，例如 /agent start %7")
            if not target_pane_id.startswith("%"):
                raise ValueError(f"pane id 需以 % 開頭（例如 %7），收到：{target_pane_id}")

            # Run the agent in the caller-specified, already-existing pane instead
            # of splitting a fresh one. Verify it is an idle shell first so we
            # never clobber a running program (claude/minicom/…).
            self._assert_pane_is_idle_shell(target_pane_id)

            launch_argv = self._agent_launch_argv()
            if action == "startf":
                launch_argv.append("-f")

            self._send_to_pane(target_pane_id, shlex.join(launch_argv))
            self._agent_pane_id = target_pane_id
            payload = self._agent_status_payload(pane_id=target_pane_id)
            payload["started"] = True
            return payload

        if action == "stop":
            detected = self._detect_agent_process()
            if detected is None:
                self._agent_pane_id = None
                payload = self._agent_status_payload()
                payload["already_stopped"] = True
                return payload

            pane_id, pid = detected
            self._send_to_pane(pane_id, "exit")
            recheck_attempts = 2
            for attempt in range(recheck_attempts):
                if attempt:
                    time.sleep(0.1)
                rechecked = self._detect_agent_process()
                if rechecked is None:
                    self._agent_pane_id = None
                    payload = self._agent_status_payload()
                    payload.update({"stopped": True, "pane_id": pane_id, "pid": pid})
                    return payload

            rechecked_pane_id, rechecked_pid = rechecked
            self._agent_pane_id = rechecked_pane_id
            return self._agent_status_payload(pane_id=rechecked_pane_id, pid=rechecked_pid)

        raise ValueError("/agent 只接受 start/startf/stop/status")

    def _format_manager_status(self, status: dict[str, object]) -> str:
        daemon = status.get("daemon")
        daemon = daemon if isinstance(daemon, dict) else {}
        ready = list(status.get("ready", []))
        held = list(status.get("held", []))
        in_flight = list(status.get("in_flight", []))
        recent_done = list(status.get("recent_done", []))
        lines = [
            "manager status",
            f"updated_at: {status.get('updated_at') or '--'}",
            f"daemon: pid={daemon.get('pid', '--')} idle={daemon.get('idle', '--')} last_tick_at={daemon.get('last_tick_at', '--')}",
            f"ready({len(ready)}): {', '.join(str(item) for item in ready) if ready else '--'}",
            f"held({len(held)}): {self._format_manager_held_items(held)}",
            f"in_flight({len(in_flight)}): {self._format_manager_items(in_flight, state_key='state')}",
            f"recent_done({len(recent_done)}): {self._format_manager_items(recent_done, state_key='gate_status')}",
        ]
        if status.get("degraded"):
            lines.insert(1, f"degraded: {status.get('degraded_reason') or '--'}")
        return "\n".join(lines)

    def _format_manager_items(self, items: list[object], *, state_key: str) -> str:
        rendered: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rendered.append(f"{item.get('slice_id', '--')}({item.get(state_key, '--')})")
        return ", ".join(rendered) if rendered else "--"

    def _format_manager_held_items(self, items: list[object]) -> str:
        rendered: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            reasons = item.get("reasons", [])
            first_reason = reasons[0] if isinstance(reasons, list) and reasons else "--"
            rendered.append(f"{item.get('slice_id', '--')}({first_reason})")
        return ", ".join(rendered) if rendered else "--"

    def _format_manager_tick_result(self, req_id: str, done: dict[str, object] | None) -> str:
        if done is None:
            return "queued, check /manager status"
        status = str(done.get("status", "unknown"))
        if status == "error":
            return f"manager tick: error\nreq_id: {req_id}\nerror: {done.get('error') or '--'}"

        result = done.get("result")
        parts: list[str] = []
        if isinstance(result, dict):
            for key in ("dispatch_skipped", "dispatched", "completed", "errors", "reaped"):
                value = result.get(key)
                if value in (None, [], {}):
                    continue
                if isinstance(value, list):
                    parts.append(f"{key}={len(value)}")
                else:
                    parts.append(f"{key}={value}")
        detail = ", ".join(parts) if parts else "done"
        return f"manager tick: {status}\nreq_id: {req_id}\n{detail}"

    def handle_command(self, command: str) -> dict[str, object]:
        return self.command_dispatcher.execute(command)

    def cleanup_idle_resources(self) -> None:
        self.tmate_manager.cleanup_idle()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PaulShiaBro Stage 1 daemon entry")
    parser.add_argument("--config", help="Stage 1 JSON 設定檔路徑")
    parser.add_argument("--command", required=True, help="要執行的最小指令")
    args = parser.parse_args(argv)

    try:
        daemon = PaulShiaBroDaemon(config=load_config(config_path=args.config))
        result = daemon.handle_command(args.command)
    except (ValueError, FileNotFoundError, KeyError) as error:
        print(f"錯誤: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
