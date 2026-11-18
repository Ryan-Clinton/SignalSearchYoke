"""Why the detector gives no matching hit for planted signals that are
bright along their own track (comparable.md step 11; the traced signals of
tools/trace_bliss_only.py whose stage is the detector). Nothing is changed
or tuned: each block is read and planted again as matched.py does, and for
each such signal and each ON look the detector's own stages are measured
around it:

- the hits: how many, whether the look reached MAX_HITS (then it is
  searched again without the cap, to see whether the signal would be
  picked), and the hits within 2,000 channels, strongest first;
- before any hit is picked: the best line start within +-3 channels of the
  signal and its drift, and the detector's S/N on the signal's own track
  (its start and drift), with the noise of the summed lines in the
  signal's block of 1,024 channels against the look's median (interference
  in the block inflates it and lowers every S/N there);
- the cadence test's S/N along the same track (onoff's best_track), which
  measures its noise from lines 60 to 1,900 channels aside instead;
- whether a picked hit's blanking covers the signal's start.

One file a block under data/analysis/bliss_only/, written whole, and
detector_misses.json over them all.

    python tools/detector_misses.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import matched  # noqa: E402
import onoff  # noqa: E402
import searching  # noqa: E402
import seti  # noqa: E402
import store  # noqa: E402
import yoke  # noqa: E402
from trace_bliss_only import OUT  # noqa: E402

NEAR = 2000         # channels either side in which hits are listed
REACH = 3           # channels either side for the best line start


def _signals():
    s = json.loads((OUT / "trace_summary.json").read_text(encoding="utf-8"))
    return [r for r in s["rows"] if r["stage"].startswith("detector: no matching hit")]


def _own_track(plane, x, k):
    """The detector's S/N on one line (start x, drift k), measured as
    Plane.search measures it, with that look's noise of the summed lines."""
    w = plane.width[k]
    back = w - 1 if k < 0 else 0
    s = 0.0
    for t, sh in enumerate(plane.shifts[k]):
        a = plane.margin + x + sh - back
        s += float(plane.padded[t, a:a + w].sum())
    med, spread = plane.norm[plane._group(k)]
    b = x // searching.BLOCK
    return (s - float(med[b])) / float(spread[b]), float(spread[b]) / float(np.median(spread))


def look(raw, s, x, drift, f_hz, position):
    """The detector's stages around one signal in one look."""
    flags = searching.kurtosis(raw) > searching.SK_FLAG
    flat = searching.flatten(raw)
    plane = searching.Plane(flat, s["tsamp"], s["foff"], searching.MAX_DRIFT, searching.METHOD, flags)
    best, best_k = plane.search()
    xi = int(round(x))
    k = int(round(drift * plane.span / (s["foff"] * 1e6)))
    k = max(-plane.most, min(plane.most, k))
    win = slice(xi - REACH, xi + REACH + 1)
    j = int(np.argmax(best[win]))
    pre = {"snr": round(float(best[win][j]), 2), "channel_offset": j - REACH,
           "drift_hz_s": round(float(best_k[win][j]) * s["foff"] * 1e6 / plane.span, 4)}
    own = [_own_track(plane, xi + d, kk) for d in range(-REACH, REACH + 1)
           for kk in range(k - 1, k + 2) if kk in plane.width]
    own_snr, inflation = max(own)
    flagged = float(flags[max(0, xi - 8):xi + 9].mean())
    del plane, flat, best, best_k

    details = {}
    hits = searching.search(raw, s["foff"], s["tsamp"], s["fch1"], details=details)
    near = sorted((h for h in hits if abs(h["channel"] - xi) <= NEAR), key=lambda h: -h["snr"])
    # Hits other than the signal's own whose blanking reaches its start.
    covering = [h for h in hits if abs(h["channel"] - xi) <= h["box_channels"] + 1 +
                (h["width_channels"] if h["wide"] else 0)
                and not (abs(h["frequency_mhz"] * 1e6 - f_hz) <= matched.TOL_HZ
                         and abs(h["drift_hz_s"] - drift) <= matched.TOL_DRIFT)]
    out = {"hits": len(hits), "complete": details["complete"], "unpicked": details["unpicked"],
           "pre_pick_best_near": pre, "own_track_snr": round(own_snr, 2),
           "block_noise_over_median": round(inflation, 2), "flagged_share_near": round(flagged, 3),
           "near_hits": [{"df_channels": h["channel"] - xi, "snr": h["snr"], "drift_hz_s": h["drift_hz_s"],
                          "wide": h["wide"], "width_channels": h["width_channels"]} for h in near[:12]],
           "hits_near": len(near), "covering_hits": len(covering)}
    lk = onoff.Look(hits, s["tstart"], s["fch1"], s["foff"], s["tsamp"], details["flat"], position)
    f_tol = matched.TOL_HZ / abs(s["foff"] * 1e6)
    d_tol = matched.TOL_DRIFT * lk.span / abs(s["foff"] * 1e6)
    track = lk.best_track(x, drift, f_tol, d_tol)[0]
    out["cadence_test_track_snr"] = None if track is None else round(track, 2)
    del lk, details["flat"]
    if not details["complete"]:
        more = searching.search(raw, s["foff"], s["tsamp"], s["fch1"], max_hits=10 ** 7)
        m = [h for h in more if abs((h["frequency_mhz"] * 1e6 - f_hz)) <= matched.TOL_HZ
             and abs(h["drift_hz_s"] - drift) <= matched.TOL_DRIFT]
        out["uncapped"] = {"hits": len(more), "matching_hit_snr": max((h["snr"] for h in m), default=None)}
    return out


