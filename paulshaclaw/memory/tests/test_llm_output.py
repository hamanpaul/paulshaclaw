from __future__ import annotations

import unittest

from paulshaclaw.memory.atomizer import llm_output

PROJECTS = ["paulshaclaw", "prplos-core"]
GOOD = (
    'prose before\n```json\n'
    '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":["t"],'
    '"body":"b","source_fragment_indices":[0],"relations":[]}]\n```\nprose after'
)


class LlmOutputTests(unittest.TestCase):
    def test_parses_fenced_json(self):
        proposals = llm_output.parse(GOOD, PROJECTS)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].artifact_kind, "report")
        self.assertEqual(proposals[0].project, "paulshaclaw")

    def test_parses_bare_array(self):
        raw = (
            '[{"title":"a","artifact_kind":"plan","project":"_unknown","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]'
        )
        self.assertEqual(len(llm_output.parse(raw, PROJECTS)), 1)

    def test_parses_bare_array_after_label_on_previous_line(self):
        raw = (
            "Output:\n"
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]'
        )
        self.assertEqual(len(llm_output.parse(raw, PROJECTS)), 1)

    def test_malformed_json_raises(self):
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse("not json at all", PROJECTS)

    def test_bad_artifact_kind_raises(self):
        raw = (
            '[{"title":"a","artifact_kind":"banana","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]'
        )
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_unknown_project_raises(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"ghost","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]'
        )
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_empty_body_raises(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"  ",'
            '"source_fragment_indices":[0],"relations":[]}]'
        )
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_missing_required_fields_raise(self):
        cases = (
            ('[{"artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b","source_fragment_indices":[0],"relations":[]}]'),
            ('[{"title":"a","artifact_kind":"report","project":"paulshaclaw","body":"b","source_fragment_indices":[0],"relations":[]}]'),
            ('[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b","relations":[]}]'),
            ('[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b","source_fragment_indices":[0]}]'),
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(llm_output.LlmOutputError):
                    llm_output.parse(raw, PROJECTS)

    def test_title_must_be_non_empty_string(self):
        cases = (
            '[{"title":"","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b","source_fragment_indices":[0],"relations":[]}]',
            '[{"title":"   ","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b","source_fragment_indices":[0],"relations":[]}]',
            '[{"title":7,"artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b","source_fragment_indices":[0],"relations":[]}]',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(llm_output.LlmOutputError):
                    llm_output.parse(raw, PROJECTS)

    def test_tag_entries_must_be_strings(self):
        cases = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[7],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]',
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[true],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]',
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[null],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(llm_output.LlmOutputError):
                    llm_output.parse(raw, PROJECTS)

    def test_source_fragment_indices_must_be_ints_and_not_bools(self):
        cases = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":["1"],"relations":[]}]',
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[2.9],"relations":[]}]',
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[true],"relations":[]}]',
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[false],"relations":[]}]',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(llm_output.LlmOutputError):
                    llm_output.parse(raw, PROJECTS)

    def test_empty_source_fragment_indices_raise(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[],"relations":[]}]'
        )
        with self.assertRaisesRegex(
            llm_output.LlmOutputError, "proposal 0 source_fragment_indices must not be empty"
        ):
            llm_output.parse(raw, PROJECTS)

    def test_parses_bare_array_with_non_json_brackets_in_prose(self):
        raw = (
            'analysis [draft only]\n'
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]\n'
            'done ] trailing note'
        )
        proposals = llm_output.parse(raw, PROJECTS)
        self.assertEqual(len(proposals), 1)

    def test_duplicate_titles_raise(self):
        raw = (
            '[{"title":"dup","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b1",'
            '"source_fragment_indices":[0],"relations":[]},'
            '{"title":"dup","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b2",'
            '"source_fragment_indices":[1],"relations":[]}]'
        )
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_non_list_fields_raise(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":"x","body":"b",'
            '"source_fragment_indices":"0","relations":{}}]'
        )
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_unknown_top_level_fields_raise(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[],"extra":"x"}]'
        )
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_relation_entries_must_be_objects(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":["bad"]}]'
        )
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_dangling_relates_to_parses_for_later_resolution(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[{"type":"relates_to","target_title":"missing"}]}]'
        )
        proposals = llm_output.parse(raw, PROJECTS)
        self.assertEqual(proposals[0].relations, ({"type": "relates_to", "target_title": "missing"},))

    def test_relates_to_relation_requires_non_empty_target_title(self):
        cases = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[{"type":"relates_to"}]}]',
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[{"type":"relates_to","target_title":"  "}]}]',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(llm_output.LlmOutputError):
                    llm_output.parse(raw, PROJECTS)

    def test_mentions_relation_requires_non_empty_entity(self):
        cases = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[{"type":"mentions"}]}]',
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[{"type":"mentions","entity":"  "}]}]',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(llm_output.LlmOutputError):
                    llm_output.parse(raw, PROJECTS)

    def test_unknown_relation_type_raises(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[{"type":"unknown","target_title":"x"}]}]'
        )
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_relation_extra_fields_raise(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"body a",'
            '"source_fragment_indices":[0],"relations":[{"type":"mentions","entity":"MTK","extra":"x"}]},'
            '{"title":"b","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"body b",'
            '"source_fragment_indices":[1],"relations":[]}]'
        )
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_skips_syntactically_valid_non_proposal_array(self):
        raw = (
            'analysis scratch: [1, 2, 3]\n'
            'actual payload follows\n'
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]'
        )
        proposals = llm_output.parse(raw, PROJECTS)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].title, "a")

    def test_multiple_valid_proposal_arrays_raise(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]\n'
            '[{"title":"c","artifact_kind":"plan","project":"prplos-core","tags":[],"body":"d",'
            '"source_fragment_indices":[1],"relations":[]}]'
        )
        with self.assertRaisesRegex(llm_output.LlmOutputError, "multiple valid JSON arrays found"):
            llm_output.parse(raw, PROJECTS)


if __name__ == "__main__":
    unittest.main()
