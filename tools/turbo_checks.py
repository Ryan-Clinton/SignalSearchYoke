"""How much of the difference from turboSETI is the detector and how much the
cadence test, at matched false-candidate rates, and where turboSETI loses
planted signals (the turboSETI audit, docs/audits.md 3). Supplementary and
exploratory: the published comparison (matched.py, tools/turbo_curves.py,
turboSETI 2.3.2 as released) and steps 4, 10 and 12 are unchanged.

    python tools/turbo_checks.py reference    turboSETI's reported frequency and drift, on synthetic tones
    python tools/turbo_checks.py blocks       the block experiments below (16 blocks)
    python tools/turbo_checks.py all

**blocks**: eight blocks of the 2017 session and eight of the 2016 one (four
crowded and four clean of each, drawn at random, seed 12) read again and
planted with their records' own signals. Four pipelines, each a detector and
a cadence test:

| | detector | cadence test |
|---|---|---|
| ours | this search | this search's (onoff.judge) |
| turbo | turboSETI | turboSETI's (find_events, filter 3) |
| turbohits_ourtest | turboSETI | this search's, its hits from SNR 5 as shadow hits |
| ourhits_turbotest | this search | turboSETI's, this search's hits written as turboSETI writes its own |

and turboSETI with its zero-drift trial searched (turbo_zero). For each,
at every cut of the grid: three-look recovery of the planted signals (the
true ON looks) and the false-candidate control (the 19 wrong choices on the
unplanted blocks, distinct candidates joined by shared hits as matched.py
counts them). Each pipeline's matched cut by step 4's rule
(matched_tables._matched_cut) on these blocks, by session, and recovery
there. SNR scales differ between the detectors, so only matched cuts, not
equal ones, compare pipelines; with eight blocks a session the false rates
are rough (exploratory), unweighted by class.

Also, at SNR 10 and 30:
- **scaled tolerances**: ours and turbo scored with tolerances growing with
  drift, the same for both (scaled_tolerances), beside the published ones;
- **members**: for each signal turbo is credited with, per ON look: its
  event (rows grouped by Hit_ID) has a row with the same TopHitNum as the
  hit matched in the hit table (verified), a different one (disagrees), or
  no row (unknown: find_events left it out);
- **stages**: where turbo lost each planted signal; "another hit in the
  top-hit window" is a suspicion of suppression, not shown;
- **numbering**: ourhits_turbotest with this search's hits numbered
  strongest first instead of in channel order: how much find_events'
  deduplication by TopHitNum depends on the numbering alone;
- **threshold**: turboSETI's search at SNR 30 itself against the SNR 5
  search cut to > 30.

Each block's result records a fingerprint of the code that made it, and is
reused only if the code is the same.

Writes data/analysis/turbo_checks.json and turbo_reference.json.
"""
import hashlib
import itertools
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import matched  # noqa: E402
import matched_tables  # noqa: E402
import measure  # noqa: E402
import seti  # noqa: E402
import store  # noqa: E402
import yoke  # noqa: E402
from injection_checks import paired, _drift_bin  # noqa: E402

OUT = yoke.DATA / "analysis"
WORK = yoke.DATA / "analysis" / "turbo_work"
CUTS = (5, 6, 7, 8, 10, 12, 15, 20, 30, 50, 100)
SCORE = (10, 30)
SESSIONS = ("KIC8462852", "HIP17147")
MAX_DRIFT = 4.0
VARIANTS = ("ours", "turbo", "turbohits_ourtest", "ourhits_turbotest")
CODE = ("tools/turbo_checks.py", "tools/turbo_diag.py", "tools/injection_checks.py", "matched.py", "matched_tables.py",
        "onoff.py", "searching.py", "seti.py", "measure.py")
TRUE_KEY = "0,2,4"
CHOICES = list(itertools.combinations(range(6), 3))


def _say(*a):
    print(*a, flush=True)


