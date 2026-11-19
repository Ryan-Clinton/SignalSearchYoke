"""Step 10 (comparable.md): step 4's matched comparison, and the curved
second pass with it, on another session, with every choice fixed before any
of its data is read.

The choices are in config/step10.json, committed before the sweep starts:
the session and its six files, the block rule and its seed, the measurement
(matched.block unchanged, the curved pass unchanged), the cut (SNR 30 for
both pipelines), the rate (0.1 false candidates a block) and what counts as
the result holding. The config also holds a fingerprint of the code that
makes the measurement: whole files for the search, the cadence test and the
measurement, and the functions used from seti.py and curved_pass.py. Every
stage refuses to run if the config has uncommitted changes or any
fingerprint differs, unless it is given --deviation "why", which is logged
(data/step10/deviations.json) and printed in the verdict. Nothing chooses a
cut on the new session: the curves are measured and shown, not used.

Stages, each resumable:

    python independent.py check                 the config and the code as frozen (reads no data)
    python independent.py sweep [--blocks N]    the whole session, by seti.py sweep (into the store)
    python independent.py choose                the block rule, on the swept blocks' hit counts
    python independent.py measure [--shard i/n] matched.py's measurement on the chosen blocks
    python independent.py curved [--shard i/n]  the curved second pass on the same blocks
    python independent.py verdict [--progress]  the criteria, the page and the record: refused unless
                                                every chosen block's records are whole (--progress: how
                                                far the runs are, and no verdict)

    python independent.py freeze                write the code fingerprints into the config (before the
                                                first stage only; then commit it)

The sweep adds the session's hits to the store, so check 6 (recurrence) of
every other session's candidates sees its looks from then on; the store's
sessions are recorded with the verdict.
"""
import argparse
import hashlib
import inspect
import json
import subprocess
import sys
import time

import numpy as np

import curved_pass
import matched
import matched_tables
import measure
import seti
import store
import yoke

STEP = 10
CONFIG = yoke.ROOT / "config" / "step10.json"
ROOT = yoke.DATA / "step10"
KEEP = ("selection", "catalogue")       # a step's own folders written before its freeze (step 12's choice)


def set_step(n):
    """Run another step's config: config/stepN.json, data/stepN/ (step 12 takes step 10's code)."""
    global STEP, CONFIG, ROOT
    STEP, CONFIG, ROOT = int(n), yoke.ROOT / "config" / f"step{int(n)}.json", yoke.DATA / f"step{int(n)}"

# The code the measurement and the verdict rest on. Whole files: this one,
# and every project module the measurement imports (the import closure of
# matched, curved_pass, seti and this file), and the tools it runs. seti.py
# and curved_pass.py also hold other work, so from them the functions below
# and everything they reach in their own module (functions, classes and
# constants, followed through every name their code uses) are fingerprinted.
FILES = ("independent.py", "searching.py", "onoff.py", "reading.py", "store.py", "injection.py", "measure.py",
         "matched.py", "matched_tables.py", "pipelines.py", "instrument.py", "vetting.py", "occupancy.py",
         "check.py", "ranking.py", "report.py", "curved.py", "yoke.py",
         "tools/turbo_curves.py", "tools/pickles_choices.py")
FUNCTIONS = {
    "seti": ("find", "folder", "_session", "_scan", "query", "_bare", "channels", "blank_dc", "read_looks",
             "read_slice", "search", "at_cut", "describe", "look", "cadence", "blocks", "search_params",
             "_cadence_files", "_same_event", "export", "sweep"),
    "curved_pass": ("key", "second_pass", "_kept_pass", "judge_all", "tones", "plant", "expected", "_matches",
                    "status", "statuses", "block", "run", "tables"),
}
MODULES = {"seti": seti, "curved_pass": curved_pass}
PLAIN = (str, int, float, bool, type(None), tuple, list, dict, frozenset, set)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def _stable(v):
    """A constant as text that is the same every run (a function by its source, not its address)."""
    if isinstance(v, (tuple, list)):
        return "(" + ", ".join(_stable(x) for x in v) + ")"
    if callable(v):
        return inspect.getsource(v).strip().replace("\r\n", "\n")
    return repr(v)


