"""Run in turboSETI's environment: Painter et al. 2025's kurtosis pipeline
(pickles.py, github.com/UCBerkeleySETI/pickles, fetched by pipelines.py to
PICKLES) on a cadence's six slices, its own code from the hotspots on:

    python tools/pickles_block.py PICKLES OUT_DIR ON1.h5 OFF1.h5 ON2.h5 OFF2.h5 ON3.h5 OFF3.h5

pickler_wrapper with its published settings (1,024-channel blocks, SNR 10,
not sectioned) gives every hotspot's kurtosis scores; then the paper's
levels: 1, median ON kurtosis >= 0.5 and largest OFF kurtosis <= 0.25; 2, of
those, not zero drift by either of its two tests and not broadband or a
blip. Run twice: with its interference bands masked, as published, and with
none masked, to see what the masks hid. Writes OUT_DIR/pickles.csv (one row
a hotspot, both runs) and OUT_DIR/pickles.json (the counts).
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
spec = importlib.util.spec_from_file_location("pickles", source)
pickles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pickles)
# Its get_k_scores names `h5_files`, never defined there, when a block has no
# hotspots (pickles.py line 630): given here as the module's global, its code
# otherwise run as published.
pickles.h5_files = files
masked_filter = pickles.filter_hotspots
SCALARS = ["Index", "Freq", "k1", "k2", "k3", "k4", "k5", "k6", "k_score", "min_k", "med_k", "max_k", "drift1",
           "drift2", "blip or broadband"]
rows, counts = [], {}
for masks in (True, False):
    pickles.filter_hotspots = masked_filter if masks else (lambda *a, **k: [])
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        table = pickles.pickler_wrapper(("ssy", 0), files, 1024, 10, "False")
    table = table[table["k1"].notna()] if len(table) else table
    n0 = len(table)
    level1 = table[(table[["k1", "k3", "k5"]].median(axis=1) >= 0.5)
                   & (table[["k2", "k4", "k6"]].max(axis=1) <= 0.25)] if n0 else table
    level2 = level1[(level1["drift1"] == 1) & (level1["drift2"].astype(bool))
                    & ~(level1["blip or broadband"].astype(bool))] if len(level1) else level1
    counts["masked" if masks else "unmasked"] = {"level0": n0, "level1": len(level1), "level2": len(level2)}
    for _, r in table.iterrows():
        row = {"masks": masks, **{k: (r[k].item() if isinstance(r[k], np.generic) else r[k]) for k in SCALARS}}
        row["level"] = 2 if r.name in level2.index else 1 if r.name in level1.index else 0
        rows.append(row)
out.mkdir(parents=True, exist_ok=True)
cols = ["masks", "level"] + SCALARS
with open(out / "pickles.csv", "w", encoding="utf-8") as f:
    f.write(",".join(cols) + "\n")
    for row in rows:
        f.write(",".join(str(row[c]) for c in cols) + "\n")
(out / "pickles.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
print("ok", json.dumps(counts))