def fingerprint():
    h = hashlib.sha256()
    for f in CODE:
        h.update((ROOT / f).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def turbo_order(hits, foff):
    """Hits in the order turboSETI's tophitsearch numbers its own: channel
    index rising, i.e. frequency rising when foff > 0 and falling when < 0."""
    return sorted(hits, key=lambda h: h["freq_mhz"] if foff > 0 else -h["freq_mhz"])


def _diag(spec, out):
    seti.need_turboseti()
    inp = out.with_suffix(".in.json")
    inp.write_text(json.dumps(spec), encoding="utf-8")
    done = subprocess.run([str(seti.TURBOSETI_PYTHON), "-I", str(ROOT / "tools" / "turbo_diag.py"), str(inp), str(out)],
                          capture_output=True, text=True, timeout=14400)
    if done.returncode:
        raise yoke.Refusal("INTERNAL_ERROR", f"turbo_diag.py failed: {done.stderr.strip()[-600:]}")
    return json.loads(out.read_text(encoding="utf-8"))


def _turbo_hits_as_ours(cad, look_hits, flats):
    """turboSETI's hits (its frequency at the first spectrum's middle) as this
    search's for onoff.judge: at the look's start, the box this search would
    have at the drift."""
    out = []
    for j, c in enumerate(cad):
        s = c["s"]
        n_t = c["spectra"].shape[0]
        span = max(n_t - 1, 1) * s["tsamp"]
        hs = []
        for h in look_hits[j]:
            k = h["drift_hz_s"] * span / (s["foff"] * 1e6)
            hs.append({"frequency_mhz": h["freq_mhz"] - h["drift_hz_s"] * s["tsamp"] / 2 / 1e6,
                       "drift_hz_s": h["drift_hz_s"], "snr": h["snr"],
                       "box_channels": max(1, math.ceil(abs(k) / max(n_t - 1, 1) - 1e-9))})
        hs.sort(key=lambda h: -h["snr"])
        out.append((hs, flats[j], True))
    return out


def _kept(cad, searched, ons, caches):
    out = {}
    for c in CUTS:
        looks, events, order = matched.our_events(cad, searched, ons, c, caches)
        out[c] = matched._our_kept(looks, events, order)
        for lk in looks:
            lk.flat = None
    return out


def _t_f(cad, t):
    t_f = {j: matched.where(cad, t, j)[1] for j in matched.TRUE}
    return t_f, {j: f + t["drift"] * cad[j]["s"]["tsamp"] / 2 / 1e6 for j, f in t_f.items()}


def _turbo_found(t_ft, drift, planted_rows, plain_rows, look_hits, cut):
    st = matched._status(t_ft, drift, matched._turbo_kept(planted_rows), matched._turbo_kept(plain_rows),
                         turboseti=True)
    on = matched._turbo_on_hits({"look_hits": look_hits}, t_ft, drift, cut)
    return st["three_looks"] == "recovered" and on == 3, st


def _match(hits, f, drift, cut=None):
    out = [h for h in hits if abs((h["freq_mhz"] - f) * 1e6) <= matched.TOL_HZ
           and abs(h["drift_hz_s"] - drift) <= matched.TOL_DRIFT and (cut is None or h["snr"] > cut)]
    return sorted(out, key=lambda h: -h["snr"])


def _window_hz(cad):
    s = cad[0]["s"]
    width = abs(s["foff"]) * 1e6
    step = width / (cad[0]["spectra"].shape[0] * s["tsamp"])
    return 2 * math.ceil(MAX_DRIFT / step) * width


class scaled_tolerances:
    """Within this, matched's tolerances (read by its matching when it runs)
    grow with the signal's drift, the same for every pipeline:
    +-max(6 Hz, 10 s x |drift|) and +-max(0.05, 0.08 x |drift|) Hz/s."""

    def __init__(self, drift):
        self.hz = max(matched.TOL_HZ, 10.0 * abs(drift))
        self.dd = max(matched.TOL_DRIFT, 0.08 * abs(drift))

    def __enter__(self):
        self.saved = (matched.TOL_HZ, matched.TOL_DRIFT)
        matched.TOL_HZ, matched.TOL_DRIFT = self.hz, self.dd

    def __exit__(self, *_):
        matched.TOL_HZ, matched.TOL_DRIFT = self.saved


def stage(t_ft, drift, hits, found, st, cut, window_hz):
    """Where turboSETI lost a planted signal (None if found), from its hit
    tables and its event status at the cut."""
    if found:
        return None
    for j in matched.TRUE:
        if not _match(hits[j], t_ft[j], drift):
            near = [h for h in hits[j] if abs((h["freq_mhz"] - t_ft[j]) * 1e6) <= window_hz]
            if any(abs((h["freq_mhz"] - t_ft[j]) * 1e6) <= 5 * matched.TOL_HZ
                   and abs(h["drift_hz_s"] - drift) <= 4 * matched.TOL_DRIFT for h in near):
                return "found at SNR 5, measured outside the tolerances"
            return "another hit in the top-hit window (suppression suspected, not shown)" if near else "no hit at SNR 5"
    for j in matched.TRUE:
        if not _match(hits[j], t_ft[j], drift, cut):
            return "a matching hit only at or under the cut"
    if st["three_looks"] is None:
        for j in matched.TRUE:
            h = _match(hits[j], t_ft[j], drift, cut)[0]
            for o in (1, 3, 5):
                if any(abs((x["freq_mhz"] - h["freq_mhz"]) * 1e6) <= window_hz and x["snr"] > cut for x in hits[o]):
                    return "an OFF hit over the cut in the window (veto likely)"
        return "hits over the cut in each ON look, no event"
    if st["three_looks"] == "false association":
        return "a false association (the unplanted block held it)"
    return "an event, not matching within the tolerances"


def members(t_ft, drift, hits, rows, cut):
    """For a signal credited to turboSETI: per ON look, "verified" (its event
    has a row there with the TopHitNum of the hit matched in that look's table),
    "disagrees" (a row with another), or "unknown" (no row: find_events left
    it out). Its event: the Hit_ID whose rows match the signal best."""
    by = {}
    for r in rows:
        by.setdefault(r["hit_id"], []).append(r)
    best, score = None, -1
    for hid, rs in by.items():
        n = sum(abs((r["freq_mhz"] - t_ft[r["look"]]) * 1e6) <= matched.TOL_HZ
                and abs(r["drift_hz_s"] - drift) <= matched.TOL_DRIFT for r in rs if r["look"] in t_ft)
        if n > score:
            best, score = hid, n
    rs = by.get(best, [])
    out = {}
    for j in matched.TRUE:
        h = _match(hits[j], t_ft[j], drift, cut)
        row = [r for r in rs if r["look"] == j]
        if not row:
            out[str(j)] = "unknown"
        elif h and row[0]["top_hit_num"] is not None and row[0]["top_hit_num"] == h[0]["top_hit_num"]:
            out[str(j)] = "verified"
        else:
            out[str(j)] = "disagrees"
    return out


def _picks(target):
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, target)
    db.close()
    base = matched.folder(target, session)
    meta = json.loads((base / "blocks.json").read_text(encoding="utf-8"))
    chosen = {int(b): c for b, c in meta["chosen"].items()}
    rng = np.random.default_rng(12)
    picks = sorted(int(b) for cls in ("crowded", "clean")
                   for b in rng.choice(sorted(b for b, c in chosen.items() if c == cls), 4, replace=False))
    return session, urls, base, chosen, picks


