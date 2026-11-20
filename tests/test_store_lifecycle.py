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

    def tearDown(self):
        self.db.close()

    def test_a_block_needs_six_looks(self):
        before = store.content(self.db)
        with self.assertRaises(yoke.Refusal):
            store.save_block(self.db, 1, "S", 0, 1.0, 2.0, [1, 2, 3, 4, 5, 6], [[]] * 5, [], {})
        with self.assertRaises(yoke.Refusal):
            store.save_block(self.db, 1, "S", 0, 1.0, 2.0, [1, 2, 3, 4, 5, 5], [[]] * 6, [], {})
        self.assertEqual(store.content(self.db), before)                 # nothing changed

    def test_checks_saved_whole(self):
        checks = [{"n": n, "name": f"c{n}", "result": "r", "strength": None, "evidence": {}} for n in range(1, 11)]
        store.save_checks(self.db, "L", checks[:3], "v", 77)              # as a run cut off would have left
        self.assertNotIn(77, store.checked_events(self.db, "v", 10))
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
