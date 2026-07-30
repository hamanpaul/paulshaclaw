from __future__ import annotations

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.screen import ModalScreen
    from textual.widgets import Static
except Exception:  # pragma: no cover - fallback when textual not installed
    from typing import Any, Generic, Iterable, TypeVar

    T = TypeVar("T")
    ComposeResult = Iterable[Any]

    class Binding:  # pragma: no cover - noop
        def __init__(self, key: str, handler: str, description: str) -> None:
            self.key = key
            self.handler = handler
            self.description = description

    class ModalScreen(Generic[T]):  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def dismiss(self) -> None:
            pass

    class Static:  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass


class HelpModal(ModalScreen[None]):
    BINDINGS = [Binding("escape", "dismiss_help", "Close")]

    def __init__(self, bindings: list[Binding]) -> None:
        super().__init__()
        self.help_text = self.render_help_text(bindings)

    @staticmethod
    def render_help_text(bindings: list[Binding]) -> str:
        rows = []
        for binding in bindings:
            key = getattr(binding, "key", "")
            description = getattr(binding, "description", "")
            if key and description:
                rows.append(f"{key}: {description}")
        return "\n".join(
            [
                "Stage 11 Cockpit Help",
                "",
                "面板：",
                "tab 切換 WORK／JOBS focus",
                "WORK：↑↓ 選 pane，enter 或雙擊把選中的 pane 換到我面前",
                "JOBS：↑↓ 移動節點，enter/space 展開或收合該群，",
                "      滾輪或 PgUp/PgDn 捲動，j 收合/展開整個 JOBS 面板",
                "",
                "Keys:",
                *rows,
                "",
                "Behavior:",
                "WORK 只列 cockpit session 的 panes；其他 session 只計入",
                "banner 摘要（#249），不再逐列列出。",
                "Enter 或雙擊把選中的 pane 換到我面前；上一次 swap 會在下一次",
                "swap 前自動復原。",
                "JOBS 是可捲動的樹：多 phase 群展開看細節，needs_human 的",
                "detail 行含可直接複製執行的命令。",
                "active slot 不會用其他 session 的相同幾何來猜測。",
            ]
        )

    def compose(self) -> ComposeResult:
        card = Static(self.help_text, id="help-modal")
        # 面板化：品牌橘框卡片 + 標題/副標（cockpit.tcss 上色）。stub 無此屬性則略過。
        try:
            card.border_title = "🦞 Cockpit · 說明"
            card.border_subtitle = "esc 關閉"
        except Exception:
            pass
        yield card

    def action_dismiss_help(self) -> None:
        callback = getattr(self.app, "_on_help_closed", None)
        if callable(callback):
            callback()
        self.dismiss()
