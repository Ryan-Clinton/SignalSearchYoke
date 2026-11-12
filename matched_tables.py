"""The tables of matched.py's run (comparable.md steps 4 and 7): each
pipeline's false candidates against its cut, the cut that gives the chosen
rate with its interval, and recovery at those cuts and at the published
ones. Written to data/measurements/matched.json and, as a page,
docs/results/TARGET-SESSION-matched.md.

False candidates are counted per block as distinct signals over the 19
wrong choices. How two candidates are taken to be one signal is a choice, so
it is made several ways and all are shown:

- shared hits (the one used for the curves): candidates with any member hit
  in common are one group (this search: the same hit of the same look;
  turboSETI: the same look, frequency and drift), joined through any chain
  of shared hits: connected groups of detections, which need not be one
  physical signal (A sharing a hit with B, and B another with C, makes one
  group even if A and C share none). No tolerance.
- frequency and drift: each candidate's start projected to the first look
  along its drift; within TOL_HZ and TOL_DRIFT of another is the same.
- frequency only, within 6 Hz, 100 Hz or 3 kHz (the first run's merging).
- none: every candidate of every wrong choice counted.

Recovery is counted four ways (matched.RECOVERY), each with false
associations (the block had such an event before planting) apart: in all
three ON looks (the main one: each ON look matching, by its hit or by the
track measured where it has none), three hits, strict (every ON member hit
matching) and lenient (any member).

The false-candidate rate is a wrong-cadence control: real looks of the
target given the wrong roles, not empty sky, so it is how often the
cadence logic keeps something when the roles are wrong, not a probability
of false detection in other observations."""
import json
import time

import numpy as np

import matched
import measure
import store
import yoke

RATE = 0.1                  # false candidates a block the cuts are matched at
BOOT = 4000
HOWS = ("three_looks", "three_hits", "strict", "lenient")
HOW_NAME = {"three_looks": "All three ON looks", "three_hits": "Three hits", "strict": "Strict (member hits)",
            "lenient": "Lenient"}
WAYS = ("shared hits", "frequency and drift", "frequency within 6 Hz", "frequency within 100 Hz",
        "frequency within 3 kHz", "none")
NAME = {"ours": "this search", "turboseti": "turboSETI", "pickles": "pickles"}


def load(target):
    db = store.connect()
    session, _ = store.cadence_files(db, target)
    db.close()
    base = matched.folder(target, session)
    meta = json.loads((base / "blocks.json").read_text(encoding="utf-8"))
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob("block_*.json"))]
    return session, meta, [r for r in recs if r.get("format") == matched.FORMAT]


def _has_tracks(r):
    return matched.complete(r)


def _single_link(items, close):
    groups = []
    for x in items:
        hit = [g for g in groups if any(close(x, y) for y in g)]
        merged = [x] + [y for g in hit for y in g]
        groups = [g for g in groups if all(g is not h for h in hit)] + [merged]
    return groups


def distinct(rec, by_choice, way):
    """The number of distinct false signals in one block's wrong choices."""
    evs = [ev for v in by_choice.values() for ev in v]
    if way == "none":
        return len(evs)
    if way == "shared hits":
        return len(matched.shared_hits(by_choice))
    if way == "frequency and drift":
        t = rec["tstarts"]
        pts = [(ev["f_mhz"] - ev["drift"] * (t[ev["look"]] - t[0]) * 86400 / 1e6, ev["drift"]) for ev in evs]
        return len(_single_link(pts, lambda a, b: abs(a[0] - b[0]) * 1e6 <= matched.TOL_HZ
                                and abs(a[1] - b[1]) <= matched.TOL_DRIFT))
    apart = {"frequency within 6 Hz": 6e-6, "frequency within 100 Hz": 1e-4, "frequency within 3 kHz": 3e-3}[way]
    return len(matched._distinct([ev["f_mhz"] for ev in evs], apart))