def _names(code):
    """Every name a code object and the code nested in it use."""
    out = set(code.co_names)
    for c in code.co_consts:
        if inspect.iscode(c):
            out |= _names(c)
    return out


def _codes(obj):
    if inspect.isfunction(obj):
        return [obj.__code__]
    if inspect.isclass(obj):
        return [v.__code__ for v in vars(obj).values() if inspect.isfunction(v)]
    return []


def reachable(module, entries):
    """{name: text}: the entry functions and every function, class and plain
    constant of the same module their code reaches, followed through."""
    out, todo = {}, list(entries)
    while todo:
        n = todo.pop()
        if n in out or n.startswith("__") or not hasattr(module, n):
            continue
        v = getattr(module, n)
        if inspect.ismodule(v):
            continue
        if inspect.isfunction(v) or inspect.isclass(v):
            if v.__module__ != module.__name__:
                continue    # from another module: those are fingerprinted whole
            out[n] = inspect.getsource(v).replace("\r\n", "\n")
            for c in _codes(v):
                todo += sorted(_names(c))
        elif isinstance(v, PLAIN):
            out[n] = _stable(v)
            for x in (v if isinstance(v, (tuple, list)) else ()):
                if inspect.isfunction(x):     # a table of functions (curved_pass.WAYS)
                    todo += sorted(_names(x.__code__))
    return out


def fingerprint():
    """{item: sha256} of the code the measurement and the verdict rest on."""
    out = {}
    for f in FILES:
        # line endings normalised, so a checkout on another system gives the same print
        out[f] = _sha((yoke.ROOT / f).read_bytes().replace(b"\r\n", b"\n"))
    for mod, names in FUNCTIONS.items():
        for n, text in reachable(MODULES[mod], names).items():
            out[f"{mod}.{n}"] = _sha(text)
    return out


def load():
    raw = CONFIG.read_bytes()
    return json.loads(raw), _sha(raw.replace(b"\r\n", b"\n"))


def _git(*args):
    return subprocess.run(["git", "-C", str(yoke.ROOT), *args], capture_output=True, text=True).stdout.strip()


def frozen(cfg, deviation=None, stage=""):
    """Refuse unless the config is committed as it stands and the code is as
    fingerprinted; a deviation is logged and allowed."""
    rel = CONFIG.relative_to(yoke.ROOT).as_posix()
    problems = []
    if not _git("ls-files", rel):
        problems.append(f"{rel} is not committed")
    elif _git("status", "--porcelain", "--", rel):
        problems.append(f"{rel} has uncommitted changes")
    if not cfg.get("code"):
        problems.append("the config holds no code fingerprint (independent.py freeze)")
    else:
        now = fingerprint()
        changed = sorted(k for k in set(now) | set(cfg["code"]) if now.get(k) != cfg["code"].get(k))
        if changed:
            problems.append("changed since the freeze: " + ", ".join(changed))
    if problems and not deviation:
        raise yoke.Refusal("INVALID_REQUEST", f"Step {STEP} is frozen: " + "; ".join(problems)
                           + ". Put it back, or run with --deviation \"why\" (logged and reported).")
    if problems:
        ROOT.mkdir(parents=True, exist_ok=True)
        log = ROOT / "deviations.json"
        items = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
        items.append({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stage": stage,
                      "problems": problems, "why": deviation, "git_commit": _git("rev-parse", "HEAD")})
        log.write_text(json.dumps(items, indent=1), encoding="utf-8")
    return {"config_commit": _git("log", "-1", "--format=%H %cI", "--", rel), "problems": problems}


def _files(cfg, db):
    """The session's six files: the store's once swept, checked against the config."""
    kept = store.cadence_files(db, cfg["target"])
    if kept and (kept[0] != cfg["session"] or list(kept[1]) != cfg["files"]):
        raise yoke.Refusal("INVALID_REQUEST", f"The store's cadence of {cfg['target']} is not the frozen one.")
    return kept


