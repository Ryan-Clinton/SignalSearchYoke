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
        p.write_text(json.dumps({"passed": True}), encoding="utf-8")
        self.assertIsNone(independent.regression_problem())
        p.unlink()


if __name__ == "__main__":
    unittest.main()