def _rate(recs, count, weights, rng):
    """Per block, by class and weighted by each class's share of all blocks,
    with a stratified bootstrap interval (the blocks the unit)."""
    by = {}
    for cls in ("clean", "crowded"):
        rs = [r for r in recs if r["class"] == cls]
        n = [count(r) for r in rs]
        m = max(len(rs), 1)
        if sum(n):
            # Bootstrap over the class's blocks: their counts are far from Poisson (one block can hold
            # most of them), so a Poisson interval on the total would be much too narrow.
            lo, hi = np.percentile([np.mean(rng.choice(n, len(n))) for _ in range(BOOT)], [2.5, 97.5])
        else:
            lo, hi = (x / m for x in measure.poisson_interval(0))
        by[cls] = {"blocks": len(rs), "distinct": sum(n), "per_block": round(sum(n) / m, 4),
                   "interval": (round(float(lo), 4), round(float(hi), 4)), "most_in_a_block": max(n, default=0),
                   "_n": n}
    est = sum(weights[c] * by[c]["per_block"] for c in by)
    boots = [sum(weights[c] * (np.mean(rng.choice(by[c]["_n"], len(by[c]["_n"]))) if by[c]["_n"] else 0)
                 for c in by) for _ in range(BOOT)]
    for c in by:
        by[c].pop("_n")
    lo, hi = np.percentile(boots, [2.5, 97.5])
    if hi == 0:     # nothing counted: the upper bound from the classes' Poisson intervals
        hi = sum(weights[c] * by[c]["interval"][1] for c in by)
    return {"per_block": round(est, 4), "interval": (round(float(lo), 4), round(float(hi), 4)), **by}


def _from(cuts, ok):
    """The lowest cut from which ok holds at it and at every higher cut tested
    (None if it fails at the highest)."""
    best = None
    for c in reversed(cuts):
        if not ok(c):
            break
        best = c
    return best


def _matched_cut(curve):
    """The lowest cut from which the rate stays at most RATE at every higher
    cut tested (None if it is above RATE at the highest: then nothing is
    matched). The curve need not fall with the cut: a higher cut can remove
    the OFF hits that vetoed an event (turboSETI, block 129), so a dip under
    RATE followed by a rise is not taken. Its interval: from the lowest cut
    from which every interval reaches down to RATE to the lowest from which
    every whole interval is under it. "monotonic" says whether the rate never
    rises with the cut."""
    cuts = sorted(curve, key=float)
    rates = [curve[c]["per_block"] for c in cuts]
    return {"cut": _from(cuts, lambda c: curve[c]["per_block"] <= RATE),
            "interval": (_from(cuts, lambda c: curve[c]["interval"][0] <= RATE),
                         _from(cuts, lambda c: curve[c]["interval"][1] <= RATE)),
            "monotonic": all(b <= a for a, b in zip(rates, rates[1:]))}


def _got(t, p, cut, how):
    if p == "pickles":
        x = t["pickles"]["unmasked"]
        return x.get("level") is not None and x["level"] >= cut and \
            (x.get("level_before") is None or x["level_before"] < cut)
    got = t[p][matched.ck(cut)].get(how) == "recovered"
    if p == "turboseti" and how == "three_looks":
        # Its event rule, checked: a matching hit in each true ON look of its own hit table at the cut.
        got = got and t["turboseti_on_hits"][matched.ck(cut)] == len(matched.TRUE)
    return got


def _false_assoc(t, p, cut, how):
    if p == "pickles":
        x = t["pickles"]["unmasked"]
        return x.get("level") is not None and x["level"] >= cut and \
            x.get("level_before") is not None and x["level_before"] >= cut
    return t[p][matched.ck(cut)].get(how) == "false association"


def recovery(tones, cuts, how):
    """By drift bin and S_in, each pipeline at its cut (cuts: {pipeline: cut};
    pickles: a level), with false associations apart."""
    out = []
    for b, (lo, hi) in enumerate(measure.DRIFT_BINS):
        for s in matched.STRENGTHS:
            cell = [t for t in tones if t["bin"] == b and t["s_in"] == s]
            if not cell:
                continue
            row = {"drift_hz_s": [lo, hi], "s_in": s, "flux_jy_hz": cell[0]["flux_jy_hz"]}
            for p, c in cuts.items():
                k = sum(_got(t, p, c, how) for t in cell)
                row[p] = {"planted": len(cell), "recovered": k, "interval": measure.wilson(k, len(cell)),
                          "false_associations": sum(_false_assoc(t, p, c, how) for t in cell)}
            if "ours" in cuts and "turboseti" in cuts:
                row["ours_not_turboseti"] = sum(_got(t, "ours", cuts["ours"], how)
                                                and not _got(t, "turboseti", cuts["turboseti"], how) for t in cell)
                row["turboseti_not_ours"] = sum(_got(t, "turboseti", cuts["turboseti"], how)
                                                and not _got(t, "ours", cuts["ours"], how) for t in cell)
            out.append(row)
    return out


