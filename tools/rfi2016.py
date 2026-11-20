"""The 2016 session's false candidates taken apart (the interference audit,
docs/audits.md 5). Supplementary and exploratory: steps 4, 10 and 12, their
cuts, thresholds and verdicts are unchanged; nothing here changes the
detector or the cadence test. Any rule these suggest becomes a new
version, tested on observations chosen beforehand.

    python tools/rfi2016.py records     anatomy, residual and evidence, from the block records
    python tools/rfi2016.py reread      veto, cap and families, from blocks read again (hours)
    python tools/rfi2016.py all

From the records:
- **anatomy**: every distinct false candidate of the 2016 session's wrong
  choices at SNR 30 and 10 (groups by shared hits, as the rate counts them):
  block and class, frequency, drift, the look it was seeded in, its ON
  evidence (three hits; two hits and a track; one hit and two tracks), in how
  many wrong choices it appears, where it lies (in one of check 3's listed
  bands; within 10 MHz of one; in vetting.KNOWN_RFI, an annotation; else in a
  crowded or a clean block), and whether its block's hit lists were cut at
  the hit cap.
- **residual**: the rate a block (weighted by class, as published) of each
  of those places, so that what is left outside the bands is measured.
- **evidence**: requiring two, or three, of a candidate's ON looks to hold a
  hit at the cut instead of one and tracks: the false rate left (all three
  sessions, exact from the records' wrong-choice candidates) and, for the
  planted signals, an upper bound on those kept: the records keep, for each
  signal, the hits of the event matching most of its ON hits, which need not
  be the event that recovered it in all three looks. The exact count, from
  the event that does recover each signal, comes from the blocks read again.

From blocks read again (the 2016 session's seven blocks with most false
candidates at 30, four other crowded and four clean ones at random, and
eight of the 2017 session's at random, seed 12, so that nothing is set on
2016 alone):
- **veto**: onoff.OFF_MAX at 5, 6 (in use), 7, 8 and 10: the false
  candidates of the 19 wrong choices and the planted signals recovered, at
  SNR 30 and 10; at 6 each block is checked to give its record's own counts;
- **evidence, exact**: at OFF_MAX 6, the planted signals recovered by an
  event with at least one, two or three ON hits at the cut (the event that
  recovers the signal, recovered_with), and the false candidates left;
- **cap**: the seven blocks searched with the hit cap raised to 20,000: their
  false candidates at 30 matched across the two searches by frequency and
  drift (hit numbers index each search's own list, so they are not compared):
  kept, kept with other member hits, gone, new;
- **families**: for each false candidate of the seven blocks at 30, the hits
  in its OFF looks within 3 kHz (any drift, and within 0.1 Hz/s of its own),
  and the S/N its OFF looks show along its track.

Each block read again records a fingerprint of the code that made it and is
made again when it differs.

Writes data/analysis/rfi2016_records.json and rfi2016_reread.json.
"""
import os

# Remakes step 10's blocks and checks them against its records: the DC bins blanked as those reads
# did, by storage chunk (seti.dc_rule).
os.environ.setdefault("SSY_DC_BY_CHUNK", "1")
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import matched  # noqa: E402
import matched_tables  # noqa: E402
import onoff  # noqa: E402
import searching  # noqa: E402
import seti  # noqa: E402
import vetting  # noqa: E402
import yoke  # noqa: E402
from injection_checks import _drift_bin  # noqa: E402

OUT = yoke.DATA / "analysis"
TARGET = "HIP17147"
CUTS = (30, 10)
OFF_MAX_GRID = (5.0, 6.0, 7.0, 8.0, 10.0)
NEAR_MHZ = 10.0
RAISED_CAP = 20000
CODE = ("tools/rfi2016.py", "matched.py", "matched_tables.py", "onoff.py", "searching.py", "seti.py", "measure.py",
        "vetting.py")


