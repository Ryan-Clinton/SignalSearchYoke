"""Recovery against false candidates at every tested cut, for each session
(supplementary and exploratory: the frozen verdicts of steps 10 and 12 stay
as they are). From the per-block records and each session's tables record,
nothing searched again:

- for each pipeline and each cut: the wrong-choice false-candidate rate a
  block (the tables' own, with its interval) and the planted signals found
  in all three ON looks;
- the operating points: the frozen cut (30 each), the published one (10
  each), and the lowest tested cut of each whose rate's point estimate is
  at most 0.1 (its interval may reach above it);
- at each operating point, the paired difference in share on the same
  signals, with a block bootstrap, and again with blocks resampled in runs
  of 4 and 16 adjacent blocks, to show how much the interval rests on
  treating neighbouring blocks as independent.

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
RATE = 0.1
RUNS = (1, 4, 16)
BOOT = 4000
SEED = 2


def _paired(by_block, run, seed=SEED, boot=BOOT):
    """Paired difference in share, blocks (in frequency order) resampled in runs of `run` adjacent ones."""
    groups = [by_block[i:i + run] for i in range(0, len(by_block), run)]
    d = np.array([sum(int(a) - int(b) for blk in g for a, b in blk) for g in groups], float)
    n = np.array([sum(len(blk) for blk in g) for g in groups], float)
    rng = np.random.default_rng(seed)
    draws = [d[i].sum() / n[i].sum() for i in (rng.integers(0, len(groups), len(groups)) for _ in range(boot))]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"runs_of": run, "groups": len(groups), "difference": round(float(d.sum() / n.sum()), 4),
            "interval": [round(float(lo), 4), round(float(hi), 4)]}


def session(target, record, label):
    tables = json.loads((yoke.DATA / "measurements" / record).read_text(encoding="utf-8"))
    _, _, recs = matched_tables.load(target)
    recs = sorted(recs, key=lambda r: r["from_mhz"])
    tones = [t for r in recs for t in r["tones"]]
    curves = {}
    for p, grid in (("ours", matched.CUTS_OURS), ("turboseti", matched.CUTS_TURBO)):
        curves[p] = {}
        for c in grid:
            fc = tables["false_curves"][p][matched.ck(c)]
            curves[p][matched.ck(c)] = {
                "false_per_block": fc["per_block"], "interval": fc["interval"],
                "found": sum(matched_tables._got(t, p, c, "three_looks") for t in tones)}

    def lowest(p):
        ok = [c for c, v in curves[p].items() if v["false_per_block"] <= RATE]
        return min(ok, key=float) if ok else None

    points = {"frozen (30 each)": ("30", "30"), "published (10 each)": ("10", "10"),
              "lowest cut with point estimate at most 0.1": (lowest("ours"), lowest("turboseti"))}
    out_points = {}
    for name, (co, ct) in points.items():
        if co is None or ct is None:
            out_points[name] = {"cuts": [co, ct], "note": "no tested cut reaches 0.1 for "
                                + ("this search" if co is None else "turboSETI")}
            continue
        by_block = [[(matched_tables._got(t, "ours", float(co), "three_looks"),
                      matched_tables._got(t, "turboseti", float(ct), "three_looks")) for t in r["tones"]]
                    for r in recs]
        fo, ft = curves["ours"][co], curves["turboseti"][ct]
        out_points[name] = {
            "cuts": [co, ct], "found": [fo["found"], ft["found"]],
            "ratio": round(fo["found"] / ft["found"], 2) if ft["found"] else None,
            "false_per_block": [fo["false_per_block"], ft["false_per_block"]],
            "false_intervals": [fo["interval"], ft["interval"]],
            "paired": [_paired(by_block, k) for k in RUNS]}
    return {"target": target, "session": tables["session"], "label": label, "blocks": len(recs),
            "signals": len(tones), "classes": tables.get("classes"), "curves": curves, "points": out_points}


def main():
    rec = {"rate": RATE, "how": "supplementary and exploratory; the frozen verdicts are unchanged",
           "sessions": [session(*s) for s in SESSIONS], "kind": "measured"}
    yoke.write(yoke.DATA / "analysis" / "operating_points.json", rec, indent=1, stamp=True)
    for s in rec["sessions"]:
        print(f"{s['target']} ({s['label']}), {s['signals']} signals in {s['blocks']} blocks:")
        for name, p in s["points"].items():
            if "found" not in p:
                print(f"  {name}: {p['note']}")
                continue
            pr = {x["runs_of"]: x["interval"] for x in p["paired"]}
            print(f"  {name}: cuts {p['cuts']}, found {p['found']} (x{p['ratio']}), false {p['false_per_block']}; "
                  f"paired {p['paired'][0]['difference']:+.3f}, intervals by runs of 1/4/16: {pr}")


if __name__ == "__main__":
    main()
