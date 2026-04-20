#!/usr/bin/env python3
"""
破蝦哥 Lobster CLI banners (A/B/C) with ANSI colors.
Usage:
    python3 lobster_banner.py          # 印出全部
    python3 lobster_banner.py a|b|c    # 指定版本
"""
import sys

# ANSI palette
R  = "\033[38;5;203m"   # 紅殼 (lobster red)
RB = "\033[1;38;5;203m" # 粗紅
G  = "\033[1;38;5;220m" # 金項鍊
K  = "\033[48;5;235;38;5;235m"  # 黑墨鏡（黑底黑字色塊）
W  = "\033[1;37m"       # 觸鬚/亮線
S  = "\033[2;37m"       # 煙霧
Y  = "\033[38;5;136m"   # 雪茄
B  = "\033[38;5;94m"    # 公事包棕
X  = "\033[0m"          # reset


def banner_a() -> str:
    return (
        f"{W}     ╲╲        ╱╱\n"
        f"{W}      ╲╲      ╱╱\n"
        f"{RB}       ▄▄████▄▄\n"
        f"{RB}     ◣█  {K}▀▀{X}{RB}  {K}▀▀{X}{RB}  █◢  {Y}━▓{S}≈≈≈>{X}\n"
        f"{RB}      ▀█▄━━━━━▄█▀\n"
        f"{G}         $$$$$$$\n"
        f"{B}         ▐ ▪▪ ▌{X}\n"
    )


def banner_b() -> str:
    return (
        f"{W}    ╲╲  ╱╱\n"
        f"{RB}   ◣▄██▀██▄◢  {Y}━▓{S}≈>{X}\n"
        f"{RB}   █ {K}▀▀{X}{RB} {K}▀▀{X}{RB} █\n"
        f"{RB}    ▀{G}$$$$${RB}▀  {B}[▫]{X}\n"
    )


def banner_c() -> str:
    return (
        f"{W}  ╲╱\n"
        f"{RB} ◣{K}▀▀{X}{RB}◢{Y}≈>{X}\n"
        f"{G}  ${B}[▫]{X}\n"
    )


BANNERS = {"a": banner_a, "b": banner_b, "c": banner_c}


def print_banner(variant: str = "a") -> None:
    variant = variant.lower()
    fn = BANNERS.get(variant)
    if not fn:
        raise ValueError(f"unknown variant: {variant!r} (choose a/b/c)")
    print(fn(), end="")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        for k in ("a", "b", "c"):
            print(f"\n--- variant {k.upper()} ---")
            print_banner(k)
        return
    for a in args:
        print_banner(a)


if __name__ == "__main__":
    main()
