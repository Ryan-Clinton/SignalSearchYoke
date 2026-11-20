"""The turboSETI comparison checks (tools/turbo_checks.py) that run without
turboSETI: the order its hits are numbered in, the verdict on an event's
members, and where a lost signal is put."""
import unittest

import synth  # noqa: F401  (paths and a throwaway data folder)
import turbo_checks as tc

F = {0: 2000.0, 2: 2000.0, 4: 2000.0}       # a signal's frequency (MHz) in each true ON look, turboSETI's reference
WINDOW = 2300.0


def hit(f_off_hz, drift, snr, num, look=None):
    h = {"freq_mhz": 2000.0 + f_off_hz / 1e6, "drift_hz_s": drift, "snr": snr, "top_hit_num": num}
    if look is not None:
        h["look"] = look
    return h


class Numbering(unittest.TestCase):
    def test_channel_order_follows_the_sign_of_foff(self):
        hs = [{"freq_mhz": 1.0, "snr": 9}, {"freq_mhz": 3.0, "snr": 5}, {"freq_mhz": 2.0, "snr": 7}]
        self.assertEqual([h["freq_mhz"] for h in tc.turbo_order(hs, foff=-2.79e-6)], [3.0, 2.0, 1.0])
        self.assertEqual([h["freq_mhz"] for h in tc.turbo_order(hs, foff=2.79e-6)], [1.0, 2.0, 3.0])


class Members(unittest.TestCase):
    def rows(self, nums):
        """One event (Hit_ID 1) with a row in each look given."""
        return [dict(hit(0.0, 0.5, 40, n, look=j), hit_id="1") for j, n in nums.items()]

    def test_verified_disagrees_and_unknown_are_kept_apart(self):
        hits = [[hit(0.0, 0.5, 40, 7)], [], [hit(0.0, 0.5, 40, 3)], [], [hit(0.0, 0.5, 40, 9)], []]
        got = tc.members(F, 0.5, hits, self.rows({0: 7, 2: 4}), cut=10)
        self.assertEqual(got, {"0": "verified", "2": "disagrees", "4": "unknown"})

    def test_a_missing_row_is_never_verified(self):
        hits = [[hit(0.0, 0.5, 40, 1)], [], [hit(0.0, 0.5, 40, 1)], [], [hit(0.0, 0.5, 40, 1)], []]
        self.assertEqual(set(tc.members(F, 0.5, hits, [], cut=10).values()), {"unknown"})


class Stages(unittest.TestCase):
    def test_each_cause(self):
        none = {"three_looks": None}
        empty = [[] for _ in range(6)]
        self.assertEqual(tc.stage(F, 0.5, empty, False, none, 10, WINDOW), "no hit at SNR 5")
        far = [[hit(900.0, 0.5, 40, 1)], [], [hit(0, 0.5, 40, 1)], [], [hit(0, 0.5, 40, 1)], []]
        self.assertTrue(tc.stage(F, 0.5, far, False, none, 10, WINDOW).startswith("another hit in the top-hit window"))
        off = [[hit(20.0, 0.6, 40, 1)], [], [hit(0, 0.5, 40, 1)], [], [hit(0, 0.5, 40, 1)], []]
        self.assertEqual(tc.stage(F, 0.5, off, False, none, 10, WINDOW), "found at SNR 5, measured outside the tolerances")
        weak = [[hit(0, 0.5, 8, 1)], [], [hit(0, 0.5, 40, 1)], [], [hit(0, 0.5, 40, 1)], []]
        self.assertEqual(tc.stage(F, 0.5, weak, False, none, 10, WINDOW), "a matching hit only at or under the cut")
        strong = [[hit(0, 0.5, 40, 1)], [], [hit(0, 0.5, 40, 1)], [], [hit(0, 0.5, 40, 1)], []]
        vetoed = [strong[0], [hit(500.0, 0.0, 30, 2)], strong[2], [], strong[4], []]
        self.assertTrue(tc.stage(F, 0.5, vetoed, False, none, 10, WINDOW).startswith("an OFF hit over the cut"))
        self.assertEqual(tc.stage(F, 0.5, strong, False, none, 10, WINDOW), "hits over the cut in each ON look, no event")
        self.assertIsNone(tc.stage(F, 0.5, strong, True, {"three_looks": "recovered"}, 10, WINDOW))


class Tolerances(unittest.TestCase):
    def test_scaled_tolerances_grow_with_drift_and_are_put_back(self):
        import matched
        before = (matched.TOL_HZ, matched.TOL_DRIFT)
        with tc.scaled_tolerances(3.0):
            self.assertEqual((matched.TOL_HZ, matched.TOL_DRIFT), (30.0, 0.24))
        with tc.scaled_tolerances(0.1):
            self.assertEqual((matched.TOL_HZ, matched.TOL_DRIFT), before)
        self.assertEqual((matched.TOL_HZ, matched.TOL_DRIFT), before)


if __name__ == "__main__":
    unittest.main()
