"""Cockpit 吉祥物（破蝦哥 / PoHsiaBro 🦞）品牌呈現（issue #116）。

ASCII banner art 移植自既有設計稿 ``docs/research/lobster_banner.py``（A/B/C 三尺寸）——
此處為 runtime 單一真相源；docs/research 版保留為設計稿。純函式 + fail-soft：
任何呈現都不得影響 TUI 啟動，並尊重 ``NO_COLOR``。

cockpit 目前固定用 C（迷你蝦）置頂；A/B 一併移植備未來寬窗 / Telegram / daemon boot 用。
"""
from __future__ import annotations

import os
import re

LOBSTER_EMOJI = "\U0001f99e"  # 🦞 標準 emoji，作為 Header 標題前綴
BASE_TITLE = "PaulShiaBro Stage 11 Cockpit"

# ANSI palette（同設計稿）
_R = "\033[38;5;203m"            # 紅殼
_RB = "\033[1;38;5;203m"         # 粗紅
_G = "\033[1;38;5;220m"          # 金項鍊
_K = "\033[48;5;235;38;5;235m"   # 黑墨鏡
_W = "\033[1;37m"                # 觸鬚/亮線
_S = "\033[2;37m"                # 煙霧
_Y = "\033[38;5;136m"            # 雪茄
_B = "\033[38;5;94m"             # 公事包棕
_X = "\033[0m"                   # reset

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def banner_a() -> str:
    return (
        f"{_W}     ╲╲        ╱╱\n"
        f"{_W}      ╲╲      ╱╱\n"
        f"{_RB}       ▄▄████▄▄\n"
        f"{_RB}     ◣█  {_K}▀▀{_X}{_RB}  {_K}▀▀{_X}{_RB}  █◢  {_Y}━▓{_S}≈≈≈>{_X}\n"
        f"{_RB}      ▀█▄━━━━━▄█▀\n"
        f"{_G}         $$$$$$$\n"
        f"{_B}         ▐ ▪▪ ▌{_X}\n"
    )


def banner_b() -> str:
    return (
        f"{_W}    ╲╲  ╱╱\n"
        f"{_RB}   ◣▄██▀██▄◢  {_Y}━▓{_S}≈>{_X}\n"
        f"{_RB}   █ {_K}▀▀{_X}{_RB} {_K}▀▀{_X}{_RB} █\n"
        f"{_RB}    ▀{_G}$$$$${_RB}▀  {_B}[▫]{_X}\n"
    )


def banner_c() -> str:
    return (
        f"{_W}  ╲╱\n"
        f"{_RB} ◣{_K}▀▀{_X}{_RB}◢{_Y}≈>{_X}\n"
        f"{_G}  ${_B}[▫]{_X}\n"
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
