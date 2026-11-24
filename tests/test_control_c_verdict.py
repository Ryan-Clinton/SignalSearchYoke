"""The adoption rule of docs/control-c.md, on known cases with faults planted."""
import synth  # noqa: F401  (first: the tests' own data folder)

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import control_c_verdict as cv  # noqa: E402


def blocks(n, u5, u6, k=10, counted=110, cls="capped"):
    return [[u5, u6, k, counted]] * n, [cls] * n


class Rule(unittest.TestCase):
    def rows(self, capped=(2, 8), complete=(7, 8)):
        a, ca = blocks(16, *capped)
        b, cb = blocks(16, *complete, cls="complete")
        return np.array(a + b, float), np.array(ca + cb)

    def test_a_clear_gain_is_seen(self):
        rows, classes = self.rows()
        got = cv.paired_difference(rows, classes, only="capped")
        self.assertAlmostEqual(got["difference"], 0.6)
        self.assertGreater(got["interval"][0], 0)
        self.assertGreater(cv.paired_difference(rows, classes, w_capped=0.137)["interval"][0], 0)

    def test_no_gain_is_not_a_gain(self):
        rows, classes = self.rows(capped=(3, 3), complete=(7, 7))
        got = cv.paired_difference(rows, classes, only="capped")
        self.assertEqual(got["difference"], 0.0)
        self.assertFalse(cv.decide(got, got, {"rate": 0.0, "interval": [0, 0]})["adopted"])

    def test_a_noisy_gain_does_not_pass(self):
        rows = np.array([[0, 10, 10, 110], [5, 0, 10, 110]] * 8 + [[7, 7, 10, 110]] * 16, float)
        classes = np.array(["capped"] * 16 + ["complete"] * 16)
        got = cv.paired_difference(rows, classes, only="capped")
        self.assertLessEqual(got["interval"][0], 0)

    def test_interference_let_through_fails(self):
        gain = {"difference": 0.5, "interval": [0.3, 0.7]}
        self.assertTrue(cv.decide(gain, gain, {"rate": 0.01, "interval": [0.0, 0.03]})["adopted"])
        self.assertFalse(cv.decide(gain, gain, {"rate": 0.03, "interval": [0.0, 0.04]})["adopted"])
        self.assertFalse(cv.decide(gain, gain, {"rate": 0.01, "interval": [0.0, 0.08]})["adopted"])

    def test_the_rate_over_runs_of_blocks(self):
        bunched = [[0] * 300 + [12] + [0] * 7]
        got = cv.false_rate(bunched)
        self.assertEqual((got["unexplained"], got["blocks"]), (12, 308))
        self.assertGreater(got["interval"][1], got["rate"])


