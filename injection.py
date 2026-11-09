"""Signals planted in whole cadences and followed through everything: the
search of each look, the cadence test, and the checks. What comes out the
other end is the search's completeness; where a signal is lost is
recorded stage by stage.

A planted signal is a tone as the sky makes it (measure.plant: smeared
through each spectrum, an FFT channel's response, a random place in a
channel), its strength S_in set from each look's own noise (measured
apart from the search), placed in the three ON looks at the frequency
its drift carries it to by each look's start, and in none of the OFF
looks ("on"). Some are placed in all six looks alike ("all"), as
interference would be, to measure how often the cadence test and the
checks wrongly keep interference.

Each signal's journey:

- search: found at the cut in how many ON looks (at its place, its drift
  within 3 steps or 10%);
- cadence: the label of the event its hits made (candidate, interference,
  unconfirmed), or none;
- checks: the verdict of the checks on a candidate (vetting.py), when run.
"""
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np


import measure
import onoff
import searching
import seti

EDGE_KEEP = 3000        # channels kept clear of a slice's ends: a track moves up to ~2,300 channels between looks


def load(files):
    """A cadence's six saved looks, each with its own channel noise."""
    out = []
    for path in files:
        s = seti.read_slice(path, -1e12, 1e12)
        out.append({"s": s, "raw": s["spectra"], "sigma": measure.channel_noise(s["spectra"])})
    return out


