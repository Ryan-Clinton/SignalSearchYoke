"""Planted faults for the measuring tools behind the evidence ledger (docs/audits.md D25-06): each tool's
measurement is shown to change when its input is made wrong on purpose, not only to give the current answer
on right input. The tools read real records; here they read small synthetic ones."""
import synth  # noqa: F401  (first: the tests' own data folder)

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import bliss_checks
import completeness_checks
import dc_checks
import detector_misses
import measure
import matched
import matched_tables
import numpy as np
import seti
import yoke


def _event(*hits):
    """A kept event whose members are (look, hit index, f, drift)."""
    return {"members": [(j, i, 1400.0 + i * 1e-3, 0.5) for j, i in hits]}


class BlissPins(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="ssy-bliss-"))
        pinned = dict(matched.BLISS_PINS)
        self.recs = [{"block": b, "class": "clean", "provenance": {"plain": dict(pinned), "planted": dict(pinned)}}
                     for b in (1, 2, 3)]

    def run_pins(self, recs):
        for p in self.folder.glob("block_*.json"):
            p.unlink()
        for r in recs:
            (self.folder / f"block_{r['block']:03d}.json").write_text(json.dumps(r), encoding="utf-8")
        with mock.patch.object(matched_tables, "load", return_value=("S", {"of": {"clean": 3, "crowded": 0}}, [])), \
                mock.patch.object(matched, "bliss_folder", return_value=self.folder):
            return bliss_checks.pins(say=lambda *a: None)

    def test_right_records_pass(self):
        self.assertEqual(self.run_pins(self.recs)["differing"], [])

    def test_a_changed_pin_is_seen(self):
        recs = copy.deepcopy(self.recs)
        recs[1]["provenance"]["planted"]["response_sha"] = "0" * 16
        bad = self.run_pins(recs)["differing"]
        self.assertEqual([(b["block"], b["part"]) for b in bad], [(2, "planted")])

    def test_a_missing_run_is_not_pinned(self):
        recs = copy.deepcopy(self.recs)
        del recs[0]["provenance"]["plain"]                 # passed before: only the parts present were checked
        recs[2].pop("provenance")
        bad = self.run_pins(recs)["differing"]
        self.assertEqual(sorted((b["block"], b["part"]) for b in bad), [(1, "plain"), (3, "plain"), (3, "planted")])


class BlissTwoAndThree(unittest.TestCase):
    """bliss_checks.events: false candidates split by how many ON looks hold a member."""

    def run_events(self, recs):
        folder = Path(tempfile.mkdtemp(prefix="ssy-bliss-"))
        for r in recs:
            (folder / f"block_{r['block']:03d}.json").write_text(json.dumps(r), encoding="utf-8")
        with mock.patch.object(matched_tables, "load", return_value=("S", {"of": {"clean": 1, "crowded": 1}}, [])), \
                mock.patch.object(matched, "bliss_folder", return_value=folder):
            return bliss_checks.events(say=lambda *a: None)["false_a_block"][matched.ck(30)]

    def recs(self):
        three = _event((0, 1), (2, 2), (4, 3))
        two = _event((0, 4), (2, 5))
        false = {matched.ck(c): {"(0, 1, 2)": [three, two]} for c in matched.CUTS_BLISS}
        return [{"block": b, "class": cls, "false": copy.deepcopy(false), "tones": []}
                for b, cls in ((1, "clean"), (2, "crowded"))]

    def test_the_split(self):
        got = self.run_events(self.recs())
        self.assertEqual((got["all"], got["exactly_two_on"], got["three_on"]), (2.0, 1.0, 1.0))

    def test_a_dropped_member_moves_an_event(self):
        recs = self.recs()
        recs[1]["false"][matched.ck(30)]["(0, 1, 2)"][0]["members"].pop()   # the crowded block's three-ON event
        got = self.run_events(recs)
        self.assertEqual((got["exactly_two_on"], got["three_on"]), (1.5, 0.5))

    def test_a_doubled_event_is_not_counted_twice(self):
        recs = self.recs()
        evs = recs[0]["false"][matched.ck(30)]["(0, 1, 2)"]
        recs[0]["false"][matched.ck(30)]["(0, 1, 3)"] = copy.deepcopy(evs)  # the same hits under another choice
        self.assertEqual(self.run_events(recs)["all"], 2.0)


