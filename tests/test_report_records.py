"""tools/report.py refuses records that do not belong together (docs/audits.md 18)."""
import importlib.util
import sys
import unittest

import synth  # noqa: F401  (paths and a throwaway data folder)
import yoke

_spec = importlib.util.spec_from_file_location("report_tool", str(yoke.ROOT / "tools" / "report.py"))
rt = importlib.util.module_from_spec(_spec)
sys.modules["report_tool"] = rt
_spec.loader.exec_module(rt)


def good():
    b = {"target": "KIC8462852", "session": "AGBT17A_999_68"}
    s10 = {"target": "HIP17147", "session": "AGBT16A_999_192", "config_sha256": rt.FROZEN_CONFIG_SHA[10]}
    s12 = {"target": "NGC6946", "session": "AGBT19B_999_104", "config_sha256": rt.FROZEN_CONFIG_SHA[12]}
    ops = {"sessions": [{"target": t, "session": s} for t, s in rt.SESSIONS.items()]}
    return b, s10, s12, ops


class Records(unittest.TestCase):
    def test_the_right_records_pass(self):
        self.assertEqual(rt.record_problems(*good()), [])

    def test_mixed_records_refused(self):
        b, s10, s12, ops = good()
        self.assertTrue(rt.record_problems(dict(b, session="AGBT16A_999_192"), s10, s12, ops))
        self.assertTrue(rt.record_problems(b, dict(s10, config_sha256="0" * 64), s12, ops))
        self.assertTrue(rt.record_problems(b, s10, dict(s12, target="HIP17147"), ops))
        self.assertTrue(rt.record_problems(b, s10, s12, {"sessions": [{"target": "NGC6946", "session": "X"}]}))


if __name__ == "__main__":
    unittest.main()
