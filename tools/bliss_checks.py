"""Checks of the BLISS comparison (the BLISS audit, docs/audits.md 7).
Supplementary: the published comparison (matched-bliss.json, its pages and
step 11) is unchanged.

    python tools/bliss_checks.py events    two-ON against three-ON events, from the records
    python tools/bliss_checks.py pins      every BLISS record's provenance against matched.BLISS_PINS

- **events**: BLISS's event stage keeps an event with a hit in at least two
  ON looks (event_search.cpp at 2b98afe, as ported); this search's recovery
  standard needs all three. From the 2017 records: BLISS's false candidates
  (the 19 wrong choices, distinct by shared hits, weighted by class) counted
  from all its events, from those with exactly two ON hits and from those
  with three, at each cut; and the matched cut by step 4's rule if only
  three-ON events counted. Planted signals are credited only by three-ON
  events already, so recovery does not change.
- **pins**: matched.BLISS_PINS (the pinned checkout, local change and response
  file) against each record's provenance, plain and planted.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matched  # noqa: E402
import matched_tables  # noqa: E402
import yoke  # noqa: E402

OUT = yoke.DATA / "analysis"
TARGET = "KIC8462852"


def _say(*a):
    print(*a, flush=True)


def _records():
    session, meta, _ = matched_tables.load(TARGET)
    folder = matched.bliss_folder(TARGET, session)
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("block_*.json"))]
    total = meta["of"]["clean"] + meta["of"]["crowded"]
    return session, [r for r in recs if "failed" not in r], {c: meta["of"][c] / total for c in ("clean", "crowded")}


def _rate(recs, weights, count):
    out = 0.0
    for cls in ("clean", "crowded"):
        rs = [r for r in recs if r["class"] == cls]
        if rs:
            out += weights[cls] * sum(count(r) for r in rs) / len(rs)
    return out


def events(say=_say):
    session, recs, weights = _records()
    rows = {}
    for c in matched.CUTS_BLISS:
        k = matched.ck(c)

        def count(r, keep):
            return len(matched.shared_hits({ch: [e for e in evs if keep(len(e["members"]))]
                                            for ch, evs in r["false"].get(k, {}).items()}))
        rows[k] = {"all": round(_rate(recs, weights, lambda r: count(r, lambda n: True)), 4),
                   "exactly_two_on": round(_rate(recs, weights, lambda r: count(r, lambda n: n == 2)), 4),
                   "three_on": round(_rate(recs, weights, lambda r: count(r, lambda n: n >= 3)), 4)}
    curve = {k: {"per_block": v["three_on"], "interval": [v["three_on"], v["three_on"]]} for k, v in rows.items()}
    cut3 = matched_tables._matched_cut(curve)["cut"]
    found3 = None
    if cut3 is not None:
        found3 = sum(t["bliss"][cut3].get("three_looks") == "recovered" for r in recs for t in r["tones"])
    rec = {"target": TARGET, "session": session, "blocks": len(recs), "false_a_block": rows,
           "matched_cut_three_on_only": cut3, "found_at_that_cut": found3,
           "note": "point estimates (the intervals are the published curves'); planted signals are credited by "
                   "three-ON events only, so recovery is the same either way", "kind": "measured"}
    yoke.write(OUT / "bliss_events_two_three.json", rec, indent=1, stamp=True)
    for k, v in rows.items():
        say(f"cut {k}: all {v['all']}, two ON {v['exactly_two_on']}, three ON {v['three_on']}")
    say(f"matched cut with three-ON events only: {cut3}, found {found3}")
    return rec


def pins(say=_say):
    session, recs, _ = _records()
    bad = []
    for r in recs:
        for part, pv in r.get("provenance", {}).items():
            pr = matched.bliss_pins_problems(pv or {})
            if pr:
                bad.append({"block": r["block"], "part": part, "problems": pr})
    rec = {"target": TARGET, "session": session, "records": len(recs), "runs_checked": 2 * len(recs),
           "pins": matched.BLISS_PINS, "differing": bad, "kind": "measured"}
    yoke.write(OUT / "bliss_pins.json", rec, indent=1, stamp=True)
    say(f"pins: {2 * len(recs)} runs checked, {len(bad)} differing")
    return rec


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "events"
    {"events": events, "pins": pins}[what]()


if __name__ == "__main__":
    main()
