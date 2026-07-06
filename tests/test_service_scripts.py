from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


class ServiceScriptExtractionTests(unittest.TestCase):
    def test_service_scripts_exist_and_parse(self) -> None:
        for name in ("cost", "dream", "manager", "bot"):
            with self.subTest(name=name):
                script = SCRIPTS / f"service-{name}.sh"
                self.assertTrue(script.is_file(), script)
                self.assertTrue(os.access(script, os.X_OK), script)
                self.assertEqual(
                    subprocess.run(
                        ["bash", "-n", str(script)],
                        check=False,
                        capture_output=True,
                        text=True,
                    ).returncode,
                    0,
                )

    def test_start_sh_delegates_long_running_services_to_scripts(self) -> None:
        text = (SCRIPTS / "start.sh").read_text(encoding="utf-8")
        for name in ("cost", "dream", "manager", "bot"):
            self.assertIn(f"service-{name}.sh", text)


if __name__ == "__main__":
    unittest.main()
