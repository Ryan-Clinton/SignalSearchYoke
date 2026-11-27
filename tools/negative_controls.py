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
    python tools/negative_controls.py context       the candidate version 6 of the checks beside those in force
    python tools/negative_controls.py package       the choice, sweep records, verdicts and results, with their hashes
    (any of these with --control c: control C, docs/control-c.md)
    python tools/negative_controls.py replay [DIR]  the tables and summary made again from the package alone
    python tools/negative_controls.py recheck       the checks run again from nothing on a copy of the store

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

def _which_control():
    """Control B by default; `--control c` (or SSY_CONTROL=c, which the subprocesses inherit) for control C, the
    next four sessions by the same rule (docs/control-c.md)."""
    if "--control" in sys.argv:
        i = sys.argv.index("--control")
        os.environ["SSY_CONTROL"] = sys.argv[i + 1].lower()
        del sys.argv[i:i + 2]
    return os.environ.get("SSY_CONTROL", "b")


CONTROL = _which_control()
COUNT = 4
OUT = yoke.DATA / "analysis" / ("negative_controls" if CONTROL == "b" else f"negative_controls_{CONTROL}")
CONTROLS = yoke.DATA / ("controls" if CONTROL == "b" else f"controls_{CONTROL}")   # the control's own data folder
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
    if CONTROL != "b":
        # a later control takes the next sessions by the same rule: never one an earlier control read
        before = json.loads((yoke.DATA / "analysis" / "negative_controls" / "choice.json").read_text(encoding="utf-8"))
        s12.READ_SESSIONS |= {c["session"] for c in before["chosen"]}
        s12.READ_TARGETS |= {s12._bare(c["target"]) for c in before["chosen"]}
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
            if any(c["session"] == session for c in chosen):
                # one session can be listed under several catalogue stars: each control holds a session once
                tried.append({"target": target, "session": session, "passed_over": "already chosen"})
                continue
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
    if len(chosen) != COUNT:
        raise yoke.Refusal("NOT_FOUND", f"Only {len(chosen)} of {COUNT} sessions pass the rule: no choice is written.")
    rec = {"rule": "tools/negative_controls.py, the rule in its docstring", "count_asked": COUNT,
           "catalogue": {"file": "config/isaacson2017_table1.tsv", "sha256": sha, "stars": len(names)},
           "chosen": chosen, "passed_over": tried, "replies": replies, "kind": "measured"}
    yoke.write(out, rec, indent=1, stamp=True)
    say(f"{len(chosen)} of {COUNT} chosen; {len(tried)} sessions passed over")
    return rec


def _choice():
    """The choice record, refused unless it holds exactly COUNT different sessions of COUNT different targets."""
    rec = json.loads((OUT / "choice.json").read_text(encoding="utf-8"))
    problems = choice_problems(rec["chosen"])
    if problems:
        raise yoke.Refusal("INVALID_REQUEST", problems[0])
    return rec


def sweep_problems(c, rec, version=None):
    """Why a cadence's sweep record is not the whole cadence: its blocks exactly 0 to n-1 at the record's own
    boundaries, each by one search version."""
    name, blocks, done = c["session"], rec["blocks"], rec["done"]
    if len(done) != len(blocks):
        return [f"{name}: {len(done)} of {len(blocks)} blocks"]
    if set(done) != {str(k) for k in range(len(blocks))}:
        return [f"{name}: its block numbers are not 0 to {len(blocks) - 1}"]
    out = [f"{name}: block {k} is not at its boundaries" for k, (lo, hi) in enumerate(blocks)
           if abs(done[str(k)]["from_mhz"] - lo) > 1e-6 or abs(done[str(k)]["to_mhz"] - hi) > 1e-6]
    versions = {d.get("search_version") for d in done.values()}
    if len(versions) != 1 or (version is not None and versions != {version}):
        out.append(f"{name}: not all by the search version in force")
    return out


