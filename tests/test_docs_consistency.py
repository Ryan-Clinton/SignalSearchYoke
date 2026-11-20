"""The README states the versions the code holds (docs/audits.md 19)."""
import importlib.util
import re
import unittest

import synth  # noqa: F401  (paths and a throwaway data folder)
import vetting
import yoke


def _report_version():
    spec = importlib.util.spec_from_file_location("report_tool", str(yoke.ROOT / "tools" / "report.py"))
    text = spec.origin and open(spec.origin, encoding="utf-8").read()
    return re.search(r'^VERSION = "([^"]+)"', text, re.M).group(1)


class Readme(unittest.TestCase):
    def setUp(self):
        self.text = (yoke.ROOT / "README.md").read_text(encoding="utf-8")

    def test_report_version(self):
        self.assertIn(f"(version {_report_version()};", self.text)

    def test_checks_version(self):
        self.assertIn(f"checks version {vetting.VERSION.split()[0]}", self.text)

    def test_sessions(self):
        self.assertNotIn("both sessions", self.text)

    def test_bliss_named_as_the_report_names_it(self):
        self.assertNotIn("BLISS as published", self.text)


if __name__ == "__main__":
    unittest.main()
