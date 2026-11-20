"""Which kinds of signal the search has been shown to recover (docs/audits.md
15): signals planted with shapes the published completeness never planted,
through the search and cadence test unchanged (matched.our_search,
our_events, _our_kept, _status), on synthetic cadences (tests/synth.py:
16 spectra of 16,384 channels, Green Bank's channel width and sampling, noise
only). Supplementary; nothing published changes.

    python tools/coverage_checks.py

Each kind is planted in the three ON looks, six signals a cadence, three
cadences, at S_in 30, 60 and 120, drift ±0.3 Hz/s:

- continuous: as the published completeness plants them (the baseline);
- half of each ON look, a quarter of each ON look: on for the first spectra;
- missing from one ON look: absent from the second ON look;
- a hop between looks: 100 Hz further at each ON look (beyond the matching
  tolerance, as a hopping transmitter);
- a random walk: the frequency wandering 0.5 Hz a spectrum (sd) about the
  drift;
- 16 channels wide: the same power spread over 16 adjacent channels.

For each signal: in how many ON looks a hit lies within 3 channels of where
it was planted at the look's start (single-look detection), whether the
cadence test recovers it in all three ON looks at cut 10 (matched._status
against its straight track) and whether any candidate lies within 200 Hz
(found, perhaps on another track). Kinds whose track is not straight
(hops, walks) can be found without being recovered on the straight track:
the two are reported apart, and a kind not planted here is untested, not
missed.
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
SEEDS = (21, 22, 23)
CHANNELS = (2500, 4500, 6500, 8500, 10500, 12500)
DRIFT = 0.3
CUT = 10.0
KINDS = ("continuous", "half of each ON look", "a quarter of each ON look", "missing from one ON look",
         "a hop between looks", "a random walk", "16 channels wide")


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
                x += k * 100.0 / abs(s["foff"] * 1e6)
            if kind == "16 channels wide":
                tones = [(x + w, t["drift"], h / 16) for w in range(16)]
            elif kind == "a random walk":
                steps = np.concatenate([[0.0], np.cumsum(rng.normal(0, 0.5, n_t))])
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


def _looks_with_hit(cad, searched, t):
    n = 0
    for j in matched.TRUE:
        x, _ = matched.where(cad, t, j)
        n += any(abs((h["frequency_mhz"] - cad[j]["s"]["fch1"]) / cad[j]["s"]["foff"] - x) <= 3
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
        for kind, s_in in itertools.product(KINDS, STRENGTHS):
            rng = np.random.default_rng([seed, KINDS.index(kind), s_in])
            ts = [{"x0": float(c), "drift": DRIFT if i % 2 == 0 else -DRIFT,
                   "h": s_in * sigma / math.sqrt(base[0]["raw"].shape[0])} for i, c in enumerate(CHANNELS)]
            cad = _plant_kind(base, ts, kind, rng)
            searched = matched.our_search(cad)
            looks, events, order = matched.our_events(cad, searched, matched.TRUE, CUT, [{} for _ in range(6)])
            kept = matched._our_kept(looks, events, order)
            for t in ts:
                st = matched._status({j: matched.where(base, t, j)[1] for j in matched.TRUE}, t["drift"], kept,
                                     kept_plain)
                near = any(j in matched.TRUE and abs(f - matched.where(base, t, j)[1]) * 1e6 <= 200
                           for ev in kept for j, _, f, _ in ev["members"])
                rows.append({"seed": seed, "kind": kind, "s_in": s_in, "on_looks_with_hit": _looks_with_hit(base, searched, t),
                             "recovered": st["three_looks"] == "recovered", "candidate_near": near})
        say(f"seed {seed} done")
    table = {}
    for kind in KINDS:
        table[kind] = {}
        for s_in in STRENGTHS:
            rs = [r for r in rows if r["kind"] == kind and r["s_in"] == s_in]
            n = len(rs)
            table[kind][str(s_in)] = {
                "signals": n,
                "hit_in_every_on_look": sum(r["on_looks_with_hit"] == 3 for r in rs),
                "recovered_on_its_straight_track": sum(r["recovered"] for r in rs),
                "recovered_interval": list(measure.wilson(sum(r["recovered"] for r in rs), n)),
                "a_candidate_within_200_hz": sum(r["candidate_near"] for r in rs)}
        say(f"{kind}: " + "; ".join(f"S_in {s}: hit in every ON look {v['hit_in_every_on_look']}, recovered "
                                    f"{v['recovered_on_its_straight_track']}/{v['signals']}, "
                                    f"candidate near {v['a_candidate_within_200_hz']}"
                                    for s, v in table[kind].items()))
    rec = {"kind": "measured", "cut": CUT, "strengths": STRENGTHS, "seeds": SEEDS, "drift_hz_s": DRIFT,
           "cadence": "synthetic (tests/synth.py), noise only", "table": table, "rows": rows,
           "untested": ["pulses and periodic trains (needs another data product)", "drift beyond ±4 Hz/s",
                        "eccentric orbits", "broadband beyond 16 channels"]}
    yoke.write(OUT, rec, indent=1, stamp=True)
    return rec


if __name__ == "__main__":
    run()
