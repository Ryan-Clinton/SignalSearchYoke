"""Run in turboSETI's environment: on a cadence's six slices with hotspots,
pickles' pickler_wrapper exactly as published against the same call with
tools/pickles_block.py's one change (the module global `h5_files`), both
with its interference bands unmasked; the two score tables must be the same.

    python tools/pickles_check.py PICKLES OUT.json ON1.h5 OFF1.h5 ON2.h5 OFF2.h5 ON3.h5 OFF3.h5
"""
import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import numpy as np

source, out = Path(sys.argv[1]), Path(sys.argv[2])
files = [str(Path(p).resolve()) for p in sys.argv[3:]]
COLS = ["Index", "Freq", "k1", "k2", "k3", "k4", "k5", "k6", "k_score", "drift1", "drift2", "blip or broadband"]


def load():
    spec = importlib.util.spec_from_file_location("pickles", source)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


tables = []
for patched in (False, True):
    m = load()
    # Masks off in both runs, the same way as pickles_block.py's unmasked run, so the block's hotspots
    # are scored (with its masks on a masked block has none and the published code stops at line 630).
    m.filter_hotspots = lambda *a, **k: []
    if patched:
        m.h5_files = files
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        tables.append(m.pickler_wrapper(("ssy", 0), files, 1024, 10, "False")[COLS])
a, b = tables
same = len(a) == len(b) and all(
    np.allclose(a[c].astype(float), b[c].astype(float), equal_nan=True, rtol=0, atol=0) for c in COLS)
out.write_text(json.dumps({"rows_published": len(a), "rows_patched": len(b), "identical": bool(same)}, indent=1),
               encoding="utf-8")
print("ok", len(a), same)
