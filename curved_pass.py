#!/usr/bin/env python3
"""EXPERIMENTAL, not part of the search: a curved second pass after the
production cadence test, over step 4's blocks at matched false-candidate
rates (comparable.md step 9).

    python curved_pass.py run KIC8462852 [--blocks N]   each block of step 4: false candidates and planted signals
    python curved_pass.py tables KIC8462852              the rates, the matched cuts and the recovery tables

The production test (onoff.judge) runs first, unchanged. The second pass
then looks only at what it did not settle: hits at the cut that are no
member of a production candidate or of a production interference event
(an OFF veto found along the straight track stands). From any two ON looks
with such hits, it joins a pair whose drifts differ by what a constant
acceleration |a| <= a_max allows (and whose frequencies agree with that
curve), needs the third ON look on the curve (a hit there or the track at
S/N 5, onoff.ON_MIN), and measures the OFF looks along the curve and where
the first hit was (curved.judge's rules, seeded from every pair of ON looks,
not only the first and last). What it keeps is added to the production
candidates.

On each of step 4's 121 blocks (matched.choose_blocks, the same blocks and
the same archive reads), searched once:

- false candidates: every one of the 19 wrong choices of ON looks, at each
  of step 4's cuts, production alone and production with the second pass at
  each a_max; every eligible hit in those choices goes through the pass, not
  only planted ones. Distinct signals per block by shared member hits
  (matched.shared_hits), blocks the unit, weighted by class (step 4's rule).
- recovery: signals planted in the true ON looks (STRENGTHS x the drift
  bins x ACCELS, a constant acceleration over the cadence), searched and
  judged at every cut. A signal is recovered by a kept candidate whose every
  ON member hit is on its track in that look (the best straight line over
  the look: frequency within 6 Hz + |a| T^2 / 12 of its start, drift within
  0.05 Hz/s of its slope at mid-look); a match the unplanted block's true
  choice already had is a false association, counted apart.

Then each configuration's cut is matched at 0.1 false candidates a block
(matched_tables' rule) and the recovery compared there.

One JSON a block under data/curved_pass/TARGET-SESSION/, resumable. Nothing
here changes the search, the cadence test, the store or step 4's records.
"""
import argparse
import itertools
import json
import math
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import curved
import injection
import matched
import matched_tables
import measure
import onoff
import seti
import store
import yoke

ROOT = yoke.DATA / "curved_pass"
A_MAX = (1e-4, 3e-4, 1e-3)                       # Hz/s^2: the second pass's bounds
ACCELS = (0.0, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3)    # Hz/s^2: the planted signals' |a|
STRENGTHS = (30, 60, 120, 400)                   # S_in
CUTS = matched.CUTS_OURS
SEED = 61
FORMAT = 1
TRUE = matched.TRUE


def key(a):
    return f"pass_{a:g}"


CONFIGS = ("production",) + tuple(key(a) for a in A_MAX)


# --- the second pass ------------------------------------------------------------

def second_pass(looks, events, a_max):
    """Candidates and interference from curved tracks through hits the
    production test left unsettled: [{members {position: hit}, label, a}]."""
    taken = set()
    for e in events:
        if e["label"] in ("candidate", "interference"):
            taken.update((p, i) for p, i in enumerate(e["matches"]) if i is not None)
    on = [lk for lk in looks if lk.on]
    off = [lk for lk in looks if not lk.on]

    def free(lk):
        return sorted(((h["frequency_mhz"], i, h) for i, h in enumerate(lk.hits)
                       if not h.get("shadow") and (lk.position, i) not in taken), key=lambda x: x[0])
    pool = {lk.position: free(lk) for lk in on}
    out, seen = [], set()
    for la, lb in itertools.combinations(on, 2):
        lr = next(lk for lk in on if lk is not la and lk is not lb)
        span = curved._t(lb, la)
        cands_b = pool[lb.position]
        fb_arr = np.array([x[0] for x in cands_b])
        reach_hz = 4.0 * span + 0.5 * a_max * span * span + 10 * la.width_hz
        for _, ia, ha in pool[la.position]:
            lo = np.searchsorted(fb_arr, ha["frequency_mhz"] - reach_hz / 1e6)
            hi = np.searchsorted(fb_arr, ha["frequency_mhz"] + reach_hz / 1e6, "right")
            for _, ib, hb in cands_b[lo:hi]:
                a = (hb["drift_hz_s"] - ha["drift_hz_s"]) / span
                a_tol = 2 * (curved.D_TOL_STEPS * la.step + 0.05 * abs(ha["drift_hz_s"])) / span
                if abs(a) > a_max + a_tol:
                    continue
                a_use = max(-a_max, min(a_max, a))
                fb, db = curved._track(ha["frequency_mhz"], ha["drift_hz_s"], a_use, lb, la)
                if not curved._on_track(hb, fb, db, lb):
                    continue
                fr, dr = curved._track(ha["frequency_mhz"], ha["drift_hz_s"], a_use, lr, la)
                members = {la.position: ia, lb.position: ib}
                mid = [i for i in curved._hits_near(lr, fr, dr) if (lr.position, i) not in taken]
                if mid:
                    members[lr.position] = max(mid, key=lambda i: lr.hits[i]["snr"])
                else:
                    snr, _, _ = lr.best_track(lr.channel(fr), dr, curved.F_TOL_CHANNELS, curved.D_TOL_STEPS)
                    if snr is None or snr < onoff.ON_MIN:
                        continue
                sig = frozenset(members.items())
                if sig in seen:
                    continue
                seen.add(sig)
                off_max, off_hit = -np.inf, False
                for lk in off:
                    fo, do = curved._track(ha["frequency_mhz"], ha["drift_hz_s"], a_use, lk, la)
                    for f_try in (fo, ha["frequency_mhz"]):
                        snr, _, _ = lk.best_track(lk.channel(f_try), do, curved.F_TOL_CHANNELS, curved.D_TOL_STEPS)
                        if snr is not None:
                            off_max = max(off_max, snr)
                        off_hit = off_hit or bool(curved._hits_near(lk, f_try, do, any_strength=True))
                label = "interference" if (off_hit or off_max >= onoff.OFF_MAX) else "candidate"
                out.append({"members": members, "label": label, "a": round(a, 7)})
    return out