def block(target, session, urls, base, b, cls, block_list, say=_say):
    path = OUT / "turbo_checks" / f"{target}_{b:03d}.json"
    fp = fingerprint()
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if old.get("code") == fp:
            return old
        say(f"{path.name}: made by other code ({old.get('code')}, now {fp}); made again")
    rec = json.loads((base / f"block_{b:03d}.json").read_text(encoding="utf-8"))
    cad = matched._cadence(seti.read_looks(urls, *block_list[b]), urls)
    if [c["s"]["tstart"] for c in cad] != rec["tstarts"]:
        raise yoke.Refusal("INVALID_REQUEST", f"block {b} read again is not the one recorded")
    ts = rec["tones"]
    cad_p = [dict(c, spectra=p["spectra"]) for c, p in zip(cad, matched.plant(cad, ts))]
    work = WORK / f"{target}_{b:03d}"
    shutil.rmtree(work, ignore_errors=True)
    paths = {k: [seti.save(dict(c["s"], spectra=c["spectra"]), work / k / f"{j}.h5") for j, c in enumerate(cs)]
             for k, cs in (("plain", cad), ("planted", cad_p))}
    s_plain, s_planted = matched.our_search(cad), matched.our_search(cad_p)
    foff = cad[0]["s"]["foff"]

    def ours_list(searched):
        return [turbo_order([{"freq_mhz": h["frequency_mhz"], "drift_hz_s": h["drift_hz_s"], "snr": h["snr"]}
                             for h in x[0]], foff) for x in searched]
    diag = _diag({"planted": [str(p) for p in paths["planted"]], "plain": [str(p) for p in paths["plain"]],
                  "cuts": list(CUTS), "ours": {"planted": ours_list(s_planted), "plain": ours_list(s_plain)}},
                 work / "diag.json")
    th_plain = _turbo_hits_as_ours(cad, diag["plain"]["native"]["hits"], [x[1] for x in s_plain])
    th_planted = _turbo_hits_as_ours(cad_p, diag["planted"]["native"]["hits"], [x[1] for x in s_planted])
    caches_plain, caches_th = [{} for _ in range(6)], [{} for _ in range(6)]
    kept = {"ours": (_kept(cad_p, s_planted, matched.TRUE, [{} for _ in range(6)]),
                     _kept(cad, s_plain, matched.TRUE, caches_plain)),
            "turbohits_ourtest": (_kept(cad_p, th_planted, matched.TRUE, [{} for _ in range(6)]),
                                  _kept(cad, th_plain, matched.TRUE, caches_th))}

    # The false-candidate controls on the unplanted block: the 19 wrong choices.
    false = {}
    wrong = [ons for ons in CHOICES if ons != matched.TRUE]
    for v, searched, caches in (("ours", s_plain, caches_plain), ("turbohits_ourtest", th_plain, caches_th)):
        per_cut = {c: {} for c in CUTS}
        for ons in wrong:
            k = _kept(cad, searched, ons, caches)
            for c in CUTS:
                per_cut[c][str(ons)] = k[c]
        false[v] = {str(c): len(matched.shared_hits(per_cut[c])) for c in CUTS}
    for v, src in (("turbo", "native"), ("ourhits_turbotest", "ours_judged")):
        ev = diag["plain"][src]["events"]
        false[v] = {str(c): len(matched.shared_hits({ch: matched._turbo_kept(ev[ch][str(float(c))])
                                                     for ch in ev if ch != TRUE_KEY})) for c in CUTS}

    ours_hits_turbo_ref = [[{"freq_mhz": h["frequency_mhz"] + h["drift_hz_s"] * cad[j]["s"]["tsamp"] / 2 / 1e6,
                             "drift_hz_s": h["drift_hz_s"], "snr": h["snr"]} for h in s_planted[j][0]] for j in range(6)]
    window_hz = _window_hz(cad)
    rows = []
    for t in ts:
        t_f, t_ft = _t_f(cad, t)
        r = {"s_in": t["s_in"], "drift": t["drift"], "class": cls, "found": {v: [] for v in VARIANTS + ("turbo_zero",)}}
        for c in CUTS:
            cf = str(float(c))
            if matched._status(t_f, t["drift"], kept["ours"][0][c], kept["ours"][1][c])["three_looks"] == "recovered":
                r["found"]["ours"].append(c)
            if matched._status(t_f, t["drift"], kept["turbohits_ourtest"][0][c],
                               kept["turbohits_ourtest"][1][c])["three_looks"] == "recovered":
                r["found"]["turbohits_ourtest"].append(c)
            for v, src in (("turbo", "native"), ("turbo_zero", "zero_drift")):
                ok, _ = _turbo_found(t_ft, t["drift"], diag["planted"][src]["events"][TRUE_KEY][cf],
                                     diag["plain"][src]["events"][TRUE_KEY][cf], diag["planted"][src]["hits"], c)
                if ok:
                    r["found"][v].append(c)
            ok, _ = _turbo_found(t_ft, t["drift"], diag["planted"]["ours_judged"]["events"][TRUE_KEY][cf],
                                 diag["plain"]["ours_judged"]["events"][TRUE_KEY][cf], ours_hits_turbo_ref, c)
            if ok:
                r["found"]["ourhits_turbotest"].append(c)
        # The same signal judged from turboSETI searched at 30 itself, against its search at 5 cut to > 30.
        r["turbo_searched_at_30"] = _turbo_found(t_ft, t["drift"], diag["planted"]["direct"]["events"][TRUE_KEY]["30.0"],
                                                 diag["plain"]["direct"]["events"][TRUE_KEY]["30.0"],
                                                 diag["planted"]["direct"]["hits"], 30)[0]
        for c in SCORE:
            cf = str(float(c))
            nat_p = diag["planted"]["native"]["events"][TRUE_KEY][cf]
            nat_u = diag["plain"]["native"]["events"][TRUE_KEY][cf]
            hits = diag["planted"]["native"]["hits"]
            with scaled_tolerances(t["drift"]):
                r[f"ours_scaled_{c}"] = matched._status(t_f, t["drift"], kept["ours"][0][c],
                                                        kept["ours"][1][c])["three_looks"] == "recovered"
                r[f"turbo_scaled_{c}"] = _turbo_found(t_ft, t["drift"], nat_p, nat_u, hits, c)[0]
            ok, st = _turbo_found(t_ft, t["drift"], nat_p, nat_u, hits, c)
            r[f"stage_{c}"] = stage(t_ft, t["drift"], hits, ok, st, c, window_hz)
            r[f"members_{c}"] = members(t_ft, t["drift"], hits, nat_p, c) if ok else None
            r[f"ourhits_turbotest_snr_numbering_{c}"] = _turbo_found(
                t_ft, t["drift"], diag["planted"]["ours_judged_snr_numbering"]["events"][TRUE_KEY][cf],
                diag["plain"]["ours_judged"]["events"][TRUE_KEY][cf], ours_hits_turbo_ref, c)[0]
        rows.append(r)
    nat, direct = diag["planted"]["native"], diag["planted"]["direct"]
    key = lambda h: (round(h["freq_mhz"], 6), round(h["drift_hz_s"], 4))  # noqa: E731
    thr = {}
    for j in range(6):
        a = {key(h) for h in nat["hits"][j] if h["snr"] > 30}
        d = {key(h) for h in direct["hits"][j] if h["snr"] > 30}
        num_a = {key(h): h.get("top_hit_num") for h in nat["hits"][j] if h["snr"] > 30}
        num_d = {key(h): h.get("top_hit_num") for h in direct["hits"][j] if h["snr"] > 30}
        thr[str(j)] = {"cut_from_5": len(a), "searched_at_30": len(d), "only_cut": len(a - d), "only_searched": len(d - a),
                       # find_events deduplicates by TopHitNum, which numbers a look's hits afresh in each search
                       "same_hit_numbered_differently": sum(num_a[k] != num_d[k] for k in a & d)}
    ev_a = {(r["look"], round(r["freq_mhz"], 6)) for r in nat["events"][TRUE_KEY]["30.0"]}
    ev_d = {(r["look"], round(r["freq_mhz"], 6)) for r in direct["events"][TRUE_KEY]["30.0"]}
    out = {"target": target, "session": session, "block": b, "class": cls, "code": fp, "rows": rows, "false": false,
           "threshold": {"hits_by_look": thr, "event_rows_cut_from_5": len(ev_a), "event_rows_searched_at_30": len(ev_d),
                         "event_rows_differing": len(ev_a ^ ev_d)}}
    path.parent.mkdir(parents=True, exist_ok=True)
    yoke.write(path, out, indent=1)
    shutil.rmtree(work, ignore_errors=True)
    return out


