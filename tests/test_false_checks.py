"""The mended combined interval of the false-candidate rate
(tools/false_checks.py): a class with no candidate keeps its own
uncertainty whether or not the other class has some."""
import unittest

import numpy as np

import synth  # noqa: F401  (paths and a throwaway data folder)
import false_checks as fc

W = {"clean": 61 / 64, "crowded": 3 / 64}


class Interval(unittest.TestCase):
    def test_published_drops_the_empty_class_when_the_other_has_one(self):
        rng = np.random.default_rng(0)
        counts = {"clean": [0] * 61, "crowded": [1, 0, 0]}
        _, (_, hi) = fc.published_interval(counts, W, rng, boot=2000)
        # the crowded class alone, bootstrapped: at most 1/3 of its weight
        self.assertLessEqual(hi, W["crowded"] * 1.0 + 1e-9)

    def test_mended_keeps_the_empty_class(self):
        rng = np.random.default_rng(0)
        counts = {"clean": [0] * 61, "crowded": [1, 0, 0]}
        _, (_, hi_mixed) = fc.mended_interval(counts, W, rng, boot=4000)
        _, (_, hi_pub) = fc.published_interval(counts, W, np.random.default_rng(0), boot=4000)
        self.assertGreater(hi_mixed, hi_pub)

    def test_an_empty_class_reaches_the_exact_poisson_limit(self):
        # Gamma(1, 1/n): its 97.5% point is -ln(0.025)/n = 3.689/n, the exact (Garwood) upper limit for 0 events.
        rng = np.random.default_rng(0)
        _, (_, hi) = fc.mended_interval({"clean": [0] * 100}, {"clean": 1.0}, rng, boot=20000)
        self.assertAlmostEqual(hi, 3.689 / 100, delta=0.003)

    def test_the_estimate_is_unchanged(self):
        counts = {"clean": [0, 2, 1], "crowded": [5, 0]}
        e1, _ = fc.mended_interval(counts, {"clean": 0.5, "crowded": 0.5}, np.random.default_rng(0), boot=200)
        e2, _ = fc.published_interval(counts, {"clean": 0.5, "crowded": 0.5}, np.random.default_rng(0), boot=200)
        self.assertAlmostEqual(e1, 0.5 * 1.0 + 0.5 * 2.5)
        self.assertAlmostEqual(e1, e2)


if __name__ == "__main__":
    unittest.main()
