#!/usr/bin/env python3
"""
建立 PoHsiaBro PUA font：U+E100 → lobster_mascot.svg
FontForge import SVG 時已自動翻轉 Y，不再額外 flip。
只做 scale + center 使 glyph 置中於 em square。
"""
import fontforge, subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
SVG_FILE   = SCRIPT_DIR / "lobster_mascot.svg"
FONT_DIR   = Path.home() / ".local/share/fonts"
FONT_PATH  = FONT_DIR / "PoHsiaBro.ttf"
EM         = 1024
MARGIN     = 60          # 上下左右留白

def build_font():
    f = fontforge.font()
    f.fontname   = "PoHsiaBro"
    f.familyname = "PoHsiaBro"
    f.fullname   = "Po Hsia Bro PUA Icon"
    f.copyright  = "CC0 Public Domain"
    f.encoding   = "UnicodeFull"
    f.em         = EM

    g = f.createChar(0xE100, "pohsiabro")
    g.importOutlines(str(SVG_FILE))
    # FontForge 已自動 flip Y（SVG Y↓ → font Y↑），不需再 flip

    bb   = g.boundingBox()          # (xmin, ymin, xmax, ymax) in font units
    w    = bb[2] - bb[0]
    h    = bb[3] - bb[1]

    # 計算 uniform scale 使 glyph 填滿 em - 2*MARGIN
    target = EM - 2 * MARGIN
    scale  = target / max(w, h)

    # 置中
    tx = (EM - w * scale) / 2 - bb[0] * scale
    ty = (EM - h * scale) / 2 - bb[1] * scale

    g.transform((scale, 0, 0, scale, tx, ty))
    g.width = EM

    g.removeOverlap()
    g.simplify()
    g.canonicalContours()
    g.canonicalStart()

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    f.generate(str(FONT_PATH))
    print(f"[OK] 字型儲存：{FONT_PATH}")
    print(f"     raw bbox={bb}  scale={scale:.3f}  tx={tx:.1f}  ty={ty:.1f}")

def refresh():
    subprocess.run(["fc-cache", "-fv", str(FONT_DIR)], capture_output=True, check=True)
    r = subprocess.run(["fc-list", ":family=PoHsiaBro"], capture_output=True, text=True)
    ok = "PoHsiaBro" in r.stdout
    print(f"[{'OK' if ok else 'WARN'}] fc-list: {'找到' if ok else '未找到'} PoHsiaBro")

if __name__ == "__main__":
    build_font()
    refresh()
    print("\n  code point : U+E100")
    print("  printf test: printf '\\ue100\\n'")
    print("  Python test: print('\\ue100')")
