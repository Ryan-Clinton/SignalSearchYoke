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
from pathlib import Path

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
CUTS_OURS = (8, 10, 12, 15, 20, 30, 50, 100)
CUTS_TURBO = (5, 6, 7, 8, 10, 12, 15, 20, 30, 50, 100)
PUBLISHED = {"ours": 10, "turboseti": 10}
STRENGTHS = (10, 15, 20, 30, 40, 50, 60, 80, 120, 200, 400)     # S_in
TONES = 110                     # a block: two in each drift bin and strength
TOL_HZ = 6.0                    # Margot et al. 2023's tolerances
TOL_DRIFT = 0.05
CROWDED_HITS = 20               # a block with more hits than this at the cut, six looks together, is crowded
N_CLEAN = 60
SEED = 4
APART_MHZ = 0.003               # the first run's merging of false candidates (frequency only): kept as one variant
FORMAT = 2                      # 2: kept events with their member hits; recovery lenient and strict
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
    """Candidates: each with the look of its strongest hit and its member hit
    in each ON look as [look, hit index, MHz, Hz/s]. A hit index is into that
    look's one hit list, the same in every choice and cut, so two candidates
    sharing one are the same signal."""
    out = []
    for e in events:
        if e["label"] != "candidate":
            continue
        members = [[order[p], int(i), looks[p].hits[i]["frequency_mhz"], looks[p].hits[i]["drift_hz_s"]]
                   for p, i in enumerate(e["matches"]) if i is not None and p % 2 == 0]
        # An ON look with no hit at the cut: the track judge measured there
        # (its start in MHz, drift, S/N), which made the candidate.
        tracks = [[order[p], looks[p].fch1 + x["track_channel"] * looks[p].foff, x["track_drift_hz_s"],
                   x["track_snr"]]
                  for p, x in enumerate(e["looks"])
                  if p % 2 == 0 and e["matches"][p] is None and x.get("track_channel") is not None]
        out.append({"f_mhz": round(e["frequency_mhz"], 6), "drift": round(e["drift_hz_s"], 4),
                    "snr": round(e["snr"], 2), "look": order[e["seed_position"]], "members": members,
                    "tracks": tracks})
    return out


def _turbo_kept(rows):
    """turboSETI's events (rows grouped by its Hit_ID): each with its member
    hits as [look, None, MHz, Hz/s] (a hit is known by its look, frequency
    and drift)."""
    by = {}
    for r in rows:
        by.setdefault(r["hit_id"], []).append([r["look"], None, r["freq_mhz"], r["drift_hz_s"]])
    return [{"f_mhz": round(m[0][2], 6), "drift": m[0][3], "look": m[0][0], "members": m} for m in by.values()]


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


def _event_fit(t_f, t_drift, ev, tracks=False):
    """How many of a kept event's ON members (with `tracks`, also the tracks
    measured in ON looks without a hit) match a planted signal, of how many."""
    looks = [m[:1] + m[2:4] for m in ev["members"]] + ([x[:3] for x in ev.get("tracks", [])] if tracks else [])
    ok = sum(abs((f - t_f[j]) * 1e6) <= TOL_HZ and abs(d - t_drift) <= TOL_DRIFT for j, f, d in looks if j in t_f)
    return ok, len(looks)


# Recovery, weakest to strongest. Lenient: an event with any ON member hit
# matching. Strict: every ON member hit matching. Three hits: a member hit in
# each of the three ON looks, all matching. Three looks: each ON look matching,
# by its member hit or, where it has none at the cut, by the track measured
# there.
RECOVERY = (("lenient", False, lambda ok, n: ok >= 1), ("strict", False, lambda ok, n: n >= 1 and ok == n),
            ("three_hits", False, lambda ok, n: ok == n == len(TRUE)),
            ("three_looks", True, lambda ok, n: ok == n == len(TRUE)))


def _status(t_f, t_drift, planted, plain, turboseti=False):
    """A planted signal against a pipeline's kept events, planted and
    unplanted: each way of RECOVERY a recovery, or a false association when
    the unplanted block already had such an event.

    turboSETI: its event needs a hit in every ON look (within its own follow
    window of the first ON look's hit), but its table of an event's hits
    leaves out a look whose first hit's number (TopHitNum, counted afresh in
    each look) it has already written, so the rows do not show every look.
    For it, three looks here is strict (every hit it lists matching); the
    tables add the check of its own hit tables (turboseti_on_hits, a
    matching hit in each ON look at the cut). Three hits cannot be told."""
    rows = [{"look": j, "f_mhz": f, "drift": d} for ev in planted for j, _, f, d in ev["members"]]
    _, off = _match(t_f, t_drift, rows)
    out = {"nearest": off}
    for name, tracks, test in RECOVERY:
        if turboseti and name in ("three_hits", "three_looks"):
            continue
        hit = [ev for ev in planted if test(*_event_fit(t_f, t_drift, ev, tracks))]
        if not hit:
            out[name] = None
            continue
        before = any(test(*_event_fit(t_f, t_drift, ev, tracks)) for ev in plain)
        out[name] = "false association" if before else "recovered"
    if turboseti:
        out["three_looks"] = out["strict"]
    best =max(planted, key=lambda ev: _event_fit(t_f, t_drift, ev)[0], default=None)
    out["members"] = list(_event_fit(t_f, t_drift, best)) if best else None
    return out


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

def _distinct(freqs, apart=APART_MHZ):
    seen = []
    for f in sorted(freqs):
        if all(abs(f - g) > apart for g in seen):
            seen.append(f)
    return seen


def _hit_key(m):
    j, i, f, d = m
    return (j, i) if i is not None else (j, round(f, 6), round(d, 6))


def shared_hits(by_choice):
    """The distinct signals among the candidates of all the wrong choices
    ({choice: [kept event]}): candidates sharing any member hit are one
    signal (joined through any chain of shared hits)."""
    events = [ev for evs in by_choice.values() for ev in evs]
    parent = list(range(len(events)))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    owner = {}
    for n, ev in enumerate(events):
        for m in ev["members"]:
            key = _hit_key(m)
            if key in owner:
                parent[root(n)] = root(owner[key])
            else:
                owner[key] = n
    groups = {}
    for n, ev in enumerate(events):
        groups.setdefault(root(n), []).append(ev)
    return list(groups.values())


