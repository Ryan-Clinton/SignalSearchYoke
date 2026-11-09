"""Run in turboSETI's environment: Painter et al. 2025's pickles (as in
tools/pickles_block.py, the same one supplied name) on a cadence's six slices
with several choices of which three looks are ON (comparable.md steps 4
and 7).

    python tools/pickles_choices.py PICKLES OUT.json CHOICES F0.h5 F1.h5 F2.h5 F3.h5 F4.h5 F5.h5

F0..F5 in time order (the true cadence). CHOICES: "all" (20) or "true"
(0,2,4). For each choice the six files go to its pickler_wrapper as ON, OFF,
ON, OFF, ON, OFF: the chosen ON looks in time order, each followed by the
next OFF look. Run with its interference bands masked as published and with
none masked; the paper's levels applied (level 1: median ON kurtosis >= 0.5
and largest OFF <= 0.25; level 2: of those, drift1 == 1, drift2 true, not a
blip or broadband). Every hotspot's row is kept.
"""
import contextlib
import importlib.util
import io
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np

source, out, which = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
files = [str(Path(p).resolve()) for p in sys.argv[4:]]
assert len(files) == 6
spec = importlib.util.spec_from_file_location("pickles", source)
pickles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pickles)
masked_filter = pickles.filter_hotspots
choices = list(itertools.combinations(range(6), 3)) if which == "all" else [(0, 2, 4)]
KEEP = ["Index", "Freq", "k1", "k2", "k3", "k4", "k5", "k6", "drift1", "drift2", "blip or broadband"]


def plain(v):
    v = v.item() if isinstance(v, np.generic) else v
    return None if isinstance(v, float) and v != v else v


started = time.monotonic()
record = {"choices": []}
for ons in choices:
    offs = [j for j in range(6) if j not in ons]
    order = [x for pair in zip(ons, offs) for x in pair]
    ordered = [files[j] for j in order]
    pickles.h5_files = ordered         # the name its get_k_scores uses on a block with no hotspots (line 630)
    entry = {"as_on": list(ons), "runs": {}}
    for masks in (True, False):
        pickles.filter_hotspots = masked_filter if masks else (lambda *a, **k: [])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            table = pickles.pickler_wrapper(("ssy", 0), ordered, 1024, 10, "False")
        table = table[table["k1"].notna()] if len(table) else table
        rows = []
        for _, r in table.iterrows() if len(table) else []:
            on_k = sorted([r["k1"], r["k3"], r["k5"]])
            off_k = max(r["k2"], r["k4"], r["k6"])
            level1 = on_k[1] >= 0.5 and off_k <= 0.25
            level2 = level1 and r["drift1"] == 1 and bool(r["drift2"]) and not bool(r["blip or broadband"])
            rows.append({**{k: plain(r[k]) for k in KEEP}, "level": 2 if level2 else 1 if level1 else 0})
        entry["runs"]["masked" if masks else "unmasked"] = rows
    record["choices"].append(entry)
record["total_s"] = round(time.monotonic() - started, 1)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(record), encoding="utf-8")
print("ok", record["total_s"])