def position_bin(channel_in_file, per, reach):
    """Where in its coarse channel a signal starts: edge (within 5% of an
    end), dc (within the drift's reach of the middle), or middle."""
    within = channel_in_file % per
    if min(within, per - 1 - within) < seti.EDGE_FRACTION * per:
        return "edge"
    if abs(within - per // 2) <= reach:
        return "dc"
    return "middle"


def trial(cadence, tones, vet=None):
    """One cadence with `tones` planted, searched, judged (and checked, with
    `vet`): each tone's journey. A tone: {x0 (fractional channel at the first
    look's start), drift (Hz/s), s_in, where ("on" or "all")}."""
    first = cadence[0]["s"]
    t0 = first["tstart"]
    per_channel = first["foff"] * 1e6
    planted = []
    for j, look in enumerate(cadence):
        s, raw, sigma = look["s"], look["raw"], look["sigma"]
        dt = (s["tstart"] - t0) * 86400
        here = []
        for tone in tones:
            if tone["where"] == "all" or j % 2 == 0:
                x = tone["x0"] + tone["drift"] * dt / per_channel
                c = int(min(max(round(x), 0), raw.shape[1] - 1))
                here.append((x, tone["drift"], tone["s_in"] * sigma[c] / math.sqrt(raw.shape[0])))
        planted.append(measure.plant(raw, here, s["tsamp"], s["foff"]) if here else raw)

    def one(j):
        s = cadence[j]["s"]
        details = {}
        hits = seti.describe(searching.search(planted[j], s["foff"], s["tsamp"], s["fch1"], details=details),
                             dict(s, spectra=planted[j]))
        return hits, details["flat"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        searched = list(pool.map(one, range(len(cadence))))
    looks = [onoff.Look(hits, c["s"]["tstart"], c["s"]["fch1"], c["s"]["foff"], c["s"]["tsamp"], flat, j)
             for j, ((hits, flat), c) in enumerate(zip(searched, cadence))]
    events = onoff.judge(looks)
    verdicts = {}
    if vet is not None:
        for i, e in enumerate(events):
            if e["label"] == "candidate":
                verdicts[i] = vet(e, looks)
    out = []
    used = [set() for _ in looks]
    for tone in tones:
        found_in = {}
        for lk in looks:
            if not lk.on:
                continue
            dt = (lk.tstart - t0) * 86400
            x = tone["x0"] + tone["drift"] * dt / per_channel
            before = set(used[lk.position])
            hit = measure.matched(lk.hits, x, tone["drift"], lk.step, used[lk.position])
            if hit:
                found_in[lk.position] = (used[lk.position] - before).pop()
        event = next((i for i, e in enumerate(events)
                      if any(e["matches"][p] == idx for p, idx in found_in.items())), None)
        e = events[event] if event is not None else None
        out.append(dict(tone, found_on_looks=len(found_in),
                        label=e["label"] if e else None,
                        off_snr_max=e["off_snr_max"] if e else None, on_snr_min=e["on_snr_min"] if e else None,
                        drift_flag=e["drift_flag"] if e else None,
                        verdict=verdicts.get(event, {}).get("verdict") if event is not None else None,
                        reasons=verdicts.get(event, {}).get("reasons") if event is not None else None))
    for lk in looks:
        lk.flat = None
    return out, events


def tones_for(cadence, n_on, n_all, rng, strengths=measure.STRENGTHS, bins=measure.DRIFT_BINS, avoid=(),
              which=None):
    """Tones spread over the slice, clear of each other, in every drift bin
    and strength in turn."""
    s = cadence[0]["s"]
    n_f = s["spectra"].shape[1]
    span = (s["spectra"].shape[0] - 1) * s["tsamp"]
    margin = int(searching.MAX_DRIFT * span / (abs(s["foff"]) * 1e6)) + 30
    where = measure.places(n_f, n_on + n_all, 2 * margin + 2400, list(avoid), EDGE_KEEP, rng)
    cells = [(b, st) for b in (which if which is not None else range(len(bins))) for st in strengths]
    out = []
    for k, c in enumerate(where):
        b, st = cells[k % len(cells)]
        lo, hi = bins[b]
        drift = float(rng.uniform(lo, hi)) * (1 if rng.random() < 0.5 else -1)
        out.append({"x0": c + float(rng.uniform(-0.5, 0.5)), "drift": drift, "s_in": st, "bin": b,
                    "where": "on" if k < n_on else "all",
                    "position": position_bin(int(s.get("first_channel", 0)) + c, int(s["coarse_channel"]),
                                             margin)})
    rng.shuffle(out)
    return out


# --- Phase 6: completeness through everything, and false candidates -------------

SEFD_JY = 10.0          # Green Bank at L and S band (Price et al. 2020): assumed, not measured here
N_POL = 2


def flux_jy_hz(s_in, n_t, width_hz, tsamp):
    """A planted signal's flux in Jy Hz (1e-26 W m^-2), from its S_in and the
    radiometer equation with SEFD_JY: one channel's noise in one spectrum is
    SEFD / sqrt(n_pol x channel width x tsamp) Jy, and S_in = h x sqrt(n_t) / sigma."""
    sigma_jy = SEFD_JY / math.sqrt(N_POL * width_hz * tsamp)
    return s_in / math.sqrt(n_t) * sigma_jy * width_hz


def dc_tone(cadence, rng, s_in=60):
    """One tone starting near the coarse channel's middle (the blanked spike)."""
    s = cadence[0]["s"]
    per, first = int(s["coarse_channel"]), int(s.get("first_channel", 0))
    middle = (per // 2 - first) % per          # the middle's channel in this slice
    span = (s["spectra"].shape[0] - 1) * s["tsamp"]
    reach = int(searching.MAX_DRIFT * span / (abs(s["foff"]) * 1e6))
    c = middle + int(rng.integers(-reach, reach + 1))
    b = int(rng.integers(0, len(measure.DRIFT_BINS)))
    lo, hi = measure.DRIFT_BINS[b]
    return {"x0": c + float(rng.uniform(-0.5, 0.5)), "drift": float(rng.uniform(lo, hi)) * (1 if rng.random() < 0.5 else -1),
            "s_in": s_in, "bin": b, "where": "on", "position": "dc"}


def study(cadence_files, runs, n_on=32, n_all=8, seed=11, vet=None, say=print, which=None, dc=1):
    """Signals planted through everything in each cadence `runs` times:
    every tone's journey."""
    rng = np.random.default_rng(seed)
    rows = []
    for files in cadence_files:
        cad = load(files)
        for r in range(runs):
            middle = [dc_tone(cad, rng) for _ in range(dc)]
            tones = tones_for(cad, n_on, n_all, rng, avoid=[int(m["x0"]) for m in middle], which=which)
            out, _ = trial(cad, tones + middle, vet=vet)
            name = files[0].replace("\\", "/").rsplit("/", 1)[-1]
            for t in out:
                rows.append(dict(t, cadence=name))
            say(f"{name}: run {r + 1} of {runs}: "
                f"{sum(t['label'] == 'candidate' for t in out if t['where'] == 'on')} of "
                f"{sum(t['where'] == 'on' for t in out)} ON-only signals candidates", flush=True)
    return rows


def kept(t):
    """A planted ON-only signal kept to the end: a candidate the checks do
    not call interference (shown). "Likely interference" is a weight, kept
    apart in the tables."""
    return t["label"] == "candidate" and not str(t.get("verdict") or "").startswith("interference")


def tables(rows, n_t, width_hz, tsamp):
    """Completeness by drift bin and S_in, through each stage, with Wilson
    intervals; by position; and the in-all signals wrongly kept."""
    out = {"by_cell": [], "by_position": [], "in_all": None}
    on = [t for t in rows if t["where"] == "on" and t["position"] != "dc"]
    for b, (lo, hi) in enumerate(measure.DRIFT_BINS):
        for st in measure.STRENGTHS:
            cell = [t for t in on if t["bin"] == b and t["s_in"] == st]
            n = len(cell)
            if not n:
                continue
            found = sum(t["found_on_looks"] > 0 for t in cell)
            cand = sum(t["label"] == "candidate" for t in cell)
            k = sum(kept(t) for t in cell)
            likely = sum(t["label"] == "candidate" and str(t.get("verdict") or "").startswith("likely") for t in cell)
            out["by_cell"].append({
                "drift_hz_s": [lo, hi], "s_in": st, "flux_jy_hz": round(flux_jy_hz(st, n_t, width_hz, tsamp), 1),
                "planted": n, "found_in_a_look": found, "candidate": cand, "kept": k,
                "kept_rate": round(k / n, 3), "kept_interval": measure.wilson(k, n),
                "marked_likely_interference": likely,
                "lost_at": {"search": n - found, "cadence": found - cand, "checks": cand - k}})
    for pos in ("middle", "edge", "dc"):
        cell = [t for t in rows if t["where"] == "on" and t["position"] == pos and t["s_in"] >= 60]
        n = len(cell)
        if n:
            k = sum(kept(t) for t in cell)
            out["by_position"].append({"position": pos, "s_in": "60 and 120", "planted": n, "kept": k,
                                       "kept_rate": round(k / n, 3), "kept_interval": measure.wilson(k, n)})
    allr = [t for t in rows if t["where"] == "all"]
    if allr:
        wrong = [t for t in allr if t["label"] == "candidate" and not str(t.get("verdict") or "").startswith("interference")]
        found = [t for t in allr if t["found_on_looks"] > 0]
        out["in_all"] = {"planted": len(allr), "found_in_a_look": len(found),
                         "labelled_interference": sum(t["label"] == "interference" for t in allr),
                         "kept_as_candidate": len(wrong), "kept_interval": measure.wilson(len(wrong), len(found)),
                         "kept": [{k: t[k] for k in ("s_in", "drift", "label", "off_snr_max", "verdict")} for t in wrong]}
    return out


def false_candidates(cadence_files, vet=None, say=print):
    """Candidates where none can be: each cadence's six looks searched once,
    then judged with every other choice of three looks as the ON looks (19
    of the 20; the true ON looks are left out). A signal from the target is
    in the true ON looks only, so anything these call a candidate is noise
    or interference passing the test. Each goes through the checks too."""
    import itertools
    out = []
    for files in cadence_files:
        cad = load(files)

        def one(j):
            s = cad[j]["s"]
            details = {}
            hits = seti.describe(searching.search(cad[j]["raw"], s["foff"], s["tsamp"], s["fch1"], details=details),
                                 s)
            return hits, details["flat"]
        with ThreadPoolExecutor(max_workers=6) as pool:
            searched = list(pool.map(one, range(6)))
        name = files[0].replace("\\", "/").rsplit("/", 1)[-1]
        for ons in itertools.combinations(range(6), 3):
            if ons == (0, 2, 4):
                continue
            offs = [j for j in range(6) if j not in ons]
            order = {j: 2 * i for i, j in enumerate(ons)} | {j: 2 * i + 1 for i, j in enumerate(offs)}
            looks = sorted((onoff.Look(searched[j][0], cad[j]["s"]["tstart"], cad[j]["s"]["fch1"], cad[j]["s"]["foff"],
                                       cad[j]["s"]["tsamp"], searched[j][1], order[j]) for j in range(6)),
                           key=lambda lk: lk.position)
            events = onoff.judge(looks)
            cands = [e for e in events if e["label"] == "candidate"]
            verdicts = [vet(e, looks)["verdict"] if vet else None for e in cands]
            out.append({"cadence": name, "as_on": list(ons), "events": len(events), "candidates": len(cands),
                        "survivors": sum(not str(v or "").startswith("interference") for v in verdicts),
                        "unexplained": sum(str(v or "").startswith("unexplained") for v in verdicts),
                        "verdicts": verdicts,
                        "frequencies": [round(e["frequency_mhz"], 6) for e in cands]})
            say(f"{name} with looks {ons} as ON: {len(cands)} candidate(s)"
                + (f", checks: {verdicts}" if cands else ""), flush=True)
    return out
