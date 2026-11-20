"""Why the detector gives no matching hit for planted signals that are
bright along their own track (comparable.md step 11; the traced signals of
tools/trace_bliss_only.py whose stage is the detector). Nothing in the
search is changed or tuned: each block is read and planted again as
matched.py does, each ON look is searched once by searching.search as it
is, and the diagnostic watches it from outside (Plane.search, Plane.blank
and Plane.lit wrapped to record what they did, then put back). For each
signal and each ON look:

- before any hit is picked (the first, full pass): the detector's S/N on
  the signal's exact track (its start channel and drift, rounded to the
  detector's grid) and the noise of the summed lines for that drift's box
  width in the signal's block of 1,024 channels, over that width's median
  across the look (interference in the block inflates it and lowers every
  S/N there); separately, the best S/N within +-3 channels and +-1 drift
  step of it, and the best line start the pass kept within +-3 channels,
  with its drift;
- the hits: how many, whether the look reached MAX_HITS; if it did, the
  look is searched again with the cap at 5,000, then 10,000, then 20,000,
  stopping when a matching hit appears or the look is complete;
- the blanking: every pixel the detector blanked for each hit (its track,
  or a wide hit's lit runs), against the pixels of the signal's own track,
  spectrum by spectrum: how many and what share were blanked by hits other
  than the signal's own, and by which;
- the cadence test's S/N along the same track (onoff's best_track), which
  measures its noise from lines 60 to 1,900 channels aside instead.

One file a block under data/analysis/bliss_only/, written whole, reused
only if it is of that block's signals; detector_misses.json over them all.

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

NEAR = 2000                     # channels either side in which hits are listed
REACH = 3                       # channels either side for the neighbourhood
CAPS = (5000, 10000, 20000)     # the cap tried in turn when a look reaches MAX_HITS
CODE = ("tools/detector_misses.py", "matched.py", "onoff.py", "searching.py", "seti.py", "measure.py")


def fingerprint():
    import hashlib
    h = hashlib.sha256()
    for f in CODE:
        h.update((ROOT / f).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def _signals():
    s = json.loads((OUT / "trace_summary.json").read_text(encoding="utf-8"))
    return [r for r in s["rows"] if r["stage"].startswith("detector: no matching hit")]


def _line(plane, x, k):
    """The detector's S/N on one line (start x, drift k), as Plane.search
    measures it, and that line's noise of the summed lines in its block over
    the median of the same width's noise across the look."""
    w = plane.width[k]
    back = w - 1 if k < 0 else 0
    s = 0.0
    for t, sh in enumerate(plane.shifts[k]):
        a = plane.margin + x + sh - back
        s += float(plane.padded[t, a:a + w].sum())
    med, spread = plane.norm[plane._group(k)]
    b = x // searching.BLOCK
    used = spread[:-(-plane.n_f // searching.BLOCK)]
    return (s - float(med[b])) / float(spread[b]), float(spread[b]) / float(np.median(used))


def _track_pixels(plane, x, k):
    """The signal's own track: {spectrum: set of channels}."""
    w = plane.width[k]
    back = w - 1 if k < 0 else 0
    return {t: set(range(x + sh - back, x + sh - back + w)) for t, sh in enumerate(plane.shifts[k])}


def _watched_search(raw, s, first_pass, max_hits=searching.MAX_HITS):
    """searching.search as it is, with what its Plane does recorded:
    `first_pass(plane, best, best_k)` is called after the full pass, before
    any pick; returns (hits, details, blanked) with blanked[n] the pixels
    {spectrum: (lo, hi)} the detector cleared for hit n."""
    P = searching.Plane
    orig_search, orig_blank, orig_lit = P.search, P.blank, P.lit
    lit_calls, blank_calls = [], []

    def w_search(self, lo=0, hi=None, measure=True):
        best, best_k = orig_search(self, lo, hi, measure)
        if measure and first_pass is not None:
            first_pass(self, best, best_k)
        return best, best_k

    def w_blank(self, channel, k, width):
        w = self.width[k]
        back = w - 1 if k < 0 else 0
        blank_calls.append((channel, k, {t: (channel + sh - back - width, channel + sh - back + w + width - 1)
                                         for t, sh in enumerate(self.shifts[k])}))
        return orig_blank(self, channel, k, width)

    def w_lit(self, channel, k, reach=50000):
        got = orig_lit(self, channel, k, reach)
        lit_calls.append((channel, k, got))
        return got

    P.search, P.blank, P.lit = w_search, w_blank, w_lit
    try:
        details = {}
        hits = searching.search(raw, s["foff"], s["tsamp"], s["fch1"], max_hits=max_hits, details=details)
    finally:
        P.search, P.blank, P.lit = orig_search, orig_blank, orig_lit
    # lit is called once for each hit picked, in order; blank once for each
    # hit that is not wide, in order.
    blanks = iter(blank_calls)
    blanked = []
    for h, (ch, _, lit) in zip(hits, lit_calls):
        if h["channel"] != ch:
            raise yoke.Refusal("INVALID_REQUEST", "the detector's picks and its recorded blanking disagree")
        if h["wide"]:
            blanked.append({t: x for t, x in enumerate(lit) if x})
        else:
            c, _, px = next(blanks)
            if c != ch:
                raise yoke.Refusal("INVALID_REQUEST", "the detector's picks and its recorded blanking disagree")
            blanked.append(px)
    return hits, details, blanked


def _matches(h, f_hz, drift):
    return abs(h["frequency_mhz"] * 1e6 - f_hz) <= matched.TOL_HZ and abs(h["drift_hz_s"] - drift) <= matched.TOL_DRIFT


def look(raw, s, sigs, position):
    """The detector's stages around each signal of one look; sigs is
    [(x, drift Hz/s, f Hz)]."""
    pre = [None] * len(sigs)

    def first_pass(plane, best, best_k):
        for n, (x, drift, _) in enumerate(sigs):
            xi = int(round(x))
            k = int(round(drift * plane.span / (s["foff"] * 1e6)))
            k = max(-plane.most, min(plane.most, k))
            snr, infl = _line(plane, xi, k)
            hood = max((_line(plane, xi + d, kk)[0], d, kk) for d in range(-REACH, REACH + 1)
                       for kk in (k - 1, k, k + 1) if kk in plane.width)
            win = best[xi - REACH:xi + REACH + 1]
            j = int(np.argmax(win))
            pre[n] = {"exact_track": {"snr": round(snr, 2), "drift_step": k,
                                      "block_noise_over_median": round(infl, 3)},
                      "best_in_neighbourhood": {"snr": round(hood[0], 2), "channel_offset": hood[1],
                                                "drift_steps_off": hood[2] - k},
                      "pass_best_near": {"snr": round(float(win[j]), 2), "channel_offset": j - REACH,
                                         "drift_hz_s": round(float(best_k[xi - REACH + j]) * s["foff"] * 1e6
                                                             / plane.span, 4)},
                      "_track": _track_pixels(plane, xi, k)}

    flags = searching.kurtosis(raw) > searching.SK_FLAG
    hits, details, blanked = _watched_search(raw, s, first_pass)
    lk = onoff.Look(hits, s["tstart"], s["fch1"], s["foff"], s["tsamp"], details["flat"], position)
    out = []
    for n, (x, drift, f_hz) in enumerate(sigs):
        xi = int(round(x))
        p = pre[n]
        track = p.pop("_track")
        n_px = sum(len(v) for v in track.values())
        by_hit = []
        hit_px = set()
        for h, px in zip(hits, blanked):
            if _matches(h, f_hz, drift):
                continue
            got = set()
            for t, (lo, hi) in px.items():
                got |= {(t, c) for c in track.get(t, ()) if lo <= c <= hi}
            if got:
                hit_px |= got
                by_hit.append({"df_channels": h["channel"] - xi, "snr": h["snr"], "drift_hz_s": h["drift_hz_s"],
                               "wide": h["wide"], "pixels": len(got)})
        near = sorted((h for h in hits if abs(h["channel"] - xi) <= NEAR), key=lambda h: -h["snr"])
        f_tol = matched.TOL_HZ / abs(s["foff"] * 1e6)
        d_tol = matched.TOL_DRIFT * lk.span / abs(s["foff"] * 1e6)
        ct = lk.best_track(x, drift, f_tol, d_tol)[0]
        rec = dict(p, hits=len(hits), complete=details["complete"], unpicked=details["unpicked"],
                   matching_hit_snr=max((h["snr"] for h in hits if _matches(h, f_hz, drift)), default=None),
                   blanked_by_others={"pixels": len(hit_px), "of": n_px, "share": round(len(hit_px) / n_px, 3),
                                      "hits": sorted(by_hit, key=lambda b: -b["pixels"])[:10]},
                   flagged_share_near=round(float(flags[max(0, xi - 8):xi + 9].mean()), 3),
                   near_hits=[{"df_channels": h["channel"] - xi, "snr": h["snr"], "drift_hz_s": h["drift_hz_s"],
                               "wide": h["wide"], "width_channels": h["width_channels"]} for h in near[:12]],
                   hits_near=len(near), cadence_test_track_snr=None if ct is None else round(ct, 2))
        out.append(rec)
    del lk, details
    if not out or all(r["complete"] or r["matching_hit_snr"] is not None for r in out):
        return out
    for cap in CAPS:
        d = {}
        more = searching.search(raw, s["foff"], s["tsamp"], s["fch1"], max_hits=cap, details=d)
        for (x, drift, f_hz), r in zip(sigs, out):
            if r["matching_hit_snr"] is None:
                r.setdefault("raised_caps", []).append(
                    {"cap": cap, "hits": len(more), "complete": d["complete"],
                     "matching_hit_snr": max((h["snr"] for h in more if _matches(h, f_hz, drift)), default=None)})
        if d["complete"] or all(r["raised_caps"][-1]["matching_hit_snr"] is not None
                                for r in out if "raised_caps" in r):
            break
    return out


def block(b, rows, urls, block_list, base):
    rec = json.loads((base / f"block_{b:03d}.json").read_text(encoding="utf-8"))
    cad = matched._cadence(seti.read_looks(urls, *block_list[rec["block"]]), urls)
    if [c["s"]["tstart"] for c in cad] != rec["tstarts"]:
        raise yoke.Refusal("INVALID_REQUEST", f"block {b} read again is not the one recorded")
    planted = matched.plant(cad, rec["tones"])
    tones = [rec["tones"][r["tone"]] for r in rows]
    per = {}
    for j in matched.TRUE:
        sigs = []
        for t in tones:
            x, f = matched.where(cad, t, j)
            sigs.append((x, t["drift"], f * 1e6))
        per[j] = look(planted[j]["spectra"], cad[j]["s"], sigs, j)
    return [{"block": b, "tone": r["tone"], "s_in": t["s_in"], "drift": t["drift"], "cause": r["cause"],
             "looks": [dict(per[j][n], look=j) for j in matched.TRUE]}
            for n, (r, t) in enumerate(zip(rows, tones))]


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
        fp = fingerprint()
        cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        # A block's record is reused only when the same code made it (records from before the fingerprint,
        # a bare list, are made again).
        if isinstance(cached, dict) and cached.get("code") == fp:
            old = cached["rows"]
            if sorted(r["tone"] for r in old) != sorted(r["tone"] for r in rs):
                raise yoke.Refusal("INVALID_REQUEST", f"{path.name} is not of block {b}'s signals; move it aside")
        else:
            old = block(b, rs, urls, block_list, base)
            yoke.write(path, {"code": fp, "rows": old}, indent=1)
        every += old
        for r in old:
            for lk in r["looks"]:
                print(f"block {b} tone {r['tone']} look {lk['look']}: exact {lk['exact_track']}, "
                      f"hood {lk['best_in_neighbourhood']['snr']}, hits {lk['hits']} complete {lk['complete']}, "
                      f"match {lk['matching_hit_snr']}, blanked {lk['blanked_by_others']['share']}"
                      + (f", caps {lk['raised_caps']}" if "raised_caps" in lk else ""), flush=True)
    want = sorted((r["block"], r["tone"]) for r in rows)
    if sorted((r["block"], r["tone"]) for r in every) != want:
        raise yoke.Refusal("INVALID_REQUEST", "the measured signals are not the traced detector misses")
    yoke.write(OUT / "detector_misses.json", {"signals": every, "kind": "measured"}, indent=1, stamp=True)
    print(f"detector misses measured: {len(every)} signals in {len(by_block)} blocks", flush=True)


if __name__ == "__main__":
    main()
