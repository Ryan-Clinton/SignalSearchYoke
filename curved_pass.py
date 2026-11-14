#!/usr/bin/env python3
"""EXPERIMENTAL, not part of the search: a curved second pass after the
production cadence test, over step 4's blocks at matched false-candidate
rates (comparable.md step 9).

    python curved_pass.py run KIC8462852 [--blocks N]   each block of step 4: false candidates and planted signals
    python curved_pass.py recheck KIC8462852 [--shard i/n]  add the three-look recovery test to recorded blocks
    python curved_pass.py orbits KIC8462852 [--shard i/n]   orbital signals with the Earth's motion (orbit-tables)
    python curved_pass.py vet KIC8462852 [--shard i/n]      the checks on what the pass adds (vet-tables)
    python curved_pass.py turboseti KIC8462852 [--shard i/n] turboSETI on the same signals (turboseti-tables)
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
from pathlib import Path

import numpy as np

import check
import curved
import injection
import matched
import matched_tables
import measure
import occupancy
import onoff
import pipelines
import seti
import store
import vetting
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
                off_max, off_hit, offs = -np.inf, False, []
                for lk in off:
                    fo, do = curved._track(ha["frequency_mhz"], ha["drift_hz_s"], a_use, lk, la)
                    snrs = []
                    for f_try in (fo, ha["frequency_mhz"]):
                        snr, _, _ = lk.best_track(lk.channel(f_try), do, curved.F_TOL_CHANNELS, curved.D_TOL_STEPS)
                        snrs.append(None if snr is None else round(snr, 2))
                        if snr is not None:
                            off_max = max(off_max, snr)
                        off_hit = off_hit or bool(curved._hits_near(lk, f_try, do, any_strength=True))
                    offs.append((lk.position, *snrs))         # along the curve, where the first hit was
                label = "interference" if (off_hit or off_max >= onoff.OFF_MAX) else "candidate"
                out.append({"members": members, "track": track, "offs": offs, "label": label, "a": round(a, 7)})
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


def _matches(cad, t, ev, tracks=False, exp=None):
    """How many of an event's ON member hits (with `tracks`, also the tracks
    measured in its ON looks without a hit) lie on a planted signal's track
    in their look, of how many. `exp`: where the signal is in a look
    (expected's form; expected if not given)."""
    exp = exp or expected
    rows = [(m[0], m[2], m[3]) for m in ev["members"]] + ([tuple(x[:3]) for x in ev.get("tracks", [])]
                                                         if tracks else [])
    ok = 0
    for j, f, d in rows:
        if f is None or d is None:
            continue
        fe, de, tol = exp(cad, t, j)
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


def statuses(cad, t, planted, plain, exp=None):
    """Each way of WAYS: recovered / false association / missed; and, for
    three looks, how many of the three ON looks the recovering event holds by
    a formal hit (the most of any such event)."""
    out = {}
    for name, tracks, test in WAYS:
        hit = [ev for ev in planted if test(*_matches(cad, t, ev, tracks, exp))]
        if not hit:
            out[name] = "missed"
        elif any(test(*_matches(cad, t, ev, tracks, exp)) for ev in plain):
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
    db.close()
    # matched.py's blocks for the session, as its run chose them (step 4's rule, or step 10's).
    step4 = json.loads((matched.folder(target, session) / "blocks.json").read_text(encoding="utf-8"))
    chosen, totals = {int(b): c for b, c in step4["chosen"].items()}, step4["of"]
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


# --- orbits: sinusoidal line-of-sight motion and the Earth's own -------------------

# A transmitter on a circular orbit (or a spinning body) seen edge-on: its
# line-of-sight acceleration a_pk cos(w t - phase), so the drift and the
# acceleration both change over the cadence (the second pass assumes a
# constant acceleration). On top, the Earth's turning and orbit at Green Bank
# toward the target (vetting.expected_drift), beyond the drift it has at the
# cadence's start (that part is the planted drift's own). A no-orbit case,
# the Earth's motion alone, is the control. Fixed before the run: the second
# pass unchanged, the same blocks, the matched cut (30) and the published
# (10), recovery by the three-look standard.
#
# What the cases are, physically (line-of-sight acceleration a_pk c / f; at
# 2 GHz 10^-4 Hz/s^2 is 0.015 m/s^2, 10^-3 is 0.15 m/s^2, against the Earth's
# turning at Green Bank, 0.025 m/s^2 at most): a 1-day orbit with a_pk
# 10^-3 at 2 GHz is a line-of-sight speed of 2.1 km/s (a = v w), a 10-day
# orbit 21 km/s, a 10-hour period 0.86 km/s, which is more a fast spin of a
# body (a transmitter on a planet turning in 10 hours at 0.86 km/s, about
# twice Jupiter's equatorial speed) than an orbit. They are a grid over the
# range where the pass's bound matters, seen edge-on (inclination folds into
# a_pk), not a sample of real planetary systems.
#
# Two controls on the matching: "tight", the same recovery with the
# frequency tolerance 6 Hz only (not widened by the path's departure from
# its best line in a look), and "mirror", each signal scored against the
# path it would have with its phase turned half a cycle (the opposite
# curvature and jerk): a recovery there is the matching being loose, not
# the signal found.
ORBIT_PEAKS = (1e-4, 3e-4, 1e-3)                 # Hz/s^2: peak line-of-sight acceleration
PERIODS_H = (10.0, 24.0, 240.0)                  # a fast spin, a 1-day and a 10-day orbit
ORBIT_CASES = ((0.0, None),) + tuple((a, p) for a in ORBIT_PEAKS for p in PERIODS_H)
ORBIT_STRENGTHS = (60, 120, 400)                 # S_in 30 is under the matched cut (0% there above)
SEED_ORBIT = 62


def _earth(cad, ra_hours, dec_deg):
    """The Earth's path toward the target per MHz of sky frequency: a
    function of t (s from the cadence's start) giving the frequency offset
    (Hz per MHz) beyond the drift it has at t = 0."""
    s0, s5 = cad[0]["s"], cad[-1]["s"]
    end = (s5["tstart"] - s0["tstart"]) * 86400 + cad[-1]["raw"].shape[0] * s5["tsamp"] + 10
    grid = np.arange(0.0, end, 1.0)
    d = np.array([vetting.expected_drift(1.0, s0["tstart"] + g / 86400, ra_hours, dec_deg)[0] for g in grid])
    cum = np.concatenate([[0.0], np.cumsum((d[1:] + d[:-1]) / 2 - d[0])])
    return lambda t: np.interp(t, grid, cum)


def orbit_offset(t, tau, earth):
    """A planted orbital signal's offset from its start frequency (Hz), tau
    s from the cadence's start (array or number)."""
    tau = np.asarray(tau, dtype=float)
    off = t["drift"] * tau + t["f_mhz"] * earth(tau)
    if t["a_pk"]:
        w = 2 * math.pi / (t["period_h"] * 3600)
        a, th = t["a_pk"], t["phase"]
        off = off + (a * math.cos(th) * (1 - np.cos(w * tau)) + a * math.sin(th) * (w * tau - np.sin(w * tau))) / w ** 2
    return off


def orbit_tones(cad, rng):
    """Each ORBIT_CASES case in every drift bin and strength, a random phase."""
    s = cad[0]["s"]
    n = len(ORBIT_STRENGTHS) * len(measure.DRIFT_BINS) * len(ORBIT_CASES)
    ts = injection.tones_for(cad, n, 0, rng, strengths=ORBIT_STRENGTHS)
    by_cell = {}
    for t in ts:
        by_cell.setdefault((t["bin"], t["s_in"]), []).append(t)
    for cell in by_cell.values():
        for k, t in enumerate(cell):
            t["a_pk"], t["period_h"] = ORBIT_CASES[k % len(ORBIT_CASES)]
            t["phase"] = float(rng.uniform(0, 2 * math.pi))
            t["f_mhz"] = s["fch1"] + t["x0"] * s["foff"]
    return ts


def orbit_plant(cad, ts, earth):
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
            start = float(orbit_offset(t, dt, earth))
            x = t["x0"] + start / per_channel
            c = int(min(max(round(x), 0), raw.shape[1] - 1))

            def path(tau, t=t, dt=dt, start=start):
                return orbit_offset(t, dt + tau, earth) - start
            here.append((x, 0.0, t["s_in"] * sigma[c] / math.sqrt(raw.shape[0]), path))
        out.append(measure.plant(raw, here, s["tsamp"], s["foff"]))
    return out


def orbit_expected(earth, widen=True):
    """expected's form for orbital signals: the best straight line over look
    j fitted to the path (start MHz, slope Hz/s), the tolerance 6 Hz plus the
    path's largest departure from that line (with `widen`; 6 Hz alone
    without). Kept for each signal and look: it is asked for every event."""
    memo = {}

    def exp(cad, t, j):
        k = (id(t), j)
        if k not in memo:
            memo[k] = (t, _fit(cad, t, j))
        return memo[k][1]

    def _fit(cad, t, j):
        s0, s = cad[0]["s"], cad[j]["s"]
        dt = (s["tstart"] - s0["tstart"]) * 86400
        T = cad[j]["raw"].shape[0] * s["tsamp"]
        tau = np.linspace(0.0, T, 65)
        f = orbit_offset(t, dt + tau, earth)
        slope, start = np.polyfit(tau, f, 1)
        dev = float(np.max(np.abs(f - (start + slope * tau)))) if widen else 0.0
        return s0["fch1"] + t["x0"] * s0["foff"] + start / 1e6, float(slope), matched.TOL_HZ + dev
    return exp


def mirror(t):
    """The same signal with its phase turned half a cycle."""
    return dict(t, phase=t["phase"] + math.pi)


def _orbit_block(k, slices, urls, coords):
    cad = matched._cadence(slices, urls)
    rng = np.random.default_rng([SEED_ORBIT, k])
    earth = _earth(cad, *coords)
    times = {}
    t = time.monotonic()
    searched = matched.our_search(cad)
    caches = [{} for _ in range(6)]
    plain = {matched.ck(cut): judge_all(cad, searched, TRUE, cut, caches) for cut in CUTS}
    del searched, caches
    ts = orbit_tones(cad, rng)
    cad_p = [dict(c, spectra=p) for c, p in zip(cad, orbit_plant(cad, ts, earth))]
    searched_p = matched.our_search(cad_p)
    caches = [{} for _ in range(6)]
    planted = {matched.ck(cut): judge_all(cad_p, searched_p, TRUE, cut, caches) for cut in CUTS}
    times["block_s"] = round(time.monotonic() - t, 1)
    exp, tight = orbit_expected(earth), orbit_expected(earth, widen=False)
    mirrors = [mirror(t) for t in ts]
    span = (cad[-1]["s"]["tstart"] - cad[0]["s"]["tstart"]) * 86400 + cad[-1]["raw"].shape[0] * cad[-1]["s"]["tsamp"]
    grid = np.linspace(0.0, span, 200)
    rows = []
    for tone, mir in zip(ts, mirrors):
        f = orbit_offset(tone, grid, earth)
        acc = np.gradient(np.gradient(f, grid), grid)[2:-2]
        r = {k2: tone[k2] for k2 in ("x0", "drift", "s_in", "bin", "a_pk", "period_h", "phase", "f_mhz")}
        r["accel_range"] = [round(float(acc.min()), 8), round(float(acc.max()), 8)]
        r["status"] = {c: {cfg: statuses(cad, tone, planted[c][cfg], plain[c][cfg], exp) for cfg in CONFIGS}
                       for c in planted}
        r["status_tight"] = {c: {cfg: statuses(cad, tone, planted[c][cfg], plain[c][cfg], tight)["three_looks"]
                                 for cfg in CONFIGS} for c in planted}
        r["status_mirror"] = None if not tone["a_pk"] else {
            c: {cfg: statuses(cad, mir, planted[c][cfg], plain[c][cfg], exp)["three_looks"] for cfg in CONFIGS}
            for c in planted}
        rows.append(r)
    times["scored_s"] = round(time.monotonic() - t, 1)
    return {"format": 2, "block": k, "tstarts": [c["s"]["tstart"] for c in cad], "coords": list(coords),
            "tones": rows, "times": times, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def orbit_folder(target, session):
    return ROOT / f"orbits-{target}-{session}"


def orbits(target, say=print, shard=(0, 1), count=None):
    """Orbital signals planted in the true ON looks of step 4's blocks (the
    false candidates do not change: the pass is the same)."""
    db = store.connect()
    session, urls = store.cadence_files(db, target)
    row = db.execute("SELECT ra_hours, dec_degrees FROM files WHERE url=?", (urls[0],)).fetchone()
    chosen, _ = matched.choose_blocks(db, session)
    db.close()
    coords = (row["ra_hours"], row["dec_degrees"])
    base = orbit_folder(target, session)
    base.mkdir(parents=True, exist_ok=True)
    todo = [b for i, b in enumerate(chosen) if i % shard[1] == shard[0] and not (base / f"block_{b:03d}.json").exists()]
    todo = todo if count is None else todo[:count]
    say(f"{target} {session}: {len(todo)} blocks of this share to run (RA {coords[0]:.4f} h, Dec {coords[1]:.4f})",
        flush=True)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])

    def fetch(b):
        return seti.read_looks(urls, *block_list[b])

    with ThreadPoolExecutor(max_workers=1) as ahead:
        coming = ahead.submit(fetch, todo[0]) if todo else None
        for i, b in enumerate(todo):
            slices = coming.result()
            coming = ahead.submit(fetch, todo[i + 1]) if i + 1 < len(todo) else None
            started = time.monotonic()
            rec = _orbit_block(b, slices, urls, coords)
            rec["class"] = chosen[b]
            rec["times"]["wall_s"] = round(time.monotonic() - started, 1)
            del slices
            (base / f"block_{b:03d}.json").write_text(json.dumps(rec), encoding="utf-8")
            t30 = [t["status"]["30"] for t in rec["tones"]]
            say(f"  block {b}: three looks at cut 30 " + ", ".join(
                f"{cfg} {sum(x[cfg]['three_looks'] == 'recovered' for x in t30)}" for cfg in CONFIGS)
                + f" of {len(t30)}; {rec['times']['block_s']} s", flush=True)


