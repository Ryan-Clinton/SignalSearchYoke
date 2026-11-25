"""tools/setigen_plant.py in setigen's own environment (tests/setigen_env_checks.py runs there): both frequency
orders, drift direction, where a tone is placed with and without Doppler smearing, power, signal order, alone against
together, bounding, and the axis check. Skipped where that environment is not installed (SSY_SETIGEN_PYTHON, or
%LOCALAPPDATA%/ssy-setigen)."""
import json
import os
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = Path(os.environ.get("SSY_SETIGEN_PYTHON") or Path(os.environ.get("LOCALAPPDATA", "")) / "ssy-setigen" /
              "Scripts" / "python.exe")
DT = 18.253611008


@unittest.skipUnless(PYTHON.exists(), "setigen's environment is not installed")
class SetigenPlant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        done = subprocess.run([str(PYTHON), "-I", str(HERE / "setigen_env_checks.py")], capture_output=True, text=True,
                              timeout=600)
        if done.returncode:
            raise AssertionError(done.stderr[-1500:])
        cls.r = json.loads(done.stdout)

    def test_both_frequency_orders_plant_the_same(self):
        self.assertEqual(self.r["unsmeared_orientation_max_diff"], 0.0)
        self.assertEqual(self.r["smeared_orientation_max_diff"], 0.0)

    def test_without_smearing_the_tone_sits_at_the_spectrum_start(self):
        # the first run's fault: half a spectrum's drift (18 Hz at 2 Hz/s) from where the scoring looks
        for k in ("unsmeared_offsets_hz", "unsmeared_negative_offsets_hz"):
            self.assertTrue(all(abs(v) < 1.0 for v in self.r[k]), self.r[k])

    def test_with_smearing_the_tone_sits_near_the_spectrum_middle_and_follows_the_drift_sign(self):
        half = 2.0 * DT / 2
        for v in self.r["smeared_offsets_hz"]:
            self.assertLess(abs(v - half), 2.5)          # within 2.5 Hz at 2 Hz/s; the scoring allows 6
        for v in self.r["smeared_negative_offsets_hz"]:
            self.assertLess(abs(v + half), 2.5)

    def test_a_drifting_tone_keeps_most_of_a_still_ones_power(self):
        # setigen's truncated sinc² loses more of a tone between channels: about 9%, the same with or without smearing
        for k in ("unsmeared_power_ratio_drift_to_still", "smeared_power_ratio_drift_to_still"):
            self.assertGreater(self.r[k], 0.85)
            self.assertLess(self.r[k], 1.01)

    def test_strength_does_not_depend_on_the_signals_added_before(self):
        for tag in ("unsmeared", "smeared"):
            self.assertGreater(self.r[f"{tag}_peak"], 1.0)
            self.assertLess(self.r[f"{tag}_order_max_diff"], 1e-9)
            self.assertLess(self.r[f"{tag}_alone_max_diff"], 1e-9)

    def test_bounding_a_smeared_signal_changes_nothing(self):
        self.assertLess(self.r["bounded_max_diff"], 1e-9)
        self.assertAlmostEqual(self.r["bounded_power_ratio"], 1.0, places=9)

    def test_an_axis_off_by_more_than_a_millihertz_is_refused(self):
        self.assertTrue(self.r["axis_off_refused"])


if __name__ == "__main__":
    unittest.main()
