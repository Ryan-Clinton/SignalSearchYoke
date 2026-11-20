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


if __name__ == "__main__":
    unittest.main()