def check(cfg, say=print):
    info = frozen(cfg, stage="check")
    say(f"config {CONFIG.name}: committed at {info['config_commit']}; the code is as frozen "
        f"({len(cfg['code'])} items)")
    return info


def sweep(cfg, count=None, deviation=None, say=print):
    frozen(cfg, deviation, "sweep")
    db = store.connect()
    kept = _files(cfg, db)
    db.close()
    files = None
    if not kept and cfg.get("files_from_config"):
        # The cadence is six files of one recording node, which seti.find does not list as one cadence
        # (it reads the session's nodes together): the sweep is given the frozen files.
        files = (cfg["session"], list(cfg["files"]))
    elif not kept:
        # Before its first block: the archive's first whole cadence of the target must be the frozen one,
        # since seti.sweep takes that.
        found = seti.find(cfg["target"], say=lambda *_: None)
        first = next((s for s in found["sessions"] if s["complete"]), None)
        pattern = "".join("A" if sc["on"] else "B" for sc in first["scans"]) if first else ""
        urls = [sc["url"] for sc in first["scans"][pattern.index("ABABAB"):][:6]] if first else []
        if not first or first["session"] != cfg["session"] or urls != cfg["files"]:
            raise yoke.Refusal("INVALID_REQUEST", "The archive's first whole cadence of "
                               f"{cfg['target']} is not the frozen session and files.")
    n = cfg["blocks"]["of_session"]
    return seti.sweep(cfg["target"], count=n if count is None else count, say=say, files=files)


def choose(cfg, deviation=None, say=print):
    """The frozen block rule on the swept blocks' hit counts (the same count
    as step 4's: hits at the sweep's cut, six looks together)."""
    frozen(cfg, deviation, "choose")
    rule = cfg["blocks"]
    db = store.connect()
    session, urls = _files(cfg, db) or (None, None)
    if session is None:
        raise yoke.Refusal("NOT_FOUND", "The session is not swept yet (independent.py sweep).")
    rows = list(store.done_blocks(db, session).values())  # search_version is the run's, not the block's
    db.close()
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    if len(rows) != len(block_list) or rule["of_session"] != len(block_list):
        raise yoke.Refusal("INVALID_REQUEST", f"{len(rows)} of {len(block_list)} blocks swept: the rule needs all "
                           f"(the config expects {rule['of_session']}).")
    stale = [r["block_idx"] for r in rows if r["search_version"] != cfg["sweep"]["search_version"]]
    if stale:
        raise yoke.Refusal("INVALID_REQUEST", f"blocks {stale[:5]}... swept by another search version.")
    crowded = [int(r["block_idx"]) for r in rows if r["hits"] > rule["crowded_hits"]]
    clean = [int(r["block_idx"]) for r in rows if r["hits"] <= rule["crowded_hits"]]
    rng = np.random.default_rng(rule["seed"])
    if len(rows) <= rule["total"]:
        # A session of no more blocks than the sample: every block (comparable.md step 12).
        pick_crowded, pick_clean = sorted(crowded), sorted(clean)
    else:
        pick_crowded = sorted(int(b) for b in rng.choice(crowded, size=min(rule["crowded_max"], len(crowded)),
                                                         replace=False)) if crowded else []
        n_clean = min(rule["total"] - len(pick_crowded), len(clean))
        pick_clean = sorted(int(b) for b in rng.choice(clean, size=n_clean, replace=False)) if clean else []
        short = rule["total"] - len(pick_crowded) - len(pick_clean)
        rest = sorted(set(crowded) - set(pick_crowded))
        if short > 0 and rest:
            # Too few clean blocks: more crowded ones at random to make the total (step 12's rule; drawn
            # after the others, so step 10's choice, which never came here, is unchanged).
            pick_crowded = sorted(pick_crowded + [int(b) for b in rng.choice(rest, size=min(short, len(rest)),
                                                                             replace=False)])
    chosen = dict(sorted(({b: "crowded" for b in pick_crowded} | {b: "clean" for b in pick_clean}).items()))
    choice = {"chosen": chosen, "of": {"crowded": len(crowded), "clean": len(clean)},
              "crowded_hits": rule["crowded_hits"], "rule": rule, "config_sha256": load()[1]}
    ROOT.mkdir(parents=True, exist_ok=True)
    out = ROOT / "choice.json"
    if out.exists() and json.loads(out.read_text(encoding="utf-8"))["chosen"] != json.loads(json.dumps(chosen)):
        raise yoke.Refusal("INVALID_REQUEST", f"{out} holds another choice.")
    out.write_text(json.dumps(choice, indent=1), encoding="utf-8")
    say(f"{cfg['target']} {session}: {len(crowded)} crowded and {len(clean)} clean of {len(rows)}; chosen "
        f"{len(pick_crowded)} crowded and {len(pick_clean)} clean")
    return choice