def _turbo_on_hits(planted, t_f_turbo, drift, cut):
    """In how many true ON looks turboSETI's own hit table (planted run, SNR
    over `cut`) has a hit matching the planted signal: its three-look
    evidence checked by the same tolerances as this search's, not by its
    event rule."""
    return sum(_match({j: t_f_turbo[j]}, drift,
                      [{"look": j, "f_mhz": h["freq_mhz"], "drift": h["drift_hz_s"]}
                       for h in planted["look_hits"][j] if h["snr"] > cut])[0] for j in TRUE)


def _ours_true(cad, searched):
    """The true choice at every cut: {cut: kept events}."""
    caches = [{} for _ in range(6)]
    out = {}
    for cut in CUTS_OURS:
        looks, events, order = our_events(cad, searched, TRUE, cut, caches)
        out[str(cut)] = _our_kept(looks, events, order)
        for lk in looks:
            lk.flat = None
    return out


def _cadence(slices, urls):
    out = []
    for u in urls:
        s = slices[u]
        out.append({"s": s, "raw": s["spectra"], "spectra": s["spectra"], "sigma": measure.channel_noise(s["spectra"])})
    return out


def block(k, cls, slices, urls, work, source, vet, rng):
    """Everything for one block: its record."""
    times = {}
    t = time.monotonic()
    cad = _cadence(slices, urls)
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
                ours_false.setdefault(str(cut), {})[str(ons)] = kept
                if cut == PUBLISHED["ours"] and kept and vet is not None:
                    for e in events:
                        if e["label"] == "candidate":
                            v = vet(e, looks)
                            checks.append({"as_on": list(ons), "f_mhz": round(e["frequency_mhz"], 6),
                                           "drift": round(e["drift_hz_s"], 4), "snr": round(e["snr"], 2),
                                           "verdict": v.get("verdict"), "reasons": v.get("reasons")})
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
    ours_true_planted = _ours_true(cad_p, our_search(cad_p))
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
        r["ours"] = {str(c): _status(t_f, tone["drift"], ours_true_planted[str(c)], ours_true_plain[str(c)])
                     for c in CUTS_OURS}
        # turboSETI's frequency is the channel in the first spectrum: where the signal is on average over
        # that spectrum, half a spectrum after the look's start. Matched at its own reference time.
        t_f_turbo = {j: f + tone["drift"] * cad[j]["s"]["tsamp"] / 2 / 1e6 for j, f in t_f.items()}
        r["turboseti"] = {str(c): _status(t_f_turbo, tone["drift"],
                                          _turbo_kept(turbo_at(turbo_planted, TRUE, float(c))),
                                          _turbo_kept(turbo_at(turbo_plain, TRUE, float(c))), turboseti=True)
                           for c in CUTS_TURBO}
        r["turboseti_hit_looks"] = _turbo_on_hits(turbo_planted, t_f_turbo, tone["drift"], PUBLISHED["turboseti"])
        r["turboseti_on_hits"] = {str(c): _turbo_on_hits(turbo_planted, t_f_turbo, tone["drift"], c)
                                  for c in CUTS_TURBO}
        r["pickles"] = _pickles_status(cad, tone, pk_true_planted, pk_true_plain)
        rows.append(r)

    def wrong(rec_events):
        out = {}
        for e in rec_events:
            if tuple(e["as_on"]) != TRUE:
                out.setdefault(ck(e["cut"]), {})[str(tuple(e["as_on"]))] = _turbo_kept(e["rows"])
        return out

    pk_false = {}
    for c in pickles_plain["choices"]:
        if tuple(c["as_on"]) == TRUE:
            continue
        for run, rws in c["runs"].items():
            for level in (1, 2):
                pk_false.setdefault(run, {}).setdefault(str(level), {})[str(tuple(c["as_on"]))] = sorted(
                    {(x["Index"], round(x["Freq"], 6)) for x in rws if x["level"] >= level})
    s0 = cad[0]["s"]
    return {"format": FORMAT, "block": k, "class": cls, "tstarts": [c["s"]["tstart"] for c in cad], "from_mhz": round(min(s0["fch1"], s0["fch1"] + s0["foff"] * cad[0]["raw"].shape[1]), 6),
            "to_mhz": round(max(s0["fch1"], s0["fch1"] + s0["foff"] * cad[0]["raw"].shape[1]), 6),
            "complete": complete, "times": times,
            "ours": {"false": ours_false, "true_plain": ours_true_plain, "checks_at_published_cut": checks},
            "turboseti": {"false": wrong(turbo_plain["events"]), "hits_plain": turbo_plain["hits"],
                          "true_plain": {ck(e["cut"]): _turbo_kept(e["rows"]) for e in turbo_plain["events"]
                                         if tuple(e["as_on"]) == TRUE}},
            "pickles": {"false": pk_false, "true_plain": pk_true_plain},
            "tones": rows,
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def run(target, count=None, say=print, choice=None, shard=(0, 1)):
    """choice: the blocks chosen elsewhere ({"chosen": {block: class},
    "of": {class: blocks swept}, and how they were chosen}), written as the
    run's blocks.json; a run already begun with another choice is refused.
    Without it, choose_blocks (step 4's rule). shard (i, n): every n-th
    chosen block from the i-th (each block has its own seed, so the records
    do not depend on the split)."""
    db = store.connect()
    kept = store.cadence_files(db, target)
    if not kept:
        raise yoke.Refusal("NOT_FOUND", f"No swept cadence of {target} in the store.")
    session, urls = kept
    if choice is None:
        chosen, totals = choose_blocks(db, session)
        meta = {"chosen": chosen, "of": totals, "crowded_hits": CROWDED_HITS, "n_clean": N_CLEAN, "seed": SEED}
    else:
        chosen = {int(b): c for b, c in choice["chosen"].items()}
        meta = dict(choice, chosen=chosen, seed=SEED)
    db.close()
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    base, work_root = folder(target, session), ROOT / f"work_{shard[0]}"
    base.mkdir(parents=True, exist_ok=True)
    meta_path = base / "blocks.json"
    if meta_path.exists():
        before = json.loads(meta_path.read_text(encoding="utf-8"))
        if {int(b): c for b, c in before["chosen"].items()} != chosen and list(base.glob("block_*.json")):
            raise yoke.Refusal("INVALID_REQUEST", f"{base} was begun with another choice of blocks.")
    if not meta_path.exists() or json.loads(meta_path.read_text(encoding="utf-8")) != json.loads(json.dumps(meta)):
        meta_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    todo_all = [b for i, b in enumerate(chosen) if i % shard[1] == shard[0]
                and not (base / f"block_{b:03d}.json").exists()]
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
                    f"{sum(t['ours']['10']['three_looks'] == 'recovered' for t in rec['tones'])}/{n}, turboSETI "
                    f"{sum(t['turboseti']['10']['three_looks'] == 'recovered' and t['turboseti_on_hits']['10'] == 3 for t in rec['tones'])}/{n} "
                    f"(all three ON looks; here {sum(t['ours']['10']['strict'] == 'recovered' for t in rec['tones'])}"
                    " strict); "
                    f"wrong-ON candidates here {len(shared_hits(rec['ours']['false']['10']))}, "
                    f"turboSETI {len(shared_hits(rec['turboseti']['false']['10']))} (by shared hits); "
                    f"{rec['times']['block_s']} s")
            say("  " + line, flush=True)
            with open(base / "progress.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%dT%H:%M:%S ", time.gmtime()) + line + "\n")
    shutil.rmtree(work_root, ignore_errors=True)
    done = len(list(base.glob("block_*.json")))
    say(f"{target} {session}: {done} of {len(chosen)} chosen blocks done")
    return {"done": done, "of": len(chosen)}


