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

    def test_the_reading_follows_the_protocol(self):
        kept = [{"target": "A", "class": "complete", "tones": [tone(at())] * 4}] * 3
        lost = [{"target": "A", "class": "capped", "tones": [tone(at(verdict="likely interference (indicated: x)"))] * 4}] * 3
        got = ci.summarise(kept + lost)["30"]
        self.assertEqual(got["complete"]["unexplained_of_candidates_interval"], [1.0, 1.0])
        self.assertTrue(got["complete"]["reading"].startswith("the checks kept"))
        self.assertTrue(got["capped"]["reading"].startswith("not shown"))
        self.assertTrue(got["all"]["reading"].startswith("not shown"))      # half kept: its lower end is under 0.5


class Records(unittest.TestCase):
    """record_problems: a block record is the protocol's whole result, or it is refused."""
    C = {"target": "A", "session": "S", "urls": []}
    INFO = {"class": "capped", "range": [1, 2]}
    V = {"search": "s", "checks": "c"}

    def rec(self, n=matched.TONES, **change):
        tones = [{"x0": float(i), "drift": 0.1 * i, "s_in": 30, "bin": 0, "at": {"30": at(), "10": at()}} for i in range(n)]
        r = {"target": "A", "session": "S", "block": 7, "class": "capped", "versions": dict(self.V),
             "complete": [True] * 6, "tones": tones, "provenance": {"git_commit": "abc"}}
        r.update(change)
        return r

    def problems(self, rec, unchanged=lambda c: True):
        return ci.record_problems(rec, self.C, 7, self.INFO, self.V, unchanged)

    def test_a_whole_record_passes(self):
        self.assertEqual(self.problems(self.rec()), [])

    def test_one_signal_is_not_a_block(self):
        self.assertTrue(self.problems(self.rec(n=1)))

    def test_repeated_signals_are_refused(self):
        r = self.rec()
        r["tones"][5] = dict(r["tones"][4])
        self.assertTrue(self.problems(r))

    def test_a_missing_cut_is_refused(self):
        r = self.rec()
        del r["tones"][3]["at"]["10"]
        self.assertTrue(self.problems(r))

    def test_another_block_is_refused(self):
        self.assertTrue(self.problems(self.rec(block=8)))
        self.assertTrue(self.problems(self.rec(**{"class": "complete"})))

    def test_another_version_is_refused(self):
        self.assertTrue(self.problems(self.rec(versions={"search": "old", "checks": "c"})))

    def test_no_versions_needs_unchanged_code(self):
        r = self.rec()
        del r["versions"]
        self.assertEqual(self.problems(r, lambda c: True), [])
        self.assertTrue(self.problems(r, lambda c: False))


class Intervals(unittest.TestCase):
    def test_a_draw_with_no_candidates_is_left_out_not_zero(self):
        kept = {"target": "A", "class": "capped", "tones": [tone(at())] * 3}
        none = {"target": "A", "class": "capped", "tones": [tone(at(looks=0, candidate=False))] * 3}
        got = ci._block_interval([kept] + [none] * 4, 30, "candidates")
        self.assertEqual(got, [1.0, 1.0])                      # every draw with candidates keeps them all

    def test_weighting_moves_toward_the_population(self):
        kept = {"target": "A", "class": "complete", "tones": [tone(at())] * 4}
        lost = {"target": "A", "class": "capped", "tones": [tone(at(verdict="likely interference (indicated: x)"))] * 4}
        recs = [kept] * 3 + [lost] * 3
        self.assertAlmostEqual(ci.weighted(recs, 30, 0.5)["unexplained_of_candidates"][0], 0.5)
        self.assertAlmostEqual(ci.weighted(recs, 30, 0.137)["unexplained_of_candidates"][0], 0.863)


