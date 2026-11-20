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
        errors = []

        def go(i):
            try:
                for _ in range(20):
                    yoke.write(path, {"writer": i, "pad": "x" * 20000}, indent=None)
            except Exception as e:      # noqa: BLE001 (every writer's failure is the finding)
                errors.append(repr(e))
        ts = [threading.Thread(target=go, args=(i,)) for i in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errors, [])
        self.assertTrue(yoke.whole(path))
        self.assertEqual([p.name for p in self.d.iterdir()], ["same.json"])      # no temporary file left

    def test_writers_in_separate_processes(self):
        import subprocess
        import sys
        path = self.d / "proc.json"
        code = ("import sys; sys.path.insert(0, r'%s'); import yoke\n"
                "for _ in range(15): yoke.write(r'%s', {'w': sys.argv[1], 'pad': 'y' * 50000}, indent=None)"
                % (yoke.ROOT, path))
        ps = [subprocess.Popen([sys.executable, "-c", code, str(i)], stderr=subprocess.PIPE) for i in range(4)]
        errs = [p.communicate()[1].decode(errors="replace") for p in ps]
        self.assertEqual([p.returncode for p in ps], [0, 0, 0, 0], errs)
        self.assertTrue(yoke.whole(path))
        self.assertEqual([p.name for p in self.d.iterdir()], ["proc.json"])

    def test_an_incomplete_record_is_set_aside(self):
        path = self.d / "block_008.json"
        path.write_text(json.dumps({"block": 7}), encoding="utf-8")            # parses, but not block 8's results
        self.assertFalse(yoke.whole(path, lambda r: r.get("block") == 8 and "tones" in r))
        self.assertEqual(len(list(self.d.glob("block_008.json.bad-*"))), 1)

    def test_a_broken_record_is_set_aside(self):
        path = self.d / "block_007.json"
        path.write_text('{"block": 7, "tones": [', encoding="utf-8")              # cut off mid-write
        self.assertFalse(yoke.whole(path))
        self.assertFalse(path.exists())
        self.assertEqual(len(list(self.d.glob("block_007.json.bad-*"))), 1)
        self.assertFalse(yoke.whole(self.d / "absent.json"))


if __name__ == "__main__":
    unittest.main()
