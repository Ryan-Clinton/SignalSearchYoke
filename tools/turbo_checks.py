"""How much of the difference from turboSETI is the detector and how much the
cadence test, and where turboSETI loses planted signals (comparable.md; the
turboSETI audit, docs/audits.md 3). Supplementary: the published comparison
(matched.py, tools/turbo_curves.py, turboSETI 2.3.2 as released) and steps
4, 10 and 12 are unchanged.

    python tools/turbo_checks.py reference    turboSETI's frequency reference time, on synthetic tones
    python tools/turbo_checks.py blocks       the block experiments below (16 blocks)
    python tools/turbo_checks.py all

**blocks**: eight blocks of the 2017 session and eight of the 2016 one (four
crowded and four clean of each, drawn at random, seed 12) read again and
planted with their records' own signals. Each pipeline's three-look
recovery at SNR 10 and 30, five ways:

| | detector | cadence test |
|---|---|---|
| this search, as published | this search | this search's (onoff.judge) |
| turboSETI, as published | turboSETI | turboSETI's (find_events, filter 3) |
| turboSETI with the zero-drift trial | turboSETI, min_drift below 0 | turboSETI's |
| turboSETI's hits, this search's test | turboSETI | this search's |
| this search's hits, turboSETI's test | this search | turboSETI's |

this search's test on turboSETI's hits uses its hits from SNR 5 as shadow
hits, as it does its own; turboSETI's test on this search's hits takes them
written as turboSETI writes its own (tools/turbo_diag.py). Paired, signal by
signal, so the detector's part and the cadence test's part can be read off.

Also, for turboSETI as published:
- **members**: its event table can leave out a look's row when two looks'
  hits share a TopHitNum (each look numbers its own); recovery is credited
  from its event and its hit tables together. For each signal credited: does
  its event have a row in each ON look, and are the hits matched in the hit
  tables the event's own (same TopHitNum in that look)?
- **stages**: where each planted signal is lost, the first of: no hit at SNR
  5 matching it in some ON look (a stronger hit within the top-hit window
  there: suppressed; none: not found); a matching hit only at or under the
  cut; matching hits over the cut in each ON look but no event (an OFF hit
  over the cut in the window: vetoed; none: not associated); an event not
  matching within the tolerances. By S_in, drift and class.
- **threshold**: its search run at SNR 30 itself against the SNR 5 search cut
  to > 30 (what turbo_curves does): the hits and events of each.

Writes data/analysis/turbo_checks.json and turbo_reference.json.
"""
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
import measure  # noqa: E402
import seti  # noqa: E402
import store  # noqa: E402
import yoke  # noqa: E402
from injection_checks import paired, _drift_bin  # noqa: E402

OUT = yoke.DATA / "analysis"
WORK = yoke.DATA / "analysis" / "turbo_work"
CUTS = (10, 30)
SESSIONS = ("KIC8462852", "HIP17147")
MAX_DRIFT = 4.0


def _say(*a):
    print(*a, flush=True)


def _diag(spec, out):
    seti.need_turboseti()
    inp = out.with_suffix(".in.json")
    inp.write_text(json.dumps(spec), encoding="utf-8")
    done = subprocess.run([str(seti.TURBOSETI_PYTHON), "-I", str(ROOT / "tools" / "turbo_diag.py"), str(inp), str(out)],
                          capture_output=True, text=True, timeout=14400)
    if done.returncode:
        raise yoke.Refusal("INTERNAL_ERROR", f"turbo_diag.py failed: {done.stderr.strip()[-600:]}")
    return json.loads(out.read_text(encoding="utf-8"))


def _turbo_hits_as_ours(cad, look_hits, flats, cut):
    """turboSETI's hits (its frequency at the first spectrum's middle) as this
    search's for onoff.judge: at the look's start, the box this search would
    have at the drift; those under `cut` shadow hits."""
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


def _kept_by_cut(cad, searched):
    caches = [{} for _ in range(6)]
    out = {}
    for c in CUTS:
        looks, events, order = matched.our_events(cad, searched, matched.TRUE, c, caches)
        out[c] = matched._our_kept(looks, events, order)
        for lk in looks:
            lk.flat = None
    return out


