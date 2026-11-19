"""The planting of signals (measure.plant), checked against what it should
do rather than against the detector: its power, its convergence in the
sub-steps it is sampled at, the direction of a drift when the band runs
downward, and what blanking the DC bin does to a signal there."""
import math
import unittest

import numpy as np

import synth  # noqa: F401  (paths and a throwaway data folder)
import measure
import seti

FOFF = -2.7939677238464355e-06      # MHz a channel, the band running downward as Green Bank's does
TSAMP = 18.253611008


def plant(x0, drift, h=1.0, n_f=1200, substeps=measure.SUBSTEPS, n_t=16):
    return measure.plant(np.zeros((n_t, n_f)), [(x0, drift, h)], TSAMP, FOFF, substeps=substeps)


class Planting(unittest.TestCase):
    def test_power_is_h_less_the_far_sidelobes(self):
        # sinc^2 sums to 1 over all channels; 4 either side keep about 98% of it.
        for frac in (0.0, 0.25, 0.5):
            for drift in (0.0, 0.5, 4.0):
                per = plant(1000 + frac, drift).sum(axis=1)
                self.assertTrue(np.all((per > 0.95) & (per <= 1.0 + 1e-9)), (frac, drift, per.min(), per.max()))

    def test_converges_in_the_substeps(self):
        for drift in (0.15, 1.0, 4.0):
            ref = plant(1000.3, drift, substeps=256)
            for k in (32, 51, 128):
                p = plant(1000.3, drift, substeps=k)
                self.assertAlmostEqual(p.sum() / ref.sum(), 1.0, delta=1e-3)
                # the largest single-channel difference shrinks as the sub-steps grow
            d = [np.abs(plant(1000.3, drift, substeps=k) - ref).max() for k in (32, 51, 128)]
            self.assertTrue(d[0] >= d[1] >= d[2], (drift, d))

    def test_a_positive_drift_moves_to_lower_channels_when_the_band_runs_down(self):
        # Frequency rises with a positive drift; with foff < 0 that is towards channel 0.
        p = plant(1000.0, 1.0, n_t=16)
        centroid = [(row * np.arange(row.size)).sum() / row.sum() for row in p]
        self.assertLess(centroid[-1], centroid[0])
        moved = (centroid[0] - centroid[-1]) * abs(FOFF) * 1e6
        self.assertAlmostEqual(moved, 1.0 * 15 * TSAMP, delta=0.05 * 15 * TSAMP)

    def test_blanking_after_planting_takes_a_signal_off_the_dc_bin(self):
        # A slow signal sitting on the DC bin loses most of its power there when blanked after planting
        # (as the sky would be), and keeps it when planted after the blanking (as the experiments plant).
        per, n_f = 256, 512
        dc = per // 2
        raw = np.ones((16, n_f))
        real = measure.plant(raw, [(dc, 0.0, 10.0)], TSAMP, FOFF)
        seti.blank_dc(real, 0, per)
        blanked = raw.copy()
        seti.blank_dc(blanked, 0, per)
        in_use = measure.plant(blanked, [(dc, 0.0, 10.0)], TSAMP, FOFF)
        self.assertLess(real[:, dc].mean() - 1, 0.2 * (in_use[:, dc].mean() - 1))
        self.assertAlmostEqual(in_use[:, dc].mean() - 1, 10.0 * np.sinc(0.0) ** 2, delta=0.5)
        self.assertTrue(math.isclose(real[:, dc + 5].mean(), in_use[:, dc + 5].mean(), rel_tol=1e-9))


if __name__ == "__main__":
    unittest.main()
