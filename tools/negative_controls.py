"""Control B (docs/audits.md 4): real cadences of other targets, in their own
time order, searched and judged by the frozen search and cadence test as
published. No candidate in them is taken to be a signal, so their yield is
a false-alarm rate measured on cadences as they are observed, which the 19
wrong ON/OFF choices only stand in for. Supplementary: no verdict of steps
4, 10 or 12 changes.

    python tools/negative_controls.py select        choose the sessions (archive listing and headers only)
    python tools/negative_controls.py run           sweep each chosen cadence whole (hours; resumes)
    python tools/negative_controls.py tables        the rates from the swept cadences
    python tools/negative_controls.py checks        the checks on every candidate, in the controls' own store (resumes)
    python tools/negative_controls.py summary       after the checks; where the candidates fall; beside one wrong choice

The rule, fixed before any of its listings were read (20 November 2026):

1. Targets in the order of Breakthrough Listen's target list (Isaacson et
   al. 2017, config/isaacson2017_table1.tsv, its hash recorded), each asked
   of the archive by name; every reply kept with its SHA-256.
2. Green Bank sessions only, in the listing's order; for each, the first run
   of six looks ON, OFF, ON, OFF, ON, OFF of the finest product with one
   set-up (tools/step12_select.structural); never a session or ON target
   this project has read (step12_select.READ_SESSIONS, READ_TARGETS and
   the sessions of steps 4, 10 and 12).
3. The first ON file's header only (no spectra): the layout the frozen
   search was validated on: 16 spectra of 18.25 s and 2.79 or 2.84 Hz
   channels (each to 1%), and at least 61 blocks.
4. The first FOUR sessions that pass, one a target.

Run: each cadence swept whole by the search as it is (seti.sweep), in a
store of its own (data/controls/), so their hits never enter the main
store's checks. Primary measure, fixed now: cadence candidates (before the
checks) with SNR at least 30, the frozen cut, a block, by session with its
exact Poisson 95% interval and a bootstrap over its blocks (clustered
interference breaks the count model, so both are given), and over the four. Secondary: the same at 10;
after the checks, the unexplained only; beside each, the rate one wrong
ON/OFF choice gives on the three sessions (docs/audits.md F4-01).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import yoke  # noqa: E402

COUNT = 4
OUT = yoke.DATA / "analysis" / "negative_controls"
CONTROLS = yoke.DATA / "controls"           # the controls' own data folder (their store, sweeps, indexes)
PROJECT_SESSIONS = {"AGBT17A_999_68", "AGBT16A_999_192", "AGBT19B_999_104"}
PROJECT_TARGETS = {"KIC8462852", "HIP17147", "NGC6946"}
WIDTHS_HZ = (2.7939677238464355, 2.84)
TSAMP = 18.253611008
N_T = 16


def _layout(geo):
    """Why the header is not the validated layout, or None."""
    width = abs(geo["foff"]) * 1e6
    if not any(abs(width - w) <= 0.01 * w for w in WIDTHS_HZ):
        return f"channels of {width:.3f} Hz"
    if abs(geo["tsamp"] - TSAMP) > 0.01 * TSAMP:
        return f"spectra of {geo['tsamp']:.2f} s"
    if geo["n_t"] != N_T:
        return f"{geo['n_t']} spectra"
    return None


def select(say=print):
    import step12_select as s12
    out = OUT / "choice.json"
    if out.exists():
        raise yoke.Refusal("INVALID_REQUEST", f"{out} exists: the choice is made once")
    s12.OUT = OUT / "replies"
    s12.READ_SESSIONS = set(s12.READ_SESSIONS) | PROJECT_SESSIONS
    s12.READ_TARGETS = set(s12.READ_TARGETS) | PROJECT_TARGETS
    names, sha = s12.catalogue_targets()
    replies, tried, chosen = [], [], []
    for target in names:
        if len(chosen) == COUNT:
            break
        if s12._bare(target) in s12.READ_TARGETS or any(c["target"] == target for c in chosen):
            continue
        rows = s12._query(replies, target=target) or []
        gbt = [r for r in rows if s12._is_gbt(r.get("telescope"))]
        for session, rs in s12._sessions(gbt).items():
            run, why = s12.structural(session, rs, replies, True)
            if run is None:
                tried.append({"target": target, "session": session, "passed_over": why})
                continue
            geo, why = s12.header(run["looks"][0]["url"])
            why = why or (_layout(geo) if geo else "no header")
            if why:
                tried.append({"target": target, "session": session, "passed_over": why, "header": geo})
                continue
            chosen.append({"target": target, **run, "header": geo})
            say(f"chosen {len(chosen)}: {target} {session}")
            break
    rec = {"rule": "tools/negative_controls.py, the rule in its docstring", "count_asked": COUNT,
           "catalogue": {"file": "config/isaacson2017_table1.tsv", "sha256": sha, "stars": len(names)},
           "chosen": chosen, "passed_over": tried, "replies": replies, "kind": "measured"}
    yoke.write(out, rec, indent=1, stamp=True)
    say(f"{len(chosen)} of {COUNT} chosen; {len(tried)} sessions passed over")
    return rec


def _choice():
    return json.loads((OUT / "choice.json").read_text(encoding="utf-8"))


def sweep_one(target, session, urls):
    """One chosen cadence swept whole, in the controls' own data folder (run as its own process, whose
    SSY_DATA is that folder: the choice is passed in, not read)."""
    import seti
    return seti.sweep(target, count=10 ** 6, files=(session, list(urls)))


def run(say=print):
    env = dict(os.environ, SSY_DATA=str(CONTROLS))
    for c in _choice()["chosen"]:
        say(f"{c['target']} {c['session']}: sweeping")
        urls = [x["url"] for x in c["looks"]]
        r = subprocess.run([sys.executable, "-u", str(Path(__file__)), "sweep-one", c["target"], c["session"], *urls],
                           env=env)
        if r.returncode:
            raise yoke.Refusal("INTERNAL_ERROR", f"{c['session']}: the sweep stopped ({r.returncode})")


def _poisson95(n, exposure):
    """The exact (Garwood) 95% interval of a Poisson rate, n events over exposure (normal beyond 200)."""
    import measure
    lo, hi = measure.poisson_interval(n) if n <= 200 else (n - 1.96 * n ** 0.5, n + 1.96 * n ** 0.5)
    return [round(lo / exposure, 4), round(hi / exposure, 4)]


def _bootstrap95(per_block, seed=4, boot=2000):
    """The rate a block, its 2.5 and 97.5 percentiles over blocks drawn again with replacement."""
    import numpy as np
    x = np.asarray(per_block, float)
    if not len(x):
        return None
    rng = np.random.default_rng(seed)
    means = [rng.choice(x, len(x)).mean() for _ in range(boot)]
    return [round(float(v), 4) for v in np.percentile(means, [2.5, 97.5])]


def tables(say=print):
    rows, total = [], {"blocks": 0, 30: 0, 10: 0}
    records, short = [], []
    for c in _choice()["chosen"]:
        rec_path = CONTROLS / "sweeps" / f"{c['target']}-{c['session']}.json"
        rec = json.loads(rec_path.read_text(encoding="utf-8")) if rec_path.exists() else None
        if rec is None:
            short.append(f"{c['session']}: not swept yet")
        elif len(rec["done"]) != len(rec["blocks"]):
            short.append(f"{c['session']}: {len(rec['done'])} of {len(rec['blocks'])} blocks")
        records.append((c, rec))
    if short:                                   # a rate over part of the control is not the control's rate
        raise yoke.Refusal("INVALID_REQUEST", "The tables need every block of all four cadences: " + "; ".join(short))
    for c, rec in records:
        done = rec["done"]
        n = len(done)
        row = {"target": c["target"], "session": c["session"], "blocks": n,
               "complete_blocks": sum(1 for d in done.values() if d.get("complete") in (1, True))}
        for cut in (30, 10):
            per_block = [sum(1 for e in d["events"] if e["snr"] >= cut) for d in done.values()]
            k = sum(per_block)
            row[f"candidates_{cut}"] = k
            row[f"rate_{cut}"] = round(k / n, 4) if n else None
            row[f"interval_{cut}"] = _poisson95(k, n) if n else None
            row[f"bootstrap_{cut}"] = _bootstrap95(per_block)
            total[cut] += k
        total["blocks"] += n
        rows.append(row)
    out = {"sessions": rows, "kind": "measured",
           "over_all": {"blocks": total["blocks"],
                        **{f"rate_{c}": round(total[c] / total["blocks"], 4) if total["blocks"] else None
                           for c in (30, 10)},
                        **{f"interval_{c}": _poisson95(total[c], total["blocks"]) if total["blocks"] else None
                           for c in (30, 10)}}}
    yoke.write(OUT / "tables.json", out, indent=1, stamp=True)
    for r in rows:
        say(f"{r['target']} {r['session']}: {r['blocks']} blocks, at 30 {r['rate_30']} a block {r['interval_30']}, "
            f"at 10 {r['rate_10']} {r['interval_10']}")
    return out


def checks_here(say=print):
    """Every current candidate through the checks as they are, kept in this process's store (SSY_DATA is the
    controls' folder). No reports are written: docs/leads is for the project's own sessions."""
    import check
    import store
    import vetting
    db = store.connect()
    done = store.checked_events(db, vetting.VERSION, vetting.N_CHECKS)
    rows = [r for r in db.execute("SELECT * FROM events WHERE label='candidate' AND superseded_run IS NULL"
                                  " ORDER BY session, block_idx, event_id").fetchall() if r["event_id"] not in done]
    say(f"{len(done)} checked already, {len(rows)} to check")
    hits, targets, at = {}, {}, None
    for n, r in enumerate(rows, 1):
        session = r["session"]
        if session not in hits:
            hits, targets = {session: check.session_hits(db, session)}, {session: check.target_of(db, session)}
        if at != (session, r["block_idx"]):
            at, (looks, where, _) = (session, r["block_idx"]), check._cadence(db, session, r["block_idx"])
        e = check._event(db, r, where)
        own = {x[0] for x in db.execute("SELECT hit_id FROM event_hits WHERE event_id=?", (r["event_id"],))}
        lead = f"{check.lead_id(targets[session]['name'], session, e['frequency_mhz'])}-e{r['event_id']}"
        result = check.vet_from_store(db, e, looks, session, targets[session], own, hits=hits[session])
        store.save_checks(db, lead, result["checks"], vetting.VERSION, r["event_id"])
        if n % 25 == 0 or n == len(rows):
            say(f"  {n} of {len(rows)} checked")
    db.close()


def checks(say=print):
    r = subprocess.run([sys.executable, "-u", str(Path(__file__)), "checks-here"], env=dict(os.environ, SSY_DATA=str(CONTROLS)))
    if r.returncode:
        raise yoke.Refusal("INTERNAL_ERROR", f"the checks stopped ({r.returncode})")


def verdict_class(verdict):
    for name in ("interference", "likely interference", "unexplained, strong", "unexplained, weak"):
        if verdict == name or verdict.startswith(name + " "):
            return name
    raise yoke.Refusal("INTERNAL_ERROR", f"a verdict not known here: {verdict!r}")


def describe(events, blocks, cut):
    """Candidates at `cut` over `blocks` ({(session, block): complete}): `events` are dicts of session, block, snr
    and verdict. How many, what the checks call them, how bunched they are, and in which blocks."""
    from collections import Counter
    at = [e for e in events if e["snr"] >= cut and (e["session"], e["block"]) in blocks]
    n, classes = len(blocks), Counter(verdict_class(e["verdict"]) for e in at)
    by_block = Counter((e["session"], e["block"]) for e in at)
    top = [v for _, v in by_block.most_common()]
    whole = sum(1 for c in blocks.values() if c)
    in_whole = sum(1 for e in at if blocks[(e["session"], e["block"])])
    unexplained = classes["unexplained, strong"] + classes["unexplained, weak"]
    per_block = [by_block.get(b, 0) for b in blocks]
    return {"blocks": n, "candidates": len(at), "rate": round(len(at) / n, 4) if n else None,
            "by_verdict": {k: classes[k] for k in ("interference", "likely interference", "unexplained, strong",
                                                  "unexplained, weak")},
            "unexplained": unexplained, "unexplained_rate": round(unexplained / n, 4) if n else None,
            "unexplained_interval": _poisson95(unexplained, n) if n else None,
            "unexplained_bootstrap": _bootstrap95([sum(1 for e in at if (e["session"], e["block"]) == b and
                                                       verdict_class(e["verdict"]).startswith("unexplained"))
                                                   for b in blocks]) if unexplained else [0.0, 0.0],
            "bootstrap": _bootstrap95(per_block),
            "blocks_with_any": len(by_block), "in_the_busiest_block": top[0] if top else 0,
            "in_the_three_busiest_blocks": sum(top[:3]),
            "blocks_complete": whole, "candidates_in_complete_blocks": in_whole,
            "blocks_capped": n - whole, "candidates_in_capped_blocks": len(at) - in_whole}


def _one_wrong_choice():
    """Beside the control: distinct candidates a block of one wrong choice on the three project sessions, this
    search, each class weighted by its share of the session as the published rates are (F4-01's are as sampled)."""
    import false_checks
    import matched
    import numpy as np
    out = {}
    for target, year in false_checks.SESSIONS:
        _, recs, weights = false_checks._session(target)
        out[year] = {"target": target}
        for cut in (30, 10):
            mean = {}
            for cls in weights:
                per = [x for r in recs if r["class"] == cls
                       for x in false_checks.assignment_stats(r["ours"]["false"].get(matched.ck(cut), {}))[0]]
                mean[cls] = float(np.mean(per)) if per else 0.0
            out[year][f"rate_{cut}"] = round(sum(weights[c] * mean[c] for c in weights), 4)
    return out


def summary(say=print):
    import sqlite3
    db = sqlite3.connect(f"file:{(CONTROLS / 'ssy.sqlite').as_posix()}?mode=ro", uri=True)
    events = [{"session": s, "block": b, "snr": snr, "verdict": v, "frequency_mhz": f} for s, b, snr, f, v in db.execute(
        "SELECT e.session, e.block_idx, e.snr, e.f_start_mhz, c.result FROM events e LEFT JOIN checks c ON"
        " c.event_id=e.event_id AND c.name='10. report' WHERE e.label='candidate' AND e.superseded_run IS NULL")]
    db.close()
    missing = sum(1 for e in events if e["verdict"] is None)
    if missing:
        raise yoke.Refusal("INVALID_REQUEST", f"{missing} candidates have not been through the checks")
    blocks, sessions = {}, []
    for c in _choice()["chosen"]:
        rec = json.loads((CONTROLS / "sweeps" / f"{c['target']}-{c['session']}.json").read_text(encoding="utf-8"))
        if len(rec["done"]) != len(rec["blocks"]):
            raise yoke.Refusal("INVALID_REQUEST", f"{c['session']} is not swept whole")
        here = {(c["session"], int(k)): d.get("complete") in (1, True) for k, d in rec["done"].items()}
        blocks.update(here)
        sessions.append({"target": c["target"], "session": c["session"], "band": "S" if rec["blocks"][0][0] > 1500 else "L",
                         **{f"at_{cut}": describe(events, here, cut) for cut in (30, 10)}})
    groups = {"all four": blocks}
    for band in ("L", "S"):
        names = {s["session"] for s in sessions if s["band"] == band}
        groups[f"{band} band"] = {k: v for k, v in blocks.items() if k[0] in names}
    out = {"sessions": sessions,
           "groups": {g: {f"at_{cut}": describe(events, b, cut) for cut in (30, 10)} for g, b in groups.items()},
           "one_wrong_choice_on_the_project_sessions": _one_wrong_choice(), "kind": "measured"}
    yoke.write(OUT / "summary.json", out, indent=1, stamp=True)
    for s in sessions:
        say(f"{s['target']} ({s['band']}): {json.dumps(s['at_30'])}")
    for g, v in out["groups"].items():
        say(f"{g}: {json.dumps(v)}")
    say(json.dumps(out["one_wrong_choice_on_the_project_sessions"]))
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "select":
        select()
    elif cmd == "run":
        run()
    elif cmd == "sweep-one":
        sweep_one(sys.argv[2], sys.argv[3], sys.argv[4:10])
    elif cmd == "tables":
        tables()
    elif cmd == "checks":
        checks()
    elif cmd == "checks-here":
        checks_here()
    elif cmd == "summary":
        summary()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