class Lanes(unittest.TestCase):
    class P:
        def __init__(self, code):
            self.code, self.stopped = code, False

        def poll(self):
            return -15 if self.stopped else self.code

        def terminate(self):
            self.stopped = True

    def test_a_fault_is_reported_while_another_lane_waits(self):
        waiting, broken = self.P(None), self.P(1)
        with self.assertRaises(yoke.Refusal):
            ci.watch([waiting, broken], wait=0)
        self.assertTrue(waiting.stopped)

    def test_network_and_success_end_without_a_fault(self):
        self.assertEqual(ci.watch([self.P(0), self.P(yoke.NETWORK_EXIT)], wait=0), [0, yoke.NETWORK_EXIT])


class BandsAsContext(unittest.TestCase):
    """The candidate version 6 of the checks: a band alone no longer makes a verdict; anything else still does."""

    def vet(self, f, drift, context):
        import vetting
        from types import SimpleNamespace
        look = SimpleNamespace(step=0.05, tstart=58000.0, hits=[], position=0, complete=True)
        event = {"frequency_mhz": f, "drift_hz_s": drift, "looks": [], "stamps": None, "off_snr_max": 3.0}
        return vetting.vet(event, [look] * 6, None, (), (), bands_as_context=context)

    def test_a_band_alone_no_longer_decides(self):
        f = next((lo + hi) / 2 for lo, hi, _ in __import__("vetting").BANDS if hi - lo > 0.1)
        in_force, candidate = self.vet(f, 1.3, False), self.vet(f, 1.3, True)
        self.assertTrue(in_force["verdict"].startswith("likely interference"))
        self.assertIn("known interference bands", in_force["reasons"])
        self.assertTrue(candidate["verdict"].startswith("unexplained"))
        self.assertIn("context only", candidate["checks"][2]["result"])
        self.assertNotEqual(in_force["version"], candidate["version"])

    def test_other_signs_still_decide(self):
        f = next((lo + hi) / 2 for lo, hi, _ in __import__("vetting").BANDS if hi - lo > 0.1)
        got = self.vet(f, 0.0, True)                         # zero drift is still a sign
        self.assertTrue(got["verdict"].startswith("likely interference"))
        self.assertNotIn("known interference bands", got["reasons"])

    def test_the_stage_counts_read_either_version(self):
        a = at(verdict="likely interference (indicated: known interference bands)")
        a["verdict_context"], a["reasons_context"] = "unexplained, weak", []
        self.assertEqual(ci.stage_counts([tone(a)], 30)["unexplained"], 0)
        self.assertEqual(ci.stage_counts([tone(a)], 30, "verdict_context")["unexplained"], 1)


class LeaveOneOut(unittest.TestCase):
    def test_a_lone_check_is_what_it_costs(self):
        planted = [("capped", "likely interference (indicated: known interference bands)", ["known interference bands"]),
                   ("capped", "likely interference (indicated: known interference bands; crowding)",
                    ["known interference bands", "crowding"]),
                   ("complete", "interference (shown: recurrence at other targets and times)",
                    ["recurrence at other targets and times", "known interference bands"]),
                   ("complete", "unexplained, strong", [])]
        control = [(40, {"known interference bands": "indicated"}), (12, {"known interference bands": "indicated"}),
                   (40, {"crowding": "indicated", "known interference bands": "indicated"})]
        got = ci.leave_one_out(planted, control, 30)
        self.assertEqual(got["known interference bands"]["planted_kept_without_it"], {"complete": 0, "capped": 1})
        self.assertEqual(got["known interference bands"]["control_b_unexplained_without_it"], 1)
        self.assertEqual(got["recurrence at other targets and times"]["planted_kept_without_it"],
                         {"complete": 0, "capped": 0})     # still indicated by the band: likely interference

    def test_the_verdict_names_what_was_shown(self):
        shown, indicated = ci.verdict_parts("interference (shown: a; b)", ["a", "b", "c"])
        self.assertEqual((shown, indicated), ({"a", "b"}, {"c"}))


if __name__ == "__main__":
    unittest.main()
