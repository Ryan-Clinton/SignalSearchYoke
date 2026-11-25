"""Planted signals through the search, the cadence test and the checks, in control B's own four cadences
(docs/control-injection.md is the protocol, committed before the first block was run). Control B found no candidate
left unexplained by the checks; this measures how many real-looking signals those checks would have kept.
Supplementary: no verdict of steps 4, 10 or 12 changes, and the frozen search and checks are used as they are.

    python tools/control_injection.py choose     the blocks, by the protocol's rule (once)
    python tools/control_injection.py run        every chosen block, in three lanes (hours; resumes)
    python tools/control_injection.py tables     the survival at each stage
    python tools/control_injection.py checks-left-out   each check left out in turn (from the records)
"""
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import records  # noqa: E402
import yoke  # noqa: E402

def _which_control():
    """Control B by default; `--control c` (or SSY_CONTROL=c) for control C (docs/control-c.md)."""
    if "--control" in sys.argv:
        i = sys.argv.index("--control")
        os.environ["SSY_CONTROL"] = sys.argv[i + 1].lower()
        del sys.argv[i:i + 2]
    return os.environ.get("SSY_CONTROL", "b")


CONTROL = _which_control()
SEED = {"b": 20261124, "c": 20261125}[CONTROL]
PER_CLASS = 4                    # blocks a cadence: this many capped and this many complete
LANES = 3
CUTS = (30, 10)
TRUE = (0, 2, 4)
OUT = Path(os.environ.get("SSY_INJECTION_OUT") or yoke.DATA / "analysis" / (
    "negative_controls" if CONTROL == "b" else f"negative_controls_{CONTROL}") / "injection")


def pick_blocks(done, n, seed, per_class=PER_CLASS):
    """`per_class` capped and complete blocks of one cadence's sweep record ({block: record}), drawn by seed from
    the blocks' completeness alone: what they hold is not looked at."""
    capped = sorted(int(k) for k, d in done.items() if d.get("complete") not in (1, True))
    whole = sorted(int(k) for k, d in done.items() if d.get("complete") in (1, True))
    rng = np.random.default_rng([seed, n])
    if len(capped) < per_class or len(whole) < per_class:
        raise yoke.Refusal("INVALID_REQUEST", "A cadence has too few capped or complete blocks.")
    out = {int(b): "capped" for b in rng.choice(capped, per_class, replace=False)}
    out |= {int(b): "complete" for b in rng.choice(whole, per_class, replace=False)}
    return dict(sorted(out.items()))


def choose(say=print):
    import negative_controls as nc
    path = OUT / "choice.json"
    if path.exists():
        raise yoke.Refusal("INVALID_REQUEST", f"{path} exists: the blocks are chosen once")
    cadences = []
    for n, (c, rec) in enumerate(nc._whole_control()):
        chosen = pick_blocks(rec["done"], n, SEED)
        cadences.append({"target": c["target"], "session": c["session"], "urls": [x["url"] for x in c["looks"]],
                         "blocks": {str(k): {"class": v, "range": rec["blocks"][k]} for k, v in chosen.items()}})
        say(f"{c['target']}: {chosen}")
    yoke.write(path, {"seed": SEED, "per_class": PER_CLASS, "cadences": cadences, "kind": "measured"}, indent=1, stamp=True)


def tone_at(tone_f, drift, ons_hits, kept, plain, cut, test, fit, match):
    """One planted signal at one cut: in how many ON looks a hit at the cut matches, the kept event that holds it
    (its index), and whether a candidate of the unplanted block already matched."""
    looks = 0
    for j in TRUE:
        rows = [{"look": j, "f_mhz": h["frequency_mhz"], "drift": h["drift_hz_s"]} for h in ons_hits[j] if h["snr"] >= cut]
        looks += bool(match({j: tone_f[j]}, drift, rows)[0])
    event = next((i for i, ev in enumerate(kept) if test(*fit(tone_f, drift, ev, True))), None)
    already = any(fit(tone_f, drift, ev)[0] >= 1 for ev in plain)
    return looks, event, already


def _plain_candidates(db, session, block):
    """The unplanted block's candidates with their ON member hits, from the store."""
    out = {}
    for event, pos, f, d in db.execute(
            "SELECT e.event_id, x.position, h.f_start_mhz, h.drift_hz_s FROM events e JOIN event_hits x ON "
            "x.event_id=e.event_id JOIN hits h ON h.hit_id=x.hit_id WHERE e.session=? AND e.block_idx=? AND "
            "e.label='candidate' AND e.superseded_run IS NULL AND x.position IN (0, 2, 4)", (session, block)):
        out.setdefault(event, {"members": []})["members"].append([pos, None, f, d])
    return list(out.values())


