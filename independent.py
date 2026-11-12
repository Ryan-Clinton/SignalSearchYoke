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
    python independent.py verdict               the criteria, the page and the record

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

CONFIG = yoke.ROOT / "config" / "step10.json"
ROOT = yoke.DATA / "step10"

# The code the measurement rests on. Whole files where all of the file is the
# measurement; the functions used where the file also holds other work.
FILES = ("searching.py", "onoff.py", "reading.py", "store.py", "injection.py", "measure.py", "matched.py",
         "matched_tables.py", "pipelines.py", "instrument.py", "tools/turbo_curves.py", "tools/pickles_choices.py")
FUNCTIONS = {
    "seti": ("find", "folder", "_session", "_scan", "query", "_bare", "channels", "blank_dc", "read_looks",
             "read_slice", "search", "at_cut", "describe", "look", "cadence", "blocks", "search_params",
             "_cadence_files", "_same_event", "export", "sweep"),
    "curved_pass": ("key", "second_pass", "_kept_pass", "judge_all", "tones", "plant", "expected", "_matches",
                    "status", "statuses", "block", "run", "tables"),
}
CONSTANTS = {
    "seti": ("SNR_MIN", "MAX_DRIFT", "BLOCK", "WINDOW_CHANNELS", "EDGE_FRACTION", "CADENCE_DAYS", "SEARCH_VERSION"),
    "curved_pass": ("A_MAX", "ACCELS", "STRENGTHS", "CUTS", "SEED", "FORMAT", "WAYS"),
    "matched": ("CUTS_OURS", "CUTS_TURBO", "STRENGTHS", "TONES", "TOL_HZ", "TOL_DRIFT", "CROWDED_HITS", "SEED",
                "FORMAT"),
}
MODULES = {"seti": seti, "curved_pass": curved_pass, "matched": matched}


def _sha(text):
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def _stable(v):
    """A constant as text that is the same every run (a function by its source, not its address)."""
    if isinstance(v, (tuple, list)):
        return "(" + ", ".join(_stable(x) for x in v) + ")"
    if callable(v):
        return inspect.getsource(v).strip().replace("\r\n", "\n")
    return repr(v)