def s_in_at(tones, p, cut, how="three_looks", share=0.8):
    """By drift bin, the lowest S_in from which at least `share` are
    recovered at it and every higher S_in."""
    out = {}
    for b, (lo, hi) in enumerate(measure.DRIFT_BINS):
        best = None
        for s in sorted(matched.STRENGTHS, reverse=True):
            cell = [t for t in tones if t["bin"] == b and t["s_in"] == s]
            if not cell:
                continue
            if sum(_got(t, p, cut, how) for t in cell) / len(cell) < share:
                break
            best = s
        out[f"{lo}-{hi}"] = best
    return out


def _offsets(tones, p, cut):
    near = [t[p][matched.ck(cut)]["nearest"] for t in tones if t["s_in"] >= 60 and t[p][matched.ck(cut)]["nearest"]]
    if not near:
        return None
    df = np.array([abs(x["df_hz"]) for x in near])
    dd = np.array([abs(x["dd_hz_s"]) for x in near])
    return {"signals": len(near), "df_hz_median": round(float(np.median(df)), 2),
            "dd_hz_s_median": round(float(np.median(dd)), 4),
            "within_hz_only": int(((df <= matched.TOL_HZ) & (dd > matched.TOL_DRIFT)).sum()),
            "within_drift_only": int(((df > matched.TOL_HZ) & (dd <= matched.TOL_DRIFT)).sum())}


