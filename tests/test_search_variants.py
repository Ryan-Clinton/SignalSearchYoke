"""The diagnostic copy of the search (tools/search_variants.py) gives exactly
what searching.search gives when its switches are at their defaults, so a
difference under a switch is the switch's alone."""
import math
import unittest

import numpy as np

import synth
import measure
import searching
import search_variants as sv


class SameAsProduction(unittest.TestCase):
    def test_defaults_match(self):
        cad = synth.cadence(3)
        raw = cad[0]["raw"]
        s = cad[0]["s"]
        sigma = float(np.median(cad[0]["sigma"]))
        tones = [(4000.3, 0.5, 40 * sigma / 4), (4010.7, -2.5, 30 * sigma / 4), (9000.1, 3.5, 25 * sigma / 4),
                 (12000.5, 0.0, 12 * sigma / 4)]
        p = measure.plant(raw, tones, s["tsamp"], s["foff"])
        a = searching.search(p, s["foff"], s["tsamp"], s["fch1"])
        b = sv.search_variant(p, s["foff"], s["tsamp"], s["fch1"])
        self.assertEqual(a, b)
        self.assertGreater(len(a), 3)

    def test_a_small_cap_matches_too(self):
        cad = synth.cadence(4)
        s, raw = cad[0]["s"], cad[0]["raw"]
        da, db = {}, {}
        a = searching.search(raw, s["foff"], s["tsamp"], s["fch1"], max_hits=3, details=da)
        b = sv.search_variant(raw, s["foff"], s["tsamp"], s["fch1"], max_hits=3, details=db)
        self.assertEqual(a, b)
        self.assertEqual(da["complete"], db["complete"])
        self.assertEqual(da["unpicked"], db["unpicked"])

    def test_a_region_cap_leaves_other_regions_searched(self):
        cad = synth.cadence(5)
        s, raw = cad[0]["s"], cad[0]["raw"]
        sigma = float(np.median(cad[0]["sigma"]))
        crowd = [(1000.0 + 40 * n + 0.3, 0.2, 50 * sigma / math.sqrt(16)) for n in range(30)]
        lone = [(12000.4, 0.3, 30 * sigma / math.sqrt(16))]
        p = measure.plant(raw, crowd + lone, s["tsamp"], s["foff"])
        f_lone = s["fch1"] + 12000.4 * s["foff"]

        def found(hits):
            return any(abs((h["frequency_mhz"] - f_lone) * 1e6) <= 6 for h in hits)
        glob = sv.search_variant(p, s["foff"], s["tsamp"], s["fch1"], max_hits=10)
        local = sv.search_variant(p, s["foff"], s["tsamp"], s["fch1"], region=(4096, 10))
        self.assertFalse(found(glob))          # the global cap is spent on the crowd
        self.assertTrue(found(local))          # a budget a region keeps the lone signal


if __name__ == "__main__":
    unittest.main()
