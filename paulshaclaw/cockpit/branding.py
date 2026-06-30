"""Cockpit 吉祥物（破蝦哥 / PoHsiaBro）品牌呈現（issue #116）。

顏文字風龍蝦：觸鬚 ʅ ʃ（蝦）+ 墨鏡臉 (⌐■_■)（酷）+ 螯 ⋑ ⋐（蝦）+ 叼菸冒煙 y~（幫）
+ 金鏈 ◦○◦（財）。橘色三階色盤取自 ui-ux-pro-max design-system（playful orange）。
純函式 + fail-soft：任何呈現都不得影響 TUI 啟動，並尊重 ``NO_COLOR``。

cockpit 固定用 C（mini）置頂；A/B 為同識別的放大版（寬窗 / Telegram / daemon boot 備用）。
字元集刻意收斂在已驗證可渲染者：ʅ ʃ ⋑ ⋐ ⌐ ■ _ y ~ ◦ ○ ( ) 與 ASCII。
"""
from __future__ import annotations

import os
import re

LOBSTER_EMOJI = "\U0001f99e"  # 🦞 Header 標題前綴
BASE_TITLE = "PaulShiaBro Stage 11 Cockpit"

# ANSI palette（映射 ui-ux-pro-max design-system 色盤）
_ANT = "\033[38;5;215m"          # 觸鬚（淺橘）
_OR = "\033[1;38;5;208m"         # 殼 / 螯（橘）#F97316
_GD = "\033[1;38;5;220m"         # 金鏈
_BK = "\033[1;38;5;236m"         # 墨鏡（深）
_CIG = "\033[38;5;180m"          # 菸身（淺褐）
_SMK = "\033[2;37m"              # 煙
_X = "\033[0m"                   # reset

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def banner_a() -> str:  # 完整版（寬窗）：觸鬚 + 臉 + 叼菸 + 金鏈 + 節肢尾
    return (
        f"{_ANT}    ʅ     ʃ{_X}\n"
        f"{_OR}   ⋑({_BK}⌐■_■{_OR})⋐{_X} {_CIG}y{_SMK}~~{_X}\n"
        f"{_GD}     ◦○○○◦{_X}\n"
        f"{_OR}     )))))){_X}\n"
    )


def banner_b() -> str:  # 中版
    return (
        f"{_ANT}   ʅ   ʃ{_X}\n"
        f"{_OR}  ⋑({_BK}⌐■_■{_OR})⋐{_X} {_CIG}y{_SMK}~{_X}\n"
        f"{_GD}    ◦○○◦{_X}\n"
        f"{_OR}    )))){_X}\n"
    )


def banner_c() -> str:  # mini（cockpit 置頂用）
    return (
        f"{_ANT}  ʅ   ʃ{_X}\n"
        f"{_OR}⋑({_BK}⌐■_■{_OR})⋐{_X} {_CIG}y{_SMK}~{_X}\n"
        f"{_GD}   ◦○◦{_X}\n"
    )


_BANNERS = {"a": banner_a, "b": banner_b, "c": banner_c}


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _color_enabled() -> bool:
    """NO_COLOR（任何非空值）→ 關色，符合 https://no-color.org/ 慣例。"""
    return not os.environ.get("NO_COLOR")


def banner(variant: str = "c", *, color: bool | None = None) -> str:
    """回傳指定尺寸的破蝦哥 banner；``color`` 預設依 NO_COLOR env，False 則去 ANSI。

    未知 variant → 退回 C（fail-soft，不拋）。
    """
    fn = _BANNERS.get(str(variant).lower(), banner_c)
    art = fn()
    use_color = _color_enabled() if color is None else color
    return art if use_color else strip_ansi(art)


def cockpit_title(base: str = BASE_TITLE) -> str:
    """Header 標題：``🦞 PaulShiaBro Stage 11 Cockpit``。"""
    return f"{LOBSTER_EMOJI} {base}"
