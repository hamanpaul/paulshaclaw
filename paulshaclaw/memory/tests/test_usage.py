from __future__ import annotations

import unittest

from paulshaclaw.memory.usage import extract_offered, extract_cited, extract_matched


_BRIEF = (
    "# Memory wake-up\n\n"
    "- [[llm-atomizer-core--sl-7be63668250fff95|LLM Atomizer Technical Specification]] — spec\n"
    "- [[phase-2a--sl-c1e80dbdadedb8cf|Phase 2a Promoter Integration]] — ship\n"
)


class ExtractOfferedTests(unittest.TestCase):
    def test_extracts_id_and_title_pairs(self):
        offered = extract_offered(_BRIEF)
        self.assertIn(("sl-7be63668250fff95", "LLM Atomizer Technical Specification"), offered)
        self.assertIn(("sl-c1e80dbdadedb8cf", "Phase 2a Promoter Integration"), offered)

    def test_malformed_brief_returns_empty(self):
        self.assertEqual(extract_offered("no wikilinks here"), [])


class ExtractCitedTests(unittest.TestCase):
    def test_cites_offered_ids_only(self):
        offered_ids = {"sl-7be63668250fff95", "sl-c1e80dbdadedb8cf"}
        text = "我參考了 [[sl-7be63668250fff95]] 與不存在的 sl-aaaaaaaaaaaaaaaa。"
        self.assertEqual(extract_cited(text, offered_ids), {"sl-7be63668250fff95"})

    def test_bare_id_also_counts(self):
        offered_ids = {"sl-c1e80dbdadedb8cf"}
        self.assertEqual(extract_cited("見 sl-c1e80dbdadedb8cf", offered_ids), {"sl-c1e80dbdadedb8cf"})


class ExtractMatchedTests(unittest.TestCase):
    def test_title_match_excludes_short_and_cited(self):
        offered = [
            ("sl-7be63668250fff95", "LLM Atomizer Technical Specification"),
            ("sl-c1e80dbdadedb8cf", "Phase 2a Promoter Integration"),
            ("sl-1111111111111111", "spec"),
        ]
        text = "本次用到 LLM Atomizer Technical Specification 與 Phase 2a Promoter Integration；spec 是巧合。"
        matched = extract_matched(text, offered, exclude={"sl-c1e80dbdadedb8cf"})
        self.assertEqual(matched, {"sl-7be63668250fff95"})


if __name__ == "__main__":
    unittest.main()