def _kept_same(a, b):
    key = ("f_mhz", "drift", "snr", "look", "members")
    return [[ev[x] for x in key] for ev in a] == [[ev[x] for x in key] for ev in b]


def complete(rec):
    """Whether a block's record has everything recovery is counted from."""
    return "three_looks" in rec["tones"][0]["ours"][ck(PUBLISHED["ours"])] and "turboseti_on_hits" in rec["tones"][0]


def add_tracks(target, say=print):
    """Blocks recorded before the measured ON tracks (this search) or the
    matching ON hits at every cut (turboSETI) were kept: the signals planted
    again from the record, and

    - this search: its true choice judged again at every cut, unplanted and
      planted, and its recovery redone with every way of RECOVERY;
    - turboSETI: run again on the planted looks, its recovery redone, and
      its ON hits matching each signal counted at every cut.

    What was recorded before must come out the same, or the block is left
    as it was. At the end, the blocks still without either are named."""
    db = store.connect()
    session, urls = store.cadence_files(db, target)
    db.close()
    base = folder(target, session)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    pub = ck(PUBLISHED["ours"])
    work = ROOT / "work_tracks"
    for p in sorted(base.glob("block_*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("format") != FORMAT or complete(rec):
            continue
        need_tracks = "three_looks" not in rec["tones"][0]["ours"][pub]
        need_turbo = "turboseti_on_hits" not in rec["tones"][0]
        started = time.monotonic()
        cad = _cadence(seti.read_looks(urls, *block_list[rec["block"]]), urls)
        planted_c = plant(cad, rec["tones"])
        differ = []
        if need_tracks:
            plain = _ours_true(cad, our_search(cad))
            cad_p = [dict(c, spectra=x["spectra"]) for c, x in zip(cad, planted_c)]
            planted = _ours_true(cad_p, our_search(cad_p))
            differ += [c for c in plain if not _kept_same(plain[c], rec["ours"]["true_plain"][c])]
        if need_turbo:
            shutil.rmtree(work, ignore_errors=True)
            paths = [seti.save(dict(x["s"], spectra=x["spectra"]), work / f"{j}.h5") for j, x in enumerate(planted_c)]
            pipelines._tool("turbo_curves.py", work / "turbo_planted.json", ",".join(map(str, CUTS_TURBO)), "true",
                            *paths)
            turbo = json.loads((work / "turbo_planted.json").read_text(encoding="utf-8"))
            shutil.rmtree(work, ignore_errors=True)
        for t in rec["tones"]:
            t_f = {j: where(cad, t, j)[1] for j in TRUE}
            if need_tracks:
                new = {str(c): _status(t_f, t["drift"], planted[str(c)], plain[str(c)]) for c in CUTS_OURS}
                differ += [(t["f_mhz"], c) for c in new for x in ("nearest", "lenient", "strict", "members")
                           if new[c][x] != t["ours"][c][x]]
                t["ours"] = new
            if need_turbo:
                t_f_turbo = {j: f + t["drift"] * cad[j]["s"]["tsamp"] / 2 / 1e6 for j, f in t_f.items()}
                for c in CUTS_TURBO:
                    rows = next(e["rows"] for e in turbo["events"] if tuple(e["as_on"]) == TRUE and e["cut"] == c)
                    new = _status(t_f_turbo, t["drift"], _turbo_kept(rows),
                                  rec["turboseti"]["true_plain"].get(ck(c), []), turboseti=True)
                    differ += [(t["f_mhz"], "turboSETI", c) for x in ("nearest", "lenient", "strict", "members")
                               if new[x] != t["turboseti"][str(c)][x]]
                    t["turboseti"][str(c)] = new
                hl = _turbo_on_hits(turbo, t_f_turbo, t["drift"], PUBLISHED["turboseti"])
                if hl != t["turboseti_hit_looks"]:
                    differ.append((t["f_mhz"], "turboSETI hit looks"))
                t["turboseti_on_hits"] = {str(c): _turbo_on_hits(turbo, t_f_turbo, t["drift"], c) for c in CUTS_TURBO}
        if differ:
            say(f"  block {rec['block']}: judged again, {len(differ)} results differ from the record "
                f"(first {differ[:3]}); left as it was", flush=True)
            continue
        if need_tracks:
            rec["ours"]["true_plain"] = plain
        rec["tracks_added_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        p.write_text(json.dumps(rec), encoding="utf-8")
        n = len(rec["tones"])
        say(f"  block {rec['block']}: completed ({'tracks' if need_tracks else ''}"
            f"{', ' if need_tracks and need_turbo else ''}{'turboSETI ON hits' if need_turbo else ''}), "
            f"the record otherwise the same; in all three ON looks here "
            f"{sum(t['ours'][pub]['three_looks'] == 'recovered' for t in rec['tones'])}/{n}, turboSETI "
            f"{sum(t['turboseti'][pub]['three_looks'] == 'recovered' and t['turboseti_on_hits'][pub] == 3 for t in rec['tones'])}"
            f"/{n}; {round(time.monotonic() - started, 1)} s", flush=True)
    left = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob("block_*.json"))]
    left = [r["block"] for r in left if r.get("format") == FORMAT and not complete(r)]
    say(f"Blocks still without them: {', '.join(map(str, left)) if left else 'none'}.")


# --- BLISS (comparable.md step 11) ---------------------------------------------

# What the comparison is (kept in every record, and a record is only taken as done when it matches) ...
BLISS_COMMIT = "2b98afe960f13ee7e467aca499576d87ee7502f5"
BLISS_FORMAT = 2                # 2: configuration and provenance kept; flags and the hit filter on planted tracks
CUTS_BLISS = CUTS_TURBO
BLISS_TOOLS = ("tools/bliss_curves.py", "tools/bliss/bliss_events.py", "tools/bliss/event_search_off_hits_once.patch")
# ... and where it runs (settings, not part of the comparison): the WSL distribution, the Python with
# BLISS's module, and the libraries it needs. Unset, the last two are under ~/ssy in the distribution
# (docs/reproducing-results.md). bliss_curves.py takes BLISS_PYTHON_DIR, BLISS_RESPONSE and BLISS_DEVICE
# from the same environment.
BLISS_DISTRO = __import__("os").environ.get("SSY_BLISS_DISTRO", "Ubuntu")
BLISS_PYTHON = __import__("os").environ.get("SSY_BLISS_PYTHON")
BLISS_LD_PATH = __import__("os").environ.get("SSY_BLISS_LD_PATH")
BLISS_TIMEOUT_S = 4 * 3600
_bliss_where = None


def bliss_where():
    """(python, LD_LIBRARY_PATH) for BLISS in WSL, checked once: refused, saying
    what is missing, when WSL, the distribution or BLISS's Python is not there."""
    global _bliss_where
    if _bliss_where:
        return _bliss_where
    import subprocess
    how = "BLISS runs only for the comparison (step 11); docs/reproducing-results.md says how to build it"
    try:
        home = subprocess.run(["wsl", "-d", BLISS_DISTRO, "--", "sh", "-c", 'printf %s "$HOME"'],
                              capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise yoke.Refusal("INVALID_REQUEST", f"WSL is not available here. {how}.")
    if home.returncode or not home.stdout.strip():
        raise yoke.Refusal("INVALID_REQUEST", f"WSL has no distribution {BLISS_DISTRO!r} (SSY_BLISS_DISTRO names "
                                              f"another). {how}.")
    home = home.stdout.strip()
    python = BLISS_PYTHON or f"{home}/ssy/blissenv/bin/python"
    ld = BLISS_LD_PATH or f"{home}/ssy/cuda126/lib:/usr/lib/wsl/lib"
    if subprocess.run(["wsl", "-d", BLISS_DISTRO, "--", "test", "-x", python], timeout=120).returncode:
        raise yoke.Refusal("INVALID_REQUEST", f"No Python for BLISS at {python} in WSL's {BLISS_DISTRO} "
                                              f"(SSY_BLISS_PYTHON names another). {how}.")
    _bliss_where = python, ld
    return _bliss_where


def bliss_config():
    import hashlib
    return {"bliss_format": BLISS_FORMAT, "bliss_commit": BLISS_COMMIT, "cuts": list(CUTS_BLISS),
            "tools": {t: hashlib.sha256((yoke.ROOT / t).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]
                      for t in BLISS_TOOLS}}


def _wsl_path(p):
    p = str(p).replace("\\", "/")
    return f"/mnt/{p[0].lower()}{p[2:]}" if len(p) > 1 and p[1] == ":" else p


def _bliss_tool(out, which, paths, tones=None, cuts=CUTS_BLISS, shuffles=None):
    import subprocess
    extra = ["--tones", _wsl_path(tones)] if tones else []
    env = [] if shuffles is None else [f"BLISS_SHUFFLES={shuffles}"]
    python, ld = bliss_where()
    done = subprocess.run(["wsl", "-d", BLISS_DISTRO, "--", "env", f"LD_LIBRARY_PATH={ld}", *env, python,
                           _wsl_path(yoke.ROOT / "tools" / "bliss_curves.py"), *extra, _wsl_path(out),
                           ",".join(map(str, cuts)), which, *map(_wsl_path, paths)],
                          capture_output=True, text=True, timeout=BLISS_TIMEOUT_S)
    if done.returncode:
        raise yoke.Refusal("INTERNAL_ERROR", f"bliss_curves.py failed: {done.stderr.strip()[-400:]}")
    return json.loads(Path(out).read_text(encoding="utf-8"))


BLISS_ATTEMPTS = 2


def bliss_done(path, config):
    """A block's BLISS record that parses and was made with this
    configuration. A failure counts as done (and is reported) once it has
    failed BLISS_ATTEMPTS times: a run cut off by WSL stopping or the
    machine restarting is tried again, not recorded as BLISS's failure."""
    try:
        r = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if r.get("config") != config:
        return False
    return r.get("attempts", 1) >= BLISS_ATTEMPTS if "failed" in r else len(r.get("tones", [])) == TONES


def _run_lock(path):
    """Hold an OS lock on `path` for the life of the process (released by the
    OS however the process ends, a power cut included); refused if another
    run holds it, so a restart cannot run beside a run still going."""
    f = open(path, "a+")
    try:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise yoke.Refusal("INVALID_REQUEST", f"another run holds {path}") from None
    return f


def _bliss_kept(rows):
    """BLISS's events: each with its member hits as [look, None, MHz, Hz/s],
    one in each ON look it matched (it lists every member)."""
    return [{"f_mhz": round(r["hits"][0]["freq_mhz"], 6), "drift": r["hits"][0]["drift_hz_s"],
             "look": r["hits"][0]["look"], "snr": round(r["snr"], 2),
             "members": [[h["look"], None, h["freq_mhz"], h["drift_hz_s"]] for h in r["hits"]]} for r in rows]


def _bliss_on_hits(rec, t_f, drift, cut, which="hits"):
    """In how many true ON looks BLISS's own hits (planted run, at `cut`;
    with which="hits_unfiltered", before its hit filter) hold one matching
    the planted signal."""
    return sum(_match({j: t_f[j]}, drift, [{"look": j, "f_mhz": h["freq_mhz"], "drift": h["drift_hz_s"]}
                                           for h in rec[which][str(float(cut))][j]])[0] for j in TRUE)


def bliss_folder(target, session):
    return folder(target, session) / "bliss"


def add_bliss(target, say=print, shard=(0, 1), count=None):
    """BLISS as a further pipeline on the blocks step 4 recorded: each block
    read again (refused unless its MHz range and look starts are the
    record's), its unplanted looks through tools/bliss_curves.py with every
    choice, the record's signals planted again (plant(), their MHz checked
    against the record's) and the planted looks through it with the true
    choice; scored as the others are (_status, at the look's start). For
    each planted signal also: the share of its track BLISS's flags cover in
    each ON look, and its matching hits before and after BLISS's hit filter,
    so a loss can be put to the flags, the search, the filter or the event
    stage.

    One JSON a block under the run's bliss/ folder, written whole or not at
    all, with the comparison's configuration (bliss_config: BLISS's commit,
    the cuts, hashes of the tools and the patch) and the run's provenance
    (from bliss_curves.py). A block counts as done only when its record
    parses and has this configuration; a block whose BLISS run fails is
    recorded as failed, with the error, and the run goes on. Crowded blocks
    run first. Step 4's records are only read."""
    import subprocess
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, target)
    db.close()
    base, out = folder(target, session), bliss_folder(target, session)
    out.mkdir(parents=True, exist_ok=True)
    lock = _run_lock(out / f"run_{shard[0]}.lock")  # noqa: F841 -- held until the process ends
    partial = out / "partial"  # a block's unplanted half, kept so a stop mid-block loses at most the planted half
    partial.mkdir(exist_ok=True)
    config = bliss_config()
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    recs = sorted(base.glob("block_*.json"))
    classes = json.loads((base / "blocks.json").read_text(encoding="utf-8"))["chosen"]
    # crowded blocks first: the slowest and most likely to fail, found early
    recs.sort(key=lambda p: (classes.get(str(int(p.stem.split("_")[1]))) != "crowded", p.name))
    todo = [p for i, p in enumerate(recs) if i % shard[1] == shard[0] and not bliss_done(out / p.name, config)]
    todo = todo if count is None else todo[:count]
    say(f"{target} {session}: BLISS on {len(todo)} of the {len(recs)} recorded blocks in this share", flush=True)
    work = ROOT / f"work_bliss_{shard[0]}"

    def fetch(p):
        rec = json.loads(p.read_text(encoding="utf-8"))
        started = time.monotonic()
        return rec, seti.read_looks(urls, *block_list[rec["block"]]), round(time.monotonic() - started, 1)

    def log(line):
        say("  " + line, flush=True)
        with open(out / "progress.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%S ", time.gmtime()) + line + "\n")

    with ThreadPoolExecutor(max_workers=1) as ahead:
        coming = ahead.submit(fetch, todo[0]) if todo else None
        for i, p in enumerate(todo):
            rec, slices, fetch_s = coming.result()
            coming = ahead.submit(fetch, todo[i + 1]) if i + 1 < len(todo) else None
            started = time.monotonic()
            cad = _cadence(slices, urls)
            del slices
            s0 = cad[0]["s"]
            span = (round(min(s0["fch1"], s0["fch1"] + s0["foff"] * cad[0]["raw"].shape[1]), 6),
                    round(max(s0["fch1"], s0["fch1"] + s0["foff"] * cad[0]["raw"].shape[1]), 6))
            if span != (rec["from_mhz"], rec["to_mhz"]) or [c["s"]["tstart"] for c in cad] != rec["tstarts"]:
                raise yoke.Refusal("INVALID_REQUEST", f"block {rec['block']} read again is not the one recorded")
            moved = [t["f_mhz"] for t in rec["tones"] if round(where(cad, t, 0)[1], 6) != t["f_mhz"]]
            if moved:
                raise yoke.Refusal("INVALID_REQUEST", f"block {rec['block']}: signals not where recorded: {moved[:3]}")
            shutil.rmtree(work, ignore_errors=True)
            try:
                kept = partial / p.name
                try:
                    k = json.loads(kept.read_text(encoding="utf-8"))
                    plain = k["plain"] if k["config"] == config else None
                except (OSError, ValueError, KeyError):
                    plain = None
                if plain is None:
                    plain_paths = [seti.save(c["s"], work / "plain" / f"{j}.h5") for j, c in enumerate(cad)]
                    plain = _bliss_tool(work / "bliss_plain.json", "all", plain_paths)
                    yoke.write(kept, {"config": config, "plain": plain}, indent=None)
                else:
                    log(f"block {rec['block']}: unplanted half from before a stop")
                planted = plant(cad, rec["tones"])
                planted_paths = [seti.save(dict(x["s"], spectra=x["spectra"]), work / "planted" / f"{j}.h5")
                                 for j, x in enumerate(planted)]
                del planted
                # each signal's channel at each ON look's start, for the flags along its track
                tracks = {str(j): [[where(cad, t, j)[0], t["drift"]] for t in rec["tones"]] for j in TRUE}
                (work / "tones.json").write_text(json.dumps(tracks), encoding="utf-8")
                bp = _bliss_tool(work / "bliss_planted.json", "true", planted_paths, tones=work / "tones.json")
            except (yoke.Refusal, subprocess.TimeoutExpired, OSError, ValueError) as e:
                try:
                    before = json.loads((out / p.name).read_text(encoding="utf-8"))
                    tries = before.get("attempts", 1) if before.get("config") == config and "failed" in before else 0
                except (OSError, ValueError):
                    tries = 0
                yoke.write(out / p.name, {"format": FORMAT, "block": rec["block"], "class": rec["class"],
                                          "config": config, "failed": str(e)[-600:], "attempts": tries + 1,
                                          "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                           indent=None)
                log(f"block {rec['block']} ({rec['class']}): BLISS FAILED (attempt {tries + 1} of "
                    f"{BLISS_ATTEMPTS}): {str(e)[-200:]}")
                continue
            finally:
                shutil.rmtree(work, ignore_errors=True)

            def at(r, ons, cut):
                return next(e["rows"] for e in r["events"] if tuple(e["as_on"]) == tuple(ons) and e["cut"] == cut)

            tones_out = []
            for n_t, t in enumerate(rec["tones"]):
                t_f = {j: where(cad, t, j)[1] for j in TRUE}
                tones_out.append({"f_mhz": t["f_mhz"], "drift": t["drift"], "s_in": t["s_in"], "bin": t["bin"],
                                  "bliss": {str(c): _status(t_f, t["drift"], _bliss_kept(at(bp, TRUE, float(c))),
                                                            _bliss_kept(at(plain, TRUE, float(c))))
                                            for c in CUTS_BLISS},
                                  "bliss_on_hits": {str(c): _bliss_on_hits(bp, t_f, t["drift"], c) for c in CUTS_BLISS},
                                  "bliss_on_hits_unfiltered": {str(c): _bliss_on_hits(bp, t_f, t["drift"], c,
                                                                                      "hits_unfiltered")
                                                               for c in CUTS_BLISS},
                                  "bliss_flagged": [bp["tones_flagged"][str(j)][n_t] for j in TRUE]})
            false = {}
            for e in plain["events"]:
                if tuple(e["as_on"]) != TRUE:
                    false.setdefault(ck(e["cut"]), {})[str(tuple(e["as_on"]))] = _bliss_kept(e["rows"])
            # the same, with each look's hits in seeded random orders (BLISS's own order changes from run to run)
            shuffled = {}
            for k, evs in plain.get("events_shuffled", {}).items():
                fk = {}
                for e in evs:
                    if tuple(e["as_on"]) != TRUE:
                        fk.setdefault(ck(e["cut"]), {})[str(tuple(e["as_on"]))] = _bliss_kept(e["rows"])
                tp = {ck(e["cut"]): _bliss_kept(e["rows"]) for e in evs if tuple(e["as_on"]) == TRUE}
                pp = {ck(e["cut"]): _bliss_kept(e["rows"]) for e in bp["events_shuffled"][k]}
                shuffled[k] = {"false": fk, "tones": [
                    {str(c): {x: s[x] for x in ("three_looks", "strict")}
                     for c in CUTS_BLISS for s in [_status({j: where(cad, t, j)[1] for j in TRUE}, t["drift"],
                                                           pp[ck(c)], tp[ck(c)])]}
                    for t in rec["tones"]]}
            res = {"format": FORMAT, "block": rec["block"], "class": rec["class"], "config": config,
                   "provenance": {"plain": plain["provenance"], "planted": bp["provenance"]},
                   "false": false,
                   "true_plain": {ck(e["cut"]): _bliss_kept(e["rows"]) for e in plain["events"]
                                  if tuple(e["as_on"]) == TRUE},
                   "hits_plain": {c: [len(x) for x in v] for c, v in plain["hits"].items()},
                   "hits_planted": {c: [len(x) for x in v] for c, v in bp["hits"].items()},
                   "tones": tones_out, "shuffled": shuffled,
                   "times": {"fetch_s": fetch_s, "plain_s": plain["search_s"] + plain["event_s"],
                             "planted_s": bp["search_s"] + bp["event_s"],
                             "block_s": round(time.monotonic() - started, 1)},
                   "peak_mb": {"plain": plain["peak_mb"], "planted": bp["peak_mb"]},
                   "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            yoke.write(out / p.name, res, indent=None)
            kept.unlink(missing_ok=True)
            n, pub = len(tones_out), ck(PUBLISHED["turboseti"])
            log(f"block {rec['block']} ({rec['class']}): at SNR 10, BLISS recovered "
                f"{sum(x['bliss'][pub]['three_looks'] == 'recovered' for x in tones_out)}/{n} in all three ON "
                f"looks; wrong-ON candidates {len(shared_hits(false.get(pub, {})))} (by shared hits); "
                f"{res['times']['block_s']} s, peak {max(res['peak_mb'].values())} MB")
    shutil.rmtree(work, ignore_errors=True)
    done = [x for x in out.glob("block_*.json") if bliss_done(x, config)]
    failed = [x.stem for x in done if "failed" in json.loads(x.read_text(encoding="utf-8"))]
    say(f"{target} {session}: BLISS on {len(done)} of {len(recs)} blocks"
        + (f" ({len(failed)} failed: {', '.join(failed)})" if failed else ""), flush=True)


# --- BLISS's hits through this search's cadence test ---------------------------

BLISS_HIT_CUT = 5.0     # its hits found once, at the lowest cut, as this search's are (SHADOW_MIN)
JUDGE_FORMAT = 1


def bliss_judge_config():
    """bliss_config, with the hit cut and the cadence test's code (onoff.py)."""
    import hashlib
    return dict(bliss_config(), judge_format=JUDGE_FORMAT, hit_cut=BLISS_HIT_CUT, cuts=list(CUTS_OURS),
                onoff=hashlib.sha256((yoke.ROOT / "onoff.py").read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16])


def _bliss_searched(cad, rec, cut=BLISS_HIT_CUT, shadows_from=None):
    """BLISS's hits (a bliss_curves.py record, found at `cut`) as this
    search's would be for onoff.judge: (hits, flattened spectra, complete) a
    look. A hit's frequency is at the look's start, as this search's; its box
    is the one this search's would have at its drift. With shadows_from (a
    lower cut in the same record), that cut's hits under `cut` are added as
    the shadow hits."""
    out = []
    for j, c in enumerate(cad):
        s = c["s"]
        n_t = c["spectra"].shape[0]
        span = max(n_t - 1, 1) * s["tsamp"]
        hits = []
        found = list(rec["hits"][str(float(cut))][j])
        if shadows_from is not None:
            found += [h for h in rec["hits"][str(float(shadows_from))][j] if h["snr"] < cut]
        for h in found:
            k = h["drift_hz_s"] * span / (s["foff"] * 1e6)
            hits.append({"frequency_mhz": h["freq_mhz"], "drift_hz_s": h["drift_hz_s"], "snr": h["snr"],
                         "box_channels": max(1, math.ceil(abs(k) / max(n_t - 1, 1) - 1e-9))})
        hits.sort(key=lambda h: -h["snr"])
        out.append((hits, searching.flatten(c["spectra"]).astype(np.float32), True))
    return out


def judge_folder(target, session):
    return folder(target, session) / "bliss_judge"


def judge_whole(r, config):
    """A bliss-judge record made with this configuration and with every field
    the tables read: TONES signals, each judged at every cut, and the 19
    wrong choices and the true one at every cut."""
    cuts = [ck(c) for c in CUTS_OURS]
    wrong = {str(o) for o in itertools.combinations(range(6), 3) if o != TRUE}
    try:
        return (r.get("config") == config and len(r["tones"]) == TONES
                and all(c in t["judged"] and "three_looks" in t["judged"][c] for t in r["tones"] for c in cuts)
                and all(set(r["false"].get(c, {})) == wrong and c in r["true_plain"] for c in cuts))
    except (KeyError, TypeError, AttributeError):
        return False


def add_bliss_judge(target, say=print):
    """BLISS's hits through this search's cadence test (comparable.md step
    11), so a difference from BLISS's own event stage can be laid to the
    detector or to the cadence logic. Each of step 4's blocks read again
    (checked as add_bliss checks it); BLISS's hits found once a look at
    BLISS_HIT_CUT (bliss_curves.py, the GPU, its authors' pipeline), on the
    unplanted looks and on the record's signals planted again; onoff.judge
    on them as on this search's own hits (a cut X makes BLISS's hits under X
    shadow hits), every choice at CUTS_OURS unplanted and the true choice
    planted; scored as the others. One record a block under bliss_judge/,
    written whole, done when it parses with this configuration; a lock, as
    add_bliss."""
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, target)
    db.close()
    base, out = folder(target, session), judge_folder(target, session)
    out.mkdir(parents=True, exist_ok=True)
    lock = _run_lock(out / "run.lock")  # noqa: F841 -- held until the process ends
    config = bliss_judge_config()
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    recs = sorted(base.glob("block_*.json"))
    classes = json.loads((base / "blocks.json").read_text(encoding="utf-8"))["chosen"]
    recs.sort(key=lambda p: (classes.get(str(int(p.stem.split("_")[1]))) != "crowded", p.name))

    def done(p):
        try:
            return judge_whole(json.loads(p.read_text(encoding="utf-8")), config)
        except (OSError, ValueError):
            return False
    todo = [p for p in recs if not done(out / p.name)]
    say(f"{target} {session}: BLISS's hits through this search's cadence test on {len(todo)} of {len(recs)} blocks",
        flush=True)
    work = ROOT / "work_bliss_judge"

    def log(line):
        say("  " + line, flush=True)
        with open(out / "progress.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%S ", time.gmtime()) + line + "\n")

    for p in todo:
        started = time.monotonic()
        rec = json.loads(p.read_text(encoding="utf-8"))
        cad = _cadence(seti.read_looks(urls, *block_list[rec["block"]]), urls)
        if [c["s"]["tstart"] for c in cad] != rec["tstarts"]:
            raise yoke.Refusal("INVALID_REQUEST", f"block {rec['block']} read again is not the one recorded")
        moved = [t["f_mhz"] for t in rec["tones"] if round(where(cad, t, 0)[1], 6) != t["f_mhz"]]
        if moved:
            raise yoke.Refusal("INVALID_REQUEST", f"block {rec['block']}: signals not where recorded: {moved[:3]}")
        shutil.rmtree(work, ignore_errors=True)
        times = {}
        try:
            t = time.monotonic()
            paths = [seti.save(c["s"], work / "plain" / f"{j}.h5") for j, c in enumerate(cad)]
            hp = _bliss_tool(work / "plain.json", "true", paths, cuts=(BLISS_HIT_CUT,), shuffles=0)
            planted = plant(cad, rec["tones"])
            cad_p = [dict(c, spectra=x["spectra"]) for c, x in zip(cad, planted)]
            del planted
            paths = [seti.save(dict(c["s"], spectra=c["spectra"]), work / "planted" / f"{j}.h5")
                     for j, c in enumerate(cad_p)]
            hb = _bliss_tool(work / "planted.json", "true", paths, cuts=(BLISS_HIT_CUT,), shuffles=0)
            times["bliss_s"] = round(time.monotonic() - t, 1)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        t = time.monotonic()
        searched = _bliss_searched(cad, hp)
        false, true_plain = {}, {}
        caches = [{} for _ in range(6)]
        for ons in itertools.combinations(range(6), 3):
            for cut in CUTS_OURS:
                looks, events, order = our_events(cad, searched, ons, cut, caches)
                kept = _our_kept(looks, events, order)
                if ons == TRUE:
                    true_plain[ck(cut)] = kept
                else:
                    false.setdefault(ck(cut), {})[str(ons)] = kept
                for lk in looks:
                    lk.flat = None
        del searched, caches
        times["judge_plain_s"] = round(time.monotonic() - t, 1)
        t = time.monotonic()
        true_planted = _ours_true(cad_p, _bliss_searched(cad_p, hb))
        times["judge_planted_s"] = round(time.monotonic() - t, 1)
        tones_out = []
        for tn in rec["tones"]:
            t_f = {j: where(cad, tn, j)[1] for j in TRUE}
            tones_out.append({"f_mhz": tn["f_mhz"], "drift": tn["drift"], "s_in": tn["s_in"],
                              "judged": {ck(c): _status(t_f, tn["drift"], true_planted[str(c)], true_plain[ck(c)])
                                         for c in CUTS_OURS}})
        times["block_s"] = round(time.monotonic() - started, 1)
        res = {"format": FORMAT, "block": rec["block"], "class": rec["class"], "config": config,
               "provenance": {"plain": hp["provenance"], "planted": hb["provenance"]},
               "hits": {"plain": [len(x) for x in hp["hits"][str(BLISS_HIT_CUT)]],
                        "planted": [len(x) for x in hb["hits"][str(BLISS_HIT_CUT)]]},
               "false": false, "true_plain": true_plain, "tones": tones_out, "times": times,
               "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        yoke.write(out / p.name, res, indent=None)
        pub = ck(PUBLISHED["ours"])
        log(f"block {rec['block']} ({rec['class']}): at SNR 10 recovered "
            f"{sum(x['judged'][pub]['three_looks'] == 'recovered' for x in tones_out)}/{len(tones_out)}; "
            f"wrong-ON candidates {len(shared_hits(false.get(pub, {})))}; hits {res['hits']['plain']}; "
            f"{times['block_s']} s")
    n = sum(done(out / p.name) for p in recs)
    say(f"{target} {session}: BLISS's hits through this search's cadence test on {n} of {len(recs)} blocks",
        flush=True)


CONTROL_CUT = 30.0     # the matched cut of this search and of BLISS's hits through its cadence test


def bliss_control(target, blocks, say=print):
    """The same BLISS hit list under each ON/OFF logic (comparable.md step
    11's control). bliss-judge finds BLISS's hits once at BLISS_HIT_CUT and
    cuts them afterwards; BLISS's own run at CONTROL_CUT groups its hits at
    that cut, and the grouping changes with the cut, so the two are not the
    same input. Here, on the unplanted looks of the named blocks, BLISS's
    hits are found at both cuts in one run (the GPU, shuffles=0), and the
    distinct false candidates of the 19 wrong choices at CONTROL_CUT
    (shared hits) are counted for: BLISS's event stage on the CONTROL_CUT
    hits (the port, in the same run, on the same in-memory hit lists in its
    documented order); this search's cadence test on those hits with no
    shadow hits; on them with the BLISS_HIT_CUT hits under the cut added as
    shadow hits; and on the BLISS_HIT_CUT hits alone (as bliss-judge, run
    again). The earlier runs' counts (add_bliss, bliss-judge) are recorded
    beside them, not used in their place. A fingerprint of each cut's hit
    lists, as both logics were given them, is in the record. One record a
    block under bliss_control/."""
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, target)
    db.close()
    base, out = folder(target, session), folder(target, session) / "bliss_control"
    out.mkdir(parents=True, exist_ok=True)
    lock = _run_lock(out / "run.lock")  # noqa: F841 -- held until the process ends
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    work = ROOT / "work_bliss_control"
    cut = ck(CONTROL_CUT)
    for b in blocks:
        rec = json.loads((base / f"block_{b:03d}.json").read_text(encoding="utf-8"))
        started = time.monotonic()
        cad = _cadence(seti.read_looks(urls, *block_list[rec["block"]]), urls)
        if [c["s"]["tstart"] for c in cad] != rec["tstarts"]:
            raise yoke.Refusal("INVALID_REQUEST", f"block {b} read again is not the one recorded")
        shutil.rmtree(work, ignore_errors=True)
        try:
            paths = [seti.save(c["s"], work / f"{j}.h5") for j, c in enumerate(cad)]
            h = _bliss_tool(work / "plain.json", "all", paths, cuts=(BLISS_HIT_CUT, CONTROL_CUT), shuffles=0)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        arrangements = {"hits at 30, no shadow hits": _bliss_searched(cad, h, CONTROL_CUT),
                        "hits at 30, shadow hits from 5": _bliss_searched(cad, h, CONTROL_CUT, BLISS_HIT_CUT),
                        "hits at 5 (as bliss-judge)": _bliss_searched(cad, h, BLISS_HIT_CUT)}
        counts = {}
        for name, searched in arrangements.items():
            false = {}
            caches = [{} for _ in range(6)]
            for ons in itertools.combinations(range(6), 3):
                if ons == TRUE:
                    continue
                looks, events, order = our_events(cad, searched, ons, CONTROL_CUT, caches)
                false[str(ons)] = _our_kept(looks, events, order)
                for lk in looks:
                    lk.flat = None
            counts[name] = len(shared_hits(false))
        import hashlib
        same_run = {str(tuple(e["as_on"])): _bliss_kept(e["rows"]) for e in h["events"]
                    if tuple(e["as_on"]) != TRUE and e["cut"] == CONTROL_CUT}
        if len(same_run) != 19:
            raise yoke.Refusal("INTERNAL_ERROR", f"block {b}: BLISS's events for {len(same_run)} wrong choices, not 19")
        fingerprint = {k: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()[:16]
                       for k, v in h["hits"].items()}
        native = json.loads((bliss_folder(target, session) / f"block_{b:03d}.json").read_text(encoding="utf-8"))
        judged = json.loads((judge_folder(target, session) / f"block_{b:03d}.json").read_text(encoding="utf-8"))
        res = {"block": b, "class": rec["class"], "cut": CONTROL_CUT, "config": bliss_judge_config(),
               "provenance": h["provenance"], "hits_fingerprint": fingerprint,
               "hits": {k: [len(x) for x in v] for k, v in h["hits"].items()},
               "false_distinct": {"BLISS's event stage, same hits": len(shared_hits(same_run)),
                                  **counts,
                                  "BLISS's event stage, add_bliss's run": len(shared_hits(native["false"][cut])),
                                  "hits at 5, bliss-judge's record": len(shared_hits(judged["false"][cut]))},
               "s": round(time.monotonic() - started, 1),
               "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        yoke.write(out / f"block_{b:03d}.json", res, indent=None)
        say(f"  block {b} ({rec['class']}): distinct false candidates at SNR {CONTROL_CUT:g}: "
            + "; ".join(f"{k} {v}" for k, v in res["false_distinct"].items()) + f"; hits {res['hits']}; {res['s']} s",
            flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("target")
    r.add_argument("--blocks", type=int)
    r.add_argument("--shard", default="0/1", help="i/n: every n-th chosen block from the i-th")
    t = sub.add_parser("tables")
    t.add_argument("target")
    t = sub.add_parser("tracks", help="add the measured ON tracks to blocks recorded without them")
    t.add_argument("target")
    b = sub.add_parser("bliss", help="BLISS on the recorded blocks (comparable.md step 11)")
    b.add_argument("target")
    b.add_argument("--blocks", type=int)
    b.add_argument("--shard", default="0/1")
    j = sub.add_parser("bliss-judge", help="BLISS's hits through this search's cadence test (step 11)")
    j.add_argument("target")
    c = sub.add_parser("bliss-control", help="the same BLISS hits under each ON/OFF logic, on named blocks (step 11)")
    c.add_argument("target")
    c.add_argument("--blocks", default="35,129", help="comma-separated block numbers")
    a = p.parse_args(argv)
    try:
        if a.command == "run":
            run(a.target, a.blocks, shard=tuple(int(x) for x in a.shard.split("/")))
        elif a.command == "tracks":
            add_tracks(a.target)
        elif a.command == "bliss":
            add_bliss(a.target, shard=tuple(int(x) for x in a.shard.split("/")), count=a.blocks)
        elif a.command == "bliss-judge":
            add_bliss_judge(a.target)
        elif a.command == "bliss-control":
            bliss_control(a.target, [int(x) for x in a.blocks.split(",")])
        else:
            import matched_tables
            matched_tables.write(a.target)
    except yoke.Refusal as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
