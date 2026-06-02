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

    def test_missing_optional_fields_default_empty(self):
        raw = '[{"artifact_kind":"report","project":"paulshaclaw","body":"b"}]'
        proposals = llm_output.parse(raw, PROJECTS)
        self.assertEqual(proposals[0].title, "")
        self.assertEqual(proposals[0].tags, ())
        self.assertEqual(proposals[0].source_fragment_indices, ())
        self.assertEqual(proposals[0].relations, ())

    def test_title_is_stringified(self):
        raw = (
            '[{"title":7,"artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]'
        )
        proposals = llm_output.parse(raw, PROJECTS)
        self.assertEqual(proposals[0].title, "7")

    def test_tag_entries_are_stringified(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[7,true,null],"body":"b",'
            '"source_fragment_indices":[0],"relations":[]}]'
        )
        proposals = llm_output.parse(raw, PROJECTS)
        self.assertEqual(proposals[0].tags, ("7", "True", "None"))

    def test_source_fragment_indices_are_coerced_with_int(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":["1",2.9,true],"relations":[]}]'
        )
        proposals = llm_output.parse(raw, PROJECTS)
        self.assertEqual(proposals[0].source_fragment_indices, (1, 2, 1))

    def test_duplicate_titles_are_allowed(self):
        raw = (
            '[{"title":"dup","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b1",'
            '"source_fragment_indices":[0],"relations":[]},'
            '{"title":"dup","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b2",'
            '"source_fragment_indices":[1],"relations":[]}]'
        )
        proposals = llm_output.parse(raw, PROJECTS)
        self.assertEqual(len(proposals), 2)
        self.assertEqual([proposal.title for proposal in proposals], ["dup", "dup"])

    def test_non_list_fields_raise(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":"x","body":"b",'
            '"source_fragment_indices":"0","relations":{}}]'
        )
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_relation_objects_are_preserved_without_shape_validation(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[{"type":"relates_to"}]}]'
        )
        proposals = llm_output.parse(raw, PROJECTS)
        self.assertEqual(proposals[0].relations, ({"type": "relates_to"},))

    def test_dangling_relates_to_parses_for_later_resolution(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"b",'
            '"source_fragment_indices":[0],"relations":[{"type":"relates_to","target_title":"missing"}]}]'
        )
        proposals = llm_output.parse(raw, PROJECTS)
        self.assertEqual(proposals[0].relations, ({"type": "relates_to", "target_title": "missing"},))

    def test_relation_extra_fields_are_preserved(self):
        raw = (
            '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"body a",'
            '"source_fragment_indices":[0],"relations":[{"type":"mentions","entity":"MTK","extra":"x"}]},'
            '{"title":"b","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"body b",'
            '"source_fragment_indices":[1],"relations":[]}]'
        )
        proposals = llm_output.parse(raw, PROJECTS)
        self.assertEqual(
            proposals[0].relations,
            ({"type": "mentions", "entity": "MTK", "extra": "x"},),
        )


if __name__ == "__main__":
    unittest.main()