def one_block(cadence, k, info, ctx):
    import check
    import matched
    import seti
    urls, session = cadence["urls"], cadence["session"]
    cad = matched._cadence(seti.read_looks(urls, *info["range"]), urls)
    rng = np.random.default_rng([SEED, int(session.split("_")[-1]), k])
    tones = matched.tones(cad, rng)
    planted = matched.plant(cad, tones)
    cad_p = [dict(c, spectra=p["spectra"]) for c, p in zip(cad, planted)]
    searched = matched.our_search(cad_p)
    hits = [x[0] for x in searched]
    plain = _plain_candidates(ctx["db"], session, k)
    test = matched.RECOVERY[3][2]
    rows = [{"x0": t["x0"], "drift": t["drift"], "s_in": t["s_in"], "bin": t["bin"], "at": {}} for t in tones]
    caches = [{} for _ in range(6)]
    for cut in CUTS:
        looks, events, order = matched.our_events(cad_p, searched, TRUE, cut, caches)
        candidates = [e for e in events if e["label"] == "candidate"]
        kept = matched._our_kept(looks, events, order)
        verdicts = {}
        for t, row in zip(tones, rows):
            t_f = {j: matched.where(cad, t, j)[1] for j in TRUE}
            n, event, already = tone_at(t_f, t["drift"], hits, kept, plain, cut, test, matched._event_fit, matched._match)
            at = {"hit_looks": n, "candidate": event is not None, "already_in_the_block": already}
            if event is not None and not already:
                if event not in verdicts:
                    v = check.vet_from_store(ctx["db"], candidates[event], looks, session, ctx["target"], own=(),
                                             on_positions=TRUE, hits=ctx["hits"])
                    v6 = check.vet_from_store(ctx["db"], candidates[event], looks, session, ctx["target"], own=(),
                                              on_positions=TRUE, hits=ctx["hits"], bands_as_context=True)
                    verdicts[event] = {"verdict": v["verdict"], "reasons": v["reasons"],
                                       "verdict_context": v6["verdict"], "reasons_context": v6["reasons"]}
                at.update(verdicts[event])
            row["at"][str(cut)] = at
        for lk in looks:
            lk.flat = None
    return {"target": cadence["target"], "session": session, "block": k, "class": info["class"],
            "versions": _versions_now(),
            "complete": [bool(x[2]) for x in searched], "tones": rows, "kind": "measured"}


def _versions_now():
    """The versions a record is made by: the search, the checks in force, and the candidate version 6."""
    import seti
    import vetting
    return {"search": seti.SEARCH_VERSION, "checks": vetting.VERSION, "checks_context": vetting.VERSION_BANDS_AS_CONTEXT}


# where each version is written: (file, name)
VERSION_NAMES = {"search": ("seti.py", "SEARCH_VERSION"), "checks": ("vetting.py", "VERSION"),
                 "checks_context": ("vetting.py", "VERSION_BANDS_AS_CONTEXT")}


def versions_at(commit):
    """The versions as the code held them at `commit` (a key is missing where its name did not exist then), read
    from the files at that commit: for records made before records carried their versions."""
    import ast
    out = {}
    if not commit:
        return out
    for key, (path, name) in VERSION_NAMES.items():
        got = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{path}"], capture_output=True, text=True)
        if got.returncode:
            continue
        for node in ast.parse(got.stdout).body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
                out[key] = ast.literal_eval(node.value)
    return out


def _needed(rec):
    """The versions a record must be made by: the search and the checks in force, and version 6 where the record
    carries its verdicts."""
    keys = {"search", "checks"}
    if any("verdict_context" in a for t in rec.get("tones", []) for a in t.get("at", {}).values()):
        keys.add("checks_context")
    return keys


