"""Which kinds of signal the search has been shown to recover (docs/audits.md
15): signals planted with shapes the published completeness never planted,
through the search and cadence test unchanged (matched.our_search,
our_events, _our_kept, _status), on synthetic cadences (tests/synth.py:
16 spectra of 16,384 channels, Green Bank's channel width and sampling, noise
only). Supplementary; nothing published changes.

    python tools/coverage_checks.py

Each kind is planted in the three ON looks, six signals a cadence at random
places, five cadences, at S_in 30, 60 and 120, drift ±0.3 and ±2 Hz/s (60
signals a cell; exploratory: synthetic noise, no interference):

- continuous: as the published completeness plants them (the baseline);
- half of each ON look, a quarter of each ON look: on for the first spectra;
- missing from one ON look: absent from the second ON look;
- a hop between looks: 100 Hz further at each ON look (beyond the matching
  tolerance, as a hopping transmitter);
- a random walk: the frequency wandering 0.5 Hz a spectrum (sd) about the
  drift, a fresh walk in each ON look; and a wide walk, 2.8 Hz (a channel)
  a spectrum;
- 16 channels wide: the same power spread over 16 adjacent channels.

For each signal, measured where it was actually planted in each ON look
(true_x: the hop and the wide signal's centre included): in how many ON
looks a hit lies at it (single-look detection); whether one kept candidate
holds a hit at it in all three ON looks (found across the cadence, on its
true positions); and, apart, whether the cadence test recovers it on its
straight track (matched._status, the published standard). Intervals are
Wilson's over signals and assume them independent, which six signals a
cadence are not; a kind not planted here is untested, not missed.
"""
import itertools
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import matched  # noqa: E402
import measure  # noqa: E402
import synth  # noqa: E402
import yoke  # noqa: E402

OUT = yoke.DATA / "analysis" / "coverage_checks.json"
STRENGTHS = (30, 60, 120)
SEEDS = (21, 22, 23, 24, 25)
DRIFTS = (0.3, 2.0)
N_SIGNALS = 6
CUT = 10.0
KINDS = ("continuous", "half of each ON look", "a quarter of each ON look", "missing from one ON look",
         "a hop between looks", "a random walk", "a wide random walk", "16 channels wide")
HOP_HZ = 100.0
WIDE = 16


def true_x(cad, t, kind, j):
    """Where the signal was planted in ON look j at its start (fractional channel): the straight track,
    plus the hop, or the wide signal's centre."""
    s = cad[j]["s"]
    x = matched.where(cad, t, j)[0]
    k = matched.TRUE.index(j)
    if kind == "a hop between looks":
        x += k * HOP_HZ / abs(s["foff"] * 1e6)
    if kind == "16 channels wide":
        x += (WIDE - 1) / 2
    return x


def reach(kind):
    """How far from true_x a hit may lie and still be this signal's (channels)."""
    return WIDE / 2 + 3 if kind == "16 channels wide" else 3


def associated(kept, cad, t, kind):
    """Whether one kept candidate holds a hit at the signal's true place in every ON look."""
    for ev in kept:
        on = {}
        for j, _, f, _ in ev["members"]:
            if j in matched.TRUE:
                x = (f - cad[j]["s"]["fch1"]) / cad[j]["s"]["foff"]
                on[j] = on.get(j, False) or abs(x - true_x(cad, t, kind, j)) <= reach(kind)
        if len(on) == 3 and all(on.values()):
            return True
    return False


def _say(*a):
    print(*a, flush=True)


def _plant_kind(cad, ts, kind, rng):
    """The cadence with each signal of ts planted in the ON looks as `kind`."""
    out = []
    n_t = cad[0]["raw"].shape[0]
    for j, c in enumerate(cad):
        raw, s = c["raw"], c["s"]
        if j not in matched.TRUE:
            out.append(dict(c, spectra=raw))
            continue
        k = matched.TRUE.index(j)
        dt = (s["tstart"] - cad[0]["s"]["tstart"]) * 86400
        sig = np.zeros_like(raw)
        for t in ts:
            x = t["x0"] + t["drift"] * dt / (s["foff"] * 1e6)
            h = t["h"]
            if kind == "missing from one ON look" and k == 1:
                continue
            if kind == "a hop between looks":
                x += k * HOP_HZ / abs(s["foff"] * 1e6)
            if kind == "16 channels wide":
                tones = [(x + w, t["drift"], h / WIDE) for w in range(WIDE)]
            elif kind in ("a random walk", "a wide random walk"):
                sd = 0.5 if kind == "a random walk" else abs(s["foff"] * 1e6)
                steps = np.concatenate([[0.0], np.cumsum(rng.normal(0, sd, n_t))])
                grid = np.arange(n_t + 1) * s["tsamp"]

                def path(tau, steps=steps, grid=grid, d=t["drift"]):
                    return d * tau + np.interp(tau, grid, steps)
                tones = [(x, t["drift"], h, path)]
            else:
                tones = [(x, t["drift"], h)]
            sig += measure.plant(np.zeros_like(raw), tones, s["tsamp"], s["foff"])
        if kind in ("half of each ON look", "a quarter of each ON look"):
            keep = n_t // 2 if kind.startswith("half") else n_t // 4
            sig[keep:] = 0.0
        spectra = raw + sig
        out.append(dict(c, raw=spectra, spectra=spectra, s=dict(s, spectra=spectra)))
    return out


