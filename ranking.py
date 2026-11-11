#!/usr/bin/env python3
"""Candidates ranked, and how often a planted signal ranks where a person
would look at it (comparable.md step 5).

    python ranking.py offnull               the OFF looks' S/N on random tracks (the OFF term's chance)
    python ranking.py rank                  every current candidate of the store, ranked
    python ranking.py birdies [--runs N]    signals planted in the saved cadences, checked as a sweep's
                                            candidates are, scored and ranked against the real ones
    python ranking.py heldout               the 24 wrong-choice candidates step 4 left unexplained, scored
    python ranking.py tables                the tables, from what the three above kept

**The score** is the sum, over what the checks measure, of -log10 of the
chance that a signal from the sky, at a random place in this session's
band, would show it by accident; each term is capped at CAP (a chance of
1e-4: past that the check has already said what it can):

- off: the brightest OFF look's S/N along the track, against the same S/N
  on random tracks in the saved cadences' OFF looks (`offnull`);
- band: in a listed band (check 3): the listed bands' share of the band
  searched;
- zero drift: under one drift step (check 4): that range's share of the
  drifts searched (+-4 Hz/s);
- recurrence: check 6's chance of as many matches elsewhere (or, closer
  in time with the drift agreeing, of as many of those), when it found any;
- look-alikes: check 7's chance of as many in the OFF looks, when any and
  the drift is 0.1 Hz/s or more (nearer zero, interference crowds the
  drifts and the check's chance, which takes them as even, means nothing:
  the check itself calls those a possible coincidence; step 6 measures
  the drifts);
- relations: check 8's share of random frequencies with any harmonic or
  intermodulation relation, when it found one;
- crowding: the share of places in the band searched with as many hits at
  the cut within 0.5 MHz (check 9's count).

The drift against the Earth's (check 5) is not a term: a transmitter at the
target needs no particular drift, so it is no chance of anything. Data
sanity (check 1) is not a term either: it is shown beside the rank.

Nothing in the score is fitted: the terms are the checks' own chances and
shares measured on this session's hits, the cap is fixed, and no candidate,
planted or real, set any of it. Lower is more worth a look. **It is a
heuristic ranking score, not a probability:** the terms are of different
kinds (a chance of coincidence, a share of the band, a place in a random-
track distribution), and they are not independent (a crowded place also
tends to have recurrences and relations), so their sum is neither a
combined chance nor a likelihood ratio, and says nothing of how likely a
candidate is to be a signal. `tables` measures how much the ranking leans
on each term by taking it out.

**A score belongs to its calibration:** the session whose hits gave the
band and crowding shares, the OFF null's file and the cadences it came
from, the cap, the look-alike line and the ranking version. They are kept
with every ranked list (`calibration`); scores made with different
calibrations (another session, receiver or telescope) are not compared. A candidate
whose checks *show* interference (check 2 or 6) ranks after every other;
ties go to the higher SNR.

**Birdies** (SETI@home's term): signals planted in the ON looks of the five
saved cadences of this session, as Phase 6 planted them, searched and
judged, and every candidate they make put through the checks with the
store's evidence as a sweep candidate is (check.vet_from_store), scored,
and ranked against the store's real candidates. Uncovered at N: ranked
within the first N of the real candidates and itself (N = 10 for one
cadence, as the plan sets; N = 1, ahead of every real candidate, is the
bar for a survey of many cadences).

**Held out:** the 24 candidates that step 4's wrong choices of ON looks
made and its checks left unexplained are not used for anything above:
`heldout` reads their blocks again, judges the same choices, checks them
with the store's evidence (recurrence in the choice's own OFF looks) and
scores them, to see where interference the checks cannot explain ranks.
"""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

import check
import injection
import measure
import onoff
import store
import vetting
import yoke

VERSION = ("2 (11 Nov 2026: crowding and look-alikes from the checks' measured chances (checks version 4); "
           "version 1: crowding as the share of places, look-alikes from 0.1 Hz/s)")
