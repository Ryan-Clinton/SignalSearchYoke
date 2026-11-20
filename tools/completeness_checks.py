"""Where the detector loses planted signals and why (the detector-completeness
audit, docs/audits.md 6). Supplementary and exploratory: the detector, the
cadence test and every published result are unchanged; the variants come
from tools/search_variants.py, a diagnostic copy of the search.

    python tools/completeness_checks.py records   cap, occupancy and errors, from the block records
    python tools/completeness_checks.py pairs     close pairs at fast drifts: the start-channel corridor and shadow refresh
    python tools/completeness_checks.py cluster   a lone signal far from a crowd, a global cap against a budget a region
    python tools/completeness_checks.py strong    the 2017 session's strong signals at 2-4 Hz/s not found, traced (read again)
    python tools/completeness_checks.py shadow    four crowded 2016 blocks searched with shadow refresh (read again)

- **records**: (cap) recovery and false candidates split by whether a block's
  looks were all complete, an ON look stopped at the hit cap, or only OFF
  looks did, all three sessions; (occupancy) recovery against the block's
  hit count at the sweep's cut; (errors) the frequency and drift offsets of
  the nearest event to each planted signal, found and missed, by drift, with
  their tails.
- **pairs**: two signals close in frequency at 2, 3 and 4 Hz/s, the same,
  opposite and a little different in drift, 1 to 100 channels apart, the
  second weaker (1, 1/2, 1/4), two places in a channel, in noise. Whether
  the second is found by the search as it is, with the corridor of excluded
  starts off, and with the scores refreshed after shadow hits too.
- **cluster**: a lone signal at the far end of a slice from a crowd of strong
  ones; the crowd grown until the cap is spent (the cap scaled down with the
  slice); found under the global cap and under a budget a region.
- **strong**: every planted signal at S_in 400 and 2 to 4 Hz/s of the 2017
  session not recovered at SNR 30, read again and traced stage by stage
  (tools/trace_bliss_only.py's trace at the cut 30): no hit, measured outside
  the tolerances, under the cut, no event, the cadence test's label; with
  whether its block's looks were cut at the hit cap.
- **shadow**: four crowded blocks of the 2016 session, searched as the search
  is and with shadow refresh: the hits, shadow hits and complete looks of
  each, the false candidates of the wrong choices and the planted signals
  recovered at 30.

Every block read again records a fingerprint of the code and is made again
when it differs. Writes data/analysis/completeness_<name>.json.
"""
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import matched  # noqa: E402
import matched_tables  # noqa: E402
import measure  # noqa: E402
import seti  # noqa: E402
import store  # noqa: E402
import yoke  # noqa: E402
import search_variants as sv  # noqa: E402
from injection_checks import _drift_bin  # noqa: E402

OUT = yoke.DATA / "analysis"
SESSIONS = ("KIC8462852", "HIP17147", "NGC6946")
FOFF, TSAMP, FCH1 = -2.7939677238464355e-06, 18.253611008, 2000.0
CODE = ("tools/completeness_checks.py", "tools/search_variants.py", "tools/trace_bliss_only.py", "matched.py",
        "onoff.py", "searching.py", "seti.py", "measure.py")


def _say(*a):
    print(*a, flush=True)


