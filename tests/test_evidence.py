"""The evidence package's checks catch what they are for: a zip with an entry
changed, added or missing, or no store, is refused; a reproduction with an
output missing, new or changed in anything but its stamps fails; and a
record's provenance notices a changed tracked file of any kind, not only
code."""
import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import synth  # noqa: F401  (sets SSY_DATA to a fresh folder)

import evidence
import yoke


def rewrite(src, dst, drop=(), change=None, add=None):
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(dst, "w") as b:
        for n in a.namelist():
            if n in drop:
                continue
            raw = a.read(n)
            if change and n == change[0]:
                raw = change[1]
            b.writestr(n, raw)
        if add:
            b.writestr(*add)


class Package(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="ssy-evidence-test-"))
        data = yoke.DATA
        (data / "measurements").mkdir(parents=True, exist_ok=True)
        (data / "measurements" / "m.json").write_text('{"found": 4520}', encoding="utf-8")
        (data / "measurements" / "b.json").write_text(json.dumps(
            {"found": 7, "provenance": {"response": "/home/someone/ssy/gbt.f32", "host": "A-PC",
                                        "win": "C:\\Users\\Someone\\x.txt"}}), encoding="utf-8")
        db = sqlite3.connect(data / evidence.STORE)
        db.execute("CREATE TABLE IF NOT EXISTS runs (run_id INTEGER PRIMARY KEY, host TEXT, command TEXT)")
        db.execute("INSERT INTO runs (host, command) VALUES ('A-PC', 'sweep X')")
        db.commit()
        db.close()
        cls.zip = evidence.build(cls.tmp / "out", say=lambda *a: None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def check(self, path):
        return evidence.check(path, say=lambda *a: None)

    def test_whole_package_passes(self):
        self.assertTrue(self.check(self.zip))
        man = json.loads(zipfile.ZipFile(self.zip).read("MANIFEST.json"))
        self.assertEqual(man["store"]["computer_names"], [evidence.COMPUTER])
        self.assertNotIn("ssy.sqlite", man["not_included"])

    def test_machine_names_taken_out_and_nothing_else(self):
        z = zipfile.ZipFile(self.zip)
        man = json.loads(z.read("MANIFEST.json"))
        rec = json.loads(z.read("data/measurements/b.json"))
        self.assertEqual(rec, {"found": 7, "provenance": {"response": "~/ssy/gbt.f32", "host": evidence.COMPUTER,
                                                          "win": "~\\x.txt"}})
        self.assertEqual(z.read("data/measurements/m.json"), b'{"found": 4520}')
        rows = {r["path"]: r for r in man["files"]}
        self.assertIn("original_sha256", rows["measurements/b.json"])
        self.assertNotIn("original_sha256", rows["measurements/m.json"])
        self.assertEqual(man["machine_names_substituted"]["store_runs_changed"], 1)
        store = z.read("data/" + evidence.STORE)
        self.assertNotIn(b"A-PC", store)

    def test_changed_entry_refused(self):
        bad = self.tmp / "changed.zip"
        rewrite(self.zip, bad, change=("data/measurements/m.json", b'{"found": 4521}'))
        self.assertFalse(self.check(bad))

    def test_unlisted_entry_refused(self):
        bad = self.tmp / "extra.zip"
        rewrite(self.zip, bad, add=("data/measurements/extra.json", b"{}"))
        self.assertFalse(self.check(bad))

    def test_missing_store_refused(self):
        bad = self.tmp / "nostore.zip"
        rewrite(self.zip, bad, drop=("data/" + evidence.STORE,))
        self.assertFalse(self.check(bad))

    def test_missing_record_refused(self):
        bad = self.tmp / "norecord.zip"
        rewrite(self.zip, bad, drop=("data/measurements/m.json",))
        self.assertFalse(self.check(bad))


class Compare(unittest.TestCase):
    def rec(self, **kw):
        r = {"found": 4520, "record": "a", "provenance": {"git_commit": "abc"}, "written_utc": "2026-11-18T00:00:00Z"}
        r.update(kw)
        return json.dumps(r).encode()

    def test_stamps_only_is_the_same(self):
        res = evidence.compare({"m.json": self.rec()},
                               {"m.json": self.rec(provenance={"git_commit": "def"}, written_utc="2027-01-01T00:00:00Z")})
        self.assertEqual((res["same"], res["changed"], res["missing"], res["new"]), (1, [], [], []))

    def test_changed_value_fails(self):
        res = evidence.compare({"m.json": self.rec()}, {"m.json": self.rec(found=4521)})
        self.assertEqual(len(res["changed"]), 1)

    def test_a_field_named_record_is_compared(self):
        res = evidence.compare({"m.json": self.rec()}, {"m.json": self.rec(record="b")})
        self.assertEqual(len(res["changed"]), 1)

    def test_added_field_fails(self):
        res = evidence.compare({"m.json": self.rec()}, {"m.json": self.rec(extra=1)})
        self.assertEqual(len(res["changed"]), 1)

    def test_missing_and_new_outputs_fail(self):
        res = evidence.compare({"a.md": b"x", "b.md": b"y"}, {"a.md": b"x", "c.md": b"z"})
        self.assertEqual((res["missing"], res["new"]), (["b.md"], ["c.md"]))

    def test_page_stamp_ignored_but_other_times_are_not(self):
        old = b"Written by `x` (2026-11-18T13:42:14Z).\n- m.json: written 2026-11-18T13:42:14Z, commit 5fbaa17\n4,520\n"
        new = b"Written by `x` (2027-01-01T00:00:00Z).\n- m.json: written 2027-01-01T00:00:00Z, commit None\n4,520\n"
        self.assertEqual(evidence.compare({"r.md": old}, {"r.md": new})["same"], 1)
        worse = new.replace(b"4,520", b"4,521")
        self.assertEqual(len(evidence.compare({"r.md": old}, {"r.md": worse})["changed"]), 1)
        obs = {"r.md": b"observed 2017-05-25T06:13:00Z\n"}
        moved = {"r.md": b"observed 2017-05-26T06:13:00Z\n"}          # an observation's time is compared
        self.assertEqual(len(evidence.compare(obs, moved)["changed"]), 1)

    def test_provenance_compared_but_for_when_and_where(self):
        a = self.rec(provenance={"git_commit": "abc", "python": "3.12.1", "input_sha256": "aa"})
        b = self.rec(provenance={"git_commit": "def", "python": "3.13.0", "input_sha256": "aa"})
        self.assertEqual(evidence.compare({"m.json": a}, {"m.json": b})["same"], 1)
        c = self.rec(provenance={"git_commit": "def", "python": "3.13.0", "input_sha256": "bb"})
        self.assertEqual(len(evidence.compare({"m.json": a}, {"m.json": c})["changed"]), 1)

    def test_a_command_that_writes_nothing_fails(self):
        cmd = ("matched.py", "tables", "KIC8462852")
        page = b"# t\n\nWritten by `matched.py tables KIC8462852` from runs.\n"
        self.assertEqual(evidence.not_made_again({cmd: ["p.md"]}, {"p.md": page}), [])
        self.assertTrue(evidence.not_made_again({cmd: []}, {"p.md": page}))
        other = ("tools/report.py",)
        self.assertEqual(evidence.not_made_again({cmd: ["q.md"], other: ["r.md"]}, {"p.md": page}),
                         ["not made again by matched.py tables KIC8462852: p.md"])

    def test_other_commits_on_a_page_are_compared(self):
        res = evidence.compare({"p.md": b"BLISS at commit 2b98afe\n"}, {"p.md": b"BLISS at commit 1111111\n"})
        self.assertEqual(len(res["changed"]), 1)


class Provenance(unittest.TestCase):
    def test_a_changed_config_file_is_noticed(self):
        repo = Path(tempfile.mkdtemp(prefix="ssy-prov-test-"))
        try:
            git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
            subprocess.run(git + ["init", "-q"], check=True)
            (repo / "step10.json").write_text('{"cut": 30}', encoding="utf-8")
            subprocess.run(git + ["add", "."], check=True)
            subprocess.run(git + ["commit", "-q", "-m", "x"], check=True)
            with mock.patch.object(yoke, "ROOT", repo):
                clean = yoke.provenance()
                (repo / "step10.json").write_text('{"cut": 20}', encoding="utf-8")
                one = yoke.provenance()
                (repo / "step10.json").write_text('{"cut": 10}', encoding="utf-8")
                two = yoke.provenance()
            self.assertIs(clean["uncommitted_changes"], False)
            self.assertIsNone(clean["uncommitted_diff_sha256"])
            self.assertIs(one["uncommitted_changes"], True)
            self.assertNotEqual(one["uncommitted_diff_sha256"], two["uncommitted_diff_sha256"])
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_a_long_run_names_the_code_it_started_with(self):
        repo = Path(tempfile.mkdtemp(prefix="ssy-prov-test-"))
        try:
            git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
            subprocess.run(git + ["init", "-q"], check=True)
            (repo / "a.py").write_text("x = 1" + chr(10), encoding="utf-8")
            subprocess.run(git + ["add", "."], check=True)
            subprocess.run(git + ["commit", "-q", "-m", "one"], check=True)
            with mock.patch.object(yoke, "ROOT", repo), mock.patch.dict(yoke._STARTED, {repo: yoke._code_state(repo)}):
                first = yoke._STARTED[repo][0]
                self.assertNotIn("code_changed_while_running", yoke.provenance())
                (repo / "a.py").write_text("x = 2" + chr(10), encoding="utf-8")
                subprocess.run(git + ["commit", "-q", "-am", "two"], check=True)
                later = yoke.provenance()
            self.assertEqual(later["git_commit"], first)                 # what the process loaded
            self.assertIs(later["uncommitted_changes"], False)
            moved = later["code_changed_while_running"]
            self.assertNotEqual(moved["git_commit"], first)              # what the checkout held when written
        finally:
            yoke.remove_tree(repo)


if __name__ == "__main__":
    unittest.main()