def _turbo_status(cad, t, events_planted, events_plain, look_hits, cut):
    t_f = {j: matched.where(cad, t, j)[1] for j in matched.TRUE}
    t_ft = {j: f + t["drift"] * cad[j]["s"]["tsamp"] / 2 / 1e6 for j, f in t_f.items()}
    st = matched._status(t_ft, t["drift"], matched._turbo_kept(events_planted), matched._turbo_kept(events_plain),
                         turboseti=True)
    on = matched._turbo_on_hits({"look_hits": look_hits}, t_ft, t["drift"], cut)
    return st, on, t_ft


def _match(hits, f, drift, cut=None):
    """The hits matching a signal (within the tolerances), strongest first."""
    out = [h for h in hits if abs((h["freq_mhz"] - f) * 1e6) <= matched.TOL_HZ
           and abs(h["drift_hz_s"] - drift) <= matched.TOL_DRIFT and (cut is None or h["snr"] > cut)]
    return sorted(out, key=lambda h: -h["snr"])


def _window_hz(cad):
    s = cad[0]["s"]
    width = abs(s["foff"]) * 1e6
    step = width / (cad[0]["spectra"].shape[0] * s["tsamp"])
    return 2 * math.ceil(MAX_DRIFT / step) * width


def _stage(cad, t, diag, cut, window_hz):
    """Where turboSETI as published lost a planted signal (None if found)."""
    hits = diag["planted"]["native"]["hits"]
    st, on, t_ft = _turbo_status(cad, t, diag["planted"]["native"]["events"][str(float(cut))],
                                 diag["plain"]["native"]["events"][str(float(cut))], hits, cut)
    if st["three_looks"] == "recovered" and on == 3:
        return None
    for j in matched.TRUE:
        if not _match(hits[j], t_ft[j], t["drift"]):
            near = [h for h in hits[j] if abs((h["freq_mhz"] - t_ft[j]) * 1e6) <= window_hz]
            if any(abs((h["freq_mhz"] - t_ft[j]) * 1e6) <= 5 * matched.TOL_HZ
                   and abs(h["drift_hz_s"] - t["drift"]) <= 4 * matched.TOL_DRIFT for h in near):
                return "found at SNR 5, measured outside the tolerances"
            return "another hit in the top-hit window (it can suppress)" if near else "no hit at SNR 5"
    for j in matched.TRUE:
        if not _match(hits[j], t_ft[j], t["drift"], cut):
            return "a matching hit only at or under the cut"
    if st["three_looks"] is None:
        for j in matched.TRUE:
            h = _match(hits[j], t_ft[j], t["drift"], cut)[0]
            for o in (1, 3, 5):
                if any(abs((x["freq_mhz"] - h["freq_mhz"]) * 1e6) <= window_hz and x["snr"] > cut for x in hits[o]):
                    return "vetoed: an OFF hit over the cut in the window"
        return "hits over the cut in each ON look, no event"
    if st["three_looks"] == "false association":
        return "a false association (the unplanted block held it)"
    return "an event, not matching within the tolerances"


def _members(cad, t, diag, cut):
    """For a signal turboSETI as published is credited with: (its event's ON
    looks with a row, whether the matched hit-table hits are the event's own)."""
    hits = diag["planted"]["native"]["hits"]
    rows = diag["planted"]["native"]["events"][str(float(cut))]
    st, on, t_ft = _turbo_status(cad, t, rows, diag["plain"]["native"]["events"][str(float(cut))], hits, cut)
    if not (st["three_looks"] == "recovered" and on == 3):
        return None
    mine = [r for r in rows if abs((r["freq_mhz"] - t_ft[r["look"]]) * 1e6) <= matched.TOL_HZ
            and abs(r["drift_hz_s"] - t["drift"]) <= matched.TOL_DRIFT]
    looks_with_row = sorted({r["look"] for r in mine})
    same = True
    for j in matched.TRUE:
        h = _match(hits[j], t_ft[j], t["drift"], cut)[0]
        row = [r for r in mine if r["look"] == j]
        if row and row[0]["hit_id"] is not None and h.get("hit_id") is not None and row[0]["hit_id"] != h["hit_id"]:
            same = False
    return {"looks_with_a_row": len(looks_with_row), "matched_hits_are_the_events": same}