def orbit_tables(target, say=print):
    db = store.connect()
    session, _ = store.cadence_files(db, target)
    db.close()
    db = store.connect()
    chosen, _ = matched.choose_blocks(db, session)
    db.close()
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(orbit_folder(target, session).glob("block_*.json"))]
    recs = [r for r in recs if r.get("format") == 2]
    missing = sorted(set(chosen) - {r["block"] for r in recs})
    tones_all = [t for r in recs for t in r["tones"]]
    out = {}
    for cut in ("30", "10"):
        for way in ("three_looks", "strict"):
            rows = []
            for a_pk, period in ORBIT_CASES:
                for s_in in ORBIT_STRENGTHS:
                    cell = [t for t in tones_all if t["a_pk"] == a_pk and t["period_h"] == period and t["s_in"] == s_in]
                    row = {"a_pk": a_pk, "period_h": period, "s_in": s_in, "planted": len(cell),
                           "accel_seen": [min((t["accel_range"][0] for t in cell), default=None),
                                          max((t["accel_range"][1] for t in cell), default=None)]}
                    for cfg in CONFIGS:
                        st = [t["status"][cut][cfg] for t in cell]
                        n = sum(x[way] != "false association" for x in st)
                        k = sum(x[way] == "recovered" for x in st)
                        row[cfg] = {"recovered": k, "counted": n, "false_association": len(st) - n,
                                    "share": round(k / n, 3) if n else None,
                                    "interval": measure.wilson(k, n) if n else None}
                        if way == "three_looks":
                            row[cfg]["by_hits"] = {h: sum(x[way] == "recovered" and x["hits"] == h for x in st)
                                                   for h in (1, 2, 3)}
                            row[cfg]["tight"] = sum(t["status_tight"][cut][cfg] == "recovered" for t in cell)
                            row[cfg]["mirror"] = (sum(t["status_mirror"][cut][cfg] == "recovered" for t in cell)
                                                  if a_pk else None)
                    rows.append(row)
            out[f"cut_{cut}_{way}"] = rows
    times = {k: round(sum(r["times"].get(k, 0) for r in recs) / 3600, 2) for k in ("block_s", "scored_s", "wall_s")}
    record = {"target": target, "session": session, "blocks": len(recs), "missing_blocks": missing,
              "hours": times, "cases": ORBIT_CASES,
              "strengths": ORBIT_STRENGTHS, "a_max": A_MAX, "seed": SEED_ORBIT, "recovery": out,
              "kind": "measured", "experimental": True}
    yoke.write(yoke.DATA / "measurements" / "curved-orbits.json", record, stamp=True)
    say(f"{len(recs)} blocks of {len(chosen)} (missing {missing}), {len(tones_all)} orbital signals; hours {times}")
    for name in ("cut_30_three_looks", "cut_10_three_looks", "cut_30_strict"):
        say("")
        say(f"{name}: a_pk, period h, S_in: " + "  ".join(CONFIGS) + "  (false associations: production/last)")
        for row in out[name]:
            say(f"  {row['a_pk']:<7g} {str(row['period_h']):>6} {row['s_in']:>4} " + "".join(
                f"{row[cfg]['recovered']:>6}/{row[cfg]['counted']:<5}" for cfg in CONFIGS)
                + f"  fa {row['production']['false_association']}/{row[CONFIGS[-1]]['false_association']}"
                + (f"  tight {row['production']['tight']}/{row[CONFIGS[-1]]['tight']}"
                   f"  mirror {row['production']['mirror']}/{row[CONFIGS[-1]]['mirror']}" if "tight" in row["production"] else ""))
    for cut in ("30", "10"):
        say("")
        say(f"cut {cut} three looks, totals and formal hits 1/2/3:")
        rows = out[f"cut_{cut}_three_looks"]
        for cfg in CONFIGS:
            say(f"  {cfg:>14}: {sum(r[cfg]['recovered'] for r in rows)}/{sum(r[cfg]['counted'] for r in rows)}  "
                + "/".join(str(sum(r[cfg]['by_hits'][h] for r in rows)) for h in (1, 2, 3)))
    return record