def _rate(counts, rng):
    n = np.array(counts, float)
    lo, hi = np.percentile([rng.choice(n, len(n)).mean() for _ in range(4000)], [2.5, 97.5])
    return {"per_block": round(float(n.mean()), 4), "interval": [round(float(lo), 4), round(float(hi), 4)]}


def summarise(blocks):
    rows = [r for b in blocks for r in b["rows"]]
    rng = np.random.default_rng(1)
    out = {"signals": len(rows), "blocks": len(blocks)}
    out["found"] = {v: {str(c): sum(c in r["found"][v] for r in rows) for c in CUTS}
                    for v in VARIANTS + ("turbo_zero",)}
    sessions = {}
    for target in sorted({b["target"] for b in blocks}):
        bs = [b for b in blocks if b["target"] == target]
        rs = [r for b in bs for r in b["rows"]]
        curves, at = {}, {}
        for v in VARIANTS:
            curves[v] = {str(c): _rate([b["false"][v][str(c)] for b in bs], rng) for c in CUTS}
            cut = matched_tables._matched_cut(curves[v])["cut"]
            at[v] = {"cut": cut, "found": None if cut is None else sum(float(cut) in r["found"][v] for r in rs),
                     "false_per_block": None if cut is None else curves[v][cut]["per_block"],
                     "false_interval": None if cut is None else curves[v][cut]["interval"]}
        sessions[target] = {"blocks": len(bs), "signals": len(rs), "false_curves": curves, "matched": at}
    out["sessions"] = sessions

    def pair(get_a, get_b):
        x = [{"s_in": r["s_in"], "drift": r["drift"], "ours_1": get_a(r)} for r in rows]
        y = [{"s_in": r["s_in"], "drift": r["drift"], "ours_1": get_b(r)} for r in rows]
        p = paired(x, y)
        return {"all": p["all"]["ours_1"], "by_drift": {k: v["ours_1"] for k, v in p["by_drift"].items()}}
    pairs = {}
    for c in SCORE:
        pairs[str(c)] = {
            "turbo against turbo_zero (the zero-drift trial)":
                pair(lambda r, c=c: c in r["found"]["turbo"], lambda r, c=c: c in r["found"]["turbo_zero"]),
            "turbo against tolerances scaled with drift":
                pair(lambda r, c=c: c in r["found"]["turbo"], lambda r, c=c: r[f"turbo_scaled_{c}"]),
            "ours against tolerances scaled with drift":
                pair(lambda r, c=c: c in r["found"]["ours"], lambda r, c=c: r[f"ours_scaled_{c}"]),
            "ourhits_turbotest numbered by channel against by SNR (find_events' deduplication)":
                pair(lambda r, c=c: c in r["found"]["ourhits_turbotest"],
                     lambda r, c=c: r[f"ourhits_turbotest_snr_numbering_{c}"])}
    out["paired"] = pairs
    st, mem = {}, {}
    for c in SCORE:
        d = {}
        for r in rows:
            k = r[f"stage_{c}"] or "found"
            e = d.setdefault(k, {"all": 0, "by_class": {}, "by_drift": {}, "by_strength": {}})
            e["all"] += 1
            for key_, val in (("by_class", r["class"]), ("by_drift", _drift_bin(r["drift"])), ("by_strength", str(r["s_in"]))):
                e[key_][val] = e[key_].get(val, 0) + 1
        st[str(c)] = d
        ms = [r[f"members_{c}"] for r in rows if r[f"members_{c}"]]
        looks = [v for m in ms for v in m.values()]
        mem[str(c)] = {"credited": len(ms), "looks": {k: looks.count(k) for k in ("verified", "disagrees", "unknown")},
                       "signals_with_a_disagreement": sum("disagrees" in m.values() for m in ms),
                       "signals_all_verified": sum(all(v == "verified" for v in m.values()) for m in ms)}
    out["stages"], out["members"] = st, mem
    out["threshold"] = {
        "hits_only_in_the_cut_tables": sum(x["only_cut"] for b in blocks for x in b["threshold"]["hits_by_look"].values()),
        "hits_only_when_searched_at_30": sum(x["only_searched"] for b in blocks
                                             for x in b["threshold"]["hits_by_look"].values()),
        "event_rows_differing": sum(b["threshold"]["event_rows_differing"] for b in blocks),
        "hits_numbered_differently": sum(x.get("same_hit_numbered_differently", 0) for b in blocks
                                         for x in b["threshold"]["hits_by_look"].values()),
        "signals_at_30": pair(lambda r: 30 in r["found"]["turbo"], lambda r: r["turbo_searched_at_30"])["all"]}
    return out


