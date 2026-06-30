"""Cockpit 吉祥物（破蝦哥 / PoHsiaBro）品牌呈現（issue #116）。

顏文字臉 + 像素方塊身軀的混合龍蝦角色，逐輪與使用者調校定稿：
觸鬚 ʅ ʃ · 雙圓鉗 ◖◗ · 白墨鏡臉 (⌐■_■) · 叼菸 y~ · 金鏈項鍊 ◦◦◦ ·
框邊身體 ▐█▌ · 上抬尖尾 ◢▀◣ · 公事包 [▪]。配色取自 ui-ux-pro-max
design-system 的 playful-orange 三階色盤；墨鏡用亮白以利黑底終端機對比。

純函式 + fail-soft：任何呈現都不得影響 TUI 啟動，並尊重 ``NO_COLOR``。
cockpit 置頂用 C；A/B 暫與 C 同，保留 variant 介面供未來尺寸分化。
"""
from __future__ import annotations

import os
import re

LOBSTER_EMOJI = "\U0001f99e"  # 🦞 Header 標題前綴
BASE_TITLE = "PaulShiaBro Stage 11 Cockpit"

# ANSI palette（映射 ui-ux-pro-max design-system 色盤）
_ANT = "\033[38;5;215m"          # 觸鬚（淺橘）
_OR = "\033[1;38;5;208m"         # 殼 / 鉗 / 身（橘）#F97316
_GLS = "\033[1;38;5;231m"        # 墨鏡鏡片（亮白反光，黑底終端機才看得到）
_CIG = "\033[38;5;180m"          # 菸身（淺褐）
_SMK = "\033[2;37m"              # 煙
_GD = "\033[1;38;5;220m"         # 金鏈
_TAIL = "\033[38;5;130m"         # 像素尾扇（深橘，補強龍蝦身形）
_BR = "\033[38;5;94m"            # 公事包（棕）
_X = "\033[0m"                   # reset

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def banner_c() -> str:
    """破蝦哥（cockpit 置頂用，5 列）。"""
    return (
        f"{_ANT}  ʅ   ʃ{_X}\n"
        f"{_OR}◖◗({_GLS}⌐■_■{_OR})◖◗{_X} {_CIG}y{_SMK}~{_X}\n"
        f"{_GD}   ◦◦◦{_X}\n"
        f"{_OR}   ▐█▌{_X}  {_BR}[▪]{_X}\n"
        f"{_TAIL}   ◢▀◣{_X}\n"
    )


# A/B 暫與 C 同識別；未來如需寬窗 / Telegram 尺寸分化，於此分流。
def banner_a() -> str:
    return banner_c()


def banner_b() -> str:
    return banner_c()


_BANNERS = {"a": banner_a, "b": banner_b, "c": banner_c}


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _color_enabled() -> bool:
    """NO_COLOR（任何非空值）→ 關色，符合 https://no-color.org/ 慣例。"""
    return not os.environ.get("NO_COLOR")


def banner(variant: str = "c", *, color: bool | None = None) -> str:
    """回傳破蝦哥 banner；``color`` 預設依 NO_COLOR env，False 則去 ANSI。

    未知 variant → 退回 C（fail-soft，不拋）。
    """
    fn = _BANNERS.get(str(variant).lower(), banner_c)
    art = fn()
    use_color = _color_enabled() if color is None else color
    return art if use_color else strip_ansi(art)


def cockpit_title(base: str = BASE_TITLE) -> str:
    """Header 標題：``🦞 PaulShiaBro Stage 11 Cockpit``。"""
    return f"{LOBSTER_EMOJI} {base}"