def _choice():
    p = ROOT / "choice.json"
    if not p.exists():
        raise yoke.Refusal("NOT_FOUND", "No blocks chosen yet (independent.py choose).")
    return json.loads(p.read_text(encoding="utf-8"))


def measure_blocks(cfg, shard=(0, 1), count=None, deviation=None, say=print):
    frozen(cfg, deviation, "measure")
    choice = _choice()
    if choice["config_sha256"] != load()[1] and not deviation:
        raise yoke.Refusal("INVALID_REQUEST", "The blocks were chosen under another config.")
    return matched.run(cfg["target"], count, say=say, choice={k: choice[k] for k in ("chosen", "of", "crowded_hits")},
                       shard=shard)


def curved(cfg, shard=(0, 1), count=None, deviation=None, say=print):
    frozen(cfg, deviation, "curved")
    return curved_pass.run(cfg["target"], count=count, say=say, shard=shard)


# --- the verdict -----------------------------------------------------------------

def _rate_verdict(rate, limit):
    if rate["per_block"] > limit:
        return "fails"
    return "holds" if rate["interval"][1] <= limit else "holds, its interval reaching above the limit"


def _apart(a, b):
    """a above b with the two intervals apart."""
    if a["interval"][0] > b["interval"][1]:
        return "holds"
    return "fails" if a["share"] <= b["share"] else "not shown: the intervals overlap"


def _share(k, n):
    return {"recovered": k, "of": n, "share": round(k / n, 4) if n else None,
            "interval": measure.wilson(k, n) if n else None}


def _session_tstarts(db, session):
    return [r[0] for r in db.execute("SELECT tstart_mjd FROM files WHERE session=? AND cadence_position IS NOT NULL"
                                     " ORDER BY cadence_position", (session,))]