def store_problems(db, c, rec):
    """Where the store and the sweep record disagree: the cadence's target and files, each block's place, and
    the candidates of each block."""
    name, done = c["session"], rec["done"]
    row = db.execute("SELECT target, urls FROM cadences WHERE cadence=?", (name,)).fetchone()
    if row is None:
        return [f"{name}: no such cadence in the store"]
    out = []
    if row[0] != c["target"] or json.loads(row[1]) != [x["url"] for x in c["looks"]]:
        out.append(f"{name}: the store's cadence is not the one chosen")
    held = {b: (lo, hi) for b, lo, hi in db.execute(
        "SELECT block_idx, f_lo_mhz, f_hi_mhz FROM blocks WHERE session=? AND status='done'", (name,))}
    if set(held) != {int(k) for k in done}:
        out.append(f"{name}: the store's blocks are not the record's")
    elif any(abs(held[int(k)][0] - d["from_mhz"]) > 1e-6 or abs(held[int(k)][1] - d["to_mhz"]) > 1e-6
             for k, d in done.items()):
        out.append(f"{name}: a block's boundaries differ between the store and the record")
    held = {}
    for b, event, f, drift, snr in db.execute(
            "SELECT block_idx, event_id, f_start_mhz, drift_hz_s, snr FROM events WHERE session=? AND "
            "label='candidate' AND superseded_run IS NULL", (name,)):
        held.setdefault(b, set()).add(_candidate_key(event, f, drift, snr))
    if any(held.get(int(k), set()) != {_candidate_key(e["event_id"], e["frequency_mhz"], e["drift_hz_s"], e["snr"])
                                       for e in d["events"]} for k, d in done.items()):
        out.append(f"{name}: a block's candidates differ between the store and the record")
    return out


def _candidate_key(event, f, drift, snr):
    """A candidate as compared between the store and a sweep record: its id, frequency, drift and S/N."""
    return int(event), round(float(f), 6), round(float(drift), 4), round(float(snr), 2)


def choice_problems(chosen):
    """Why a list of chosen cadences is not COUNT different sessions of COUNT different targets."""
    if len(chosen) != COUNT or len({c["session"] for c in chosen}) != COUNT or len({c["target"] for c in chosen}) != COUNT:
        return [f"the choice must hold {COUNT} different sessions of {COUNT} different targets; it holds "
                f"{len(chosen)} entries"]
    return []


def _store():
    import sqlite3
    return sqlite3.connect(f"file:{(CONTROLS / 'ssy.sqlite').as_posix()}?mode=ro", uri=True)


def _whole_control():
    """[(choice, sweep record)] of all four cadences, refused unless each is whole and agrees with the store."""
    import seti
    records, problems = [], []
    for c in _choice()["chosen"]:
        path = CONTROLS / "sweeps" / f"{c['target']}-{c['session']}.json"
        rec = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if rec is None:
            problems.append(f"{c['session']}: not swept yet")
        else:
            problems += sweep_problems(c, rec, seti.SEARCH_VERSION)
        records.append((c, rec))
    if not problems:
        db = _store()
        try:
            for c, rec in records:
                problems += store_problems(db, c, rec)
        finally:
            db.close()
    if problems:                                # a rate over part of the control is not the control's rate
        raise yoke.Refusal("INVALID_REQUEST", "The control needs every block of all four cadences: " + "; ".join(problems))
    return records


