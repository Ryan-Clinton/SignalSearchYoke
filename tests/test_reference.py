"""A reference output for the search: one seeded synthetic look with three
planted tones, and every hit the search gives on it, committed in
reference_hits.json. A change to the search that moves any hit (its
channel, drift, width, shadow flag, or its S/N by more than 0.05) fails
here, offline, before anything is run on the archive.

The real standard stays the measured records (docs/reproducing-results.md);
this only says at once that the search's output changed. When a change is
meant to move it, the search's version goes up and the reference is written
again, in the same commit:

    python tests/test_reference.py --write
"""
import json
import sys
import unittest
from pathlib import Path

import synth

import measure
import searching
import seti

FIXTURE = Path(__file__).with_name("reference_hits.json")
TONES = ((2000.4, 0.0, 30), (7000.7, 1.2, 20), (12000.2, -2.5, 60))     # channel, Hz/s, S_in
KEEP = ("channel", "drift_hz_s", "snr", "width_channels", "shadow")


def hits():
    look = synth.cadence(seed=11)[0]
    raw, sigma = look["raw"], look["sigma"]
    n_t = raw.shape[0] ** 0.5
    tones = [(x0, drift, s_in * sigma[int(x0)] / n_t) for x0, drift, s_in in TONES]
    spectra = measure.plant(raw, tones, synth.TSAMP, synth.FOFF)
    found = searching.search(spectra, synth.FOFF, synth.TSAMP, synth.FCH1)
    return [{k: h[k] for k in KEEP} for h in sorted(found, key=lambda h: (h["channel"], h["drift_hz_s"]))]


class Reference(unittest.TestCase):
    def test_hits_match_the_reference(self):
        ref = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(ref["search_version"], seti.SEARCH_VERSION,
                         "the search's version changed: write the reference again (see the docstring)")
        got = hits()
        self.assertEqual(len(got), len(ref["hits"]), got)
        for g, r in zip(got, ref["hits"]):
            with self.subTest(channel=r["channel"], drift=r["drift_hz_s"]):
                for k in ("channel", "drift_hz_s", "width_channels", "shadow"):
                    self.assertEqual(g[k], r[k], k)
                self.assertAlmostEqual(g["snr"], r["snr"], delta=0.05)


if __name__ == "__main__":
    if "--write" in sys.argv:
        FIXTURE.write_text(json.dumps({"search_version": seti.SEARCH_VERSION, "tones": TONES,
                                       "hits": hits()}, indent=1) + "\n", encoding="utf-8")
        print(f"{FIXTURE}: written")
    else:
        unittest.main()
