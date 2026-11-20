"""Records written whole by many writers at once, and a broken record set aside
rather than taken as done (docs/audits.md 20)."""
import json
import tempfile
import threading
import unittest
from pathlib import Path

import synth  # noqa: F401  (paths and a throwaway data folder)

import yoke


class Atomic(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ssy-atomic-"))

    def test_compact_records_unchanged(self):
        rec = {"block": 3, "tones": [{"s_in": 30, "drift": -0.25}], "ok": None}
        yoke.write(self.d / "b.json", rec, indent=None)
        self.assertEqual((self.d / "b.json").read_text(encoding="utf-8"), json.dumps(rec))

    def test_many_writers_one_whole_record(self):
        path = self.d / "same.json"

        def go(i):
            for _ in range(20):
                yoke.write(path, {"writer": i, "pad": "x" * 20000}, indent=None)
        ts = [threading.Thread(target=go, args=(i,)) for i in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertTrue(yoke.whole(path))
        self.assertEqual([p.name for p in self.d.iterdir()], ["same.json"])      # no temporary file left

    def test_a_broken_record_is_set_aside(self):
        path = self.d / "block_007.json"
        path.write_text('{"block": 7, "tones": [', encoding="utf-8")              # cut off mid-write
        self.assertFalse(yoke.whole(path))
        self.assertFalse(path.exists())
        self.assertEqual(len(list(self.d.glob("block_007.json.bad-*"))), 1)
        self.assertFalse(yoke.whole(self.d / "absent.json"))


if __name__ == "__main__":
    unittest.main()