def record_problems(rec, cadence, k, info, versions=None, at_commit=versions_at, code=records.code_problems):
    """Why a block record is not this block's whole result under the protocol."""
    import matched
    name = f"{cadence['target']} {k}"
    if not isinstance(rec, dict):
        return [f"{name}: no record"]
    out = []
    if (rec.get("target"), rec.get("session"), rec.get("block"), rec.get("class")) != (
            cadence["target"], cadence["session"], k, info["class"]):
        out.append(f"{name}: the record is of another block")
    tones = rec.get("tones", [])
    if len(tones) != matched.TONES or len({(round(t["x0"], 4), round(t["drift"], 5)) for t in tones}) != matched.TONES:
        out.append(f"{name}: {len(tones)} signals, not {matched.TONES} different ones")
    if any(set(t.get("at", {})) != {str(c) for c in CUTS} for t in tones):
        out.append(f"{name}: a signal is not judged at both cuts")
    if len(rec.get("complete", [])) != 6:
        out.append(f"{name}: not six looks")
    if versions is not None:
        made = rec.get("versions")
        if made is None:            # made before records carried them: the versions its commit's code held
            made = at_commit(rec.get("provenance", {}).get("git_commit"))
        if any(made.get(key) != versions[key] for key in _needed(rec)):
            out.append(f"{name}: made by another version of the search or the checks")
        # the labels alone could stay while the code under them changed: every change since must be listed
        out += [f"{name}: {x}" for x in code(rec.get("provenance"), own=("tools/control_injection.py",))]
    return out


def lane(i, say=print):
    import check
    import store
    choice = json.loads((OUT / "choice.json").read_text(encoding="utf-8"))
    db = store.connect_readonly()
    versions = _versions_now()
    todo = [(c, int(k), v) for c in choice["cadences"] for k, v in c["blocks"].items()]
    for n, (c, k, info) in enumerate(todo):
        path = OUT / f"{c['target']}_{k:03d}.json"
        if n % LANES != i or yoke.whole(path, lambda r, c=c, k=k, info=info: not record_problems(r, c, k, info, versions)):
            continue
        ctx = {"db": db, "target": check.target_of(db, c["session"]), "hits": check.session_hits(db, c["session"])}
        rec = one_block(c, k, info, ctx)
        yoke.write(path, rec, indent=None, stamp=True)
        at = [t["at"]["30"] for t in rec["tones"]]
        say(f"{c['target']} block {k} ({info['class']}): at 30, of {len(at)} planted, {sum(a['candidate'] for a in at)} "
            f"candidates, {sum(str(a.get('verdict', '')).startswith('unexplained') for a in at)} unexplained", flush=True)
    db.close()


def run(say=print):
    import negative_controls as nc
    env = dict(os.environ, SSY_DATA=str(nc.CONTROLS), SSY_INJECTION_OUT=str(OUT))
    jobs = [subprocess.Popen([sys.executable, "-u", str(Path(__file__)), "lane", str(i)], env=env) for i in range(LANES)]
    codes = watch(jobs)
    if yoke.NETWORK_EXIT in codes:
        sys.exit(yoke.NETWORK_EXIT)


def watch(jobs, wait=5.0):
    """Every lane watched at once: a lane that fails for any reason but the network stops the others and is
    reported at once, whatever another lane is waiting for. Returns the exit codes when all have ended."""
    import time
    while True:
        codes = [p.poll() for p in jobs]
        broken = [(i, c) for i, c in enumerate(codes) if c not in (None, 0, yoke.NETWORK_EXIT)]
        if broken:
            for p in jobs:
                if p.poll() is None:
                    p.terminate()
            raise yoke.Refusal("INTERNAL_ERROR", f"lane {broken[0][0]} stopped ({broken[0][1]}); the others were stopped")
        if all(c is not None for c in codes):
            return codes
        time.sleep(wait)


def stage_counts(tones, cut, key="verdict"):
    """How many planted signals reach each stage at `cut`; those already matching a candidate of the unplanted block
    are counted apart and out of every stage. `key`: "verdict" (the checks in force) or "verdict_context" (the
    candidate version 6)."""
    at = [t["at"][str(cut)] for t in tones]
    own = [a for a in at if not a["already_in_the_block"]]
    kept = [a for a in own if a["candidate"]]
    verdicts = Counter(str(a[key]).split(" (")[0] for a in kept)
    left = sum(n for v, n in verdicts.items() if v.startswith("unexplained"))
    return {"planted": len(at), "already_in_the_block": len(at) - len(own), "counted": len(own),
            "hit_in_any_on_look": sum(a["hit_looks"] > 0 for a in own), "hit_in_all_three": sum(a["hit_looks"] == 3 for a in own),
            "candidates": len(kept), "unexplained": left, "verdicts": dict(sorted(verdicts.items())),
            "share_candidates": round(len(kept) / len(own), 4) if own else None,
            "share_unexplained": round(left / len(own), 4) if own else None,
            "unexplained_of_candidates": round(left / len(kept), 4) if kept else None}