CAP = 4.0                               # a term's most: -log10 of a chance of 1e-4
TERMS = ("off", "band", "zero_drift", "recurrence", "lookalikes", "relations", "crowding")
LOOKALIKE_MIN_DRIFT = 0.1               # Hz/s: check 7's chance is used from here (vetting.py's own line)
CROWD_MHZ = 0.5                         # check 9's window, each side
GRID_MHZ = 0.01                         # the places crowding's share is taken over
OFF_NULL_TRACKS = 2000                  # random tracks a saved cadence, for the OFF term
BIRDIE_STRENGTHS = (15, 20, 30, 45, 60, 90, 120)
N_LOOK = (10, 1)                        # uncovered within the first N
SHARE = 0.8
MEAS = yoke.DATA / "measurements"


def _p(path):
    return MEAS / path


def _log(p):
    return min(CAP, -math.log10(max(p, 1e-300)))


# --- what the terms are measured against -------------------------------------

def off_null(say=print):
    """The OFF test's S/N on random tracks, unplanted, in each saved cadence:
    OFF_NULL_TRACKS a cadence, measured as onoff.judge measures an event's."""
    values, per = [], []
    for k, files in enumerate(measure.cadences()):
        cad = injection.load(files)
        _, _, looks = injection.trial(cad, [], keep_looks=True)
        null = onoff.null_off(looks, n=OFF_NULL_TRACKS, seed=1000 + k)
        got = [x for x in null["off_snr_max"] if x is not None]
        values += got
        per.append({"cadence": Path(files[0]).name, "tracks": null["tracks"], "measured": len(got),
                    "over_off_max": null["over_off_max"], "median": float(np.median(got)) if got else None})
        say(f"{Path(files[0]).name}: {len(got)} random tracks, median OFF S/N {per[-1]['median']:.2f}, "
            f"{null['over_off_max']} over {onoff.OFF_MAX:g}", flush=True)
        for lk in looks:
            lk.flat = None
    record = {"values": sorted(values), "cadences": per, "tracks_per_cadence": OFF_NULL_TRACKS, "kind": "measured"}
    yoke.write(_p("off_null.json"), record, stamp=True)
    return record


def context(db, session):
    """The session's fixed inputs: its hits (sorted frequencies), the band
    searched, the listed bands' share of it, crowding's distribution over
    it, and the OFF null."""
    hits = check.session_hits(db, session)
    freqs = np.sort(np.array([h["frequency_mhz"] for h in hits]))
    blocks = [(min(b["f_lo_mhz"], b["f_hi_mhz"]), max(b["f_lo_mhz"], b["f_hi_mhz"])) for b in db.execute(
        "SELECT f_lo_mhz, f_hi_mhz FROM blocks WHERE session=? AND status='done'", (session,))]
    span = sum(hi - lo for lo, hi in blocks)
    in_band = sum(max(0.0, min(hi, b_hi) - max(lo, b_lo)) for lo, hi in blocks for b_lo, b_hi, _ in vetting.BANDS)
    grid = np.concatenate([np.arange(lo, hi, GRID_MHZ) for lo, hi in blocks]) if blocks else np.array([])
    counts = np.sort(np.searchsorted(freqs, grid + CROWD_MHZ, "right") - np.searchsorted(freqs, grid - CROWD_MHZ))
    null_path = _p("off_null.json")
    null_rec = json.loads(null_path.read_text(encoding="utf-8")) if null_path.exists() else None
    null = np.array(null_rec["values"]) if null_rec else None
    calibration = {
        "ranking_version": VERSION, "checks_version": vetting.VERSION, "cap": CAP,
        "lookalike_min_drift_hz_s": LOOKALIKE_MIN_DRIFT,
        "band_and_crowding": {"session": session, "hits_at_cut": len(hits), "span_mhz": round(span, 3),
                              "blocks": len(blocks), "band_share": round(in_band / span, 4) if span else None,
                              "crowding_window_mhz": CROWD_MHZ, "grid_mhz": GRID_MHZ,
                              "bands": "vetting.BANDS"},
        "off_null": None if not null_rec else {
            "file": "data/measurements/off_null.json",
            "sha256": hashlib.sha256(null_path.read_bytes()).hexdigest(),
            "tracks": len(null), "cadences": [c["cadence"] for c in null_rec.get("cadences", [])],
            "measured": null_rec.get("_stamp", {}).get("utc") if isinstance(null_rec.get("_stamp"), dict) else None}}
    return {"session": session, "hits": hits, "freqs": freqs, "span_mhz": span, "band_share": in_band / span,
            "crowd_counts": counts, "off_null": null, "target": check.target_of(db, session),
            "calibration": calibration}


