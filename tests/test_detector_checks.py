"""The core detector's behaviours found in docs/audits.md 9, pinned down so a
new detector version can be checked against them (searching.py itself is
frozen and not changed)."""
import sys
import unittest
from pathlib import Path

import numpy as np

import synth  # noqa: F401  (paths and a throwaway data folder)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import detector_checks as dc  # noqa: E402
import search_variants as sv  # noqa: E402
import searching  # noqa: E402


class Detector(unittest.TestCase):
    def test_the_published_refresh_leaves_a_stale_pick_beside_a_strong_tone(self):
        rng = np.random.default_rng(9)
        x = dc._tone(dc._noise(16, 16384, rng), 16, 8000, 2.0, 400.0)
        a = sv.search_variant(x, dc.FOFF, dc.TSAMP, dc.FCH1, exact=True)
        b = sv.search_variant(x, dc.FOFF, dc.TSAMP, dc.FCH1, exact=True, refresh_reach="full")
        self.assertEqual([h["snr"] for h in a], [h["snr"] for h in searching.search(x, dc.FOFF, dc.TSAMP, dc.FCH1)])
        self.assertGreater(sum(h["snr"] >= 10 for h in a), sum(h["snr"] >= 10 for h in b))

    def test_one_nan_empties_the_search(self):
        r = dc.nonfinite(np.random.default_rng(9))
        self.assertTrue(r["tone_found_clean"])
        self.assertFalse(r["tone_found_with_one_nan"])

    def test_rounding_flips(self):
        hits = [{"snr": 10.0, "snr_exact": 9.96}, {"snr": 10.0, "snr_exact": 10.01}, {"snr": 30.0, "snr_exact": 29.95}]
        flips = dc.rounding_flips(hits, cuts=(10, 30))
        self.assertEqual(flips, {"10": 1, "30": 1})


if __name__ == "__main__":
    unittest.main()