# --- the checks on what the pass adds -------------------------------------------------

# Three ways, on production's and the pass's candidates alike:
# - "uniform": as step 4 ran the checks on its wrong-choice candidates
#   (measure.vet_hook): the cadence's own hits for the session's, no
#   recurrence, the uniform chances. Partial checks, kept for comparison
#   with step 4's held-out figures.
# - "measured": the same with the session's measured occupancy for checks 7
#   and 9. Partial checks too.
# - "store": the full checks a sweep's candidate gets (check.vet_from_store):
#   recurrence from the store's hits (every file outside the choice's ON
#   looks; at present the store holds this one session, so these are the
#   cadence's other looks over the whole band, at the sweep's cut and its
#   shadow hits), check 6's background from them, the session's hits at the
#   cut for checks 8 and 9, its measured occupancy, its own target.
# At the published cut
# (10) and the matched (30): every wrong-choice candidate, and, with the same
# plantings as `run` (seed 61), the candidates that recover a planted signal
# by three looks, so the checks' cost to real curved signals is measured
# beside what they remove from the false ones. Nothing about the pass or its
# labels changes.
#
# A curved candidate is kept whole (as_event's "curve": its reference look
# and epoch, frequency, drift, acceleration, and each look's measured
# values), but the checks themselves are written for a straight track and
# read one frequency and one drift. Check by check: 1 (data sanity) has no
# stamps for a pass candidate and rests on the looks being complete (marked
# "stamps_retained": false); 2 (OFF looks) reads the S/N measured along the
# curve and where the first hit was, each OFF look measured or marked
# unmeasurable; 3 and 8 (bands, harmonics) read the frequency only; 5 (the
# Earth's drift) only reports; 4, 7 and 9 (zero drift, look-alikes,
# crowding) and 6 (recurrence, which carries the signal by its drift) read
# the reference drift, so a curved candidate's verdict could depend on which
# look is the reference. With "store", each pass candidate is also checked
# with each of its member looks as the reference (by_reference), and the
# tables say how often the verdict changes. Check 6 extrapolates in a
# straight line: a curved signal's recurrence in the cadence's other looks
# can be missed by it (a 10^-3 Hz/s^2 track is 700 Hz off the line 20
# minutes on), which leaves more of the pass's candidates unexplained, not
# fewer; those looks are the ones the pass already measured along the curve.
VET_CUTS = (10, 30)
RANK = ("unexplained, strong", "unexplained, weak", "likely interference", "interference")


def rank(verdict):
    v = str(verdict)
    return next((i for i, r in enumerate(RANK) if v.startswith(r)), len(RANK))


