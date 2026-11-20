"""How much statistical confidence the matched comparisons carry
(docs/audits.md 8). Supplementary analysis of the recorded runs: nothing here
changes a cut, a record or a frozen verdict.

    python tools/statistical_checks.py all          every part, all three sessions
    python tools/statistical_checks.py coverage     the recovery-interval simulation only

Per session (2017, 2016, 2019), at the frozen cut (30 each) and, where both
exist, the matched cuts:

- **recovery**: each pipeline's share found (three looks), Wilson's interval
  (planted signals as independent) beside the block-clustered one (blocks
  resampled within their class, weighted by the session's classes), the
  paired difference, and the ratio of signals found with its interval;
  the number of blocks behind each.
- **false**: the paired difference in false candidates a block (this search
  minus turboSETI; the union of the 19 wrong choices, distinct by shared
  hits, as published), the same blocks resampled for both.
- **selection**: step 4's rule (the lowest cut from which the rate stays at
  most 0.1) applied again to each resample of the blocks: how often each cut
  is chosen, how often none is, and the paired recovery difference at the
  cuts chosen. Selection and evaluation share the data, so this measures the
  operating point's instability, not out-of-sample performance.
- **correlation**: between blocks a given number of blocks apart, the
  correlation of their recovery differences and of their false counts; and
  the paired-difference interval as the resampled window widens, with the
  number of windows left.

- **coverage**: synthetic paired outcomes with a known difference (independent
  signals; a shared block effect; blocks correlated along frequency; unequal
  class sampling; rare recoveries; each pipeline finding some the other
  misses): how often the block-clustered interval and Wilson's (on one share)
  hold the true value, and the bias of the estimate.

Between sessions: three sessions from one telescope are reported side by
side, not pooled; no interval over sessions is given (too few to estimate).
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import matched  # noqa: E402
import matched_tables  # noqa: E402
import measure  # noqa: E402
import yoke  # noqa: E402
from operating_points import SESSIONS  # noqa: E402

OUT = yoke.DATA / "analysis" / "statistical_checks.json"
CLASSES = ("clean", "crowded")
BOOT = 2000
SEED = 8
RATE = matched_tables.RATE
LAGS = (1, 2, 4, 8, 16, 32)
WINDOW_SIZES = (1, 2, 4, 8, 16, 32)


def _say(*a):
    print(*a, flush=True)


# --- estimators on per-block arrays (pure; tests/test_statistical_checks.py) ---------------

def class_index(classes):
    return {c: np.flatnonzero(np.asarray(classes) == c) for c in CLASSES}


def weighted_share(found, n, idx, weights):
    """found, n: per block (found by one pipeline, planted). Each class's share weighted."""
    out = 0.0
    for c, ix in idx.items():
        if len(ix) and n[ix].sum():
            out += weights[c] * found[ix].sum() / n[ix].sum()
    return out


def pooled_share(found, n, idx):
    """The sample's share found, all blocks drawn together (Wilson's estimand)."""
    ix = np.concatenate([v for v in idx.values()])
    return found[ix].sum() / n[ix].sum()


def weighted_mean(x, idx, weights):
    return sum(weights[c] * x[ix].mean() for c, ix in idx.items() if len(ix))


def resample(idx, rng):
    """Block indices drawn with replacement within each class."""
    return {c: ix[rng.integers(0, len(ix), len(ix))] if len(ix) else ix for c, ix in idx.items()}


def boot_interval(stat, idx, rng, boot=BOOT):
    draws = np.array([stat(resample(idx, rng)) for _ in range(boot)], dtype=float)
    draws = draws[np.isfinite(draws)]
    if not len(draws):
        return None
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return [round(float(lo), 4), round(float(hi), 4)]


def choose_cut(rates, cuts):
    """Step 4's rule on point rates: the lowest cut from which the rate stays at most RATE (None if none)."""
    best = None
    for k in range(len(cuts) - 1, -1, -1):
        if rates[k] > RATE:
            break
        best = cuts[k]
    return best


def lag_correlation(blocks, values, lag):
    """Pearson correlation of values at blocks `lag` apart (block numbers), with how many pairs."""
    at = dict(zip(blocks, values))
    pairs = [(at[b], at[b + lag]) for b in blocks if b + lag in at]
    if len(pairs) < 5:
        return {"pairs": len(pairs), "r": None}
    a, b = np.array(pairs, dtype=float).T
    if a.std() == 0 or b.std() == 0:
        return {"pairs": len(pairs), "r": None}
    return {"pairs": len(pairs), "r": round(float(np.corrcoef(a, b)[0, 1]), 3)}


