"""A6-08: the planted signals of the matched experiment scored at the middle of each look, beside the published
scoring at its start. A fast signal's frequency is measured where the search's track fits it best, near the look's
middle, so a small drift error moves the frequency at the start by drift error x half the look: the published
scoring then counts a detected signal as missed. This is a new scoring version beside the published tables, for
this search; no frozen verdict uses it.

    python tools/midlook.py run TARGET     each matched block read again, planted again, searched (resumes)
    python tools/midlook.py run TARGET --from-end   the same from the last block, for a second lane
    python tools/midlook.py tables         recovery as published, at mid-look, and at mid-look with tolerances
                                           that grow with drift (A6-05), by drift range

Each block plants the same signals as the matched run (the same seed), and the published scoring is recomputed
from the new search: a block counts only if it reproduces the record's published statuses exactly.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import yoke  # noqa: E402

OUT = yoke.DATA / "analysis" / "midlook"
CUTS = ("10", "30")
TARGETS = ("KIC8462852", "HIP17147", "NGC6946")
DC_BY_CHUNK = {"HIP17147"}          # its records were read under the earlier DC rule; read again the same way
READ_THREADS = 4                    # beside control C's sweep: fewer streams to the archive


def tolerances(drift, scaled):
    """(Hz, Hz/s): the published ±6 Hz, ±0.05 Hz/s, or with `scaled` growing with drift as A6-05 sets them."""
    import matched
    if not scaled:
        return matched.TOL_HZ, matched.TOL_DRIFT
    return max(matched.TOL_HZ, 10.0 * abs(drift)), max(matched.TOL_DRIFT, 0.08 * abs(drift))


def fit(t_f, t_drift, ev, half, tol):
    """How many of an event's ON members and measured tracks match a planted signal, of how many, comparing
    frequencies `half` seconds into each look (0: at its start, as published)."""
    looks = [m[:1] + m[2:4] for m in ev["members"]] + [x[:3] for x in ev.get("tracks", [])]
    ok = sum(abs(((f + d * half / 1e6) - (t_f[j] + t_drift * half / 1e6)) * 1e6) <= tol[0] and abs(d - t_drift) <= tol[1]
             for j, f, d in looks if j in t_f)
    return ok, len(looks)


def status(t_f, t_drift, planted, plain, half, tol):
    """As matched._status's three looks: recovered, a false association (the unplanted block had it), or None."""
    test = lambda ev: (lambda ok, n: ok == n == 3)(*fit(t_f, t_drift, ev, half, tol))  # noqa: E731
    if not any(test(ev) for ev in planted):
        return None
    return "false association" if any(test(ev) for ev in plain) else "recovered"


def score(tone, t_f, planted, plain, half):
    tol0, tol1 = tolerances(tone["drift"], False), tolerances(tone["drift"], True)
    return {"published": status(t_f, tone["drift"], planted, plain, 0.0, tol0),
            "mid": status(t_f, tone["drift"], planted, plain, half, tol0),
            "mid_scaled": status(t_f, tone["drift"], planted, plain, half, tol1)}


