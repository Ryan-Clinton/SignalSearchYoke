"""The store's lifecycle (docs/audits.md 21): a block needs six looks, a
candidate's checks are saved whole, a known source version is never replaced
by an unknown one, and a changed value shows in the store's content."""
import unittest

import synth  # noqa: F401  (paths and a throwaway data folder)

import store
import yoke


def _index(url, etag='"v1"', size=100):
    return {"url": url, "etag": etag, "size": size, "shape": [16, 1, 64],
            "attrs": {"tstart": 57000.0, "fch1": 1500.0, "foff": -2.79e-6, "tsamp": 18.25, "nchans": 64}}


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.db = store.connect()
        # the tests save blocks under run 1: made here, so they do not rely on another test having made it
        if not self.db.execute("SELECT 1 FROM runs WHERE run_id=1").fetchone():
            with self.db:
                self.db.execute("INSERT INTO runs (run_id, started_utc, command) VALUES (1, ?, 'test')",
                                (store.now(),))

    def tearDown(self):
        self.db.close()

    def test_a_block_needs_six_looks(self):
        before = store.content(self.db)
        with self.assertRaises(yoke.Refusal):
            store.save_block(self.db, 1, "S", 0, 1.0, 2.0, [1, 2, 3, 4, 5, 6], [[]] * 5, [], {})
        with self.assertRaises(yoke.Refusal):
            store.save_block(self.db, 1, "S", 0, 1.0, 2.0, [1, 2, 3, 4, 5, 5], [[]] * 6, [], {})
        self.assertEqual(store.content(self.db), before)                 # nothing changed

    def test_a_second_cadence_of_a_session_refused(self):
        ids = [store.upsert_file(self.db, _index(f"https://example.invalid/c1_{i}.h5"), session="S2", position=i,
                                 is_on=i % 2 == 0) for i in range(6)]
        other = [store.upsert_file(self.db, _index(f"https://example.invalid/c2_{i}.h5")) for i in range(6)]
        before = store.content(self.db)
        with self.assertRaises(yoke.Refusal):
            store.save_block(self.db, 1, "S2", 0, 1.0, 2.0, other, [[]] * 6, [], {}, scans=[{}] * 6)
        self.assertEqual(store.content(self.db), before)
        self.assertEqual(len(ids), 6)

    def test_a_store_made_before_cadences_is_migrated(self):
        import tempfile
        from pathlib import Path
        where = Path(tempfile.mkdtemp(prefix="ssy-schema2-")) / "ssy.sqlite"
        db = store.connect(where)
        urls = [f"https://example.invalid/m_{i}.h5" for i in range(6)]
        ids = [store.upsert_file(db, _index(u), session="M", cadence_target="T", position=i, is_on=i % 2 == 0)
               for i, u in enumerate(urls)]
        with db:                                    # as a store of schema 2 has it: files only, no cadences
            db.execute("DELETE FROM cadence_files")
            db.execute("DELETE FROM cadences")
        db.close()
        db = store.connect(where)
        self.assertTrue(store.has_cadence(db, "M"))
        self.assertEqual([r["file_id"] for r in store.cadence_rows(db, "M")], ids)
        self.assertEqual(store.cadence_files(db, "T"), ("M", urls))
        self.assertEqual(store.register_cadence(db, "M", "T", urls, ids), "M")      # the same six: the same key
        db.close()

    def test_a_second_cadence_of_a_session_gets_its_own_key(self):
        first = [f"https://example.invalid/k1_{i}.h5" for i in range(6)]
        second = [f"https://example.invalid/k2_{i}.h5" for i in range(6)]
        ids1, ids2 = ([store.upsert_file(self.db, _index(u), session="K", cadence_target="T", position=i,
                                         is_on=i % 2 == 0) for i, u in enumerate(urls)] for urls in (first, second))
        k1 = store.register_cadence(self.db, "K", "T", first, ids1)
        k2 = store.register_cadence(self.db, "K", "T", second, ids2)
        self.assertEqual((k1, k2), ("K", "K-c2"))
        for key, ids in ((k1, ids1), (k2, ids2)):
            store.save_block(self.db, 1, key, 0, 1.0, 2.0, ids, [[]] * 6, [], {}, scans=[{"complete": True}] * 6)
        for key, ids in ((k1, ids1), (k2, ids2)):               # neither block superseded the other
            self.assertEqual(sorted(store.done_blocks(self.db, key)), [0])
            current = self.db.execute("SELECT file_id FROM looks WHERE session=? AND superseded_run IS NULL"
                                      " ORDER BY position", (key,)).fetchall()
            self.assertEqual([r[0] for r in current], ids)
            self.assertEqual([r["file_id"] for r in store.cadence_rows(self.db, key)], ids)
            self.assertEqual(store.cadence_session(self.db, key), "K")
        with self.assertRaises(yoke.Refusal):                   # one cadence's files under the other's key
            store.save_block(self.db, 1, k1, 1, 1.0, 2.0, ids2, [[]] * 6, [], {}, scans=[{}] * 6)

    def test_recurrence_files_as_before_with_one_cadence_a_session(self):
        import check
        for s, tgt in (("RA", "TA"), ("RB", "TB")):
            urls = [f"https://example.invalid/{s}_{i}.h5" for i in range(6)]
            ids = [store.upsert_file(self.db, _index(u), session=s, target=tgt if i % 2 == 0 else "OFF",
                                     cadence_target=tgt, position=i, is_on=i % 2 == 0) for i, u in enumerate(urls)]
            store.register_cadence(self.db, s, tgt, urls, ids)
        store.upsert_file(self.db, _index("https://example.invalid/RA_extra.h5"), session="RA")   # in no cadence

        def ids(rows):
            return sorted(r["file_id"] for r in rows)
        old = self.db.execute("SELECT file_id FROM files WHERE is_on = 0 OR session != ? OR is_on IS NULL",
                              ("RA",)).fetchall()
        self.assertEqual(ids(check.recurrence_files(self.db, "RA")), ids(old))
        for on in ((1, 3, 5), (0, 1, 2)):
            old = [r for r in self.db.execute("SELECT file_id, session, cadence_position FROM files")
                   if r["session"] != "RA" or (r["cadence_position"] is not None and r["cadence_position"] not in on)]
            self.assertEqual(ids(check.recurrence_files(self.db, "RA", on)), ids(old), on)

    def test_cadence_conflict(self):
        urls = [f"https://example.invalid/own_{i}.h5" for i in range(6)]
        for i, u in enumerate(urls):
            store.upsert_file(self.db, _index(u), session="S3", position=i, is_on=i % 2 == 0)
        self.assertFalse(store.cadence_conflict(self.db, "S3", urls))                   # its own: resumes
        self.assertTrue(store.cadence_conflict(self.db, "S3", [u.replace("own", "other") for u in urls]))
        self.assertFalse(store.cadence_conflict(self.db, "NEW", urls))                  # a new session: fine

    def test_unknown_completeness_is_not_complete(self):
        ids = [store.upsert_file(self.db, _index(f"https://example.invalid/u_{i}.h5"), session="S4", position=i,
                                 is_on=i % 2 == 0) for i in range(6)]
        for scans, want in (([{"complete": True}] * 6, 1), ([{"complete": True}] * 5 + [{"complete": False}], 0),
                            ([{"complete": True}] * 5 + [{}], None), ([{"complete": True}] * 5 + [{"complete": None}], None)):
            store.save_block(self.db, 1, "S4", 0, 1.0, 2.0, ids, [[]] * 6, [], {}, scans=scans)
            got = self.db.execute("SELECT complete FROM blocks WHERE session='S4' AND block_idx=0").fetchone()[0]
            self.assertEqual(got, want, scans)

    def test_checks_saved_whole(self):
        checks = [{"n": n, "name": f"c{n}", "result": "r", "strength": None, "evidence": {}} for n in range(1, 11)]
        store.save_checks(self.db, "L", checks[:3], "v", 77)              # as a run cut off would have left
        self.assertNotIn(77, store.checked_events(self.db, "v", 10))
        with self.db:                                                     # the rest from another evaluation
            self.db.executemany("INSERT INTO checks (event_id, lead, name, result, strength, evidence, version,"
                                " checked_utc) VALUES (?,?,?,?,?,?,?,?)",
                                [(77, "L", f"{c['n']}. {c['name']}", "r", None, "{}", "v", "2099-01-01T00:00:00+00:00")
                                 for c in checks[3:]])
        self.assertNotIn(77, store.checked_events(self.db, "v", 10))      # two halves are not one whole set
        store.save_checks(self.db, "L", checks, "v", 78)
        self.assertIn(78, store.checked_events(self.db, "v", 10))

    def test_a_known_source_version_kept(self):
        url = "https://example.invalid/lifecycle.h5"
        store.upsert_file(self.db, _index(url))
        with self.assertRaises(yoke.Refusal):
            store.upsert_file(self.db, _index(url, etag=None))           # unknown where it was known
        with self.assertRaises(yoke.Refusal):
            store.upsert_file(self.db, _index(url, etag='"v2"'))

    def test_a_changed_value_shows(self):
        store.save_checks(self.db, "L", [{"n": 1, "name": "c", "result": "r", "strength": None, "evidence": {}}],
                          "v", 90)
        before = store.content(self.db)
        with self.db:
            self.db.execute("UPDATE checks SET result='changed' WHERE event_id=90")
        self.assertNotEqual(store.content(self.db), before)

    def test_occupancy_follows_a_change_in_completeness(self):
        import occupancy
        with self.db:
            self.db.execute("INSERT INTO blocks (session, block_idx, status, run_id, complete) VALUES ('R', 0, 'done', 1, 1)")
        before = occupancy.revision(self.db, "R")
        with self.db:
            self.db.execute("UPDATE blocks SET complete=0 WHERE session='R' AND block_idx=0")   # same run, no hits
        self.assertNotEqual(occupancy.revision(self.db, "R"), before)

    def test_integrity(self):
        self.assertEqual(store.integrity(self.db), [])


class Expected(unittest.TestCase):
    def test_every_table_command_has_its_outputs(self):
        import sys
        sys.path.insert(0, str(yoke.ROOT / "tools"))
        import evidence
        self.assertEqual(set(evidence.EXPECTED), set(evidence.TABLES))


if __name__ == "__main__":
    unittest.main()
