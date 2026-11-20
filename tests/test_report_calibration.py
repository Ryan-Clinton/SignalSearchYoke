"""report.py uses a calibration record only for the session and band it was
measured for (docs/audits.md 13)."""
import json
import unittest

import synth  # noqa: F401  (paths and a throwaway data folder)

import yoke  # noqa: E402
import importlib.util  # noqa: E402
import sys  # noqa: E402

_spec = importlib.util.spec_from_file_location("report_root", str(yoke.ROOT / "report.py"))
report = importlib.util.module_from_spec(_spec)
sys.modules["report_root"] = report
_spec.loader.exec_module(report)


def _real(name):
    p = yoke.ROOT / "data" / "measurements" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


class Applies(unittest.TestCase):
    def test_sefd_only_in_its_band(self):
        rec = {"by_50_mhz": [{"from_mhz": 1800, "sefd_jy": 11.5}, {"from_mhz": 2650, "sefd_jy": 13.5}]}
        self.assertTrue(report.sefd_applies(rec, 1820.0, 2600.0))
        self.assertFalse(report.sefd_applies(rec, 4000.0, 7800.0))      # C band
        self.assertFalse(report.sefd_applies(rec, 1100.0, 1900.0))      # L band, part outside
        self.assertFalse(report.sefd_applies(None, 1820.0, 2600.0))

    def test_completeness_only_on_its_cadence(self):
        rec = {"cadences": ["data/reference/spliced_x_guppi_57898_22410_DIAG_KIC8462852_0031.h5"]}
        kic = [{"tstart_mjd": 57898.26}]
        self.assertTrue(report.completeness_applies(rec, "KIC8462852", kic))
        self.assertFalse(report.completeness_applies(rec, "NGC6946", [{"tstart_mjd": 58819.1}]))
        self.assertFalse(report.completeness_applies(rec, "KIC8462852", [{"tstart_mjd": 58000.1}]))

    def test_response_only_for_its_product(self):
        rec = {"channel_hz": 2.7939677238464355, "tsamp_s": 18.253611008}
        self.assertTrue(report.response_applies(rec, 2.7939677238464355, 18.253611008))
        self.assertFalse(report.response_applies(rec, 2.7939677238464355, 1.07))

    def test_the_real_records_apply_to_2017_only(self):
        sefd, comp = _real("sefd"), _real("completeness")
        if sefd is None or comp is None:
            self.skipTest("no measurement records here")
        self.assertTrue(report.sefd_applies(sefd, 1820.0, 2620.0))
        self.assertFalse(report.sefd_applies(sefd, 4000.0, 7800.0))
        self.assertTrue(report.completeness_applies(comp, "KIC8462852", [{"tstart_mjd": 57898.26}]))
        self.assertFalse(report.completeness_applies(comp, "NGC6946", [{"tstart_mjd": 58819.1}]))


if __name__ == "__main__":
    unittest.main()
