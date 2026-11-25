"""Mid-look scoring (A6-08): a fast signal measured with a small drift error is credited at the middle of the look
and not at its start; a signal in the wrong place is credited by neither."""
import synth  # noqa: F401  (first: the tests' own data folder)

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import midlook  # noqa: E402
import midlook as ml  # noqa: E402

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


class Records(unittest.TestCase):
    """record_problems: a block record is the matched block's whole result, or it is refused."""
    NONE = staticmethod(lambda pv, own=(): [])

    def pair(self):
        import matched
        want = {"class": "clean", "tones": [{"drift": 0.1 * i, "s_in": 30, "bin": i % 5,
                                             "ours": {c: {"three_looks": "recovered" if i % 2 else None}
                                                      for c in ml.CUTS}} for i in range(matched.TONES)]}
        rec = {"target": "T", "block": 7, "class": "clean", "published_reproduced": True,
               "tones": [{"drift": w["drift"], "s_in": 30, "bin": w["bin"],
                          "at": {c: {"published": w["ours"][c]["three_looks"], "mid": "recovered",
                                     "mid_scaled": "recovered"} for c in ml.CUTS}} for w in want["tones"]]}
        return rec, want

    def problems(self, rec, want, code=None):
        return ml.record_problems(rec, "T", 7, want, code or self.NONE)

    def test_a_whole_record_passes(self):
        self.assertEqual(self.problems(*self.pair()), [])

    def test_a_partial_record_is_refused(self):
        rec, want = self.pair()
        self.assertTrue(self.problems(dict(rec, tones=rec["tones"][:1]), want))

    def test_another_block_is_refused(self):
        rec, want = self.pair()
        self.assertTrue(self.problems(dict(rec, block=8), want))

    def test_unreproduced_or_other_published_statuses_are_refused(self):
        rec, want = self.pair()
        self.assertTrue(self.problems(dict(rec, published_reproduced=False), want))
        rec["tones"][0]["at"]["10"]["published"] = "recovered"
        self.assertTrue(self.problems(rec, want))

    def test_a_missing_scoring_is_refused(self):
        rec, want = self.pair()
        del rec["tones"][4]["at"]["30"]["mid_scaled"]
        self.assertTrue(self.problems(rec, want))

    def test_changed_code_is_refused(self):
        self.assertTrue(self.problems(*self.pair(), code=lambda pv, own=(): ["changed"]))


class TurboScoring(unittest.TestCase):
    """turbo_status at half 0 with the published tolerances is matched._status (turboSETI) and its hit check."""
    T_F = {0: 1400.0, 2: 1400.0 + 0.5e-3, 4: 1400.0 + 1.0e-3}

    def event(self, off_hz=0.0, drift=0.5):
        return {"members": [[j, None, f + off_hz / 1e6, drift] for j, f in self.T_F.items()]}

    def hits(self, off_hz=0.0, snr=20.0):
        return [[{"freq_mhz": self.T_F[j] + off_hz / 1e6, "drift_hz_s": 0.5, "snr": snr}] if j in self.T_F else []
                for j in range(6)]

    def published(self, kept, plain, hits, cut="10"):
        import matched
        st = matched._status(self.T_F, 0.5, kept, plain, turboseti=True)["three_looks"]
        on = matched._turbo_on_hits({"look_hits": hits}, self.T_F, 0.5, float(cut))
        return "recovered" if st == "recovered" and on == 3 else (None if st == "recovered" else st)

    def test_as_published_at_half_zero(self):
        import matched
        tol = (matched.TOL_HZ, matched.TOL_DRIFT)
        for kept, plain, hits in (([self.event()], [], self.hits()), ([self.event(5.0)], [], self.hits()),
                                  ([self.event(7.0)], [], self.hits()), ([self.event()], [self.event(1.0)], self.hits()),
                                  ([self.event()], [], self.hits(snr=5.0)), ([self.event()], [], self.hits(9.0))):
            self.assertEqual(ml.turbo_status(self.T_F, 0.5, kept, plain, hits, "10", 0.0, tol),
                             self.published(kept, plain, hits))


class Paired(unittest.TestCase):
    """paired: each session's difference in share between the pipelines, and its change from the published
    scoring, by block."""

    def rows(self):
        # 20 blocks of 10 signals: this search finds 6, 7, 8 under the three scorings, turboSETI 2, 2, 3
        return [{"signals": 10, "published": [6, 2], "mid": [7, 2], "mid_scaled": [8, 3]} for _ in range(20)]

    def test_the_differences_and_changes_are_the_shares(self):
        got = ml.paired(self.rows(), boot=200)
        self.assertEqual([got[k]["difference"] for k in ml.KEYS], [0.4, 0.5, 0.5])
        self.assertEqual(got["change_from_published"]["mid"]["difference"], 0.1)
        self.assertEqual(got["change_from_published"]["mid_scaled"]["difference"], 0.1)
        self.assertEqual(got["mid"]["interval"], [0.5, 0.5])          # every block alike: no spread

    def test_blocks_that_differ_give_an_interval_around_the_difference(self):
        rows = self.rows()
        for i in range(0, 20, 2):
            rows[i] = dict(rows[i], mid=[6, 2])                            # half the blocks gain nothing
        got = ml.paired(rows, boot=500)["change_from_published"]["mid"]
        self.assertAlmostEqual(got["difference"], 0.05)
        self.assertLess(got["interval"][0], 0.05)
        self.assertGreater(got["interval"][1], 0.05)
        self.assertGreaterEqual(got["interval"][0], 0.0)
