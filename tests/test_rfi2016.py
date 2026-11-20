"""The 2016 interference analysis (tools/rfi2016.py): a planted signal is
counted under a stricter ON-hit rule only by the event that recovers it;
candidates are matched across two searches by frequency and drift; and
the ON evidence and places are named as the analysis names them."""
import unittest

import synth  # noqa: F401  (paths and a throwaway data folder)
import rfi2016 as rf

F = 2000.0
T_F = {0: F, 2: F, 4: F}


def ev(hits_in, tracks_in=(), f=F, drift=0.5, off_hz=0.0):
    """A kept event: member hits in the looks hits_in, tracks in tracks_in, at f + off_hz."""
    g = f + off_hz / 1e6
    return {"f_mhz": g, "drift": drift, "members": [[j, n, g, drift] for n, j in enumerate(hits_in)],
            "tracks": [[j, g, drift, 8.0] for j in tracks_in]}


class RecoveredWith(unittest.TestCase):
    def test_the_recovering_event_decides_not_the_one_with_most_hits(self):
        # Event A: three ON hits, but one of them 40 Hz off, so it does not match in all three looks.
        a = ev((0, 2), off_hz=0.0)
        a["members"].append([4, 9, F + 40e-6, 0.5])
        # Event B: one hit and two tracks, matching in all three looks: it is the one that recovers the signal.
        b = ev((0,), tracks_in=(2, 4))
        planted = [a, b]
        self.assertTrue(rf.recovered_with(T_F, 0.5, planted, [], 1))
        # A two-hit rule removes B; A has three hits but does not recover: the signal is lost.
        self.assertFalse(rf.recovered_with(T_F, 0.5, planted, [], 2))

    def test_a_qualifying_event_in_the_unplanted_block_is_a_false_association(self):
        b = ev((0, 2, 4))
        self.assertTrue(rf.recovered_with(T_F, 0.5, [b], [], 3))
        self.assertFalse(rf.recovered_with(T_F, 0.5, [b], [ev((0, 2, 4))], 3))


class MatchGroups(unittest.TestCase):
    def test_kept_changed_gone_new(self):
        before = [ev((0,), (2, 4)), ev((0, 2), (4,), off_hz=500.0), ev((0,), (2, 4), off_hz=9000.0)]
        after = [ev((0,), (2, 4)), ev((0, 2, 4), off_hz=500.0), ev((0,), (2, 4), off_hz=20000.0)]
        got = rf.match_groups(before, after)
        self.assertEqual(got, {"kept": 1, "kept_with_other_members": 1, "gone": 1, "new": 1})


class Names(unittest.TestCase):
    def test_evidence(self):
        self.assertEqual(rf.evidence(ev((0, 2, 4))), "three hits")
        self.assertEqual(rf.evidence(ev((0, 2), (4,))), "two hits and a track")
        self.assertEqual(rf.evidence(ev((0,), (2, 4))), "one hit and two tracks")

    def test_place(self):
        self.assertEqual(rf.place(1176.45, "crowded"), "in a listed band")
        self.assertEqual(rf.place(1160.0, "crowded"), "within 10 MHz of a listed band")
        self.assertEqual(rf.place(1378.5, "crowded"), "in the known-RFI annotation (GPS L3)")
        self.assertEqual(rf.place(1450.0, "clean"), "elsewhere, clean block")


if __name__ == "__main__":
    unittest.main()
