from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Protocol

from paulshaclaw.core.config import AppConfig, load_config
from paulshaclaw.core.command_dispatcher import CommandDispatcher
from paulshaclaw.core.command_registry import CommandRegistry, CommandSpec, load_default_command_registry


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
    ) -> None:
        self.config = config
        self.coordinator = coordinator or LocalCoordinator()
        self.command_registry = command_registry or load_default_command_registry()
        self.command_dispatcher = CommandDispatcher(
            registry=self.command_registry,
            python_handlers={
                "help": self._handle_help_command,
                "status": self._handle_status_command,
                "dispatch": self._handle_dispatch_command,
                "tmate": self._handle_tmate_command,
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
            raise ValueError("help 只接受一個參數")
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
        raise ValueError("tmate backend 未設定")

    def handle_command(self, command: str) -> dict[str, object]:
        return self.command_dispatcher.execute(command)


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
