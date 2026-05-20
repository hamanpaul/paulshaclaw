from __future__ import annotations

from paulshaclaw.chat.backend import ChatBackend, ClosedChatBackend
from paulshaclaw.core.daemon import PaulShiaBroDaemon


def _format_message(result: dict[str, object]) -> str:
    if result.get("kind") == "help":
        return str(result["text"])
    if result.get("kind") == "tmate":
        state = str(result.get("state", "unknown"))
        if state == "running" and all(result.get(key) for key in ("ssh", "web", "ssh_ro", "web_ro")):
            return "\n".join(
                [
                    "tmate: running",
                    f"ssh: {result['ssh']}",
                    f"web: {result['web']}",
                    f"ssh_ro: {result['ssh_ro']}",
                    f"web_ro: {result['web_ro']}",
                ]
            )
        return f"tmate: {state}"
    if "sent" in result:
        return f"已送出 -> {result['pane_id']}\n{result['sent']}"
    if "daemon" in result:
        lines = [
            f"{result['daemon']} 狀態",
            f"project={result['project']}",
            "",
            "Panes:",
            str(result.get("panes", "(unavailable)")),
        ]
        return "\n".join(lines)
    return f"已派工 {result['job_id']} -> {result['scope']}"


class TelegramCommandRouter:
    def __init__(self, daemon: PaulShiaBroDaemon, chat_backend: ChatBackend | None = None) -> None:
        self.daemon = daemon
        self.chat_backend = chat_backend or ClosedChatBackend()

    def handle_message(self, *, user_id: int, text: str) -> dict[str, object]:
        if user_id not in self.daemon.config.allowed_user_ids:
            return {
                "ok": False,
                "message": "未授權使用者",
            }

        if not text.lstrip().startswith("/"):
            return {
                "ok": True,
                "message": self.chat_backend.reply(user_id=user_id, text=text),
            }

        try:
            result = self.daemon.handle_command(text.lstrip())
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
