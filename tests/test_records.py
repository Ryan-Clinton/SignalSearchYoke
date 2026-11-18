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


if __name__ == "__main__":
    unittest.main()
