"""A synthetic cadence for the offline tests: six looks of Green Bank's
high-resolution layout (16 spectra, 2.79 Hz channels, 18.25 s apart),
noise only, small enough to search in seconds. No archive is read."""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Nothing a test does may touch a real data folder: the tests always get a fresh one of their own, whatever
# SSY_DATA was set to, and refuse to run if a project module was loaded with another before this.
if "yoke" in sys.modules:       # loaded before this: its data folder is not this run's own, whatever it is
    raise RuntimeError("yoke was imported before tests/synth.py; import synth first, so the tests get their own "
                       "data folder")
# Every temporary folder a test run makes, its data folder among them, goes in one folder of the run's own,
# removed when the run ends.
tempfile.tempdir = tempfile.mkdtemp(prefix="ssy-tests-")


@atexit.register
def _remove_run_folder(where=tempfile.tempdir):
    try:
        import yoke
        yoke.remove_tree(where)
    except OSError:                     # a file still open: the system's cleaning gets it
        shutil.rmtree(where, ignore_errors=True)


os.environ["SSY_DATA"] = tempfile.mkdtemp(prefix="ssy-test-data-")
for p in (ROOT, ROOT / "tools", ROOT / "tools" / "bliss"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np  # noqa: E402

N_T = 16
N_F = 16384
FOFF = -2.7939677238464355e-06      # MHz a channel
TSAMP = 18.253611008
FCH1 = 2000.0
LOOK_S = 330.0                      # seconds from one look's start to the next


def cadence(seed=0):
    """Six looks as injection.trial takes them: {"s": slice, "raw", "sigma"}."""
    import measure
    rng = np.random.default_rng(seed)
    out = []
    for j in range(6):
        raw = rng.chisquare(64, size=(N_T, N_F)).astype(np.float64) * 1e3
        s = {"spectra": raw, "fch1": FCH1, "foff": FOFF, "tsamp": TSAMP, "tstart": 60000.0 + j * LOOK_S / 86400,
             "target": "SYNTH" if j % 2 == 0 else "SYNTH_OFF", "first_channel": 0, "coarse_channel": 0}
        out.append({"s": s, "raw": raw, "sigma": measure.channel_noise(raw)})
    return out


def judging_cadence(seed=5):
    """A cadence for comparing versions of the cadence test, with tones that
    reach every verdict and straddle its thresholds, so a change to either
    shows: a tone in every look (interference), one in the ON looks only
    (a candidate), one in the OFF looks only, one strong in the ON looks
    with a faint echo in the OFF looks (OFF S/N about 5.5, under OFF_MAX 6),
    and one strong in two ON looks and faint in the third (about 5.5 along
    its track, over ON_MIN 5). Returns the six looks, planted, as
    matched.our_search takes them."""
    import math
    import measure
    cad = cadence(seed)
    sigma = float(np.median(cad[1]["sigma"]))
    out = []
    for j, c in enumerate(cad):
        raw = c["raw"]
        n = math.sqrt(raw.shape[0])
        k = (c["s"]["tstart"] - cad[0]["s"]["tstart"]) * 86400 / (c["s"]["foff"] * 1e6)
        tones = [(8000.3 + 0.2 * k, 0.2, 60 * sigma / n)]
        if j in (0, 2, 4):
            tones.append((12000.7 - 0.1 * k, -0.1, 40 * sigma / n))
        if j in (1, 3, 5):
            tones.append((4000.2, 0.0, 30 * sigma / n))
        tones.append((6000.4 + 0.3 * k, 0.3, (40 if j % 2 == 0 else 8) * sigma / n))
        if j in (0, 2, 4):
            tones.append((10000.6 - 0.2 * k, -0.2, (40 if j < 4 else 11) * sigma / n))
        raw = measure.plant(raw, tones, c["s"]["tsamp"], c["s"]["foff"])
        out.append(dict(c, raw=raw, spectra=raw, s=dict(c["s"], spectra=raw)))
    return out
