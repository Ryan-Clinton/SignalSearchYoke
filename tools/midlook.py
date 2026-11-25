"""A6-08: the planted signals of the matched experiment scored at the middle of each look, beside the published
scoring at its start. A fast signal's frequency is measured where the search's track fits it best, near the look's
middle, so a small drift error moves the frequency at the start by drift error x half the look: the published
scoring then counts a detected signal as missed. This is a new scoring version beside the published tables, for
this search; no frozen verdict uses it.

    python tools/midlook.py run TARGET     each matched block read again, planted again, searched (resumes)
    python tools/midlook.py run TARGET --from-end   the same from the last block, for a second lane
    python tools/midlook.py tables         recovery as published, at mid-look, and at mid-look with tolerances
                                           that grow with drift (A6-05), by drift range
    python tools/midlook.py checks         from the records alone: chance matches of each scoring against the
                                           unplanted blocks' events, close pairs of signals, and the frequency and
                                           drift errors apart (association_checks.json)
    python tools/midlook.py turbo TARGET [--from-end]   turboSETI on the same blocks, scored the same three ways
    python tools/midlook.py turbo-tables   both pipelines under the three scorings (turbo_tables.json)

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

import records  # noqa: E402
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


KEYS = ("published", "mid", "mid_scaled")
STATUSES = (None, "recovered", "false association")


def record_problems(rec, target, k, matched_rec, code=records.code_problems):
    """Why a block record is not this block's whole result: its session and block, every signal the matched
    record's in order, both cuts with all three scorings, the published statuses reproduced, and the code it was
    made by."""
    import matched
    name = f"{target} {k}"
    if not isinstance(rec, dict):
        return [f"{name}: no record"]
    out = []
    if (rec.get("target"), rec.get("block"), rec.get("class")) != (target, k, matched_rec.get("class")):
        out.append(f"{name}: the record is of another block")
    tones, want = rec.get("tones", []), matched_rec.get("tones", [])
    if len(tones) != matched.TONES or len(want) != matched.TONES:
        out.append(f"{name}: {len(tones)} signals, not {matched.TONES}")
    elif any((round(t.get("drift", 0), 6), t.get("s_in"), t.get("bin")) != (round(w["drift"], 6), w["s_in"], w["bin"])
             for t, w in zip(tones, want)):
        out.append(f"{name}: the signals are not the matched record's")
    elif any(t["at"].get(c, {}).get("published", "missing") != w["ours"][c]["three_looks"]
             for t, w in zip(tones, want) for c in CUTS):
        out.append(f"{name}: the published statuses are not the matched record's")
    if any(set(t.get("at", {})) != set(CUTS) or any(set(t["at"][c]) != set(KEYS) or
                                                     any(t["at"][c][key] not in STATUSES for key in KEYS)
                                                     for c in CUTS) for t in tones):
        out.append(f"{name}: a signal is not scored at both cuts in all three ways")
    if rec.get("published_reproduced") is not True:
        out.append(f"{name}: the published statuses were not reproduced")
    out += [f"{name}: {x}" for x in code(rec.get("provenance"), own=("tools/midlook.py",))]
    return out


def _base(target):
    """The matched run's folder for a target."""
    import matched
    found = sorted(matched.ROOT.glob(f"{target}-*"))
    if len(found) != 1:
        raise yoke.Refusal("INVALID_REQUEST", f"{target}: {len(found)} matched folders, not one")
    return found[0]


def _whole(target, k, matched_rec):
    return lambda r: not record_problems(r, target, k, matched_rec)


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
        rec = json.loads(p.read_text(encoding="utf-8"))
        if not yoke.whole(out / f"block_{k:03d}.json", _whole(target, k, rec)):
            todo.append((k, rec))
    say(f"{target}: {len(todo)} blocks to read again" + (", from the end" if from_end else ""))
    for k, rec in (todo[::-1] if from_end else todo):
        path = out / f"block_{k:03d}.json"
        # another lane may work the same session: a block is claimed before it is read, and skipped once whole
        with records.claim(path) as mine:
            if not mine or yoke.whole(path, _whole(target, k, rec)):
                continue
            got = one_block(target, k, rec, seti.read_looks(urls, *block_list[k]), urls)
            yoke.write(path, got, indent=None, stamp=True)
        n = lambda key, c: sum(t["at"][c][key] == "recovered" for t in got["tones"])  # noqa: E731
        say(f"  {target} block {k}: at 10, published {n('published', '10')}, mid {n('mid', '10')}, mid scaled "
            f"{n('mid_scaled', '10')}; reproduced {got['published_reproduced']}", flush=True)


