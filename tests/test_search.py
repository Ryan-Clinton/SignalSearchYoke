"""The search on one synthetic look: a planted drifting tone is found where
and at the drift it was planted, pure noise gives no hit at the cut, and
the same input gives the same hits."""
import math
import unittest

import synth

import measure
import searching


def planted(look, x0, drift, s_in):
    raw, sigma = look["raw"], look["sigma"]
    h = s_in * sigma[int(x0)] / math.sqrt(raw.shape[0])
    return measure.plant(raw, [(x0, drift, h)], synth.TSAMP, synth.FOFF)


def search(spectra):
    return searching.search(spectra, synth.FOFF, synth.TSAMP, synth.FCH1)


class Search(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.look = synth.cadence(seed=1)[0]
        width_hz = abs(synth.FOFF) * 1e6
        cls.step = width_hz / ((synth.N_T - 1) * synth.TSAMP)

    def test_planted_tone_recovered(self):
        for drift in (0.0, 0.3, 1.5, -3.0):
            with self.subTest(drift=drift):
                hits = search(planted(self.look, 6000.3, drift, 60))
                hit = measure.matched(hits, 6000.3, drift, self.step, set())
                self.assertIsNotNone(hit, hits[:3])
                self.assertGreaterEqual(hit["snr"], searching.SNR_MIN)
                self.assertFalse(hit["shadow"])

    def test_noise_gives_no_hit_at_the_cut(self):
        hits = search(self.look["raw"])
        self.assertEqual([h for h in hits if not h["shadow"]], [])
        self.assertTrue(all(searching.SHADOW_MIN <= h["snr"] < searching.SNR_MIN for h in hits))

    def test_repeatable(self):
        spectra = planted(self.look, 9000.5, 0.7, 40)
        self.assertEqual(search(spectra), search(spectra))

    def test_stronger_is_brighter(self):
        snr = []
        for s_in in (30, 60, 120):
            hit = measure.matched(search(planted(self.look, 7000.5, 0.2, s_in)), 7000.5, 0.2, self.step, set())
            self.assertIsNotNone(hit)
            snr.append(hit["snr"])
        self.assertEqual(snr, sorted(snr))


if __name__ == "__main__":
    unittest.main()
