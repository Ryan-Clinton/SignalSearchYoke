"""onoff.py versions listed in matched.ONOFF_EQUIVALENT judge the matched
pipeline's cadences exactly as the current one: every one of the 20 choices
of ON looks, every field of every event (the DOT score too). The earlier
version comes from git; the test is skipped without it."""
import importlib.util
import itertools
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

import synth

ROOT = Path(__file__).resolve().parents[1]


def _old(commit):
    try:
        src = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:onoff.py"], capture_output=True,
                             check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    d = Path(tempfile.mkdtemp())
    (d / "onoff_old.py").write_bytes(src)
    spec = importlib.util.spec_from_file_location("onoff_old", d / "onoff_old.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["onoff_old"] = mod
    spec.loader.exec_module(mod)
    return mod


def _plain(ev):
    return {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in ev.items()}


class Equivalent(unittest.TestCase):
    def test_listed_versions_judge_alike(self):
        import math
        import matched
        import measure
        import onoff
        cad = synth.cadence(5)
        sigma = float(np.median(cad[1]["sigma"]))
        planted = []
        for j, c in enumerate(cad):
            raw = c["raw"]
            dt = (c["s"]["tstart"] - cad[0]["s"]["tstart"]) * 86400
            tones = [(8000.3 + 0.2 * dt / (c["s"]["foff"] * 1e6), 0.2, 60 * sigma / math.sqrt(raw.shape[0]))]
            if j in (0, 2, 4):
                tones.append((12000.7 - 0.1 * dt / (c["s"]["foff"] * 1e6), -0.1, 40 * sigma / math.sqrt(raw.shape[0])))
            if j in (1, 3, 5):
                tones.append((4000.2, 0.0, 30 * sigma / math.sqrt(raw.shape[0])))
            raw = measure.plant(raw, tones, c["s"]["tsamp"], c["s"]["foff"])
            planted.append(dict(c, raw=raw, spectra=raw, s=dict(c["s"], spectra=raw)))
        searched = matched.our_search(planted)
        self.assertTrue(matched.ONOFF_EQUIVALENT)
        for commit in sorted(set(matched.ONOFF_EQUIVALENT.values())):
            old = _old(commit)
            if old is None:
                self.skipTest("git not available")
            checked = 0
            for ons in itertools.combinations(range(6), 3):
                for cut in (10, 30):
                    caches = [{} for _ in range(6)]
                    looks, new_events, _ = matched.our_events(planted, searched, ons, cut, caches)
                    try:
                        matched.onoff = old
                        _, old_events, _ = matched.our_events(planted, searched, ons, cut, [{} for _ in range(6)])
                    finally:
                        matched.onoff = onoff
                    self.assertEqual([_plain(e) for e in new_events], [_plain(e) for e in old_events], (commit, ons, cut))
                    checked += len(new_events)
            self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