def tables(say=print):
    out = {"sessions": {}, "kind": "measured"}
    for target in TARGETS:
        # exactly the matched run's blocks, each record checked whole against its matched record
        want = {int(p.stem.split("_")[1]): json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(_base(target).glob("block_*.json"))}
        have = {int(p.stem.split("_")[1]) for p in (OUT / target).glob("block_*.json")}
        if have - set(want):
            raise yoke.Refusal("INVALID_REQUEST", f"{target}: records of blocks the matched run has not: "
                                                  f"{sorted(have - set(want))}")
        recs, problems = [], []
        for k, m in want.items():
            p = OUT / target / f"block_{k:03d}.json"
            if p.exists():
                rec = json.loads(p.read_text(encoding="utf-8"))
                got = record_problems(rec, target, k, m)
                (problems.extend(got) if got else recs.append(rec))
        if problems:
            raise yoke.Refusal("INVALID_REQUEST", f"{target}: {len(problems)} problems, first {problems[:3]}")
        if not recs:
            continue
        cell = {"blocks": len(recs), "of": len(want), "not_reproduced": [], "missing": sorted(set(want) - have)}
        good = recs
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


# --- turboSETI scored the same way ---------------------------------------------------------------------------------
TURBO = OUT / "turboseti"


def turbo_status(t_f_turbo, drift, kept, plain, look_hits, cut, half, tol):
    """turboSETI's published three looks (matched._status with turboseti=True, then a matching hit of its own in
    every ON look at the cut, matched._turbo_on_hits), comparing `half` seconds after its reference time (the middle
    of a look's first spectrum) with tolerances `tol`. half 0 and the published tolerances: as published."""
    import matched

    def strict(ev):
        ok, n = fit(t_f_turbo, drift, ev, half, tol)
        return n >= 1 and ok == n

    def matches(j, h):
        return fit({j: t_f_turbo[j]}, drift, {"members": [[j, None, h["freq_mhz"], h["drift_hz_s"]]]}, half, tol)[0] == 1

    if not any(strict(ev) for ev in kept):
        return None
    if any(strict(ev) for ev in plain):
        return "false association"
    on = sum(any(h["snr"] > float(cut) and matches(j, h) for h in look_hits[j]) for j in matched.TRUE)
    return "recovered" if on == 3 else None


def _turbo_published(w, c):
    """A matched record's turboSETI status at cut c as the tables count it: recovered needs a hit in each ON look."""
    st = w["turboseti"][c]["three_looks"]
    return "recovered" if st == "recovered" and w["turboseti_on_hits"][c] == 3 else (None if st == "recovered" else st)


