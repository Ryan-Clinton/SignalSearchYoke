"""tools/curved_checks.py's diagnostic matcher: deduplicated first-wins it is
curved_pass.second_pass exactly; and its helpers."""
import itertools
import sys
import unittest
from pathlib import Path

import numpy as np

import synth

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import curved_checks as cc  # noqa: E402


class Matcher(unittest.TestCase):
    def test_first_wins_is_second_pass(self):
        import curved_pass
        import matched
        cad = synth.cadence(5)
        for c in cad:
            c["s"]["coarse_channel"] = synth.N_F         # planting asks for the coarse channel's size
        import injection
        ts = injection.tones_for(cad, 8, 0, np.random.default_rng(7), strengths=[200])
        for k, t in enumerate(ts):
            # curved enough that straight lines miss them; the third past the limit 1e-3, so the limit is used
            # (tests/test_planted_faults.py: with another limit the copy differs here)
            t["accel"] = (8e-4, -8e-4, 2e-3)[k % 3]
        cad_p = [dict(c, spectra=p) for c, p in zip(cad, curved_pass.plant(cad, ts))]
        searched = matched.our_search(cad_p)
        checked = hyps_seen = 0
        for ons in itertools.combinations(range(6), 3):
            looks, events, _ = matched.our_events(cad_p, searched, ons, 10, [{} for _ in range(6)])
            published = curved_pass.second_pass(looks, events, 1e-3)
            hyps = cc.second_pass_all(looks, events, 1e-3)
            self.assertEqual(cc.first_wins(hyps), published, ons)
            checked += len(published)
            hyps_seen += len(hyps)
        self.assertGreater(checked, 0)
        self.assertGreaterEqual(hyps_seen, checked)

    def test_the_same_hits_give_fits_with_other_off_measurements(self):
        """CD-01's mechanism end to end: on the true choice the same three ON hits, reached from two
        pairs of ON looks, give two fitted accelerations and different OFF measurements, and the
        published matcher keeps only the first."""
        import curved_pass
        import injection
        import matched
        cad = synth.cadence(5)
        for c in cad:
            c["s"]["coarse_channel"] = synth.N_F
        ts = injection.tones_for(cad, 8, 0, np.random.default_rng(7), strengths=[200])
        for k, t in enumerate(ts):
            t["accel"] = (8e-4, -8e-4, 5e-4, -5e-4)[k % 4]
        cad_p = [dict(c, spectra=p) for c, p in zip(cad, curved_pass.plant(cad, ts))]
        looks, events, _ = matched.our_events(cad_p, matched.our_search(cad_p), matched.TRUE, 10,
                                              [{} for _ in range(6)])
        hyps = cc.second_pass_all(looks, events, 1e-3)
        by = {}
        for h in hyps:
            by.setdefault(h["sig"], []).append(h)
        multi = [v for v in by.values() if len(v) > 1 and len({h["a"] for h in v}) > 1]
        self.assertTrue(multi)
        self.assertTrue(any(len({tuple(h["offs"]) for h in v}) > 1 for v in multi))
        kept = cc.first_wins(hyps)
        self.assertEqual(len(kept), len(by))

    def test_helpers(self):
        def h(sig, label, measured):
            return {"sig": frozenset(sig), "label": label, "off_measured": measured, "off_looks": 3,
                    "members": dict(sig), "track": None, "offs": [], "a": 0.0}
        hyps = [h({(0, 1), (2, 1)}, "interference", 3), h({(0, 1), (2, 1)}, "candidate", 3),
                h({(0, 2), (4, 2)}, "candidate", 0)]
        self.assertEqual([e["label"] for e in cc.first_wins(hyps)], ["interference", "candidate"])
        self.assertEqual(sorted(e["label"] for e in cc.any_candidate(hyps)), ["candidate", "candidate"])
        self.assertEqual([e["label"] for e in cc.measured_only(hyps)], ["interference", "unmeasured"])
        hyps[1]["off_measured"] = 2
        self.assertEqual([e["label"] for e in cc.measured_at_least(3)([hyps[1]])], ["unmeasured"])
        self.assertEqual([e["label"] for e in cc.measured_at_least(2)([hyps[1]])], ["candidate"])
        st = cc.order_stats(hyps)
        self.assertEqual((st["sets_disagreeing"], st["first_is_interference_another_candidate"],
                          st["candidates_no_off_measured"]), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