def fingerprint():
    h = hashlib.sha256()
    for f in CODE:
        h.update((ROOT / f).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def recovered_with(t_f, drift, kept_planted, kept_plain, need):
    """Whether a planted signal is recovered in all three ON looks (each by a
    member hit or a measured track) by an event with at least `need` ON member
    hits, the same event for both, and no such event in the unplanted block."""
    def qualifies(ev):
        ok, n = matched._event_fit(t_f, drift, ev, tracks=True)
        return ok == n == len(matched.TRUE) and len(ev["members"]) >= need
    return any(qualifies(e) for e in kept_planted) and not any(qualifies(e) for e in kept_plain)


def match_groups(a, b):
    """Two searches' distinct candidates ({representative event}) matched by
    frequency and drift within the tolerances: (kept, kept with other member
    hits, gone, new)."""
    used, kept, changed = set(), 0, 0
    for ev in a:
        hit = next((i for i, e in enumerate(b) if i not in used
                    and abs((e["f_mhz"] - ev["f_mhz"]) * 1e6) <= matched.TOL_HZ
                    and abs(e["drift"] - ev["drift"]) <= matched.TOL_DRIFT), None)
        if hit is None:
            continue
        used.add(hit)
        if len(b[hit]["members"]) == len(ev["members"]) and len(b[hit].get("tracks", [])) == len(ev.get("tracks", [])):
            kept += 1
        else:
            changed += 1
    return {"kept": kept, "kept_with_other_members": changed, "gone": len(a) - kept - changed,
            "new": len(b) - len(used)}


def _say(*a):
    print(*a, flush=True)


def place(f_mhz, cls):
    """Where a frequency lies: in a listed band, near one, in the known-RFI annotation, or neither."""
    if any(lo <= f_mhz <= hi for lo, hi, _ in vetting.BANDS):
        return "in a listed band"
    if any(lo - NEAR_MHZ <= f_mhz <= hi + NEAR_MHZ for lo, hi, _ in vetting.BANDS):
        return "within 10 MHz of a listed band"
    if vetting.known_rfi(f_mhz):
        return "in the known-RFI annotation (GPS L3)"
    return f"elsewhere, {cls} block"


def evidence(ev):
    """A kept candidate's ON evidence: its member hits and its tracks."""
    h, t = len(ev["members"]), len(ev.get("tracks", []))
    return {3: "three hits", 2: "two hits and a track", 1: "one hit and two tracks"}.get(h, f"{h} hits, {t} tracks")


def groups_of(by_choice):
    """The distinct candidates of a block's wrong choices: one representative
    each (the event with most member hits) and the choices it appears in."""
    events, choice_of = [], []
    for ch, evs in by_choice.items():
        for ev in evs:
            events.append(ev)
            choice_of.append(ch)
    parent = list(range(len(events)))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    owner = {}
    for n, ev in enumerate(events):
        for m in ev["members"]:
            k = matched._hit_key(m)
            if k in owner:
                parent[root(n)] = root(owner[k])
            else:
                owner[k] = n
    out = {}
    for n in range(len(events)):
        out.setdefault(root(n), []).append(n)
    return [(max((events[i] for i in idx), key=lambda e: len(e["members"])), len({choice_of[i] for i in idx}))
            for idx in out.values()]


def _session(target):
    session, meta, recs = matched_tables.load(target)
    total = meta["of"]["clean"] + meta["of"]["crowded"]
    return dict(meta, session=session), sorted(recs, key=lambda r: r["block"]), \
        {c: meta["of"][c] / total for c in ("clean", "crowded")}


def _weighted(per_block, recs, weights):
    """{block: count} to the published rate a block: each class's mean weighted by its share."""
    out = 0.0
    for cls in ("clean", "crowded"):
        bs = [r["block"] for r in recs if r["class"] == cls]
        if bs:
            out += weights[cls] * sum(per_block.get(b, 0) for b in bs) / len(bs)
    return out


def records(say=_say):
    meta, recs, weights = _session(TARGET)
    rec = {"target": TARGET, "session": meta.get("session"), "weights": weights}
    for c in CUTS:
        k = matched.ck(c)
        rows = []
        for r in recs:
            capped = not all(r.get("complete", [True] * 6))
            for ev, n in groups_of(r["ours"]["false"].get(k, {})):
                rows.append({"block": r["block"], "class": r["class"], "f_mhz": ev["f_mhz"], "drift": ev["drift"],
                             "seed_look": ev["look"], "evidence": evidence(ev), "wrong_choices": n,
                             "place": place(ev["f_mhz"], r["class"]), "known_rfi": vetting.known_rfi(ev["f_mhz"]),
                             "block_capped": capped})
        by_block = {}
        for x in rows:
            by_block[x["block"]] = by_block.get(x["block"], 0) + 1
        top = sorted(by_block.items(), key=lambda kv: -kv[1])[:7]
        count = lambda key: {v: sum(x[key] == v for x in rows) for v in sorted({x[key] for x in rows}, key=str)}  # noqa: E731
        residual = {}
        for pl in sorted({x["place"] for x in rows}):
            pb = {}
            for x in rows:
                if x["place"] == pl:
                    pb[x["block"]] = pb.get(x["block"], 0) + 1
            residual[pl] = {"candidates": sum(pb.values()), "rate_a_block": round(_weighted(pb, recs, weights), 4)}
        by_ev = {}
        for x in rows:
            d = by_ev.setdefault(x["evidence"], {"candidates": 0, "seven_blocks": 0})
            d["candidates"] += 1
            d["seven_blocks"] += x["block"] in dict(top)
        rec[f"cut_{c}"] = {"candidates": len(rows), "rate_a_block": round(_weighted(by_block, recs, weights), 4),
                           "seven_blocks": {str(b): n for b, n in top},
                           "in_the_seven_blocks": sum(n for _, n in top),
                           "by_evidence": by_ev, "by_place": count("place"), "by_capped_block": count("block_capped"),
                           "residual": residual, "rows": rows}
    # Requiring more ON hits: the false rate left in each session, and the planted signals lost.
    req = {}
    for target in ("KIC8462852", "HIP17147", "NGC6946"):
        _, rs, w = _session(target)
        out = {}
        for c in CUTS:
            k = matched.ck(c)
            for need in (1, 2, 3):
                pb = {r["block"]: len(matched.shared_hits({ch: [e for e in evs if len(e["members"]) >= need]
                                                           for ch, evs in r["ours"]["false"].get(k, {}).items()}))
                      for r in rs}
                tones = [t for r in rs for t in r["tones"]]
                found = [t for t in tones if t["ours"][k].get("three_looks") == "recovered"
                         and (t["ours"][k].get("members") or [0, 0])[1] >= need]
                by_d, by_s = {}, {}
                for t in found:
                    by_d[_drift_bin(t["drift"])] = by_d.get(_drift_bin(t["drift"]), 0) + 1
                    by_s[str(t["s_in"])] = by_s.get(str(t["s_in"]), 0) + 1
                out[f"cut {c}, at least {need} ON hit(s)"] = {
                    "false_rate_a_block": round(_weighted(pb, rs, w), 4), "found_at_most": len(found), "of": len(tones),
                    "found_by_drift": by_d, "found_by_strength": dict(sorted(by_s.items(), key=lambda kv: float(kv[0])))}
        req[target] = out
    rec["evidence_requirement"] = req
    rec["note"] = ("found_at_most: a planted signal is counted under a requirement when it is recovered in all three "
                   "ON looks and the event matching most of its ON hits has at least that many ON member hits; that "
                   "event need not be the one recovering it, so this bounds the count from above. The exact count, "
                   "from the recovering event itself, is rfi2016_reread.json's, on the blocks read again.")
    rec["kind"] = "measured"
    yoke.write(OUT / "rfi2016_records.json", rec, indent=1, stamp=True)
    for c in CUTS:
        x = rec[f"cut_{c}"]
        say(f"cut {c}: {x['candidates']} candidates ({x['rate_a_block']} a block), {x['in_the_seven_blocks']} in seven "
            f"blocks {list(x['seven_blocks'])}; by evidence {x['by_evidence']}")
        say(f"  residual: {x['residual']}")
    for t, out in req.items():
        say(f"{t}: " + "; ".join(f"{k}: false {v['false_rate_a_block']}, found at most {v['found_at_most']}"
                                 for k, v in out.items()))
    return rec


# --- blocks read again ----------------------------------------------------------------------

class off_max:
    def __init__(self, v):
        self.v = v

    def __enter__(self):
        self.saved = onoff.OFF_MAX
        onoff.OFF_MAX = self.v

    def __exit__(self, *_):
        onoff.OFF_MAX = self.saved


def _search(cad, max_hits=searching.MAX_HITS):
    if max_hits == searching.MAX_HITS:
        return matched.our_search(cad)
    from concurrent.futures import ThreadPoolExecutor

    def one(j):
        s, raw = cad[j]["s"], cad[j]["spectra"]
        details = {}
        hits = seti.describe(searching.search(raw, s["foff"], s["tsamp"], s["fch1"], max_hits=max_hits,
                                              details=details), dict(s, spectra=raw))
        return hits, details["flat"], bool(details["complete"])
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(one, range(6)))


