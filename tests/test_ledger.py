"""tools/ledger.py: each way a ledger row can be wrong is caught (docs/audits.md 25: a check is shown to
fail on a wrong input, not only to pass on a right one)."""
import synth  # noqa: F401  (first: the tests' own data folder)

import json
import tempfile
import unittest
from pathlib import Path

import ledger

TABLE = """# Plan

## Evidence for the material findings

| Finding | Audit | Result | Made at | Command |
|---|---|---|---|---|
| A clean one | 6 | `data/analysis/a.json` | `abc1234`, clean | `tools/x.py records` |
| One with local changes | 2 | `data/analysis/b.json` | `abc1234`, local changes (diff not kept) | `tools/y.py` |

## Next section
| Not | a | ledger | row | here |
"""


def _write(data, name, commit, changed=False, diff=None, command=None):
    p = data / "analysis" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"provenance": {"git_commit": commit, "uncommitted_changes": changed,
                                            "uncommitted_diff_sha256": diff, "command": command}}), encoding="utf-8")


class Ledger(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="ssy-ledger-"))
        self.rows = ledger.rows(TABLE)

    def check(self, i):
        return ledger.problems(self.rows[i], self.data, ancestor=lambda c: c.startswith("abc1234"))

    def test_rows_parsed_and_only_the_ledgers(self):
        self.assertEqual([r["result"] for r in self.rows], ["data/analysis/a.json", "data/analysis/b.json"])
        self.assertEqual(self.rows[1]["state"], "local changes")

    def test_a_right_row_holds(self):
        _write(self.data, "a.json", "abc1234" + "0" * 33, command=["tools/x.py", "records"])
        _write(self.data, "b.json", "abc1234" + "0" * 33, changed=True, diff="d" * 64)
        self.assertEqual(self.check(0), [])
        self.assertEqual(self.check(1), [])

    def test_each_wrong_row_fails(self):
        self.assertIn("not there", self.check(0)[0])                                    # missing
        _write(self.data, "a.json", "fff0000" + "0" * 33)
        self.assertIn("not abc1234", self.check(0)[0])                                  # another commit
        _write(self.data, "a.json", "abc1234" + "0" * 33, changed=True)
        self.assertTrue(any("not clean" in b for b in self.check(0)))                   # wrong state
        _write(self.data, "a.json", "abc1234" + "0" * 33, command=["tools/z.py"])
        self.assertTrue(any("made by tools/z.py" in b for b in self.check(0)))         # another command
        (self.data / "analysis" / "a.json").write_text("{", encoding="utf-8")
        self.assertIn("does not parse", self.check(0)[0])                               # broken
        _write(self.data, "a.json", "abc1234" + "0" * 33)
        self.assertEqual(ledger.problems(self.rows[0], self.data, ancestor=lambda c: False),
                         ["abc1234 is not in this checkout's history"])               # not in history

    def test_local_changes_need_the_diff_or_say_so(self):
        row = dict(self.rows[1], note="")
        _write(self.data, "b.json", "abc1234" + "0" * 33, changed=True, diff="e" * 64)
        self.assertTrue(any("diff is not kept" in b for b in
                            ledger.problems(row, self.data, ancestor=lambda c: True)))
        kept = self.data / "provenance" / "diffs" / ("e" * 64 + ".patch")
        kept.parent.mkdir(parents=True)
        kept.write_text("diff", encoding="utf-8")
        self.assertEqual(ledger.problems(row, self.data, ancestor=lambda c: True), [])

    def test_a_checkout_changed_while_running_must_be_said(self):
        row = dict(self.rows[0], note="")
        p = self.data / "analysis" / "a.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"provenance": {"git_commit": "abc1234" + "0" * 33, "uncommitted_changes": False,
                                                "code_changed_while_running": {"git_commit": "fff" + "0" * 37}}}),
                     encoding="utf-8")
        self.assertTrue(any("changed while it ran" in b for b in
                            ledger.problems(row, self.data, ancestor=lambda c: True)))
        said = dict(row, note=" (changed while running: later commits loaded nothing it used)")
        self.assertEqual(ledger.problems(said, self.data, ancestor=lambda c: True), [])


if __name__ == "__main__":
    unittest.main()
