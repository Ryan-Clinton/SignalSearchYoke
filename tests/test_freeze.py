"""The freeze (docs/audits.md 17): a committed edit to a frozen config is a
deviation, every logged deviation reaches the verdict, and step 12's verdict
needs its regression."""
import json
import unittest
from unittest import mock

import synth  # noqa: F401  (paths and a throwaway data folder)

import independent
import yoke


class Freeze(unittest.TestCase):
    def setUp(self):
        independent.set_step(10)

    def test_the_real_configs_are_as_frozen(self):
        for n in (10, 12):
            independent.set_step(n)
            self.assertEqual(independent.load()[1], independent.FROZEN_CONFIGS[n][1])

    def test_an_edited_config_is_a_deviation(self):
        cfg, _ = independent.load()
        with mock.patch.object(independent, "load", return_value=(cfg, "0" * 64)), \
                mock.patch.object(independent, "fingerprint", return_value=cfg["code"]):
            with self.assertRaises(yoke.Refusal):
                independent.frozen(cfg, stage="test")

    def test_the_history_stays(self):
        independent.ROOT.mkdir(parents=True, exist_ok=True)
        log = independent.ROOT / "deviations.json"
        items = [{"utc": "2026-11-12T00:00:00Z", "stage": "measure", "problems": ["changed since the freeze: x"],
                  "why": "a fix", "git_commit": "abc1234"}]
        log.write_text(json.dumps(items), encoding="utf-8")
        try:
            self.assertEqual(independent.deviation_history(), items)
        finally:
            log.unlink()

    def test_step_12_needs_its_regression(self):
        p = yoke.DATA / "analysis" / "regress_step10.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            p.unlink()
        self.assertIn("not been run", independent.regression_problem())
        p.write_text(json.dumps({"passed": False}), encoding="utf-8")
        self.assertIn("did not pass", independent.regression_problem())
        p.write_text(json.dumps({"passed": True, "code_sha256": "stale"}), encoding="utf-8")
        self.assertIn("other code", independent.regression_problem())          # passed, but with other code
        p.write_text(json.dumps({"passed": True, "code_sha256": independent.code_sha()}), encoding="utf-8")
        self.assertIsNone(independent.regression_problem())
        p.unlink()

    def test_block_provenance(self):
        import hashlib
        folder = yoke.DATA / "matched" / "T-S"
        folder.mkdir(parents=True, exist_ok=True)
        made = {"config_sha256": "c", "code_sha256": "k", "dc_bins": "coarse channel", "sources": []}
        legacy = json.dumps({"block": 1}).encode()
        (folder / "block_001.json").write_bytes(legacy)
        (folder / "block_002.json").write_text(json.dumps({"block": 2, "made_with": made}), encoding="utf-8")
        (folder / "block_003.json").write_text(json.dumps({"block": 3, "made_with": dict(made, dc_bins="storage chunk")}),
                                               encoding="utf-8")
        listed = {"matched/T-S/block_001.json": hashlib.sha256(legacy).hexdigest()}
        bad = independent.provenance_problems(folder, [1, 2, 3], made, listed)
        self.assertEqual(len(bad), 1)
        self.assertIn("block_003", bad[0])                                     # made with another DC rule
        (folder / "block_001.json").write_bytes(json.dumps({"block": 1, "x": 0}).encode())   # changed since packaged
        self.assertEqual(len(independent.provenance_problems(folder, [1, 2], made, listed)), 1)


if __name__ == "__main__":
    unittest.main()
