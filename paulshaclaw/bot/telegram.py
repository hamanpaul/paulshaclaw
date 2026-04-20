from __future__ import annotations

from paulshaclaw.core.daemon import PaulShiaBroDaemon


def _format_message(result: dict[str, object]) -> str:
    if "daemon" in result:
        return (
            f"{result['daemon']} 狀態\n"
            f"project={result['project']}\n"
            f"panes={result['pane_count']}"
        )
    return f"已派工 {result['job_id']} -> {result['scope']}"


class TelegramCommandRouter:
    def __init__(self, daemon: PaulShiaBroDaemon) -> None:
        self.daemon = daemon

    def handle_message(self, *, user_id: int, text: str) -> dict[str, object]:
        if user_id not in self.daemon.config.allowed_user_ids:
            return {
                "ok": False,
                "message": "未授權使用者",
            }

        try:
            result = self.daemon.handle_command(text)
        except ValueError as error:
            return {
                "ok": False,
                "message": str(error),
            }
        return {
            "ok": True,
            "message": _format_message(result),
            "result": result,
        }
