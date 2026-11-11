#!/usr/bin/env python3
"""EXPERIMENTAL, not part of the search: a cadence test for curved tracks
(comparable.md step 9), to see whether one would recover what the cadence
test loses, and at what cost in false candidates.

    python curved.py study [--runs N]          the curved test against the straight one, with false candidates
    python curved.py turboseti [--runs N]      curved tracks through this search and turboSETI

The production cadence test (onoff.py) joins a signal's hits across the
looks along a straight line: each look's hit must lie where the first one's
drift carries it, with nearly the same drift (2 drift steps and 5%). A
signal whose drift changes (a frequency acceleration, Hz/s^2) drifts out of
that between the ON looks 11 minutes apart.

Here a track is f(t) = f0 + d0 t + a t^2 / 2 over the whole cadence, a held
constant. For every hit at the cut in the first ON look and every one in the
last that a track with |a| <= a_max could join, a is taken from their drifts
(each hit's drift is its track's slope at mid-look), the last hit's
frequency must agree with the track, and the middle ON look must have a hit
on it or the track at S/N 5 there (onoff.ON_MIN). The OFF looks are then
measured along the track (S/N 6 there, or any hit near it, of any strength,
is interference), as onoff.judge measures them, and also where the first hit
started (a transmitter fixed in frequency).

It is run with a_max = 0 as well: the same code as a straight-line test, so
that what a_max > 0 adds (recovery and false candidates) is against the same
code, not against onoff.py's different rules (onoff.py also seeds from every
ON look and accepts a track in the first or last ON look; this needs a hit in
both). False candidates: each saved cadence judged with the 19 wrong choices
of three ON looks, as step 7, counted as distinct frequencies, on ten blocks of the
KIC 8462852 sweep read again (FALSE_BLOCKS: the saved cadences hold too
few hits to cost anything).

Nothing here changes the search, the cadence test, the store or any record
other than data/measurements/curved.json.
"""
import argparse
import itertools
from pathlib import Path

import numpy as np

import injection
import measure
import onoff
import yoke

A_MAX = (0.0, 1e-4, 1e-3, 1e-2)          # Hz/s^2: the curved tests run, 0 the straight baseline
F_TOL_CHANNELS = 4.0                     # a hit is on the track within this, plus its box
D_TOL_STEPS = 2.0                        # and its drift within this, plus 5%


def _t(look, look0):
    return (look.tstart - look0.tstart) * 86400


def _track(f0_mhz, d_mid, a, look, look0):
    """The track through a hit of look0 (start frequency f0, drift d_mid at
    mid-look) with acceleration a: in `look`, the start frequency and the
    drift at mid-look of the best straight line over that look."""
    T = look0.n_t * look0.tsamp
    d0 = d_mid - a * T / 2                       # drift at look0's start
    F0 = f0_mhz * 1e6 + a * T * T / 12           # the curve's frequency at look0's start (the line starts below it)
    t = _t(look, look0)
    Tl = look.n_t * look.tsamp
    f_start = F0 + d0 * t + 0.5 * a * t * t - a * Tl * Tl / 12
    d_here = d0 + a * (t + Tl / 2)
    return f_start / 1e6, d_here


def _on_track(h, f_mhz, d, look):
    df = abs(h["frequency_mhz"] - f_mhz) * 1e6 / look.width_hz
    dd = abs(h["drift_hz_s"] - d) / look.step
    return df <= F_TOL_CHANNELS + h.get("box_channels", 1) and dd <= D_TOL_STEPS + 0.05 * abs(d) / look.step


def _hits_near(look, f_mhz, d, any_strength=False):
    out = []
    for i, h in enumerate(look.hits):
        if (any_strength or not h.get("shadow")) and _on_track(h, f_mhz, d, look):
            out.append(i)
    return out