def fingerprint():
    """{item: sha256} of the code the measurement rests on."""
    out = {}
    for f in FILES:
        # line endings normalised, so a checkout on another system gives the same print
        out[f] = _sha((yoke.ROOT / f).read_bytes().replace(b"\r\n", b"\n"))
    for mod, names in FUNCTIONS.items():
        for n in names:
            out[f"{mod}.{n}"] = _sha(inspect.getsource(getattr(MODULES[mod], n)).replace("\r\n", "\n"))
    for mod, names in CONSTANTS.items():
        for n in names:
            out[f"{mod}.{n}"] = _sha(_stable(getattr(MODULES[mod], n)))
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
        raise yoke.Refusal("INVALID_REQUEST", "Step 10 is frozen: " + "; ".join(problems)
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
    if not kept:
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
    return seti.sweep(cfg["target"], count=n if count is None else count, say=say)


def choose(cfg, deviation=None, say=print):
    """The frozen block rule on the swept blocks' hit counts (the same count
    as step 4's: hits at the sweep's cut, six looks together)."""
    frozen(cfg, deviation, "choose")
    rule = cfg["blocks"]
    db = store.connect()
    session, urls = _files(cfg, db) or (None, None)
    if session is None:
        raise yoke.Refusal("NOT_FOUND", "The session is not swept yet (independent.py sweep).")
    rows = db.execute("SELECT block_idx, hits, search_version FROM blocks WHERE session=? AND status='done'"
                      " ORDER BY block_idx", (session,)).fetchall()
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
    pick_crowded = sorted(int(b) for b in rng.choice(crowded, size=min(rule["crowded_max"], len(crowded)),
                                                     replace=False)) if crowded else []
    n_clean = min(rule["total"] - len(pick_crowded), len(clean))
    pick_clean = sorted(int(b) for b in rng.choice(clean, size=n_clean, replace=False)) if clean else []
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


def verdict(cfg, deviation=None, say=print):
    info = frozen(cfg, deviation, "verdict")
    crit = cfg["criteria"]
    cut, limit = crit["cut"], crit["rate"]
    target = cfg["target"]
    db = store.connect()
    session = _files(cfg, db)[0]
    sessions = [r[0] for r in db.execute("SELECT DISTINCT session FROM files ORDER BY session")]
    db.close()
    choice = _choice()
    _, meta, recs = matched_tables.load(target)
    if {int(b) for b in meta["chosen"]} != {int(b) for b in choice["chosen"]}:
        raise yoke.Refusal("INVALID_REQUEST", "matched.py's blocks are not the chosen ones.")
    missing = sorted(set(map(int, choice["chosen"])) - {r["block"] for r in recs})
    rng = np.random.default_rng(1)
    total = meta["of"]["clean"] + meta["of"]["crowded"]
    weights = {c: meta["of"][c] / total for c in ("clean", "crowded")}
    c = matched.ck(cut)
    rates = {p: matched_tables._rate(recs, lambda r, p=p: matched_tables.distinct(r, r[p]["false"].get(c, {}),
                                                                                    "shared hits"), weights, rng)
             for p in ("ours", "turboseti")}
    tones = [t for r in recs if matched_tables._has_tracks(r) for t in r["tones"]]
    rec_ = {p: _share(sum(matched_tables._got(t, p, cut, "three_looks") for t in tones), len(tones))
            for p in ("ours", "turboseti")}
    out = {"target": target, "session": session, "config_sha256": load()[1], "config_commit": info["config_commit"],
           "deviations": info["problems"], "store_sessions": sessions, "blocks": len(recs),
           "missing_blocks": missing, "classes": {k: sum(r["class"] == k for r in recs) for k in ("clean", "crowded")},
           "of": meta["of"], "weights": weights, "cut": cut, "rate_limit": limit,
           "false_rate": rates, "recovery_three_looks": rec_,
           "criteria": {
               "this search's false rate": _rate_verdict(rates["ours"], limit),
               "turboSETI's false rate": _rate_verdict(rates["turboseti"], limit),
               "this search's recovery above turboSETI's": _apart(rec_["ours"], rec_["turboseti"])}}
    # Step 4, for the page: the same numbers there.
    out["step4"] = cfg.get("step4")
    # The curved second pass on the same blocks, if its run is done.
    cbase = curved_pass.folder(target, session)
    crecs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(cbase.glob("block_*.json"))]
    crecs = [r for r in crecs if r.get("format") == curved_pass.FORMAT]
    if crecs:
        cp = crit["curved_pass"]
        cfg_key = curved_pass.key(cp["a_max"])
        cmissing = sorted(set(map(int, choice["chosen"])) - {r["block"] for r in crecs})
        crates = {k: matched_tables._rate(crecs, lambda r, k=k: len(matched.shared_hits(r["false"][c][k])), weights,
                                          rng) for k in ("production", cfg_key)}
        ct = [t for r in crecs for t in r["tones"]]
        curved_ = [t for t in ct if abs(t["accel"]) >= cp["curved_from"] - 1e-12]

        def got(t, k):
            return t["status_v2"][c][k]["three_looks"] == "recovered"
        crec = {k: _share(sum(got(t, k) for t in curved_), len(curved_)) for k in ("production", cfg_key)}
        lost = sum(got(t, "production") and not got(t, cfg_key) for t in ct)
        out["curved_pass"] = {
            "a_max": cp["a_max"], "blocks": len(crecs), "missing_blocks": cmissing, "false_rate": crates,
            "recovery_three_looks_curved": crec, "curved_from": cp["curved_from"],
            "production_recoveries_lost": lost, "signals": len(ct),
            "false_associations": {k: sum(t["status_v2"][c][k]["three_looks"] == "false association" for t in ct)
                                   for k in ("production", cfg_key)}}
        out["criteria"].update({
            "the pass's false rate": _rate_verdict(crates[cfg_key], limit),
            "the pass's curved recovery above production's": _apart(crec[cfg_key], crec["production"]),
            "the pass loses none of production's recoveries": "holds" if lost == 0 else f"fails ({lost})"})
    out["kind"] = "measured"
    yoke.write(yoke.DATA / "measurements" / "step10.json", out, stamp=True)
    # The full tables of the new session, under their own names (step 4's records are left as they are).
    matched_tables.write(target, say=lambda *_: None, name=f"matched-{target}.json")
    if crecs:
        curved_pass.tables(target, say=lambda *_: None, name=f"curved-pass-{target}.json")
    page = yoke.ROOT / "docs" / "results" / f"{target}-{session}-step10.md"
    page.write_text(markdown(out, cfg), encoding="utf-8")
    say(f"{page}")
    for k, v in out["criteria"].items():
        say(f"  {k}: {v}")
    return out