def block(b, rows, urls, block_list, base):
    rec = json.loads((base / f"block_{b:03d}.json").read_text(encoding="utf-8"))
    cad = matched._cadence(seti.read_looks(urls, *block_list[rec["block"]]), urls)
    if [c["s"]["tstart"] for c in cad] != rec["tstarts"]:
        raise yoke.Refusal("INVALID_REQUEST", f"block {b} read again is not the one recorded")
    planted = matched.plant(cad, rec["tones"])
    res = []
    for r in rows:
        t = rec["tones"][r["tone"]]
        per = []
        for j in matched.TRUE:
            x, f = matched.where(cad, t, j)
            got = look(planted[j]["spectra"], cad[j]["s"], x, t["drift"], f * 1e6, j)
            got["look"] = j
            per.append(got)
        res.append({"block": b, "tone": r["tone"], "s_in": t["s_in"], "drift": t["drift"], "cause": r["cause"],
                    "looks": per})
    return res


def main():
    rows = _signals()
    by_block = {}
    for r in rows:
        by_block.setdefault(r["block"], []).append(r)
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, "KIC8462852")
    db.close()
    base = matched.folder("KIC8462852", session)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    every = []
    for b, rs in sorted(by_block.items()):
        path = OUT / f"detector_block_{b:03d}.json"
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if sorted(r["tone"] for r in old) != sorted(r["tone"] for r in rs):
                raise yoke.Refusal("INVALID_REQUEST", f"{path.name} is not of block {b}'s signals; move it aside")
        else:
            old = block(b, rs, urls, block_list, base)
            yoke.write(path, old, indent=1)
        every += old
        for r in old:
            for lk in r["looks"]:
                print(f"block {b} tone {r['tone']} look {lk['look']}: hits {lk['hits']} complete {lk['complete']}, "
                      f"own track {lk['own_track_snr']}, block noise x{lk['block_noise_over_median']}, "
                      f"pre-pick best {lk['pre_pick_best_near']['snr']}, covering {lk['covering_hits']}"
                      + (f", uncapped {lk['uncapped']}" if "uncapped" in lk else ""), flush=True)
    yoke.write(OUT / "detector_misses.json", {"signals": every, "kind": "measured"}, indent=1, stamp=True)
    print(f"detector misses measured: {len(every)} signals in {len(by_block)} blocks", flush=True)


if __name__ == "__main__":
    main()