def _looks_with_hit(cad, searched, t, kind):
    n = 0
    for j in matched.TRUE:
        x = true_x(cad, t, kind, j)
        n += any(abs((h["frequency_mhz"] - cad[j]["s"]["fch1"]) / cad[j]["s"]["foff"] - x) <= reach(kind)
                 for h in searched[j][0] if h["snr"] >= CUT)
    return n


def run(say=_say):
    rows = []
    for seed in SEEDS:
        base = [dict(c, spectra=c["raw"]) for c in synth.cadence(seed)]
        sigma = float(np.median(base[0]["sigma"]))
        plain = matched.our_search(base)
        looks, events, order = matched.our_events(base, plain, matched.TRUE, CUT, [{} for _ in range(6)])
        kept_plain = matched._our_kept(looks, events, order)
        for kind, s_in, drift in itertools.product(KINDS, STRENGTHS, DRIFTS):
            rng = np.random.default_rng([seed, KINDS.index(kind), s_in, int(drift * 10)])
            places = np.sort(rng.choice(np.arange(1500, 14500, 1800), N_SIGNALS, replace=False)
                             + rng.uniform(0, 400, N_SIGNALS))
            ts = [{"x0": float(c), "drift": drift if i % 2 == 0 else -drift,
                   "h": s_in * sigma / math.sqrt(base[0]["raw"].shape[0])} for i, c in enumerate(places)]
            cad = _plant_kind(base, ts, kind, rng)
            searched = matched.our_search(cad)
            looks, events, order = matched.our_events(cad, searched, matched.TRUE, CUT, [{} for _ in range(6)])
            kept = matched._our_kept(looks, events, order)
            for t in ts:
                st = matched._status({j: matched.where(base, t, j)[1] for j in matched.TRUE}, t["drift"], kept,
                                     kept_plain)
                found = associated(kept, base, t, kind)
                rows.append({"seed": seed, "kind": kind, "s_in": s_in, "drift": drift,
                             "on_looks_with_hit": _looks_with_hit(base, searched, t, kind),
                             "found_on_its_true_places": found, "recovered": st["three_looks"] == "recovered"})
        say(f"seed {seed} done")
    table = {}
    for kind in KINDS:
        table[kind] = {}
        for s_in in STRENGTHS:
            rs = [r for r in rows if r["kind"] == kind and r["s_in"] == s_in]
            n = len(rs)
            found = sum(r["found_on_its_true_places"] for r in rs)
            table[kind][str(s_in)] = {
                "signals": n,
                "hit_in_every_on_look": sum(r["on_looks_with_hit"] == 3 for r in rs),
                "found_on_its_true_places": found,
                "found_interval_if_independent": list(measure.wilson(found, n)),
                "recovered_on_its_straight_track": sum(r["recovered"] for r in rs),
                "by_cadence_found": [sum(r["found_on_its_true_places"] for r in rs if r["seed"] == sd) for sd in SEEDS]}
        say(f"{kind}: " + "; ".join(f"S_in {s}: hit in every ON look {v['hit_in_every_on_look']}, found "
                                    f"{v['found_on_its_true_places']}, straight-track {v['recovered_on_its_straight_track']}"
                                    f" of {v['signals']}" for s, v in table[kind].items()))
    rec = {"kind": "measured", "label": "synthetic exploratory checks", "cut": CUT, "strengths": STRENGTHS,
           "seeds": SEEDS, "drifts_hz_s": DRIFTS,
           "cadence": "synthetic (tests/synth.py), noise only", "table": table, "rows": rows,
           "untested": ["pulses and periodic trains (needs another data product)", "drift beyond ±4 Hz/s",
                        "eccentric orbits", "broadband beyond 16 channels"]}
    yoke.write(OUT, rec, indent=1, stamp=True)
    return rec


if __name__ == "__main__":
    run()
