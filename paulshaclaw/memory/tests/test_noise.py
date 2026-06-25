from __future__ import annotations

import unittest

from paulshaclaw.memory.noise import classify_noise


class ClassifyNoiseTests(unittest.TestCase):
    def test_structural_echo_headings_are_noise(self):
        for section in ("CWD", "Source", "Prompts", "Touched files",
                        "Referenced artifacts", "Summary"):
            body = f"## {section}\nsome value here that is fairly long but still echo\n"
            verdict = classify_noise({"atom_title": section.lower()}, body)
            self.assertTrue(verdict.is_noise, section)
            self.assertEqual(verdict.reason, f"structural-echo:{section}")

    def test_empty_body_is_noise(self):
        verdict = classify_noise({"atom_title": "x"}, "tiny\n")
        self.assertTrue(verdict.is_noise)
        self.assertEqual(verdict.reason, "empty")

    def test_placeholder_phrases_are_noise(self):
        for phrase in ("由於目前尚未收到您的具體需求，請提供更多細節以便我協助您完成任務。",
                       "目前尚未收到您的具體需求或任務指令，請提供。",
                       "(無內容) 這是一個空的 session 沒有任何實際內容可供原子化處理。"):
            verdict = classify_noise({}, phrase + "\n")
            self.assertTrue(verdict.is_noise, phrase[:10])
            self.assertEqual(verdict.reason, "placeholder")

    def test_untitled_with_real_body_is_kept(self):
        body = ("## 動工前\n- [ ] 確認當前分支不是 `main`\n  - 若在 `main`，先開 "
                "`feature/<slug>` 分支\n- [ ] 跨多子項先用 `git worktree` 拆開\n")
        verdict = classify_noise({"atom_title": "untitled"}, body)
        self.assertFalse(verdict.is_noise)

    def test_real_short_fact_is_kept(self):
        body = "gh 2.45.0 的 pr checks 沒有 --json，要用 pr view --json statusCheckRollup 判 CI。\n"
        verdict = classify_noise({"atom_title": "ci-gating"}, body)
        self.assertFalse(verdict.is_noise)

    def test_empty_threshold_boundary(self):
        # 真實、非 placeholder、非結構段落的 body，長度剛好跨越 40 字元門檻。
        below = "merge 前先跑 unit 與 integration 測試才算完成。"  # strip 後 36 字
        self.assertLess(len(below.strip()), 40)
        verdict_below = classify_noise({"atom_title": "x"}, below + "\n")
        self.assertTrue(verdict_below.is_noise)
        self.assertEqual(verdict_below.reason, "empty")

        above = "merge 前先跑 unit 與 integration 測試，未綠不得宣告完成喔。"  # strip 後 42 字
        self.assertGreater(len(above.strip()), 40)
        verdict_above = classify_noise({"atom_title": "x"}, above + "\n")
        self.assertFalse(verdict_above.is_noise)


if __name__ == "__main__":
    unittest.main()