def judge(looks, a_max):
    """Candidates and interference from curved tracks: [{f_mhz, drift, a,
    members {position: hit index}, label, off_snr_max}]."""
    on = [lk for lk in looks if lk.on]
    off = [lk for lk in looks if not lk.on]
    l0, l1, l2 = on
    span = _t(l2, l0)
    width = l0.width_hz
    first = [(i, h) for i, h in enumerate(l0.hits) if not h.get("shadow")]
    last = sorted(((h["frequency_mhz"], i, h) for i, h in enumerate(l2.hits) if not h.get("shadow")),
                  key=lambda x: x[0])
    last_f = np.array([x[0] for x in last])
    out = []
    reach_hz = 4.0 * span + 0.5 * a_max * span * span + 10 * width
    for i0, h0 in first:
        lo = np.searchsorted(last_f, h0["frequency_mhz"] - reach_hz / 1e6)
        hi = np.searchsorted(last_f, h0["frequency_mhz"] + reach_hz / 1e6, "right")
        for _, i2, h2 in last[lo:hi]:
            a = (h2["drift_hz_s"] - h0["drift_hz_s"]) / span
            a_tol = 2 * (D_TOL_STEPS * l0.step + 0.05 * abs(h0["drift_hz_s"])) / span
            if abs(a) > a_max + a_tol:
                continue
            a_use = max(-a_max, min(a_max, a))       # the model's acceleration, within its bound
            f2, d2 = _track(h0["frequency_mhz"], h0["drift_hz_s"], a_use, l2, l0)
            if not _on_track(h2, f2, d2, l2):
                continue
            f1, d1 = _track(h0["frequency_mhz"], h0["drift_hz_s"], a_use, l1, l0)
            mid = _hits_near(l1, f1, d1)
            members = {l0.position: i0, l2.position: i2}
            if mid:
                members[l1.position] = max(mid, key=lambda i: l1.hits[i]["snr"])
                ok_mid = True
            else:
                snr, _, _ = l1.best_track(l1.channel(f1), d1, F_TOL_CHANNELS, D_TOL_STEPS)
                ok_mid = snr is not None and snr >= onoff.ON_MIN
            if not ok_mid:
                continue
            off_max, off_hit = -np.inf, False
            for lk in off:
                fo, do = _track(h0["frequency_mhz"], h0["drift_hz_s"], a_use, lk, l0)
                for f_try in (fo, h0["frequency_mhz"]):          # along the track, and fixed where it began
                    snr, _, _ = lk.best_track(lk.channel(f_try), do, F_TOL_CHANNELS, D_TOL_STEPS)
                    if snr is not None:
                        off_max = max(off_max, snr)
                    off_hit = off_hit or bool(_hits_near(lk, f_try, do, any_strength=True))
            label = "interference" if (off_hit or off_max >= onoff.OFF_MAX) else "candidate"
            out.append({"f_mhz": h0["frequency_mhz"], "drift": h0["drift_hz_s"], "a": round(a, 7),
                        "members": members, "label": label,
                        "off_snr_max": None if not np.isfinite(off_max) else round(float(off_max), 2)})
    return out


def _relook(looks, ons):
    """The same six looks with `ons` as the ON looks (step 7's wrong choices)."""
    offs = [j for j in range(6) if j not in ons]
    order = [x for pair in zip(ons, offs) for x in pair]
    return [onoff.Look(looks[j].hits, looks[j].tstart, looks[j].fch1, looks[j].foff, looks[j].tsamp,
                       looks[j].flat, pos) for pos, j in enumerate(order)]


def _distinct(fs, apart_mhz=0.003):
    out = []
    for f in sorted(fs):
        if not out or f - out[-1] > apart_mhz:
            out.append(f)
    return len(out)


