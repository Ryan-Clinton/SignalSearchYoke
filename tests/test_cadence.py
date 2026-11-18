"""The ON-OFF cadence test on a synthetic cadence, through injection.trial
(plant, search each look, judge the six): a tone in the ON looks only is a
candidate, matched once in each ON look; one in every look is interference;
noise alone raises no candidate."""
import unittest

import synth

import injection

TONES = [{"x0": 5000.5, "drift": 0.3, "s_in": 60, "where": "on"},
         {"x0": 9000.5, "drift": -0.7, "s_in": 60, "where": "all"},
         {"x0": 12000.5, "drift": 0.0, "s_in": 60, "where": "on"}]


class Cadence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out, cls.events = injection.trial(synth.cadence(seed=0), TONES)

    def test_on_only_is_candidate(self):
        for t in self.out:
            if t["where"] == "on":
                with self.subTest(x0=t["x0"]):
                    self.assertEqual(t["found_on_looks"], 3)
                    self.assertEqual(t["label"], "candidate")
                    self.assertTrue(t["any_candidate"])

    def test_in_every_look_is_interference(self):
        t = next(t for t in self.out if t["where"] == "all")
        self.assertEqual(t["label"], "interference")
        self.assertFalse(t["any_candidate"])

    def test_one_event_a_signal(self):
        # Grouping: each planted signal is one event, holding one hit in each ON look.
        cands = [e for e in self.events if e["label"] == "candidate"]
        self.assertEqual(len(cands), 2)
        for e in cands:
            self.assertTrue(all(e["matches"][p] is not None for p in (0, 2, 4)), e["matches"])
            self.assertEqual(e["in_off"], [False, False, False])

    def test_noise_alone_no_candidate(self):
        out, events = injection.trial(synth.cadence(seed=5), [])
        self.assertEqual(out, [])
        self.assertEqual([e for e in events if e["label"] == "candidate"], [])


if __name__ == "__main__":
    unittest.main()