def _kept_pass(looks, found, order):
    """Second-pass candidates in matched._our_kept's form."""
    out = []
    for e in found:
        if e["label"] != "candidate":
            continue
        mem = sorted(e["members"].items())
        members = [[order[p], int(i), looks[p].hits[i]["frequency_mhz"], looks[p].hits[i]["drift_hz_s"]]
                   for p, i in mem]
        top = max(mem, key=lambda m: looks[m[0]].hits[m[1]]["snr"])
        h = looks[top[0]].hits[top[1]]
        out.append({"f_mhz": round(h["frequency_mhz"], 6), "drift": round(h["drift_hz_s"], 4),
                    "snr": round(h["snr"], 2), "look": order[top[0]], "members": members, "tracks": [],
                    "a": e["a"]})
    return out


def judge_all(cad, searched, ons, cut, caches):
    """{config: kept candidates} for one choice and cut."""
    looks, events, order = matched.our_events(cad, searched, ons, cut, caches)
    prod = matched._our_kept(looks, events, order)
    out = {"production": prod}
    for a in A_MAX:
        out[key(a)] = prod + _kept_pass(looks, second_pass(looks, events, a), order)
    for lk in looks:
        lk.flat = None
    return out


# --- planting curved signals ----------------------------------------------------

def tones(cad, rng):
    """One signal a strength, drift bin and |a| (signs at random), clear of
    each other."""
    n = len(STRENGTHS) * len(measure.DRIFT_BINS) * len(ACCELS)
    ts = injection.tones_for(cad, n, 0, rng, strengths=STRENGTHS)
    by_cell = {}
    for t in ts:
        by_cell.setdefault((t["bin"], t["s_in"]), []).append(t)
    for cell in by_cell.values():
        for k, t in enumerate(cell):
            t["accel"] = ACCELS[k % len(ACCELS)] * (1 if rng.random() < 0.5 else -1)
    return ts


def plant(cad, ts):
    t0 = cad[0]["s"]["tstart"]
    per_channel = cad[0]["s"]["foff"] * 1e6
    out = []
    for j, look in enumerate(cad):
        s, raw, sigma = look["s"], look["raw"], look["sigma"]
        if j % 2:
            out.append(raw)
            continue
        dt = (s["tstart"] - t0) * 86400
        here = []
        for t in ts:
            a = t["accel"]
            x = t["x0"] + (t["drift"] * dt + 0.5 * a * dt * dt) / per_channel
            c = int(min(max(round(x), 0), raw.shape[1] - 1))
            here.append((x, t["drift"] + a * dt, t["s_in"] * sigma[c] / math.sqrt(raw.shape[0]), a))
        out.append(measure.plant(raw, here, s["tsamp"], s["foff"]))
    return out


def expected(cad, t, j):
    """Where a planted signal's best straight line over look j starts (MHz),
    its slope (Hz/s) and the frequency tolerance (Hz)."""
    s0, s = cad[0]["s"], cad[j]["s"]
    per_channel = s0["foff"] * 1e6
    a = t["accel"]
    dt = (s["tstart"] - s0["tstart"]) * 86400
    T = cad[j]["raw"].shape[0] * s["tsamp"]
    x = t["x0"] + (t["drift"] * dt + 0.5 * a * dt * dt - a * T * T / 12) / per_channel
    return s["fch1"] + x * s["foff"], t["drift"] + a * (dt + T / 2), matched.TOL_HZ + abs(a) * T * T / 12


