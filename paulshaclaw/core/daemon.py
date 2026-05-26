from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from paulshaclaw.core.config import AppConfig, load_config
from paulshaclaw.core.command_dispatcher import CommandDispatcher
from paulshaclaw.core.command_registry import CommandRegistry, CommandSpec, load_default_command_registry
from paulshaclaw.core.tmate import TmateManager


class CoordinatorClient(Protocol):
    def create_job(self, *, phase: str, scope: str, payload: dict[str, object]) -> dict[str, object]:
        """Create a minimal coordinator job."""


@dataclass
class LocalCoordinator:
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
    def __init__(
        self,
        config: AppConfig,
        coordinator: CoordinatorClient | None = None,
        command_registry: CommandRegistry | None = None,
        tmate_manager: TmateManager | None = None,
    ) -> None:
        self.config = config
        self.coordinator = coordinator or LocalCoordinator()
        self.command_registry = command_registry or load_default_command_registry()
        tmate_timeout = self.command_registry.get("/tmate").func_call.timeout_seconds or 3600
        self.tmate_manager = tmate_manager or TmateManager(timeout_seconds=tmate_timeout)
        self._cockpit_pane_id = next((pane.pane_id for pane in self.config.pane_assignments if pane.title == "cockpit"), None)
        self._agent_pane_id: str | None = None
        self.command_dispatcher = CommandDispatcher(
            registry=self.command_registry,
            python_handlers={
                "help": self._handle_help_command,
                "status": self._handle_status_command,
                "dispatch": self._handle_dispatch_command,
                "tmate": self._handle_tmate_command,
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
        if "claude-gemma4" in basenames:
            return True
        return basenames[:1] in (["claude"], ["claude.exe"]) and ".claude-gemma4/settings.json" in command

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

    def _resolve_agent_script_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "scripts" / "claude-gemma4"

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
        self._send_to_pane(pane_id, f"[user:{user_id}] {text}")
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

    def _handle_agent_command(self, args: list[str], command: CommandSpec) -> dict[str, object]:
        if len(args) > 1:
            raise ValueError("/agent 只接受 start/startf/stop/status")

        action = args[0] if args else "status"
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

            cockpit_pane_id = self._cockpit_pane_id
            if not cockpit_pane_id:
                raise ValueError("cockpit pane unavailable")

            launch_argv = [str(self._resolve_agent_script_path())]
            if action == "startf":
                launch_argv.append("-f")

            try:
                result = subprocess.run(
                    [
                        "tmux",
                        "split-window",
                        "-h",
                        "-t",
                        cockpit_pane_id,
                        "-P",
                        "-F",
                        "#{pane_id}",
                        shlex.join(launch_argv),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                raise ValueError((exc.stderr or "").strip() or "tmux split-window failed") from exc
            except FileNotFoundError as exc:
                raise ValueError("tmux unavailable") from exc

            pane_id = result.stdout.strip()
            if not pane_id:
                raise ValueError("tmux split-window did not return pane id")
            self._agent_pane_id = pane_id
            payload = self._agent_status_payload(pane_id=pane_id)
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
            self._agent_pane_id = None
            payload = self._agent_status_payload()
            payload.update({"stopped": True, "pane_id": pane_id, "pid": pid})
            return payload

        raise ValueError("/agent 只接受 start/startf/stop/status")

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
