"""A synthetic cadence for the offline tests: six looks of Green Bank's
high-resolution layout (16 spectra, 2.79 Hz channels, 18.25 s apart),
noise only, small enough to search in seconds. No archive is read."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Nothing a test does may touch a real data folder: the tests always get a fresh one of their own, whatever
# SSY_DATA was set to, and refuse to run if a project module was loaded with another before this.
os.environ["SSY_DATA"] = tempfile.mkdtemp(prefix="ssy-test-data-")
if "yoke" in sys.modules and not str(sys.modules["yoke"].DATA).startswith(tempfile.gettempdir()):
    raise RuntimeError("yoke was imported with a real data folder before tests/synth.py; import synth first")
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
