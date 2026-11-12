#!/usr/bin/env python3
"""EXPERIMENTAL, not part of the search: a curved second pass after the
production cadence test, over step 4's blocks at matched false-candidate
rates (comparable.md step 9).

    python curved_pass.py run KIC8462852 [--blocks N]   each block of step 4: false candidates and planted signals
    python curved_pass.py recheck KIC8462852 [--shard i/n]  add the three-look recovery test to recorded blocks
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
  choice already had is a false association, counted apart. That is the
  strict test (the first measurements); the three-look test, step 4's
  standard, needs every one of the three ON looks on the track, by its
  member hit or, where it has none at the cut, by the track measured there
  (status_v2, with how many of the three are formal hits). `recheck` adds
  it to blocks recorded before it (the true choice judged again, the same
  seeds).

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
                track = None
                mid = [i for i in curved._hits_near(lr, fr, dr) if (lr.position, i) not in taken]
                if mid:
                    members[lr.position] = max(mid, key=lambda i: lr.hits[i]["snr"])
                else:
                    snr, at, d_fit = lr.best_track(lr.channel(fr), dr, curved.F_TOL_CHANNELS, curved.D_TOL_STEPS)
                    if snr is None or snr < onoff.ON_MIN:
                        continue
                    track = (lr.position, at, d_fit, snr)      # the third ON look, measured on the curve
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
                out.append({"members": members, "track": track, "label": label, "a": round(a, 7)})
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
        tracks = []
        if e.get("track"):
            p, at, d_fit, snr = e["track"]
            tracks = [[order[p], looks[p].fch1 + at * looks[p].foff, d_fit, round(snr, 2)]]
        out.append({"f_mhz": round(h["frequency_mhz"], 6), "drift": round(h["drift_hz_s"], 4),
                    "snr": round(h["snr"], 2), "look": order[top[0]], "members": members, "tracks": tracks,
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


def _matches(cad, t, ev, tracks=False):
    """How many of an event's ON member hits (with `tracks`, also the tracks
    measured in its ON looks without a hit) lie on a planted signal's track
    in their look, of how many."""
    rows = [(m[0], m[2], m[3]) for m in ev["members"]] + ([tuple(x[:3]) for x in ev.get("tracks", [])]
                                                         if tracks else [])
    ok = 0
    for j, f, d in rows:
        if f is None or d is None:
            continue
        fe, de, tol = expected(cad, t, j)
        ok += abs((f - fe) * 1e6) <= tol and abs(d - de) <= matched.TOL_DRIFT
    return ok, len(rows)


# Recovery, as step 4's (matched.RECOVERY) but on the curved track. Strict:
# every ON member hit on the track (the first measurements here). Three looks:
# each of the three ON looks on the track, by its member hit or, where it has
# none at the cut, by the track measured there.
WAYS = (("strict", False, lambda ok, n: n >= 1 and ok == n),
        ("three_looks", True, lambda ok, n: ok == n == len(TRUE)))


def status(cad, t, planted, plain):
    """recovered / false association / missed, strict (every ON member hit
    on the track). Format 1's test, kept for its records."""
    return statuses(cad, t, planted, plain)["strict"]


def statuses(cad, t, planted, plain):
    """Each way of WAYS: recovered / false association / missed; and, for
    three looks, how many of the three ON looks the recovering event holds by
    a formal hit (the most of any such event)."""
    out = {}
    for name, tracks, test in WAYS:
        hit = [ev for ev in planted if test(*_matches(cad, t, ev, tracks))]
        if not hit:
            out[name] = "missed"
        elif any(test(*_matches(cad, t, ev, tracks)) for ev in plain):
            out[name] = "false association"
        else:
            out[name] = "recovered"
        if tracks:
            out["hits"] = max(len(ev["members"]) for ev in hit) if hit else None
    return out


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
        both = {c: {cfg: statuses(cad, tone, true_planted[c][cfg], true_plain[c][cfg]) for cfg in CONFIGS}
                for c in true_planted}
        r["status"] = {c: {cfg: v["strict"] for cfg, v in x.items()} for c, x in both.items()}
        r["status_v2"] = both
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


