"""Planted signals through the search, the cadence test and the checks, in control B's own four cadences
(docs/control-injection.md is the protocol, committed before the first block was run). Control B found no candidate
left unexplained by the checks; this measures how many real-looking signals those checks would have kept.
Supplementary: no verdict of steps 4, 10 or 12 changes, and the frozen search and checks are used as they are.

    python tools/control_injection.py choose     the blocks, by the protocol's rule (once)
    python tools/control_injection.py run        every chosen block, in three lanes (hours; resumes)
    python tools/control_injection.py tables     the survival at each stage
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

import yoke  # noqa: E402

SEED = 20261124
PER_CLASS = 4                    # blocks a cadence: this many capped and this many complete
LANES = 3
CUTS = (30, 10)
TRUE = (0, 2, 4)
OUT = Path(os.environ.get("SSY_INJECTION_OUT") or yoke.DATA / "analysis" / "negative_controls" / "injection")


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
                    verdicts[event] = {"verdict": v["verdict"], "reasons": v["reasons"]}
                at.update(verdicts[event])
            row["at"][str(cut)] = at
        for lk in looks:
            lk.flat = None
    return {"target": cadence["target"], "session": session, "block": k, "class": info["class"],
            "complete": [bool(x[2]) for x in searched], "tones": rows, "kind": "measured"}


def lane(i, say=print):
    import check
    import store
    choice = json.loads((OUT / "choice.json").read_text(encoding="utf-8"))
    db = store.connect_readonly()
    todo = [(c, int(k), v) for c in choice["cadences"] for k, v in c["blocks"].items()]
    for n, (c, k, info) in enumerate(todo):
        path = OUT / f"{c['target']}_{k:03d}.json"
        if n % LANES != i or yoke.whole(path, lambda r: len(r.get("tones", [])) > 0):
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
    codes = [p.wait() for p in jobs]
    if yoke.NETWORK_EXIT in codes:
        sys.exit(yoke.NETWORK_EXIT)
    if any(codes):
        raise yoke.Refusal("INTERNAL_ERROR", f"a lane stopped: {codes}")


def stage_counts(tones, cut):
    """How many planted signals reach each stage at `cut`; those already matching a candidate of the unplanted block
    are counted apart and out of every stage."""
    at = [t["at"][str(cut)] for t in tones]
    own = [a for a in at if not a["already_in_the_block"]]
    kept = [a for a in own if a["candidate"]]
    verdicts = Counter(str(a["verdict"]).split(" (")[0] for a in kept)
    left = sum(n for v, n in verdicts.items() if v.startswith("unexplained"))
    return {"planted": len(at), "already_in_the_block": len(at) - len(own), "counted": len(own),
            "hit_in_any_on_look": sum(a["hit_looks"] > 0 for a in own), "hit_in_all_three": sum(a["hit_looks"] == 3 for a in own),
            "candidates": len(kept), "unexplained": left, "verdicts": dict(sorted(verdicts.items())),
            "share_candidates": round(len(kept) / len(own), 4) if own else None,
            "share_unexplained": round(left / len(own), 4) if own else None,
            "unexplained_of_candidates": round(left / len(kept), 4) if kept else None}


def _block_interval(records, cut, of="counted", seed=SEED, boot=2000):
    """The share left unexplained (of the counted signals, or with of="candidates" of the candidates), 95% over
    blocks drawn again with replacement."""
    counts = [stage_counts(r["tones"], cut) for r in records]
    pairs = np.array([[c["unexplained"], c[of]] for c in counts], float)
    if not len(pairs) or not pairs[:, 1].sum():
        return None
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(pairs), (boot, len(pairs)))
    shares = pairs[picks, 0].sum(axis=1) / np.maximum(pairs[picks, 1].sum(axis=1), 1)
    return [round(float(v), 4) for v in np.percentile(shares, [2.5, 97.5])]


def summarise(records):
    def part(rs, cut, keep=lambda t: True):
        return stage_counts([t for r in rs for t in r["tones"] if keep(t)], cut)
    def with_intervals(rs, cut):
        c = part(rs, cut)
        lo = _block_interval(rs, cut, "candidates")
        # the protocol's reading: informative where the lower end for unexplained among candidates is 0.5 or more
        return dict(c, share_unexplained_interval=_block_interval(rs, cut),
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
        reasons = Counter(x for r in records for t in r["tones"] for x in t["at"][str(cut)].get("reasons", [])
                          if not str(t["at"][str(cut)].get("verdict", "")).startswith("unexplained"))
        cell["what_the_checks_cited_against_kept_signals"] = dict(reasons.most_common())
        out[str(cut)] = cell
    return out


def tables(say=print):
    choice = json.loads((OUT / "choice.json").read_text(encoding="utf-8"))
    records, missing = [], []
    for c in choice["cadences"]:
        for k in c["blocks"]:
            path = OUT / f"{c['target']}_{int(k):03d}.json"
            if yoke.whole(path, lambda r: len(r.get("tones", [])) > 0):
                records.append(json.loads(path.read_text(encoding="utf-8")))
            else:
                missing.append(f"{c['target']} {k}")
    if missing:
        raise yoke.Refusal("INVALID_REQUEST", f"Blocks not done: {missing}")
    out = {"blocks": len(records), "signals": sum(len(r["tones"]) for r in records), "cuts": summarise(records),
           "kind": "measured"}
    yoke.write(OUT.parent / "injection.json", out, indent=1, stamp=True)
    for cut, cell in out["cuts"].items():
        for g in ("all", "capped", "complete"):
            say(f"at {cut}, {g}: {json.dumps(cell[g])}")
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
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
