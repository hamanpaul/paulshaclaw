import unittest
import tempfile
from pathlib import Path

from paulshaclaw.memory.dream import proposals


class DreamProposalsTest(unittest.TestCase):
    def test_pending_and_requires(self):
        with tempfile.TemporaryDirectory() as tmp:
            prop = proposals.Proposal(
                proposal_id="p1",
                kind="merge",
                status="pending",
                created_ts="2026-06-02T00:00:00Z",
                subject_slice_ids=["s1", "s2"],
                detail={},
                source="tests",
                config_hash="abc123",
            )
            ret = proposals.append(Path(tmp), prop)
            # append should return None per plan
            self.assertIsNone(ret)
            pend = proposals.pending(Path(tmp))
            self.assertEqual(len(pend), 1)
            p = pend[0]
            self.assertEqual(p["proposal_id"], "p1")
            self.assertEqual(p["created_ts"], "2026-06-02T00:00:00Z")
            self.assertEqual(p["detail"], {})

        # approval kinds
        self.assertTrue(proposals.requires_approval("merge"))
        self.assertTrue(proposals.requires_approval("supersede"))
        self.assertTrue(proposals.requires_approval("contradiction"))


if __name__ == "__main__":
    unittest.main()