def _matches(cad, t, ev):
    ok = 0
    for j, f, d in ((m[0], m[2], m[3]) for m in ev["members"]):
        fe, de, tol = expected(cad, t, j)
        ok += abs((f - fe) * 1e6) <= tol and abs(d - de) <= matched.TOL_DRIFT
    return ok, len(ev["members"])


def status(cad, t, planted, plain):
    """recovered / false association / missed, strict (every ON member hit
    on the track)."""
    def got(evs):
        return any(n >= 1 and ok == n for ok, n in (_matches(cad, t, ev) for ev in evs))
    if got(planted):
        return "false association" if got(plain) else "recovered"
    return "missed"


# --- a block ---------------------------------------------------------------------

def block(k, cls, slices, urls, rng):
    times = {}
    t = time.monotonic()
    cad = matched._cadence(slices, urls)
    searched = matched.our_search(cad)
    times["search_s"] = round(time.monotonic() - t, 1)
    t = time.monotonic()
    false, true_plain = {}, {}
    caches = [{} for _ in range(6)]
    for ons in itertools.combinations(range(6), 3):
        for cut in CUTS:
            got = judge_all(cad, searched, ons, cut, caches)
            for cfg, kept in got.items():
                if ons == TRUE:
                    true_plain.setdefault(matched.ck(cut), {})[cfg] = kept
                else:
                    false.setdefault(matched.ck(cut), {}).setdefault(cfg, {})[str(ons)] = kept
    times["judge_s"] = round(time.monotonic() - t, 1)
    del searched, caches
    t = time.monotonic()
    ts = tones(cad, rng)
    cad_p = [dict(c, spectra=p) for c, p in zip(cad, plant(cad, ts))]
    searched_p = matched.our_search(cad_p)
    caches = [{} for _ in range(6)]
    true_planted = {matched.ck(cut): judge_all(cad_p, searched_p, TRUE, cut, caches) for cut in CUTS}
    times["planted_s"] = round(time.monotonic() - t, 1)
    rows = []
    for tone in ts:
        r = {k2: tone[k2] for k2 in ("x0", "drift", "accel", "s_in", "bin")}
        r["status"] = {c: {cfg: status(cad, tone, true_planted[c][cfg], true_plain[c][cfg]) for cfg in CONFIGS}
                       for c in true_planted}
        rows.append(r)
    return {"format": FORMAT, "block": k, "class": cls, "tstarts": [c["s"]["tstart"] for c in cad],
            "false": false, "tones": rows, "times": times,
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def folder(target, session):
    return ROOT / f"{target}-{session}"


def run(target, count=None, say=print, shard=(0, 1)):
    """shard (i, n): only every n-th chosen block from the i-th, so n
    processes can share the run (each block has its own seed, so the
    records do not depend on the order or the split)."""
    db = store.connect()
    session, urls = store.cadence_files(db, target)
    chosen, totals = matched.choose_blocks(db, session)
    db.close()
    step4 = json.loads((matched.folder(target, session) / "blocks.json").read_text(encoding="utf-8"))
    assert {int(b): c for b, c in step4["chosen"].items()} == chosen, "not step 4's blocks"
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    base = folder(target, session)
    base.mkdir(parents=True, exist_ok=True)
    (base / "blocks.json").write_text(json.dumps({"chosen": chosen, "of": totals, "a_max": A_MAX, "accels": ACCELS,
                                                  "strengths": STRENGTHS, "cuts": CUTS, "seed": SEED},
                                                 indent=1), encoding="utf-8")
    todo_all = [b for i, b in enumerate(chosen) if i % shard[1] == shard[0]
                and not (base / f"block_{b:03d}.json").exists()]
    todo = todo_all if count is None else todo_all[:count]
    say(f"{target} {session}: {len(chosen)} blocks, {len(chosen) - len(todo_all)} done before, {len(todo)} to run",
        flush=True)

    def fetch(k):
        return seti.read_looks(urls, *block_list[k])

    with ThreadPoolExecutor(max_workers=1) as ahead:
        coming = ahead.submit(fetch, todo[0]) if todo else None
        for i, k in enumerate(todo):
            slices = coming.result()
            coming = ahead.submit(fetch, todo[i + 1]) if i + 1 < len(todo) else None
            if (base / f"block_{k:03d}.json").exists():
                continue
            started = time.monotonic()
            rec = block(k, chosen[k], slices, urls, np.random.default_rng([SEED, k]))
            del slices
            rec["times"]["block_s"] = round(time.monotonic() - started, 1)
            (base / f"block_{k:03d}.json").write_text(json.dumps(rec), encoding="utf-8")
            f10 = rec["false"]["10"]
            say(f"  block {k} ({chosen[k]}): false at cut 10 " + ", ".join(
                f"{cfg} {len(matched.shared_hits(f10[cfg]))}" for cfg in CONFIGS) + "; recovered at cut 10 " + ", ".join(
                f"{cfg} {sum(t['status']['10'][cfg] == 'recovered' for t in rec['tones'])}" for cfg in CONFIGS)
                + f" of {len(rec['tones'])}; {rec['times']['block_s']} s", flush=True)
    shutil.rmtree(ROOT / "work", ignore_errors=True)
    return len(list(base.glob("block_*.json")))


# --- tables -----------------------------------------------------------------------

def tables(target, say=print):
    db = store.connect()
    session, _ = store.cadence_files(db, target)
    db.close()
    base = folder(target, session)
    meta = json.loads((base / "blocks.json").read_text(encoding="utf-8"))
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob("block_*.json"))]
    recs = [r for r in recs if r.get("format") == FORMAT]
    rng = np.random.default_rng(1)
    total = meta["of"]["clean"] + meta["of"]["crowded"]
    weights = {c: meta["of"][c] / total for c in ("clean", "crowded")}
    curves = {cfg: {matched.ck(c): matched_tables._rate(
        recs, lambda r, c=c, cfg=cfg: len(matched.shared_hits(r["false"][matched.ck(c)][cfg])), weights, rng)
        for c in CUTS} for cfg in CONFIGS}
    cuts = {cfg: matched_tables._matched_cut(curves[cfg]) for cfg in CONFIGS}
    tones_all = [t for r in recs for t in r["tones"]]

    def recovery(cfg, cut):
        out = []
        for acc in ACCELS:
            for s_in in STRENGTHS:
                cell = [t for t in tones_all if abs(abs(t["accel"]) - acc) < 1e-12 and t["s_in"] == s_in]
                n = sum(t["status"][cut][cfg] != "false association" for t in cell)
                k = sum(t["status"][cut][cfg] == "recovered" for t in cell)
                out.append({"accel": acc, "s_in": s_in, "planted": len(cell), "counted": n, "recovered": k,
                            "share": round(k / n, 3) if n else None, "interval": measure.wilson(k, n) if n else None})
        return out
    at = {}
    prod_cut = cuts["production"]["cut"]
    for cfg in CONFIGS:
        c = cuts[cfg]["cut"]
        at[cfg] = {"matched_cut": c,
                   "at_matched": recovery(cfg, c) if c is not None else None,
                   "at_production_matched_cut": recovery(cfg, prod_cut) if prod_cut is not None else None,
                   "at_published_cut": recovery(cfg, "10")}
    record = {"target": target, "session": session, "blocks": len(recs), "of_chosen": len(meta["chosen"]),
              "weights": weights, "rate_matched": matched_tables.RATE, "a_max": A_MAX, "accels": ACCELS,
              "strengths": STRENGTHS, "false_curves": curves, "matched_cuts": cuts, "recovery": at,
              "kind": "measured", "experimental": True}
    yoke.write(yoke.DATA / "measurements" / "curved-pass.json", record, stamp=True)
    say(f"{len(recs)} blocks of {len(meta['chosen'])}. False candidates a block (95% interval), by cut:")
    say("  cut   " + "".join(f"{cfg:>24}" for cfg in CONFIGS))
    for c in CUTS:
        say(f"  {c:>4}  " + "".join(f"{curves[cfg][matched.ck(c)]['per_block']:>9.3f} "
                                    f"({curves[cfg][matched.ck(c)]['interval'][0]:.3f}-"
                                    f"{curves[cfg][matched.ck(c)]['interval'][1]:.3f})" for cfg in CONFIGS))
    say("Matched cuts (0.1 a block): " + ", ".join(f"{cfg} {cuts[cfg]['cut']}" for cfg in CONFIGS))
    for label in ("at_matched", "at_production_matched_cut", "at_published_cut"):
        say(f"\nRecovered ({label}), by |a| and S_in:")
        say("  |a|      S_in " + "".join(f"{cfg:>14}" for cfg in CONFIGS))
        for i, row in enumerate(at["production"][label] or []):
            say(f"  {row['accel']:<8g} {row['s_in']:>4} " + "".join(
                f"{(at[cfg][label][i]['share'] if at[cfg][label] else float('nan')) or 0:>14.0%}" for cfg in CONFIGS))
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("target")
    r.add_argument("--blocks", type=int)
    r.add_argument("--shard", default="0/1", help="i/n: this process's share of the blocks")
    t = sub.add_parser("tables")
    t.add_argument("target")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run(a.target, a.blocks, shard=tuple(int(x) for x in a.shard.split("/")))
    else:
        tables(a.target)


if __name__ == "__main__":
    main()
