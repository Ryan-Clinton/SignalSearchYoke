"""The 2016 DC bins (docs/audits.md 14): the same 2016 blocks read with the DC
bins blanked by storage chunk (as step 10's reads did) and by coarse channel
(the instrument's, from 20 Nov 2026), each through the search and cadence
test unchanged: false candidates over the 19 wrong choices and planted
signals found at cut 30, and the hits that differ. Supplementary: step 10's
records and verdict stay as made.

    python tools/dc_checks.py

Blocks: four crowded and four clean of step 10's, chosen by seed 12.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import matched  # noqa: E402
import matched_tables  # noqa: E402
import seti  # noqa: E402
import store  # noqa: E402
import yoke  # noqa: E402
from detector_checks import _judged, _keys  # noqa: E402

TARGET = "HIP17147"
OUT = yoke.DATA / "analysis" / "dc_checks.json"


def _say(*a):
    print(*a, flush=True)


def _read(urls, block, chunk):
    old = os.environ.get("SSY_DC_BY_CHUNK")
    os.environ["SSY_DC_BY_CHUNK"] = "1" if chunk else "0"
    try:
        return seti.read_looks(urls, *block)
    finally:
        if old is None:
            os.environ.pop("SSY_DC_BY_CHUNK", None)
        else:
            os.environ["SSY_DC_BY_CHUNK"] = old


def main(say=_say):
    session, _, recs = matched_tables.load(TARGET)
    rng = np.random.default_rng(12)
    by = {c: sorted(int(r["block"]) for r in recs if r["class"] == c) for c in ("crowded", "clean")}
    picks = sorted(int(b) for c in by for b in rng.choice(by[c], 4, replace=False))
    db = store.connect_readonly()
    _, urls = store.cadence_files(db, TARGET)
    db.close()
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    rows = []
    for b in picks:
        rec = json.loads((matched.folder(TARGET, session) / f"block_{b:03d}.json").read_text(encoding="utf-8"))
        row = {"block": b, "class": rec["class"]}
        keys = {}
        for name, chunk in (("by storage chunk", True), ("by coarse channel", False)):
            cad = matched._cadence(_read(urls, block_list[b], chunk), urls)
            if [c["s"]["tstart"] for c in cad] != rec["tstarts"]:
                raise yoke.Refusal("INVALID_REQUEST", f"block {b}: looks start at other times than the record's")
            cad_p = [dict(c, spectra=p["spectra"]) for c, p in zip(cad, matched.plant(cad, rec["tones"]))]
            su, sp = matched.our_search(cad), matched.our_search(cad_p)
            false30, found30 = _judged(cad, cad_p, su, sp, rec["tones"])
            row[name] = {"false_30": false30, "found_30": found30, "hits": [len(x[0]) for x in su]}
            keys[name] = [_keys(x[0]) for x in su]
        row["hits_differing"] = [len(keys["by storage chunk"][j] ^ keys["by coarse channel"][j]) for j in range(6)]
        rows.append(row)
        say(f"block {b} ({row['class']}): chunk {row['by storage chunk']}; coarse {row['by coarse channel']}; "
            f"hits differing {row['hits_differing']}")
    yoke.write(OUT, {"target": TARGET, "session": session, "blocks": picks, "rows": rows, "kind": "measured"},
               indent=1, stamp=True)


if __name__ == "__main__":
    main()
