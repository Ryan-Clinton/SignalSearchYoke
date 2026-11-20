"""The paired comparison of two ways of planting the same signals
(tools/injection_checks.py): equal totals must not hide signals found in
one and lost in the other."""
import unittest

import synth  # noqa: F401  (paths and a throwaway data folder)
import injection_checks as ic


def row(s_in, drift, ours, turbo):
    return {"s_in": s_in, "drift": drift, "ours_10": ours, "turboseti_10": turbo}


class Paired(unittest.TestCase):
    def test_equal_totals_with_swapped_signals_are_seen(self):
        a = [row(20, 0.1, True, False), row(20, 0.1, False, False), row(40, 1.5, True, True)]
        b = [row(20, 0.1, False, False), row(20, 0.1, True, False), row(40, 1.5, True, True)]
        p = ic.paired(a, b)
        self.assertEqual(p["all"]["ours_10"], {"both": 1, "first_only": 1, "second_only": 1, "neither": 0})
        self.assertEqual(p["all"]["turboseti_10"], {"both": 1, "first_only": 0, "second_only": 0, "neither": 2})
        self.assertEqual(ic._discordant(p), 1)
        self.assertEqual(p["by_strength"]["20"]["ours_10"]["first_only"], 1)
        self.assertEqual(p["by_drift"]["1.0-2.0"]["ours_10"]["both"], 1)

    def test_refuses_different_signals(self):
        with self.assertRaises(ValueError):
            ic.paired([row(20, 0.1, True, True)], [row(30, 0.1, True, True)])

    def test_drift_bins_cover_the_grid(self):
        self.assertEqual(ic._drift_bin(-0.05), "0.0-0.15")
        self.assertEqual(ic._drift_bin(4.0), "2.0-4.0")


if __name__ == "__main__":
    unittest.main()
