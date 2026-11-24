"""The planted-signal test on control B's cadences: its block rule and its stage counts, with faults planted."""
import synth  # noqa: F401  (first: the tests' own data folder)

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import control_injection as ci  # noqa: E402
import matched  # noqa: E402
import yoke  # noqa: E402


def at(looks=3, candidate=True, already=False, verdict="unexplained, strong"):
    a = {"hit_looks": looks, "candidate": candidate, "already_in_the_block": already}
    if candidate and not already:
        a.update(verdict=verdict, reasons=[] if verdict.startswith("unexplained") else ["zero or very low drift"])
    return a


def tone(a30, a10=None, b=0, s=30):
    return {"bin": b, "s_in": s, "at": {"30": a30, "10": a10 or a30}}


class Blocks(unittest.TestCase):
    DONE = {str(k): {"complete": k % 3 != 0} for k in range(60)}

    def test_the_rule_is_repeatable_and_balanced(self):
        a, b = ci.pick_blocks(self.DONE, 0, 7), ci.pick_blocks(self.DONE, 0, 7)
        self.assertEqual(a, b)
        self.assertEqual(sorted(a.values()), ["capped"] * 4 + ["complete"] * 4)
        self.assertTrue(all((k % 3 == 0) == (v == "capped") for k, v in a.items()))

    def test_it_reads_only_completeness(self):
        held = {k: dict(d, events=[{"snr": 90}] * int(k)) for k, d in self.DONE.items()}
        self.assertEqual(ci.pick_blocks(held, 1, 7), ci.pick_blocks(self.DONE, 1, 7))

    def test_too_few_is_refused(self):
        with self.assertRaises(yoke.Refusal):
            ci.pick_blocks({str(k): {"complete": True} for k in range(9)}, 0, 7)


class Stages(unittest.TestCase):
    def test_each_stage(self):
        tones = [tone(at()), tone(at(verdict="likely interference (indicated: x)")),
                 tone(at(looks=2, candidate=False)), tone(at(looks=0, candidate=False)), tone(at(already=True))]
        got = ci.stage_counts(tones, 30)
        self.assertEqual((got["planted"], got["already_in_the_block"], got["counted"]), (5, 1, 4))
        self.assertEqual((got["hit_in_any_on_look"], got["hit_in_all_three"], got["candidates"], got["unexplained"]), (3, 2, 2, 1))
        self.assertEqual((got["share_unexplained"], got["unexplained_of_candidates"]), (0.25, 0.5))
        self.assertEqual(got["verdicts"], {"likely interference": 1, "unexplained, strong": 1})

    def test_a_signal_already_there_is_never_credited(self):
        got = ci.stage_counts([tone(at(already=True))], 30)
        self.assertEqual((got["counted"], got["candidates"], got["unexplained"]), (0, 0, 0))

    def test_each_cut_is_its_own(self):
        tones = [tone(at(), at(candidate=False, looks=1))]
        self.assertEqual(ci.stage_counts(tones, 30)["candidates"], 1)
        self.assertEqual(ci.stage_counts(tones, 10)["candidates"], 0)


class Matching(unittest.TestCase):
    F = {0: 1400.0, 2: 1400.0, 4: 1400.0}

    def run_at(self, df_hz=0.0, snr=40, cut=30):
        hit = {"frequency_mhz": 1400.0 + df_hz / 1e6, "drift_hz_s": 1.0, "snr": snr}
        kept = [{"members": [[j, 1, 1400.0 + df_hz / 1e6, 1.0] for j in (0, 2, 4)], "tracks": []}]
        return ci.tone_at(self.F, 1.0, {j: [hit] for j in (0, 2, 4)}, kept, [], cut, matched.RECOVERY[3][2],
                          matched._event_fit, matched._match)

    def test_the_signal_is_found(self):
        self.assertEqual(self.run_at(), (3, 0, False))

    def test_a_signal_elsewhere_is_not_credited(self):
        self.assertEqual(self.run_at(df_hz=50.0), (0, None, False))

    def test_a_hit_under_the_cut_is_not_counted(self):
        self.assertEqual(self.run_at(snr=20)[0], 0)

    def test_a_candidate_already_in_the_block_is_seen(self):
        plain = [{"members": [[0, None, 1400.0, 1.0]]}]
        hit = {"frequency_mhz": 1400.0, "drift_hz_s": 1.0, "snr": 40}
        got = ci.tone_at(self.F, 1.0, {j: [hit] for j in (0, 2, 4)}, [], plain, 30, matched.RECOVERY[3][2],
                         matched._event_fit, matched._match)
        self.assertTrue(got[2])


class Summary(unittest.TestCase):
    def test_capped_and_complete_are_apart(self):
        records = [{"target": "A", "class": "capped", "tones": [tone(at(verdict="likely interference (indicated: x)"))]},
                   {"target": "A", "class": "complete", "tones": [tone(at())]}]
        got = ci.summarise(records)["30"]
        self.assertEqual((got["capped"]["unexplained"], got["complete"]["unexplained"], got["all"]["unexplained"]), (0, 1, 1))
        self.assertEqual(got["what_the_checks_cited_against_kept_signals"], {"zero or very low drift": 1})


if __name__ == "__main__":
    unittest.main()
