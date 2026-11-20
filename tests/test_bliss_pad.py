"""The general padding for BLISS (tools/bliss/pad.py) gives what
bliss_curves.padded gives on the 2017 layout, and handles others."""
import sys
import unittest
from pathlib import Path

import numpy as np

import synth  # noqa: F401  (paths and a throwaway data folder)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "bliss"))
from pad import pad_to_coarse  # noqa: E402

PER = 64


def published(x, first):
    """bliss_curves.padded's arithmetic on the 2017 layout (one channel short, offset 0 or 1)."""
    offset = first % PER
    assert x.shape[2] == PER - 1 and offset in (0, 1)
    return np.concatenate([x, x[:, :, -1:]] if offset == 0 else [x[:, :, :1], x], axis=2), offset


class Pad(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(0)

    def test_the_2017_layout_is_unchanged(self):
        for first in (0, 1, PER * 5, PER * 5 + 1):
            x = self.rng.normal(size=(16, 1, PER - 1))
            a, fa = published(x, first)
            b, fb = pad_to_coarse(x, first, PER)
            self.assertEqual(fa, fb)
            np.testing.assert_array_equal(a, b)

    def test_other_layouts(self):
        x = self.rng.normal(size=(16, 1, PER - 2))           # a channel off each side
        y, front = pad_to_coarse(x, PER * 3 + 1, PER)
        self.assertEqual((y.shape[2], front), (PER, 1))
        np.testing.assert_array_equal(y[:, :, 1:-1], x)
        z, front = pad_to_coarse(self.rng.normal(size=(16, 1, PER)), PER * 2, PER)   # a whole coarse channel
        self.assertEqual((z.shape[2], front), (PER, 0))

    def test_refuses_a_slice_past_its_coarse_channel(self):
        with self.assertRaises(ValueError):
            pad_to_coarse(self.rng.normal(size=(16, 1, PER)), 3, PER)


if __name__ == "__main__":
    unittest.main()
