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
import matched
import matched_tables
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


if __name__ == "__main__":
    unittest.main()