def as_event(looks, e, ref=None):
    """A second-pass candidate in onoff.judge's form, for vetting.vet.

    The reference (the frequency and drift the checks read) is its strongest
    member hit, or the member in look `ref`. Each ON look is found (a member
    hit) or measured on the curve; each OFF look's S/N along the curve and
    where the first hit was, with off_evidence from those values
    (onoff.OFF_MAX), and "measured": false where neither could be measured.
    "curve" keeps the candidate whole: the reference look, its start (MJD),
    the frequency there (MHz, the hit's start), the drift (Hz/s, mid-look),
    the acceleration (Hz/s^2), and each look's measured values. No stamps
    are cut ("stamps_retained": false): check 1 then rests on the looks
    being complete."""
    mem = e["members"]
    if ref is None:
        top_pos, top_i = max(mem.items(), key=lambda m: looks[m[0]].hits[m[1]]["snr"])
    else:
        top_pos, top_i = ref, mem[ref]
    h = looks[top_pos].hits[top_i]
    matches = [None] * len(looks)
    for p, i in mem.items():
        matches[p] = i
    offs = {o[0]: o for o in e.get("offs", [])}
    per, values = [], []
    for lk in looks:
        entry = {"position": lk.position, "on": lk.on}
        if lk.position in mem:
            hh = lk.hits[mem[lk.position]]
            entry.update(found=True, snr=hh["snr"], drift_hz_s=hh["drift_hz_s"])
            values.append({"position": lk.position, "kind": "hit", "frequency_mhz": hh["frequency_mhz"],
                           "drift_hz_s": hh["drift_hz_s"], "snr": hh["snr"]})
        elif lk.on:
            tr = e.get("track")
            entry.update(found=False, track_snr=None if tr is None else round(tr[3], 2))
            values.append({"position": lk.position, "kind": "track",
                           "channel": None if tr is None else tr[1], "drift_hz_s": None if tr is None else tr[2],
                           "snr": None if tr is None else round(tr[3], 2)})
        else:
            o = offs.get(lk.position, (lk.position, None, None))
            known = [x for x in o[1:3] if x is not None]
            entry.update(found=False, track_snr=o[1], track_snr_fixed=o[2], measured=bool(known),
                         off_evidence=bool(known) and max(known) >= onoff.OFF_MAX)
            values.append({"position": lk.position, "kind": "off", "snr_on_curve": o[1], "snr_at_start": o[2],
                           "measured": bool(known)})
        per.append(entry)
    off_max = max((x for o in offs.values() for x in o[1:3] if x is not None), default=None)
    curve = {"ref_position": top_pos, "ref_epoch_mjd": looks[top_pos].tstart, "frequency_mhz": h["frequency_mhz"],
             "drift_hz_s": h["drift_hz_s"], "accel_hz_s2": e["a"], "looks": values}
    return {"frequency_mhz": h["frequency_mhz"], "drift_hz_s": h["drift_hz_s"], "snr": h["snr"],
            "seed_position": top_pos, "matches": matches, "looks": per, "off_snr_max": off_max,
            "label": "candidate", "stamps": None, "stamps_retained": False, "a": e["a"], "curve": curve,
            "members": dict(mem)}


def _vetters(ctx):
    """The three ways (see above). ctx: db, session, target, occupancy, the
    session's hits. Each takes (event, looks, ons): ons the file positions
    taken as ON."""
    target, occ = ctx["target"], ctx["occupancy"]

    def uniform(event, looks, ons):
        hits = [h for lk in looks for h in lk.hits if not h.get("shadow")]
        return vetting.vet(event, looks, target, (), hits)

    def measured(event, looks, ons):
        hits = [h for lk in looks for h in lk.hits if not h.get("shadow")]
        return vetting.vet(event, looks, target, (), hits, occupancy=occ)

    def full(event, looks, ons):
        return check.vet_from_store(ctx["db"], event, looks, ctx["session"], target, own=(),
                                    on_positions=tuple(ons), hits=ctx["hits"])
    return {"uniform": uniform, "measured": measured, "store": full}


def _context(db, session):
    return {"db": db, "session": session, "target": check.target_of(db, session),
            "occupancy": occupancy.load(db, session), "hits": check.session_hits(db, session)}


def _by_reference(ev, looks, ons, fn):
    """A pass candidate checked with each member look as the reference:
    {position: verdict}."""
    return {str(p): fn(as_event(looks, {"members": ev["members"], "offs": ev.get("_offs", []),
                                        "track": ev.get("_track"), "a": ev["a"]}, ref=p), looks, ons)["verdict"]
            for p in sorted(ev["members"])}


def _candidates(looks, events, order):
    """Every candidate of production and of the pass at each a_max, once
    each: [(kept form, event in judge's form, configs that keep it, by)]."""
    out = []
    for e in events:
        if e["label"] == "candidate":
            out.append((matched._our_kept(looks, [e], order)[0], e, list(CONFIGS), "production"))
    by_sig = {}
    for a in A_MAX:
        for pe in second_pass(looks, events, a):
            if pe["label"] != "candidate":
                continue
            sig = frozenset(pe["members"].items())
            if sig not in by_sig:
                by_sig[sig] = [pe, []]
            by_sig[sig][1].append(key(a))
    for pe, cfgs in by_sig.values():
        ev = as_event(looks, pe)
        ev["_offs"], ev["_track"] = pe.get("offs", []), pe.get("track")
        out.append((_kept_pass(looks, [pe], order)[0], ev, cfgs, "pass"))
    return out


def _vet_all(cands, looks, vetters, ons):
    rows = []
    for kept, ev, cfgs, by in cands:
        r = dict(kept, configs=cfgs, by=by)
        for name, fn in vetters.items():
            v = fn(ev, looks, ons)
            r[name] = {"verdict": v["verdict"], "reasons": v["reasons"]}
        if by == "pass":
            r["curve"] = ev["curve"]
            r["store"]["by_reference"] = _by_reference(ev, looks, ons, vetters["store"])
        rows.append(r)
    return rows