def turbo_block(target, k, rec, slices, urls, work):
    """A matched block planted again and searched by turboSETI as the matched run did; each signal scored as
    published, at mid-look and at mid-look with tolerances growing with drift. The published statuses must be the
    record's."""
    import matched
    import numpy as np
    import pipelines
    import seti
    cad = matched._cadence(slices, urls)
    ts = matched.tones(cad, np.random.default_rng([matched.SEED, k]))
    if [(round(a["x0"], 6), round(a["drift"], 6), a["s_in"]) for a in ts] != [
            (round(b["x0"], 6), round(b["drift"], 6), b["s_in"]) for b in rec["tones"]]:
        raise yoke.Refusal("INTERNAL_ERROR", f"{target} block {k}: the signals planted again are not the record's")
    planted = matched.plant(cad, ts)
    work.mkdir(parents=True, exist_ok=True)
    paths = [seti.save(dict(p["s"], spectra=p["spectra"]), work / f"{j}.h5") for j, p in enumerate(planted)]
    pipelines._tool("turbo_curves.py", work / "turbo.json", ",".join(map(str, matched.CUTS_TURBO)), "true", *paths)
    turbo = json.loads((work / "turbo.json").read_text(encoding="utf-8"))
    s = cad[0]["s"]
    half = cad[0]["raw"].shape[0] * s["tsamp"] / 2 - s["tsamp"] / 2      # from turboSETI's reference to mid-look
    rows, differ = [], []
    for i, (t, r) in enumerate(zip(ts, rec["tones"])):
        t_f = {j: matched.where(cad, t, j)[1] for j in matched.TRUE}
        t_f_turbo = {j: f + t["drift"] * cad[j]["s"]["tsamp"] / 2 / 1e6 for j, f in t_f.items()}
        at = {}
        for c in CUTS:
            kept = matched._turbo_kept(next(e["rows"] for e in turbo["events"] if tuple(e["as_on"]) == matched.TRUE
                                            and e["cut"] == float(c)))
            plain = rec["turboseti"]["true_plain"][matched.ck(c)]
            at[c] = {key: turbo_status(t_f_turbo, t["drift"], kept, plain, turbo["look_hits"], c, h, tol)
                     for key, (h, tol) in _scorings(t["drift"], half).items()}
            if at[c]["published"] != _turbo_published(r, c):
                differ.append([i, c, at[c]["published"], _turbo_published(r, c)])
        rows.append({"drift": t["drift"], "s_in": t["s_in"], "bin": t["bin"], "at": at})
    return {"target": target, "block": k, "class": rec["class"], "half_look_s": half, "tones": rows,
            "published_reproduced": not differ, "differ": differ[:20], "kind": "measured"}


def turbo_record_problems(rec, target, k, matched_rec, code=records.code_problems):
    """As record_problems, with the published statuses turboSETI's."""
    import matched
    name = f"{target} {k} (turboSETI)"
    if not isinstance(rec, dict):
        return [f"{name}: no record"]
    out = []
    if (rec.get("target"), rec.get("block"), rec.get("class")) != (target, k, matched_rec.get("class")):
        out.append(f"{name}: the record is of another block")
    tones, want = rec.get("tones", []), matched_rec.get("tones", [])
    if len(tones) != matched.TONES or len(want) != matched.TONES:
        out.append(f"{name}: {len(tones)} signals, not {matched.TONES}")
    elif any((round(t.get("drift", 0), 6), t.get("s_in"), t.get("bin")) != (round(w["drift"], 6), w["s_in"], w["bin"])
             for t, w in zip(tones, want)):
        out.append(f"{name}: the signals are not the matched record's")
    elif any(t["at"].get(c, {}).get("published", "missing") != _turbo_published(w, c)
             for t, w in zip(tones, want) for c in CUTS):
        out.append(f"{name}: the published statuses are not the matched record's")
    if any(set(t.get("at", {})) != set(CUTS) or any(set(t["at"][c]) != set(KEYS) or
                                                     any(t["at"][c][key] not in STATUSES for key in KEYS)
                                                     for c in CUTS) for t in tones):
        out.append(f"{name}: a signal is not scored at both cuts in all three ways")
    if rec.get("published_reproduced") is not True:
        out.append(f"{name}: the published statuses were not reproduced")
    out += [f"{name}: {x}" for x in code(rec.get("provenance"), own=("tools/midlook.py",))]
    return out