class scaled_tolerances:
    """Within this, matched's tolerances (which its matching reads when it
    runs) scale with the signal's drift, the same for every pipeline:
    +-max(6 Hz, 10 s x |drift|) and +-max(0.05, 0.08 x |drift|) Hz/s. At fast
    drifts turboSETI reports a strong signal's frequency up to 36 Hz and its
    drift up to 0.23 Hz/s from the truth (turbo_reference.json), which the
    published +-6 Hz, +-0.05 Hz/s do not credit."""

    def __init__(self, drift):
        self.hz = max(matched.TOL_HZ, 10.0 * abs(drift))
        self.dd = max(matched.TOL_DRIFT, 0.08 * abs(drift))

    def __enter__(self):
        self.saved = (matched.TOL_HZ, matched.TOL_DRIFT)
        matched.TOL_HZ, matched.TOL_DRIFT = self.hz, self.dd

    def __exit__(self, *_):
        matched.TOL_HZ, matched.TOL_DRIFT = self.saved


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


def block(target, session, urls, base, b, cls, block_list):
    path = OUT / "turbo_checks" / f"{target}_{b:03d}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
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

    def ours_list(searched):
        return [[{"freq_mhz": h["frequency_mhz"], "drift_hz_s": h["drift_hz_s"], "snr": h["snr"]} for h in x[0]]
                for x in searched]
    diag = _diag({"planted": [str(p) for p in paths["planted"]], "plain": [str(p) for p in paths["plain"]],
                  "cuts": list(CUTS), "ours": {"planted": ours_list(s_planted), "plain": ours_list(s_plain)}},
                 work / "diag.json")
    ours_planted, ours_plain = _kept_by_cut(cad_p, s_planted), _kept_by_cut(cad, s_plain)
    th_planted = _kept_by_cut(cad_p, _turbo_hits_as_ours(cad_p, diag["planted"]["native"]["hits"],
                                                          [x[1] for x in s_planted], 0))
    th_plain = _kept_by_cut(cad, _turbo_hits_as_ours(cad, diag["plain"]["native"]["hits"], [x[1] for x in s_plain], 0))
    window_hz = _window_hz(cad)
    rows = []
    for t in ts:
        t_f = {j: matched.where(cad, t, j)[1] for j in matched.TRUE}
        r = {"s_in": t["s_in"], "drift": t["drift"], "class": cls}
        for c in CUTS:
            r[f"ours_{c}"] = matched._status(t_f, t["drift"], ours_planted[c], ours_plain[c])["three_looks"] == "recovered"
            for name, v in (("turbo", "native"), ("turbo_zero", "zero_drift")):
                st, on, _ = _turbo_status(cad, t, diag["planted"][v]["events"][str(float(c))],
                                          diag["plain"][v]["events"][str(float(c))], diag["planted"][v]["hits"], c)
                r[f"{name}_{c}"] = st["three_looks"] == "recovered" and on == 3
            r[f"turbohits_ourtest_{c}"] = matched._status(t_f, t["drift"], th_planted[c], th_plain[c])["three_looks"] \
                == "recovered"
            t_ft = {j: f + t["drift"] * cad[j]["s"]["tsamp"] / 2 / 1e6 for j, f in t_f.items()}
            stb = matched._status(t_ft, t["drift"], matched._turbo_kept(diag["planted"]["ours_judged"]["events"][str(float(c))]),
                                  matched._turbo_kept(diag["plain"]["ours_judged"]["events"][str(float(c))]),
                                  turboseti=True)
            ours_hits = [[{"freq_mhz": h["frequency_mhz"] + h["drift_hz_s"] * cad[j]["s"]["tsamp"] / 2 / 1e6,
                           "drift_hz_s": h["drift_hz_s"], "snr": h["snr"]} for h in s_planted[j][0]] for j in range(6)]
            r[f"ourhits_turbotest_{c}"] = stb["three_looks"] == "recovered" and \
                matched._turbo_on_hits({"look_hits": ours_hits}, t_ft, t["drift"], c) == 3
            with scaled_tolerances(t["drift"]):
                r[f"ours_scaled_{c}"] = matched._status(t_f, t["drift"], ours_planted[c],
                                                        ours_plain[c])["three_looks"] == "recovered"
                st2, on2, _ = _turbo_status(cad, t, diag["planted"]["native"]["events"][str(float(c))],
                                            diag["plain"]["native"]["events"][str(float(c))],
                                            diag["planted"]["native"]["hits"], c)
                r[f"turbo_scaled_{c}"] = st2["three_looks"] == "recovered" and on2 == 3
            r[f"stage_{c}"] = _stage(cad, t, diag, c, window_hz)
            r[f"members_{c}"] = _members(cad, t, diag, c)
        rows.append(r)
    thr = {}
    nat = diag["planted"]["native"]
    direct = diag["planted"]["direct"]
    key = lambda h: (round(h["freq_mhz"], 6), round(h["drift_hz_s"], 4))  # noqa: E731
    for j in range(6):
        a = {key(h) for h in nat["hits"][j] if h["snr"] > 30}
        d = {key(h) for h in direct["hits"][j] if h["snr"] > 30}
        thr[j] = {"cut_from_5": len(a), "searched_at_30": len(d), "only_cut": len(a - d), "only_searched": len(d - a)}
    ev_a = {(r["look"], round(r["freq_mhz"], 6)) for r in nat["events"]["30.0"]}
    ev_d = {(r["look"], round(r["freq_mhz"], 6)) for r in direct["events"]["30.0"]}
    out = {"target": target, "block": b, "class": cls, "rows": rows,
           "threshold": {"hits_by_look": thr, "event_rows_cut_from_5": len(ev_a), "event_rows_searched_at_30": len(ev_d),
                         "event_rows_differing": len(ev_a ^ ev_d)}}
    path.parent.mkdir(parents=True, exist_ok=True)
    yoke.write(path, out, indent=1)
    shutil.rmtree(work, ignore_errors=True)
    return out


