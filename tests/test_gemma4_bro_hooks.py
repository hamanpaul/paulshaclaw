import importlib.util
import json
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "scripts" / "gemma4-hooks"

def _load(name):
    loader = SourceFileLoader(name, str(HOOKS / f"{name}.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    import sys as _sys; _sys.modules[name] = module
    loader.exec_module(module)
    return module

class BroInTests(unittest.TestCase):
    def setUp(self):
        self.bro_in = _load("bro_in")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)

    def test_bro_prompt_writes_user_id(self):
        self.bro_in.handle({"session_id": "s1", "prompt": "[bro:8313353234] 早安"}, self.state)
        data = json.loads((self.state / "s1.json").read_text(encoding="utf-8"))
        self.assertEqual(data["user_id"], 8313353234)

    def test_non_bro_prompt_clears_existing_statefile(self):
        (self.state / "s1.json").write_text('{"user_id": 1}', encoding="utf-8")
        self.bro_in.handle({"session_id": "s1", "prompt": "hello"}, self.state)
        self.assertFalse((self.state / "s1.json").exists())

    def test_missing_session_id_is_noop(self):
        self.bro_in.handle({"prompt": "[bro:1] hi"}, self.state)
        self.assertEqual(list(self.state.glob("*.json")), [])

if __name__ == "__main__":
    unittest.main()