def _tone_hits(looks, tone, t0, per_channel):
    """The planted tone's hit index in each ON look (as injection.trial finds them)."""
    found, used = {}, [set() for _ in looks]
    a = tone.get("accel", 0.0)
    for lk in looks:
        if not lk.on:
            continue
        dt = (lk.tstart - t0) * 86400
        span_t = lk.n_t * lk.tsamp if a else 0.0
        x = tone["x0"] + (tone["drift"] * dt + 0.5 * a * dt ** 2 - a * span_t ** 2 / 12) / per_channel
        before = set(used[lk.position])
        if measure.matched(lk.hits, x, tone["drift"] + a * (dt + 0.5 * span_t), lk.step, used[lk.position]):
            found[lk.position] = (used[lk.position] - before).pop()
    return found


# Blocks of the KIC 8462852 sweep for the false candidates (the saved cadences hold 1 to 3 hits a look,
# too few to cost anything): 8 crowded ones with many wrong-choice candidates in step 4 (at the cut of
# 10, as connected groups: 158, 83, 51, 37, 35, 35, 28, 22) that search quickly, and 2 clean ones (4, 4).
FALSE_BLOCKS = (34, 45, 56, 47, 139, 98, 49, 48, 275, 39)
CUT = 10.0


def false_candidates(blocks=FALSE_BLOCKS, say=print):
    """Each block read from the archive and searched once, then judged with
    the 19 wrong choices of ON looks by this test at each a_max, hits under
    the cut of 10 as shadow hits (step 4's published cut)."""
    import matched
    import seti
    import store
    db = store.connect()
    session, urls = store.cadence_files(db, "KIC8462852")
    db.close()
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    false = []
    for k in blocks:
        cad = matched._cadence(seti.read_looks(urls, *block_list[k]), urls)
        searched = matched.our_search(cad)
        base = []
        for j in range(6):
            sj = cad[j]["s"]
            hits = [dict(h, shadow=h["snr"] < CUT) for h in searched[j][0]]
            base.append(onoff.Look(hits, sj["tstart"], sj["fch1"], sj["foff"], sj["tsamp"], searched[j][1], j))
        for ons in itertools.combinations(range(6), 3):
            if ons == (0, 2, 4):
                continue
            rel = _relook(base, ons)
            for a_max in A_MAX:
                got = [e["f_mhz"] for e in judge(rel, a_max) if e["label"] == "candidate"]
                false.append({"block": k, "as_on": list(ons), "a_max": a_max, "candidates": len(got),
                              "distinct": _distinct(got), "f_mhz": sorted(got)[:20]})
        say(f"block {k}: wrong-choice candidates (distinct) " + ", ".join(
            f"a_max {a:g}: {sum(x['distinct'] for x in false if x['block'] == k and x['a_max'] == a)}"
            for a in A_MAX), flush=True)
        del cad, searched, base
    return false