def blocks(say=_say):
    done = []
    for target in SESSIONS:
        session, urls, base, chosen, picks = _picks(target)
        block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
        for b in picks:
            r = block(target, session, urls, base, b, chosen[b], block_list, say)
            done.append(r)
            f = summarise([r])["found"]
            say(f"{target} block {b} ({chosen[b]}): found at 10/30 "
                + ", ".join(f"{v} {f[v]['10']}/{f[v]['30']}" for v in f)
                + "; false at 10/30 " + ", ".join(f"{v} {r['false'][v]['10']}/{r['false'][v]['30']}" for v in VARIANTS))
    rec = {"blocks": [{"target": r["target"], "block": r["block"], "class": r["class"]} for r in done],
           "sample": "of each of the 2017 and 2016 sessions, 4 crowded and 4 clean blocks at random (seed 12)",
           "turboseti": "2.3.2 as released; turbo_zero sets min_drift to -1 after FindDoppler is made",
           "code": fingerprint(), **summarise(done), "kind": "measured"}
    yoke.write(OUT / "turbo_checks.json", rec, indent=1, stamp=True)
    for t, s in rec["sessions"].items():
        say(f"{t}: matched cuts " + ", ".join(f"{v} {x['cut']} ({x['found']} found, {x['false_per_block']} false)"
                                              for v, x in s["matched"].items()))
    return rec


