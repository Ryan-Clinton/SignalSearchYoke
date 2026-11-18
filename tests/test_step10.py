"""Step 10's frozen configuration: it parses, it names its session's six
files and its criteria, the code fingerprint is the same every time it is
taken, and a fingerprint that does not match is refused without a
deviation, with nothing written."""
import json
import unittest

import synth  # noqa: F401  (paths and a temporary SSY_DATA)

import independent
import yoke


class Step10(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.sha = independent.load()

    def test_config(self):
        for k in ("target", "session", "files", "criteria", "code"):
            self.assertIn(k, self.cfg)
        self.assertEqual(len(self.cfg["files"]), 6)
        self.assertEqual(len(self.sha), 64)
        self.assertEqual(json.loads(independent.CONFIG.read_text(encoding="utf-8")), self.cfg)

    def test_fingerprint_repeats_and_covers_the_files(self):
        a, b = independent.fingerprint(), independent.fingerprint()
        self.assertEqual(a, b)
        for f in independent.FILES:
            self.assertIn(f, a)
            self.assertIn(f, self.cfg["code"])

    def test_changed_code_refused(self):
        cfg = dict(self.cfg, code=dict(self.cfg["code"], **{"searching.py": "0" * 64}))
        with self.assertRaises(yoke.Refusal) as stop:
            independent.frozen(cfg)
        self.assertIn("searching.py", stop.exception.message)
        self.assertFalse((independent.ROOT / "deviations.json").exists())


if __name__ == "__main__":
    unittest.main()