def candidate_verdicts(db, version, n_checks):
    """Every current candidate with its one whole evaluation by this version of the checks; refused if any has
    none, or more than one. Whole: exactly `n_checks` rows, each check once, one of them the final report."""
    evaluations = {}
    for event, verdict in db.execute(
            "SELECT event_id, max(CASE WHEN name='10. report' THEN result END) FROM checks WHERE version=?"
            " GROUP BY event_id, lead, checked_utc HAVING count(*) = ? AND count(DISTINCT name) = ?"
            " AND sum(name='10. report') = 1", (version, n_checks, n_checks)):
        evaluations.setdefault(event, []).append(verdict)
    events, none, many = [], 0, 0
    for event, session, block, snr, f, drift in db.execute(
            "SELECT event_id, session, block_idx, snr, f_start_mhz, drift_hz_s FROM events WHERE label='candidate' "
            "AND superseded_run IS NULL ORDER BY event_id"):
        got = evaluations.get(event, [])
        none += not got or got[0] is None
        many += len(got) > 1
        events.append({"event_id": event, "session": session, "block": block, "snr": snr, "frequency_mhz": f,
                       "drift_hz_s": drift, "verdict": got[0] if got else None})
    if none or many:
        raise yoke.Refusal("INVALID_REQUEST", f"{none} candidates have no whole evaluation by the checks in force and "
                                              f"{many} have more than one")
    return events


def sweep_one(target, session, urls):
    """One chosen cadence swept whole, in the controls' own data folder (run as its own process, whose
    SSY_DATA is that folder: the choice is passed in, not read). A cadence another lane is sweeping is waited
    for, then resumed, which finds it done."""
    import seti
    return seti.sweep(target, count=10 ** 6, files=(session, list(urls)), wait=True)


def run(say=print):
    env = dict(os.environ, SSY_DATA=str(CONTROLS))
    for c in _choice()["chosen"]:
        say(f"{c['target']} {c['session']}: sweeping")
        urls = [x["url"] for x in c["looks"]]
        r = subprocess.run([sys.executable, "-u", str(Path(__file__)), "sweep-one", c["target"], c["session"], *urls],
                           env=env)
        if r.returncode == yoke.NETWORK_EXIT:
            sys.exit(yoke.NETWORK_EXIT)
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


def _windows95(per_session, w, seed=4, boot=2000, digits=4):
    """The rate a block, 2.5 and 97.5 percentiles, drawing runs of `w` consecutive blocks with replacement within
    each session (per_session: each session's counts in frequency order), so neighbouring blocks stay together."""
    import numpy as np
    rng = np.random.default_rng([seed, w])
    total = sum(len(x) for x in per_session)
    if not total:
        return None
    draws = np.zeros(boot)
    for x in per_session:
        x, n = np.asarray(x, float), len(x)
        size = min(w, n)
        sums = np.convolve(x, np.ones(size), "valid")
        picks = sums[rng.integers(0, len(sums), (boot, int(np.ceil(n / size))))]
        draws += picks.mean(axis=1) / size * n
    ends = [float(v) for v in np.percentile(draws / total, [2.5, 97.5])]
    return ends if digits is None else [round(v, digits) for v in ends]


def table_rows(records):
    rows, total = [], {"blocks": 0, 30: 0, 10: 0}
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
    return out


def tables(say=print):
    out = table_rows(_whole_control())
    yoke.write(OUT / "tables.json", out, indent=1, stamp=True)
    for r in out["sessions"]:
        say(f"{r['target']} {r['session']}: {r['blocks']} blocks, at 30 {r['rate_30']} a block {r['interval_30']}, "
            f"at 10 {r['rate_10']} {r['interval_10']}")
    return out


def checks_here(say=print, bands_as_context=False):
    """Every current candidate through the checks as they are (with `bands_as_context`, the candidate version 6 of
    docs/control-c.md, kept under its own version beside them), in this process's store (SSY_DATA is the
    controls' folder). No reports are written: docs/leads is for the project's own sessions."""
    import check
    import store
    import vetting
    version = vetting.VERSION_BANDS_AS_CONTEXT if bands_as_context else vetting.VERSION
    db = store.connect()
    done = store.checked_events(db, version, vetting.N_CHECKS)
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
        result = check.vet_from_store(db, e, looks, session, targets[session], own, hits=hits[session],
                                      bands_as_context=bands_as_context)
        store.save_checks(db, lead, result["checks"], version, r["event_id"])
        if n % 25 == 0 or n == len(rows):
            say(f"  {n} of {len(rows)} checked")
    db.close()


