"""Code kept identical to another version of itself: BLISS's event stage
ported line for line against its array version (as bliss_curves.py's
selftest, without BLISS), and check 8 before and after its lookups were
indexed (as tools/check8_equivalence.py, on hand-made hits, no store)."""
import unittest

import numpy as np

import synth  # noqa: F401  (paths and a temporary SSY_DATA)

import bliss_events
import check8_equivalence as check8


def random_cadence(rng):
    """Six looks of hits crowded around a few frequencies (bliss_curves._random_cadence)."""
    looks = []
    centres = rng.uniform(1000, 1001, rng.integers(1, 6))
    for j in range(6):
        hs = [{"start_freq_MHz": float(rng.choice(centres) + rng.normal(0, 2e-5)),
               "drift_rate_Hz_per_sec": float(rng.choice([rng.uniform(-4, 4), 0.0, 0.5])),
               "snr": float(rng.uniform(5, 50)), "power": float(rng.uniform(1, 1e9)),
               "bandwidth": float(rng.uniform(1, 30)), "start_time_sec": 300.0 * j,
               "duration_sec": 292.0, "_look": j} for _ in range(int(rng.integers(0, 40)))]
        looks.append((57000 + j * 300 / 86400, 292.0, hs))
    return looks


def key(events):
    return [[(h["_look"], h["start_freq_MHz"], h["drift_rate_Hz_per_sec"], h["snr"]) for h in e["hits"]]
            for e in events]


class BlissEvents(unittest.TestCase):
    def test_array_version_identical(self):
        rng = np.random.default_rng(11)
        events = 0
        for _ in range(60):
            looks = random_cadence(rng)
            for ons in [(0, 2, 4), tuple(sorted(rng.choice(6, 3, replace=False)))]:
                on = [looks[j] for j in ons]
                off = [looks[j][2] for j in range(6) if j not in ons]
                for offs in (off, [[], [], []]):          # with the OFF veto, and the matching alone
                    slow = bliss_events.event_search(on, offs)
                    self.assertEqual(key(slow), key(bliss_events.event_search_fast(on, offs)))
                    events += len(slow)
        self.assertGreater(events, 0)          # the matching was exercised

    def test_on_only_is_an_event_and_off_vetoes(self):
        hit = {"drift_rate_Hz_per_sec": 0.5, "snr": 20.0, "power": 1.0, "bandwidth": 3.0, "duration_sec": 292.0}

        def at(t, look):
            return dict(hit, start_time_sec=t, _look=look, start_freq_MHz=1000.0 + 0.5 * t / 1e6)
        on = [(57000 + 600.0 * j / 86400, 292.0, [at(600.0 * j, 2 * j)]) for j in range(3)]
        self.assertEqual(len(bliss_events.event_search(on, [[], [], []])), 1)
        on = [(t0, d, [dict(h) for h in hs]) for t0, d, hs in on]
        self.assertEqual(bliss_events.event_search(on, [[at(300.0, 1)], [], []]), [])


class Check8(unittest.TestCase):
    def test_before_and_after_indexing(self):
        rng = np.random.default_rng(8)
        hits = [{"frequency_mhz": float(f), "drift_hz_s": float(rng.choice([0.0, 0.005, 1.0])),
                 "snr": float(rng.uniform(10, 60))} for f in rng.uniform(1000, 1100, 400)]
        cases = [(1000.0, []), (1000.0, [{"frequency_mhz": 1000.0005, "drift_hz_s": 0.0, "snr": 30.0}]),
                 (1000.0, [{"frequency_mhz": 500.0, "drift_hz_s": 0.0, "snr": 30.0}] * 3)]
        for f, hs in cases:
            self.assertEqual(check8.old(f, hs, 0.01), check8.new(f, hs, 0.01))
        for step in (0.0102, 0.02):
            for f in check8.edges(hits):
                self.assertEqual(check8.old(f, hits, step, chance=False), check8.new(f, hits, step, chance=False))
            for f in (1050.0, float(rng.uniform(1000, 1100))):
                self.assertEqual(check8.old(f, hits, step, trials=40), check8.new(f, hits, step, trials=40))


if __name__ == "__main__":
    unittest.main()