def _recheck_block(k, rec, slices, urls):
    """A block recorded before the three-look test (status_v2): the true
    choice searched and judged again, unplanted and planted with the same
    seed, so the same signals; nothing else of the record changes. Returns
    how many strict statuses differ from the record (0 if reproduced)."""
    cad = matched._cadence(slices, urls)
    assert [c["s"]["tstart"] for c in cad] == rec["tstarts"], "not the recorded block"
    rng = np.random.default_rng([SEED, k])
    searched = matched.our_search(cad)
    caches = [{} for _ in range(6)]
    plain = {matched.ck(cut): judge_all(cad, searched, TRUE, cut, caches) for cut in CUTS}
    del searched, caches
    ts = tones(cad, rng)
    assert all(abs(t["x0"] - r["x0"]) < 1e-9 and t["accel"] == r["accel"] and t["s_in"] == r["s_in"]
               for t, r in zip(ts, rec["tones"])) and len(ts) == len(rec["tones"]), "not the recorded signals"
    cad_p = [dict(c, spectra=p) for c, p in zip(cad, plant(cad, ts))]
    searched_p = matched.our_search(cad_p)
    caches = [{} for _ in range(6)]
    planted = {matched.ck(cut): judge_all(cad_p, searched_p, TRUE, cut, caches) for cut in CUTS}
    differ = 0
    for tone, row in zip(ts, rec["tones"]):
        row["status_v2"] = {c: {cfg: statuses(cad, tone, planted[c][cfg], plain[c][cfg]) for cfg in CONFIGS}
                            for c in planted}
        differ += sum(row["status_v2"][c][cfg]["strict"] != row["status"][c][cfg] for c in planted for cfg in CONFIGS)
    return differ


