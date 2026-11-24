"""The adoption rule of docs/control-c.md, on known cases with faults planted."""
import synth  # noqa: F401  (first: the tests' own data folder)

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import control_c_verdict as cv  # noqa: E402


def blocks(n, u5, u6, k=10, counted=110, cls="capped"):
    return [[u5, u6, k, counted]] * n, [cls] * n


class Rule(unittest.TestCase):
    def rows(self, capped=(2, 8), complete=(7, 8)):
        a, ca = blocks(16, *capped)
        b, cb = blocks(16, *complete, cls="complete")
        return np.array(a + b, float), np.array(ca + cb)

    def test_a_clear_gain_is_seen(self):
        rows, classes = self.rows()
        got = cv.paired_difference(rows, classes, only="capped")
        self.assertAlmostEqual(got["difference"], 0.6)
        self.assertGreater(got["interval"][0], 0)
        self.assertGreater(cv.paired_difference(rows, classes, w_capped=0.137)["interval"][0], 0)

    def test_no_gain_is_not_a_gain(self):
        rows, classes = self.rows(capped=(3, 3), complete=(7, 7))
        got = cv.paired_difference(rows, classes, only="capped")
        self.assertEqual(got["difference"], 0.0)
        self.assertFalse(cv.decide(got, got, {"rate": 0.0, "interval": [0, 0]})["adopted"])

    def test_a_noisy_gain_does_not_pass(self):
        rows = np.array([[0, 10, 10, 110], [5, 0, 10, 110]] * 8 + [[7, 7, 10, 110]] * 16, float)
        classes = np.array(["capped"] * 16 + ["complete"] * 16)
        got = cv.paired_difference(rows, classes, only="capped")
        self.assertLessEqual(got["interval"][0], 0)

    def test_interference_let_through_fails(self):
        gain = {"difference": 0.5, "interval": [0.3, 0.7]}
        self.assertTrue(cv.decide(gain, gain, {"rate": 0.01, "interval": [0.0, 0.03]})["adopted"])
        self.assertFalse(cv.decide(gain, gain, {"rate": 0.03, "interval": [0.0, 0.04]})["adopted"])
        self.assertFalse(cv.decide(gain, gain, {"rate": 0.01, "interval": [0.0, 0.08]})["adopted"])

    def test_the_rate_over_runs_of_blocks(self):
        bunched = [[0] * 300 + [12] + [0] * 7]
        got = cv.false_rate(bunched)
        self.assertEqual((got["unexplained"], got["blocks"]), (12, 308))
        self.assertGreater(got["interval"][1], got["rate"])


if __name__ == "__main__":
    unittest.main()
