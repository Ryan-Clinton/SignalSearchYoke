"""Mid-look scoring (A6-08): a fast signal measured with a small drift error is credited at the middle of the look
and not at its start; a signal in the wrong place is credited by neither."""
import synth  # noqa: F401  (first: the tests' own data folder)

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import midlook  # noqa: E402

HALF = 146.0
F = {0: 1400.0, 2: 1400.001, 4: 1400.002}


def event(df_start_hz, drift):
    return {"members": [[j, 1, f + df_start_hz / 1e6, drift] for j, f in F.items()], "tracks": []}


class Scoring(unittest.TestCase):
    def test_a_fast_signal_with_a_small_drift_error(self):
        # true drift 3 Hz/s, measured 3.06 and right at the middle of the look: 0.06 x 146 = 8.8 Hz off at its start
        true, measured = 3.0, 3.06
        ev = event(-(measured - true) * HALF, measured)           # matches at mid-look, 8.8 Hz off at the start
        tone = {"drift": true}
        got = midlook.score(tone, F, [ev], [], HALF)
        self.assertIsNone(got["published"])
        self.assertEqual(got["mid"], None)                        # drift off by 0.06 > 0.05: the published drift test
        self.assertEqual(got["mid_scaled"], "recovered")          # 0.08 x 3 = 0.24 Hz/s allowed

    def test_within_the_drift_tolerance_mid_look_recovers(self):
        true, measured = 3.0, 3.04
        ev = event(-(measured - true) * HALF, measured)           # 5.84 Hz off at the start: just inside
        got = midlook.score({"drift": true}, F, [ev], [], HALF)
        self.assertEqual(got["mid"], "recovered")
        ev = event(-(measured - true) * 300, measured)            # off at the middle too
        self.assertIsNone(midlook.score({"drift": true}, F, [ev], [], HALF)["mid"])

    def test_the_wrong_place_is_credited_by_none(self):
        got = midlook.score({"drift": 1.0}, F, [event(80.0, 1.0)], [], HALF)
        self.assertEqual(set(got.values()), {None})

    def test_published_is_the_start(self):
        self.assertEqual(midlook.score({"drift": 0.5}, F, [event(2.0, 0.5)], [], HALF)["published"], "recovered")

    def test_already_in_the_block_is_not_recovered(self):
        ev = event(0.0, 0.5)
        self.assertEqual(midlook.score({"drift": 0.5}, F, [ev], [ev], HALF)["mid"], "false association")

    def test_tolerances_grow_only_past_the_published(self):
        self.assertEqual(midlook.tolerances(0.2, True), (6.0, 0.05))
        self.assertEqual(midlook.tolerances(-3.0, True), (30.0, 0.24))


if __name__ == "__main__":
    unittest.main()