def track_match(f_hit, d_hit, f_sig, d_sig, span, t_ref=0.0):
    """A hit matches a signal along its track: drift within TOL_DRIFT, and the
    hit's line (its frequency at t_ref after the look's start) within TOL_HZ
    of the signal's (at the look's start) at some moment of the look."""
    if abs(d_hit - d_sig) > matched.TOL_DRIFT:
        return False
    a0 = (f_hit - d_hit * t_ref / 1e6 - f_sig) * 1e6
    a1 = a0 + (d_hit - d_sig) * span
    return min(abs(a0), abs(a1)) <= matched.TOL_HZ or (a0 > 0) != (a1 > 0)


def reference(say=_say):
    """turboSETI's reported frequency and drift for strong synthetic tones,
    against where the tone is at the look's start and at the first spectrum's
    middle (the point the comparison matches turboSETI at), over the drifts
    and six places within a channel; and whether each would be credited by
    the comparison's point match and by a match along the track."""
    import pipelines
    rows = []
    rng = np.random.default_rng(12)
    work = WORK / "reference"
    foff, tsamp, fch1, n_f, n_t = -2.7939677238464355e-06, 18.253611008, 2000.0, 65536, 16
    span = n_t * tsamp
    fracs = (0.0, 0.17, 0.33, 0.5, 0.67, 0.83)
    for drift in [x / 2 for x in range(-8, 9)]:
        files = []
        for j, frac in enumerate(fracs):
            noise = rng.chisquare(102, size=(n_t, n_f)) * 1e3
            sigma = float(np.median(measure.channel_noise(noise)))
            p = measure.plant(noise, [(30000.0 + frac, drift, 200 * sigma / 4)], tsamp, foff)
            sl = {"spectra": p, "fch1": fch1, "foff": foff, "tsamp": tsamp, "tstart": 60000.0 + j * 330 / 86400,
                  "target": "SYNTH" if j % 2 == 0 else f"OFF{j}", "first_channel": 0, "coarse_channel": n_f,
                  "nchans": n_f}
            files.append(seti.save(sl, work / f"{drift}" / f"{j}.h5"))
        out = work / f"{drift}" / "t.json"
        pipelines._tool("turbo_curves.py", out, "10", "true", *files)
        rec = json.loads(out.read_text(encoding="utf-8"))
        for j, frac in enumerate(fracs):
            f_start = fch1 + (30000.0 + frac) * foff
            f_mid = f_start + drift * tsamp / 2 / 1e6
            near = [h for h in rec["look_hits"][j] if abs((h["freq_mhz"] - f_start) * 1e6) < 300]
            if not near:
                rows.append({"drift": drift, "start_fraction": frac, "found": False})
                continue
            best = max(near, key=lambda h: h["snr"])
            hz_mid = (best["freq_mhz"] - f_mid) * 1e6
            dd = best["drift_hz_s"] - drift
            rows.append({"drift": drift, "start_fraction": frac, "found": True, "snr": round(best["snr"], 1),
                         "hz_from_start": round((best["freq_mhz"] - f_start) * 1e6, 3),
                         "hz_from_first_spectrum_middle": round(hz_mid, 3), "drift_error": round(dd, 4),
                         "point_match": abs(hz_mid) <= matched.TOL_HZ and abs(dd) <= matched.TOL_DRIFT,
                         "track_match": track_match(best["freq_mhz"], best["drift_hz_s"], f_start, drift, span,
                                                    t_ref=tsamp / 2)})
        found = [r for r in rows if r["drift"] == drift and r["found"]]
        say(f"reference, drift {drift:+.1f}: found {len(found)} of {len(fracs)}; point match "
            f"{sum(r['point_match'] for r in found)}, track match {sum(r['track_match'] for r in found)}")
    shutil.rmtree(work, ignore_errors=True)
    by = {}
    for r in rows:
        d = by.setdefault(_drift_bin(r["drift"]), {"tones": 0, "found": 0, "point_match": 0, "track_match": 0,
                                                   "largest_hz_off": 0.0, "largest_drift_off": 0.0})
        d["tones"] += 1
        if r["found"]:
            d["found"] += 1
            d["point_match"] += r["point_match"]
            d["track_match"] += r["track_match"]
            d["largest_hz_off"] = max(d["largest_hz_off"], abs(r["hz_from_first_spectrum_middle"]))
            d["largest_drift_off"] = max(d["largest_drift_off"], abs(r["drift_error"]))
    rec = {"rows": rows, "by_drift": by, "channel_hz": abs(foff) * 1e6,
           "tolerances": [matched.TOL_HZ, matched.TOL_DRIFT],
           "mechanism": "turboSETI 2.3.2 searches drifts past about one channel a spectrum in drift blocks: each "
                        "spectrum rolled by a whole number of channels, then a Taylor tree summing one channel a "
                        "spectrum along approximate paths, with no sum over the channels a signal smears across in "
                        "a spectrum (find_doppler.py, populate_tree, flt). The path that catches most of a smeared "
                        "signal can start and slope away from it: read from the code, consistent with the errors "
                        "here, not shown separately.",
           "kind": "measured"}
    yoke.write(OUT / "turbo_reference.json", rec, indent=1, stamp=True)
    say(f"reference by drift: {by}")
    return rec


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("reference", "all"):
        reference()
    if what in ("blocks", "all"):
        blocks()


if __name__ == "__main__":
    main()
