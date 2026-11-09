"""The tables of matched.py's run (comparable.md steps 4 and 7): each
pipeline's false candidates against its cut, the cut that gives the chosen
rate with its interval, and recovery at those cuts and at the published
ones. Written to data/measurements/matched.json and, as a page,
docs/results/TARGET-SESSION-matched.md."""
import json
import time

import numpy as np

import matched
import measure
import store
import yoke

RATE = 0.1                  # false candidates a block the cuts are matched at
BOOT = 4000


def load(target):
    db = store.connect()
    session, _ = store.cadence_files(db, target)
    db.close()
    base = matched.folder(target, session)
    meta = json.loads((base / "blocks.json").read_text(encoding="utf-8"))
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob("block_*.json"))]
    return session, meta, recs


def _counts(recs, get):
    """Distinct false signals in each block: get(rec) gives {choice: [MHz]}."""
    return [len(matched._distinct(f for v in get(r).values() for f in v)) for r in recs]


def _rate(recs, get, weights, rng):
    """Per block, by class and weighted by each class's share of all blocks,
    with a stratified bootstrap interval (the blocks the unit)."""
    by = {}
    for cls in ("clean", "crowded"):
        rs = [r for r in recs if r["class"] == cls]
        n = _counts(rs, get)
        lo, hi = measure.poisson_interval(sum(n))
        by[cls] = {"blocks": len(rs), "distinct": sum(n), "per_block": round(sum(n) / max(len(rs), 1), 4),
                   "interval": (round(lo / max(len(rs), 1), 4), round(hi / max(len(rs), 1), 4)), "_n": n}
    est = sum(weights[c] * by[c]["per_block"] for c in by)
    boots = []
    for _ in range(BOOT):
        boots.append(sum(weights[c] * (np.mean(rng.choice(by[c]["_n"], len(by[c]["_n"]))) if by[c]["_n"] else 0)
                         for c in by))
    for c in by:
        by[c].pop("_n")
    lo, hi = np.percentile(boots, [2.5, 97.5])
    # A count of zero bootstraps to zero: its upper bound from the Poisson interval instead.
    if hi == 0:
        hi = sum(weights[c] * by[c]["interval"][1] for c in by)
    return {"per_block": round(est, 4), "interval": (round(float(lo), 4), round(float(hi), 4)), **by}


def _matched_cut(curve):
    """The lowest cut whose rate is at most RATE; its interval: from the
    lowest cut whose interval reaches down to RATE to the lowest whose
    whole interval is under it."""
    cuts = sorted(curve, key=float)
    at = next((c for c in cuts if curve[c]["per_block"] <= RATE), None)
    lo = next((c for c in cuts if curve[c]["interval"][0] <= RATE), None)
    hi = next((c for c in cuts if curve[c]["interval"][1] <= RATE), None)
    return {"cut": at, "interval": (lo, hi)}


def _cell(tones, ok):
    n = len(tones)
    k = sum(ok(t) for t in tones)
    return {"planted": n, "recovered": k, "rate": round(k / n, 3) if n else None, "interval": measure.wilson(k, n)}


def recovery(tones, cuts):
    """By drift bin and S_in, each pipeline at its cut (cuts: {pipeline: cut};
    pickles: a level), with false associations apart."""
    def got(t, p):
        if p == "pickles":
            x = t["pickles"]["unmasked"]
            return x.get("level") is not None and x["level"] >= cuts[p] and \
                (x.get("level_before") is None or x["level_before"] < cuts[p])
        return t[p][matched.ck(cuts[p])]["status"] == "recovered"

    def false_assoc(t, p):
        if p == "pickles":
            x = t["pickles"]["unmasked"]
            return x.get("level") is not None and x["level"] >= cuts[p] and \
                x.get("level_before") is not None and x["level_before"] >= cuts[p]
        return t[p][matched.ck(cuts[p])]["status"] == "false association"
    out = []
    for b, (lo, hi) in enumerate(measure.DRIFT_BINS):
        for s in matched.STRENGTHS:
            cell = [t for t in tones if t["bin"] == b and t["s_in"] == s]
            if not cell:
                continue
            row = {"drift_hz_s": [lo, hi], "s_in": s, "flux_jy_hz": cell[0]["flux_jy_hz"]}
            for p in cuts:
                row[p] = _cell(cell, lambda t: got(t, p))
                row[p]["false_associations"] = sum(false_assoc(t, p) for t in cell)
            if "ours" in cuts and "turboseti" in cuts:
                row["ours_not_turboseti"] = sum(got(t, "ours") and not got(t, "turboseti") for t in cell)
                row["turboseti_not_ours"] = sum(got(t, "turboseti") and not got(t, "ours") for t in cell)
            out.append(row)
    return out


def s_in_at(tones, p, cut, share=0.8):
    """By drift bin, the lowest S_in at which at least `share` are recovered
    (and at every higher S_in)."""
    out = {}
    for b, (lo, hi) in enumerate(measure.DRIFT_BINS):
        best = None
        for s in sorted(matched.STRENGTHS, reverse=True):
            cell = [t for t in tones if t["bin"] == b and t["s_in"] == s]
            if not cell:
                continue
            rate = sum(t[p][matched.ck(cut)]["status"] == "recovered" for t in cell) / len(cell)
            if rate < share:
                break
            best = s
        out[f"{lo}-{hi}"] = best
    return out