def recheck(target, say=print, shard=(0, 1)):
    """Add the three-look recovery test (status_v2) to blocks recorded
    without it: only the true choice is judged again (the false candidates
    are recorded already and do not depend on how recovery is tested)."""
    db = store.connect()
    session, urls = store.cadence_files(db, target)
    db.close()
    base = folder(target, session)
    paths = sorted(base.glob("block_*.json"))
    todo = [p for i, p in enumerate(paths) if i % shard[1] == shard[0]
            and "status_v2" not in json.loads(p.read_text(encoding="utf-8"))["tones"][0]]
    say(f"{target} {session}: {len(paths)} blocks recorded, {len(todo)} of this share to check again", flush=True)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])

    def fetch(p):
        rec = json.loads(p.read_text(encoding="utf-8"))
        return rec, seti.read_looks(urls, *block_list[rec["block"]])

    with ThreadPoolExecutor(max_workers=1) as ahead:
        coming = ahead.submit(fetch, todo[0]) if todo else None
        for i, p in enumerate(todo):
            rec, slices = coming.result()
            coming = ahead.submit(fetch, todo[i + 1]) if i + 1 < len(todo) else None
            started = time.monotonic()
            differ = _recheck_block(rec["block"], rec, slices, urls)
            del slices
            rec["recheck"] = {"strict_differ": differ, "s": round(time.monotonic() - started, 1),
                              "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            p.write_text(json.dumps(rec), encoding="utf-8")
            t30 = [t["status_v2"]["30"] for t in rec["tones"]]
            say(f"  block {rec['block']}: strict statuses differing from the record {differ}; at cut 30 "
                + ", ".join(f"{cfg} strict {sum(x[cfg]['strict'] == 'recovered' for x in t30)} three looks "
                            f"{sum(x[cfg]['three_looks'] == 'recovered' for x in t30)}" for cfg in CONFIGS)
                + f"; {rec['recheck']['s']} s", flush=True)


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

    three = all("status_v2" in t for t in tones_all)
    ways = ("strict", "three_looks") if three else ("strict",)

    def st(t, cut, cfg, way):
        return t["status"][cut][cfg] if way == "strict" and not three else t["status_v2"][cut][cfg][way]

    def recovery(cfg, cut, way="strict"):
        out = []
        for acc in ACCELS:
            for s_in in STRENGTHS:
                cell = [t for t in tones_all if abs(abs(t["accel"]) - acc) < 1e-12 and t["s_in"] == s_in]
                n = sum(st(t, cut, cfg, way) != "false association" for t in cell)
                k = sum(st(t, cut, cfg, way) == "recovered" for t in cell)
                row = {"accel": acc, "s_in": s_in, "planted": len(cell), "counted": n, "recovered": k,
                       "share": round(k / n, 3) if n else None, "interval": measure.wilson(k, n) if n else None}
                if way == "three_looks":
                    # of those recovered, by how many of the three ON looks hold a formal hit
                    row["by_hits"] = {h: sum(st(t, cut, cfg, way) == "recovered"
                                             and t["status_v2"][cut][cfg]["hits"] == h for t in cell)
                                      for h in (1, 2, 3)}
                out.append(row)
        return out

    def totals(rows):
        return {"recovered": sum(r["recovered"] for r in rows), "counted": sum(r["counted"] for r in rows)}
    at = {}
    prod_cut = cuts["production"]["cut"]
    for cfg in CONFIGS:
        c = cuts[cfg]["cut"]
        at[cfg] = {"matched_cut": c}
        for way in ways:
            sfx = "" if way == "strict" else "_three_looks"
            at[cfg]["at_matched" + sfx] = recovery(cfg, c, way) if c is not None else None
            at[cfg]["at_production_matched_cut" + sfx] = recovery(cfg, prod_cut, way) if prod_cut is not None else None
            at[cfg]["at_published_cut" + sfx] = recovery(cfg, "10", way)
            if c is not None:
                at[cfg]["totals_at_matched" + sfx] = totals(at[cfg]["at_matched" + sfx])
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
    labels = ("at_matched", "at_production_matched_cut", "at_published_cut")
    if three:
        labels += tuple(x + "_three_looks" for x in labels)
    for label in labels:
        say(f"\nRecovered ({label}), by |a| and S_in:")
        say("  |a|      S_in " + "".join(f"{cfg:>14}" for cfg in CONFIGS))
        for i, row in enumerate(at["production"][label] or []):
            say(f"  {row['accel']:<8g} {row['s_in']:>4} " + "".join(
                f"{(at[cfg][label][i]['share'] if at[cfg][label] else float('nan')) or 0:>14.0%}" for cfg in CONFIGS))
    if three:
        say("\nAt the matched cut: totals, strict and three looks; three-look recoveries by formal hits (1/2/3):")
        for cfg in CONFIGS:
            a, b = at[cfg].get("totals_at_matched"), at[cfg].get("totals_at_matched_three_looks")
            if a and b:
                h = {n: sum(r["by_hits"][n] for r in at[cfg]["at_matched_three_looks"]) for n in (1, 2, 3)}
                say(f"  {cfg:>14}: strict {a['recovered']}/{a['counted']}, three looks {b['recovered']}/{b['counted']}"
                    f"  ({h[1]}/{h[2]}/{h[3]})")
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("target")
    r.add_argument("--blocks", type=int)
    r.add_argument("--shard", default="0/1", help="i/n: this process's share of the blocks")
    c = sub.add_parser("recheck", help="add the three-look recovery test to blocks recorded without it")
    c.add_argument("target")
    c.add_argument("--shard", default="0/1")
    t = sub.add_parser("tables")
    t.add_argument("target")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run(a.target, a.blocks, shard=tuple(int(x) for x in a.shard.split("/")))
    elif a.cmd == "recheck":
        recheck(a.target, shard=tuple(int(x) for x in a.shard.split("/")))
    else:
        tables(a.target)


if __name__ == "__main__":
    main()
