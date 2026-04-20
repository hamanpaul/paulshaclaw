from __future__ import annotations

import argparse
import json
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

    def status_snapshot(self) -> dict[str, object]:
        return {
            "ok": True,
            "daemon": self.config.daemon_name,
            "project": self.config.default_project,
            "pane_count": len(self.config.pane_assignments),
            "allowed_user_count": len(self.config.allowed_user_ids),
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
            task_id = normalized.split(maxsplit=1)[1].strip()
            if not task_id:
                raise ValueError("/dispatch 需要 task_id")
            return self.dispatch(task_id)

        raise ValueError(f"不支援的指令: {command}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PaulShiaBro Stage 1 daemon entry")
    parser.add_argument("--config", help="Stage 1 JSON 設定檔路徑")
    parser.add_argument("--command", required=True, help="要執行的最小指令")
    args = parser.parse_args(argv)

    daemon = PaulShiaBroDaemon(config=load_config(config_path=args.config))
    result = daemon.handle_command(args.command)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
