"""tools/coverage_checks.py: signals measured where they were planted, and a
candidate counted only when it holds the signal in every ON look."""
import sys
import unittest
from pathlib import Path

import synth

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import coverage_checks as cc  # noqa: E402
import matched  # noqa: E402


class Coverage(unittest.TestCase):
    def setUp(self):
        self.cad = [dict(c, spectra=c["raw"]) for c in synth.cadence(1)]
        self.t = {"x0": 5000.0, "drift": 0.3, "h": 1.0}

    def test_true_places(self):
        straight = [matched.where(self.cad, self.t, j)[0] for j in matched.TRUE]
        hop = [cc.true_x(self.cad, self.t, "a hop between looks", j) for j in matched.TRUE]
        per = abs(self.cad[0]["s"]["foff"] * 1e6)
        self.assertAlmostEqual(hop[0] - straight[0], 0.0)
        self.assertAlmostEqual(hop[2] - straight[2], 2 * cc.HOP_HZ / per)
        wide = cc.true_x(self.cad, self.t, "16 channels wide", matched.TRUE[0])
        self.assertAlmostEqual(wide - straight[0], 7.5)

    def _event(self, offsets):
        """A candidate with a hit in each ON look, `offsets` channels from the signal's true place."""
        members = []
        for j, off in zip(matched.TRUE, offsets):
            x = cc.true_x(self.cad, self.t, "continuous", j) + off
            members.append([j, 0, self.cad[j]["s"]["fch1"] + x * self.cad[j]["s"]["foff"], 0.3])
        return {"members": members}

    def test_only_a_candidate_holding_the_signal_counts(self):
        self.assertTrue(cc.associated([self._event([0, 1, -2])], self.cad, self.t, "continuous"))
        self.assertFalse(cc.associated([self._event([0, 1, 40])], self.cad, self.t, "continuous"))   # one look off
        near = self._event([0, 0, 0])
        near["members"] = near["members"][:2]                        # two ON looks only
        self.assertFalse(cc.associated([near], self.cad, self.t, "continuous"))
        unrelated = self._event([60, 60, 60])                        # within 200 Hz, not the signal
        self.assertFalse(cc.associated([unrelated], self.cad, self.t, "continuous"))


if __name__ == "__main__":
    unittest.main()
