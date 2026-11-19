"""Recovery against false candidates at every tested cut, for each session
(supplementary and exploratory: the frozen verdicts of steps 10 and 12 stay
as they are). From the per-block records and each session's tables record,
nothing searched again:

- for each pipeline and each cut: the wrong-choice false-candidate rate a
  block (the tables' own, weighted by each class's share of the session,
  with its interval) and the planted signals found in all three ON looks,
  as counted in the sample;
- the operating points: the frozen cut (30 each), the published one (10
  each), and each pipeline's matched cut by step 4's rule
  (matched_tables._matched_cut: the lowest cut from which the rate's point
  estimate stays at most 0.1 at every higher cut tested; its interval may
  reach above);
- at each operating point, the paired difference in share on the same
  signals, two ways:
  - **in the sample**, as the blocks were measured, with a bootstrap over
    blocks; and over windows of 4 and 16 consecutive blocks of the session
    (by block number, gaps of unmeasured blocks kept), to see how much the
    interval rests on neighbouring blocks being independent; the number of
    windows is given, and an interval from fewer than 20 is marked as such;
  - **weighted to the session**: each class's (clean, crowded) recovery and
    difference weighted by its share of the session's blocks, as the false
    rates are, with a bootstrap over blocks within each class (the sample
    was drawn by class). Where a session's sample over- or under-represents
    crowded blocks (2017: 61 of 121 against 61 of 308), the two differ.

Writes data/analysis/operating_points.json.

    python tools/operating_points.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matched  # noqa: E402
import matched_tables  # noqa: E402
import yoke  # noqa: E402

SESSIONS = (("KIC8462852", "matched.json", "2017, S band, cuts chosen on these blocks"),
            ("HIP17147", "matched-HIP17147.json", "2016, L band, fixed in advance (step 10)"),
            ("NGC6946", "matched-NGC6946.json", "2019, C band, fixed in advance (step 12)"))
WINDOWS = (1, 4, 16)        # consecutive blocks of the session in one resampled unit
FEW = 20                    # an interval from fewer windows than this is marked
BOOT = 4000
SEED = 2
CLASSES = ("clean", "crowded")


# --- the estimates (pure, tested in tests/test_operating_points.py) -------------------

def sample_difference(blocks):
    """Paired difference in share over the sample: blocks are
    [{"block", "class", "pairs": [(a, b), ...]}]."""
    d = sum(int(a) - int(b) for blk in blocks for a, b in blk["pairs"])
    n = sum(len(blk["pairs"]) for blk in blocks)
    return d / n if n else float("nan")


def weighted(blocks, weights):
    """Each class's share found by a and b, and their difference, weighted
    by the class's share of the session: (share a, share b, difference).
    A class with no measured block counts nothing, and the weights of the
    rest are not stretched to cover it (it is reported absent)."""
    sa = sb = 0.0
    for c in CLASSES:
        pairs = [p for blk in blocks if blk["class"] == c for p in blk["pairs"]]
        if not pairs:
            continue
        sa += weights[c] * sum(int(a) for a, _ in pairs) / len(pairs)
        sb += weights[c] * sum(int(b) for _, b in pairs) / len(pairs)
    return sa, sb, sa - sb


def windows(blocks, k):
    """Blocks grouped by window of k consecutive blocks of the session (block number // k)."""
    out = {}
    for blk in blocks:
        out.setdefault(blk["block"] // k, []).append(blk)
    return [out[w] for w in sorted(out)]


def bootstrap_sample(blocks, k, seed=SEED, boot=BOOT):
    """The sample difference, windows of k blocks resampled whole."""
    groups = windows(blocks, k)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(boot):
        pick = [blk for i in rng.integers(0, len(groups), len(groups)) for blk in groups[i]]
        draws.append(sample_difference(pick))
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"windows_of": k, "windows": len(groups), "difference": round(sample_difference(blocks), 4),
            "interval": [round(float(lo), 4), round(float(hi), 4)], "few_windows": len(groups) < FEW}


def bootstrap_weighted(blocks, weights, seed=SEED, boot=BOOT):
    """The weighted difference, blocks resampled within each class."""
    by = {c: [b for b in blocks if b["class"] == c] for c in CLASSES}
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(boot):
        pick = [bs[i] for c, bs in by.items() if bs for i in rng.integers(0, len(bs), len(bs))]
        draws.append(weighted(pick, weights)[2])
    lo, hi = np.percentile(draws, [2.5, 97.5])
    a, b, d = weighted(blocks, weights)
    return {"share": [round(a, 4), round(b, 4)], "difference": round(d, 4),
            "interval": [round(float(lo), 4), round(float(hi), 4)],
            "classes_absent": [c for c, bs in by.items() if not bs and weights[c] > 0]}


# --- the sessions ----------------------------------------------------------------------

def session(target, record, label):
    tables = json.loads((yoke.DATA / "measurements" / record).read_text(encoding="utf-8"))
    _, meta, recs = matched_tables.load(target)
    total = meta["of"]["clean"] + meta["of"]["crowded"]
    weights = {c: meta["of"][c] / total for c in CLASSES}
    tones = [t for r in recs for t in r["tones"]]
    curves = {}
    for p, grid in (("ours", matched.CUTS_OURS), ("turboseti", matched.CUTS_TURBO)):
        curves[p] = {}
        for c in grid:
            fc = tables["false_curves"][p][matched.ck(c)]
            curves[p][matched.ck(c)] = {
                "false_per_block": fc["per_block"], "interval": fc["interval"],
                "found": sum(matched_tables._got(t, p, c, "three_looks") for t in tones)}

    def rule(p):
        return matched_tables._matched_cut({c: {"per_block": v["false_per_block"], "interval": v["interval"]}
                                            for c, v in curves[p].items()})["cut"]

    points = {"frozen (30 each)": ("30", "30"), "published (10 each)": ("10", "10"),
              "matched (step 4's rule)": (rule("ours"), rule("turboseti"))}
    out_points = {}
    for name, (co, ct) in points.items():
        if co is None or ct is None:
            out_points[name] = {"cuts": [co, ct], "note": "no matched cut for "
                                + ("this search" if co is None else "turboSETI")}
            continue
        blocks = [{"block": int(r["block"]), "class": r["class"],
                   "pairs": [(matched_tables._got(t, "ours", float(co), "three_looks"),
                              matched_tables._got(t, "turboseti", float(ct), "three_looks")) for t in r["tones"]]}
                  for r in recs]
        fo, ft = curves["ours"][co], curves["turboseti"][ct]
        out_points[name] = {
            "cuts": [co, ct], "found": [fo["found"], ft["found"]],
            "ratio": round(fo["found"] / ft["found"], 2) if ft["found"] else None,
            "false_per_block": [fo["false_per_block"], ft["false_per_block"]],
            "false_intervals": [fo["interval"], ft["interval"]],
            "sample": [bootstrap_sample(blocks, k) for k in WINDOWS],
            "weighted": bootstrap_weighted(blocks, weights)}
    return {"target": target, "session": tables["session"], "label": label, "blocks": len(recs),
            "of": meta["of"], "weights": {c: round(w, 4) for c, w in weights.items()},
            "sampled": {c: sum(r["class"] == c for r in recs) for c in CLASSES},
            "signals": len(tones), "curves": curves, "points": out_points}


def main():
    rec = {"rate": matched_tables.RATE, "how": "supplementary and exploratory; the frozen verdicts are unchanged",
           "sessions": [session(*s) for s in SESSIONS], "kind": "measured"}
    yoke.write(yoke.DATA / "analysis" / "operating_points.json", rec, indent=1, stamp=True)
    for s in rec["sessions"]:
        print(f"{s['target']} ({s['label']}): {s['signals']} signals in {s['blocks']} blocks, sampled "
              f"{s['sampled']} of {s['of']}")
        for name, p in s["points"].items():
            if "found" not in p:
                print(f"  {name}: {p['note']}")
                continue
            sm = "; ".join(f"windows of {x['windows_of']} ({x['windows']}): {x['interval']}" for x in p["sample"])
            wt = p["weighted"]
            print(f"  {name}: cuts {p['cuts']}, found {p['found']} (x{p['ratio']}); sample "
                  f"{p['sample'][0]['difference']:+.3f} [{sm}]; weighted shares {wt['share']}, "
                  f"{wt['difference']:+.3f} {wt['interval']}")


if __name__ == "__main__":
    main()
