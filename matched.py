"""The pipelines at matched sensitivity (comparable.md steps 4 and 7).

Over a set of swept blocks (every crowded one, and as many clean ones drawn
at random), each block's six slices are read once and:

- **false candidates** (step 7): every pipeline judged with each of the 19
  wrong choices of three ON looks, at a range of its cuts. A signal from the
  target is in the true ON looks only, so what these keep is noise or
  interference passing the test. Counted per block, distinct signals (a
  signal kept in several choices is one), the blocks the unit.
- **recovery** (step 4): TONES signals planted in the true ON looks only, as
  Phase 6 plants them (measure.plant), at strengths STRENGTHS and drifts over
  measure.DRIFT_BINS, then the same six slices through every pipeline again.
  A planted signal is recovered when a pipeline's kept output matches it in
  frequency and drift both (TOL_HZ, TOL_DRIFT, the same for every pipeline),
  each at its own reference time: this search's frequency is at the look's
  start, turboSETI's half a spectrum in (the channel of the first spectrum). A match the unplanted block already had is a false
  association, counted apart.

The pipelines, each at its own event stage:

- this search: searching.search (its hits from SNR 5 kept; a cut X makes the
  hits under X shadow hits, the same as searching at X, since the hit list
  does not depend on the cut) and onoff.judge, the label "candidate". The
  checks (vetting.py) are run on the false candidates at the published cut
  only: the planted signals' losses to them are Phase 6's.
- turboSETI: tools/turbo_curves.py (its hit search at the lowest cut, every
  table cut to the SNR before its event stage, filter threshold 3).
- pickles: tools/pickles_choices.py (its windows at level 1 and level 2, its
  masks on and off); it is compared by the windows it keeps, not at a
  matched SNR.

One JSON a block under data/matched/TARGET-SESSION/; a block with one is
done, so a run that stops goes on where it stopped.

    python matched.py run KIC8462852 [--blocks N]
    python matched.py tables KIC8462852       the curves, the matched cuts and the recovery tables
"""
import argparse
import itertools
import json
import math
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import injection
import measure
import onoff
import pipelines
import searching
import seti
import store
import yoke

ROOT = yoke.DATA / "matched"
CUTS_OURS = (8, 10, 12, 15, 20, 30)
CUTS_TURBO = (5, 6, 7, 8, 10, 12, 15, 20, 30)
PUBLISHED = {"ours": 10, "turboseti": 10}
STRENGTHS = (10, 15, 20, 30, 40, 50, 60, 80, 120, 200, 400)     # S_in
TONES = 110                     # a block: two in each drift bin and strength
TOL_HZ = 6.0                    # Margot et al. 2023's tolerances
TOL_DRIFT = 0.05
CROWDED_HITS = 20               # a block with more hits than this at the cut, six looks together, is crowded
N_CLEAN = 60
SEED = 4
APART_MHZ = 0.003               # signals kept in several wrong choices closer than this are one
TRUE = (0, 2, 4)


def ck(cut):
    """A cut as a record's key: '10', '7.5'."""
    return f"{float(cut):g}"


def folder(target, session):
    return ROOT / f"{target}-{session}"


def choose_blocks(db, session, n_clean=N_CLEAN, seed=SEED):
    """Every crowded block and n_clean clean ones at random: {block: class}."""
    rows = db.execute("SELECT block_idx, hits FROM blocks WHERE session = ? AND status = 'done' ORDER BY block_idx",
                      (session,)).fetchall()
    crowded = [b for b, h in rows if h > CROWDED_HITS]
    clean = [b for b, h in rows if h <= CROWDED_HITS]
    rng = np.random.default_rng(seed)
    pick = sorted(int(b) for b in rng.choice(clean, size=min(n_clean, len(clean)), replace=False))
    out = {b: "crowded" for b in crowded} | {b: "clean" for b in pick}
    return dict(sorted(out.items())), {"crowded": len(crowded), "clean": len(clean)}


# --- this search ---------------------------------------------------------------

def our_search(cad):
    """The six looks searched once: (hits, flat, complete) each."""
    def one(j):
        s, raw = cad[j]["s"], cad[j]["spectra"]
        details = {}
        hits = seti.describe(searching.search(raw, s["foff"], s["tsamp"], s["fch1"], details=details),
                             dict(s, spectra=raw))
        return hits, details["flat"], bool(details["complete"])
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(one, range(6)))