def fingerprint():
    h = hashlib.sha256()
    for f in CODE:
        h.update((ROOT / f).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def _q(xs, p):
    return round(float(np.percentile(xs, p)), 3) if len(xs) else None


# --- records -----------------------------------------------------------------------------

def records(say=_say):
    rec = {"sessions": {}}
    db = store.connect_readonly()
    for target in SESSIONS:
        session, meta, recs = matched_tables.load(target)
        hits_of = {int(r[0]): int(r[1]) for r in db.execute(
            "SELECT block_idx, hits FROM blocks WHERE session = ? AND status = 'done'", (session,))}
        out = {}
        # cap
        cap = {}
        for r in recs:
            comp = r.get("complete", [True] * 6)
            kind = "all complete" if all(comp) else ("an ON look capped" if not all(comp[j] for j in matched.TRUE)
                                                     else "only OFF looks capped")
            d = cap.setdefault(kind, {"blocks": 0, "signals": 0, "found_30": 0, "found_10": 0, "false_30": 0})
            d["blocks"] += 1
            d["signals"] += len(r["tones"])
            d["found_30"] += sum(t["ours"]["30"].get("three_looks") == "recovered" for t in r["tones"])
            d["found_10"] += sum(t["ours"]["10"].get("three_looks") == "recovered" for t in r["tones"])
            d["false_30"] += matched_tables.distinct(r, r["ours"]["false"].get("30", {}), "shared hits")
        for d in cap.values():
            d["share_30"] = round(d["found_30"] / d["signals"], 4) if d["signals"] else None
            d["false_30_a_block"] = round(d["false_30"] / d["blocks"], 3) if d["blocks"] else None
        out["cap"] = cap
        # occupancy
        bins = [(0, 5), (5, 20), (20, 100), (100, 1000), (1000, 10 ** 9)]
        occ = {}
        for r in recs:
            h = hits_of.get(int(r["block"]))
            if h is None:
                continue
            lab = next(f"{lo}-{hi if hi < 10 ** 9 else 'more'}" for lo, hi in bins if lo <= h < hi)
            d = occ.setdefault(lab, {"blocks": 0, "signals": 0, "found_30": 0})
            d["blocks"] += 1
            d["signals"] += len(r["tones"])
            d["found_30"] += sum(t["ours"]["30"].get("three_looks") == "recovered" for t in r["tones"])
        for d in occ.values():
            d["share_30"] = round(d["found_30"] / d["signals"], 4)
        out["occupancy_hits_at_the_sweep_cut"] = occ
        # errors
        err = {}
        for r in recs:
            for t in r["tones"]:
                st = t["ours"]["30"]
                near = st.get("nearest")
                if not near:
                    continue
                key = (_drift_bin(t["drift"]), "found" if st.get("three_looks") == "recovered" else "missed")
                d = err.setdefault(f"{key[0]} {key[1]}", {"hz": [], "dd": []})
                d["hz"].append(abs(near.get("df_hz", 0.0)))
                d["dd"].append(abs(near.get("dd_hz_s", 0.0)))
        out["errors_nearest_member_30"] = {k: {"n": len(v["hz"]), "hz_p50_p90_p99_max": [_q(v["hz"], 50), _q(v["hz"], 90),
                                                                                       _q(v["hz"], 99), _q(v["hz"], 100)],
                                               "drift_p50_p90_p99_max": [_q(v["dd"], 50), _q(v["dd"], 90),
                                                                         _q(v["dd"], 99), _q(v["dd"], 100)]}
                                           for k, v in sorted(err.items())}
        rec["sessions"][target] = out
    db.close()
    rec["kind"] = "measured"
    yoke.write(OUT / "completeness_records.json", rec, indent=1, stamp=True)
    for t, o in rec["sessions"].items():
        say(f"{t} cap: " + "; ".join(f"{k}: {v['blocks']} blocks, found {v['share_30']}, false {v['false_30_a_block']} a block"
                                     for k, v in o["cap"].items()))
        say(f"{t} occupancy: " + "; ".join(f"{k}: {v['share_30']} ({v['blocks']})"
                                           for k, v in o["occupancy_hits_at_the_sweep_cut"].items()))
    return rec


# --- pairs ---------------------------------------------------------------------------------

def _found(hits, f, drift):
    return any(abs((h["frequency_mhz"] - f) * 1e6) <= matched.TOL_HZ and abs(h["drift_hz_s"] - drift) <= matched.TOL_DRIFT
               for h in hits)


def pairs(say=_say):
    rng = np.random.default_rng(12)
    rows = []
    n_f = 16384
    for mag in (2.0, 3.0, 4.0):
        for sign in (1, -1):
            d1 = sign * mag
            for rel in ("same", "opposite", "0.3 Hz/s apart"):
                d2 = d1 if rel == "same" else (-d1 if rel == "opposite" else d1 + 0.3 * (-sign))
                for sep in (1, 2, 4, 8, 16, 32, 64, 100):
                    for ratio in (1.0, 0.5, 0.25):
                        for phase in (0.0, 0.5):
                            noise = rng.chisquare(102, size=(16, n_f)) * 1e3
                            sigma = float(np.median(measure.channel_noise(noise)))
                            x1 = 8000.0 + phase
                            x2 = x1 + sep
                            h1 = 60 * sigma / 4
                            p = measure.plant(noise, [(x1, d1, h1), (x2, d2, h1 * ratio)], TSAMP, FOFF)
                            f2 = FCH1 + x2 * FOFF
                            got = {}
                            for name, kw in (("as is", {}), ("no corridor", {"corridor": False}),
                                             ("shadow refresh", {"refresh_shadow": True})):
                                got[name] = _found(sv.search_variant(p, FOFF, TSAMP, FCH1, **kw), f2, d2)
                            rows.append({"drift": d1, "relative": rel, "second_drift": round(d2, 3), "channels_apart": sep,
                                         "ratio": ratio, "phase": phase, **got})
    lost = [r for r in rows if not r["as is"]]
    rec = {"cases": len(rows), "second_lost_as_is": len(lost),
           "of_those_found_without_the_corridor": sum(r["no corridor"] for r in lost),
           "of_those_found_with_shadow_refresh": sum(r["shadow refresh"] for r in lost),
           "found_as_is_but_lost_without_the_corridor": sum(r["as is"] and not r["no corridor"] for r in rows),
           "by_separation": {str(s): {"cases": sum(r["channels_apart"] == s for r in rows),
                                      "lost_as_is": sum(r["channels_apart"] == s and not r["as is"] for r in rows),
                                      "lost_without_corridor": sum(r["channels_apart"] == s and not r["no corridor"]
                                                                   for r in rows)}
                             for s in (1, 2, 4, 8, 16, 32, 64, 100)},
           "by_relative_drift": {rel: {"cases": sum(r["relative"] == rel for r in rows),
                                       "lost_as_is": sum(r["relative"] == rel and not r["as is"] for r in rows)}
                                 for rel in ("same", "opposite", "0.3 Hz/s apart")},
           "rows": rows, "kind": "measured",
           "note": "the second signal at S_in 60 x ratio, the first at 60; in noise, one look; found within the tolerances"}
    yoke.write(OUT / "completeness_pairs.json", rec, indent=1, stamp=True)
    say(f"pairs: {len(rows)} cases, second lost as is {len(lost)}; of those found without the corridor "
        f"{rec['of_those_found_without_the_corridor']}, with shadow refresh {rec['of_those_found_with_shadow_refresh']}")
    say(f"  by separation: {rec['by_separation']}")
    return rec


# --- cluster -------------------------------------------------------------------------------

def cluster(say=_say):
    rng = np.random.default_rng(12)
    n_f, cap, region = 262144, 200, 32768
    rows = []
    for n_crowd in (50, 100, 150, 200, 250, 400, 800):
        noise = rng.chisquare(102, size=(16, n_f)) * 1e3
        sigma = float(np.median(measure.channel_noise(noise)))
        crowd = [(2000.0 + 40 * k + rng.uniform(0, 1), float(rng.uniform(-1, 1)), float(rng.uniform(40, 200)) * sigma / 4)
                 for k in range(n_crowd)]
        lone = (240000.3, 0.4, 30 * sigma / 4)
        p = measure.plant(noise, crowd + [lone], TSAMP, FOFF)
        f = FCH1 + lone[0] * FOFF
        dg, dr = {}, {}
        g = sv.search_variant(p, FOFF, TSAMP, FCH1, max_hits=cap, details=dg)
        r = sv.search_variant(p, FOFF, TSAMP, FCH1, region=(region, cap * region // n_f), details=dr)
        rows.append({"crowd": n_crowd, "global_cap": cap, "global_complete": dg["complete"], "lone_found_global": _found(g, f, 0.4),
                     "region_cap": cap * region // n_f, "regions_full": dr["regions_full"], "lone_found_region": _found(r, f, 0.4)})
        say(f"cluster, crowd {n_crowd}: {rows[-1]}")
    rec = {"channels": n_f, "rows": rows, "kind": "measured",
           "note": "the production cap of 2,000 a slice of 1,048,576 channels scaled to 200 a slice of 262,144 for speed; "
                   "the region budget the same share a region"}
    yoke.write(OUT / "completeness_cluster.json", rec, indent=1, stamp=True)
    return rec


# --- strong (read again) -------------------------------------------------------------------

def strong(say=_say):
    import trace_bliss_only as tb
    tb.CUT = 30.0
    target = "KIC8462852"
    session, meta, recs = matched_tables.load(target)
    want = {}
    for r in recs:
        for n, t in enumerate(r["tones"]):
            if t["s_in"] == 400 and abs(t["drift"]) >= 2.0 and t["ours"]["30"].get("three_looks") != "recovered":
                want.setdefault(int(r["block"]), []).append(n)
    db = store.connect_readonly()
    _, urls = store.cadence_files(db, target)
    db.close()
    base = matched.folder(target, session)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    fp = fingerprint()
    rows = []
    for b, ts in sorted(want.items()):
        path = OUT / "completeness_strong" / f"block_{b:03d}.json"
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if old.get("code") == fp:
                rows += old["rows"]
                continue
        rec = json.loads((base / f"block_{b:03d}.json").read_text(encoding="utf-8"))
        res = tb.trace_block(b, ts, urls, block_list, base)
        comp = rec.get("complete", [True] * 6)
        for x in res:
            near = [lk["nearest_hit"] for lk in x["looks"]]
            outside = any(lk["best_matching_hit"] is None and lk["nearest_hit"]
                          and abs(lk["nearest_hit"]["df_hz"]) <= 5 * matched.TOL_HZ
                          and abs(lk["nearest_hit"]["dd_hz_s"]) <= 4 * matched.TOL_DRIFT for lk in x["looks"])
            x["detected_outside_tolerances"] = bool(outside) and x["stage"].startswith("detector")
            x["capped_on_looks"] = [j for j in matched.TRUE if not comp[j]]
            x["capped_off_looks"] = [j for j in (1, 3, 5) if not comp[j]]
            x["nearest"] = near
        path.parent.mkdir(parents=True, exist_ok=True)
        yoke.write(path, {"code": fp, "rows": res}, indent=1)
        rows += res
        say(f"strong, block {b}: " + "; ".join(f"{x['stage']}{' (outside tolerances)' if x['detected_outside_tolerances'] else ''}"
                                               f"{' capped ON' if x['capped_on_looks'] else ''}" for x in res))
    def label(x):
        if x["detected_outside_tolerances"]:
            return "detected, measured outside the tolerances"
        return x["stage"] + (" (an ON look capped)" if x["capped_on_looks"] and x["stage"].startswith("detector") else "")
    by = {}
    for x in rows:
        by[label(x)] = by.get(label(x), 0) + 1
    out = {"signals": len(rows), "by_stage": dict(sorted(by.items(), key=lambda kv: -kv[1])), "rows": rows,
           "code": fp, "kind": "measured"}
    yoke.write(OUT / "completeness_strong.json", out, indent=1, stamp=True)
    say(f"strong: {out['signals']} signals; {out['by_stage']}")
    return out


# --- shadow (read again) -------------------------------------------------------------------

def shadow(say=_say):
    target = "HIP17147"
    session, meta, recs = matched_tables.load(target)
    rng = np.random.default_rng(12)
    crowded = sorted(int(r["block"]) for r in recs if r["class"] == "crowded")
    picks = sorted(int(b) for b in rng.choice(crowded, 4, replace=False))
    db = store.connect_readonly()
    _, urls = store.cadence_files(db, target)
    db.close()
    base = matched.folder(target, session)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    fp = fingerprint()
    rows = []
    from concurrent.futures import ThreadPoolExecutor

    def searched(cad, **kw):
        def one(j):
            s, raw = cad[j]["s"], cad[j]["spectra"]
            d = {}
            hits = seti.describe(sv.search_variant(raw, s["foff"], s["tsamp"], s["fch1"], details=d, **kw),
                                 dict(s, spectra=raw))
            return hits, d["flat"], bool(d["complete"])
        with ThreadPoolExecutor(max_workers=6) as pool:
            return list(pool.map(one, range(6)))
    for b in picks:
        path = OUT / "completeness_shadow" / f"block_{b:03d}.json"
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if old.get("code") == fp:
                rows.append(old)
                continue
        rec = json.loads((base / f"block_{b:03d}.json").read_text(encoding="utf-8"))
        cad = matched._cadence(seti.read_looks(urls, *block_list[b]), urls)
        ts = rec["tones"]
        cad_p = [dict(c, spectra=p["spectra"]) for c, p in zip(cad, matched.plant(cad, ts))]
        row = {"block": b, "code": fp}
        for name, kw in (("as is", {}), ("shadow refresh", {"refresh_shadow": True})):
            sp, su = searched(cad_p, **kw), searched(cad, **kw)
            caches = [{} for _ in range(6)]
            by = {}
            for ons in itertools.combinations(range(6), 3):
                if ons == matched.TRUE:
                    continue
                looks, events, order = matched.our_events(cad, su, ons, 30, caches)
                by[str(ons)] = matched._our_kept(looks, events, order)
            looks, events, order = matched.our_events(cad_p, sp, matched.TRUE, 30, [{} for _ in range(6)])
            kp = matched._our_kept(looks, events, order)
            looks, events, order = matched.our_events(cad, su, matched.TRUE, 30, [{} for _ in range(6)])
            ku = matched._our_kept(looks, events, order)
            found = sum(matched._status({j: matched.where(cad, t, j)[1] for j in matched.TRUE}, t["drift"], kp, ku)
                        ["three_looks"] == "recovered" for t in ts)
            row[name] = {"hits": [len(x[0]) for x in su], "shadow_hits": [sum(h.get("shadow", False) for h in x[0]) for x in su],
                         "complete": [x[2] for x in su], "false_30": len(matched.shared_hits(by)), "found_30": found,
                         "keys": [sorted((round(h["frequency_mhz"], 6), round(h["drift_hz_s"], 4)) for h in x[0]) for x in su]}
        a, z = row["as is"], row["shadow refresh"]
        row["hits_differing"] = [len(set(map(tuple, a["keys"][j])) ^ set(map(tuple, z["keys"][j]))) for j in range(6)]
        for v in (a, z):
            v.pop("keys")
        path.parent.mkdir(parents=True, exist_ok=True)
        yoke.write(path, row, indent=1)
        rows.append(row)
        say(f"shadow, block {b}: as is {a['false_30']} false, {a['found_30']} found, complete {a['complete']}; refresh "
            f"{z['false_30']} false, {z['found_30']} found, complete {z['complete']}; hits differing {row['hits_differing']}")
    out = {"blocks": picks, "rows": rows, "code": fp, "kind": "measured"}
    yoke.write(OUT / "completeness_shadow.json", out, indent=1, stamp=True)
    return out


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "records"
    steps = {"records": records, "pairs": pairs, "cluster": cluster, "strong": strong, "shadow": shadow}
    for name in (list(steps) if what == "all" else [what]):
        steps[name]()


if __name__ == "__main__":
    main()
