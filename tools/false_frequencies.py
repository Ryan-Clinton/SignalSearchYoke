"""Where a matched run's false candidates are, by their own frequencies, not
their blocks': each distinct false candidate (the wrong choices' candidates
joined by shared hits, as the rates count them) at a cut, its frequency and
drift from its member hits, and whether that frequency lies inside one of
check 3's listed bands (vetting.BANDS), in a block that overlaps one, or in
a block that overlaps none. Reads matched.py's block records only.

A frequency inside a listed band is not an identification: it says the
candidate is where such transmitters are, not that it is one of them.

    python tools/false_frequencies.py HIP17147 [--cut 30] [--block 119]

--block lists that block's candidates whole (members and tracks), for a
look at their paths. Writes data/measurements/false-frequencies-TARGET.json."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matched  # noqa: E402
import store  # noqa: E402
import vetting  # noqa: E402
import yoke  # noqa: E402


def band_of(f):
    return next((name for lo, hi, name in vetting.BANDS if lo <= f <= hi), None)


def run(target, cut="30", block=None, say=print):
    db = store.connect_readonly()
    session, _ = store.cadence_files(db, target)
    db.close()
    recs = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(matched.folder(target, session).glob("block_*.json"))]
    recs = [r for r in recs if r.get("format") == 2]
    rows, whole = [], []
    for r in recs:
        lo, hi = r["from_mhz"], r["to_mhz"]
        overlaps = [n for a, b, n in vetting.BANDS if a <= hi and b >= lo]
        for group in matched.shared_hits(r["ours"]["false"][cut]):
            members = [m for ev in group for m in ev["members"]]
            f = sorted(m[2] for m in members)[len(members) // 2]
            drift = sorted(m[3] for m in members)[len(members) // 2]
            name = band_of(f)
            rows.append({"block": r["block"], "class": r["class"], "f_mhz": round(f, 6), "drift": drift,
                         "snr": max(ev["snr"] for ev in group), "candidates": len(group),
                         "where": "inside a listed band" if name else
                                  ("in a block overlapping one" if overlaps else "in a block overlapping none"),
                         "band": name or (overlaps[0] if overlaps else None)})
            if block is not None and r["block"] == block:
                whole.append(group)
    out = {"target": target, "session": session, "cut": cut, "blocks": len(recs), "distinct": len(rows),
           "by_where": {}, "by_band": {}, "rows": rows}
    for x in rows:
        out["by_where"][x["where"]] = out["by_where"].get(x["where"], 0) + 1
        if x["where"] == "inside a listed band":
            out["by_band"][x["band"]] = out["by_band"].get(x["band"], 0) + 1
    if block is not None:
        out[f"block_{block}"] = whole
    yoke.write(yoke.DATA / "measurements" / f"false-frequencies-{target}.json", dict(out, kind="measured"),
               stamp=True)
    say(f"{target} {session}, cut {cut}: {len(rows)} distinct false candidates in {len(recs)} blocks")
    for k, v in out["by_where"].items():
        say(f"  {k}: {v}")
    for k, v in sorted(out["by_band"].items(), key=lambda kv: -kv[1]):
        say(f"    {k}: {v}")
    if block is not None:
        say(f"block {block}: {len(whole)} distinct")
        for g in whole:
            ms = sorted({tuple(m) for ev in g for m in ev["members"]})
            say(f"  {len(g)} candidate(s); member hits (look, n, MHz, Hz/s): "
                + "; ".join(f"{m[0]} {m[2]:.6f} {m[3]:+.4f}" for m in ms))
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("target")
    p.add_argument("--cut", default="30")
    p.add_argument("--block", type=int)
    a = p.parse_args()
    run(a.target, a.cut, a.block)
