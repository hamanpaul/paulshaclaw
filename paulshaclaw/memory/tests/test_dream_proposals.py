import unittest
import tempfile
from pathlib import Path

from paulshaclaw.memory.dream.proposals import (
    Proposal,
    append,
    pending,
    requires_approval,
)


class DreamProposalsTest(unittest.TestCase):
    def test_append_creates_file_and_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            prop = Proposal(
                proposal_id="p1",
                kind="merge",
                status="pending",
                created_ts=123456.0,
                subject_slice_ids=["s1", "s2"],
                detail="details",
                source="tests",
                config_hash="abc123",
            )
            path = append(tmp, prop)
            self.assertTrue(Path(path).exists())
            pend = pending(tmp)
            ids = [p["proposal_id"] for p in pend]
            self.assertIn("p1", ids)

    def test_requires_approval(self):
        self.assertTrue(requires_approval("merge"))
        self.assertTrue(requires_approval("supersede"))
        self.assertTrue(requires_approval("contradiction"))
        self.assertFalse(requires_approval("other"))


if __name__ == "__main__":
    unittest.main()
