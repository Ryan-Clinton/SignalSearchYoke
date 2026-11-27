"""The report's checks of control C's records refuse what is not the one
experiment its protocol describes: other sessions or control B's, another
planting, different candidates under the two versions, a verdict that does
not follow from its own measures, a replay that differed."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import report  # noqa: E402

C = ROOT / "data" / "analysis" / "negative_controls_c"
B = ROOT / "data" / "analysis" / "negative_controls"


@unittest.skipUnless((C / "verdict.json").exists() and (B / "tables.json").exists(), "control C's records are not here")
class ControlCProblems(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load = lambda d, p: json.loads((d / p).read_text(encoding="utf-8"))  # noqa: E731
        cls.args = [load(C, p) for p in ("tables.json", "summary.json", "injection.json", "verdict.json",
                                         "package_replay.json", "checks_context.json")] + [load(B, "tables.json")]

    def problems(self, change=None):
        args = copy.deepcopy(self.args)
        if change:
            change(*args)
        return report.control_c_problems(*args)

    def test_the_records_as_made_pass(self):
        self.assertEqual(self.problems(), [])

    def test_a_session_twice_or_control_bs_is_refused(self):
        self.assertTrue(self.problems(lambda t, *_: t["sessions"][1].update(session=t["sessions"][0]["session"])))
        self.assertTrue(self.problems(lambda t, *a: t["sessions"][0].update(session=a[-1]["sessions"][0]["session"])))

    def test_another_planting_is_refused(self):
        self.assertTrue(self.problems(lambda t, s, i, *_: i.update(signals=3410)))

    def test_different_candidates_under_the_two_versions_are_refused(self):
        self.assertTrue(self.problems(
            lambda t, s, i, *_: i["cuts_bands_as_context"]["30"]["capped"].update(candidates=1)))
        self.assertTrue(self.problems(
            lambda t, s, i, v, r, x, b: x["bands_as_context"]["all four"]["at_10"].update(candidates=1)))

    def test_a_verdict_that_does_not_follow_from_its_measures_is_refused(self):
        def flip(t, s, i, v, *_):
            v["planted_capped"]["interval"][0] = -0.01
        self.assertTrue(self.problems(flip))
        self.assertTrue(self.problems(lambda t, s, i, v, *_: v.update(adopted=not v["adopted"])))

    def test_a_replay_that_differed_is_refused(self):
        self.assertTrue(self.problems(lambda t, s, i, v, r, *_: r.update(summary_same=False)))

    def test_the_summary_sentence_takes_its_counts_from_the_records(self):
        t, s, i, v = copy.deepcopy(self.args[:4])
        v["real_unexplained_by_version_6"]["unexplained"] = 3
        self.assertIn("left three real candidates unexplained", report.control_c_summary(s, v))
        s["groups"]["all four"]["at_30"]["unexplained"] = 2
        self.assertIn("2 left unexplained by the checks in force", report.control_c_summary(s, v))


if __name__ == "__main__":
    unittest.main()
