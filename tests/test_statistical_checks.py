"""tools/statistical_checks.py's estimators."""
import sys
import unittest
from pathlib import Path

import numpy as np

import synth  # noqa: F401  (paths and a throwaway data folder)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import statistical_checks as sc  # noqa: E402


class Estimators(unittest.TestCase):
    def test_choose_cut_is_step_4s_rule(self):
        cuts = ["10", "20", "30", "50"]
        self.assertEqual(sc.choose_cut([0.5, 0.05, 0.2, 0.0], cuts), "50")     # a dip then a rise is not taken
        self.assertEqual(sc.choose_cut([0.5, 0.05, 0.08, 0.0], cuts), "20")
        self.assertIsNone(sc.choose_cut([0.5, 0.5, 0.5, 0.2], cuts))

    def test_weighted_share_weights_classes(self):
        idx = sc.class_index(["clean", "clean", "crowded"])
        found, n = np.array([10, 10, 0]), np.array([10, 10, 10])
        self.assertAlmostEqual(sc.weighted_share(found, n, idx, {"clean": 0.9, "crowded": 0.1}), 0.9)

    def test_lag_correlation_uses_block_numbers(self):
        blocks = list(range(0, 40, 2))                  # gaps: no block is 1 from another
        self.assertEqual(sc.lag_correlation(blocks, np.arange(20.0), 1)["pairs"], 0)
        self.assertGreater(sc.lag_correlation(blocks, np.arange(20.0), 2)["r"], 0.99)

    def test_pairing_matters(self):
        """Paired outcomes give a narrower difference interval than the same outcomes with the
        pairing broken: a resampler that dropped the pairing would show up here."""
        rng = np.random.default_rng(3)
        labels, fa, fb, n, w, *_ = sc.simulate(rng, block_sd=1.5)
        idx = sc.class_index(labels)
        paired = sc.boot_interval(lambda s: sc.weighted_share(fa, n, s, w) - sc.weighted_share(fb, n, s, w),
                                  idx, np.random.default_rng(1), 500)
        fb_broken = fb.copy()
        for ix in idx.values():
            fb_broken[ix] = fb[ix][np.random.default_rng(2).permutation(len(ix))]

        def broken(s):
            other = sc.resample(idx, np.random.default_rng(int(sum(v.sum() for v in s.values()))))
            return sc.weighted_share(fa, n, s, w) - sc.weighted_share(fb_broken, n, other, w)
        unpaired = sc.boot_interval(broken, idx, np.random.default_rng(1), 500)
        self.assertLess(paired[1] - paired[0], unpaired[1] - unpaired[0])

    def test_clustered_interval_covers_with_block_effects(self):
        cov = sc.coverage(trials=30, boot=150, seed=4, say=lambda *a: None)
        self.assertGreaterEqual(cov["a shared block effect"]["clustered_difference_coverage"], 0.8)
        self.assertLess(cov["a shared block effect"]["wilson_share_coverage"], 0.8)

    def test_wilson_and_clustered_on_the_same_estimand(self):
        """With independent signals and no block effect, the clustered interval on the pooled share is
        about as wide as Wilson's (they estimate the same thing)."""
        rng = np.random.default_rng(5)
        labels, fa, fb, n, w, *_ = sc.simulate(rng)
        idx = sc.class_index(labels)
        c = sc.boot_interval(lambda s: sc.pooled_share(fa, n, s), idx, np.random.default_rng(1), 800)
        lo, hi = sc.measure.wilson(int(fa.sum()), int(n.sum()))
        self.assertAlmostEqual((c[1] - c[0]) / (hi - lo), 1.0, delta=0.3)

    def test_windows_keep_classes_and_weights(self):
        blocks = list(range(16))
        classes = ["clean"] * 4 + ["crowded"] * 12
        g = sc.class_windows(blocks, classes, 4)
        self.assertEqual({c: len(v) for c, v in g.items()}, {"clean": 1, "crowded": 3})
        fa = np.array([10] * 4 + [0] * 12)
        fb = np.zeros(16, int)
        n = np.full(16, 10)
        r = sc.window_interval(blocks, classes, fa, fb, n, {"clean": 0.9, "crowded": 0.1}, 4,
                               np.random.default_rng(0), 50)
        self.assertEqual(r["interval"], [0.9, 0.9])          # weighted, not pooled (which would be 0.25)

    def test_zero_false_counts_give_no_interval(self):
        idx = ["clean"] * 3 + ["crowded"] * 3
        z = {"30": np.zeros(6, int)}
        f = {"30": np.full(6, 5)}
        out = sc._at("x", {"clean": 0.5, "crowded": 0.5}, list(range(6)), idx, np.full(6, 10),
                     {"ours": f, "turboseti": f}, {"ours": z, "turboseti": z}, "30", "30",
                     np.random.default_rng(0))
        self.assertIsNone(out["false_difference_interval"])


if __name__ == "__main__":
    unittest.main()