class EndToEnd(unittest.TestCase):
    """control_c_verdict.main through the real tools on a synthetic control: four cadences, their sweep records and
    store, the protocol's draw, every planted block's record with both versions' verdicts, and the decision."""

    def setUp(self):
        import json
        import sqlite3
        import tempfile
        import control_injection as ci
        import matched
        import negative_controls as nc
        import seti
        import vetting
        self.ci, self.nc = ci, nc
        self.folder = Path(tempfile.mkdtemp(prefix="ssy-control-c-"))
        (self.folder / "sweeps").mkdir()
        (self.folder / "injection").mkdir()
        self.chosen = [{"target": t, "session": f"S{t}", "looks": [{"url": f"u{t}{i}"} for i in range(6)]} for t in "ABCD"]
        self.db_path = self.folder / "ssy.sqlite"
        db = sqlite3.connect(self.db_path)
        db.executescript("""CREATE TABLE cadences (cadence TEXT, session TEXT, target TEXT, urls TEXT);
            CREATE TABLE blocks (session TEXT, block_idx INTEGER, f_lo_mhz REAL, f_hi_mhz REAL, status TEXT);
            CREATE TABLE events (event_id INTEGER, session TEXT, block_idx INTEGER, snr REAL, f_start_mhz REAL,
                                 drift_hz_s REAL, label TEXT, superseded_run INTEGER);
            CREATE TABLE checks (event_id INTEGER, lead TEXT, name TEXT, result TEXT, version TEXT, checked_utc TEXT);""")
        control = []
        for n, c in enumerate(self.chosen):
            db.execute("INSERT INTO cadences VALUES (?,?,?,?)", (c["session"], c["session"], c["target"],
                                                                json.dumps([x["url"] for x in c["looks"]])))
            done = {}
            for k in range(12):
                db.execute("INSERT INTO blocks VALUES (?,?,?,?, 'done')", (c["session"], k, k, k + 1))
                done[str(k)] = {"complete": k % 2 == 1, "from_mhz": k, "to_mhz": k + 1,
                                "search_version": seti.SEARCH_VERSION, "events": []}
            event = 100 + n                                    # one real candidate a cadence, in block 0
            db.execute("INSERT INTO events VALUES (?,?,0,40,0.5,0,'candidate',NULL)", (event, c["session"]))
            done["0"]["events"] = [{"event_id": event, "frequency_mhz": 0.5, "drift_hz_s": 0.0, "snr": 40.0}]
            for version, verdict in ((vetting.VERSION, "likely interference (indicated: zero or very low drift)"),
                                     (vetting.VERSION_BANDS_AS_CONTEXT, "likely interference (indicated: zero or very low drift)")):
                db.executemany("INSERT INTO checks VALUES (?,?,?,?,?,?)",
                               [(event, f"L{event}", name, verdict if name == "10. report" else "x", version, version[:1])
                                for name in [f"{i}. check {i}" for i in range(1, 10)] + ["10. report"]])
            rec = {"blocks": [[k, k + 1] for k in range(12)], "done": done}
            (self.folder / "sweeps" / f"{c['target']}-{c['session']}.json").write_text(json.dumps(rec), encoding="utf-8")
            control.append((c, rec))
        db.commit()
        db.close()
        cadences = []
        for n, (c, rec) in enumerate(control):
            picked = ci.pick_blocks(rec["done"], n, ci.SEED)
            cadences.append({"target": c["target"], "session": c["session"], "urls": [x["url"] for x in c["looks"]],
                             "blocks": {str(k): {"class": v, "range": rec["blocks"][k]} for k, v in picked.items()}})
        (self.folder / "injection" / "choice.json").write_text(
            json.dumps({"seed": ci.SEED, "per_class": ci.PER_CLASS, "cadences": cadences}), encoding="utf-8")
        self.cadences, self.versions, self.tones = cadences, ci._versions_now(), matched.TONES

    def planted(self, v5_capped, v6_capped):
        import json
        for c in self.cadences:
            for k, info in c["blocks"].items():
                v5 = v5_capped if info["class"] == "capped" else "unexplained, strong"
                v6 = v6_capped if info["class"] == "capped" else "unexplained, strong"
                a = {"hit_looks": 3, "candidate": True, "already_in_the_block": False, "verdict": v5, "reasons": [],
                     "verdict_context": v6, "reasons_context": []}
                rec = {"target": c["target"], "session": c["session"], "block": int(k), "class": info["class"],
                       "versions": self.versions, "complete": [True] * 6,
                       "tones": [{"x0": float(i), "drift": 0.01 * i, "s_in": 30, "bin": 0, "at": {"30": a, "10": a}}
                                 for i in range(self.tones)]}
                (self.folder / "injection" / f"{c['target']}_{int(k):03d}.json").write_text(json.dumps(rec), encoding="utf-8")

    def decide(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ), \
                mock.patch.object(self.nc, "CONTROLS", self.folder), mock.patch.object(self.nc, "OUT", self.folder), \
                mock.patch.object(self.nc, "_choice", return_value={"chosen": self.chosen}), \
                mock.patch.object(self.ci, "OUT", self.folder / "injection"):
            return cv.main(say=lambda *a: None)

    def test_a_real_gain_with_nothing_let_through_is_adopted(self):
        self.planted("likely interference (indicated: known interference bands)", "unexplained, weak")
        got = self.decide()
        self.assertTrue(got["adopted"])
        self.assertEqual(got["planted_capped"]["difference"], 1.0)
        self.assertEqual(got["real_unexplained_by_version_6"]["unexplained"], 0)
        self.assertGreater(got["real_unexplained_by_version_6"]["poisson_upper_95"], 0)

    def test_no_gain_is_not_adopted(self):
        self.planted("likely interference (indicated: known interference bands)",
                     "likely interference (indicated: known interference bands)")
        self.assertFalse(self.decide()["adopted"])

    def test_interference_let_through_is_not_adopted(self):
        import sqlite3
        self.planted("likely interference (indicated: known interference bands)", "unexplained, weak")
        db = sqlite3.connect(self.db_path)
        with db:
            db.execute("UPDATE checks SET result='unexplained, weak' WHERE name='10. report' AND version LIKE '6%'")
        db.close()
        got = self.decide()
        self.assertFalse(got["adopted"])
        self.assertTrue(got["keeps_more_real_signals"])
        self.assertFalse(got["lets_no_more_interference_through"])

    def test_a_planted_record_by_another_version_6_is_refused(self):
        import json
        import yoke
        self.planted("likely interference (indicated: known interference bands)", "unexplained, weak")
        path = next((self.folder / "injection").glob("A_*.json"))
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["versions"] = dict(rec["versions"], checks_context="an earlier 6")
        path.write_text(json.dumps(rec), encoding="utf-8")
        with self.assertRaises(yoke.Refusal):
            self.decide()


if __name__ == "__main__":
    unittest.main()