def _block_interval(records, cut, of="counted", seed=SEED, boot=2000, key="verdict"):
    """The share left unexplained (of the counted signals, or with of="candidates" of the candidates), 95% over
    blocks drawn again with replacement."""
    counts = [stage_counts(r["tones"], cut, key) for r in records]
    pairs = np.array([[c["unexplained"], c[of]] for c in counts], float)
    if not len(pairs) or not pairs[:, 1].sum():
        return None
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(pairs), (boot, len(pairs)))
    num, den = pairs[picks, 0].sum(axis=1), pairs[picks, 1].sum(axis=1)
    # a draw with nothing to divide by has no share: it is left out, not counted as none kept
    shares = num[den > 0] / den[den > 0]
    if len(shares) < boot / 2:
        return None
    return [round(float(v), 4) for v in np.percentile(shares, [2.5, 97.5])]


def weighted(records, cut, w_capped, seed=SEED, boot=2000, key="verdict"):
    """The balanced sample reweighted to a population whose share of capped blocks is `w_capped`: each class's
    rates combined by its share, with blocks drawn again within each class. Shares of counted signals left
    unexplained, and unexplained among candidates."""
    rng = np.random.default_rng([seed, 1])
    by = {cls: np.array([[c["unexplained"], c["candidates"], c["counted"]] for c in
                         (stage_counts(r["tones"], cut, key) for r in records if r["class"] == cls)], float)
          for cls in ("complete", "capped")}
    if any(not len(x) or not x[:, 2].sum() for x in by.values()):
        return None
    w = {"complete": 1 - w_capped, "capped": w_capped}

    def est(sums):
        u = sum(w[c] * sums[c][0] / sums[c][2] for c in w)
        k = sum(w[c] * sums[c][1] / sums[c][2] for c in w)
        return u, (u / k if k else np.nan)
    point = est({c: x.sum(axis=0) for c, x in by.items()})
    draws = np.array([est({c: x[rng.integers(0, len(x), len(x))].sum(axis=0) for c, x in by.items()})
                      for _ in range(boot)])
    good = draws[~np.isnan(draws[:, 1])]
    return {"share_of_blocks_capped": round(w_capped, 4),
            "share_unexplained": [round(point[0], 4)] + [round(float(v), 4) for v in np.percentile(draws[:, 0], [2.5, 97.5])],
            "unexplained_of_candidates": [round(point[1], 4)] + [round(float(v), 4) for v in np.percentile(good[:, 1], [2.5, 97.5])]}


def summarise(records, key="verdict"):
    def part(rs, cut, keep=lambda t: True):
        return stage_counts([t for r in rs for t in r["tones"] if keep(t)], cut, key)
    def with_intervals(rs, cut):
        c = part(rs, cut)
        lo = _block_interval(rs, cut, "candidates", key=key)
        # the protocol's reading: informative where the lower end for unexplained among candidates is 0.5 or more
        return dict(c, share_unexplained_interval=_block_interval(rs, cut, key=key),
                    unexplained_of_candidates_interval=lo,
                    reading="the checks kept planted signals here" if lo and lo[0] >= 0.5 else
                    "not shown that the checks keep real signals here")
    out = {}
    for cut in CUTS:
        cell = {"all": with_intervals(records, cut)}
        for cls in ("capped", "complete"):
            cell[cls] = with_intervals([r for r in records if r["class"] == cls], cut)
        cell["by_cadence"] = {t: part([r for r in records if r["target"] == t], cut)
                              for t in dict.fromkeys(r["target"] for r in records)}
        cell["by_drift_bin"] = {str(b): part(records, cut, lambda t, b=b: t["bin"] == b)
                                for b in sorted({t["bin"] for r in records for t in r["tones"]})}
        cell["by_strength"] = {str(s): part(records, cut, lambda t, s=s: t["s_in"] == s)
                               for s in sorted({t["s_in"] for r in records for t in r["tones"]})}
        why = "reasons" if key == "verdict" else "reasons_context"
        reasons = Counter(x for r in records for t in r["tones"] for x in t["at"][str(cut)].get(why, [])
                          if not str(t["at"][str(cut)].get(key, "")).startswith("unexplained"))
        cell["what_the_checks_cited_against_kept_signals"] = dict(reasons.most_common())
        out[str(cut)] = cell
    return out