def _false(cad, searched, cut):
    by, events_by = {}, {}
    caches = [{} for _ in range(6)]
    for ons in [x for x in __import__("itertools").combinations(range(6), 3) if x != matched.TRUE]:
        looks, events, order = matched.our_events(cad, searched, ons, cut, caches)
        by[str(ons)] = matched._our_kept(looks, events, order)
        events_by[str(ons)] = [e for e in events if e["label"] == "candidate"]
        for lk in looks:
            lk.flat = None
    return by, events_by


def _picks():
    import turbo_checks
    _, recs, _ = _session(TARGET)
    counts = {r["block"]: len(groups_of(r["ours"]["false"].get("30", {}))) for r in recs}
    seven = [b for b, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:7]]
    rng = np.random.default_rng(12)
    others = []
    for cls in ("crowded", "clean"):
        pool = sorted(r["block"] for r in recs if r["class"] == cls and r["block"] not in seven)
        others += [int(b) for b in rng.choice(pool, 4, replace=False)]
    _, _, _, chosen17, picks17 = turbo_checks._picks("KIC8462852")
    return seven, others, picks17


def reread(say=_say):
    import store
    seven, others, picks17 = _picks()
    rec = {"seven": seven, "others": others, "kic8462852": picks17, "off_max_grid": OFF_MAX_GRID, "blocks": []}
    for target, blocks in ((TARGET, seven + others), ("KIC8462852", picks17)):
        db = store.connect_readonly()
        session, urls = store.cadence_files(db, target)
        db.close()
        base = matched.folder(target, session)
        block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
        for b in blocks:
            path = OUT / "rfi2016" / f"{target}_{b:03d}.json"
            fp = fingerprint()
            if path.exists():
                old = json.loads(path.read_text(encoding="utf-8"))
                if old.get("code") == fp:
                    rec["blocks"].append(old)
                    continue
                say(f"{path.name}: made by other code ({old.get('code')}, now {fp}); made again")
            r = json.loads((base / f"block_{b:03d}.json").read_text(encoding="utf-8"))
            cad = matched._cadence(seti.read_looks(urls, *block_list[b]), urls)
            if [c["s"]["tstart"] for c in cad] != r["tstarts"]:
                raise yoke.Refusal("INVALID_REQUEST", f"block {b} read again is not the one recorded")
            ts = r["tones"]
            cad_p = [dict(c, spectra=p["spectra"]) for c, p in zip(cad, matched.plant(cad, ts))]
            s_plain, s_planted = _search(cad), _search(cad_p)
            row = {"target": target, "block": b, "class": r["class"], "code": fp, "veto": {}, "evidence": {}}
            for v in OFF_MAX_GRID:
                with off_max(v):
                    for c in CUTS:
                        by, _ = _false(cad, s_plain, c)
                        caches = [{} for _ in range(6)]
                        looks, events, order = matched.our_events(cad_p, s_planted, matched.TRUE, c, caches)
                        kept_p = matched._our_kept(looks, events, order)
                        looks, events, order = matched.our_events(cad, s_plain, matched.TRUE, c, [{} for _ in range(6)])
                        kept_u = matched._our_kept(looks, events, order)
                        t_fs = [{j: matched.where(cad, t, j)[1] for j in matched.TRUE} for t in ts]
                        found = sum(matched._status(tf, t["drift"], kept_p, kept_u)["three_looks"] == "recovered"
                                    for tf, t in zip(t_fs, ts))
                        row["veto"][f"{v:g} {c}"] = {"false": len(groups_of(by)), "found": found, "of": len(ts)}
                        if v == 6.0:
                            # The baseline must give the block record's own counts.
                            k = matched.ck(c)
                            rec_false = len(groups_of(r["ours"]["false"].get(k, {})))
                            rec_found = sum(t["ours"][k].get("three_looks") == "recovered" for t in ts)
                            row["veto"][f"{v:g} {c}"]["reproduces_record"] = (len(groups_of(by)), found) == \
                                (rec_false, rec_found)
                            for need in (1, 2, 3):
                                byn = {ch: [e for e in evs if len(e["members"]) >= need] for ch, evs in by.items()}
                                row["evidence"][f"{c}, at least {need}"] = {
                                    "false": len(groups_of(byn)),
                                    "found": sum(recovered_with(tf, t["drift"], kept_p, kept_u, need)
                                                 for tf, t in zip(t_fs, ts)), "of": len(ts)}
            if target == TARGET and b in seven:
                by_c, ev_c = _false(cad, s_plain, 30)
                s_raised = _search(cad, RAISED_CAP)
                by_r, _ = _false(cad, s_raised, 30)
                ga, gz = [ev for ev, _ in groups_of(by_c)], [ev for ev, _ in groups_of(by_r)]
                row["cap"] = {"capped_looks": [not x[2] for x in s_plain], "raised_complete": [x[2] for x in s_raised],
                              "false_capped": len(ga), "false_raised": len(gz), **match_groups(ga, gz)}
                fam = []
                hits = [x[0] for x in s_plain]
                for ch, evs in ev_c.items():
                    ons = eval(ch)  # noqa: S307  (a tuple of ints written by str())
                    offs = [j for j in range(6) if j not in ons]
                    for e in evs:
                        near = [h for j in offs for h in hits[j] if abs((h["frequency_mhz"] - e["frequency_mhz"]) * 1e6) <= 3000]
                        fam.append({"choice": ch, "f_mhz": round(e["frequency_mhz"], 6), "drift": e["drift_hz_s"],
                                    "off_hits_within_3_khz": len(near),
                                    "off_hits_within_3_khz_and_0.1_hz_s": sum(abs(h["drift_hz_s"] - e["drift_hz_s"]) <= 0.1
                                                                            for h in near),
                                    "off_snr_max": e.get("off_snr_max"), "on_snr_min": e.get("on_snr_min")})
                row["families"] = {"candidates": len(fam),
                                   "with_an_off_hit_within_3_khz": sum(f["off_hits_within_3_khz"] > 0 for f in fam),
                                   "with_a_like_drifting_off_hit": sum(f["off_hits_within_3_khz_and_0.1_hz_s"] > 0 for f in fam),
                                   "off_snr_max_median": float(np.median([f["off_snr_max"] for f in fam
                                                                          if f["off_snr_max"] is not None] or [np.nan])),
                                   "rows": fam}
            path.parent.mkdir(parents=True, exist_ok=True)
            yoke.write(path, row, indent=1)
            rec["blocks"].append(row)
            say(f"{target} block {b} ({r['class']}): " + ", ".join(f"OFF_MAX {k}: {v['false']} false, {v['found']} found"
                                                                   for k, v in row["veto"].items())
                + (f"; cap {row['cap']}" if "cap" in row else "")
                + (f"; families {({k: v for k, v in row['families'].items() if k != 'rows'})}" if "families" in row else ""))
    tot, ev_tot = {}, {}
    for row in rec["blocks"]:
        for k, v in row["veto"].items():
            d = tot.setdefault(row["target"], {}).setdefault(k, {"false": 0, "found": 0, "of": 0})
            for x in ("false", "found", "of"):
                d[x] += v[x]
        for k, v in row.get("evidence", {}).items():
            d = ev_tot.setdefault(row["target"], {}).setdefault(k, {"false": 0, "found": 0, "of": 0})
            for x in ("false", "found", "of"):
                d[x] += v[x]
    rec["veto_totals"] = tot
    rec["evidence_totals"] = ev_tot
    rec["baseline_reproduces_records"] = all(v.get("reproduces_record", True) for row in rec["blocks"]
                                             for v in row["veto"].values())
    rec["cap_totals"] = {k: sum(row["cap"][k] for row in rec["blocks"] if "cap" in row)
                         for k in ("false_capped", "false_raised", "kept", "kept_with_other_members", "gone", "new")}
    rec["kind"] = "measured"
    yoke.write(OUT / "rfi2016_reread.json", rec, indent=1, stamp=True)
    say(f"veto totals: {tot}")
    say(f"evidence (exact): {ev_tot}; cap: {rec['cap_totals']}; baseline reproduces records: "
        f"{rec['baseline_reproduces_records']}")
    return rec


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("records", "all"):
        records()
    if what in ("reread", "all"):
        reread()


if __name__ == "__main__":
    main()