class CachedLook(onoff.Look):
    """onoff.Look whose best_track is remembered: it depends only on the look's
    spectra and four whole numbers (start channel, drift in channels, and the
    two tolerances rounded as best_track rounds them), so one look judged in
    many choices and at many cuts measures each track once."""

    def __init__(self, *a, cache):
        super().__init__(*a)
        self.cache = cache

    def best_track(self, start, drift, f_tol, d_tol):
        key = (int(round(start)), int(round(self.k(drift))), max(1, int(round(d_tol))), int(math.ceil(f_tol)))
        got = self.cache.get(key)
        if got is None:
            got = self.cache[key] = super().best_track(start, drift, f_tol, d_tol)
        return got


def our_events(cad, searched, ons, cut, caches):
    """onoff.judge with `ons` as the ON looks and hits under `cut` made shadow
    hits: (looks, events, look index of each position). caches: one dict a
    look, kept across choices and cuts."""
    offs = [j for j in range(6) if j not in ons]
    order = [x for pair in zip(ons, offs) for x in pair]          # position -> look
    looks = []
    for pos, j in enumerate(order):
        s = cad[j]["s"]
        hits = [dict(h, shadow=h["snr"] < cut) for h in searched[j][0]]
        looks.append(CachedLook(hits, s["tstart"], s["fch1"], s["foff"], s["tsamp"], searched[j][1], pos,
                                cache=caches[j]))
    return looks, onoff.judge(looks), order


def _our_kept(looks, events, order):
    """Candidates: each with its matched hit in each ON look (look index, MHz, Hz/s)."""
    out = []
    for e in events:
        if e["label"] != "candidate":
            continue
        members = [(order[p], looks[p].hits[i]["frequency_mhz"], looks[p].hits[i]["drift_hz_s"])
                   for p, i in enumerate(e["matches"]) if i is not None and p % 2 == 0]
        out.append({"f_mhz": round(e["frequency_mhz"], 6), "drift": round(e["drift_hz_s"], 4),
                    "snr": round(e["snr"], 2), "on_hits": members})
    return out


# --- the planted signals -------------------------------------------------------

def tones(cad, rng, n=TONES):
    """n signals over the slice, clear of each other, every drift bin and
    strength in turn (injection.tones_for, Phase 6's placing)."""
    return injection.tones_for(cad, n, 0, rng, strengths=STRENGTHS)


def plant(cad, ts):
    """The six looks with the signals in the ON looks: [(s, spectra)]."""
    t0 = cad[0]["s"]["tstart"]
    per_channel = cad[0]["s"]["foff"] * 1e6
    out = []
    for j, look in enumerate(cad):
        s, raw, sigma = look["s"], look["raw"], look["sigma"]
        if j % 2:
            out.append({"s": s, "spectra": raw})
            continue
        dt = (s["tstart"] - t0) * 86400
        here = []
        for t in ts:
            x = t["x0"] + t["drift"] * dt / per_channel
            c = int(min(max(round(x), 0), raw.shape[1] - 1))
            here.append((x, t["drift"], t["s_in"] * sigma[c] / math.sqrt(raw.shape[0])))
        out.append({"s": s, "spectra": measure.plant(raw, here, s["tsamp"], s["foff"])})
    return out


def where(cad, t, j, mid=False):
    """A planted signal's channel and MHz at look j's start (or, with `mid`,
    at the middle of its eighth spectrum, the one pickles looks at)."""
    s0 = cad[0]["s"]
    s = cad[j]["s"]
    per_channel = s0["foff"] * 1e6
    dt = (s["tstart"] - s0["tstart"]) * 86400 + (7.5 * s["tsamp"] if mid else 0.0)
    x = t["x0"] + t["drift"] * dt / per_channel
    return x, s["fch1"] + x * s["foff"]


def _match(t_f, t_drift, rows):
    """The closest of rows (each {look, f_mhz, drift}) to a planted signal
    ({look: MHz at the look's start}, drift): (within the tolerances, its
    offsets)."""
    best, within = None, False
    for r in rows:
        f = t_f.get(r["look"])
        if f is None:
            continue
        df, dd = (r["f_mhz"] - f) * 1e6, r["drift"] - t_drift
        within = within or (abs(df) <= TOL_HZ and abs(dd) <= TOL_DRIFT)
        d = math.hypot(df / TOL_HZ, dd / TOL_DRIFT)
        if best is None or d < best[0]:
            best = (d, round(df, 2), round(dd, 4))
    return within, (None if best is None else {"df_hz": best[1], "dd_hz_s": best[2]})


