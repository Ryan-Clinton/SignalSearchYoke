"""Reading (docs/audits.md 14): the coarse channel's width from the instrument,
not the storage chunks (2016's differ), the same in both readers; refusals of
a missing start time, non-finite samples and filter pipelines decode cannot
rebuild."""
import unittest

import numpy as np

import synth  # noqa: F401  (paths and a throwaway data folder)

import reading
import seti
import yoke


class Reading(unittest.TestCase):
    def test_coarse_width_from_the_instrument(self):
        y2016 = {"telescope_id": 6, "foff": -2.835503418452676e-06}
        y2017 = {"telescope_id": 6, "foff": -2.7939677238464355e-06}
        self.assertEqual(seti.coarse_width(y2016, 1 << 20), 1033216)       # 308 coarse channels of the file
        self.assertEqual(seti.coarse_width(y2017, 1 << 20), 1 << 20)
        self.assertEqual(seti.coarse_width({"telescope_id": 6, "foff": -2.79e-6, "coarse_channel": 64}, 1 << 20), 64)
        self.assertEqual(seti.coarse_width({"telescope_id": 1, "foff": 1e-6}, 16384), 16384)

    def test_dc_blanked_at_the_coarse_middle(self):
        per = 1033216
        x = np.ones((2, 40))
        first = per // 2 - 20                     # the slice holds the first coarse channel's middle
        x[:, 20] = 1e4
        seti.blank_dc(x, first, per)
        self.assertEqual(x[0, 20], 1.0)

    def test_missing_start_refused(self):
        with self.assertRaises(yoke.Refusal):
            seti.start_mjd({}, "a file")
        self.assertEqual(seti.start_mjd({"tstart": 57523.5}, "a file"), 57523.5)

    def test_non_finite_refused(self):
        x = np.ones((4, 8))
        seti.finite_or_refuse(x, "ok")
        x[1, 3] = np.nan
        with self.assertRaises(yoke.Refusal):
            seti.finite_or_refuse(x, "bad")

    def test_filter_pipelines_not_read_directly(self):
        base = {"shape": [16, 1, 64], "chunk_shape": [1, 1, 32], "dtype": "float32", "chunks": [0] * 32}
        self.assertTrue(reading.direct_ready(dict(base, filters=[(32008, 0, [])])))
        self.assertFalse(reading.direct_ready(dict(base, filters=[(2, 0, [4]), (1, 0, [4])])))


    def test_dc_rule_recorded_and_switchable(self):
        import os
        old = os.environ.pop("SSY_DC_BY_CHUNK", None)
        try:
            self.assertEqual(seti.search_params()["dc_bins"], "coarse channel")
            os.environ["SSY_DC_BY_CHUNK"] = "1"
            self.assertEqual(seti.search_params()["dc_bins"], "storage chunk")
        finally:
            os.environ.pop("SSY_DC_BY_CHUNK", None)
            if old is not None:
                os.environ["SSY_DC_BY_CHUNK"] = old
        ix16 = {"attrs": {"telescope_id": 6, "foff": -2.835503418452676e-06}, "chunk_shape": [1, 1, 1 << 20]}
        ix17 = {"attrs": {"telescope_id": 6, "foff": -2.7939677238464355e-06}, "chunk_shape": [1, 1, 1 << 20]}
        self.assertTrue(seti.dc_rules_differ([ix16]))
        self.assertFalse(seti.dc_rules_differ([ix17]))

    def test_a_changed_source_is_refused(self):
        import store
        db = store.connect()
        index = {"url": "https://example.invalid/a.h5", "etag": "\"v1\"", "size": 100, "shape": [16, 1, 64],
                 "attrs": {"tstart": 57000.0, "fch1": 1500.0, "foff": -2.79e-6, "tsamp": 18.25, "nchans": 64}}
        store.upsert_file(db, index)
        store.upsert_file(db, index)                                   # the same version again: fine
        with self.assertRaises(yoke.Refusal):
            store.upsert_file(db, dict(index, etag="\"v2\""))
        with self.assertRaises(yoke.Refusal):
            store.upsert_file(db, dict(index, size=101))
        db.close()


if __name__ == "__main__":
    unittest.main()