def study(runs=2, seed=41, say=print, with_false=True):
    rng = np.random.default_rng(seed)
    rows = []
    false = false_candidates(say=say) if with_false else []
    for files in measure.cadences():
        cad = injection.load(files)
        name = Path(files[0]).name
        s0 = cad[0]["s"]
        # Recovery: curved tones, the production test and each a_max.
        for r in range(runs):
            tones = injection.tones_for(cad, len(measure.ACCELS) * len(measure.DRIFT_BINS), 0, rng,
                                        strengths=(measure.CURVE_S_IN,))
            for k, t in enumerate(tones):
                t["accel"] = measure.ACCELS[k % len(measure.ACCELS)] * (1 if rng.random() < 0.5 else -1)
            out, _, looks = injection.trial(cad, tones, keep_looks=True)
            per_channel = s0["foff"] * 1e6
            judged = {a: judge(looks, a) for a in A_MAX}
            for t, o in zip(tones, out):
                hits = _tone_hits(looks, t, s0["tstart"], per_channel)
                row = {"accel": t["accel"], "drift": t["drift"], "bin": t["bin"], "found_on_looks": len(hits),
                       "production": o["label"]}
                for a, events in judged.items():
                    got = None
                    if 0 in hits and 4 in hits:
                        got = next((e["label"] for e in events
                                    if e["members"].get(0) == hits[0] and e["members"].get(4) == hits[4]), None)
                    row[f"a_max_{a:g}"] = got
                rows.append(row)
            for lk in looks:
                lk.flat = None
            say(f"{name}: run {r + 1} of {runs}: production {sum(x['production'] == 'candidate' for x in rows[-len(tones):])}"
                + "".join(f", a_max {a:g} {sum(x[f'a_max_{a:g}'] == 'candidate' for x in rows[-len(tones):])}"
                          for a in A_MAX) + f" of {len(tones)}", flush=True)
        del cad
    table = []
    for acc in measure.ACCELS:
        cell = [x for x in rows if abs(abs(x["accel"]) - acc) < 1e-12]
        n = len(cell)
        entry = {"accel_hz_s2": acc, "planted": n,
                 "production": sum(x["production"] == "candidate" for x in cell)}
        for a in A_MAX:
            entry[f"a_max_{a:g}"] = sum(x[f"a_max_{a:g}"] == "candidate" for x in cell)
        table.append(entry)
    false_tot = {f"a_max_{a:g}": {"distinct": sum(x["distinct"] for x in false if x["a_max"] == a),
                                  "judged_cadences": sum(1 for x in false if x["a_max"] == a),
                                  "by_block": {str(k): sum(x["distinct"] for x in false
                                                           if x["a_max"] == a and x["block"] == k)
                                               for k in FALSE_BLOCKS}} for a in A_MAX}
    record = {"a_max": A_MAX, "s_in": measure.CURVE_S_IN, "runs": runs, "seed": seed, "table": table,
              "false": false_tot, "false_rows": false, "rows": rows, "kind": "measured", "experimental": True}
    yoke.write(yoke.DATA / "measurements" / "curved.json", record, stamp=True)
    say("\nCandidates of those planted, by |acceleration| (production; then this test at each a_max):")
    for e in table:
        say(f"  {e['accel_hz_s2']:g}: production {e['production']}/{e['planted']}; "
            + ", ".join(f"a_max {a:g} {e[f'a_max_{a:g}']}" for a in A_MAX))
    say(f"False candidates, distinct, in {len(FALSE_BLOCKS) * 19} wrong-choice cadences of {len(FALSE_BLOCKS)} blocks: "
        + ", ".join(f"a_max {a:g}: {false_tot[f'a_max_{a:g}']['distinct']}" for a in A_MAX))
    return record


TURBO_S_IN = 400            # turboSETI keeps 80% of straight signals near zero drift only from about here (step 4)
TURBO_BINS = (0, 1)         # drifts under 0.5 Hz/s: above that it keeps almost none, curved or not (step 4)
TURBO_CUT = 10.0