def one_block(target, k, rec, slices, urls):
    import matched
    import numpy as np
    cad = matched._cadence(slices, urls)
    ts = matched.tones(cad, np.random.default_rng([matched.SEED, k]))
    same = [(round(a["x0"], 6), round(a["drift"], 6), a["s_in"]) == (round(b["x0"], 6), round(b["drift"], 6), b["s_in"])
            for a, b in zip(ts, rec["tones"])]
    if len(ts) != len(rec["tones"]) or not all(same):
        raise yoke.Refusal("INTERNAL_ERROR", f"{target} block {k}: the signals planted again are not the record's")
    planted = matched.plant(cad, ts)
    cad_p = [dict(c, spectra=p["spectra"]) for c, p in zip(cad, planted)]
    kept = matched._ours_true(cad_p, matched.our_search(cad_p))
    s = cad[0]["s"]
    half = cad[0]["raw"].shape[0] * s["tsamp"] / 2
    rows, differ = [], []
    for i, (t, r) in enumerate(zip(ts, rec["tones"])):
        t_f = {j: matched.where(cad, t, j)[1] for j in matched.TRUE}
        at = {c: score(t, t_f, kept[c], rec["ours"]["true_plain"][c], half) for c in CUTS}
        for c in CUTS:
            if at[c]["published"] != r["ours"][c]["three_looks"]:
                differ.append([i, c, at[c]["published"], r["ours"][c]["three_looks"]])
        rows.append({"drift": t["drift"], "s_in": t["s_in"], "bin": t["bin"], "at": at})
    return {"target": target, "block": k, "class": rec["class"], "half_look_s": half, "tones": rows,
            "published_reproduced": not differ, "differ": differ[:20], "kind": "measured"}


def run(target, say=print, from_end=False):
    import matched
    import seti
    import store
    if target in DC_BY_CHUNK:
        os.environ["SSY_DC_BY_CHUNK"] = "1"
    seti.reading.set_threads(READ_THREADS)
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, target)
    db.close()
    base = matched.folder(target, session)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    out = OUT / target
    todo = []
    for p in sorted(base.glob("block_*.json")):
        k = int(p.stem.split("_")[1])
        if not yoke.whole(out / f"block_{k:03d}.json", lambda r: len(r.get("tones", [])) > 0):
            todo.append((k, p))
    say(f"{target}: {len(todo)} blocks to read again" + (", from the end" if from_end else ""))
    for k, p in (todo[::-1] if from_end else todo):
        # a second lane may work the same session from the other end: skip what it has finished
        if yoke.whole(out / f"block_{k:03d}.json", lambda r: len(r.get("tones", [])) > 0):
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        got = one_block(target, k, rec, seti.read_looks(urls, *block_list[k]), urls)
        yoke.write(out / f"block_{k:03d}.json", got, indent=None, stamp=True)
        n = lambda key, c: sum(t["at"][c][key] == "recovered" for t in got["tones"])  # noqa: E731
        say(f"  {target} block {k}: at 10, published {n('published', '10')}, mid {n('mid', '10')}, mid scaled "
            f"{n('mid_scaled', '10')}; reproduced {got['published_reproduced']}", flush=True)


def tables(say=print):
    import matched
    out = {"sessions": {}, "kind": "measured"}
    for target in TARGETS:
        recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((OUT / target).glob("block_*.json"))]
        if not recs:
            continue
        expected = len(list(matched.ROOT.glob(f"{target}-*/block_*.json")))
        bad = [r["block"] for r in recs if not r["published_reproduced"]]
        cell = {"blocks": len(recs), "of": expected, "not_reproduced": bad}
        good = [r for r in recs if r["published_reproduced"]]
        for c in CUTS:
            by = {}
            for r in good:
                for t in r["tones"]:
                    b = by.setdefault(str(t["bin"]), {"signals": 0, "published": 0, "mid": 0, "mid_scaled": 0})
                    b["signals"] += 1
                    for key in ("published", "mid", "mid_scaled"):
                        b[key] += t["at"][c][key] == "recovered"
            total = {key: sum(v[key] for v in by.values()) for key in ("signals", "published", "mid", "mid_scaled")}
            cell[f"at_{c}"] = {"by_drift_bin": dict(sorted(by.items())), "all": total}
        out["sessions"][target] = cell
    yoke.write(OUT / "tables.json", out, indent=1, stamp=True)
    for t, cell in out["sessions"].items():
        say(f"{t}: {cell['blocks']} of {cell['of']} blocks, not reproduced {cell['not_reproduced']}; at 10 "
            f"{cell['at_10']['all']}")
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "run" and len(sys.argv) > 2:
        run(sys.argv[2], from_end="--from-end" in sys.argv[3:])
    elif cmd == "tables":
        tables()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