class CompletenessRecords(unittest.TestCase):
    """completeness_checks.records: recovery split by whether an ON look was capped, and by occupancy."""

    def recs(self):
        def tone(found):
            st = {"three_looks": "recovered" if found else "missed", "nearest": {"df_hz": 1.0, "dd_hz_s": 0.01}}
            return {"drift": 1.0, "ours": {"30": dict(st), "10": dict(st)}}
        return [{"block": 1, "complete": [True] * 6, "tones": [tone(True), tone(True)], "ours": {"false": {}}},
                {"block": 2, "complete": [False] + [True] * 5, "tones": [tone(True), tone(False)],
                 "ours": {"false": {"30": {"(0, 1, 2)": [_event((0, 1), (2, 2), (4, 3))]}}}}]

    def run_records(self, recs, hits=(10, 3000)):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE blocks (session TEXT, block_idx INTEGER, hits INTEGER, status TEXT)")
        db.executemany("INSERT INTO blocks VALUES ('S', ?, ?, 'done')", [(1, hits[0]), (2, hits[1])])
        with mock.patch.object(completeness_checks, "SESSIONS", ("T",)), \
                mock.patch.object(matched_tables, "load", return_value=("S", {}, recs)), \
                mock.patch.object(completeness_checks.store, "connect_readonly", return_value=db), \
                mock.patch.object(yoke, "write"):
            return completeness_checks.records(say=lambda *a: None)["sessions"]["T"]

    def test_the_split(self):
        cap = self.run_records(self.recs())["cap"]
        self.assertEqual(cap["all complete"]["share_30"], 1.0)
        self.assertEqual(cap["an ON look capped"]["share_30"], 0.5)
        self.assertEqual(cap["an ON look capped"]["false_30"], 1)

    def test_a_flipped_flag_moves_the_block(self):
        recs = self.recs()
        recs[1]["complete"] = [True, False] + [True] * 4      # an OFF look capped instead of an ON look
        cap = self.run_records(recs)["cap"]
        self.assertNotIn("an ON look capped", cap)
        self.assertEqual(cap["only OFF looks capped"]["blocks"], 1)

    def test_a_shifted_frequency_is_seen_in_the_errors(self):
        recs = self.recs()
        recs[0]["tones"][0]["ours"]["30"]["nearest"]["df_hz"] = 9.0
        err = self.run_records(recs)["errors_nearest_member_30"]
        self.assertEqual(max(v["hz_p50_p90_p99_max"][3] for v in err.values()), 9.0)

    def test_swapped_occupancy_moves_the_shares(self):
        a = self.run_records(self.recs())["occupancy_hits_at_the_sweep_cut"]
        b = self.run_records(self.recs(), hits=(3000, 10))["occupancy_hits_at_the_sweep_cut"]
        self.assertEqual((a["5-20"]["share_30"], a["1000-more"]["share_30"]), (1.0, 0.5))
        self.assertEqual((b["5-20"]["share_30"], b["1000-more"]["share_30"]), (0.5, 1.0))


class DcRead(unittest.TestCase):
    """dc_checks reads each block under both DC rules; its result (identical counts, audit 14) means something only
    if the switch reaches the reader at each call, not once at import."""

    def test_each_read_under_its_rule_and_the_setting_put_back(self):
        os.environ["SSY_DC_BY_CHUNK"] = "1"
        try:
            with mock.patch.object(seti, "read_looks", side_effect=lambda *a: seti.dc_rule()):
                self.assertEqual(dc_checks._read([], (0, 1), True), "storage chunk")
                self.assertEqual(dc_checks._read([], (0, 1), False), "coarse channel")
            self.assertEqual(os.environ["SSY_DC_BY_CHUNK"], "1")
        finally:
            os.environ.pop("SSY_DC_BY_CHUNK", None)