def class_windows(blocks, classes, w):
    """Per class, the index arrays of its blocks in windows of w consecutive block numbers."""
    out = {c: {} for c in CLASSES}
    for i, (b, c) in enumerate(zip(blocks, classes)):
        out[c].setdefault(b // w, []).append(i)
    return {c: [np.array(g) for g in v.values()] for c, v in out.items()}


def resample_windows(groups, rng):
    """Windows drawn with replacement within each class; their blocks' indices by class."""
    return {c: (np.concatenate([gs[i] for i in rng.integers(0, len(gs), len(gs))]) if gs else np.array([], int))
            for c, gs in groups.items()}


def window_interval(blocks, classes, fa, fb, n, weights, w, rng, boot=BOOT):
    """The class-weighted paired difference, windows of w consecutive block numbers resampled whole
    within each class (the same estimand as the block bootstrap at w = 1)."""
    groups = class_windows(blocks, classes, w)
    draws = [weighted_share(fa, n, s, weights) - weighted_share(fb, n, s, weights)
             for s in (resample_windows(groups, rng) for _ in range(boot))]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    windows = {c: len(gs) for c, gs in groups.items()}
    return {"windows_of": w, "windows": windows, "fewest_windows": min(v for v in windows.values() if v),
            "interval": [round(float(lo), 4), round(float(hi), 4)], "width": round(float(hi - lo), 4)}


# --- the sessions ------------------------------------------------------------------------

def _arrays(target):
    session, meta, recs = matched_tables.load(target)
    total = meta["of"]["clean"] + meta["of"]["crowded"]
    weights = {c: meta["of"][c] / total for c in CLASSES}
    recs = sorted(recs, key=lambda r: int(r["block"]))
    blocks = [int(r["block"]) for r in recs]
    classes = [r["class"] for r in recs]
    n = np.array([len(r["tones"]) for r in recs])
    found, false = {}, {}
    for p, grid in (("ours", matched.CUTS_OURS), ("turboseti", matched.CUTS_TURBO)):
        found[p] = {matched.ck(c): np.array([sum(matched_tables._got(t, p, c, "three_looks") for t in r["tones"])
                                             for r in recs]) for c in grid}
        false[p] = {matched.ck(c): np.array([matched_tables.distinct(r, r[p]["false"].get(matched.ck(c), {}),
                                                                     "shared hits") for r in recs]) for c in grid}
    return session, weights, blocks, classes, n, found, false


def _at(target, weights, blocks, classes, n, found, false, co, ct, rng):
    idx = class_index(classes)
    fo, ft = found["ours"][co], found["turboseti"][ct]
    out = {"cuts": [co, ct], "blocks": len(blocks), "blocks_by_class": {c: int(len(ix)) for c, ix in idx.items()},
           "signals": int(n.sum())}
    for p, f in (("ours", fo), ("turboseti", ft)):
        out[p] = {"found": int(f.sum()), "share_pooled": round(float(f.sum() / n.sum()), 4),
                  "wilson_pooled": list(measure.wilson(int(f.sum()), int(n.sum()))),
                  "clustered_pooled": boot_interval(lambda s, f=f: pooled_share(f, n, s), idx, rng),
                  "share_weighted": round(weighted_share(f, n, idx, weights), 4),
                  "clustered_weighted": boot_interval(lambda s, f=f: weighted_share(f, n, s, weights), idx, rng)}
        w = out[p]["wilson_pooled"]
        c = out[p]["clustered_pooled"]
        # the same estimand (the sample's pooled share) both ways
        out[p]["width_ratio_clustered_to_wilson"] = round((c[1] - c[0]) / (w[1] - w[0]), 2) if w[1] > w[0] else None
    out["difference_weighted"] = round(weighted_share(fo, n, idx, weights) - weighted_share(ft, n, idx, weights), 4)
    out["difference_interval"] = boot_interval(
        lambda s: weighted_share(fo, n, s, weights) - weighted_share(ft, n, s, weights), idx, rng)

    def ratio(s):
        a = sum(fo[ix].sum() for ix in s.values())
        b = sum(ft[ix].sum() for ix in s.values())
        return a / b if b else np.nan
    out["ratio_found"] = round(float(fo.sum() / ft.sum()), 3) if ft.sum() else None
    out["ratio_interval"] = boot_interval(ratio, idx, rng) if ft.sum() else None
    xo, xt = false["ours"][co], false["turboseti"][ct]
    out["false_a_block"] = [round(weighted_mean(xo, idx, weights), 4), round(weighted_mean(xt, idx, weights), 4)]
    out["false_difference"] = round(weighted_mean(xo - xt, idx, weights), 4)
    if xo.sum() == 0 and xt.sum() == 0:
        out["false_difference_interval"] = None
        out["false_difference_note"] = ("no false candidate in either: says nothing about a difference in the "
                                        "underlying rates; each rate's own upper bound is in the published curves")
    else:
        out["false_difference_interval"] = boot_interval(lambda s: weighted_mean(xo - xt, s, weights), idx, rng)
    out["false_blocks_with_any"] = [int((xo > 0).sum()), int((xt > 0).sum())]
    return out


def _selection(weights, classes, n, found, false, rng, boot=BOOT):
    idx = class_index(classes)
    grids = {p: sorted(found[p], key=float) for p in found}
    chosen = {p: {} for p in found}
    diffs = []
    for _ in range(boot):
        s = resample(idx, rng)
        pick = {}
        for p in found:
            rates = [weighted_mean(false[p][c], s, weights) for c in grids[p]]
            pick[p] = choose_cut(rates, grids[p])
            chosen[p][str(pick[p])] = chosen[p].get(str(pick[p]), 0) + 1
        if pick["ours"] is not None and pick["turboseti"] is not None:
            diffs.append(weighted_share(found["ours"][pick["ours"]], n, s, weights)
                         - weighted_share(found["turboseti"][pick["turboseti"]], n, s, weights))
    full = {p: choose_cut([weighted_mean(false[p][c], idx, weights) for c in grids[p]], grids[p]) for p in found}
    out = {"resamples": boot, "chosen_on_all_blocks": full,
           "chosen": {p: dict(sorted(v.items(), key=lambda kv: -kv[1])) for p, v in chosen.items()},
           "both_chosen": len(diffs)}
    if diffs:
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        out["difference_at_chosen_cuts"] = {"median": round(float(np.median(diffs)), 4),
                                            "interval": [round(float(lo), 4), round(float(hi), 4)]}
    return out


def _correlation(blocks, classes, weights, n, found, false, co, ct, rng):
    d = (found["ours"][co] - found["turboseti"][ct]) / np.maximum(n, 1)
    return {"recovery_difference": {str(g): lag_correlation(blocks, d, g) for g in LAGS},
            "false_ours": {str(g): lag_correlation(blocks, false["ours"][co], g) for g in LAGS},
            "false_turboseti": {str(g): lag_correlation(blocks, false["turboseti"][ct], g) for g in LAGS},
            "difference_by_window": [window_interval(blocks, classes, found["ours"][co], found["turboseti"][ct], n,
                                                     weights, w, rng) for w in WINDOW_SIZES]}


def session(target, label, say=_say):
    rng = np.random.default_rng(SEED)
    sess, weights, blocks, classes, n, found, false = _arrays(target)
    pts = {"frozen (30 each)": ("30", "30")}
    full = {p: choose_cut([weighted_mean(false[p][c], class_index(classes), weights)
                           for c in sorted(found[p], key=float)], sorted(found[p], key=float)) for p in found}
    if full["ours"] is not None and full["turboseti"] is not None:
        pts["matched (step 4's rule, point rates)"] = (full["ours"], full["turboseti"])
    out = {"target": target, "session": sess, "label": label,
           "weights": {c: round(w, 4) for c, w in weights.items()},
           "points": {k: _at(target, weights, blocks, classes, n, found, false, co, ct, rng)
                      for k, (co, ct) in pts.items()},
           "selection": _selection(weights, classes, n, found, false, rng),
           "correlation": _correlation(blocks, classes, weights, n, found, false, "30", "30", rng)}
    f = out["points"]["frozen (30 each)"]
    say(f"{label}: at 30 found {f['ours']['found']} / {f['turboseti']['found']}; clustered/Wilson width "
        f"{f['ours']['width_ratio_clustered_to_wilson']} / {f['turboseti']['width_ratio_clustered_to_wilson']}; "
        f"difference {f['difference_weighted']} {f['difference_interval']}; ratio {f['ratio_found']} "
        f"{f['ratio_interval']}; false difference {f['false_difference']} {f['false_difference_interval']}")
    say(f"  selection: {out['selection']['chosen']}")
    return out


# --- coverage of the recovery intervals --------------------------------------------------

SCENARIOS = {
    "independent signals": {},
    "a shared block effect": {"block_sd": 1.0},
    "blocks correlated along frequency": {"block_sd": 1.0, "ar": 0.8},
    "unequal class sampling": {"block_sd": 0.7, "classes": (20, 60), "weights": (0.9, 0.1)},
    "rare recoveries": {"block_sd": 0.7, "base": -3.0},
    "each finds some the other misses": {"block_sd": 0.7, "discordant": True},
}


def simulate(rng, block_sd=0.0, ar=0.0, classes=(40, 40), weights=(0.5, 0.5), base=0.5, gap=1.0,
             discordant=False, per_block=110):
    """One synthetic experiment: per block, signals found by a and b, and the true values: the
    weighted difference in expected share and a's expected pooled share (over the block effect's
    distribution, not the realised effects). Paired: a and b see the same draw for each signal
    unless `discordant`, when each draws its own, so each finds some the other misses."""
    nb = sum(classes)
    cls = np.array([0] * classes[0] + [1] * classes[1])
    e = np.empty(nb)
    prev = rng.normal()
    for i in range(nb):
        prev = ar * prev + np.sqrt(1 - ar * ar) * rng.normal() if i else prev
        e[i] = block_sd * (prev if ar else rng.normal())
    offset = np.where(cls == 1, -1.0, 0.0)
    pa = 1 / (1 + np.exp(-(base + gap + offset + e)))
    pb = 1 / (1 + np.exp(-(base + offset + e)))
    u = rng.random((nb, per_block))
    v = rng.random((nb, per_block)) if discordant else u
    fa, fb = (u < pa[:, None]).sum(1), (v < pb[:, None]).sum(1)
    n = np.full(nb, per_block)
    labels = np.where(cls == 0, "clean", "crowded")
    w = {"clean": weights[0], "crowded": weights[1]}
    eff = block_sd * rng.normal(size=20000)
    ta, tb = {}, {}
    for k, c in enumerate(("clean", "crowded")):
        off = -1.0 if k else 0.0
        ta[c] = float((1 / (1 + np.exp(-(base + gap + off + eff)))).mean())
        tb[c] = float((1 / (1 + np.exp(-(base + off + eff)))).mean())
    truth = sum(w[c] * (ta[c] - tb[c]) for c in w)
    pooled_a = sum(classes[k] / nb * ta[c] for k, c in enumerate(("clean", "crowded")))
    return labels, fa, fb, n, w, truth, pooled_a


def coverage(trials=300, boot=400, seed=SEED, say=_say):
    """How often the block-clustered interval holds the true weighted difference, and Wilson's
    interval on a's pooled share holds its true pooled share, over synthetic experiments."""
    rng = np.random.default_rng(seed)
    out = {}
    for name, kw in SCENARIOS.items():
        hit_c = hit_w = 0
        errs = []
        for _ in range(trials):
            labels, fa, fb, n, w, truth, pooled_a = simulate(rng, **kw)
            idx = class_index(labels)
            est = weighted_share(fa, n, idx, w) - weighted_share(fb, n, idx, w)
            errs.append(est - truth)
            iv = boot_interval(lambda s: weighted_share(fa, n, s, w) - weighted_share(fb, n, s, w), idx, rng, boot)
            hit_c += iv[0] <= truth <= iv[1]
            lo, hi = measure.wilson(int(fa.sum()), int(n.sum()))
            hit_w += lo <= pooled_a <= hi
        out[name] = {"trials": trials, "clustered_difference_coverage": round(hit_c / trials, 3),
                     "wilson_share_coverage": round(hit_w / trials, 3),
                     "bias": round(float(np.mean(errs)), 4), "rmse": round(float(np.sqrt(np.mean(np.square(errs)))), 4)}
        say(f"{name}: clustered {out[name]['clustered_difference_coverage']}, Wilson "
            f"{out[name]['wilson_share_coverage']}, bias {out[name]['bias']}")
    return out


def window_coverage(trials=200, boot=300, seed=SEED, ars=(0.5, 0.8, 0.95), ws=(1, 4, 8, 16), classes=(60, 60),
                    say=_say):
    """The stratified window bootstrap's coverage of the true weighted difference, blocks correlated
    along frequency (AR(1) block effects, block numbers in order), by window length."""
    rng = np.random.default_rng(seed)
    out = {}
    for ar in ars:
        hits = {w: 0 for w in ws}
        for _ in range(trials):
            labels, fa, fb, n, wts, truth, _ = simulate(rng, block_sd=1.0, ar=ar, classes=classes)
            blocks = list(range(len(labels)))
            for w in ws:
                iv = window_interval(blocks, list(labels), fa, fb, n, wts, w, rng, boot)["interval"]
                hits[w] += iv[0] <= truth <= iv[1]
        out[str(ar)] = {str(w): {"coverage": round(hits[w] / trials, 3),
                                 "windows_a_class": -(-classes[0] // w)} for w in ws}
        say(f"windows, AR {ar}: " + ", ".join(f"{w}: {out[str(ar)][str(w)]['coverage']}" for w in ws))
    return out


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    rec = {"kind": "measured", "seed": SEED, "boot": BOOT, "rate": RATE,
           "between_sessions": "three sessions from one telescope, reported side by side; no interval over "
                               "sessions is given: too few to estimate between-session variation"}
    if what in ("all", "sessions"):
        rec["sessions"] = [session(t, label) for t, _, label in SESSIONS]
    if what in ("all", "coverage"):
        rec["coverage"] = coverage()
        rec["window_coverage"] = window_coverage()
    yoke.write(OUT if what == "all" else OUT.with_name(f"statistical_checks_{what}.json"), rec, indent=1, stamp=True)


if __name__ == "__main__":
    main()