def _by_n(result):
    return {c["n"]: c for c in result["checks"]}


def terms(result, ctx, f_mhz):
    """The score's terms from one candidate's checks (vetting.vet's result)."""
    c = _by_n(result)
    out = dict.fromkeys(TERMS, 0.0)
    off = c[2]["evidence"].get("off_snr_max")
    if off is not None and ctx["off_null"] is not None and len(ctx["off_null"]):
        null = ctx["off_null"]
        over = len(null) - np.searchsorted(null, off, "left")
        out["off"] = _log((over + 1) / (len(null) + 1))
    if c[3]["evidence"].get("band"):
        out["band"] = _log(ctx["band_share"])
    step = c[4]["evidence"].get("one_step_hz_s")
    if step and abs(c[4]["evidence"]["drift_hz_s"]) < step:
        out["zero_drift"] = _log(2 * step / (2 * onoff.MAX_DRIFT_NULL))
    e6 = c[6]["evidence"]
    if e6.get("matches"):
        p = e6.get("chance", 1.0)
        if e6.get("close_at_cut"):
            p = min(p, e6.get("chance_close", 1.0))
        out["recurrence"] = _log(p)
    e7 = c[7]["evidence"]
    measured7 = e7.get("method") == "measured"
    if e7.get("in_off") and (measured7 or abs(c[4]["evidence"]["drift_hz_s"]) >= LOOKALIKE_MIN_DRIFT):
        out["lookalikes"] = _log(e7.get("chance", 1.0))
    e8 = c[8]["evidence"]
    if e8.get("relations"):
        out["relations"] = _log(max(e8.get("chance", 1.0), 1 / (e8.get("trials", 200) + 1)))
    near = c[9]["evidence"].get("hits_near")
    if c[9]["evidence"].get("method") == "measured":
        out["crowding"] = _log(c[9]["evidence"]["chance"])
    elif near is not None and len(ctx["crowd_counts"]):
        counts = ctx["crowd_counts"]
        over = len(counts) - np.searchsorted(counts, near, "left")
        out["crowding"] = _log(max(over, 1) / len(counts))
    return {k: round(v, 3) for k, v in out.items()}


def scored(result, ctx, f_mhz, snr):
    t = terms(result, ctx, f_mhz)
    shown = any(ch["strength"] == "shown" for ch in result["checks"])
    sound = _by_n(result)[1]["result"] == "sound"
    return {"terms": t, "score": round(sum(t.values()), 3), "shown": shown, "sound": sound, "snr": snr}


def key(s):
    return (s["shown"], s["score"], -(s["snr"] or 0))


# --- the store's candidates ---------------------------------------------------

def real(db, session, ctx=None):
    """Every current candidate of the session, from its checks record (this
    version of the checks), scored: sorted, best first."""
    ctx = ctx or context(db, session)
    rows = db.execute("SELECT event_id, f_start_mhz, snr FROM events WHERE label='candidate' AND"
                      " superseded_run IS NULL AND session=?", (session,)).fetchall()
    out = []
    for r in rows:
        lead = check.lead_id(ctx["target"]["name"], session, r["f_start_mhz"])
        path = check.records_dir() / f"{lead}.json"
        rec = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if rec is None or rec.get("version") != vetting.VERSION or rec.get("event_id") != r["event_id"]:
            raise yoke.Refusal("NOT_CHECKED", f"Candidate {r['event_id']} has no record from this version of the "
                                              "checks: run check.py first.")
        out.append(dict(scored(rec, ctx, r["f_start_mhz"], r["snr"]), lead=lead, event_id=r["event_id"],
                        frequency_mhz=r["f_start_mhz"], drift_hz_s=rec["drift_hz_s"], verdict=rec["verdict"]))
    out.sort(key=key)
    for i, s in enumerate(out, 1):
        s["rank"] = i
    return out


