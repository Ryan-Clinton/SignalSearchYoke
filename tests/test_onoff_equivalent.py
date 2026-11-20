"""onoff.py versions listed in matched.ONOFF_EQUIVALENT judge the matched
pipeline's cadences exactly as the current one: every one of the 20 choices
of ON looks, every field of every event (the DOT score too), on a cadence
whose tones straddle OFF_MAX and ON_MIN (tests/test_planted_faults.py shows
moving either changes the verdicts on it). The earlier
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
        import matched
        import onoff
        planted = synth.judging_cadence(5)    # its thresholds straddled, so a change to them shows
        searched = matched.our_search(planted)
        self.assertTrue(matched.ONOFF_EQUIVALENT)
        for commit in sorted(set(matched.ONOFF_EQUIVALENT.values())):
            old = _old(commit)
            if old is None:
                # Skipped only where there is no git at all; in a clone without the commit (a shallow checkout)
                # it fails, so a run that did not compare cannot pass as one that did.
                import shutil
                if shutil.which("git") and (ROOT / ".git").exists():
                    self.fail(f"onoff.py at {commit} is not in this clone (a shallow checkout?): fetch the history")
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