def _iv(x):
    return f"{x[0]:.3g}-{x[1]:.3g}"


def markdown(r, cfg):
    lines = [f"# {r['target']} {r['session']}: step 4's comparison on another session", "",
             f"Written by `independent.py verdict` (comparable.md step 10) under config/step10.json "
             f"(sha256 {r['config_sha256'][:12]}, committed {r['config_commit']}); the record is "
             "data/measurements/step10.json. Every choice was fixed in that file before any of this session's data "
             "was read; nothing here was chosen on it.", ""]
    if r["deviations"]:
        lines += ["**Deviations from the frozen config:** " + "; ".join(r["deviations"])
                  + " (data/step10/deviations.json).", ""]
    lines += [f"{r['blocks']} blocks ({r['classes']['crowded']} crowded of {r['of']['crowded']}, "
              f"{r['classes']['clean']} clean of {r['of']['clean']}), weighted by each class's share of the "
              f"session's blocks" + (f"; not done: {r['missing_blocks']}" if r["missing_blocks"] else "") + ".", "",
              "| criterion (fixed beforehand) | result |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in r["criteria"].items()]
    fr, rc = r["false_rate"], r["recovery_three_looks"]
    lines += ["", f"At SNR {r['cut']}, false candidates a block (95% interval) and recovery in all three ON looks "
              "(Wilson interval):", "",
              "| | false a block | recovered |", "|---|---|---|",
              f"| this search | {fr['ours']['per_block']:.3f} ({_iv(fr['ours']['interval'])}) | "
              f"{rc['ours']['recovered']} of {rc['ours']['of']} ({_iv(rc['ours']['interval'])}) |",
              f"| turboSETI | {fr['turboseti']['per_block']:.3f} ({_iv(fr['turboseti']['interval'])}) | "
              f"{rc['turboseti']['recovered']} of {rc['turboseti']['of']} ({_iv(rc['turboseti']['interval'])}) |"]
    if r.get("step4"):
        s4 = r["step4"]
        lines += ["", f"Step 4 (AGBT17A_999_68): {s4['ours_recovered']} against {s4['turboseti_recovered']} of "
                  f"{s4['planted']}, both rates about {s4['rate']} a block at SNR 30."]
    cp = r.get("curved_pass")
    if cp:
        k = curved_pass.key(cp["a_max"])
        lines += ["", f"The curved second pass (a_max {cp['a_max']:g} Hz/s², {cp['blocks']} blocks"
                  + (f"; not done: {cp['missing_blocks']}" if cp["missing_blocks"] else "") + "):", "",
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
    if ROOT.exists() and any(ROOT.iterdir()):
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
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "sweep", "choose", "measure", "curved", "verdict", "freeze"):
        p = sub.add_parser(name)
        if name != "freeze":
            p.add_argument("--deviation", help="run although the freeze does not hold; logged and reported")
        if name in ("sweep", "measure", "curved"):
            p.add_argument("--blocks", type=int)
        if name in ("measure", "curved"):
            p.add_argument("--shard", default="0/1")
    a = ap.parse_args(argv)
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
            verdict(cfg, a.deviation)
    except yoke.Refusal as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