def _rows_ours(kept):
    return [{"look": j, "f_mhz": f, "drift": d} for c in kept for j, f, d in c["on_hits"]]


def _rows_turbo(events):
    return [{"look": r["look"], "f_mhz": r["freq_mhz"], "drift": r["drift_hz_s"]} for r in events]


def _status(t_f, t_drift, planted_rows, plain_rows):
    hit, off = _match(t_f, t_drift, planted_rows)
    if not hit:
        return {"status": None, "nearest": off}
    before, _ = _match(t_f, t_drift, plain_rows)
    return {"status": "false association" if before else "recovered", "nearest": off}


def _pickles_status(cad, t, planted, plain):
    """A planted signal against pickles' windows (true choice): the highest
    level of a window holding it in any ON look's eighth spectrum, and
    whether the unplanted block had that window at that level already."""
    chans = [where(cad, t, j, mid=True)[0] for j in TRUE]
    out = {}
    for run in ("masked", "unmasked"):
        def holding(rows):
            return [r for r in rows if any(r["Index"] * 1024 <= c < (r["Index"] + 1) * 1024 for c in chans)]
        got = holding(planted[run])
        level = max((r["level"] for r in got), default=None)
        if level is None:
            out[run] = {"level": None}
            continue
        before = max((r["level"] for r in holding(plain[run]) if r["Index"] in {g["Index"] for g in got}),
                     default=None)
        out[run] = {"level": level, "level_before": before}
    return out


# --- one block -----------------------------------------------------------------

def _distinct(freqs):
    seen = []
    for f in sorted(freqs):
        if all(abs(f - g) > APART_MHZ for g in seen):
            seen.append(f)
    return seen


