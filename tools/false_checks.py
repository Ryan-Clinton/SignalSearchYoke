"""What the false-candidate control measures, and how sure its numbers are
(the false-positive audit, docs/audits.md 4). Supplementary: the published
rates (matched_tables._rate) and the frozen verdicts of steps 10 and 12 are
unchanged; these read the same block records.

    python tools/false_checks.py interval      the combined interval, mended, with a coverage simulation
    python tools/false_checks.py assignments   one wrong choice against the union of 19; recurrence
    python tools/false_checks.py grouping      what changes identity under other rules of "one signal"
    python tools/false_checks.py windows       the rate's interval with windows of consecutive blocks resampled
    python tools/false_checks.py chronological this search's wrong choices judged in time order (16 blocks read again)
    python tools/false_checks.py all          the four from the records (not chronological)

- **interval**: matched_tables._rate bootstraps each class's blocks and adds
  them by the class's share of the session. A class with no candidate then
  adds nothing in every draw, so its own uncertainty (its Poisson upper limit,
  which _rate reports for the class) is lost from the combined interval
  unless every class is empty. Two replacements, both supplementary: a
  hybrid (a class with none drawn from the flat-prior posterior of a Poisson
  rate, Gamma(1, 1/blocks); a class with some bootstrapped), exploratory, as
  it is neither a confidence nor a credible interval; and a conservative one
  (each class's interval the wider of its bootstrap and the exact Poisson
  interval of its total, weighted and added end to end). A coverage
  simulation (rare, concentrated and correlated candidates in the sessions'
  layouts) gives how often each holds the true rate.
- **assignments**: the published rate is distinct candidates over all 19
  wrong choices a block (a stress test of many assignments). One real
  observation is one assignment: per wrong choice, its distinct candidates a
  block (mean, median, 90th percentile, the share of blocks with any), and
  the union over the mean of one (the amplification); and of the union's
  candidates, in how many of the 19 each appears.
- **grouping**: the candidates of the wrong choices as one signal by shared
  hits (published), by frequency and drift within the tolerances, and by
  frequency within 3 kHz: how many shared-hit groups are joined with others,
  or split, under each.
- **windows**: the false rate's interval with blocks resampled singly and in
  windows of 4 and 16 consecutive blocks of the session (by block number),
  within each class.
- **chronological**: a wrong choice's six looks put in time order, each called
  ON or OFF by the choice, against the published ON, OFF pairs; this search's
  test only (turboSETI's event stage needs ON and OFF to alternate), 16
  blocks of 2017 and 2016 read again.

Writes data/analysis/false_<name>.json.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import matched  # noqa: E402
import matched_tables  # noqa: E402
import measure  # noqa: E402
import onoff  # noqa: E402
import seti  # noqa: E402
import yoke  # noqa: E402

OUT = yoke.DATA / "analysis"
SESSIONS = (("KIC8462852", "2017"), ("HIP17147", "2016"), ("NGC6946", "2019"))
PIPES = ("ours", "turboseti")
CUTS = (10, 30)
BOOT = 4000


def _say(*a):
    print(*a, flush=True)


# --- the interval ------------------------------------------------------------------------

def mended_interval(counts, weights, rng, boot=BOOT):
    """A hybrid, exploratory interval: a class with candidates bootstrapped over
    its blocks, a class with none drawn from the posterior of a Poisson rate
    under a flat prior, Gamma(1, 1/blocks) (whose 97.5% point is the exact
    Garwood upper limit for none). A mixture of a bootstrap and a posterior, it
    is neither a frequentist confidence interval nor a credible interval; with
    nothing counted its lower end is above zero, which says nothing about the
    rate being positive. counts: {class: [per block]}."""
    est = sum(weights[c] * (np.mean(n) if len(n) else 0.0) for c, n in counts.items())
    draws = np.zeros(boot)
    for c, n in counts.items():
        n = np.asarray(n, float)
        if not len(n):
            continue
        if n.sum() > 0:
            draws += weights[c] * np.array([rng.choice(n, len(n)).mean() for _ in range(boot)])
        else:
            draws += weights[c] * rng.gamma(1.0, 1.0 / len(n), boot)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(est), (float(lo), float(hi))


def class_interval(n, rng, boot=BOOT):
    """One class's rate a block, conservatively: the wider, at each end, of
    the bootstrap over its blocks and the exact (Garwood) Poisson interval of
    its total; with none counted, 0 to the exact upper limit."""
    n = np.asarray(n, float)
    m = max(len(n), 1)
    k = int(n.sum())
    # exact (Garwood) for small totals; for large ones the normal approximation, accurate there and fast
    g_lo, g_hi = ((x / m for x in measure.poisson_interval(k)) if k <= 200
                  else ((k - 1.96 * k ** 0.5) / m, (k + 1.96 * k ** 0.5) / m))
    if not n.sum():
        return 0.0, float(g_hi)
    b_lo, b_hi = np.percentile([rng.choice(n, len(n)).mean() for _ in range(boot)], [2.5, 97.5])
    return float(min(b_lo, g_lo)), float(max(b_hi, g_hi))


def conservative_interval(counts, weights, rng, boot=BOOT):
    """The weighted rate and a conservative interval: each class's interval
    (class_interval) weighted and added, ends to ends. Wider than a joint 95%
    interval by construction; its coverage is measured, not assumed."""
    est = sum(weights[c] * (np.mean(n) if len(n) else 0.0) for c, n in counts.items())
    lo = hi = 0.0
    for c, n in counts.items():
        if not len(n):
            continue
        a, b = class_interval(n, rng, boot)
        lo += weights[c] * a
        hi += weights[c] * b
    return float(est), (float(lo), float(hi))


def published_interval(counts, weights, rng, boot=BOOT):
    """matched_tables._rate's combined interval, as published."""
    by = {}
    for c, n in counts.items():
        m = max(len(n), 1)
        by[c] = (n, measure.poisson_interval(0)[1] / m)
    est = sum(weights[c] * (np.mean(n) if len(n) else 0.0) for c, n in counts.items())
    boots = [sum(weights[c] * (np.mean(rng.choice(n, len(n))) if len(n) else 0) for c, (n, _) in by.items())
             for _ in range(boot)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    if hi == 0:
        hi = sum(weights[c] * (up if not sum(n) else 0) for c, (n, up) in by.items())
    return float(est), (float(lo), float(hi))


METHODS = {"published": "published_interval", "hybrid (exploratory)": "mended_interval",
           "conservative": "conservative_interval"}


def _draw(rng, sc):
    """One simulated session's counts: clean blocks Poisson; crowded blocks
    negative binomial (shape 0.2: most none, a few many); with "runs", the
    crowded blocks' rate shared by runs of that many neighbouring blocks (a
    gamma-distributed intensity each run: correlated, overdispersed)."""
    clean = rng.poisson(sc["rate"]["clean"], sc["n"]["clean"])
    k = sc.get("runs")
    if k:
        n = sc["n"]["crowded"]
        lam = np.repeat(rng.gamma(0.3, sc["rate"]["crowded"] / 0.3, -(-n // k)), k)[:n]
        crowded = rng.poisson(lam)
    else:
        crowded = rng.negative_binomial(0.2, 0.2 / (0.2 + sc["rate"]["crowded"]), sc["n"]["crowded"])
    return {"clean": clean.tolist(), "crowded": crowded.tolist()}


def coverage(trials=1000, boot=1000, seed=12):
    """How often each interval holds the true weighted rate, for rare,
    concentrated and correlated candidates, in the sessions' layouts."""
    rng = np.random.default_rng(seed)
    w19 = {"clean": 61 / 64, "crowded": 3 / 64}
    w17 = {"clean": 247 / 308, "crowded": 61 / 308}
    w16 = {"clean": 120 / 304, "crowded": 184 / 304}
    scenarios = [
        {"name": "2019 layout: 61 clean, 3 crowded; clean 0.01, crowded 0.3", "n": {"clean": 61, "crowded": 3},
         "w": w19, "rate": {"clean": 0.01, "crowded": 0.3}},
        {"name": "2019 layout: clean 0.03, crowded 1.0", "n": {"clean": 61, "crowded": 3},
         "w": w19, "rate": {"clean": 0.03, "crowded": 1.0}},
        {"name": "2017 layout: 60 clean, 61 crowded; clean 0.005, crowded 0.3", "n": {"clean": 60, "crowded": 61},
         "w": w17, "rate": {"clean": 0.005, "crowded": 0.3}},
        {"name": "2017 layout: clean 0.05, crowded 0.5", "n": {"clean": 60, "crowded": 61},
         "w": w17, "rate": {"clean": 0.05, "crowded": 0.5}},
        {"name": "2017 layout, crowded correlated in runs of 4: clean 0.005, crowded 0.3",
         "n": {"clean": 60, "crowded": 61}, "w": w17, "rate": {"clean": 0.005, "crowded": 0.3}, "runs": 4},
        {"name": "2016 layout, crowded correlated in runs of 8: clean 0.5, crowded 60",
         "n": {"clean": 60, "crowded": 61}, "w": w16, "rate": {"clean": 0.5, "crowded": 60.0}, "runs": 8},
    ]
    out = []
    for sc in scenarios:
        truth = sum(sc["w"][c] * sc["rate"][c] for c in sc["n"])
        hit = {m: 0 for m in METHODS}
        width = {m: [] for m in METHODS}
        for _ in range(trials):
            counts = _draw(rng, sc)
            for name, f in METHODS.items():
                _, (lo, hi) = globals()[f](counts, sc["w"], rng, boot)
                hit[name] += lo <= truth <= hi
                width[name].append(hi - lo)
        out.append({"scenario": sc["name"], "true_rate": round(truth, 5), "trials": trials,
                    "coverage": {k: round(v / trials, 3) for k, v in hit.items()},
                    "median_width": {k: round(float(np.median(v)), 4) for k, v in width.items()}})
    return out


def _session(target):
    _, meta, recs = matched_tables.load(target)
    total = meta["of"]["clean"] + meta["of"]["crowded"]
    weights = {c: meta["of"][c] / total for c in ("clean", "crowded")}
    return meta, sorted(recs, key=lambda r: r["block"]), weights


def _key(p):
    return "turboseti" if p == "turboseti" else "ours"


def interval(say=_say):
    rng = np.random.default_rng(1)
    rec = {"coverage": coverage(), "sessions": {}}
    for target, year in SESSIONS:
        _, recs, weights = _session(target)
        rows = {}
        for p in PIPES:
            grid = matched.CUTS_OURS if p == "ours" else matched.CUTS_TURBO
            for c in grid:
                k = matched.ck(c)
                counts = {cls: [matched_tables.distinct(r, r[p]["false"][k], "shared hits") for r in recs
                                if r["class"] == cls] for cls in ("clean", "crowded")}
                e, pub = published_interval(counts, weights, rng)
                _, men = mended_interval(counts, weights, rng)
                _, con = conservative_interval(counts, weights, rng)
                rows[f"{p} {k}"] = {"per_block": round(e, 4), "published": [round(x, 4) for x in pub],
                                    "hybrid (exploratory)": [round(x, 4) for x in men],
                                    "conservative": [round(x, 4) for x in con],
                                    "classes_with_none": [cls for cls, n in counts.items() if n and not sum(n)]}
        rec["sessions"][year] = {"target": target, "weights": weights, "rates": rows}
    rec["kind"] = "measured"
    yoke.write(OUT / "false_interval.json", rec, indent=1, stamp=True)
    for c in rec["coverage"]:
        say(f"coverage, {c['scenario']}: {c['coverage']}")
    say(f"2019, this search at 8: {rec['sessions']['2019']['rates']['ours 8']}")
    return rec


# --- assignments, grouping, windows -------------------------------------------------------

def _groups(events):
    """Union-find over events sharing a member hit: a list of sets of event indices."""
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
        out.setdefault(root(n), set()).add(n)
    return list(out.values())


def assignment_stats(by):
    """One block's wrong choices ({choice: [kept candidate]}): the distinct
    candidates of each choice alone, of their union, and for each of the
    union's groups the number of choices it appears in."""
    per = [len(matched.shared_hits({ch: evs})) for ch, evs in by.items()]
    events, choice_of = [], []
    for ch, evs in by.items():
        for ev in evs:
            events.append(ev)
            choice_of.append(ch)
    recur = [len({choice_of[i] for i in g}) for g in _groups(events)]
    return per, len(matched.shared_hits(by)), recur


def window_groups(per, w):
    """Blocks {block: (class, count)} grouped by class and by window of w
    consecutive block numbers: {class: [[counts of one window], ...]}."""
    groups = {}
    for b, (cl, n) in per.items():
        groups.setdefault((cl, b // w), []).append(n)
    return {cl: [v for (c2, _), v in sorted(groups.items()) if c2 == cl] for cl in ("clean", "crowded")}


def assignments(say=_say):
    rec = {"sessions": {}}
    for target, year in SESSIONS:
        _, recs, weights = _session(target)
        res = {}
        for p in PIPES:
            for c in CUTS:
                k = matched.ck(c)
                single, union, recur = [], [], []
                any_share = []
                for r in recs:
                    per, u, rc = assignment_stats(r[p]["false"].get(k, {}))
                    single += per
                    any_share.append(np.mean([x > 0 for x in per]) if per else 0.0)
                    union.append(u)
                    recur += rc
                mean_single = float(np.mean(single)) if single else 0.0
                mean_union = float(np.mean(union)) if union else 0.0
                res[f"{p} {k}"] = {
                    "one_choice": {"mean": round(mean_single, 4), "median": float(np.median(single)) if single else 0,
                                   "p90": float(np.percentile(single, 90)) if single else 0,
                                   "share_with_any": round(float(np.mean([x > 0 for x in single])), 4) if single else 0},
                    "union_of_19_a_block": round(mean_union, 4),
                    "amplification": round(mean_union / mean_single, 2) if mean_single else None,
                    "groups_in_how_many_choices": {"median": float(np.median(recur)) if recur else None,
                                                   "share_in_one_only": round(float(np.mean([x == 1 for x in recur])), 4)
                                                   if recur else None,
                                                   "share_in_5_or_more": round(float(np.mean([x >= 5 for x in recur])), 4)
                                                   if recur else None},
                    "note": "unweighted by class: blocks as sampled"}
        rec["sessions"][year] = {"target": target, "results": res}
    rec["kind"] = "measured"
    yoke.write(OUT / "false_assignments.json", rec, indent=1, stamp=True)
    for y, s in rec["sessions"].items():
        for k, v in s["results"].items():
            say(f"{y} {k}: one choice {v['one_choice']['mean']} a block, union {v['union_of_19_a_block']}, "
                f"x{v['amplification']}; groups in one choice only {v['groups_in_how_many_choices']['share_in_one_only']}")
    return rec


def _partition(points, reach_mhz, close):
    """Single-link groups of points (f MHz, drift): sorted by frequency, each
    compared only with those within reach_mhz above it."""
    parent = list(range(len(points)))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    order = sorted(range(len(points)), key=lambda i: points[i][0])
    for a, i in enumerate(order):
        for j in order[a + 1:]:
            if points[j][0] - points[i][0] > reach_mhz:
                break
            if close(points[i], points[j]):
                parent[root(i)] = root(j)
    return [root(i) for i in range(len(points))]


def grouping(say=_say):
    rec = {"sessions": {}}
    for target, year in SESSIONS:
        _, recs, _ = _session(target)
        res = {}
        for p in PIPES:
            for c in CUTS:
                k = matched.ck(c)
                tot = {"shared_hit_groups": 0, "frequency_and_drift": {"groups": 0, "joined": 0, "split": 0},
                       "frequency_within_3_khz": {"groups": 0, "joined": 0, "split": 0}}
                for r in recs:
                    evs = [ev for v in r[p]["false"].get(k, {}).values() for ev in v]
                    if not evs:
                        continue
                    t = r["tstarts"]
                    base = [0] * len(evs)
                    for g, idx in enumerate(_groups(evs)):
                        for i in idx:
                            base[i] = g
                    tot["shared_hit_groups"] += len(set(base))
                    pts = [(ev["f_mhz"] - ev["drift"] * (t[ev["look"]] - t[0]) * 86400 / 1e6, ev["drift"]) for ev in evs]
                    rules = {"frequency_and_drift": (matched.TOL_HZ / 1e6, lambda a, b: abs(a[0] - b[0]) * 1e6
                                                     <= matched.TOL_HZ and abs(a[1] - b[1]) <= matched.TOL_DRIFT),
                             "frequency_within_3_khz": (3e-3, lambda a, b: abs(a[0] - b[0]) <= 3e-3)}
                    for name, (reach, close) in rules.items():
                        alt = _partition(pts, reach, close)
                        tot[name]["groups"] += len(set(alt))
                        # joined: shared-hit groups that share an alternative group with another; split: one
                        # shared-hit group spread over several alternative groups.
                        alt_of = {}
                        for i in range(len(evs)):
                            alt_of.setdefault(base[i], set()).add(alt[i])
                        tot[name]["split"] += sum(len(v) > 1 for v in alt_of.values())
                        base_of = {}
                        for i in range(len(evs)):
                            base_of.setdefault(alt[i], set()).add(base[i])
                        tot[name]["joined"] += sum(len(v) for v in base_of.values() if len(v) > 1)
                res[f"{p} {k}"] = tot
        rec["sessions"][year] = {"target": target, "results": res}
    rec["kind"] = "measured"
    yoke.write(OUT / "false_grouping.json", rec, indent=1, stamp=True)
    for y, s in rec["sessions"].items():
        for k, v in s["results"].items():
            say(f"{y} {k}: {v['shared_hit_groups']} shared-hit groups; by frequency and drift "
                f"{v['frequency_and_drift']}; within 3 kHz {v['frequency_within_3_khz']}")
    return rec


def windows(say=_say):
    rng = np.random.default_rng(2)
    rec = {"sessions": {}}
    for target, year in SESSIONS:
        _, recs, weights = _session(target)
        res = {}
        for p in PIPES:
            for c in CUTS:
                k = matched.ck(c)
                per = {int(r["block"]): (r["class"], matched_tables.distinct(r, r[p]["false"][k], "shared hits"))
                       for r in recs}
                est = sum(weights[cl] * np.mean([n for cl2, n in per.values() if cl2 == cl] or [0])
                          for cl in ("clean", "crowded"))
                out = {"per_block": round(float(est), 4)}
                for w in (1, 4, 16):
                    by_cls = window_groups(per, w)
                    draws = []
                    for _ in range(BOOT):
                        tot = 0.0
                        for cl, gs in by_cls.items():
                            if not gs:
                                continue
                            pick = [x for i in rng.integers(0, len(gs), len(gs)) for x in gs[i]]
                            tot += weights[cl] * np.mean(pick)
                        draws.append(tot)
                    lo, hi = np.percentile(draws, [2.5, 97.5])
                    out[f"windows_of_{w}"] = {"interval": [round(float(lo), 4), round(float(hi), 4)],
                                              "windows": {cl: len(gs) for cl, gs in by_cls.items()},
                                              "few_windows": any(0 < len(gs) < 20 for gs in by_cls.values())}
                res[f"{p} {k}"] = out
        rec["sessions"][year] = {"target": target, "results": res}
    rec["kind"] = "measured"
    yoke.write(OUT / "false_windows.json", rec, indent=1, stamp=True)
    for y, s in rec["sessions"].items():
        for k, v in s["results"].items():
            say(f"{y} {k}: {v['per_block']}; by windows of 1/4/16: "
                + ", ".join(str(v[f'windows_of_{w}']['interval']) for w in (1, 4, 16)))
    return rec


# --- chronological ----------------------------------------------------------------------------

def _judge_in_time_order(cad, searched, ons, cut, caches):
    """onoff.judge with the six looks in time order, each ON or OFF by the
    choice (the ON flag set after the look is made: the verdict reads it, and
    the projection between looks uses each look's own start time)."""
    looks = []
    for j in range(6):
        s = cad[j]["s"]
        hits = [dict(h, shadow=h["snr"] < cut) for h in searched[j][0]]
        lk = matched.CachedLook(hits, s["tstart"], s["fch1"], s["foff"], s["tsamp"], searched[j][1], j, cache=caches[j])
        lk.on = j in ons
        looks.append(lk)
    return looks, onoff.judge(looks), list(range(6))


def chronological(say=_say):
    import turbo_checks
    rec = {"blocks": [], "kind": "measured"}
    totals = {f"{w} {c}": {"union": 0, "choices_with_any": 0} for w in ("pairs", "time") for c in CUTS}
    differ = {str(c): 0 for c in CUTS}
    ident = {str(c): 0 for c in CUTS}
    by_choice_diff, by_class_diff = {}, {}
    for target in ("KIC8462852", "HIP17147"):
        session, urls, base, chosen, picks = turbo_checks._picks(target)
        block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
        for b in picks:
            r = json.loads((base / f"block_{b:03d}.json").read_text(encoding="utf-8"))
            cad = matched._cadence(seti.read_looks(urls, *block_list[b]), urls)
            if [c["s"]["tstart"] for c in cad] != r["tstarts"]:
                raise yoke.Refusal("INVALID_REQUEST", f"block {b} read again is not the one recorded")
            searched = matched.our_search(cad)
            caches = [{} for _ in range(6)]
            row = {"target": target, "block": b, "class": chosen[b]}
            for c in CUTS:
                for name, f in (("pairs", matched.our_events), ("time", _judge_in_time_order)):
                    by = {}
                    for ons in turbo_checks.CHOICES:
                        if ons == matched.TRUE:
                            continue
                        looks, events, order = f(cad, searched, ons, c, caches)
                        by[str(ons)] = matched._our_kept(looks, events, order)
                        for lk in looks:
                            lk.flat = None
                    row[f"{name} {c}"] = {"union": len(matched.shared_hits(by)),
                                          "choices_with_any": sum(bool(v) for v in by.values()),
                                          "by_choice": {k: len(v) for k, v in by.items()},
                                          "identities": {k: sorted(sorted(matched._hit_key(m) for m in ev["members"])
                                                                   for ev in v) for k, v in by.items()}}
                    totals[f"{name} {c}"]["union"] += row[f"{name} {c}"]["union"]
                    totals[f"{name} {c}"]["choices_with_any"] += row[f"{name} {c}"]["choices_with_any"]
                differ[str(c)] += sum(row[f"pairs {c}"]["by_choice"][k] != row[f"time {c}"]["by_choice"][k]
                                      for k in row[f"pairs {c}"]["by_choice"])
                ident[str(c)] += sum(row[f"pairs {c}"]["identities"][k] != row[f"time {c}"]["identities"][k]
                                     for k in row[f"pairs {c}"]["identities"])
                for k in row[f"pairs {c}"]["identities"]:
                    if row[f"pairs {c}"]["identities"][k] != row[f"time {c}"]["identities"][k]:
                        by_choice_diff.setdefault(str(c), {}).setdefault(k, 0)
                        by_choice_diff[str(c)][k] += 1
                        by_class_diff.setdefault(str(c), {}).setdefault(chosen[b], 0)
                        by_class_diff[str(c)][chosen[b]] += 1
            rec["blocks"].append(row)
            say(f"{target} block {b}: " + ", ".join(f"{k} {row[k]['union']}" for k in row if " " in k))
    rec["totals"] = totals
    rec["choices_whose_count_differs"] = differ
    rec["choices_whose_candidates_differ"] = ident
    rec["candidate_differences_by_choice"] = by_choice_diff
    rec["candidate_differences_by_class"] = by_class_diff
    rec["published_check"] = "pairs: as matched.py orders a choice's looks (ON, OFF pairs); time: in time order"
    yoke.write(OUT / "false_chronological.json", rec, indent=1, stamp=True)
    say(f"chronological: {totals}; choices differing {differ}")
    return rec


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = {"interval": interval, "assignments": assignments, "grouping": grouping, "windows": windows,
             "chronological": chronological}
    for name in (["interval", "assignments", "grouping", "windows"] if what == "all" else [what]):
        steps[name]()


if __name__ == "__main__":
    main()