def _vet_block(k, slices, urls, ctx):
    cad = matched._cadence(slices, urls)
    rng = np.random.default_rng([SEED, k])
    vetters = _vetters(ctx)
    times = {}
    t = time.monotonic()
    searched = matched.our_search(cad)
    caches = [{} for _ in range(6)]
    false, plain = {}, {}
    for ons in itertools.combinations(range(6), 3):
        for cut in VET_CUTS:
            looks, events, order = matched.our_events(cad, searched, ons, cut, caches)
            if ons == TRUE:
                prod = matched._our_kept(looks, events, order)
                plain[matched.ck(cut)] = {"production": prod}
                for a in A_MAX:
                    plain[matched.ck(cut)][key(a)] = prod + _kept_pass(looks, second_pass(looks, events, a), order)
            else:
                false.setdefault(matched.ck(cut), {})[str(ons)] = _vet_all(_candidates(looks, events, order),
                                                                          looks, vetters, ons)
            for lk in looks:
                lk.flat = None
    times["false_s"] = round(time.monotonic() - t, 1)
    del searched, caches
    t = time.monotonic()
    ts = tones(cad, rng)
    cad_p = [dict(c, spectra=p) for c, p in zip(cad, plant(cad, ts))]
    searched_p = matched.our_search(cad_p)
    caches = [{} for _ in range(6)]
    rows = [{k2: tone[k2] for k2 in ("x0", "drift", "accel", "s_in", "bin")} | {"vet": {}} for tone in ts]
    for cut in VET_CUTS:
        c = matched.ck(cut)
        looks, events, order = matched.our_events(cad_p, searched_p, TRUE, cut, caches)
        cands = _candidates(looks, events, order)
        verdicts = {}
        for tone, row in zip(ts, rows):
            row["vet"][c] = {}
            for cfg in CONFIGS:
                mine = [x for x in cands if cfg in x[2]]
                st = statuses(cad, tone, [x[0] for x in mine], plain[c][cfg])
                got = [i for i, x in enumerate(cands) if cfg in x[2]
                       and _matches(cad, tone, x[0], True)[0] == _matches(cad, tone, x[0], True)[1] == len(TRUE)]
                out = {"three_looks": st["three_looks"]}
                if st["three_looks"] == "recovered":
                    for name, fn in vetters.items():
                        best = None
                        for i in got:
                            if (i, name) not in verdicts:
                                verdicts[(i, name)] = fn(cands[i][1], looks, TRUE)["verdict"]
                            v = verdicts[(i, name)]
                            if best is None or rank(v) < rank(best):
                                best = v
                        out[name] = best
                    # the recovering candidates' own: production's, the pass's, and the pass's by reference
                    out["by"] = sorted({cands[i][3] for i in got})
                    refs = []
                    for i in got:
                        if cands[i][3] == "pass":
                            if ("ref", i) not in verdicts:
                                verdicts[("ref", i)] = _by_reference(cands[i][1], looks, TRUE, vetters["store"])
                            refs.append(verdicts[("ref", i)])
                    if refs:
                        out["store_by_reference"] = refs
                row["vet"][c][cfg] = out
        for lk in looks:
            lk.flat = None
    times["planted_s"] = round(time.monotonic() - t, 1)
    return {"format": 2, "block": k, "tstarts": [x["s"]["tstart"] for x in cad], "false": false, "tones": rows,
            "times": times, "checks_version": vetting.VERSION,
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def vet_folder(target, session, name=None):
    return ROOT / (f"vet-{target}-{session}" + (f"-{name}" if name else ""))


def vet_choice(db, session, choice=None):
    """The blocks the checks run on: with `choice` (a file holding "chosen"
    {block: class} and "of" {class: count}, as data/step10/choice.json and
    matched's blocks.json do), exactly those, refused unless every block is
    one of the session's swept blocks; without it, matched.choose_blocks
    (every crowded block and 60 clean), as the first run on step 4 used."""
    if choice is None:
        return matched.choose_blocks(db, session)
    c = json.loads(Path(choice).read_text(encoding="utf-8"))
    chosen = {int(b): k for b, k in c["chosen"].items()}
    swept = {r["block_idx"]: r["hits"] for r in db.execute(
        "SELECT block_idx, hits FROM blocks WHERE session=? AND status='done'", (session,))}
    wrong = [b for b, k in chosen.items() if b not in swept
             or k != ("crowded" if swept[b] > matched.CROWDED_HITS else "clean")]
    if wrong or set(c["of"]) != {"crowded", "clean"}:
        raise yoke.Refusal("INVALID_REQUEST", f"{choice} does not fit session {session}: blocks {wrong[:5]}")
    return dict(sorted(chosen.items())), dict(c["of"])


def vet_run(target, say=print, shard=(0, 1), count=None, choice=None, name=None):
    """The checks on the candidates and planted signals of the chosen blocks.
    The store is opened read-only, and its content is compared before and
    after: the run writes only its own records, in its own folder."""
    db = store.connect_readonly()
    before = store.content(db)
    session, urls = store.cadence_files(db, target)
    chosen, _ = vet_choice(db, session, choice)
    ctx = _context(db, session)
    base = vet_folder(target, session, name)
    base.mkdir(parents=True, exist_ok=True)
    todo = [b for i, b in enumerate(chosen) if i % shard[1] == shard[0] and not (base / f"block_{b:03d}.json").exists()]
    todo = todo if count is None else todo[:count]
    say(f"{target} {session}: {len(todo)} blocks of this share to run", flush=True)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])

    def fetch(b):
        return seti.read_looks(urls, *block_list[b])

    with ThreadPoolExecutor(max_workers=1) as ahead:
        coming = ahead.submit(fetch, todo[0]) if todo else None
        for i, b in enumerate(todo):
            slices = coming.result()
            coming = ahead.submit(fetch, todo[i + 1]) if i + 1 < len(todo) else None
            started = time.monotonic()
            rec = _vet_block(b, slices, urls, ctx)
            rec["class"] = chosen[b]
            rec["times"]["block_s"] = round(time.monotonic() - started, 1)
            del slices
            (base / f"block_{b:03d}.json").write_text(json.dumps(rec), encoding="utf-8")
            f10 = [r for rows in rec["false"]["10"].values() for r in rows]
            say(f"  block {b}: wrong-choice candidates at cut 10 production "
                f"{sum(r['by'] == 'production' for r in f10)}, pass {sum(r['by'] == 'pass' for r in f10)} "
                f"(pass unexplained, full checks: {sum(r['by'] == 'pass' and rank(r['store']['verdict']) < 2 for r in f10)})"
                f"; {rec['times']['block_s']} s", flush=True)
    after = store.content(db)
    db.close()
    if after != before:
        raise yoke.Refusal("INVALID_REQUEST", "the store changed during the checks run: "
                           + ", ".join(k for k in after if after[k] != before.get(k)))
    say("the store's content is as it was before the run", flush=True)


