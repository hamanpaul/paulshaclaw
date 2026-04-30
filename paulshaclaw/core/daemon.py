from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Protocol

from paulshaclaw.core.config import AppConfig, load_config


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
    def __init__(self, config: AppConfig, coordinator: CoordinatorClient | None = None) -> None:
        self.config = config
        self.coordinator = coordinator or LocalCoordinator()

    def _list_panes_text(self) -> str:
        try:
            result = subprocess.run(
                ["tmux", "list-panes", "-a", "-F",
                 "#{session_name}:#{window_index} #{pane_id} #{pane_current_command}"],
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

    def handle_command(self, command: str) -> dict[str, object]:
        normalized = command.strip()
        if normalized == "/status":
            return self.status_snapshot()

        if normalized.startswith("/dispatch "):
            rest = normalized.split(maxsplit=1)[1].strip()
            tokens = rest.split()
            pane_idx = next((i for i, t in enumerate(tokens) if t.startswith("%")), None)
            if pane_idx is not None:
                pane_id = tokens[pane_idx]
                message = " ".join(tokens[pane_idx + 1:])
                if not message:
                    raise ValueError(f"/dispatch {pane_id} 需要訊息內容")
                return self._send_to_pane(pane_id, message)
            if not rest:
                raise ValueError("/dispatch 需要 task_id")
            return self.dispatch(rest)

        raise ValueError(f"不支援的指令: {command}")


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
