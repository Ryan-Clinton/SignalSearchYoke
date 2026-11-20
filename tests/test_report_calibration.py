"""report.py uses a calibration record only for the session and band it was
measured for (docs/audits.md 13)."""
import importlib.util
import json
import sys
import unittest

import synth  # noqa: F401  (paths and a throwaway data folder)
import yoke

_spec = importlib.util.spec_from_file_location("report_root", str(yoke.ROOT / "report.py"))
report = importlib.util.module_from_spec(_spec)
sys.modules["report_root"] = report
_spec.loader.exec_module(report)

KIC_SCAN = "spliced_blc2021222324252627_guppi_57898_22410_DIAG_KIC8462852_0031.gpuspec.0000.h5"


def _real(name):
    p = yoke.ROOT / "data" / "measurements" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _bins(*starts):
    return {"by_50_mhz": [{"from_mhz": b, "sefd_jy": 10.0} for b in starts]}


class Applies(unittest.TestCase):
    def test_sefd_only_where_measured_bin_by_bin(self):
        full = _bins(*[b for b in range(1800, 2700, 50) if b != 2300])        # 2300-2350 inside the notch
        self.assertTrue(report.sefd_applies(full, 1820.0, 2620.0))
        self.assertFalse(report.sefd_applies(_bins(1800, 2650), 1820.0, 2600.0))   # two end bins, a gap between
        self.assertFalse(report.sefd_applies(_bins(*[b for b in range(1800, 2700, 50) if b != 2000]), 1820.0, 2620.0))
        self.assertFalse(report.sefd_applies(full, 4000.0, 7800.0))           # C band
        self.assertFalse(report.sefd_applies(None, 1820.0, 2620.0))

    def test_completeness_only_on_its_own_scans(self):
        rec = {"cadences": [f"data/reference/{KIC_SCAN[:-3]}_block153.h5", "data/reference/blocks/block040_0031.h5"]}
        mine = [{"url": "https://x/" + KIC_SCAN}]
        self.assertTrue(report.completeness_applies(rec, "KIC8462852", mine))
        other_scan = [{"url": "https://x/" + KIC_SCAN.replace("22410", "29999")}]     # same target, same day
        self.assertFalse(report.completeness_applies(rec, "KIC8462852", other_scan))
        self.assertFalse(report.completeness_applies(rec, "NGC6946", mine))

    def test_response_only_for_its_product(self):
        rec = {"channel_hz": 2.7939677238464355, "tsamp_s": 18.253611008}
        self.assertTrue(report.response_applies(rec, 2.7939677238464355, 18.253611008))
        self.assertFalse(report.response_applies(rec, 2.7939677238464355, 1.07))

    def test_the_real_records_apply_to_2017_only(self):
        import store
        sefd, comp = _real("sefd"), _real("completeness")
        if sefd is None or comp is None:
            self.skipTest("no measurement records here")
        import sqlite3
        try:
            db = store.connect_readonly()
            files = {s: [dict(r) for r in db.execute("SELECT url FROM files WHERE session=?", (s,))]
                     for s in ("AGBT17A_999_68", "AGBT19B_999_104", "AGBT16A_999_192")}
            db.close()
        except sqlite3.OperationalError:
            self.skipTest("no store here")
        if not files["AGBT17A_999_68"]:
            self.skipTest("no store here")
        self.assertTrue(report.completeness_applies(comp, "KIC8462852", files["AGBT17A_999_68"]))
        self.assertFalse(report.completeness_applies(comp, "NGC6946", files["AGBT19B_999_104"]))
        self.assertFalse(report.completeness_applies(comp, "HIP17147", files["AGBT16A_999_192"]))
        self.assertTrue(report.sefd_applies(sefd, 1820.0, 2620.0))
        self.assertFalse(report.sefd_applies(sefd, 4000.0, 7800.0))


if __name__ == "__main__":
    unittest.main()