def rank(say=print):
    db = store.connect()
    sessions = [r[0] for r in db.execute("SELECT DISTINCT session FROM events WHERE label='candidate' AND"
                                         " superseded_run IS NULL")]
    record = {"cap": CAP, "terms": TERMS, "version": VERSION, "checks_version": vetting.VERSION, "sessions": {}}
    for session in sessions:
        ctx = context(db, session)
        ranked = real(db, session, ctx)
        record["sessions"][session] = {"band_share": round(ctx["band_share"], 4), "span_mhz": round(ctx["span_mhz"], 3),
                                       "off_null_tracks": None if ctx["off_null"] is None else len(ctx["off_null"]),
                                       "calibration": ctx["calibration"], "ranked": ranked}
        say(f"{session}: {len(ranked)} candidates, ranked (lower score is more worth a look)")
        for s in ranked:
            say(f"  {s['rank']:>2}. {s['frequency_mhz']:.6f} MHz {s['drift_hz_s']:+.4f} Hz/s SNR {s['snr']:.1f}: "
                f"score {s['score']:.2f}{' (shown)' if s['shown'] else ''} "
                + ", ".join(f"{k} {v:g}" for k, v in s["terms"].items() if v))
    db.close()
    yoke.write(check.records_dir() / "ranking.json", record, stamp=True)
    return record


# --- birdies -----------------------------------------------------------------

def _store_hook(db, ctx):
    def hook(event, looks):
        result = check.vet_from_store(db, event, looks, ctx["session"], ctx["target"], hits=ctx["hits"])
        return dict(result, ranking=scored(result, ctx, event["frequency_mhz"], event["snr"]))
    return hook


def birdies(runs=10, seed=21, say=print, add=False):
    """Signals planted in the ON looks of each saved cadence `runs` times
    (one of each drift bin and strength in each run), through search,
    cadence test and the store's checks; each candidate scored."""
    db = store.connect()
    session = db.execute("SELECT DISTINCT session FROM events WHERE label='candidate' AND superseded_run IS NULL"
                         ).fetchone()[0]
    ctx = context(db, session)
    if ctx["off_null"] is None:
        raise yoke.Refusal("NOT_MEASURED", "No OFF null: run `ranking.py offnull` first.")
    hook = _store_hook(db, ctx)
    path = _p("birdies.json")
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"] if add and path.exists() else []
    rng = np.random.default_rng(seed + (len(rows) if add else 0))
    n_on = len(BIRDIE_STRENGTHS) * len(measure.DRIFT_BINS)
    started = time.monotonic()
    for files in measure.cadences():
        cad = injection.load(files)
        name = Path(files[0]).name
        for r in range(runs):
            tones = injection.tones_for(cad, n_on, 0, rng, strengths=BIRDIE_STRENGTHS)
            out, _ = injection.trial(cad, tones, vet=hook)
            for t in out:
                rows.append(dict(t, cadence=name, f_mhz=round(cad[0]["s"]["fch1"] + t["x0"] * cad[0]["s"]["foff"], 6)))
            yoke.write(path, {"rows": rows, "session": session, "strengths": BIRDIE_STRENGTHS, "kind": "measured",
                              "partial": True}, stamp=True)
            say(f"{name}: run {r + 1} of {runs}: {sum(t['label'] == 'candidate' for t in out)} of {len(out)} "
                f"candidates ({time.monotonic() - started:.0f} s)", flush=True)
        for lk in cad:
            lk["raw"] = None
    yoke.write(path, {"rows": rows, "session": session, "strengths": BIRDIE_STRENGTHS, "kind": "measured"},
               stamp=True)
    db.close()
    return {"birdies": len(rows)}