def block(k, cls, slices, urls, work, source, vet, rng):
    """Everything for one block: its record."""
    times = {}
    t = time.monotonic()
    cad = []
    for u in urls:
        s = slices[u]
        cad.append({"s": s, "raw": s["spectra"], "spectra": s["spectra"],
                    "sigma": measure.channel_noise(s["spectra"])})
    plain_dir, planted_dir = work / "plain", work / "planted"
    plain_paths = [seti.save(c["s"], plain_dir / f"{j}.h5") for j, c in enumerate(cad)]

    # Unplanted: every choice, every cut.
    searched = our_search(cad)
    complete = [bool(x[2]) for x in searched]
    times["ours_search_s"] = round(time.monotonic() - t, 1)
    t = time.monotonic()
    ours_false, ours_true_plain, checks = {}, {}, []
    caches = [{} for _ in range(6)]
    for ons in itertools.combinations(range(6), 3):
        for cut in CUTS_OURS:
            looks, events, order = our_events(cad, searched, ons, cut, caches)
            kept = _our_kept(looks, events, order)
            if ons == TRUE:
                ours_true_plain[str(cut)] = kept
            else:
                ours_false.setdefault(str(cut), {})[str(ons)] = [c["f_mhz"] for c in kept]
                if cut == PUBLISHED["ours"] and kept and vet is not None:
                    for e in events:
                        if e["label"] == "candidate":
                            v = vet(e, looks)
                            checks.append({"as_on": list(ons), "f_mhz": round(e["frequency_mhz"], 6),
                                           "verdict": v.get("verdict")})
            for lk in looks:
                lk.flat = None
    times["ours_judge_s"] = round(time.monotonic() - t, 1)
    t = time.monotonic()
    pipelines._tool("turbo_curves.py", work / "turbo_plain.json", ",".join(map(str, CUTS_TURBO)), "all", *plain_paths)
    turbo_plain = json.loads((work / "turbo_plain.json").read_text(encoding="utf-8"))
    times["turbo_plain_s"] = round(time.monotonic() - t, 1)
    t = time.monotonic()
    pipelines._tool("pickles_choices.py", source, work / "pickles_plain.json", "all", *plain_paths)
    pickles_plain = json.loads((work / "pickles_plain.json").read_text(encoding="utf-8"))
    times["pickles_plain_s"] = round(time.monotonic() - t, 1)

    del searched, caches
    # Planted: the true choice.
    t = time.monotonic()
    ts = tones(cad, rng)
    planted = plant(cad, ts)
    planted_paths = [seti.save(dict(p["s"], spectra=p["spectra"]), planted_dir / f"{j}.h5")
                     for j, p in enumerate(planted)]
    cad_p = [dict(c, spectra=p["spectra"]) for c, p in zip(cad, planted)]
    searched_p = our_search(cad_p)
    ours_true_planted = {}
    caches = [{} for _ in range(6)]
    for cut in CUTS_OURS:
        looks, events, order = our_events(cad_p, searched_p, TRUE, cut, caches)
        ours_true_planted[str(cut)] = _our_kept(looks, events, order)
        for lk in looks:
            lk.flat = None
    del searched_p
    times["ours_planted_s"] = round(time.monotonic() - t, 1)
    t = time.monotonic()
    pipelines._tool("turbo_curves.py", work / "turbo_planted.json", ",".join(map(str, CUTS_TURBO)), "true",
                    *planted_paths)
    turbo_planted = json.loads((work / "turbo_planted.json").read_text(encoding="utf-8"))
    pipelines._tool("pickles_choices.py", source, work / "pickles_planted.json", "true", *planted_paths)
    pickles_planted = json.loads((work / "pickles_planted.json").read_text(encoding="utf-8"))
    times["others_planted_s"] = round(time.monotonic() - t, 1)

    def turbo_at(rec, ons, cut):
        return next(e["rows"] for e in rec["events"] if tuple(e["as_on"]) == tuple(ons) and e["cut"] == cut)

    pk_true_plain = next(c["runs"] for c in pickles_plain["choices"] if tuple(c["as_on"]) == TRUE)
    pk_true_planted = pickles_planted["choices"][0]["runs"]
    rows = []
    for tone in ts:
        t_f = {j: where(cad, tone, j)[1] for j in TRUE}
        r = {k2: tone[k2] for k2 in ("x0", "drift", "s_in", "bin", "position")}
        r["f_mhz"] = round(t_f[0], 6)
        r["flux_jy_hz"] = round(injection.flux_jy_hz(tone["s_in"], cad[0]["raw"].shape[0],
                                                      abs(cad[0]["s"]["foff"]) * 1e6, cad[0]["s"]["tsamp"]), 2)
        r["ours"] = {str(c): _status(t_f, tone["drift"], _rows_ours(ours_true_planted[str(c)]),
                                     _rows_ours(ours_true_plain[str(c)])) for c in CUTS_OURS}
        # turboSETI's frequency is the channel in the first spectrum: where the signal is on average over
        # that spectrum, half a spectrum after the look's start. Matched at its own reference time.
        t_f_turbo = {j: f + tone["drift"] * cad[j]["s"]["tsamp"] / 2 / 1e6 for j, f in t_f.items()}
        r["turboseti"] = {str(c): _status(t_f_turbo, tone["drift"],
                                          _rows_turbo(turbo_at(turbo_planted, TRUE, float(c))),
                                          _rows_turbo(turbo_at(turbo_plain, TRUE, float(c)))) for c in CUTS_TURBO}
        r["turboseti_hit_looks"] = sum(
            _match({j: t_f_turbo[j]}, tone["drift"],
                   [{"look": j, "f_mhz": h["freq_mhz"], "drift": h["drift_hz_s"]}
                    for h in turbo_planted["look_hits"][j] if h["snr"] > PUBLISHED["turboseti"]])[0] for j in TRUE)
        r["pickles"] = _pickles_status(cad, tone, pk_true_planted, pk_true_plain)
        rows.append(r)

    def wrong(rec_events):
        out = {}
        for e in rec_events:
            if tuple(e["as_on"]) != TRUE:
                out.setdefault(ck(e["cut"]), {})[
                    str(tuple(e["as_on"]))] = sorted({round(x["freq_mhz"], 6) for x in e["rows"]})
        return out

    pk_false = {}
    for c in pickles_plain["choices"]:
        if tuple(c["as_on"]) == TRUE:
            continue
        for run, rws in c["runs"].items():
            for level in (1, 2):
                pk_false.setdefault(run, {}).setdefault(str(level), {})[str(tuple(c["as_on"]))] = sorted(
                    {round(x["Freq"], 6) for x in rws if x["level"] >= level})
    s0 = cad[0]["s"]
    return {"block": k, "class": cls, "from_mhz": round(min(s0["fch1"], s0["fch1"] + s0["foff"] * cad[0]["raw"].shape[1]), 6),
            "to_mhz": round(max(s0["fch1"], s0["fch1"] + s0["foff"] * cad[0]["raw"].shape[1]), 6),
            "complete": complete, "times": times,
            "ours": {"false": ours_false, "true_plain": ours_true_plain, "checks_at_published_cut": checks},
            "turboseti": {"false": wrong(turbo_plain["events"]), "hits_plain": turbo_plain["hits"],
                          "true_plain": {ck(e["cut"]): e["rows"] for e in turbo_plain["events"]
                                         if tuple(e["as_on"]) == TRUE}},
            "pickles": {"false": pk_false, "true_plain": pk_true_plain},
            "tones": rows,
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def run(target, count=None, say=print):
    db = store.connect()
    kept = store.cadence_files(db, target)
    if not kept:
        raise yoke.Refusal("NOT_FOUND", f"No swept cadence of {target} in the store.")
    session, urls = kept
    chosen, totals = choose_blocks(db, session)
    db.close()
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    base, work_root = folder(target, session), ROOT / "work"
    base.mkdir(parents=True, exist_ok=True)
    (base / "blocks.json").write_text(json.dumps({"chosen": chosen, "of": totals, "crowded_hits": CROWDED_HITS,
                                                  "n_clean": N_CLEAN, "seed": SEED}, indent=1), encoding="utf-8")
    todo_all = [b for b in chosen if not (base / f"block_{b:03d}.json").exists()]
    todo = todo_all if count is None else todo_all[:count]
    say(f"{target} {session}: {len(chosen)} blocks chosen ({sum(v == 'crowded' for v in chosen.values())} crowded), "
        f"{len(chosen) - len(todo_all)} done before, {len(todo)} to run")
    source, _ = pipelines.pickles_source()
    vet = measure.vet_hook()

    def fetch(k):
        started = time.monotonic()
        return seti.read_looks(urls, *block_list[k]), round(time.monotonic() - started, 1)

    with ThreadPoolExecutor(max_workers=1) as ahead:
        coming = ahead.submit(fetch, todo[0]) if todo else None
        for i, k in enumerate(todo):
            slices, fetch_s = coming.result()
            coming = ahead.submit(fetch, todo[i + 1]) if i + 1 < len(todo) else None
            work = work_root / f"block_{k:03d}"
            shutil.rmtree(work, ignore_errors=True)
            started = time.monotonic()
            try:
                rec = block(k, chosen[k], slices, urls, work, source, vet, np.random.default_rng([SEED, k]))
            finally:
                shutil.rmtree(work, ignore_errors=True)
            del slices
            rec["times"]["fetch_s"] = fetch_s
            rec["times"]["block_s"] = round(time.monotonic() - started, 1)
            (base / f"block_{k:03d}.json").write_text(json.dumps(rec), encoding="utf-8")
            n = len(rec["tones"])
            line = (f"block {k} ({chosen[k]}): at the published cuts, recovered here "
                    f"{sum(t['ours']['10']['status'] == 'recovered' for t in rec['tones'])}/{n}, turboSETI "
                    f"{sum(t['turboseti']['10']['status'] == 'recovered' for t in rec['tones'])}/{n}; wrong-ON "
                    f"candidates here {len(_distinct(f for v in rec['ours']['false']['10'].values() for f in v))}, "
                    f"turboSETI {len(_distinct(f for v in rec['turboseti']['false']['10'].values() for f in v))}; "
                    f"{rec['times']['block_s']} s")
            say("  " + line, flush=True)
            with open(base / "progress.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%dT%H:%M:%S ", time.gmtime()) + line + "\n")
    shutil.rmtree(work_root, ignore_errors=True)
    done = len(list(base.glob("block_*.json")))
    say(f"{target} {session}: {done} of {len(chosen)} chosen blocks done")
    return {"done": done, "of": len(chosen)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("target")
    r.add_argument("--blocks", type=int)
    t = sub.add_parser("tables")
    t.add_argument("target")
    a = p.parse_args(argv)
    try:
        if a.command == "run":
            run(a.target, a.blocks)
        else:
            import matched_tables
            matched_tables.write(a.target)
    except yoke.Refusal as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
