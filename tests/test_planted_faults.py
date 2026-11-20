"""The equivalence tests would notice a fault (docs/audits.md 25). A test that
a diagnostic copy gives what the frozen code gives proves nothing if its data
never reaches the code that could differ: so for each, a small fault is
planted in one side only and the same comparison must see it.

- the search's diagnostic copy (tools/search_variants.py): on data with hits
  near the cut, a strong one at extreme drift (the re-sum's reach, F9-01),
  close and drifting tones, it equals searching.search at its defaults, and
  every switch or threshold moved changes what it gives;
- the cadence test's version comparison (tests/test_onoff_equivalent.py, the
  basis of matched.ONOFF_EQUIVALENT): on its cadence, onoff.py with OFF_MAX
  or ON_MIN moved judges differently;
- the curved matcher's copy (tools/curved_checks.py): on its cadence with a
  tone accelerating between the published limit (1e-3 Hz/s^2) and 1e-2, the
  copy with the wider limit is no longer the published pass.
"""
import synth  # noqa: F401  (first: the tests' own data folder)

import itertools
import unittest
from unittest import mock

import numpy as np


class SearchCopy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import measure
        cad = synth.cadence(3)
        raw, cls.s = cad[0]["raw"], cad[0]["s"]
        sigma = float(np.median(cad[0]["sigma"]))
        tones = [(4000.3, 0.5, 40 * sigma / 4), (4010.7, -2.5, 30 * sigma / 4), (9000.1, 3.5, 25 * sigma / 4),
                 (12000.5, 0.0, 12 * sigma / 4)]
        tones += [(2000.4 + 300 * i, 0.0, k * sigma / 4) for i, k in enumerate((13.8, 14.4, 15.0, 15.6, 16.2))]
        tones += [(14000.2, -3.9, 300 * sigma / 4)]          # strong at extreme drift: the re-sum's reach
        cls.p = measure.plant(raw, tones, cls.s["tsamp"], cls.s["foff"])

    def run_copy(self, **kw):
        import search_variants as sv
        return sv.search_variant(self.p, self.s["foff"], self.s["tsamp"], self.s["fch1"], **kw)

    def test_the_data_reaches_the_cut(self):
        import searching
        hits = searching.search(self.p, self.s["foff"], self.s["tsamp"], self.s["fch1"])
        near = [h for h in hits if searching.SNR_MIN <= h["snr"] < searching.SNR_MIN + 1]
        self.assertGreaterEqual(len(near), 2, "no hits just over the cut: a fault at the cut would pass unseen")

    def test_defaults_match_and_every_planted_fault_is_seen(self):
        import searching
        base = searching.search(self.p, self.s["foff"], self.s["tsamp"], self.s["fch1"])
        self.assertEqual(self.run_copy(), base)
        faults = {"cut raised by 1": dict(snr_min=searching.SNR_MIN + 1),
                  "shadow floor raised by 1": dict(shadow_min=searching.SHADOW_MIN + 1),
                  "cap of 2": dict(max_hits=2), "no corridor": dict(corridor=False),
                  "shadow refresh": dict(refresh_shadow=True), "full re-sum reach": dict(refresh_reach="full"),
                  "exact sums": dict(exact=True), "half the drift range": dict(max_drift=searching.MAX_DRIFT / 2)}
        for name, kw in faults.items():
            self.assertNotEqual(self.run_copy(**kw), base, f"{name}: the comparison does not see it")


def _onoff_cadence():
    import matched
    planted = synth.judging_cadence(5)
    return planted, matched.our_search(planted)


def _plain(ev):
    return {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in ev.items()}


class CadenceComparison(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cad, cls.searched = _onoff_cadence()

    def events(self):
        import matched
        out = []
        for ons in itertools.combinations(range(6), 3):
            for cut in (10, 30):
                _, ev, _ = matched.our_events(self.cad, self.searched, ons, cut, [{} for _ in range(6)])
                out.append([_plain(e) for e in ev])
        return out

    def test_a_moved_threshold_is_seen(self):
        import onoff
        base = self.events()
        for name, value in (("OFF_MAX", onoff.OFF_MAX - 1.5), ("ON_MIN", onoff.ON_MIN + 3.0)):
            with mock.patch.object(onoff, name, value):
                self.assertNotEqual(self.events(), base, f"{name} moved: the version comparison does not see it")
        self.assertEqual(self.events(), base)                              # and put back, the same


class CurvedCopy(unittest.TestCase):
    def test_another_threshold_in_the_copy_is_seen(self):
        import curved_checks as cc
        import curved_pass
        import injection
        import matched
        cad = synth.cadence(5)
        for c in cad:
            c["s"]["coarse_channel"] = synth.N_F
        ts = injection.tones_for(cad, 8, 0, np.random.default_rng(7), strengths=[200])
        for k, t in enumerate(ts):
            t["accel"] = (8e-4, -8e-4, 2e-3)[k % 3]     # as test_curved_checks: the third past the limit 1e-3
        cad_p = [dict(c, spectra=p) for c, p in zip(cad, curved_pass.plant(cad, ts))]
        searched = matched.our_search(cad_p)
        same, seen = True, False
        for ons in itertools.combinations(range(6), 3):
            looks, events, _ = matched.our_events(cad_p, searched, ons, 10, [{} for _ in range(6)])
            published = curved_pass.second_pass(looks, events, 1e-3)
            same &= cc.first_wins(cc.second_pass_all(looks, events, 1e-3)) == published
            seen |= cc.first_wins(cc.second_pass_all(looks, events, 1e-2)) != published
        self.assertTrue(same)
        self.assertTrue(seen, "the copy at another threshold gives the published pass: the test cannot see it")


if __name__ == "__main__":
    unittest.main()
