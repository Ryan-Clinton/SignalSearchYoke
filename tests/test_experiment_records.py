"""tools/records.py (shared by the experiment tools): a record's code checked commit by commit, not by its version labels alone, and one worker at a
time on a block."""
import synth  # noqa: F401  (first: the tests' own data folder)

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import records  # noqa: E402


def _git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True).stdout.strip()


@unittest.skipUnless((ROOT / ".git").exists(), "needs the repository's history")
class Code(unittest.TestCase):
    def test_a_record_made_at_head_passes(self):
        self.assertEqual(records.code_problems({"git_commit": _git("rev-parse", "HEAD")}), [])

    def test_no_commit_or_an_unknown_one_is_refused(self):
        self.assertTrue(records.code_problems({}))
        self.assertTrue(records.code_problems({"git_commit": "0" * 40}))

    def test_local_changes_not_listed_are_refused(self):
        head = _git("rev-parse", "HEAD")
        self.assertTrue(records.code_problems({"git_commit": head, "uncommitted_changes": True}, dirty_ok={}))
        self.assertEqual(records.code_problems({"git_commit": head, "uncommitted_changes": True},
                                               dirty_ok={head[:7]: "listed"}), [])

    def test_a_change_to_the_science_code_since_is_refused_unless_listed(self):
        last = _git("log", "-1", "--format=%h", "--abbrev=7", "--", *records.SCIENCE)
        before = _git("rev-parse", f"{last}^")
        self.assertTrue(records.code_problems({"git_commit": before}, neutral={}))
        self.assertEqual(records.code_problems({"git_commit": before}, neutral={last: "listed"}), [])

    def test_every_listed_commit_exists(self):
        for c in list(records.NEUTRAL) + list(records.DIRTY_OK):
            self.assertTrue(_git("rev-parse", "--verify", "--quiet", f"{c}^{{commit}}"), c)


class Claim(unittest.TestCase):
    def test_one_holder_at_a_time_and_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "block_001.json"
            with records.claim(path) as a:
                self.assertTrue(a)
                with records.claim(path) as b:
                    self.assertFalse(b)
            with records.claim(path) as c:
                self.assertTrue(c)
            self.assertFalse(path.with_name(path.name + ".claim").exists())

    def test_a_claim_left_by_an_ended_process_is_taken_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "block_002.json"
            done = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True,
                                  text=True)
            path.with_name(path.name + ".claim").write_text(done.stdout.strip(), encoding="ascii")
            with records.claim(path) as mine:
                self.assertTrue(mine)

    def test_a_live_holder_keeps_its_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "block_003.json"
            path.with_name(path.name + ".claim").write_text(str(os.getpid()), encoding="ascii")
            with records.claim(path) as mine:
                self.assertFalse(mine)


if __name__ == "__main__":
    unittest.main()
