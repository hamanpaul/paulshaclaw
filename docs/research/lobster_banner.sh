#!/usr/bin/env bash
# 破蝦哥 Lobster CLI banners (A/B/C) with ANSI colors.
# Usage:
#   ./lobster_banner.sh           # 全部
#   ./lobster_banner.sh a|b|c     # 指定版本
#   source lobster_banner.sh && print_banner a

# ANSI palette
R=$'\033[38;5;203m'      # 紅殼
RB=$'\033[1;38;5;203m'   # 粗紅
G=$'\033[1;38;5;220m'    # 金項鍊
K=$'\033[48;5;235;38;5;235m'  # 黑墨鏡色塊
W=$'\033[1;37m'          # 亮線 (觸鬚)
S=$'\033[2;37m'          # 煙霧
Y=$'\033[38;5;136m'      # 雪茄
B=$'\033[38;5;94m'       # 公事包
X=$'\033[0m'             # reset

_banner_a() {
  printf '%s     ╲╲        ╱╱\n' "$W"
  printf '%s      ╲╲      ╱╱\n' "$W"
  printf '%s       ▄▄████▄▄\n' "$RB"
  printf '%s     ◣█  %s▀▀%s%s  %s▀▀%s%s  █◢  %s━▓%s≈≈≈>%s\n' \
    "$RB" "$K" "$X" "$RB" "$K" "$X" "$RB" "$Y" "$S" "$X"
  printf '%s      ▀█▄━━━━━▄█▀\n' "$RB"
  printf '%s         $$$$$$$\n' "$G"
  printf '%s         ▐ ▪▪ ▌%s\n' "$B" "$X"
}

_banner_b() {
  printf '%s    ╲╲  ╱╱\n' "$W"
  printf '%s   ◣▄██▀██▄◢  %s━▓%s≈>%s\n' "$RB" "$Y" "$S" "$X"
  printf '%s   █ %s▀▀%s%s %s▀▀%s%s █\n' "$RB" "$K" "$X" "$RB" "$K" "$X" "$RB"
  printf '%s    ▀%s$$$$$%s▀  %s[▫]%s\n' "$RB" "$G" "$RB" "$B" "$X"
}

_banner_c() {
  printf '%s  ╲╱\n' "$W"
  printf '%s ◣%s▀▀%s%s◢%s≈>%s\n' "$RB" "$K" "$X" "$RB" "$Y" "$X"
  printf '%s  $%s[▫]%s\n' "$G" "$B" "$X"
}

print_banner() {
  case "${1:-a}" in
    a|A) _banner_a ;;
    b|B) _banner_b ;;
    c|C) _banner_c ;;
    *) echo "unknown variant: $1 (choose a/b/c)" >&2; return 1 ;;
  esac
}

# only run when executed, not when sourced
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  if [[ $# -eq 0 ]]; then
    for v in a b c; do
      printf '\n--- variant %s ---\n' "${v^^}"
      print_banner "$v"
    done
  else
    for v in "$@"; do print_banner "$v"; done
  fi
fi