VARIANTS = ("ours", "turbo", "turbo_zero", "turbohits_ourtest", "ourhits_turbotest", "ours_scaled", "turbo_scaled")


def summarise(blocks):
    rows = [r for b in blocks for r in b["rows"]]
    tot = {f"{v}_{c}": int(sum(r[f"{v}_{c}"] for r in rows)) for v in VARIANTS for c in CUTS}

    def pair(a, b):
        out = {}
        for c in CUTS:
            x = [{"s_in": r["s_in"], "drift": r["drift"], "found": r[f"{a}_{c}"]} for r in rows]
            y = [{"s_in": r["s_in"], "drift": r["drift"], "found": r[f"{b}_{c}"]} for r in rows]
            for d in x + y:
                d[f"ours_{c}"] = d.pop("found")
            p = paired(x, y)
            out[str(c)] = {"all": p["all"][f"ours_{c}"],
                           "by_drift": {k: v[f"ours_{c}"] for k, v in p["by_drift"].items()}}
        return out
    pairs = {"turboSETI native against the zero-drift trial": pair("turbo", "turbo_zero"),
             "this search native against turboSETI's hits through this search's test (the detector, one test)": pair("ours", "turbohits_ourtest"),
             "turboSETI native against this search's hits through turboSETI's test (the detector, one test)": pair("turbo", "ourhits_turbotest"),
             "this search native against this search's hits through turboSETI's test (the cadence test, one detector)": pair("ours", "ourhits_turbotest"),
             "turboSETI native against turboSETI's hits through this search's test (the cadence test, one detector)": pair("turbo", "turbohits_ourtest"),
             "turboSETI, the published tolerances against tolerances scaled with drift": pair("turbo", "turbo_scaled"),
             "this search, the published tolerances against tolerances scaled with drift": pair("ours", "ours_scaled")}
    stages, members = {}, {}
    for c in CUTS:
        st = {}
        for r in rows:
            k = r[f"stage_{c}"] or "found"
            d = st.setdefault(k, {"all": 0, "by_class": {}, "by_drift": {}, "by_strength": {}})
            d["all"] += 1
            for key_, val in (("by_class", r["class"]), ("by_drift", _drift_bin(r["drift"])), ("by_strength", str(r["s_in"]))):
                d[key_][val] = d[key_].get(val, 0) + 1
        stages[str(c)] = st
        ms = [r[f"members_{c}"] for r in rows if r[f"members_{c}"]]
        members[str(c)] = {"credited": len(ms),
                           "event_has_a_row_in_each_on_look": sum(m["looks_with_a_row"] == 3 for m in ms),
                           "event_rows_missing_some_on_look": sum(m["looks_with_a_row"] < 3 for m in ms),
                           "matched_hits_not_the_events_own": sum(not m["matched_hits_are_the_events"] for m in ms)}
    thr = {"blocks": len(blocks),
           "hits_only_in_the_cut_tables": sum(x["only_cut"] for b in blocks for x in b["threshold"]["hits_by_look"].values()),
           "hits_only_when_searched_at_30": sum(x["only_searched"] for b in blocks for x in b["threshold"]["hits_by_look"].values()),
           "event_rows_differing": sum(b["threshold"]["event_rows_differing"] for b in blocks)}
    return {"signals": len(rows), "totals": tot, "paired": pairs,
            "largest_discordance": {k: max(max(v["all"]["first_only"], v["all"]["second_only"]) for v in p.values())
                                    for k, p in pairs.items()},
            "stages": stages, "members": members, "threshold": thr}


