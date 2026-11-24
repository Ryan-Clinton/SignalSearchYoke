"""The rule of docs/control-c.md applied: is the candidate version 6 of the checks adopted? Written and committed
before any of control C's results existed.

    python tools/control_c_verdict.py

Reads control C's planted-signal records (both versions' verdicts on every planted candidate), its store (both
versions' verdicts on every real candidate) and its sweep records; writes
data/analysis/negative_controls_c/verdict.json.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import yoke  # noqa: E402

SEED = 20261125
BOOT = 4000
CUT = 30
LIMIT_RATE, LIMIT_UPPER, RUN = 0.02, 0.05, 16


def _block_sums(records, cut=CUT):
    """[[unexplained by 5, unexplained by 6, candidates, counted]] a block, and each block's class."""
    import control_injection as ci
    rows, classes = [], []
    for r in records:
        a, b = ci.stage_counts(r["tones"], cut), ci.stage_counts(r["tones"], cut, "verdict_context")
        rows.append([a["unexplained"], b["unexplained"], a["candidates"], a["counted"]])
        classes.append(r["class"])
    return np.array(rows, float), np.array(classes)


def paired_difference(rows, classes, w_capped=None, only=None, seed=SEED, boot=BOOT):
    """Version 6's share unexplained among planted candidates minus version 5's, with a 95% interval over blocks
    drawn again (within each class when weighted). `only`: one class; `w_capped`: the classes combined by that
    share of capped blocks."""
    rng = np.random.default_rng(seed)
    groups = {c: rows[classes == c] for c in ("complete", "capped")}

    def diff(g):
        if only is not None:
            x = g[only].sum(axis=0)
            return (x[1] - x[0]) / x[2] if x[2] else np.nan
        w = {"complete": 1 - w_capped, "capped": w_capped}
        sums = {c: x.sum(axis=0) for c, x in g.items()}
        if any(not s[3] for s in sums.values()):
            return np.nan
        u5 = sum(w[c] * sums[c][0] / sums[c][3] for c in w)
        u6 = sum(w[c] * sums[c][1] / sums[c][3] for c in w)
        k = sum(w[c] * sums[c][2] / sums[c][3] for c in w)
        return (u6 - u5) / k if k else np.nan
    point = diff(groups)
    draws = np.array([diff({c: x[rng.integers(0, len(x), len(x))] for c, x in groups.items()}) for _ in range(boot)])
    draws = draws[~np.isnan(draws)]
    if np.isnan(point) or len(draws) < boot / 2:
        return None
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"difference": round(float(point), 4), "interval": [round(float(lo), 4), round(float(hi), 4)]}


def false_rate(per_session, run=RUN):
    """Real candidates left unexplained a block over all cadences (per_session: each cadence's counts a block in
    frequency order), and the 95% interval from runs of `run` consecutive blocks drawn again."""
    import negative_controls as nc
    total, blocks = sum(sum(x) for x in per_session), sum(len(x) for x in per_session)
    return {"unexplained": int(total), "blocks": blocks, "rate": round(total / blocks, 4),
            "interval": nc._windows95(per_session, run)}


def decide(capped, weighted, rate):
    keeps = bool(capped and weighted and capped["interval"][0] > 0 and weighted["interval"][0] > 0)
    clean = bool(rate["rate"] <= LIMIT_RATE and rate["interval"] is not None and rate["interval"][1] <= LIMIT_UPPER)
    return {"keeps_more_real_signals": keeps, "lets_no_more_interference_through": clean,
            "adopted": keeps and clean,
            "so": "version 6 becomes the checks' next version" if keeps and clean else "version 5 stays"}


def main(say=print):
    os.environ["SSY_CONTROL"] = "c"          # before the tools are imported: their paths are control C's
    import control_injection as ci
    import negative_controls as nc
    import vetting
    choice = json.loads((ci.OUT / "choice.json").read_text(encoding="utf-8"))
    control = nc._whole_control()
    problems = ci.choice_problems(choice, control)
    if problems:
        raise yoke.Refusal("INVALID_REQUEST", problems[0])
    records = ci.load_records(choice, ci._versions_now())
    if any("verdict_context" not in t["at"][str(CUT)] for r in records for t in r["tones"]
           if t["at"][str(CUT)].get("verdict")):
        raise yoke.Refusal("INVALID_REQUEST", "A planted candidate has no verdict by version 6.")
    rows, classes = _block_sums(records)
    capped_share = sum(d.get("complete") not in (1, True) for _, rec in control for d in rec["done"].values()) / sum(
        len(rec["done"]) for _, rec in control)
    capped = paired_difference(rows, classes, only="capped")
    weighted = paired_difference(rows, classes, w_capped=capped_share)
    db = nc._store()
    try:
        events = nc.candidate_verdicts(db, vetting.VERSION_BANDS_AS_CONTEXT, vetting.N_CHECKS)
    finally:
        db.close()
    left = {}
    for e in events:
        if e["snr"] >= CUT and nc.verdict_class(e["verdict"]).startswith("unexplained"):
            left[(e["session"], e["block"])] = left.get((e["session"], e["block"]), 0) + 1
    per_session = [[left.get((c["session"], k), 0) for k in range(len(rec["blocks"]))] for c, rec in control]
    rate = false_rate(per_session)
    out = {"rule": "docs/control-c.md", "cut": CUT, "share_of_blocks_capped": round(capped_share, 4),
           "planted_capped": capped, "planted_weighted": weighted, "real_unexplained_by_version_6": rate,
           "limits": {"rate": LIMIT_RATE, "upper": LIMIT_UPPER, "run": RUN}, **decide(capped, weighted, rate),
           "kind": "measured"}
    yoke.write(nc.OUT / "verdict.json", out, indent=1, stamp=True)
    say(json.dumps({k: out[k] for k in ("planted_capped", "planted_weighted", "real_unexplained_by_version_6", "so")}))
    return out


if __name__ == "__main__":
    main()
