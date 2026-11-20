"""Records and the store, in a temporary folder: yoke.write keeps a record
whole or not at all; store.connect makes its schema; a read-only connection
cannot write."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import synth

import store
import yoke


class _Unwritable:
    """A value json cannot write: yoke.jsonable's str() of it fails."""
    def __str__(self):
        raise ValueError("cannot be written")


class Write(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ssy-test-"))

    def test_written_whole(self):
        p = self.tmp / "sub" / "r.json"
        yoke.write(p, {"a": 1})
        self.assertEqual(json.loads(p.read_text(encoding="utf-8")), {"a": 1})
        self.assertFalse(p.with_name(p.name + ".part").exists())

    def test_failed_write_leaves_the_old_record(self):
        p = self.tmp / "r.json"
        yoke.write(p, {"a": 1})
        with self.assertRaises(ValueError):
            yoke.write(p, {"a": 2, "bad": _Unwritable()})
        self.assertEqual(json.loads(p.read_text(encoding="utf-8")), {"a": 1})

    def test_stamp(self):
        rec = yoke.write(self.tmp / "s.json", {"a": 1}, stamp=True)
        self.assertIn("libraries", rec["provenance"])


class Store(unittest.TestCase):
    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="ssy-test-")) / "ssy.sqlite"

    def test_schema(self):
        db = store.connect(self.where)
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("runs", "files", "blocks", "hits", "events", "checks", "injections"):
            self.assertIn(t, tables)
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], store.SCHEMA_VERSION)
        for table, column, _ in store.MIGRATIONS:
            self.assertIn(column, {r[1] for r in db.execute(f"PRAGMA table_info({table})")})
        db.close()
        store.connect(self.where).close()          # connecting again migrates nothing and fails nothing

    def test_readonly_cannot_write(self):
        store.connect(self.where).close()
        ro = store.connect_readonly(self.where)
        before = store.content(ro)
        with self.assertRaises(sqlite3.OperationalError):
            ro.execute("INSERT INTO runs (command) VALUES ('x')")
        self.assertEqual(store.content(ro), before)
        ro.close()

    def test_default_store_is_not_the_projects(self):
        self.assertNotEqual(store.path().resolve().parent, (synth.ROOT / "data").resolve())



class SessionTarget(unittest.TestCase):
    """matched.run vets each session's candidates at its own target's place on the sky."""

    def test_each_session_gets_its_own_target(self):
        import sqlite3
        import matched
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE files (session TEXT, cadence_position INTEGER, cadence_target TEXT, target TEXT, "
                   "ra_hours REAL, dec_degrees REAL)")
        db.execute("INSERT INTO files VALUES ('A', 0, 'KIC8462852', 'KIC8462852', 20.104292, 44.456833)")
        db.execute("INSERT INTO files VALUES ('A', 1, NULL, 'OFF1', 1.0, 2.0)")
        db.execute("INSERT INTO files VALUES ('B', 0, 'HIP17147', 'HIP17147', 3.67, 42.58)")
        a, b = matched.session_target(db, "A"), matched.session_target(db, "B")
        self.assertEqual((a["name"], a["ra_hours"]), ("KIC8462852", 20.104292))
        self.assertEqual((b["name"], b["ra_hours"], b["dec_deg"]), ("HIP17147", 3.67, 42.58))

    def test_gps_l3_is_an_annotation_not_a_band(self):
        import vetting
        self.assertIn("GPS L3", vetting.known_rfi(1378.5))
        self.assertFalse(any(lo <= 1378.5 <= hi for lo, hi, _ in vetting.BANDS))


if __name__ == "__main__":
    unittest.main()
