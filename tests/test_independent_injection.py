"""The independent-injector comparison: its block rule and the difference it reads, with faults planted."""
import synth  # noqa: F401  (first: the tests' own data folder)

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import independent_injection as ii  # noqa: E402


def block(own, sg, n=10):
    """own, sg: (ours found, turboSETI found) of n signals."""
    tones = []
    for i in range(n):
        at = {c: {"own": {"ours": i < own[0], "turboseti": i < own[1]},
                  "setigen": {"ours": i < sg[0], "turboseti": i < sg[1]}} for c in ii.CUTS}
        tones.append({"bin": 0, "at": at})
    return {"tones": tones}


class Rule(unittest.TestCase):
    def test_the_draw_is_repeatable_and_by_class(self):
        classes = {b: ("crowded" if b % 3 == 0 else "clean") for b in range(60)}
        a, b = ii.choose(classes), ii.choose(classes)
        self.assertEqual(a, b)
        self.assertEqual(sorted(a.values()), ["clean"] * 8 + ["crowded"] * 8)

    def test_no_favour_when_the_advantage_is_the_same(self):
        got = ii.difference_of_advantages([block((8, 2), (8, 2))] * 12, "10")
        self.assertEqual(got["difference"], 0.0)
        self.assertLessEqual(got["interval"][0], 0)

    def test_favour_is_seen(self):
        got = ii.difference_of_advantages([block((9, 1), (5, 4))] * 12, "10")
        self.assertAlmostEqual(got["difference"], 0.7)
        self.assertGreater(got["interval"][0], 0)

    def test_an_injector_that_helps_turboseti_more_is_not_called_favour(self):
        got = ii.difference_of_advantages([block((8, 2), (9, 1))] * 12, "10")
        self.assertLess(got["difference"], 0)


if __name__ == "__main__":
    unittest.main()


class Records(unittest.TestCase):
    """record_problems: a block record is the protocol's whole result, or it is refused."""
    NONE = staticmethod(lambda pv, own=(): [])

    def pair(self, n=110):
        found = {c: {"three_looks": "recovered"} for c in ii.CUTS}
        lost = {c: {"three_looks": "missed"} for c in ii.CUTS}
        want = {"tones": [{"x0": 1000.0 + 26 * i, "drift": 0.1 * i, "s_in": 30, "bin": i % 5, "ours": found,
                           "turboseti": lost, "turboseti_on_hits": {c: 3 for c in ii.CUTS}} for i in range(n)]}
        cell = {"own": {"ours": True, "turboseti": False}, "setigen": {"ours": True, "turboseti": True}}
        rec = {"block": 7, "class": "clean", "smearing": True,
               "tones": [{"x0": w["x0"], "drift": w["drift"], "s_in": w["s_in"], "bin": w["bin"],
                          "at": {c: {h: dict(v) for h, v in cell.items()} for c in ii.CUTS}} for w in want["tones"]]}
        return rec, want

    def problems(self, rec, want, smearing=True, code=None, places=False):
        return ii.record_problems(rec, 7, "clean", want, smearing, code or self.NONE, places=places)

    def test_a_whole_record_passes(self):
        self.assertEqual(self.problems(*self.pair()), [])

    def test_another_block_or_class_is_refused(self):
        rec, want = self.pair()
        self.assertTrue(self.problems(dict(rec, block=8), want))
        self.assertTrue(self.problems(dict(rec, **{"class": "crowded"}), want))

    def test_the_other_smearing_is_refused(self):
        rec, want = self.pair()
        self.assertTrue(self.problems(rec, want, smearing=False))
        self.assertTrue(self.problems({k: v for k, v in rec.items() if k != "smearing"}, want))

    def test_a_short_record_is_refused(self):
        rec, want = self.pair()
        self.assertTrue(self.problems(dict(rec, tones=rec["tones"][:50]), want))

    def test_other_signals_are_refused(self):
        rec, want = self.pair()
        rec["tones"][3] = dict(rec["tones"][3], s_in=40)
        self.assertTrue(self.problems(rec, want))

    def test_a_signal_at_another_place_is_refused(self):
        rec, want = self.pair()
        rec["tones"][5]["x0"] += 1
        self.assertTrue(self.problems(rec, want))

    def test_a_record_without_places_is_checked_by_its_other_fields(self):
        # the first and second draws' records carry no place: it was checked against the seed when they ran
        rec, want = self.pair()
        for t in rec["tones"]:
            del t["x0"]
        self.assertEqual(self.problems(rec, want), [])

    def test_from_the_third_draw_a_record_without_places_is_refused(self):
        rec, want = self.pair()
        self.assertEqual(self.problems(rec, want, places=True), [])
        del rec["tones"][4]["x0"]
        self.assertTrue(self.problems(rec, want, places=True))
        self.assertEqual(self.problems(rec, want), [])
        self.assertEqual(ii.PLACES_FROM, 3)

    def test_the_project_planting_results_must_be_the_matched_records(self):
        rec, want = self.pair()
        rec["tones"][9]["at"]["30"]["own"]["turboseti"] = True
        self.assertTrue(self.problems(rec, want))
        rec, want = self.pair()
        want["tones"][9] = dict(want["tones"][9], turboseti_on_hits={c: 2 for c in ii.CUTS},
                                turboseti={c: {"three_looks": "recovered"} for c in ii.CUTS})
        self.assertEqual(self.problems(rec, want), [])       # found in three looks but two ON hits: not counted

    def test_the_third_draw_is_of_the_2016_session(self):
        classes = {b: ("crowded" if b % 2 else "clean") for b in range(121)}
        third, folder = ii.chosen_for(classes, 3)
        self.assertEqual(sorted(third.values()), ["clean"] * 8 + ["crowded"] * 8)
        self.assertEqual((folder, ii.target_for(3)), (ii.THIRD, "HIP17147"))
        self.assertEqual(ii.target_for(2), ii.TARGET)

    def test_a_missing_cut_or_pipeline_is_refused(self):
        rec, want = self.pair()
        del rec["tones"][2]["at"]["30"]
        self.assertTrue(self.problems(rec, want))
        rec, want = self.pair()
        del rec["tones"][2]["at"]["10"]["setigen"]["turboseti"]
        self.assertTrue(self.problems(rec, want))

    def test_changed_code_is_refused(self):
        self.assertTrue(self.problems(*self.pair(), code=lambda pv, own=(): ["changed"]))

    def test_the_second_draw_leaves_out_the_first_and_the_trial(self):
        classes = {b: ("crowded" if b % 3 == 0 else "clean") for b in range(80)}
        first, _ = ii.chosen_for(classes, 1)
        second, folder = ii.chosen_for(classes, 2)
        self.assertFalse(set(first) & set(second))
        self.assertNotIn(ii.TRIAL_BLOCK, second)
        self.assertEqual(sorted(second.values()), ["clean"] * 8 + ["crowded"] * 8)
        self.assertEqual(folder, ii.SECOND)
