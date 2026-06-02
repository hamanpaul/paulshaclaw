import unittest


class DreamIdleTest(unittest.TestCase):
    def test_is_idle_true(self):
        from paulshaclaw.memory.dream import idle
        self.assertTrue(idle.is_idle(max_load=1.0, probe=lambda: (0.2, 0.3, 0.4)))

    def test_is_idle_false(self):
        from paulshaclaw.memory.dream import idle
        self.assertFalse(idle.is_idle(max_load=1.0, probe=lambda: (3.0, 1.0, 1.0)))

    def test_probe_raises_oserror(self):
        from paulshaclaw.memory.dream import idle

        def bad_probe():
            raise OSError("no load")

        # fail-safe: if probe can't determine load, we consider system idle
        self.assertTrue(idle.is_idle(probe=bad_probe))


if __name__ == "__main__":
    unittest.main()