def weighted_cells(records, cut, shares, key="verdict", seed=SEED, boot=2000):
    """Beside `weighted`: the sample reweighted by cadence and class together. `shares` is each (target, class)'s
    share of the control's blocks; each cell's blocks are drawn again within the cell."""
    rng = np.random.default_rng([seed, 2])
    cells = {}
    for r in records:
        c = stage_counts(r["tones"], cut, key)
        cells.setdefault((r["target"], r["class"]), []).append([c["unexplained"], c["candidates"], c["counted"]])
    cells = {k: np.array(v, float) for k, v in cells.items()}
    if set(cells) != set(shares) or any(not x[:, 2].sum() for x in cells.values()):
        return None

    def est(sums):
        u = sum(shares[k] * s[0] / s[2] for k, s in sums.items())
        c = sum(shares[k] * s[1] / s[2] for k, s in sums.items())
        return u, (u / c if c else np.nan)
    point = est({k: x.sum(axis=0) for k, x in cells.items()})
    draws = np.array([est({k: x[rng.integers(0, len(x), len(x))].sum(axis=0) for k, x in cells.items()})
                      for _ in range(boot)])
    good = draws[~np.isnan(draws[:, 1])]
    return {"share_unexplained": [round(point[0], 4)] + [round(float(v), 4) for v in np.percentile(draws[:, 0], [2.5, 97.5])],
            "unexplained_of_candidates": [round(point[1], 4)] + [round(float(v), 4) for v in np.percentile(good[:, 1], [2.5, 97.5])],
            "note": "supplementary; four blocks a cell, so each cell's resampling is coarse"}


def choice_problems(choice, control):
    """Why the choice record is not the protocol's draw from control B ([(cadence, sweep record)])."""
    want = [{"target": c["target"], "session": c["session"], "urls": [x["url"] for x in c["looks"]],
             "blocks": {str(k): {"class": v, "range": rec["blocks"][k]} for k, v in pick_blocks(rec["done"], n, SEED).items()}}
            for n, (c, rec) in enumerate(control)]
    if choice.get("seed") != SEED or choice.get("per_class") != PER_CLASS or choice.get("cadences") != want:
        return ["the choice record is not the protocol's draw"]
    if sum(len(c["blocks"]) for c in want) != 2 * PER_CLASS * len(want):
        return ["not two classes of blocks in each cadence"]
    return []


def load_records(choice, versions):
    """Every chosen block's record, refused unless each is whole by the protocol."""
    records, problems = [], []
    for c in choice["cadences"]:
        for k, info in c["blocks"].items():
            path = OUT / f"{c['target']}_{int(k):03d}.json"
            rec = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            got = record_problems(rec, c, int(k), info, versions)
            problems += got
            if not got:
                records.append(rec)
    if problems:
        raise yoke.Refusal("INVALID_REQUEST", "; ".join(problems[:10]))
    return records


def tables(say=print):
    import negative_controls as nc
    choice = json.loads((OUT / "choice.json").read_text(encoding="utf-8"))
    control = nc._whole_control()
    problems = choice_problems(choice, control)
    if problems:
        raise yoke.Refusal("INVALID_REQUEST", problems[0])
    records = load_records(choice, _versions_now())
    capped = sum(d.get("complete") not in (1, True) for _, rec in control for d in rec["done"].values())
    blocks = sum(len(rec["done"]) for _, rec in control)
    out = {"blocks": len(records), "signals": sum(len(r["tones"]) for r in records), "cuts": summarise(records),
           "weighted_to_control_b": {"population": f"control {CONTROL.upper()}'s {blocks} blocks, {capped} of them capped",
                                     **{str(cut): weighted(records, cut, capped / blocks) for cut in CUTS}},
           "kind": "measured"}
    shares = {(c["target"], cls): sum((d.get("complete") in (1, True)) == (cls == "complete")
                                      for d in rec["done"].values()) / blocks
              for c, rec in control for cls in ("complete", "capped")}
    out["weighted_by_cadence_and_class"] = {str(cut): weighted_cells(records, cut, shares) for cut in CUTS}
    judged = [t["at"][str(c)] for r in records for t in r["tones"] for c in CUTS
              if t["at"][str(c)].get("verdict")]
    if judged and all("verdict_context" in a for a in judged):
        # the candidate version 6 of the checks (docs/control-c.md), on the same planted candidates
        out["cuts_bands_as_context"] = summarise(records, "verdict_context")
        out["weighted_bands_as_context"] = {str(cut): weighted(records, cut, capped / blocks, key="verdict_context")
                                            for cut in CUTS}
        out["weighted_by_cadence_and_class_bands_as_context"] = {
            str(cut): weighted_cells(records, cut, shares, key="verdict_context") for cut in CUTS}
    yoke.write(OUT.parent / "injection.json", out, indent=1, stamp=True)
    for cut, cell in out["cuts"].items():
        for g in ("all", "capped", "complete"):
            say(f"at {cut}, {g}: {json.dumps(cell[g])}")
    return out


