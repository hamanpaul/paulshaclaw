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

    def test_heading_only_body_is_noise(self):
        verdict = classify_noise({"atom_title": "x"}, "# Session dcbb8041-29ef-4a9f-a9e7-c408a65cbf20\n")
        self.assertTrue(verdict.is_noise)
        self.assertEqual(verdict.reason, "empty")

    def test_blank_body_is_noise(self):
        verdict = classify_noise({}, "   \n\n")
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

    def test_real_short_content_is_kept_regardless_of_length(self):
        # 30-char CJK real conclusion — must survive (no length threshold).
        verdict = classify_noise({}, "這是一段足夠長的真實技術內容，描述某個具體結論與其理由說明。\n")
        self.assertFalse(verdict.is_noise)

    def test_structural_heading_with_substantial_prose_is_kept(self):
        # A real distilled note that merely *starts* with `## Summary` but carries
        # multiple prose lines must NOT be deleted as structural-echo (#139 finding 3).
        body = (
            "## Summary\n"
            "本次調查確認 dream 管線停擺的根因是 frontmatter escaping。\n"
            "atomize 與 moc 兩個 pass 因單一 poison-pill 檔整批 ParserError。\n"
            "修法是 per-file 隔離加寫入端 YAML escaping，兩者缺一不可。\n"
        )
        verdict = classify_noise({}, body)
        self.assertFalse(verdict.is_noise, verdict.reason)

    def test_importer_exclusive_heading_is_noise_even_with_multiline_content(self):
        # `## Prompts` / `## CWD` / `## Source` / `## Touched files` / `## Referenced artifacts`
        # are importer-template-exclusive section names — never a real standalone knowledge
        # atom — so they are structural-echo regardless of how many prose lines follow.
        body = (
            "## Prompts\n"
            "1. # AGENTS.md instructions for /home/paul_chen\n\n"
            "<INSTRUCTIONS>\n你是高度自主的互動式 CLI Agent。\n專長為嵌入式系統。\n</INSTRUCTIONS>\n"
            "2. 修 UART\n"
        )
        verdict = classify_noise({}, body)
        self.assertTrue(verdict.is_noise, verdict.reason)
        self.assertEqual(verdict.reason, "structural-echo:Prompts")

    def test_summary_guard_still_protects_real_multiline_summary(self):
        # The ≤1-prose-line guard remains ONLY for `## Summary`, the one heading that
        # legitimately appears in real notes.
        body = (
            "## Summary\n第一段真實結論說明背景與動機。\n"
            "第二段補充技術細節與取捨。\n第三段給出後續步驟。\n"
        )
        verdict = classify_noise({}, body)
        self.assertFalse(verdict.is_noise, verdict.reason)

    def test_session_metadata_heading_is_noise(self):
        for heading in ("### Session Metadata", "## Session Information", "# Session Metadata"):
            body = (heading + "\n- **Session ID**: `019ef36c-4a13-7231`\n"
                    "- **Working Directory**: `/home/paul_chen/prj`\n- **Tool**: `copilot-cli`\n")
            verdict = classify_noise({}, body)
            self.assertTrue(verdict.is_noise, heading)
            self.assertTrue(verdict.reason.startswith("structural-echo"), verdict.reason)

    def test_note_quoting_placeholder_phrase_mid_body_is_kept(self):
        # A real note that discusses the placeholder text (not opens with it) is kept.
        body = (
            "noise classifier 的 placeholder 規則設計：\n"
            "當 session 沒有實際內容時，importer 會寫入「尚未收到您的具體需求」這類佔位字串，"
            "因此 classifier 需在 body 開頭附近偵測到該字串才判為 placeholder，避免誤刪引用它的真筆記。\n"
        )
        verdict = classify_noise({}, body)
        self.assertFalse(verdict.is_noise, verdict.reason)


if __name__ == "__main__":
    unittest.main()
