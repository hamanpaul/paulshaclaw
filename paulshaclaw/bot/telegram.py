from __future__ import annotations

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
    if result.get("kind") == "agent":
        if result.get("already_running"):
            title = "agent: already_running"
        elif result.get("already_stopped"):
            title = "agent: already_stopped"
        elif result.get("started"):
            title = "agent: started"
        elif result.get("stopped"):
            title = "agent: stopped"
        else:
            title = f"agent: {result.get('state', 'unknown')}"

        lines = [title]
        pane_id = result.get("pane_id")
        if pane_id:
            lines.append(f"pane: {pane_id}")
        if "pid" in result and result.get("pid") is not None:
            lines.append(f"pid: {result['pid']}")
        return "\n".join(lines)
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
    def __init__(self, daemon: PaulShiaBroDaemon) -> None:
        self.daemon = daemon

    def handle_message(self, *, user_id: int, text: str) -> dict[str, object]:
        if user_id not in self.daemon.config.allowed_user_ids:
            return {
                "ok": False,
                "message": "未授權使用者",
            }

        if not text.lstrip().startswith("/"):
            try:
                return {
                    "ok": True,
                    "message": self.daemon.route_to_agent(user_id=user_id, text=text),
                }
            except ValueError as error:
                return {
                    "ok": False,
                    "message": str(error),
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