class DetectorMisses(unittest.TestCase):
    """detector_misses.look: the detector's S/N on a signal's own track, its matching hit, and the pixels of the
    track other hits blanked. Each must answer differently when the signal is not where it is said to be, or
    when another hit crosses it."""
    X, DRIFT = 5000.3, 0.5

    def look(self, tones, x=X):
        c = synth.cadence(3)[0]
        sigma = float(np.median(c["sigma"]))
        raw = measure.plant(c["raw"], [(t[0], t[1], t[2] * sigma / 4) for t in tones], synth.TSAMP, synth.FOFF)
        s = dict(c["s"], spectra=raw)
        f_hz = (synth.FCH1 + x * synth.FOFF) * 1e6
        return detector_misses.look(raw, s, [(x, self.DRIFT, f_hz)], 0)[0]

    def test_a_lone_signal(self):
        r = self.look([(self.X, self.DRIFT, 60)])
        self.assertIsNotNone(r["matching_hit_snr"])
        self.assertGreater(r["exact_track"]["snr"], 15)
        self.assertEqual(r["blanked_by_others"]["pixels"], 0)

    def test_the_wrong_place_is_seen(self):
        r = self.look([(self.X, self.DRIFT, 60)], x=self.X + 40)          # told it is 40 channels away
        self.assertIsNone(r["matching_hit_snr"])
        self.assertLess(r["exact_track"]["snr"], 8)

    def test_a_crossing_hit_blanks_the_track(self):
        # A stronger tone drifting the other way crosses the signal's track mid-look and is picked first.
        r = self.look([(self.X, self.DRIFT, 60), (self.X - 52.0, -self.DRIFT, 200)])
        self.assertGreater(r["blanked_by_others"]["pixels"], 0)
        self.assertTrue(r["blanked_by_others"]["hits"])


class CompletenessSwitches(unittest.TestCase):
    """completeness_checks.pairs and shadow compare the search with a switch of its diagnostic copy turned; the
    comparison says nothing if the switch does nothing. Each switch must change the answer on a case it is for."""

    def setUp(self):
        import search_variants
        self.sv = search_variants
        noise = np.random.default_rng(1).chisquare(102, size=(16, 16384)) * 1e3
        self.noise, self.h = noise, 60 * float(np.median(measure.channel_noise(noise))) / 4

    def search(self, tones, **kw):
        p = measure.plant(self.noise, tones, synth.TSAMP, synth.FOFF)
        return self.sv.search_variant(p, synth.FOFF, synth.TSAMP, synth.FCH1, **kw)

    def test_the_corridor_switch(self):
        # Two equal signals 4 channels apart drifting opposite ways at 3 Hz/s: the second is lost beside the
        # first as the search is, and found without the corridor of excluded line starts.
        x2, d2 = 8004.0, 3.0
        f2 = synth.FCH1 + x2 * synth.FOFF
        tones = [(8000.0, -3.0, self.h), (x2, d2, self.h)]
        self.assertTrue(completeness_checks._found(self.search([(x2, d2, self.h)]), f2, d2))
        self.assertFalse(completeness_checks._found(self.search(tones), f2, d2))
        self.assertTrue(completeness_checks._found(self.search(tones, corridor=False), f2, d2))

    def test_the_shadow_refresh_switch(self):
        tones = [(8000.0 + 5 * k, (-1) ** k * 2.5, self.h * (0.3 + 0.1 * k)) for k in range(8)]

        def keys(hs):
            return {(round(h["frequency_mhz"], 6), round(h["drift_hz_s"], 3)) for h in hs}
        self.assertNotEqual(keys(self.search(tones)), keys(self.search(tones, refresh_shadow=True)))


if __name__ == "__main__":
    unittest.main()