def vet_tables(target, say=print, choice=None, name=None):
    db = store.connect_readonly()
    session, _ = store.cadence_files(db, target)
    chosen, of = vet_choice(db, session, choice)
    db.close()
    recs = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(vet_folder(target, session, name).glob("block_*.json"))]
    recs = [r for r in recs if r.get("format") == 2]
    extra = sorted({r["block"] for r in recs} - set(chosen))
    if extra:
        raise yoke.Refusal("INVALID_REQUEST", f"blocks {extra[:5]} are not in the choice")
    for r in recs:
        r["class"] = chosen[r["block"]]
    missing = sorted(set(chosen) - {r["block"] for r in recs})
    weights = {k: v / sum(of.values()) for k, v in of.items()}
    hours = {k: round(sum(r["times"].get(k, 0) for r in recs) / 3600, 2) for k in ("false_s", "planted_s", "block_s")}
    out = {"blocks": len(recs), "missing_blocks": missing, "complete": not missing, "hours": hours,
           "choice": str(choice) if choice else "matched.choose_blocks", "of": of, "weights": weights}
    # how often a pass candidate's full-checks verdict depends on the reference look
    refs = [x["store"]["by_reference"] for r in recs for c in r["false"].values() for rows in c.values()
            for x in rows if x["by"] == "pass"]
    refs += [v for r in recs for t in r["tones"] for c in t["vet"].values() for x in c.values()
             for v in x.get("store_by_reference", [])]
    out["reference_sensitivity"] = {"pass_candidates_checked": len(refs), "verdict_class_differs": sum(
        len({rank(v) < 2 for v in d.values()}) > 1 for d in refs)}
    for c in map(matched.ck, VET_CUTS):
        for way in ("uniform", "measured", "store"):
            # wrong choices: distinct signals a block (by shared member hits) kept, and left unexplained
            f = {}
            for cfg in CONFIGS:
                kept = unexpl = 0
                for r in recs:
                    rows = [x for rows in r["false"][c].values() for x in rows if cfg in x["configs"]]
                    kept += len(matched.shared_hits({"_": rows}))
                    unexpl += len(matched.shared_hits({"_": [x for x in rows if rank(x[way]["verdict"]) < 2]}))
                f[cfg] = {"distinct_kept": kept, "distinct_unexplained": unexpl, "per_block_unexplained":
                          round(unexpl / len(recs), 4) if recs else None}
                if choice and recs:
                    # weighted by each class's share of the session's blocks, as the frozen rates are
                    def count(r, cfg=cfg, test=None):
                        rows = [x for rows in r["false"][c].values() for x in rows if cfg in x["configs"]
                                and (test is None or test(x))]
                        return len(matched.shared_hits({"_": rows}))
                    rng = np.random.default_rng(1)
                    f[cfg]["weighted_kept"] = matched_tables._rate(recs, count, weights, rng)
                    f[cfg]["weighted_unexplained"] = matched_tables._rate(
                        recs, lambda r, cfg=cfg: count(r, cfg, lambda x: rank(x[way]["verdict"]) < 2), weights, rng)
            # planted: of those recovered by three looks, left unexplained by the checks
            p = {}
            for cfg in CONFIGS:
                rows = []
                for acc in ACCELS:
                    for s_in in STRENGTHS:
                        cell = [t["vet"][c][cfg] for r in recs for t in r["tones"]
                                if abs(abs(t["accel"]) - acc) < 1e-12 and t["s_in"] == s_in]
                        rec_ = [x for x in cell if x["three_looks"] == "recovered"]
                        u = sum(rank(x[way]) < 2 for x in rec_)
                        rows.append({"accel": acc, "s_in": s_in, "planted": len(cell), "recovered": len(rec_),
                                     "unexplained": u, "interval": measure.wilson(u, len(rec_)) if rec_ else None,
                                     "false_association": sum(x["three_looks"] == "false association" for x in cell)})
                p[cfg] = rows
            out[f"cut_{c}_{way}"] = {"false": f, "planted": p}
    yoke.write(yoke.DATA / "measurements" / ("curved-pass-vetting.json" if not (choice or name) else
                                             f"curved-pass-vetting-{target}-{session}-{name or 'choice'}.json"),
               {"target": target, "session": session, **out, "kind": "measured", "experimental": True}, stamp=True)
    say(f"{len(recs)} blocks of {len(chosen)} (missing {missing}); hours {hours}; reference sensitivity "
        f"{out['reference_sensitivity']}")
    for c in map(matched.ck, VET_CUTS):
        for way in ("uniform", "measured", "store"):
            x = out[f"cut_{c}_{way}"]
            say("")
            say(f"cut {c}, checks {way}: wrong-choice distinct kept / unexplained, and planted recovered / unexplained")
            for cfg in CONFIGS:
                pr = x["planted"][cfg]
                say(f"  {cfg:>14}: false {x['false'][cfg]['distinct_kept']} / {x['false'][cfg]['distinct_unexplained']}"
                    f"   planted {sum(r['recovered'] for r in pr)} / {sum(r['unexplained'] for r in pr)}")
    return out


# --- turboSETI on the same curved signals, by the same three-look standard -----------

# The first comparison (curved.py turboseti, 40 signals an acceleration in
# the saved cadences) counted this search's signal kept when any event
# holding its hits was a candidate, and turboSETI's when it had an event and
# a hit in each ON look: not one standard. Here turboSETI runs on step 4's
# 121 blocks with the plantings of `run` (seed 61, the same signals), its hit
# search and event stage as step 4 runs them (tools/turbo_curves.py, the true
# choice, unplanted and planted), and is scored as step 4 scores it, against
# the curved track: an event whose every listed ON row lies on the signal's
# track and its own hit tables holding a hit on the track in each of the
# three ON looks (step 4's three looks for turboSETI). Its frequency is
# taken half a spectrum into the look, as step 4 does. This search's side is
# the three-look status already recorded (status_v2). An event the unplanted
# block already had is a false association, as for this search.
TURBO_CUTS = (10, 30)


def _turbo_expected(cad, t, j):
    fe, de, tol = expected(cad, t, j)
    return fe + de * cad[j]["s"]["tsamp"] / 2 / 1e6, de, tol


def _turbo_status(cad, t, planted, plain, cut):
    """turboSETI's three looks for one signal at one cut."""
    def on_track(j, f, d):
        fe, de, tol = _turbo_expected(cad, t, j)
        return abs((f - fe) * 1e6) <= tol and abs(d - de) <= matched.TOL_DRIFT

    def got(rec):
        rows = next(e["rows"] for e in rec["events"] if tuple(e["as_on"]) == TRUE and float(e["cut"]) == float(cut))
        events = matched._turbo_kept(rows)
        return any(len(ev["members"]) >= 1 and all(on_track(m[0], m[2], m[3]) for m in ev["members"]) for ev in events)
    hits = sum(any(on_track(j, h["freq_mhz"], h["drift_hz_s"]) for h in planted["look_hits"][j] if h["snr"] > cut)
               for j in TRUE)
    if not got(planted):
        return {"three_looks": "missed", "on_hits": hits}
    if got(plain):
        return {"three_looks": "false association", "on_hits": hits}
    return {"three_looks": "recovered" if hits == len(TRUE) else "missed", "on_hits": hits, "event": True}


