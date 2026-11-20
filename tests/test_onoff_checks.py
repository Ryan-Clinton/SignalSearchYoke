"""tools/onoff_checks.py: what the frozen cadence test does with an OFF look it
cannot measure, and the asymmetry of its matching distance."""
import sys
import unittest
from pathlib import Path

import synth  # noqa: F401  (paths and a throwaway data folder)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import onoff_checks as oc  # noqa: E402


class Cadence(unittest.TestCase):
    def test_unmeasured_off_counted(self):
        def ev(label, offs):
            return {"label": label, "looks": [{"on": True, "found": True}] + offs}
        blind = {"on": False, "found": False, "track_snr": None, "track_snr_fixed": None}
        seen = {"on": False, "found": False, "track_snr": 1.2, "track_snr_fixed": 0.3}
        events = [ev("candidate", [blind, blind, blind]), ev("candidate", [blind, seen, seen]),
                  ev("candidate", [seen, seen, seen]), ev("interference", [blind, blind, blind])]
        self.assertEqual(oc.unmeasured(events),
                         {"candidates": 3, "some_off_unmeasured": 2, "every_off_unmeasured": 1})

    def test_the_distance_is_not_symmetric(self):
        r = oc.example()
        self.assertLessEqual(r["forward"], 1)
        self.assertGreater(r["backward"], 1)

    def test_an_unmeasurable_off_look_passes_a_candidate_end_to_end(self):
        """A tone in the three ON looks and one OFF look with no spread (best_track has nothing to
        measure): onoff.judge calls it a candidate, and unmeasured() names the blind OFF look."""
        import math
        import matched
        import measure
        import numpy as np
        cad = synth.cadence(6)
        sigma = float(np.median(cad[0]["sigma"]))
        looks_in = []
        for j, c in enumerate(cad):
            raw = c["raw"]
            if j in (0, 2, 4):
                raw = measure.plant(raw, [(7000.0, 0.0, 60 * sigma / math.sqrt(raw.shape[0]))], c["s"]["tsamp"],
                                    c["s"]["foff"])
            if j == 3:
                raw = np.full_like(raw, float(np.median(raw)))      # an OFF look with nothing to measure
            looks_in.append(dict(c, raw=raw, spectra=raw, s=dict(c["s"], spectra=raw)))
        looks, events, _ = matched.our_events(looks_in, matched.our_search(looks_in), matched.TRUE, 10,
                                              [{} for _ in range(6)])
        tone = [e for e in events if abs(e["frequency_mhz"] - (looks[0].fch1 + 7000 * looks[0].foff)) < 1e-4]
        self.assertTrue(tone)
        self.assertEqual(tone[0]["label"], "candidate")
        self.assertEqual(oc.unmeasured(tone)["some_off_unmeasured"], 1)

    def test_backward_only_pairs_are_counted(self):
        """A pair within distance 1 only backward is screened in and counted (onoff._close screens on
        the forward distance alone)."""
        from types import SimpleNamespace
        width = 2.7939677238464355
        step = width / (15 * 18.253611008)

        def look(t, hits):
            return SimpleNamespace(tstart=60000.0 + t / 86400, width_hz=width, step=step, hits=hits, on=True)
        a = {"frequency_mhz": 1500.0, "drift_hz_s": 3.6141}
        found = None
        for off in range(-300, 301):
            b = {"frequency_mhz": 1500.0 + (3.4372 * 1320 + off) / 1e6, "drift_hz_s": 3.4372}
            la, lb = look(0, [a]), look(1320, [b])
            if oc.onoff.distance(a, b, la, lb) > 1 >= oc.onoff.distance(b, a, lb, la):
                found = (la, lb)
                break
        self.assertIsNotNone(found)
        r = oc.asymmetry(list(found))
        self.assertEqual((r["backward_only"], r["forward_only"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