def blocks(say=_say):
    done = []
    for target in SESSIONS:
        session, urls, base, chosen, picks = _picks(target)
        block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
        for b in picks:
            r = block(target, session, urls, base, b, chosen[b], block_list)
            done.append(r)
            s = summarise([r])
            say(f"{target} block {b} ({chosen[b]}): " + ", ".join(f"{k} {v}" for k, v in s["totals"].items()))
    rec = {"blocks": [{"target": r["target"], "block": r["block"], "class": r["class"]} for r in done],
           "sample": "of each of the 2017 and 2016 sessions, 4 crowded and 4 clean blocks at random (seed 12)",
           "turboseti": "2.3.2 as released; the zero-drift variant sets min_drift to -1 after FindDoppler is made",
           **summarise(done), "kind": "measured"}
    yoke.write(OUT / "turbo_checks.json", rec, indent=1, stamp=True)
    say(f"turbo checks: {rec['totals']}")
    return rec


def track_match(f_hit, d_hit, f_sig, d_sig, span, t_ref=0.0):
    """A hit matches a signal along its track: drift within TOL_DRIFT, and the
    hit's line (its frequency at t_ref after the look's start) within TOL_HZ
    of the signal's (at the look's start) at some moment of the look."""
    if abs(d_hit - d_sig) > matched.TOL_DRIFT:
        return False
    a0 = (f_hit - d_hit * t_ref / 1e6 - f_sig) * 1e6          # Hz apart at the look's start
    a1 = a0 + (d_hit - d_sig) * span                          # and at its end
    return min(abs(a0), abs(a1)) <= matched.TOL_HZ or (a0 > 0) != (a1 > 0)


def reference(say=_say):
    """turboSETI's reported frequency and drift for strong synthetic tones,
    against where the tone is at the look's start and at the first spectrum's
    middle (the point the comparison matches turboSETI at), over the drifts
    and six places within a channel; and whether each would be credited by the
    comparison's point match and by a match along the track."""
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
        pipelines_tool = __import__("pipelines")._tool
        pipelines_tool("turbo_curves.py", out, "10", "true", *files)
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
            f"{sum(r['point_match'] for r in found)}, track match {sum(r['track_match'] for r in found)}; Hz from "
            f"the first spectrum's middle {[r['hz_from_first_spectrum_middle'] for r in found]}")
    shutil.rmtree(work, ignore_errors=True)
    by = {}
    for r in rows:
        d = by.setdefault(_drift_bin(r["drift"]), {"tones": 0, "found": 0, "point_match": 0, "track_match": 0})
        d["tones"] += 1
        if r["found"]:
            d["found"] += 1
            d["point_match"] += r["point_match"]
            d["track_match"] += r["track_match"]
    rec = {"rows": rows, "by_drift": by, "channel_hz": abs(foff) * 1e6, "tolerances": [matched.TOL_HZ, matched.TOL_DRIFT],
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