def checks(say=print):
    """The checks in force on every candidate, then the candidate version 6 beside them (each resumes)."""
    for part in ("checks-here", "checks-here-context"):
        r = subprocess.run([sys.executable, "-u", str(Path(__file__)), part], env=dict(os.environ, SSY_DATA=str(CONTROLS)))
        if r.returncode == yoke.NETWORK_EXIT:
            sys.exit(yoke.NETWORK_EXIT)
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
    in_order = {}
    for b in sorted(blocks):
        in_order.setdefault(b[0], []).append(by_block.get(b, 0))
    return {"bootstrap_consecutive_blocks": {str(w): _windows95(list(in_order.values()), w) for w in (4, 16)},
            "unexplained_interval_is": "exact Poisson: a model that takes candidates as independent, which these are not",
            "blocks": n, "candidates": len(at), "rate": round(len(at) / n, 4) if n else None,
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


def summary_rows(records, events):
    blocks, sessions = {}, []
    for c, rec in records:
        here = {(c["session"], int(k)): d.get("complete") in (1, True) for k, d in rec["done"].items()}
        blocks.update(here)
        sessions.append({"target": c["target"], "session": c["session"], "band": "S" if rec["blocks"][0][0] > 1500 else "L",
                         **{f"at_{cut}": describe(events, here, cut) for cut in (30, 10)}})
    groups = {"all four": blocks}
    for band in ("L", "S"):
        names = {s["session"] for s in sessions if s["band"] == band}
        groups[f"{band} band"] = {k: v for k, v in blocks.items() if k[0] in names}
    return {"sessions": sessions,
            "groups": {g: {f"at_{cut}": describe(events, b, cut) for cut in (30, 10)} for g, b in groups.items()}}


def summary(say=print):
    import vetting
    records = _whole_control()
    db = _store()
    try:
        events = candidate_verdicts(db, vetting.VERSION, vetting.N_CHECKS)
    finally:
        db.close()
    out = dict(summary_rows(records, events), one_wrong_choice_on_the_project_sessions=_one_wrong_choice(),
               kind="measured")
    yoke.write(OUT / "summary.json", out, indent=1, stamp=True)
    sessions = out["sessions"]
    for s in sessions:
        say(f"{s['target']} ({s['band']}): {json.dumps(s['at_30'])}")
    for g, v in out["groups"].items():
        say(f"{g}: {json.dumps(v)}")
    say(json.dumps(out["one_wrong_choice_on_the_project_sessions"]))
    return out


def context(say=print):
    """The candidate version 6 of the checks (docs/control-c.md) beside the checks in force, on every candidate of
    the control: what each leaves unexplained, at 30 and 10, over all blocks and by class."""
    import vetting
    records = _whole_control()
    db = _store()
    try:
        by = {"in_force": candidate_verdicts(db, vetting.VERSION, vetting.N_CHECKS),
              "bands_as_context": candidate_verdicts(db, vetting.VERSION_BANDS_AS_CONTEXT, vetting.N_CHECKS)}
    finally:
        db.close()
    out = {"versions": {"in_force": vetting.VERSION, "bands_as_context": vetting.VERSION_BANDS_AS_CONTEXT},
           "control": CONTROL, "kind": "measured"}
    for name, events in by.items():
        out[name] = summary_rows(records, events)["groups"]
    yoke.write(OUT / "checks_context.json", out, indent=1, stamp=True)
    for name in by:
        g = out[name]["all four"]
        say(f"{name}: unexplained at 30 {g['at_30']['unexplained']} ({g['at_30']['unexplained_rate']} a block), "
            f"at 10 {g['at_10']['unexplained']}")
    return out


PACKAGE = OUT / "package"


def _sha(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(say=print):
    """The control's evidence in one folder: the choice, the sweep records, every candidate's verdict and the two
    results, with their hashes."""
    import shutil
    import seti
    import vetting
    records = _whole_control()
    db = _store()
    try:
        events = candidate_verdicts(db, vetting.VERSION, vetting.N_CHECKS)
        # control C's adoption rule reads the candidate version 6's verdicts on the real candidates: packaged
        # too, so the decision can be made again from the package alone (control_c_verdict.py --from-package)
        events6 = candidate_verdicts(db, vetting.VERSION_BANDS_AS_CONTEXT, vetting.N_CHECKS) if CONTROL == "c" else None
    finally:
        db.close()
    (PACKAGE / "sweeps").mkdir(parents=True, exist_ok=True)
    copied = [(OUT / n, PACKAGE / n) for n in ("choice.json", "tables.json", "summary.json")]
    copied += [(CONTROLS / "sweeps" / f"{c['target']}-{c['session']}.json",
                PACKAGE / "sweeps" / f"{c['target']}-{c['session']}.json") for c, _ in records]
    for a, b in copied:
        shutil.copyfile(a, b)
    (PACKAGE / "verdicts.json").write_text(json.dumps({"checks_version": vetting.VERSION, "events": events}, indent=0),
                                           encoding="utf-8")
    if events6 is not None:
        (PACKAGE / "verdicts_bands_as_context.json").write_text(
            json.dumps({"checks_version": vetting.VERSION_BANDS_AS_CONTEXT, "events": events6}, indent=0),
            encoding="utf-8")
    names = sorted(p for p in PACKAGE.rglob("*.json") if p.name != "manifest.json")
    yoke.write(PACKAGE / "manifest.json", {"search_version": seti.SEARCH_VERSION, "checks_version": vetting.VERSION,
                                           "files": {p.relative_to(PACKAGE).as_posix(): _sha(p) for p in names},
                                           "kind": "measured"}, indent=1, stamp=True)
    say(f"packaged {len(names)} files, {len(events)} verdicts")


def _unstamped(rec):
    return {k: v for k, v in rec.items() if k not in ("provenance", "kind", "one_wrong_choice_on_the_project_sessions")}


def replay(folder=None, say=print):
    """The tables and summary made again from the package alone (not the store), and compared with those it holds."""
    folder = Path(folder) if folder else PACKAGE
    load = lambda p: json.loads((folder / p).read_text(encoding="utf-8"))  # noqa: E731
    manifest = load("manifest.json")
    present = {p.relative_to(folder).as_posix() for p in folder.rglob("*.json") if p.name != "manifest.json"}
    if present != set(manifest["files"]):
        raise yoke.Refusal("INVALID_REQUEST", f"The package's files are not the manifest's: missing "
                                              f"{sorted(set(manifest['files']) - present)}, unlisted {sorted(present - set(manifest['files']))}")
    wrong = [n for n, sha in manifest["files"].items() if _sha(folder / n) != sha]
    if wrong:
        raise yoke.Refusal("INTERNAL_ERROR", f"Files differ from the manifest: {wrong}")
    chosen = load("choice.json")["chosen"]
    problems = choice_problems(chosen)
    if problems:
        raise yoke.Refusal("INVALID_REQUEST", problems[0])
    want = {"choice.json", "tables.json", "summary.json", "verdicts.json"} | {
        f"sweeps/{c['target']}-{c['session']}.json" for c in chosen}
    if CONTROL == "c":
        want.add("verdicts_bands_as_context.json")      # version 6's, for its adoption rule
    if present != want:
        raise yoke.Refusal("INVALID_REQUEST", f"The package holds {sorted(present ^ want)} it should not, or lacks them")
    verdicts = load("verdicts.json")
    if verdicts["checks_version"] != manifest["checks_version"]:
        raise yoke.Refusal("INVALID_REQUEST", "The verdicts are not by the checks the manifest names.")
    records = [(c, load(f"sweeps/{c['target']}-{c['session']}.json")) for c in chosen]
    problems = [p for c, rec in records for p in sweep_problems(c, rec, manifest["search_version"])]
    events = verdicts["events"]
    by_block = {}
    for e in events:
        by_block[(e["session"], e["block"])] = by_block.get((e["session"], e["block"]), 0) + 1
    problems += [f"{c['session']}: the verdicts and the sweep record differ" for c, rec in records
                 if any(by_block.get((c["session"], int(k)), 0) != len(d["events"]) for k, d in rec["done"].items())]
    if problems:
        raise yoke.Refusal("INVALID_REQUEST", "; ".join(problems))
    held = {}
    for e in events:
        held.setdefault((e["session"], int(e["block"])), set()).add(
            _candidate_key(e["event_id"], e["frequency_mhz"], e["drift_hz_s"], e["snr"]))
    for c, rec in records:                  # the same identity test as the live tables' against the store
        if any(held.get((c["session"], int(k)), set()) != {_candidate_key(e["event_id"], e["frequency_mhz"],
                                                                          e["drift_hz_s"], e["snr"])
                                                             for e in d["events"]} for k, d in rec["done"].items()):
            raise yoke.Refusal("INVALID_REQUEST", f"{c['session']}: the verdicts' candidates and the sweep record's differ")
    same_tables = _unstamped(table_rows(records)) == _unstamped(load("tables.json"))
    same_summary = _unstamped(summary_rows(records, events)) == _unstamped(load("summary.json"))
    if not (same_tables and same_summary):
        raise yoke.Refusal("INTERNAL_ERROR", f"The replay differs: tables {same_tables}, summary {same_summary}.")
    out = {"files_checked": len(manifest["files"]), "candidates": len(events), "tables_same": True,
           "summary_same": True,
           "not_replayed": ["one_wrong_choice_on_the_project_sessions: made from the project sessions' block "
                            "records, which are not in this package"],
           "is": "made again from the package on this computer by this code; not an independent verification",
           "kind": "measured"}
    if folder == PACKAGE:
        yoke.write(OUT / "package_replay.json", out, indent=1, stamp=True)
    say(f"replayed: tables and summary identical, {len(events)} verdicts")
    return out


def recheck(say=print):
    """The checks run again from nothing on a copy of the store: every candidate's verdict must come out the same."""
    import shutil
    import sqlite3
    import vetting
    work = yoke.DATA / "controls-recheck"
    if work.exists():
        yoke.remove_tree(work)
    work.mkdir()
    shutil.copyfile(CONTROLS / "ssy.sqlite", work / "ssy.sqlite")
    db = sqlite3.connect(work / "ssy.sqlite")
    with db:
        db.execute("DELETE FROM checks")
    db.close()
    r = subprocess.run([sys.executable, "-u", str(Path(__file__)), "checks-here"], env=dict(os.environ, SSY_DATA=str(work)))
    if r.returncode:
        raise yoke.Refusal("INTERNAL_ERROR", f"the checks stopped ({r.returncode})")
    db = sqlite3.connect(f"file:{(work / 'ssy.sqlite').as_posix()}?mode=ro", uri=True)
    again = {e["event_id"]: e["verdict"] for e in candidate_verdicts(db, vetting.VERSION, vetting.N_CHECKS)}
    db.close()
    first = {e["event_id"]: e["verdict"] for e in
             json.loads((PACKAGE / "verdicts.json").read_text(encoding="utf-8"))["events"]}
    differ = sorted(k for k in set(first) | set(again) if first.get(k) != again.get(k))
    yoke.write(OUT / "package_recheck.json", {"candidates": len(first), "verdicts_differing": len(differ),
                                              "first_differing": differ[:20], "kind": "measured"}, indent=1, stamp=True)
    yoke.remove_tree(work)
    say(f"checks run again: {len(first)} candidates, {len(differ)} verdicts differ")
    if differ:
        raise yoke.Refusal("INTERNAL_ERROR", f"{len(differ)} verdicts differ")


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
    elif cmd == "checks-here-context":
        checks_here(bands_as_context=True)
    elif cmd == "summary":
        summary()
    elif cmd == "context":
        context()
    elif cmd == "package":
        package()
    elif cmd == "replay":
        replay(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "recheck":
        recheck()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