def write(target, say=print, name="matched.json"):
    """name: the record's file in data/measurements (step 4's is matched.json)."""
    session, meta, recs = load(target)
    if not recs:
        raise yoke.Refusal("NOT_FOUND", f"No block of matched.py's run (record format {matched.FORMAT}) is done.")
    rng = np.random.default_rng(1)
    total = meta["of"]["clean"] + meta["of"]["crowded"]
    weights = {c: meta["of"][c] / total for c in ("clean", "crowded")}
    pub = {"ours": matched.PUBLISHED["ours"], "turboseti": matched.PUBLISHED["turboseti"]}
    curves, ways = {"ours": {}, "turboseti": {}, "pickles": {}}, {"ours": {}, "turboseti": {}}
    for p, grid in (("ours", matched.CUTS_OURS), ("turboseti", matched.CUTS_TURBO)):
        for c in grid:
            curves[p][matched.ck(c)] = _rate(
                recs, lambda r: distinct(r, r[p]["false"].get(matched.ck(c), {}), "shared hits"), weights, rng)
    cuts = {p: _matched_cut(curves[p]) for p in ("ours", "turboseti")}
    for p in ("ours", "turboseti"):
        at = {"published": pub[p]}
        if cuts[p]["cut"] is not None:
            at["matched"] = float(cuts[p]["cut"])
        for label, c in at.items():
            ways[p][label] = {"cut": c, **{w: _rate(recs, lambda r: distinct(r, r[p]["false"].get(matched.ck(c), {}), w),
                                                    weights, rng) for w in WAYS}}
    for run in ("unmasked", "masked"):
        for level in ("1", "2"):
            curves["pickles"][f"{run} level {level}"] = _rate(
                recs, lambda r: len({x[0] for v in r["pickles"]["false"][run][level].values() for x in v}),
                weights, rng)
    checks = [dict(c, block=r["block"], cls=r["class"]) for r in recs for c in r["ours"]["checks_at_published_cut"]]
    # Recovery only from blocks with the measured ON tracks (matched.py tracks adds them to older ones).
    tones = [dict(t, cls=r["class"], block=r["block"]) for r in recs if _has_tracks(r) for t in r["tones"]]
    without = [r["block"] for r in recs if not _has_tracks(r)]
    published = dict(pub, pickles=1)
    at_matched = {p: float(cuts[p]["cut"]) for p in ("ours", "turboseti") if cuts[p]["cut"] is not None}
    rec = {
        "target": target, "session": session, "blocks": len(recs),
        "classes": {c: sum(r["class"] == c for r in recs) for c in ("clean", "crowded")}, "of": meta["of"],
        "crowded_hits": meta["crowded_hits"], "rate_matched": RATE, "tolerances": [matched.TOL_HZ, matched.TOL_DRIFT],
        "false_curves": curves, "dedup_ways": ways, "matched_cuts": cuts, "both_matched": len(at_matched) == 2,
        "checks_on_false_at_published_cut": checks, "tones": len(tones),
        "recovery_blocks_without_tracks": without,
        "recovery_published": {how: {c: recovery([t for t in tones if c == "all" or t["cls"] == c],
                                                 published if how != "three_hits" else {"ours": pub["ours"]}, how)
                                     for c in ("all", "clean", "crowded")} for how in HOWS},
        "recovery_matched": ({how: {c: recovery([t for t in tones if c == "all" or t["cls"] == c], at_matched, how)
                                    for c in ("all", "clean", "crowded")} for how in ("three_looks", "strict")}
                             if len(at_matched) == 2 else None),
        "s_in_80": {p: {"published": s_in_at(tones, p, published[p]),
                        "matched": s_in_at(tones, p, at_matched[p]) if p in at_matched else None}
                    for p in ("ours", "turboseti")},
        "offsets": {p: _offsets(tones, p, published[p]) for p in ("ours", "turboseti")},
        "incomplete_looks": sum(not x for r in recs for x in r["complete"]), "record": name,
        "kind": "measured", "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    yoke.write(yoke.DATA / "measurements" / name, rec, stamp=True)
    page = yoke.ROOT / "docs" / "results" / f"{target}-{session}-matched.md"
    page.write_text(markdown(rec), encoding="utf-8")
    say(f"{page}: {len(recs)} blocks, {len(tones)} planted signals")
    return rec


def _iv(x):
    return f"{x[0]:.3g}-{x[1]:.3g}"


def _rec_table(tab, ps):
    both = "turboseti" in ps and "ours" in ps
    out = ["| drift (Hz/s) | S_in | Jy Hz | " + " | ".join(NAME[p] for p in ps)
           + (" | here, not turboSETI | turboSETI, not here |" if both else " |"),
           "|---" * (3 + len(ps) + (2 if both else 0)) + "|"]
    for row in tab["all"]:
        out.append(f"| {row['drift_hz_s'][0]}-{row['drift_hz_s'][1]} | {row['s_in']} | {row['flux_jy_hz']} | "
                   + " | ".join(f"{row[p]['recovered']}/{row[p]['planted']} ({row[p]['false_associations']})"
                                for p in ps)
                   + (f" | {row['ours_not_turboseti']} | {row['turboseti_not_ours']} |" if both else " |"))
    for cls in ("clean", "crowded"):
        tot = {p: (sum(x[p]["recovered"] for x in tab[cls]), sum(x[p]["planted"] for x in tab[cls])) for p in ps}
        out += ["", f"{cls.capitalize()} blocks, every strength and drift: "
                + "; ".join(f"{NAME[p]} {k}/{n}" for p, (k, n) in tot.items()) + "."]
    return out + [""]


def markdown(r):
    out = [f"# {r['target']} {r['session']}: the pipelines at matched sensitivity", "",
           f"Written by `matched.py tables {r['target']}` from `matched.py run` (comparable.md steps 4 and 7); "
           f"the record is data/measurements/{r.get('record', 'matched.json')}.", "",
           f"{r['blocks']} blocks: {r['classes']['crowded']} crowded (more than {r['crowded_hits']} hits at this "
           f"search's cut in the six looks; there are {r['of']['crowded']}) and {r['classes']['clean']} clean "
           f"(of {r['of']['clean']}, drawn at random). Rates over all blocks weight the two by their share of the "
           f"{r['of']['clean'] + r['of']['crowded']}. The intervals describe this sample of blocks from one session "
           "at one telescope: blocks near each other share interference, so they are not fully independent, and "
           "none of this is a false-alarm rate for other observations.", "",
           f"False candidates are from all {r['blocks']} blocks; recovery from "
           f"{r['blocks'] - len(r['recovery_blocks_without_tracks'])}"
           + (f" (waiting for `matched.py tracks`: {', '.join(map(str, r['recovery_blocks_without_tracks']))})"
              if r["recovery_blocks_without_tracks"] else "") + ".", "",
           "## False candidates against the cut", "",
           "Each block judged with the 19 wrong choices of three ON looks: what a choice keeps cannot come from the "
           "target. These are real looks of the target in the wrong roles, not empty sky: a wrong-cadence control "
           "rate, how often the cadence logic keeps something when the roles are wrong. Counted a block as groups "
           "of candidates joined through shared member hits (connected groups of detections, which need not each "
           "be one physical signal; the other ways of counting are below); 95% intervals (all blocks: stratified "
           "bootstrap over blocks; a class: bootstrap over its blocks, or Poisson on a count of none).", ""]
    for p in ("ours", "turboseti"):
        out += [f"**{NAME[p]}**", "", "| cut (its SNR) | all blocks | clean | crowded | most in one block |",
                "|---|---|---|---|---|"]
        for c, v in sorted(r["false_curves"][p].items(), key=lambda x: float(x[0])):
            most = max(v["clean"]["most_in_a_block"], v["crowded"]["most_in_a_block"])
            out.append(f"| {c} | {v['per_block']:.3g} ({_iv(v['interval'])}) | {v['clean']['per_block']:.3g} "
                       f"({_iv(v['clean']['interval'])}) | {v['crowded']['per_block']:.3g} "
                       f"({_iv(v['crowded']['interval'])}) | {most} |")
        m = r["matched_cuts"][p]
        lowest = min(r["false_curves"][p], key=float)
        hi = r["false_curves"][p][m["cut"]]["interval"][1] if m["cut"] is not None else None
        out += ["", (f"Cut for {r['rate_matched']} a block: {m['cut']} (interval {m['interval'][0]} to "
                     f"{m['interval'][1]})."
                     + (f" The rate's interval at that cut reaches {hi:.3g}, above {r['rate_matched']}: the rate "
                        "there is not shown to be under it." if hi > r["rate_matched"] else "")
                     if m["cut"] is not None else
                     f"No cut in the tested range gives {r['rate_matched']} a block or fewer.")
                + (" That is the lowest cut tested: a lower one might give the same rate, so this is an upper "
                   "bound on its matched cut." if m["cut"] == lowest else "")
                + ("" if m.get("monotonic", True) else
                   " The rate does not fall at every step of the cut: a higher cut also removes OFF hits that "
                   "vetoed events, so the cut taken is the lowest from which the rate stays under the target at "
                   "every higher cut tested."), ""]
    out += ["**pickles** (windows kept, by level; not an SNR cut; one window kept in several choices counts once)",
            "", "| run | all blocks | clean | crowded |", "|---|---|---|---|"]
    for k, v in r["false_curves"]["pickles"].items():
        out.append(f"| {k} | {v['per_block']:.3g} ({_iv(v['interval'])}) | {v['clean']['per_block']:.3g} | "
                   f"{v['crowded']['per_block']:.3g} |")
    out += ["", "### How the count depends on what is taken as one signal", "",
            "| pipeline, cut | " + " | ".join(WAYS) + " |", "|---" * (1 + len(WAYS)) + "|"]
    for p in ("ours", "turboseti"):
        for label, by in r["dedup_ways"][p].items():
            out.append(f"| {NAME[p]}, {label} ({by['cut']:g}) | " + " | ".join(
                f"{by[w]['per_block']:.3g} ({_iv(by[w]['interval'])})" for w in WAYS) + " |")
    ch = r["checks_on_false_at_published_cut"]
    verdicts = {}
    for c in ch:
        v = str(c["verdict"]).split(" (")[0]
        verdicts[v] = verdicts.get(v, 0) + 1
    out += ["", f"**This search's false candidates at its published cut, through the checks** (every wrong choice "
            f"that kept one; one signal kept in several choices is counted in each): {len(ch)}; "
            + ", ".join(f"{n} {v}" for v, n in sorted(verdicts.items(), key=lambda x: -x[1])) + "."]
    un = [c for c in ch if str(c["verdict"]).startswith("unexplained")]
    if un:
        out += ["", "Left unexplained by the checks:", "", "| block | class | as ON | MHz | Hz/s | SNR |",
                "|---|---|---|---|---|---|"]
        out += [f"| {c['block']} | {c['cls']} | {tuple(c['as_on'])} | {c['f_mhz']:.6f} | {c['drift']} | {c['snr']} |"
                for c in un]
    out += ["", "## Recovery", "",
            f"{r['tones']} signals planted in the true ON looks only, matched in frequency and drift both "
            f"(±{r['tolerances'][0]:g} Hz, ±{r['tolerances'][1]:g} Hz/s), each pipeline at its own reference time: "
            "this search's frequency is at the look's start, turboSETI's half a spectrum in (the channel of its "
            "first spectrum); pickles by the window holding the signal in an ON look's eighth spectrum, the one it "
            "scores. **All three ON looks** (the main one): an event matching the planted signal in each ON look, "
            "by its hit there or, where it has no hit at the cut, by the track this search measured there (which "
            "made it a candidate). For turboSETI, every hit it lists in the event matching, and its own hit table "
            "at the cut holding a matching hit in each ON look (its event table leaves out a look whose first hit "
            "number it has already written, so the event's rows alone do not show all three; the hit tables are "
            "checked by the same tolerances, though which hits its event used is not recorded). **Three hits:** this search only, "
            "a matching hit in each ON look. **Strict:** every ON member hit matching (an event may have fewer "
            "than three). **Lenient:** any member matching. A match the block already had unplanted is a false "
            "association, not a recovery (in brackets).", ""]
    if r["recovery_blocks_without_tracks"]:
        out += ["Blocks left out of recovery until `matched.py tracks` adds their measured tracks: "
                + ", ".join(map(str, r["recovery_blocks_without_tracks"])) + ".", ""]
    for how in HOWS:
        ps = ["ours"] if how == "three_hits" else ["ours", "turboseti", "pickles"]
        out += [f"### {HOW_NAME[how]}, at the published cuts (this search 10"
                + (", turboSETI 10, pickles level 1, its masks off)" if how != "three_hits" else ")"), ""] \
            + _rec_table(r["recovery_published"][how], ps)
    if r["recovery_matched"]:
        cm = {p: r["matched_cuts"][p]["cut"] for p in ("ours", "turboseti")}
        for how in ("three_looks", "strict"):
            out += [f"### {HOW_NAME[how]}, at the matched cuts (this search {cm['ours']}, turboSETI "
                    f"{cm['turboseti']}: {r['rate_matched']} false candidates a block)", ""] + \
                _rec_table(r["recovery_matched"][how], ["ours", "turboseti"])
        out += ["Each cut's false-candidate rate has its interval above; where those are wide, this comparison "
                "is not resolved by them, and neither pipeline is shown the better.", ""]
    else:
        out += ["### At matched cuts", "",
                f"Not made: no cut in the tested range gives {r['rate_matched']} false candidates a block for both "
                "pipelines, so they cannot be set at the same rate here. The curves above and the recovery at each "
                "cut in the record are the comparison; a matched one needs a common rate both reach.", ""]
    out += ["## S_in from which 80% are recovered (all three ON looks)", "",
            "| drift (Hz/s) | this search, published | turboSETI, published | this search, matched | turboSETI, "
            "matched |", "|---|---|---|---|---|"]
    m = r["s_in_80"]
    for b in m["ours"]["published"]:
        out.append(f"| {b} | {m['ours']['published'][b]} | {m['turboseti']['published'][b]} | "
                   f"{(m['ours']['matched'] or {}).get(b, '-')} | {(m['turboseti']['matched'] or {}).get(b, '-')} |")
    out += ["", "## Tolerances", ""]
    for p, o in r["offsets"].items():
        if o:
            out.append(f"- {NAME[p]}: of {o['signals']} planted at S_in 60 or more with a kept member hit anywhere "
                       f"in the block, the closest is a median {o['df_hz_median']} Hz and {o['dd_hz_s_median']} Hz/s "
                       f"away; {o['within_hz_only']} within the frequency tolerance only, {o['within_drift_only']} "
                       "within the drift tolerance only.")
    out += ["", f"Looks whose hit list was cut short (crowded): {r['incomplete_looks']}.", ""]
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    write(sys.argv[1] if len(sys.argv) > 1 else "KIC8462852")