# --- held out ----------------------------------------------------------------

HELD_OUT = [  # step 4's wrong-choice candidates its checks left unexplained (its result page): block, ON, MHz
    (6, (0, 1, 2), 1837.510106), (6, (0, 1, 2), 1837.510134), (14, (0, 1, 2), 1861.575111),
    (14, (0, 1, 2), 1861.576612), (14, (0, 1, 4), 1861.561119), (14, (0, 1, 5), 1861.572583),
    (19, (0, 1, 2), 1875.181581), (19, (0, 1, 2), 1875.181474), (19, (0, 1, 2), 1875.181460),
    (19, (3, 4, 5), 1875.181312), (35, (0, 1, 2), 1923.256302), (36, (0, 1, 2), 1926.765285),
    (36, (0, 1, 2), 1926.773287), (36, (0, 1, 5), 1926.763584), (36, (0, 1, 5), 1926.766484),
    (36, (0, 1, 5), 1926.766581), (36, (0, 1, 5), 1926.765984), (36, (0, 1, 5), 1926.764084),
    (36, (0, 1, 5), 1926.767185), (36, (0, 1, 5), 1926.766682), (36, (3, 4, 5), 1924.282504),
    (127, (0, 2, 3), 2190.648761), (127, (1, 3, 5), 2190.649130), (275, (0, 1, 2), 2625.354957)]


def heldout(say=print):
    import matched
    import seti
    db = store.connect()
    session, urls = store.cadence_files(db, "KIC8462852")
    ctx = context(db, session)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    rows = []
    for k in sorted({b for b, _, _ in HELD_OUT}):
        started = time.monotonic()
        cad = matched._cadence(seti.read_looks(urls, *block_list[k]), urls)
        searched = matched.our_search(cad)
        caches = [{} for _ in range(6)]
        for ons in sorted({o for b, o, _ in HELD_OUT if b == k}):
            looks, events, _ = matched.our_events(cad, searched, ons, matched.PUBLISHED["ours"], caches)
            for b, o, f in HELD_OUT:
                if b != k or o != ons:
                    continue
                e = min((e for e in events if e["label"] == "candidate"),
                        key=lambda e: abs(e["frequency_mhz"] - f), default=None)
                if e is None or abs(e["frequency_mhz"] - f) > 2e-6:
                    rows.append({"block": k, "as_on": list(ons), "f_mhz": f, "found": False})
                    say(f"  block {k} {ons} {f}: not found again", flush=True)
                    continue
                result = check.vet_from_store(db, e, looks, session, ctx["target"], on_positions=set(ons),
                                              hits=ctx["hits"])
                s = scored(result, ctx, e["frequency_mhz"], e["snr"])
                rows.append(dict(s, block=k, as_on=list(ons), f_mhz=f, found=True, drift_hz_s=e["drift_hz_s"],
                                 verdict=result["verdict"]))
                say(f"  block {k} {ons} {f:.6f}: {result['verdict']}; score {s['score']:.2f}", flush=True)
            for lk in looks:
                lk.flat = None
        say(f"block {k}: {time.monotonic() - started:.0f} s", flush=True)
        del cad, searched, caches
    db.close()
    yoke.write(_p("heldout.json"), {"rows": rows, "kind": "measured"}, stamp=True)
    return {"rows": len(rows)}


# --- tables ------------------------------------------------------------------

def _in_band(f):
    return any(lo <= f <= hi for lo, hi, _ in vetting.BANDS)


