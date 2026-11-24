"""The independent-injector comparison: its block rule and the difference it reads, with faults planted."""
import synth  # noqa: F401  (first: the tests' own data folder)

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import independent_injection as ii  # noqa: E402


def block(own, sg, n=10):
    """own, sg: (ours found, turboSETI found) of n signals."""
    tones = []
    for i in range(n):
        at = {c: {"own": {"ours": i < own[0], "turboseti": i < own[1]},
                  "setigen": {"ours": i < sg[0], "turboseti": i < sg[1]}} for c in ii.CUTS}
        tones.append({"bin": 0, "at": at})
    return {"tones": tones}


class Rule(unittest.TestCase):
    def test_the_draw_is_repeatable_and_by_class(self):
        classes = {b: ("crowded" if b % 3 == 0 else "clean") for b in range(60)}
        a, b = ii.choose(classes), ii.choose(classes)
        self.assertEqual(a, b)
        self.assertEqual(sorted(a.values()), ["clean"] * 8 + ["crowded"] * 8)

    def test_no_favour_when_the_advantage_is_the_same(self):
        got = ii.difference_of_advantages([block((8, 2), (8, 2))] * 12, "10")
        self.assertEqual(got["difference"], 0.0)
        self.assertLessEqual(got["interval"][0], 0)

    def test_favour_is_seen(self):
        got = ii.difference_of_advantages([block((9, 1), (5, 4))] * 12, "10")
        self.assertAlmostEqual(got["difference"], 0.7)
        self.assertGreater(got["interval"][0], 0)

    def test_an_injector_that_helps_turboseti_more_is_not_called_favour(self):
        got = ii.difference_of_advantages([block((8, 2), (9, 1))] * 12, "10")
        self.assertLess(got["difference"], 0)


if __name__ == "__main__":
    unittest.main()