def turbo_run(target, say=print, from_end=False):
    import seti
    import store
    if target in DC_BY_CHUNK:
        os.environ["SSY_DC_BY_CHUNK"] = "1"
    seti.reading.set_threads(READ_THREADS)
    db = store.connect_readonly()
    _, urls = store.cadence_files(db, target)
    db.close()
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    out = TURBO / target
    todo = []
    for p in sorted(_base(target).glob("block_*.json")):
        k = int(p.stem.split("_")[1])
        rec = json.loads(p.read_text(encoding="utf-8"))
        if not yoke.whole(out / f"block_{k:03d}.json", lambda r, k=k, rec=rec: not turbo_record_problems(r, target, k, rec)):
            todo.append((k, rec))
    say(f"{target} (turboSETI): {len(todo)} blocks" + (", from the end" if from_end else ""))
    for k, rec in (todo[::-1] if from_end else todo):
        path = out / f"block_{k:03d}.json"
        with records.claim(path) as mine:
            if not mine or yoke.whole(path, lambda r, k=k, rec=rec: not turbo_record_problems(r, target, k, rec)):
                continue
            work = out / f"work_{os.getpid()}"
            try:
                got = turbo_block(target, k, rec, seti.read_looks(urls, *block_list[k]), urls, work)
            finally:
                yoke.remove_tree(work) if work.exists() else None
            yoke.write(path, got, indent=None, stamp=True)
        n = lambda key: sum(t["at"]["10"][key] == "recovered" for t in got["tones"])  # noqa: E731
        say(f"  {target} block {k} (turboSETI): at 10, published {n('published')}, mid {n('mid')}, mid scaled "
            f"{n('mid_scaled')}; reproduced {got['published_reproduced']}", flush=True)


def turbo_tables(say=print):
    """Both pipelines' recovery under the three scorings, over the blocks whose records are whole for both."""
    out = {"sessions": {}, "kind": "measured"}
    for target in TARGETS:
        want = {int(p.stem.split("_")[1]): json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(_base(target).glob("block_*.json"))}
        cell = {"of": len(want), "blocks": 0}
        by = {c: {} for c in CUTS}
        problems = []
        for k, m in want.items():
            tp, op = TURBO / target / f"block_{k:03d}.json", OUT / target / f"block_{k:03d}.json"
            if not tp.exists():
                continue
            tr, orec = json.loads(tp.read_text(encoding="utf-8")), json.loads(op.read_text(encoding="utf-8"))
            got = turbo_record_problems(tr, target, k, m) + record_problems(orec, target, k, m)
            if got:
                problems.extend(got)
                continue
            cell["blocks"] += 1
            for c in CUTS:
                for t, o in zip(tr["tones"], orec["tones"]):
                    b = by[c].setdefault(str(t["bin"]), {"signals": 0, **{f"{who}_{key}": 0 for who in
                                                                          ("ours", "turboseti") for key in KEYS}})
                    b["signals"] += 1
                    for key in KEYS:
                        b[f"turboseti_{key}"] += t["at"][c][key] == "recovered"
                        b[f"ours_{key}"] += o["at"][c][key] == "recovered"
        if problems:
            raise yoke.Refusal("INVALID_REQUEST", f"{target}: {len(problems)} problems, first {problems[:3]}")
        for c in CUTS:
            rows = dict(sorted(by[c].items()))
            keys = next(iter(rows.values()), {}).keys()
            cell[f"at_{c}"] = {"by_drift_bin": rows, "all": {key: sum(v[key] for v in rows.values()) for key in keys}}
        out["sessions"][target] = cell
        say(f"{target}: {cell['blocks']} of {cell['of']} blocks; at 10 {cell['at_10']['all']}")
    yoke.write(OUT / "turbo_tables.json", out, indent=1, stamp=True)
    return out


SHIFTS_HZ = (-12000, -6000, -3000, -1500, 1500, 3000, 6000, 12000)   # well inside the ~26 kHz between signals


def _t_f(rec, tone):
    """A planted signal's MHz at each true ON look's start, from the matched record (its f_mhz is look 0's, to 1 Hz)."""
    import matched
    t0 = rec["tstarts"][0]
    return {j: tone["f_mhz"] + tone["drift"] * (rec["tstarts"][j] - t0) * 86400 / 1e6 for j in matched.TRUE}


def _scorings(drift, half):
    return {"published": (0.0, tolerances(drift, False)), "mid": (half, tolerances(drift, False)),
            "mid_scaled": (half, tolerances(drift, True))}