def write(target, say=print):
    session, meta, recs = load(target)
    if not recs:
        raise yoke.Refusal("NOT_FOUND", "No block of matched.py's run is done.")
    rng = np.random.default_rng(1)
    total = meta["of"]["clean"] + meta["of"]["crowded"]
    weights = {c: meta["of"][c] / total for c in ("clean", "crowded")}
    curves = {"ours": {}, "turboseti": {}, "pickles": {}}
    for c in matched.CUTS_OURS:
        curves["ours"][matched.ck(c)] = _rate(recs, lambda r: r["ours"]["false"][matched.ck(c)], weights, rng)
    for c in matched.CUTS_TURBO:
        curves["turboseti"][matched.ck(c)] = _rate(recs, lambda r: r["turboseti"]["false"].get(matched.ck(c), {}),
                                                   weights, rng)
    for run in ("unmasked", "masked"):
        for level in ("1", "2"):
            curves["pickles"][f"{run} level {level}"] = _rate(recs, lambda r: r["pickles"]["false"][run][level],
                                                              weights, rng)
    checks = [c for r in recs for c in r["ours"]["checks_at_published_cut"]]
    cuts = {p: _matched_cut(curves[p]) for p in ("ours", "turboseti")}
    tones = [dict(t, cls=r["class"], block=r["block"]) for r in recs for t in r["tones"]]
    published = {"ours": matched.PUBLISHED["ours"], "turboseti": matched.PUBLISHED["turboseti"], "pickles": 1}
    at_matched = {p: float(cuts[p]["cut"]) for p in ("ours", "turboseti") if cuts[p]["cut"] is not None}
    record = {
        "target": target, "session": session, "blocks": len(recs),
        "classes": {c: sum(r["class"] == c for r in recs) for c in ("clean", "crowded")}, "of": meta["of"],
        "crowded_hits": meta["crowded_hits"], "rate_matched": RATE, "tolerances": [matched.TOL_HZ, matched.TOL_DRIFT],
        "false_curves": curves, "matched_cuts": cuts, "checks_on_false_at_published_cut": checks,
        "tones": len(tones),
        "recovery_published": {c: recovery([t for t in tones if c == "all" or t["cls"] == c], published)
                               for c in ("all", "clean", "crowded")},
        "recovery_matched": {c: recovery([t for t in tones if c == "all" or t["cls"] == c], at_matched)
                             for c in ("all", "clean", "crowded")} if at_matched else None,
        "s_in_80": {p: {"published": s_in_at(tones, p, published[p]),
                        "matched": s_in_at(tones, p, at_matched[p]) if p in at_matched else None}
                    for p in ("ours", "turboseti")},
        "offsets": {p: _offsets(tones, p, published[p]) for p in ("ours", "turboseti")},
        "incomplete_looks": sum(not x for r in recs for x in r["complete"]),
        "kind": "measured", "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    yoke.write(yoke.DATA / "measurements" / "matched.json", record, stamp=True)
    page = yoke.ROOT / "docs" / "results" / f"{target}-{session}-matched.md"
    page.write_text(markdown(record), encoding="utf-8")
    say(f"{page}: {len(recs)} blocks, {len(tones)} planted signals")
    return record


def _offsets(tones, p, cut):
    """How far the closest kept output was from each planted signal at S_in
    >= 60: whether the tolerances, not the detection, decide."""
    near = [t[p][matched.ck(cut)]["nearest"] for t in tones if t["s_in"] >= 60 and t[p][matched.ck(cut)]["nearest"]]
    if not near:
        return None
    df = np.array([abs(x["df_hz"]) for x in near])
    dd = np.array([abs(x["dd_hz_s"]) for x in near])
    return {"signals": len(near), "df_hz_median": round(float(np.median(df)), 2),
            "dd_hz_s_median": round(float(np.median(dd)), 4),
            "within_hz_only": int(((df <= matched.TOL_HZ) & (dd > matched.TOL_DRIFT)).sum()),
            "within_drift_only": int(((df > matched.TOL_HZ) & (dd <= matched.TOL_DRIFT)).sum())}


def _iv(x):
    return f"{x[0]:.3g}-{x[1]:.3g}"


def markdown(r):
    name = {"ours": "this search", "turboseti": "turboSETI", "pickles": "pickles"}
    out = [f"# {r['target']} {r['session']}: the pipelines at matched sensitivity", "",
           f"Written by `matched.py tables {r['target']}` from `matched.py run` (comparable.md steps 4 and 7); "
           "the record is data/measurements/matched.json.", "",
           f"{r['blocks']} blocks: {r['classes']['crowded']} crowded (more than {r['crowded_hits']} hits at this "
           f"search's cut in the six looks; all {r['of']['crowded']} there are) and {r['classes']['clean']} clean "
           f"(of {r['of']['clean']}, drawn at random). Rates over all blocks weight the two by their share of the "
           f"{r['of']['clean'] + r['of']['crowded']}.", "",
           "## False candidates against the cut", "",
           "Each block judged with the 19 wrong choices of three ON looks; distinct signals kept a block (one kept "
           "in several choices counts once), 95% intervals (all: stratified bootstrap over blocks; a class: "
           "Poisson on its count).", ""]
    for p in ("ours", "turboseti"):
        out += [f"**{name[p]}**", "", "| cut (its SNR) | all blocks | clean | crowded |", "|---|---|---|---|"]
        for c, v in sorted(r["false_curves"][p].items(), key=lambda x: float(x[0])):
            out.append(f"| {c} | {v['per_block']:.3g} ({_iv(v['interval'])}) | {v['clean']['per_block']:.3g} "
                       f"({_iv(v['clean']['interval'])}) | {v['crowded']['per_block']:.3g} "
                       f"({_iv(v['crowded']['interval'])}) |")
        m = r["matched_cuts"][p]
        out += ["", f"Cut for {r['rate_matched']} a block: {m['cut']} (interval {m['interval'][0]} to "
                f"{m['interval'][1]}).", ""]
    out += ["**pickles** (windows kept, by level; not an SNR cut)", "", "| run | all blocks | clean | crowded |",
            "|---|---|---|---|"]
    for k, v in r["false_curves"]["pickles"].items():
        out.append(f"| {k} | {v['per_block']:.3g} ({_iv(v['interval'])}) | {v['clean']['per_block']:.3g} | "
                   f"{v['crowded']['per_block']:.3g} |")
    ch = r["checks_on_false_at_published_cut"]
    out += ["", f"This search's false candidates at its published cut through the checks: {len(ch)} in all choices; "
            + ", ".join(f"{sum(str(c['verdict'] or '').startswith(w) for c in ch)} {w}"
                        for w in ("interference", "likely", "unexplained")) + ".", ""]
    out += ["## Recovery", "",
            f"{r['tones']} signals planted in the true ON looks only, matched in frequency and drift both "
            f"(±{r['tolerances'][0]:g} Hz, ±{r['tolerances'][1]:g} Hz/s), each pipeline at its own reference time: this "
            "search's frequency is at the look's start, turboSETI's half a spectrum in (the channel of its first "
            "spectrum); pickles' by the window holding the signal in an ON look's eighth spectrum, the one it scores. "
            "A match the block already had unplanted is a false association, not a recovery (in brackets).", ""]
    for title, key in (("at the published cuts (this search 10, turboSETI 10, pickles level 1, its masks off)",
                        "recovery_published"), ("at the matched cuts", "recovery_matched")):
        tab = r[key]
        if not tab:
            continue
        ps = [p for p in ("ours", "turboseti", "pickles") if p in tab["all"][0]]
        out += [f"### {title[0].upper() + title[1:]}", "", "| drift (Hz/s) | S_in | Jy Hz | " + " | ".join(name[p] for p in ps)
                + " | here, not turboSETI | turboSETI, not here |", "|---" * (3 + len(ps) + 2) + "|"]
        for row in tab["all"]:
            out.append(f"| {row['drift_hz_s'][0]}-{row['drift_hz_s'][1]} | {row['s_in']} | {row['flux_jy_hz']} | "
                       + " | ".join(f"{row[p]['recovered']}/{row[p]['planted']} ({row[p]['false_associations']})"
                                    for p in ps)
                       + f" | {row.get('ours_not_turboseti', '')} | {row.get('turboseti_not_ours', '')} |")
        for cls in ("clean", "crowded"):
            tot = {p: (sum(x[p]["recovered"] for x in tab[cls]), sum(x[p]["planted"] for x in tab[cls])) for p in ps}
            out.append("")
            out.append(f"{cls.capitalize()} blocks, every strength and drift: " + "; ".join(
                f"{name[p]} {k}/{n}" for p, (k, n) in tot.items()) + ".")
        out.append("")
    out += ["## S_in at which 80% are recovered", "", "| drift (Hz/s) | this search, published | turboSETI, "
            "published | this search, matched | turboSETI, matched |", "|---|---|---|---|---|"]
    for b in r["s_in_80"]["ours"]["published"]:
        m = r["s_in_80"]
        out.append(f"| {b} | {m['ours']['published'][b]} | {m['turboseti']['published'][b]} | "
                   f"{(m['ours']['matched'] or {}).get(b)} | {(m['turboseti']['matched'] or {}).get(b)} |")
    out += ["", "## Tolerances", ""]
    for p, o in r["offsets"].items():
        if o:
            out.append(f"- {name[p]}: of {o['signals']} planted at S_in 60 or more with an output nearby, the closest "
                       f"is a median {o['df_hz_median']} Hz and {o['dd_hz_s_median']} Hz/s away; "
                       f"{o['within_hz_only']} within the frequency tolerance only, {o['within_drift_only']} within "
                       "the drift tolerance only.")
    out += ["", f"Looks whose hit list was cut short (crowded): {r['incomplete_looks']}.", ""]
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    write(sys.argv[1] if len(sys.argv) > 1 else "KIC8462852")