def turbo_compare(runs=2, seed=51, say=print):
    """The same curved tracks through this search (production) and turboSETI
    (its hit search and event stage, as step 4 runs it, the true ON looks,
    cut 10), in the saved cadences, at S_in 400 and drifts under 0.5 Hz/s
    where turboSETI finds straight signals. turboSETI recovered: an event,
    and its own hit tables holding a hit within 6 Hz and 0.05 Hz/s of the
    track in each ON look (step 4's three-look rule, each look at its own
    drift: the track's slope at mid-look)."""
    import json
    import tempfile
    import pipelines
    import seti
    rng = np.random.default_rng(seed)
    rows = []
    for files in measure.cadences():
        cad = injection.load(files)
        name = Path(files[0]).name
        s0 = cad[0]["s"]
        per_channel = s0["foff"] * 1e6
        for r in range(runs):
            tones = injection.tones_for(cad, 2 * len(measure.ACCELS) * len(TURBO_BINS), 0, rng,
                                        strengths=(TURBO_S_IN,), which=TURBO_BINS)
            for k, t in enumerate(tones):
                t["accel"] = measure.ACCELS[k % len(measure.ACCELS)] * (1 if rng.random() < 0.5 else -1)
            out, _, looks = injection.trial(cad, tones, keep_looks=True)
            with tempfile.TemporaryDirectory() as tmp:
                paths = [seti.save(dict(c["s"], spectra=lk.planted), Path(tmp) / f"{j}.h5")
                         for j, (c, lk) in enumerate(zip(cad, looks))]
                pipelines._tool("turbo_curves.py", Path(tmp) / "turbo.json", str(TURBO_CUT), "true", *paths)
                turbo = json.loads((Path(tmp) / "turbo.json").read_text(encoding="utf-8"))
            ev_rows = next(e["rows"] for e in turbo["events"] if tuple(e["as_on"]) == (0, 2, 4))
            for t, o in zip(tones, out):
                a = t["accel"]
                got_looks, in_event = 0, False
                for j in (0, 2, 4):
                    c = cad[j]["s"]
                    dt = (c["tstart"] - s0["tstart"]) * 86400
                    T = c["spectra"].shape[0] * c["tsamp"]
                    d_mid = t["drift"] + a * (dt + T / 2)
                    # turboSETI's frequency: its first spectrum's channel, half a spectrum in, on the best line
                    f_hz = (s0["fch1"] * 1e6 + (t["x0"] * per_channel) + t["drift"] * dt + 0.5 * a * dt * dt
                            - a * T * T / 12 + d_mid * c["tsamp"] / 2)
                    ok = any(abs(h["freq_mhz"] * 1e6 - f_hz) <= 6 and abs(h["drift_hz_s"] - d_mid) <= 0.05
                             for h in turbo["look_hits"][j] if h["snr"] > TURBO_CUT)
                    got_looks += ok
                    in_event = in_event or any(row["look"] == j and abs(row["freq_mhz"] * 1e6 - f_hz) <= 6 and
                                               abs(row["drift_hz_s"] - d_mid) <= 0.05 for row in ev_rows)
                rows.append({"accel": a, "drift": t["drift"], "bin": t["bin"], "ours": o["label"],
                             "ours_found_on_looks": o["found_on_looks"], "turbo_on_looks": got_looks,
                             "turbo_event": in_event, "turbo": in_event and got_looks == 3})
            for lk in looks:
                lk.flat = lk.planted = None
            say(f"{name}: run {r + 1} of {runs}: ours {sum(x['ours'] == 'candidate' for x in rows[-len(tones):])}, "
                f"turboSETI {sum(x['turbo'] for x in rows[-len(tones):])} of {len(tones)}", flush=True)
        del cad
    table = []
    for acc in measure.ACCELS:
        cell = [x for x in rows if abs(abs(x["accel"]) - acc) < 1e-12]
        table.append({"accel_hz_s2": acc, "planted": len(cell),
                      "ours": sum(x["ours"] == "candidate" for x in cell),
                      "turboseti": sum(x["turbo"] for x in cell),
                      "turboseti_event_any": sum(x["turbo_event"] for x in cell)})
    record = {"s_in": TURBO_S_IN, "drift_bins": [measure.DRIFT_BINS[b] for b in TURBO_BINS], "runs": runs,
              "seed": seed, "table": table, "rows": rows, "kind": "measured", "experimental": True}
    yoke.write(yoke.DATA / "measurements" / "curved-turboseti.json", record, stamp=True)
    say("Kept, by |acceleration| (S_in 400, drifts under 0.5 Hz/s): this search / turboSETI (three looks) / "
        "turboSETI (any event)")
    for e in table:
        say(f"  {e['accel_hz_s2']:g}: {e['ours']} / {e['turboseti']} / {e['turboseti_event_any']} of {e['planted']}")
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("study")
    s.add_argument("--runs", type=int, default=2)
    t = sub.add_parser("turboseti")
    t.add_argument("--runs", type=int, default=2)
    a = ap.parse_args(argv)
    if a.cmd == "study":
        study(a.runs)
    else:
        turbo_compare(a.runs)


if __name__ == "__main__":
    main()
