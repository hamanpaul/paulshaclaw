import unittest
from pathlib import Path
from unittest import mock


class TestWakeupCLI(unittest.TestCase):
    def test_explicit_project_prints_brief(self):
        # When --project is provided, run should call build_brief and print its result
        import paulshaclaw.memory.wakeup.cli as cli

        args = mock.Mock()
        args.memory_root = '/fake/root'
        args.project = 'myproj'
        args.cwd = None
        args.k = 3
        args.char_budget = 100
        args.now = None

        with mock.patch('paulshaclaw.memory.wakeup.cli.build_brief', return_value='BRIEF') as bb:
            with mock.patch('builtins.print') as p:
                rc = cli.run(args)
                bb.assert_called_once()
                p.assert_called_once_with('BRIEF')
                self.assertEqual(rc, 0)

    def test_unknown_project_prints_nothing(self):
        # When project is unknown and build_brief returns empty, nothing is printed
        import paulshaclaw.memory.wakeup.cli as cli

        args = mock.Mock()
        args.memory_root = '/fake/root'
        args.project = None
        args.cwd = None
        args.k = 1
        args.char_budget = 50
        args.now = None

        with mock.patch('paulshaclaw.memory.wakeup.cli.resolve_project', return_value='_unknown'):
            with mock.patch('paulshaclaw.memory.wakeup.cli.build_brief', return_value='') as bb:
                with mock.patch('builtins.print') as p:
                    rc = cli.run(args)
                    bb.assert_called_once()
                    p.assert_not_called()
                    self.assertEqual(rc, 0)


if __name__ == '__main__':
    unittest.main()