def false_association_checks(pairs):
    """From the records alone, for each scoring: how often the unplanted block's own events match a signal's place
    by chance (at the signal and at places shifted by SHIFTS_HZ), how many pairs of planted signals lie within each
    other's tolerances (so one event could be credited twice), and the frequency and drift errors of the signals
    each scoring recovers, apart. `pairs`: (matched record, mid-look record) of each block."""
    import numpy as np
    out = {}
    for c in CUTS:
        cell = {k: {"at_signal": [0, 0], "shifted": [0, 0], "close_pairs": 0} for k in KEYS}
        err = {k: {} for k in KEYS}
        for rec, ml in pairs:
            half = ml["half_look_s"]
            plain = rec["ours"]["true_plain"][c]
            mids = []
            for tone, row in zip(rec["tones"], ml["tones"]):
                t_f = _t_f(rec, tone)
                mids.append((tone["f_mhz"] + tone["drift"] * half / 1e6, tone["drift"]))
                for key, (h, tol) in _scorings(tone["drift"], half).items():
                    def hit(shift, h=h, tol=tol):
                        f = {j: v + shift / 1e6 for j, v in t_f.items()}
                        return any((lambda ok, n: ok == n == 3)(*fit(f, tone["drift"], ev, h, tol)) for ev in plain)
                    cell[key]["at_signal"][0] += hit(0.0)
                    cell[key]["at_signal"][1] += 1
                    cell[key]["shifted"][0] += sum(hit(x) for x in SHIFTS_HZ)
                    cell[key]["shifted"][1] += len(SHIFTS_HZ)
                    near = tone["ours"][c]["nearest"]
                    if near and row["at"][c][key] == "recovered":
                        e = err[key].setdefault(str(tone["bin"]), [[], [], []])
                        e[0].append(abs(near["df_hz"]))
                        e[1].append(abs(near["df_hz"] + near["dd_hz_s"] * half))
                        e[2].append(abs(near["dd_hz_s"]))
            for i in range(len(mids)):
                for k2 in range(i + 1, len(mids)):
                    (fa, da), (fb, db) = mids[i], mids[k2]
                    for key, (_, tol) in _scorings(max(abs(da), abs(db)), half).items():
                        cell[key]["close_pairs"] += abs(fa - fb) * 1e6 <= 2 * tol[0] and abs(da - db) <= 2 * tol[1]
        q = lambda v: [round(float(x), 3) for x in np.percentile(v, [50, 90])] if v else None  # noqa: E731
        for key in KEYS:
            x = cell[key]
            x["at_signal_rate"] = round(x["at_signal"][0] / x["at_signal"][1], 5)
            x["shifted_rate"] = round(x["shifted"][0] / x["shifted"][1], 5)
            x["errors_median_and_90th"] = {b: {"frequency_at_start_hz": q(v[0]), "frequency_at_mid_hz": q(v[1]),
                                               "drift_hz_s": q(v[2]), "signals": len(v[0])}
                                           for b, v in sorted(err[key].items())}
        out[c] = cell
    return out


def checks(say=print):
    """false_association_checks over every session's blocks, each record checked whole first."""
    out = {"sessions": {}, "shifts_hz": list(SHIFTS_HZ), "kind": "measured"}
    for target in TARGETS:
        pairs = []
        for p in sorted(_base(target).glob("block_*.json")):
            k = int(p.stem.split("_")[1])
            rec = json.loads(p.read_text(encoding="utf-8"))
            mp = OUT / target / f"block_{k:03d}.json"
            ml = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else None
            got = record_problems(ml, target, k, rec)
            if got:
                raise yoke.Refusal("INVALID_REQUEST", f"{target}: {got[:3]}")
            pairs.append((rec, ml))
        out["sessions"][target] = false_association_checks(pairs)
        for key in KEYS:
            x = out["sessions"][target]["10"][key]
            say(f"{target} at 10, {key}: chance matches at the signal {x['at_signal'][0]} of {x['at_signal'][1]}, "
                f"shifted {x['shifted'][0]} of {x['shifted'][1]}; close pairs {x['close_pairs']}", flush=True)
    yoke.write(OUT / "association_checks.json", out, indent=1, stamp=True)
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "run" and len(sys.argv) > 2:
        run(sys.argv[2], from_end="--from-end" in sys.argv[3:])
    elif cmd == "tables":
        tables()
    elif cmd == "checks":
        checks()
    elif cmd == "turbo" and len(sys.argv) > 2:
        turbo_run(sys.argv[2], from_end="--from-end" in sys.argv[3:])
    elif cmd == "turbo-tables":
        turbo_tables()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
