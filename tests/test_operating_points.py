"""The supplementary operating-point estimates (tools/operating_points.py):
the stratum weighting, the frequency windows and the bootstraps, on small
made-up samples whose answers are known."""
import unittest

import synth  # noqa: F401  (paths and a throwaway data folder)
import operating_points as op


def blk(block, cls, a, b, n):
    """n signals: a found by the first pipeline, b by the second (b <= a, the first finding every one b does)."""
    return {"block": block, "class": cls, "pairs": [(i < a, i < b) for i in range(n)]}


class Estimates(unittest.TestCase):
    def test_sample_difference(self):
        blocks = [blk(0, "clean", 8, 2, 10), blk(1, "crowded", 2, 0, 10)]
        self.assertAlmostEqual(op.sample_difference(blocks), (6 + 2) / 20)

    def test_weighted_follows_the_session_not_the_sample(self):
        # Half the sample crowded, but a tenth of the session: the weighted share leans to clean.
        blocks = [blk(0, "clean", 8, 2, 10), blk(1, "crowded", 2, 0, 10)]
        a, b, d = op.weighted(blocks, {"clean": 0.9, "crowded": 0.1})
        self.assertAlmostEqual(a, 0.9 * 0.8 + 0.1 * 0.2)
        self.assertAlmostEqual(b, 0.9 * 0.2)
        self.assertAlmostEqual(d, 0.9 * 0.6 + 0.1 * 0.2)
        self.assertNotAlmostEqual(d, op.sample_difference(blocks))

    def test_weighted_equals_sample_when_the_sample_is_the_session(self):
        blocks = [blk(i, "clean", 5, 1, 10) for i in range(9)] + [blk(9, "crowded", 1, 0, 10)]
        self.assertAlmostEqual(op.weighted(blocks, {"clean": 0.9, "crowded": 0.1})[2], op.sample_difference(blocks))

    def test_an_absent_class_is_not_stretched_over(self):
        blocks = [blk(0, "clean", 10, 0, 10)]
        self.assertAlmostEqual(op.weighted(blocks, {"clean": 0.5, "crowded": 0.5})[2], 0.5)
        self.assertEqual(op.bootstrap_weighted(blocks, {"clean": 0.5, "crowded": 0.5}, boot=50)["classes_absent"],
                         ["crowded"])

    def test_windows_are_by_block_number_with_gaps_kept(self):
        # Measured blocks 0, 1, 7, 8, 9: windows of 4 are {0,1}, {7}, {8,9}, not two runs of the sorted sample.
        blocks = [blk(k, "clean", 1, 0, 2) for k in (0, 1, 7, 8, 9)]
        got = [[b["block"] for b in w] for w in op.windows(blocks, 4)]
        self.assertEqual(got, [[0, 1], [7], [8, 9]])

    def test_few_windows_are_marked(self):
        blocks = [blk(k, "clean", 1, 0, 2) for k in range(32)]
        self.assertTrue(op.bootstrap_sample(blocks, 16, boot=50)["few_windows"])
        self.assertFalse(op.bootstrap_sample(blocks, 1, boot=50)["few_windows"])

    def test_the_interval_holds_the_estimate(self):
        blocks = [blk(k, "clean" if k % 2 else "crowded", 6 + k % 3, 1, 10) for k in range(40)]
        s = op.bootstrap_sample(blocks, 1, boot=400)
        self.assertLessEqual(s["interval"][0], s["difference"])
        self.assertLessEqual(s["difference"], s["interval"][1])
        w = op.bootstrap_weighted(blocks, {"clean": 0.7, "crowded": 0.3}, boot=400)
        self.assertLessEqual(w["interval"][0], w["difference"])
        self.assertLessEqual(w["difference"], w["interval"][1])


if __name__ == "__main__":
    unittest.main()