def _records(base):
    """Every block record in a folder, by block, unreadable ones as None."""
    out = {}
    for p in sorted(base.glob("block_*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            out[int(r["block"])] = r
        except (ValueError, KeyError):
            out[p.stem] = None
    return out


def completeness(cfg, choice, recs, crecs, tstarts):
    """What stops a verdict: each chosen block needs a whole record of each
    run, of this session's looks, with the frozen number of signals and every
    field the criteria read; no other block may be there."""
    exp = cfg["expected"]
    cut = matched.ck(cfg["criteria"]["cut"])
    pass_key = curved_pass.key(cfg["criteria"]["curved_pass"]["a_max"])
    chosen = {int(b): c for b, c in choice["chosen"].items()}
    problems = []
    if len(chosen) != exp["blocks"]:
        problems.append(f"{len(chosen)} blocks chosen, {exp['blocks']} expected")

    def same_looks(r):
        return len(r.get("tstarts", [])) == 6 and all(abs(a - b) < 1e-6 for a, b in zip(r["tstarts"], tstarts))

    for name, got, fmt, n_tones in (("measure", recs, matched.FORMAT, exp["tones_per_block"]),
                                    ("curved", crecs, curved_pass.FORMAT, exp["curved_tones_per_block"])):
        bad = []
        for b in sorted(set(chosen) - set(got)):
            bad.append(f"block {b} missing")
        for b in sorted(set(got) - set(chosen), key=str):
            bad.append(f"block {b} not chosen")
        for b in sorted(set(got) & set(chosen)):
            r = got[b]
            why = None
            if r is None:
                why = "unreadable"
            elif r.get("format") != fmt:
                why = f"format {r.get('format')}"
            elif r.get("class") != chosen[b]:
                why = f"class {r.get('class')}"
            elif not same_looks(r):
                why = "not this session's looks"
            elif len(r.get("tones", [])) != n_tones:
                why = f"{len(r.get('tones', []))} signals"
            elif name == "measure":
                if not matched_tables._has_tracks(r):
                    why = "no measured ON tracks"
                elif any(cut not in r[p]["false"] for p in ("ours", "turboseti")):
                    why = "no false candidates at the cut"
                elif any("three_looks" not in t[p].get(cut, {}) for t in r["tones"] for p in ("ours", "turboseti")) \
                        or any(cut not in t.get("turboseti_on_hits", {}) for t in r["tones"]):
                    why = "recovery fields missing"
            else:
                if any(k not in r["false"].get(cut, {}) for k in ("production", pass_key)):
                    why = "no false candidates at the cut"
                elif any("three_looks" not in t.get("status_v2", {}).get(cut, {}).get(k, {})
                         for t in r["tones"] for k in ("production", pass_key)):
                    why = "recovery fields missing"
            if why:
                bad.append(f"block {b} {why}")
        problems += [f"{name}: {x}" for x in bad]
    return problems


def _paired(by_block, seed=2, boot=4000):
    """Paired recovery of the same signals by a and b: {(got_a, got_b)} per
    block. The difference in share, with a bootstrap over blocks (signals in
    one block share its noise and interference)."""
    blocks = [np.array(v, dtype=bool).reshape(-1, 2) for v in by_block if len(v)]
    allv = np.concatenate(blocks) if blocks else np.zeros((0, 2), bool)
    a, b = allv[:, 0], allv[:, 1]
    d = np.array([x[:, 0].sum() - x[:, 1].sum() for x in blocks], float)
    n = np.array([len(x) for x in blocks], float)
    rng = np.random.default_rng(seed)
    idx = [rng.integers(0, len(blocks), len(blocks)) for _ in range(boot)]
    diffs = [d[i].sum() / n[i].sum() for i in idx]
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"signals": int(len(allv)), "both": int((a & b).sum()), "first_only": int((a & ~b).sum()),
            "second_only": int((~a & b).sum()), "neither": int((~a & ~b).sum()),
            "difference": round(float(d.sum() / n.sum()), 4), "interval": (round(float(lo), 4), round(float(hi), 4)),
            "how": f"block bootstrap, {boot} draws, seed {seed}"}


def verdict(cfg, deviation=None, progress=False, say=print):
    """The frozen criteria, only when every chosen block is whole (fail
    closed). With progress: how far the runs are, and no verdict."""
    info = frozen(cfg, deviation, "verdict")
    crit = cfg["criteria"]
    cut, limit = crit["cut"], crit["rate"]
    target = cfg["target"]
    db = store.connect()
    kept = _files(cfg, db)
    if not kept:
        db.close()
        raise yoke.Refusal("NOT_FOUND", "The session is not swept yet.")
    session = kept[0]
    tstarts = _session_tstarts(db, session)
    sessions = [r[0] for r in db.execute("SELECT DISTINCT session FROM files ORDER BY session")]
    db.close()
    choice = _choice()
    meta = json.loads((matched.folder(target, session) / "blocks.json").read_text(encoding="utf-8"))
    if {int(b): c for b, c in meta["chosen"].items()} != {int(b): c for b, c in choice["chosen"].items()} \
            or meta["of"] != choice["of"]:
        raise yoke.Refusal("INVALID_REQUEST", "matched.py's blocks are not the chosen ones.")
    got = _records(matched.folder(target, session))
    cgot = _records(curved_pass.folder(target, session))
    problems = completeness(cfg, choice, got, cgot, tstarts)
    if progress or problems:
        state = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "verdict": None,
                 "chosen": len(choice["chosen"]), "problems": problems,
                 "measure_done": sum(1 for b in choice["chosen"] if got.get(int(b))),
                 "curved_done": sum(1 for b in choice["chosen"] if cgot.get(int(b)))}
        ROOT.mkdir(parents=True, exist_ok=True)
        (ROOT / "progress.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
        say(f"incomplete: no verdict. measure {state['measure_done']} and curved {state['curved_done']} of "
            f"{state['chosen']} blocks; {len(problems)} problem(s)")
        for p in problems[:20]:
            say(f"  {p}")
        if problems and not progress:
            raise yoke.Refusal("INVALID_REQUEST", f"Step {STEP} is not complete: no verdict "
                                                  f"(see data/step{STEP}/progress.json).")
        return state
    recs = [got[b] for b in sorted(got)]
    crecs = [cgot[b] for b in sorted(cgot)]
    rng = np.random.default_rng(1)
    total = meta["of"]["clean"] + meta["of"]["crowded"]
    weights = {c: meta["of"][c] / total for c in ("clean", "crowded")}
    c = matched.ck(cut)
    rates = {p: matched_tables._rate(recs, lambda r, p=p: matched_tables.distinct(r, r[p]["false"][c], "shared hits"),
                                     weights, rng)
             for p in ("ours", "turboseti")}
    tones = [t for r in recs for t in r["tones"]]
    rec_ = {p: _share(sum(matched_tables._got(t, p, cut, "three_looks") for t in tones), len(tones))
            for p in ("ours", "turboseti")}
    fa = {p: sum(matched_tables._false_assoc(t, p, cut, "three_looks") for t in tones) for p in ("ours", "turboseti")}
    paired = _paired([[(matched_tables._got(t, "ours", cut, "three_looks"),
                        matched_tables._got(t, "turboseti", cut, "three_looks")) for t in r["tones"]] for r in recs])
    out = {"target": target, "session": session, "config_sha256": load()[1], "config_commit": info["config_commit"],
           "git_commit": _git("rev-parse", "HEAD"), "code_fingerprints": len(cfg["code"]),
           "deviations": info["problems"], "store_sessions": sessions, "blocks": len(recs), "complete": True,
           "classes": {k: sum(r["class"] == k for r in recs) for k in ("clean", "crowded")},
           "of": meta["of"], "weights": weights, "cut": cut, "rate_limit": limit,
           "false_rate": rates, "recovery_three_looks": rec_, "false_associations": fa,
           "criteria": {
               "this search's false rate": _rate_verdict(rates["ours"], limit),
               "turboSETI's false rate": _rate_verdict(rates["turboseti"], limit),
               "this search's recovery above turboSETI's": _apart(rec_["ours"], rec_["turboseti"])},
           "supplementary": {"paired_ours_turboseti": paired}}
    out["step4"] = cfg.get("step4")
    cp = crit["curved_pass"]
    cfg_key = curved_pass.key(cp["a_max"])
    crates = {k: matched_tables._rate(crecs, lambda r, k=k: len(matched.shared_hits(r["false"][c][k])), weights, rng)
              for k in ("production", cfg_key)}
    ct = [t for r in crecs for t in r["tones"]]

    def is_curved(t):
        return abs(t["accel"]) >= cp["curved_from"] - 1e-12

    def cgot_(t, k):
        return t["status_v2"][c][k]["three_looks"] == "recovered"
    curved_ = [t for t in ct if is_curved(t)]
    crec = {k: _share(sum(cgot_(t, k) for t in curved_), len(curved_)) for k in ("production", cfg_key)}
    lost = sum(cgot_(t, "production") and not cgot_(t, cfg_key) for t in ct)
    out["curved_pass"] = {
        "a_max": cp["a_max"], "blocks": len(crecs), "false_rate": crates,
        "recovery_three_looks_curved": crec, "curved_from": cp["curved_from"],
        "production_recoveries_lost": lost, "signals": len(ct),
        "false_associations": {k: sum(t["status_v2"][c][k]["three_looks"] == "false association" for t in ct)
                               for k in ("production", cfg_key)}}
    out["supplementary"]["paired_pass_production_curved"] = _paired(
        [[(cgot_(t, cfg_key), cgot_(t, "production")) for t in r["tones"] if is_curved(t)] for r in crecs])
    out["criteria"].update({
        "the pass's false rate": _rate_verdict(crates[cfg_key], limit),
        "the pass's curved recovery above production's": _apart(crec[cfg_key], crec["production"]),
        "the pass loses none of production's recoveries": "holds" if lost == 0 else f"fails ({lost})"})
    out["kind"] = "measured"
    out["step"] = STEP
    yoke.write(yoke.DATA / "measurements" / f"step{STEP}.json", out, stamp=True)
    # The full tables of the new session, under their own names (step 4's records are left as they are).
    matched_tables.write(target, say=lambda *_: None, name=f"matched-{target}.json")
    curved_pass.tables(target, say=lambda *_: None, name=f"curved-pass-{target}.json")
    page = yoke.ROOT / "docs" / "results" / f"{target}-{session}-step{STEP}.md"
    page.write_text(markdown(out, cfg), encoding="utf-8")
    say(f"{page}")
    for k, v in out["criteria"].items():
        say(f"  {k}: {v}")
    return out


def _iv(x):
    return f"{x[0]:.3g}-{x[1]:.3g}"


def markdown(r, cfg):
    lines = [f"# {r['target']} {r['session']}: step 4's comparison on another session", "",
             f"Written by `independent.py verdict` (comparable.md step {STEP}) under config/step{STEP}.json "
             f"(sha256 {r['config_sha256'][:12]}, committed {r['config_commit']}); the record is "
             f"data/measurements/step{STEP}.json. Every choice was fixed in that file before any of this "
             "session's data "
             "was read; nothing here was chosen on it.", ""]
    if r["deviations"]:
        lines += ["**Deviations from the frozen config:** " + "; ".join(r["deviations"])
                  + f" (data/step{STEP}/deviations.json).", ""]
    lines += [f"{r['blocks']} blocks ({r['classes']['crowded']} crowded of {r['of']['crowded']}, "
              f"{r['classes']['clean']} clean of {r['of']['clean']}), every one whole (the verdict is refused "
              "otherwise), weighted by each class's share of the session's blocks. Code at "
              f"{r['git_commit'][:12]}, its {r['code_fingerprints']} fingerprints as frozen.", "",
              "| criterion (fixed beforehand) | result |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in r["criteria"].items()]
    fr, rc = r["false_rate"], r["recovery_three_looks"]
    lines += ["", f"At SNR {r['cut']}, false candidates a block (95% interval) and recovery in all three ON looks "
              "(Wilson interval):", "",
              "| | false a block | recovered |", "|---|---|---|",
              f"| this search | {fr['ours']['per_block']:.3f} ({_iv(fr['ours']['interval'])}) | "
              f"{rc['ours']['recovered']} of {rc['ours']['of']} ({_iv(rc['ours']['interval'])}) |",
              f"| turboSETI | {fr['turboseti']['per_block']:.3f} ({_iv(fr['turboseti']['interval'])}) | "
              f"{rc['turboseti']['recovered']} of {rc['turboseti']['of']} ({_iv(rc['turboseti']['interval'])}) |",
              "", f"Every planted signal is in the denominator; false associations (the unplanted block already "
              f"held the match) are counted as not recovered: this search {r['false_associations']['ours']}, "
              f"turboSETI {r['false_associations']['turboseti']}."]
    sp = r["supplementary"]
    lines += ["", "**Supplementary, not a criterion:** the same signals, paired (a block bootstrap of the "
              "difference in share; signals in a block share its noise and interference):", "",
              "| | both | first only | second only | neither | difference (95%) |", "|---|---|---|---|---|---|"]
    for label, k in (("this search, turboSETI", "paired_ours_turboseti"),
                     ("the pass, production (curved signals)", "paired_pass_production_curved")):
        x = sp.get(k)
        if x:
            lines.append(f"| {label} | {x['both']} | {x['first_only']} | {x['second_only']} | {x['neither']} | "
                         f"{x['difference']:+.3f} ({_iv(x['interval'])}) |")
    if r.get("step4"):
        s4 = r["step4"]
        lines += ["", f"Step 4 (AGBT17A_999_68): {s4['ours_recovered']} against {s4['turboseti_recovered']} of "
                  f"{s4['planted']}, both rates about {s4['rate']} a block at SNR 30."]
    cp = r.get("curved_pass")
    if cp:
        k = curved_pass.key(cp["a_max"])
        lines += ["", f"The curved second pass (a_max {cp['a_max']:g} Hz/s², {cp['blocks']} blocks):", "",
                  "| | false a block | curved signals recovered (\\|a\\| ≥ "
                  f"{cp['curved_from']:g}) |", "|---|---|---|"]
        for name, key_ in (("production", "production"), ("the pass", k)):
            f_, c_ = cp["false_rate"][key_], cp["recovery_three_looks_curved"][key_]
            lines.append(f"| {name} | {f_['per_block']:.3f} ({_iv(f_['interval'])}) | {c_['recovered']} of "
                         f"{c_['of']} ({_iv(c_['interval'])}) |")
        lines += ["", f"Of {cp['signals']} planted, production's recoveries the pass lost: "
                  f"{cp['production_recoveries_lost']}; false associations {cp['false_associations']}."]
    lines += ["", f"The store held {', '.join(r['store_sessions'])} when this was written (check 6 reads every "
              "session's looks)."]
    return "\n".join(lines) + "\n"


def freeze(say=print):
    """Write the code fingerprints into the config, before the first stage only."""
    cfg, _ = load()
    if ROOT.exists() and any(x.name not in KEEP for x in ROOT.iterdir()):
        raise yoke.Refusal("INVALID_REQUEST", f"{ROOT} exists: a stage has run, so the freeze is fixed.")
    db = store.connect()
    swept = db.execute("SELECT COUNT(*) FROM files WHERE session=?", (cfg["session"],)).fetchone()[0]
    db.close()
    if swept:
        raise yoke.Refusal("INVALID_REQUEST", "The session is already in the store: too late to freeze.")
    cfg["code"] = fingerprint()
    CONFIG.write_text(json.dumps(cfg, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    say(f"{CONFIG}: {len(cfg['code'])} fingerprints written; commit it before the sweep")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--step", type=int, default=10, help="the step whose config to run (10 or 12)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "sweep", "choose", "measure", "curved", "verdict", "freeze"):
        p = sub.add_parser(name)
        if name != "freeze":
            p.add_argument("--deviation", help="run although the freeze does not hold; logged and reported")
        if name in ("sweep", "measure", "curved"):
            p.add_argument("--blocks", type=int)
        if name in ("measure", "curved"):
            p.add_argument("--shard", default="0/1")
        if name == "verdict":
            p.add_argument("--progress", action="store_true", help="how far the runs are; never a verdict")
    a = ap.parse_args(argv)
    set_step(a.step)
    try:
        if a.cmd == "freeze":
            freeze()
            return 0
        cfg, _ = load()
        shard = tuple(int(x) for x in getattr(a, "shard", "0/1").split("/"))
        if a.cmd == "check":
            check(cfg)
        elif a.cmd == "sweep":
            sweep(cfg, a.blocks, a.deviation)
        elif a.cmd == "choose":
            choose(cfg, a.deviation)
        elif a.cmd == "measure":
            measure_blocks(cfg, shard, a.blocks, a.deviation)
        elif a.cmd == "curved":
            curved(cfg, shard, a.blocks, a.deviation)
        else:
            verdict(cfg, a.deviation, progress=a.progress)
    except yoke.Refusal as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
