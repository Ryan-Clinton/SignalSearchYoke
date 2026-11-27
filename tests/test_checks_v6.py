"""checks_v6.compare: the two versions side by side, counted by session and cut, and refused unless both judged
the same candidates."""
import sys
import unittest
from pathlib import Path

import synth  # noqa: F401  (the tests' own data folder)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import checks_v6  # noqa: E402
import yoke  # noqa: E402


def ev(i, session, snr, verdict):
    return {"event_id": i, "session": session, "block": i, "snr": snr, "frequency_mhz": 1000.0 + i,
            "drift_hz_s": 0.1, "verdict": verdict}


class Compare(unittest.TestCase):
    def test_counts_changes_and_what_version_6_leaves(self):
        v5 = [ev(1, "S", 40, "likely interference (indicated: known interference bands)"),
              ev(2, "S", 12, "interference (shown: zero or very low drift)"),
              ev(3, "S", 50, "likely interference (indicated: crowding)")]
        v6 = [ev(1, "S", 40, "unexplained, weak"), ev(2, "S", 12, "interference (shown: zero or very low drift)"),
              ev(3, "S", 50, "likely interference (indicated: crowding)")]
        sessions, left = checks_v6.compare(v5, v6)
        self.assertEqual(sessions["S"]["30"], {"candidates": 2, "version_5": {"likely interference": 2},
                                               "version_6": {"likely interference": 1, "unexplained, weak": 1},
                                               "unexplained_5": 0, "unexplained_6": 1, "changed": 1})
        self.assertEqual(sessions["S"]["10"]["candidates"], 3)
        self.assertEqual([x["event_id"] for x in left], [1])

    def test_different_candidates_are_refused(self):
        with self.assertRaises(yoke.Refusal):
            checks_v6.compare([ev(1, "S", 40, "unexplained, weak")], [ev(2, "S", 40, "unexplained, weak")])


if __name__ == "__main__":
    unittest.main()
