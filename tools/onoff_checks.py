"""Checks of the cadence test, onoff.py (docs/audits.md 11). onoff.py is
frozen; these measure what it does, from its own functions. They run on
blocks inside tools/detector_checks.py's run (so blocks are read once), and
on synthetic looks here.

    python tools/onoff_checks.py synthetic

- **unmeasured OFF** (A11-01): best_track gives nothing where it has fewer
  than 16 reference lines or no spread, and judge then counts that OFF look
  as clear. unmeasured(events): candidates with an OFF look neither
  measured (projected or fixed) nor holding a hit.
- **weak ON** (A11-02, exploratory): an ON look without a hit passes on the best of
  every place and drift within the tolerances reaching ON_MIN. null_on: at
  random places in the first ON look where nothing was planted, how often
  the other ON looks reach ON_MIN that way (each, and both, which with one
  hit makes a candidate if the OFF looks are clear), by drift.
- **asymmetry** (A11-03): distance(a, b) predicts and sets its tolerance from
  a's drift, and pairs are made from the earlier look to the later.
  asymmetry: of real hit pairs within distance 1 one way, how many are not
  the other way.
"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import measure  # noqa: E402
import onoff  # noqa: E402
import yoke  # noqa: E402

OUT = yoke.DATA / "analysis"
DRIFT_BANDS = ((0.0, 0.5), (0.5, 2.0), (2.0, 4.0))


def unmeasured(events):
    """Candidates with an OFF look neither measured nor holding a hit, and with every OFF look so."""
    some = every = 0
    for e in events:
        if e["label"] != "candidate":
            continue
        offs = [x for x in e["looks"] if not x["on"]]
        blind = [x.get("track_snr") is None and x.get("track_snr_fixed") is None and not x.get("hit_snr")
                 and not x.get("found") for x in offs]
        some += any(blind)
        every += bool(blind) and all(blind)
    return {"candidates": sum(e["label"] == "candidate" for e in events), "some_off_unmeasured": some,
            "every_off_unmeasured": every}


def null_on(looks, n=200, seed=0):
    """At n random places and drifts in the first ON look: the best S/N the other ON looks give within
    the matching tolerances (as judge measures an ON look without a hit), and the OFF test there."""
    rng = np.random.default_rng(seed)
    ons = [lk for lk in looks if lk.on]
    l0 = ons[0]
    margin = int(onoff.REF_OFFSETS.max()) + 4 * l0.n_t + 64
    if l0.n_f <= 2 * margin:
        return {}
    rows = []
    for _ in range(n):
        c = int(rng.integers(margin, l0.n_f - margin))
        drift = float(rng.uniform(-4.0, 4.0))
        k = abs(drift) / l0.step
        top = {"frequency_mhz": l0.fch1 + c * l0.foff, "drift_hz_s": drift, "snr": 0.0,
               "box_channels": max(1, math.ceil(k / max(l0.n_t - 1, 1)))}
        on_best = []
        for lk in ons[1:]:
            dt = (lk.tstart - l0.tstart) * 86400
            f_tol, d_tol = onoff._tolerance(top, top, l0, lk, dt)
            s, _, _ = lk.best_track(lk.channel(top["frequency_mhz"] + drift * dt / 1e6), drift, f_tol, d_tol)
            on_best.append(-np.inf if s is None else s)
        off_best, hit = -np.inf, False
        for lk in looks:
            if lk.on:
                continue
            dt = (lk.tstart - l0.tstart) * 86400
            f_tol, d_tol = onoff._tolerance(top, top, l0, lk, dt)
            for f in (top["frequency_mhz"] + drift * dt / 1e6, top["frequency_mhz"]):
                s, _, _ = lk.best_track(lk.channel(f), drift, f_tol, d_tol)
                off_best = max(off_best, -np.inf if s is None else s)
            hit = hit or bool(onoff._near_any(top, l0, lk))
        rows.append((abs(drift), on_best, off_best >= onoff.OFF_MAX or hit))
    out = {}
    for lo, hi in DRIFT_BANDS:
        rs = [r for r in rows if lo <= r[0] < hi]
        if not rs:
            continue
        each = [b >= onoff.ON_MIN for r in rs for b in r[1]]
        both = [all(b >= onoff.ON_MIN for b in r[1]) for r in rs]
        clear = [b and not r[2] for b, r in zip(both, rs)]
        out[f"{lo}-{hi}"] = {"places": len(rs), "each_on_look_over_on_min": round(float(np.mean(each)), 4),
                             "both_over_on_min": round(float(np.mean(both)), 4),
                             "both_and_off_clear": round(float(np.mean(clear)), 4),
                             "both_and_off_clear_interval": list(measure.wilson(int(sum(clear)), len(clear)))}
    out["note"] = ("exploratory: random places, not detected hits; how often unrelated places pass the track rule, "
                   "not a candidate false-acceptance probability")
    return out


def asymmetry(looks):
    """Real hit pairs between ON looks (earlier to later, as _events makes them): how many are within
    distance 1 one way, and how many of those are not within it the other way. The candidates are
    screened both ways (onoff._close from each side), since its screen is the forward distance."""
    ons = [lk for lk in looks if lk.on]
    one_way = both_ways = only_forward = only_backward = 0
    for u, la in enumerate(ons):
        for lb in ons[u + 1:]:
            pairs = candidate_pairs(la, lb)
            for ia, ib in pairs:
                a, b = la.hits[ia], lb.hits[ib]
                f = onoff.distance(a, b, la, lb) <= 1
                r = onoff.distance(b, a, lb, la) <= 1
                if f or r:
                    one_way += 1
                    both_ways += f and r
                    only_forward += f and not r
                    only_backward += r and not f
    return {"pairs_within_1_some_way": one_way, "both_ways": both_ways, "forward_only": only_forward,
            "backward_only": only_backward}


def candidate_pairs(la, lb):
    """(index in la, index in lb) of hits at the cut that onoff._close passes either way."""
    rows_a = np.array([i for i, h in enumerate(la.hits) if not h.get("shadow")], int)
    rows_b = np.array([i for i, h in enumerate(lb.hits) if not h.get("shadow")], int)
    out = set()
    if not len(rows_a) or not len(rows_b):
        return out
    for ia in rows_a:
        out.update((int(ia), int(rows_b[k])) for k in onoff._close(la.hits[ia], la, lb, rows=rows_b))
    for ib in rows_b:
        out.update((int(rows_a[k]), int(ib)) for k in onoff._close(lb.hits[ib], lb, la, rows=rows_a))
    return out


def example():
    """Two hits 1,320 s apart with drifts 3.4372 and 3.6141 Hz/s (GBT high-resolution channels):
    the distance each way, at the separation where the forward one is 0.92."""
    tsamp, width = 18.253611008, 2.7939677238464355
    step = width / (15 * tsamp)
    la = SimpleNamespace(tstart=60000.0, width_hz=width, step=step)
    lb = SimpleNamespace(tstart=60000.0 + 1320 / 86400, width_hz=width, step=step)
    a = {"frequency_mhz": 1500.0, "drift_hz_s": 3.4372}
    best = None
    for off in np.linspace(0, 400, 40001):
        b = {"frequency_mhz": 1500.0 + (3.4372 * 1320 + off) / 1e6, "drift_hz_s": 3.6141}
        d = onoff.distance(a, b, la, lb)
        if best is None or abs(d - 0.92) < abs(best[0] - 0.92):
            best = (d, onoff.distance(b, a, lb, la), off)
    return {"forward": round(best[0], 3), "backward": round(best[1], 3), "offset_hz": round(float(best[2]), 2)}


def synthetic(say=print):
    rec = {"kind": "measured", "example": example()}
    say(f"asymmetry example: {rec['example']}")
    yoke.write(OUT / "onoff_checks_synthetic.json", rec, indent=1, stamp=True)
    return rec


if __name__ == "__main__":
    {"synthetic": synthetic}[sys.argv[1] if len(sys.argv) > 1 else "synthetic"]()