def _turbo_block(k, rec, slices, urls, work):
    cad = matched._cadence(slices, urls)
    assert [c["s"]["tstart"] for c in cad] == rec["tstarts"], "not the recorded block"
    rng = np.random.default_rng([SEED, k])
    ts = tones(cad, rng)
    assert len(ts) == len(rec["tones"]) and all(abs(t["x0"] - r["x0"]) < 1e-9 and t["accel"] == r["accel"]
                                                for t, r in zip(ts, rec["tones"])), "not the recorded signals"
    started = time.monotonic()
    cuts = ",".join(str(c) for c in TURBO_CUTS)
    plain_paths = [seti.save(c["s"], work / "plain" / f"{j}.h5") for j, c in enumerate(cad)]
    pipelines._tool("turbo_curves.py", work / "turbo_plain.json", cuts, "true", *plain_paths)
    planted_raw = plant(cad, ts)
    planted_paths = [seti.save(dict(c["s"], spectra=p), work / "planted" / f"{j}.h5")
                     for j, (c, p) in enumerate(zip(cad, planted_raw))]
    pipelines._tool("turbo_curves.py", work / "turbo_planted.json", cuts, "true", *planted_paths)
    plain = json.loads((work / "turbo_plain.json").read_text(encoding="utf-8"))
    planted = json.loads((work / "turbo_planted.json").read_text(encoding="utf-8"))
    rows = []
    for t, r in zip(ts, rec["tones"]):
        row = {k2: r[k2] for k2 in ("x0", "drift", "accel", "s_in", "bin")}
        row["turboseti"] = {matched.ck(c): _turbo_status(cad, t, planted, plain, c) for c in TURBO_CUTS}
        row["ours"] = {matched.ck(c): {cfg: r["status_v2"][matched.ck(c)][cfg]["three_looks"] for cfg in CONFIGS}
                       for c in TURBO_CUTS}
        rows.append(row)
    return {"format": 1, "block": k, "tstarts": rec["tstarts"], "tones": rows,
            "times": {"turbo_s": round(time.monotonic() - started, 1), "turbo_search_s": planted.get("search_s")},
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def turbo_folder(target, session):
    return ROOT / f"turbo-{target}-{session}"


def turbo_run(target, say=print, shard=(0, 1), count=None):
    db = store.connect()
    session, urls = store.cadence_files(db, target)
    db.close()
    src = folder(target, session)
    base = turbo_folder(target, session)
    base.mkdir(parents=True, exist_ok=True)
    paths = sorted(src.glob("block_*.json"))
    todo = [p for i, p in enumerate(paths) if i % shard[1] == shard[0] and not (base / p.name).exists()]
    todo = todo if count is None else todo[:count]
    say(f"{target} {session}: {len(todo)} blocks of this share to run", flush=True)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    work = ROOT / f"work_turbo_{shard[0]}"

    def fetch(p):
        rec = json.loads(p.read_text(encoding="utf-8"))
        return rec, seti.read_looks(urls, *block_list[rec["block"]])

    with ThreadPoolExecutor(max_workers=1) as ahead:
        coming = ahead.submit(fetch, todo[0]) if todo else None
        for i, p in enumerate(todo):
            rec, slices = coming.result()
            coming = ahead.submit(fetch, todo[i + 1]) if i + 1 < len(todo) else None
            out = _turbo_block(rec["block"], rec, slices, urls, work)
            del slices
            (base / p.name).write_text(json.dumps(out), encoding="utf-8")
            t30 = out["tones"]
            say(f"  block {out['block']}: three looks at cut 30, turboSETI "
                f"{sum(t['turboseti']['30']['three_looks'] == 'recovered' for t in t30)}, production "
                f"{sum(t['ours']['30']['production'] == 'recovered' for t in t30)}, pass 1e-3 "
                f"{sum(t['ours']['30']['pass_0.001'] == 'recovered' for t in t30)} of {len(t30)}; "
                f"{out['times']['turbo_s']} s", flush=True)
    shutil.rmtree(work, ignore_errors=True)


def turbo_tables(target, say=print):
    db = store.connect()
    session, _ = store.cadence_files(db, target)
    db.close()
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(turbo_folder(target, session).glob("block_*.json"))]
    tones_all = [t for r in recs for t in r["tones"]]
    out = {}
    for c in map(matched.ck, TURBO_CUTS):
        rows = []
        for acc in ACCELS:
            for s_in in STRENGTHS:
                cell = [t for t in tones_all if abs(abs(t["accel"]) - acc) < 1e-12 and t["s_in"] == s_in]
                row = {"accel": acc, "s_in": s_in, "planted": len(cell)}
                for name, get in [("turboseti", lambda t: t["turboseti"][c]["three_looks"])] + [
                        (cfg, lambda t, cfg=cfg: t["ours"][c][cfg]) for cfg in CONFIGS]:
                    st = [get(t) for t in cell]
                    n = sum(x != "false association" for x in st)
                    k = sum(x == "recovered" for x in st)
                    row[name] = {"recovered": k, "counted": n, "share": round(k / n, 3) if n else None,
                                 "interval": measure.wilson(k, n) if n else None}
                row["turboseti_event_any"] = sum(bool(t["turboseti"][c].get("event")) for t in cell)
                rows.append(row)
        out[f"cut_{c}"] = rows
    hours = round(sum(r["times"]["turbo_s"] for r in recs) / 3600, 2)
    yoke.write(yoke.DATA / "measurements" / "curved-turboseti-blocks.json",
               {"target": target, "session": session, "blocks": len(recs), "hours": hours, "recovery": out,
                "kind": "measured", "experimental": True}, stamp=True)
    say(f"{len(recs)} blocks, {len(tones_all)} signals, {hours} h of turboSETI")
    for c in map(matched.ck, TURBO_CUTS):
        say("")
        say(f"cut {c}, three looks: |a|, S_in: turboSETI / production / pass 1e-3 (of counted)")
        for row in out[f"cut_{c}"]:
            say(f"  {row['accel']:<7g} {row['s_in']:>4}  {row['turboseti']['recovered']:>4} / "
                f"{row['production']['recovered']:>4} / {row['pass_0.001']['recovered']:>4}  of {row['production']['counted']}")
    return out


# --- self-checks ---------------------------------------------------------------------

