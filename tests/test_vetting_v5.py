"""Checks version 5 (docs/audits.md 12): check 8 does not let a candidate be
its own intermodulation product, check 6 keeps the same target's other
sessions apart, check 1 does not take unknown completeness as complete, and
ranking refuses to score without its OFF null."""
import math
import unittest

import numpy as np

import synth


def _candidate():
    """A strong zero-drift tone in the three ON looks of a synthetic cadence, through the pipeline."""
    import matched
    import measure
    cad = synth.cadence(4)
    sigma = float(np.median(cad[1]["sigma"]))
    planted = []
    for j, c in enumerate(cad):
        raw = c["raw"]
        if j in (0, 2, 4):
            raw = measure.plant(raw, [(9000.0, 0.0, 80 * sigma / math.sqrt(raw.shape[0]))], c["s"]["tsamp"],
                                c["s"]["foff"])
        planted.append(dict(c, raw=raw, spectra=raw, s=dict(c["s"], spectra=raw)))
    searched = matched.our_search(planted)
    looks, events, _ = matched.our_events(planted, searched, matched.TRUE, 10, [{} for _ in range(6)])
    ev = next(e for e in events if e["label"] == "candidate")
    hits = [h for lk in looks for h in lk.hits if not h.get("shadow")]
    return ev, looks, hits


class Version5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev, cls.looks, cls.hits = _candidate()

    def _c(self, result, n):
        return next(c for c in result["checks"] if c["n"] == n)

    def test_check_8_needs_two_other_signals(self):
        """The candidate's own tone (detected any number of times) cannot be a parent, and one tone cannot
        be both parents; two other tones still make the relation."""
        import vetting
        f = self.ev["frequency_mhz"]

        def rel(extra):
            hits = [{"frequency_mhz": x, "drift_hz_s": 0.0, "snr": 50.0} for x in extra]
            return self._c(vetting.vet(self.ev, self.looks, None, (), hits), 8)["evidence"]["relations"]
        self.assertNotIn("2f1+-1f2", rel([f, f, f + 7.123456]))           # its own tone, three times over
        self.assertNotIn("2f1+-1f2", rel([f + 3.0, f + 3.0 + 1e-9]))      # 3f1 - 2f2 from one tone at f + 3
        self.assertIn("2f1+-1f2", rel([f + 3.0, f + 6.0]))                # 2(f + 3) - (f + 6) = f

    def test_check_6_keeps_the_same_target_apart(self):
        import vetting
        f, l0 = self.ev["frequency_mhz"], self.looks[0]
        hit = {"frequency_mhz": f, "drift_hz_s": self.ev["drift_hz_s"], "snr": 40.0, "mjd": l0.tstart + 1.0,
               "shadow": False}
        same = vetting.vet(self.ev, self.looks, {"name": "SYNTH"}, [dict(hit, target="SYNTH")], self.hits)
        other = vetting.vet(self.ev, self.looks, {"name": "SYNTH"}, [dict(hit, target="ELSEWHERE")], self.hits)
        self.assertEqual(self._c(same, 6)["evidence"]["same_target_hits_left_out"], 1)
        self.assertIsNone(self._c(same, 6)["strength"])
        self.assertEqual(self._c(other, 6)["evidence"]["same_target_hits_left_out"], 0)
        self.assertIsNotNone(self._c(other, 6)["strength"])

    def test_check_1_unknown_completeness_is_not_sound(self):
        import vetting
        infos = [vetting.LookInfo(lk.hits, lk.tstart, lk.position, lk.step, lk.width_hz, complete=None if j == 1 else True)
                 for j, lk in enumerate(self.looks)]
        self.assertEqual(self._c(vetting.vet(self.ev, infos, None, (), self.hits), 1)["result"], "not sound")
        infos[1].complete = True
        self.assertEqual(self._c(vetting.vet(self.ev, infos, None, (), self.hits), 1)["result"], "sound")


class Records(unittest.TestCase):
    def test_two_events_sharing_a_lead_id_both_found(self):
        import json
        import check
        d = check.records_dir()
        d.mkdir(parents=True, exist_ok=True)
        lead = "SETI-T-S-1000.000000"
        (d / f"{lead}.json").write_text(json.dumps({"lead": lead, "event_id": 1}), encoding="utf-8")
        (d / f"{lead}-e2.json").write_text(json.dumps({"lead": f"{lead}-e2", "event_id": 2}), encoding="utf-8")
        self.assertEqual(check.record_for(lead, 1)[1]["lead"], lead)
        self.assertEqual(check.record_for(lead, 2)[1]["lead"], f"{lead}-e2")
        self.assertEqual(check.record_for(lead, 3), (None, None))

    def test_off_null_only_for_its_own_session(self):
        import sqlite3
        import ranking
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE files (session, target, cadence_target, tstart_mjd, is_on)")
        db.executemany("INSERT INTO files VALUES (?,?,?,?,?)",
                       [("A", "KIC8462852", None, 57898.26, 1), ("B", "NGC6946", None, 58795.22, 1)])
        rec = {"cadences": [{"cadence": "spliced_x_guppi_57898_22410_DIAG_KIC8462852_0031.h5"}]}
        self.assertTrue(ranking.null_applies(rec, db, "A"))
        self.assertFalse(ranking.null_applies(rec, db, "B"))


if __name__ == "__main__":
    unittest.main()