def tables(say=print):
    ranked = json.loads((check.records_dir() / "ranking.json").read_text(encoding="utf-8"))
    bird = json.loads(_p("birdies.json").read_text(encoding="utf-8"))
    session = bird["session"]
    real_keys = sorted(key(s) for s in ranked["sessions"][session]["ranked"])

    def rank_of(s):
        return 1 + sum(k < key(s) for k in real_keys)

    rows = bird["rows"]
    for t in rows:
        r = t.get("ranking")
        t["kept"] = injection.kept(t)
        t["rank"] = rank_of(r) if (r and t["label"] == "candidate") else None
        t["in_band"] = _in_band(t["f_mhz"])
    cells = []
    for where, pick in (("all", lambda t: True), ("outside the listed bands", lambda t: not t["in_band"]),
                        ("inside the listed bands", lambda t: t["in_band"])):
        for b, (lo, hi) in enumerate(measure.DRIFT_BINS):
            for st in bird["strengths"]:
                cell = [t for t in rows if pick(t) and t["bin"] == b and t["s_in"] == st]
                if not cell:
                    continue
                n = len(cell)
                row = {"where": where, "drift": [lo, hi], "s_in": st, "planted": n,
                       "kept": sum(t["kept"] for t in cell)}
                for big in N_LOOK:
                    k = sum(t["rank"] is not None and t["rank"] <= big and t["kept"] for t in cell)
                    row[f"top{big}"] = k
                    row[f"top{big}_interval"] = measure.wilson(k, n)
                cells.append(row)

    def reach(where, b, field):
        line = sorted((c for c in cells if c["where"] == where and c["drift"] == list(measure.DRIFT_BINS[b])),
                      key=lambda c: c["s_in"])
        ok = [c["s_in"] for c in line if c[field] >= SHARE * c["planted"]]
        best = None
        for c in reversed(line):          # the lowest S_in from which every stronger one reaches the share
            if c[field] < SHARE * c["planted"]:
                break
            best = c["s_in"]
        return best if ok else None
    sens = [{"where": w, "drift": list(measure.DRIFT_BINS[b]),
             **{f: reach(w, b, f) for f in ("kept", *(f"top{n}" for n in N_LOOK))}}
            for w in ("all", "outside the listed bands", "inside the listed bands") for b in range(len(measure.DRIFT_BINS))]
    # Of the birdies kept, the share uncovered at each N whatever their strength: the ranking's own loss,
    # apart from the detection's (the S_in rule above lets one cell decide).
    picks = {"all": lambda t: True, "outside the listed bands": lambda t: not t["in_band"],
             "inside the listed bands": lambda t: t["in_band"]}
    for x in sens:
        kept = [t for t in rows if t["kept"] and picks[x["where"]](t) and
                list(measure.DRIFT_BINS[t["bin"]]) == x["drift"]]
        x["kept_n"] = len(kept)
        for big in N_LOOK:
            k = sum(t["rank"] is not None and t["rank"] <= big for t in kept)
            x[f"of_kept_top{big}"] = [k, measure.wilson(k, len(kept))] if kept else None
    held = json.loads(_p("heldout.json").read_text(encoding="utf-8"))["rows"] if _p("heldout.json").exists() else []
    for h in held:
        if h.get("found"):
            h["rank_among_real"] = rank_of(h)
            kept_birdies = [t for t in rows if t["kept"] and t["rank"] is not None]
            h["birdies_ahead"] = round(sum(key(t["ranking"]) < key(h) for t in kept_birdies) / len(kept_birdies), 3) \
                if kept_birdies else None
            h["birdies_behind_by_where"] = {
                w: round(sum(key(t["ranking"]) >= key(h) for t in kept_birdies if pick(t)) /
                         max(1, sum(1 for t in kept_birdies if pick(t))), 3)
                for w, pick in (("outside the listed bands", lambda t: not t["in_band"]),
                                ("inside the listed bands", lambda t: t["in_band"]))}
    record = {"ablation": ablation(rows, ranked["sessions"][session]["ranked"], held),
              "calibration": ranked["sessions"][session].get("calibration"),
              "cells": cells, "sensitivity": sens, "heldout": held, "birdies": len(rows),
              "real": ranked["sessions"][session], "share": SHARE, "n_look": N_LOOK, "cap": CAP, "kind": "measured"}
    yoke.write(_p("ranking_tables.json"), record, stamp=True)
    for a in record["ablation"]:
        say(f"  without {a['without']:>10}: kept birdies ahead of every real {a['kept_ahead_of_every_real'][0]}/"
            f"{a['kept_ahead_of_every_real'][1]}; best held-out ahead of {a['best_held_out_ahead_of_kept_share']} of "
            f"them; held-out ahead of every real {a['held_out_ahead_of_every_real']}; real moved "
            f"{a['real_candidates_moved']}")
    say(f"{len(rows)} birdies; S_in from which {SHARE:.0%} are kept / uncovered in the first "
        + " / ".join(map(str, N_LOOK)) + ":")
    for s in sens:
        say(f"  {s['where']:>25}, {s['drift'][0]:4.2f}-{s['drift'][1]:4.2f} Hz/s: {s['kept']} / "
            + " / ".join(str(s[f'top{n}']) for n in N_LOOK))
    for h in held:
        if h.get("found"):
            say(f"  held out: block {h['block']} {tuple(h['as_on'])} {h['f_mhz']:.6f}: {h['verdict']}, score "
                f"{h['score']:.2f}, rank {h['rank_among_real']} among the real, {h['birdies_ahead']:.0%} of kept "
                "birdies ahead of it")
    return record