def selftest(say=print):
    """Independent checks of the orbital paths, the planting and the
    candidate adapter (no archive reads; seconds). Raises on a failure."""
    import types
    # 1. The path against a separate calculation: the acceleration (the
    #    orbit's a_pk cos(w t - phase) plus the Earth's, from expected_drift
    #    differenced on its own 0.5 s grid) integrated twice from the planted
    #    drift with the trapezoid rule, not orbit_offset's closed form.
    ra, dec, mjd0 = 20.104288, 44.456838, 57898.26
    cad = [{"s": {"tstart": mjd0 + j * 330 / 86400, "tsamp": 1.073741824}, "raw": np.zeros((279, 1))}
           for j in range(6)]
    earth = _earth(cad, ra, dec)
    g = np.arange(0.0, 1950.0, 0.5)                 # within the cadence (the Earth path ends there)
    d_earth = np.array([vetting.expected_drift(1.0, mjd0 + x / 86400, ra, dec)[0] for x in g])
    worst = 0.0
    for a_pk, period, phase, drift, f_mhz in ((1e-3, 10.0, 0.4, 0.3, 2100.0), (3e-4, 24.0, 2.9, -1.7, 1850.0),
                                             (1e-4, 240.0, 5.1, 0.0, 2400.0), (0.0, None, 0.0, 0.05, 2000.0)):
        t = {"a_pk": a_pk, "period_h": period, "phase": phase, "drift": drift, "f_mhz": f_mhz}
        acc = f_mhz * np.gradient(d_earth, g)
        if a_pk:
            acc = acc + a_pk * np.cos(2 * math.pi / (period * 3600) * g - phase)
        v = drift + np.concatenate([[0.0], np.cumsum((acc[1:] + acc[:-1]) / 2 * 0.5)])
        f = np.concatenate([[0.0], np.cumsum((v[1:] + v[:-1]) / 2 * 0.5)])
        err = float(np.max(np.abs(f - orbit_offset(t, g, earth))))
        worst = max(worst, err)
        assert err < 0.05, f"path off by {err:.3f} Hz (a_pk {a_pk}, period {period})"
    say(f"1. orbital paths against a separate double integration: worst {worst:.4f} Hz over 1950 s")

    # 2. The planting: one strong orbital signal in an empty look; the power's
    #    centre in each spectrum against the path at mid-spectrum.
    n_t, n_f, tsamp, foff = 279, 4000, 1.073741824, 2.7939677238464355e-06
    t = {"a_pk": 1e-3, "period_h": 10.0, "phase": 1.0, "drift": 1.3, "f_mhz": 2000.0}

    def path(tau):
        return orbit_offset(t, tau, lambda x: 0.0 * np.asarray(x))
    out = measure.plant(np.zeros((n_t, n_f)), [(1000.3, 0.0, 1.0, path)], tsamp, foff)
    ch = np.arange(n_f)
    centre = (out * ch).sum(axis=1) / out.sum(axis=1)
    want = 1000.3 + path((np.arange(n_t) + 0.5) * tsamp) / (foff * 1e6)
    err = float(np.max(np.abs(centre - want)))
    assert err < 0.25, f"planted track off by {err:.3f} channels"
    say(f"2. a planted orbital track against its path: worst {err:.3f} channels over {n_t} spectra")

    # 3. The adapter: OFF looks measured below the threshold, unmeasurable, and
    #    at it; the third ON look a measured track; the curve kept whole.
    def look(pos, hits):
        return types.SimpleNamespace(position=pos, on=pos % 2 == 0, hits=hits, tstart=mjd0 + pos * 330 / 86400)
    hit = {"frequency_mhz": 2000.0, "drift_hz_s": 0.5, "snr": 40.0}
    looks = [look(0, [hit]), look(1, []), look(2, [dict(hit, snr=60.0, drift_hz_s=0.6)]), look(3, []), look(4, []),
             look(5, [])]
    e = {"members": {0: 0, 2: 0}, "track": (4, 1234, 0.7, 6.5), "offs": [(1, 3.1, 2.0), (3, None, None), (5, 4.0, 7.2)],
         "a": 3e-4}
    ev = as_event(looks, e)
    per = {x["position"]: x for x in ev["looks"]}
    assert ev["seed_position"] == 2 and ev["drift_hz_s"] == 0.6, "reference is the strongest member hit"
    assert per[1]["measured"] and not per[1]["off_evidence"], "OFF measured under the threshold"
    assert not per[3]["measured"] and not per[3]["off_evidence"] and per[3]["track_snr"] is None, "OFF unmeasurable"
    assert per[5]["off_evidence"], "OFF at the threshold is evidence"
    assert per[4]["found"] is False and per[4]["track_snr"] == 6.5, "third ON look a measured track"
    assert ev["off_snr_max"] == 7.2 and ev["stamps_retained"] is False
    assert ev["curve"]["accel_hz_s2"] == 3e-4 and len(ev["curve"]["looks"]) == 6
    ev0 = as_event(looks, e, ref=0)
    assert ev0["seed_position"] == 0 and ev0["drift_hz_s"] == 0.5, "a chosen reference look"
    say("3. the adapter: OFF looks measured, unmeasurable and at the threshold told apart; "
        "the track, the reference and the curve kept")

    # 4. The matching tolerance: straight (no orbit, no Earth) gives 6 Hz and
    #    the planted drift; widened only by the path's departure from a line.
    cad1 = [{"s": {"tstart": mjd0, "tsamp": tsamp, "fch1": 2000.0, "foff": foff}, "raw": np.zeros((279, 1))}]
    zero = (lambda x: 0.0 * np.asarray(x))
    straight = {"a_pk": 0.0, "period_h": None, "phase": 0.0, "drift": 0.8, "f_mhz": 2000.0, "x0": 10.0}
    _, slope, tol = orbit_expected(zero)(cad1, straight, 0)
    assert abs(slope - 0.8) < 1e-9 and abs(tol - matched.TOL_HZ) < 1e-9, "straight: 6 Hz, its own drift"
    curved_t = dict(straight, a_pk=1e-3, period_h=24.0, phase=0.0)
    _, _, tol_w = orbit_expected(zero)(cad1, curved_t, 0)
    _, _, tol_t = orbit_expected(zero, widen=False)(cad1, curved_t, 0)
    T = 279 * tsamp
    # the orbit's acceleration changes a little over the look, so near, not equal, to a T^2/12
    assert abs(tol_w - matched.TOL_HZ - 1e-3 * T * T / 12) < 0.2 and tol_t == matched.TOL_HZ
    say(f"4. the tolerance: 6 Hz straight; at 1e-3 Hz/s^2 {tol_w:.2f} Hz (6 + a T^2/12), 6 Hz tight")
    say("selftest passed")


# --- tables -----------------------------------------------------------------------

def tables(target, say=print, name="curved-pass.json"):
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
    yoke.write(yoke.DATA / "measurements" / name, record, stamp=True)
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
    o = sub.add_parser("orbits", help="orbital (sinusoidal) signals with the Earth's motion, in step 4's blocks")
    o.add_argument("target")
    o.add_argument("--shard", default="0/1")
    o.add_argument("--blocks", type=int)
    v = sub.add_parser("vet", help="the checks on production's and the pass's candidates, wrong choices and planted")
    v.add_argument("target")
    v.add_argument("--shard", default="0/1")
    v.add_argument("--blocks", type=int)
    v.add_argument("--choice", help="a file of fixed blocks (data/step10/choice.json, matched's blocks.json)")
    v.add_argument("--name", help="the records' folder: vet-TARGET-SESSION-NAME (default: no suffix)")
    vt = sub.add_parser("vet-tables")
    vt.add_argument("target")
    vt.add_argument("--choice")
    vt.add_argument("--name")
    tb = sub.add_parser("turboseti", help="turboSETI on the same blocks and signals, by three looks")
    tb.add_argument("target")
    tb.add_argument("--shard", default="0/1")
    tb.add_argument("--blocks", type=int)
    tt = sub.add_parser("turboseti-tables")
    tt.add_argument("target")
    sub.add_parser("selftest", help="the orbital paths, the planting and the candidate adapter checked")
    ot = sub.add_parser("orbit-tables")
    ot.add_argument("target")
    t = sub.add_parser("tables")
    t.add_argument("target")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run(a.target, a.blocks, shard=tuple(int(x) for x in a.shard.split("/")))
    elif a.cmd == "orbits":
        orbits(a.target, shard=tuple(int(x) for x in a.shard.split("/")), count=a.blocks)
    elif a.cmd == "vet":
        vet_run(a.target, shard=tuple(int(x) for x in a.shard.split("/")), count=a.blocks,
                choice=a.choice, name=a.name)
    elif a.cmd == "vet-tables":
        vet_tables(a.target, choice=a.choice, name=a.name)
    elif a.cmd == "turboseti":
        turbo_run(a.target, shard=tuple(int(x) for x in a.shard.split("/")), count=a.blocks)
    elif a.cmd == "turboseti-tables":
        turbo_tables(a.target)
    elif a.cmd == "selftest":
        selftest()
    elif a.cmd == "orbit-tables":
        orbit_tables(a.target)
    elif a.cmd == "recheck":
        recheck(a.target, shard=tuple(int(x) for x in a.shard.split("/")))
    else:
        tables(a.target)


if __name__ == "__main__":
    main()