def verdict_parts(verdict, reasons):
    """The checks a verdict rests on: (shown, indicated). A verdict of interference names the shown ones; the rest
    of its reasons are indicated."""
    shown = set()
    if verdict.startswith("interference (shown: "):
        shown = set(verdict[len("interference (shown: "):-1].split("; "))
    return shown, set(reasons) - shown


def without(shown, indicated, check):
    """The verdict's class with one check left out: interference, likely interference or unexplained."""
    shown, indicated = shown - {check}, indicated - {check}
    return "interference" if shown else "likely interference" if indicated else "unexplained"


def leave_one_out(planted, control, cut):
    """For each check: planted candidates that would be unexplained without it (by class of block), and control B
    candidates that would. planted: [(class, verdict, reasons)]; control: [(snr, {check: strength})]."""
    names = sorted({x for _, v, r in planted for x in r} | {x for _, s in control for x in s})
    out = {}
    for name in names:
        rescued = Counter(cls for cls, v, r in planted
                          if not v.startswith("unexplained") and without(*verdict_parts(v, r), name) == "unexplained")
        released = sum(1 for snr, s in control if snr >= cut and without(
            {x for x, g in s.items() if g == "shown"}, {x for x, g in s.items() if g == "indicated"}, name) == "unexplained")
        out[name] = {"planted_kept_without_it": {"complete": rescued["complete"], "capped": rescued["capped"]},
                     "control_b_unexplained_without_it": released}
    return out


def checks_left_out(say=print):
    """Each check left out in turn, on the planted signals' verdicts and control B's: what each costs in planted
    signals and what it removes of control B's candidates. From the records; nothing is run again."""
    import sqlite3
    import negative_controls as nc
    import vetting
    choice = json.loads((OUT / "choice.json").read_text(encoding="utf-8"))
    records = load_records(choice, _versions_now())
    db = sqlite3.connect(f"file:{(nc.CONTROLS / 'ssy.sqlite').as_posix()}?mode=ro", uri=True)
    current = {e["event_id"]: e["snr"] for e in nc.candidate_verdicts(db, vetting.VERSION, vetting.N_CHECKS)}
    strengths, bands = {}, Counter()
    for event, name, result, strength in db.execute(
            "SELECT event_id, name, result, strength FROM checks WHERE version=?", (vetting.VERSION,)):
        if event in current:
            short = name.split(". ", 1)[1]
            if strength in ("shown", "indicated"):
                strengths.setdefault(event, {})[short] = strength
            if short == "known interference bands" and current[event] >= 30 and strength:
                bands[result] += 1
    db.close()
    control = [(snr, strengths.get(e, {})) for e, snr in current.items()]
    out = {"cuts": {}, "control_b_bands_at_30": dict(bands.most_common()),
           "chosen_blocks_in_bands": {f"{c['target']} {k}": {"class": v["class"], "bands": [
               name for lo, hi, name in vetting.BANDS if lo <= max(v["range"]) and hi >= min(v["range"])]}
               for c in choice["cadences"] for k, v in c["blocks"].items()}, "kind": "measured"}
    for cut in CUTS:
        planted = [(r["class"], t["at"][str(cut)]["verdict"], t["at"][str(cut)].get("reasons", []))
                   for r in records for t in r["tones"] if t["at"][str(cut)].get("verdict")]
        out["cuts"][str(cut)] = leave_one_out(planted, control, cut)
    yoke.write(OUT.parent / "injection_checks.json", out, indent=1, stamp=True)
    for name, v in out["cuts"]["30"].items():
        say(f"without {name}: planted kept {v['planted_kept_without_it']}, control B unexplained "
            f"{v['control_b_unexplained_without_it']}")
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "choose":
        choose()
    elif cmd == "run":
        run()
    elif cmd == "lane":
        lane(int(sys.argv[2]))
    elif cmd == "tables":
        tables()
    elif cmd == "checks-left-out":
        checks_left_out()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