def ablation(rows, real_ranked, held):
    """How much the ranking leans on each term: each taken out in turn (its
    value set to 0 for every candidate, real, planted and held out), the
    ranking redone. For each: the share of kept birdies ranked ahead of every
    real candidate; the share of kept birdies the best-scoring held-out
    candidate is ahead of; how many of the real candidates change place;
    and the same with nothing taken out. Nothing is refitted: it shows
    whether one term carries the ranking, not which weights would be best."""
    kept = [t for t in rows if t["kept"] and t.get("ranking")]
    found = [h for h in held if h.get("found")]

    def without(s, term):
        t = dict(s["terms"])
        if term:
            t[term] = 0.0
        return {"shown": s["shown"], "score": round(sum(t.values()), 3), "snr": s.get("snr")}
    out = []
    base_order = None
    for term in (None, *TERMS):
        real = sorted(range(len(real_ranked)), key=lambda i: key(without(real_ranked[i], term)))
        real_keys = sorted(key(without(s, term)) for s in real_ranked)
        first = sum(key(without(t["ranking"], term)) < real_keys[0] for t in kept) if real_keys else len(kept)
        hk = sorted((key(without(h, term)) for h in found)) if found else []
        best_held_ahead = (sum(hk[0] < key(without(t["ranking"], term)) for t in kept) / len(kept)
                           if hk and kept else None)
        held_ahead_of_real = sum(k < real_keys[0] for k in hk) if real_keys else None
        if base_order is None:
            base_order = real
        out.append({"without": term or "nothing", "kept_ahead_of_every_real": [first, len(kept)],
                    "best_held_out_ahead_of_kept_share": None if best_held_ahead is None else round(best_held_ahead, 3),
                    "held_out_ahead_of_every_real": held_ahead_of_real,
                    "real_candidates_moved": sum(a != b for a, b in zip(base_order, real)),
                    "terms_nonzero_in_kept": sum(bool(t["ranking"]["terms"].get(term)) for t in kept) if term else None})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("offnull")
    sub.add_parser("rank")
    b = sub.add_parser("birdies")
    b.add_argument("--runs", type=int, default=10)
    b.add_argument("--add", action="store_true", help="add to the birdies already kept")
    sub.add_parser("heldout")
    sub.add_parser("tables")
    a = ap.parse_args(argv)
    if a.cmd == "offnull":
        off_null()
    elif a.cmd == "rank":
        rank()
    elif a.cmd == "birdies":
        birdies(a.runs, add=a.add)
    elif a.cmd == "heldout":
        heldout()
    else:
        tables()


if __name__ == "__main__":
    main()
