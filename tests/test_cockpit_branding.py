"""paulshaclaw.cockpit.branding 單測（issue #116）。

純函式、不啟動 TUI、不碰脆弱的 App/Pilot 測試。banner art 移植自設計稿。
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from paulshaclaw.cockpit import branding


class TitleTests(unittest.TestCase):
    def test_title_has_lobster_and_base(self) -> None:
        title = branding.cockpit_title()
        self.assertTrue(title.startswith(branding.LOBSTER_EMOJI + " "))
        self.assertEqual(ord(branding.LOBSTER_EMOJI), 0x1F99E)
        self.assertIn(branding.BASE_TITLE, title)

    def test_custom_base(self) -> None:
        self.assertEqual(branding.cockpit_title("X"), f"{branding.LOBSTER_EMOJI} X")


class BannerTests(unittest.TestCase):
    def test_default_variant_is_c(self) -> None:
        self.assertEqual(branding.banner(), branding.banner("c"))
        # C 為 5 列：觸鬚 / 頭(鉗+臉+菸) / 金鏈 / 身體+公事包 / 尾
        self.assertEqual(branding.banner("c", color=False).count("\n"), 5)

    def test_unknown_variant_falls_back_to_c(self) -> None:
        self.assertEqual(branding.banner("zzz", color=False), branding.banner("c", color=False))

    def test_color_true_has_ansi_false_has_none(self) -> None:
        self.assertIn("\x1b[", branding.banner("c", color=True))
        plain = branding.banner("c", color=False)
        self.assertNotIn("\x1b[", plain)
        # 去色後仍保留破蝦哥識別字元：墨鏡臉 (⌐■_■) + 叼菸 y + 金鏈 ◦◦◦ + 公事包 [▪] + 尾 ◢▀◣
        self.assertIn("⌐■_■", plain)
        self.assertIn("y", plain)
        self.assertIn("◦◦◦", plain)
        self.assertIn("[▪]", plain)
        self.assertIn("◢▀◣", plain)

    def test_strip_ansi_idempotent_and_complete(self) -> None:
        once = branding.strip_ansi(branding.banner_a())
        self.assertEqual(branding.strip_ansi(once), once)
        self.assertNotIn("\x1b", once)

    def test_all_three_variants_present(self) -> None:
        for v in ("a", "b", "c"):
            self.assertTrue(branding.banner(v, color=False).strip())


class NoColorEnvTests(unittest.TestCase):
    def test_no_color_env_strips_ansi_by_default(self) -> None:
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertNotIn("\x1b[", branding.banner("c"))

    def test_color_when_no_color_unset(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        with patch.dict(os.environ, env, clear=True):
            self.assertIn("\x1b[", branding.banner("c"))


if __name__ == "__main__":
    unittest.main()
