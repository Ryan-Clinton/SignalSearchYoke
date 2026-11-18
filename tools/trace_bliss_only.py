"""Trace, stage by stage, the planted signals BLISS recovers at SNR 10 and
this search raises no candidate for at all (comparable.md step 11; the list
from tools/bliss_only.py). Each block is read again and planted again with
its recorded signals, searched by this search unchanged, and judged at SNR 10
with the true ON looks, as matched.py does; nothing is tuned. For each
signal and each ON look it records:

- this search's nearest hit on the planted looks, and the best one within
  +-6 Hz and +-0.05 Hz/s, with its S/N (a hit under 10 is a shadow hit);
- the S/N along the signal's own track (onoff's best_track), what the
  cadence test would measure there;
- the nearest hit on the unplanted looks within 1 kHz (interference there);
- every event at SNR 10 holding a matching hit: its label (candidate,
  interference, unconfirmed), and per look what the test saw.

From these the first stage that loses it: no hit (the detector), a hit only
under the cut, a hit at the cut in no event, or an event judged
interference or unconfirmed (the cadence test). One file a block under
data/analysis/bliss_only/, written whole; a block already written is
skipped, so a stopped run picks up where it was."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matched  # noqa: E402
import seti  # noqa: E402
import store  # noqa: E402
import yoke  # noqa: E402

CUT = 10.0
OUT = ROOT / "data" / "analysis" / "bliss_only"


def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items() if k != "stamps"}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if hasattr(x, "item"):
        return x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def _near(hits, f_mhz, drift, reach_hz):
    best = None
    for i, h in enumerate(hits):
        df, dd = (h["frequency_mhz"] - f_mhz) * 1e6, h["drift_hz_s"] - drift
        if abs(df) > reach_hz:
            continue
        d = math.hypot(df / matched.TOL_HZ, dd / matched.TOL_DRIFT)
        if best is None or d < best[0]:
            best = (d, i, round(df, 2), round(dd, 4), round(h["snr"], 2))
    return None if best is None else {"index": best[1], "df_hz": best[2], "dd_hz_s": best[3], "snr": best[4]}


def _within(hits, f_mhz, drift):
    ok = [(i, h) for i, h in enumerate(hits) if abs((h["frequency_mhz"] - f_mhz) * 1e6) <= matched.TOL_HZ
          and abs(h["drift_hz_s"] - drift) <= matched.TOL_DRIFT]
    return max(ok, key=lambda x: x[1]["snr"]) if ok else None


def trace_block(b, tones_here, urls, block_list, base):
    rec = json.loads((base / f"block_{b:03d}.json").read_text(encoding="utf-8"))
    cad = matched._cadence(seti.read_looks(urls, *block_list[rec["block"]]), urls)
    if [c["s"]["tstart"] for c in cad] != rec["tstarts"]:
        raise yoke.Refusal("INVALID_REQUEST", f"block {b} read again is not the one recorded")
    planted = matched.plant(cad, rec["tones"])
    cad_p = [dict(c, spectra=x["spectra"]) for c, x in zip(cad, planted)]
    del planted
    sp = matched.our_search(cad_p)
    s0 = matched.our_search(cad)
    caches = [{} for _ in range(6)]
    looks, events, order = matched.our_events(cad_p, sp, matched.TRUE, CUT, caches)
    out = []
    for n in tones_here:
        t = rec["tones"][n]
        per_look, stage = [], None
        matched_hits = {}
        for j in matched.TRUE:
            x, f = matched.where(cad, t, j)
            lk = looks[order.index(j)]
            hits = sp[j][0]
            w = _within(hits, f, t["drift"])
            f_tol = matched.TOL_HZ / abs(lk.foff * 1e6)
            d_tol = matched.TOL_DRIFT * lk.span / abs(lk.foff * 1e6)
            track = lk.best_track(x, t["drift"], f_tol, d_tol)
            per_look.append({"look": j, "nearest_hit": _near(hits, f, t["drift"], 2000.0),
                             "best_matching_hit": None if w is None else
                             {"index": w[0], "snr": round(w[1]["snr"], 2), "drift_hz_s": w[1]["drift_hz_s"],
                              "df_hz": round((w[1]["frequency_mhz"] - f) * 1e6, 2)},
                             "track_snr": None if track[0] is None else round(track[0], 2),
                             "plain_nearest_hit": _near(s0[j][0], f, t["drift"], 1000.0)})
            if w is not None:
                matched_hits[order.index(j)] = w[0]
        evs = []
        for e in events:
            if any(e["matches"][p] == i for p, i in matched_hits.items()):
                evs.append({"label": e["label"], "seed_look": order[e["seed_position"]],
                            "f_mhz": round(e["frequency_mhz"], 6), "drift": e["drift_hz_s"], "snr": e["snr"],
                            "in_on": e["in_on"], "in_off": e["in_off"], "off_snr_max": e["off_snr_max"],
                            "on_snr_min": e["on_snr_min"], "looks": _clean(e["looks"])})
        have = [pl["best_matching_hit"] for pl in per_look]
        if any(h is None for h in have):
            stage = "detector: no matching hit in some ON look"
        elif all(h["snr"] < CUT for h in have):
            stage = "detector: matching hits only under the cut"
        elif not evs:
            stage = "no event holds a matching hit"
        elif any(e["label"] == "candidate" for e in evs):
            stage = "a candidate holds a matching hit (scoring)"
        else:
            stage = "cadence test: " + ", ".join(sorted({e["label"] for e in evs}))
        out.append({"block": b, "tone": n, "f_mhz": t["f_mhz"], "drift": t["drift"], "s_in": t["s_in"],
                    "stage": stage, "looks": per_look, "events": evs})
    return out


def main():
    lst = json.loads((OUT / "list.json").read_text(encoding="utf-8"))
    none = [x for x in lst if x["ours_10"]["lenient"] is None]
    by_block = {}
    for x in none:
        by_block.setdefault(x["block"], []).append(x["tone"])
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, "KIC8462852")
    db.close()
    base = matched.folder("KIC8462852", session)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    for b, ts in sorted(by_block.items()):
        path = OUT / f"trace_block_{b:03d}.json"
        if path.exists():
            continue
        res = trace_block(b, ts, urls, block_list, base)
        yoke.write(path, res, indent=1)
        for r in res:
            print(f"block {b} tone {r['tone']} S_in {r['s_in']} drift {r['drift']:.3f}: {r['stage']}", flush=True)
    print(f"traced {sum(len(v) for v in by_block.values())} signals in {len(by_block)} blocks", flush=True)


if __name__ == "__main__":
    main()
