"""The checks on the curved second pass's candidates, broken down from the
records `curved_pass.py vet` already wrote (nothing is re-run or read again
but the files' chunk indexes, for the frequencies):

- planted signals inside and outside check 3's known interference bands:
  how many the search recovers (detection) and how many of those the full
  checks leave unexplained (vetting), apart;
- how far the tables depend on the reference look: for the signals only the
  pass recovers, and for the pass's wrong-choice candidates, the result
  under the strongest member look (as the tables use), under some member
  look, and under every member look.

    python tools/vet_breakdown.py KIC8462852

Writes data/measurements/curved-pass-vetting-breakdown.json. A separate
tool so that nothing step 10 fingerprints changes."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import curved_pass  # noqa: E402
import matched  # noqa: E402
import seti  # noqa: E402
import store  # noqa: E402
import vetting  # noqa: E402
import yoke  # noqa: E402

CUTS = ("30", "10")
CURVED_FROM = 1e-4
PASS = curved_pass.key(1e-3)


def in_band(f):
    return any(lo <= f <= hi for lo, hi, _ in vetting.BANDS)


def frequencies(urls, k, tones):
    """Each planted signal's frequency at the first look, MHz: the block's
    slice starts where read_looks starts it."""
    index = seti.reading.prepare(urls[:1])[0]
    a = index["attrs"]
    fch1, foff = float(a["fch1"]), float(a["foff"])
    low, high = seti.blocks(index)[k]
    first = seti.channels(fch1, foff, int(a.get("nchans", index["shape"][2])), low, high)[0]
    return [fch1 + (first + t["x0"]) * foff for t in tones]


def survives(v):
    return curved_pass.rank(v) < 2


def run(target, say=print):
    db = store.connect()
    session, urls = store.cadence_files(db, target)
    db.close()
    recs = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(curved_pass.vet_folder(target, session).glob("block_*.json"))]
    recs = [r for r in recs if r.get("format") == 2]
    out = {"target": target, "session": session, "blocks": len(recs), "pass": PASS, "curved_from": CURVED_FROM}
    for c in CUTS:
        cell = {}
        for r in recs:
            fs = frequencies(urls, r["block"], r["tones"])
            for t, f in zip(r["tones"], fs):
                curved = abs(t["accel"]) >= CURVED_FROM - 1e-12
                for cfg in ("production", PASS):
                    for kind in ("all", "curved" if curved else "straight"):
                        x = t["vet"][c][cfg]
                        d = cell.setdefault(f"{cfg} {kind}", {}).setdefault("in bands" if in_band(f) else "outside",
                                                                         {"planted": 0, "recovered": 0, "survive": 0})
                        d["planted"] += 1
                        if x["three_looks"] == "recovered":
                            d["recovered"] += 1
                            d["survive"] += survives(x["store"])
        out[f"cut_{c}_bands"] = cell

        # the reference look: signals only the pass recovers
        only = {"signals": 0, "strongest": 0, "some_reference": 0, "every_reference": 0}
        for r in recs:
            for t in r["tones"]:
                x = t["vet"][c][PASS]
                if x["three_looks"] != "recovered" or x.get("by") != ["pass"] or not x.get("store_by_reference"):
                    continue
                refs = x["store_by_reference"]
                only["signals"] += 1
                only["strongest"] += survives(x["store"])
                only["some_reference"] += any(survives(v) for d in refs for v in d.values())
                only["every_reference"] += any(all(survives(v) for v in d.values()) for d in refs)
        # the pass's wrong-choice candidates, by distinct signal (shared member hits)
        rows = [x for r in recs for rr in r["false"][c].values() for x in rr if x["by"] == "pass"]
        fa = {"candidates": len(rows), "distinct": len(matched.shared_hits({"_": rows})),
              "unexplained_strongest": len(matched.shared_hits({"_": [x for x in rows
                                                                     if survives(x["store"]["verdict"])]})),
              "unexplained_some_reference": len(matched.shared_hits({"_": [
                  x for x in rows if any(survives(v) for v in x["store"]["by_reference"].values())]}))}
        out[f"cut_{c}_reference"] = {"pass_only_planted": only, "pass_wrong_choices": fa}

    yoke.write(yoke.DATA / "measurements" / "curved-pass-vetting-breakdown.json",
               dict(out, kind="measured", experimental=True), stamp=True)
    for c in CUTS:
        say(f"cut {c}: planted / recovered / survive the full checks, inside and outside the known bands")
        for k, v in out[f"cut_{c}_bands"].items():
            say(f"  {k:>22}: " + "; ".join(f"{b} {d['planted']} / {d['recovered']} / {d['survive']}"
                                           for b, d in sorted(v.items())))
        ref = out[f"cut_{c}_reference"]
        say(f"  reference look, signals only the pass recovers: {ref['pass_only_planted']}")
        say(f"  reference look, the pass's wrong choices: {ref['pass_wrong_choices']}")
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("target")
    run(p.parse_args().target)
