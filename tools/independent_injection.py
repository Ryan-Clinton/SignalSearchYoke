"""The matched experiment's signals planted a second way, by setigen, an injector this project did not write
(docs/independent-injection.md is the protocol, committed before the first block ran): does the project's own
planting (measure.plant) favour this search over turboSETI?

    python tools/independent_injection.py run       16 blocks of the 2017 session (hours; resumes)
    python tools/independent_injection.py tables
    python tools/independent_injection.py tables-first   the first run's, without Doppler smearing
    python tools/independent_injection.py run --draw 2   the second draw: 16 untouched blocks (and tables --draw 2)

Each chosen block of the matched run is read again and the same signals (the same seed) are planted by setigen in the
three ON looks; this search and turboSETI are run on them and scored exactly as the matched run scores. The same
signals planted by measure.plant are the matched records' own results.

setigen plants with its Doppler smearing (SMEAR), a change logged in the protocol: the first run, without it, put each
tone half a spectrum's drift from where the scoring looks. That run is kept in FIRST, and `tables-first` rebuilds its
tables.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import records  # noqa: E402
import yoke  # noqa: E402

TARGET = "KIC8462852"
SEED = 20261124
PER_CLASS = 8
CUTS = ("10", "30")
OUT = yoke.DATA / "analysis" / "independent_injection"
FIRST = OUT / "unsmeared"          # the first run, without setigen's Doppler smearing
SMEAR = True
# The second draw: 16 more blocks, none of the first draw's nor the trial's, fixed in the protocol before it ran.
SECOND = OUT / "second"
SEED_SECOND = 20261126
TRIAL_BLOCK = 13
SETIGEN_PYTHON = Path(os.environ.get("SSY_SETIGEN_PYTHON") or Path(os.environ.get("LOCALAPPDATA", "")) /
                      "ssy-setigen" / "Scripts" / "python.exe")
READ_THREADS = 4


def choose(classes, seed=SEED, per_class=PER_CLASS, exclude=()):
    """per_class crowded and clean blocks of the matched run ({block: class}), drawn by seed from the classes alone,
    leaving out `exclude`."""
    rng = np.random.default_rng(seed)
    out = {}
    for cls in ("crowded", "clean"):
        pool = sorted(b for b, c in classes.items() if c == cls and b not in set(exclude))
        out |= {int(b): cls for b in rng.choice(pool, per_class, replace=False)}
    return dict(sorted(out.items()))


def setigen_planted(cad, ts, work):
    """The six looks with the signals added by setigen in the ON looks (its own S/N set to each signal's S_in)."""
    import matched
    work.mkdir(parents=True, exist_ok=True)
    s = cad[0]["s"]
    on = list(matched.TRUE)
    x = np.array([[matched.where(cad, t, j)[0] for t in ts] for j in on])
    np.savez(work / "in.npz", looks=np.stack([cad[j]["raw"] for j in on]), fch1=s["fch1"], foff=s["foff"],
             tsamp=s["tsamp"], x=x, drift=np.array([t["drift"] for t in ts]), snr=np.array([t["s_in"] for t in ts], float),
             smear=SMEAR)
    done = subprocess.run([str(SETIGEN_PYTHON), "-I", str(ROOT / "tools" / "setigen_plant.py"), str(work / "in.npz"),
                           str(work / "out.npz")], capture_output=True, text=True, timeout=1800)
    if done.returncode:
        raise yoke.Refusal("INTERNAL_ERROR", f"setigen failed: {done.stderr[-400:]}")
    got = np.load(work / "out.npz")["looks"]
    return [{"s": c["s"], "spectra": got[on.index(j)].astype(c["raw"].dtype) if j in on else c["raw"]}
            for j, c in enumerate(cad)]


def one_block(k, rec, slices, urls, work):
    import matched
    import pipelines
    import seti
    cad = matched._cadence(slices, urls)
    ts = matched.tones(cad, np.random.default_rng([matched.SEED, k]))
    if [(round(a["x0"], 6), round(a["drift"], 6), a["s_in"]) for a in ts] != [
            (round(b["x0"], 6), round(b["drift"], 6), b["s_in"]) for b in rec["tones"]]:
        raise yoke.Refusal("INTERNAL_ERROR", f"block {k}: the signals planted again are not the record's")
    planted = setigen_planted(cad, ts, work)
    cad_p = [dict(c, spectra=p["spectra"]) for c, p in zip(cad, planted)]
    ours = matched._ours_true(cad_p, matched.our_search(cad_p))
    paths = [seti.save(dict(p["s"], spectra=p["spectra"]), work / f"{j}.h5") for j, p in enumerate(planted)]
    pipelines._tool("turbo_curves.py", work / "turbo.json", ",".join(map(str, matched.CUTS_TURBO)), "true", *paths)
    turbo = json.loads((work / "turbo.json").read_text(encoding="utf-8"))

    def turbo_kept(cut):
        return matched._turbo_kept(next(e["rows"] for e in turbo["events"] if tuple(e["as_on"]) == matched.TRUE
                                        and e["cut"] == float(cut)))
    rows = []
    for t, r in zip(ts, rec["tones"]):
        t_f = {j: matched.where(cad, t, j)[1] for j in matched.TRUE}
        t_f_turbo = {j: f + t["drift"] * cad[j]["s"]["tsamp"] / 2 / 1e6 for j, f in t_f.items()}
        at = {}
        for c in CUTS:
            mine = matched._status(t_f, t["drift"], ours[c], rec["ours"]["true_plain"][c])["three_looks"]
            theirs = matched._status(t_f_turbo, t["drift"], turbo_kept(c),
                                     rec["turboseti"]["true_plain"][matched.ck(c)], turboseti=True)["three_looks"]
            on_hits = matched._turbo_on_hits(turbo, t_f_turbo, t["drift"], float(c))
            at[c] = {"setigen": {"ours": mine == "recovered", "turboseti": theirs == "recovered" and on_hits == 3},
                     "own": {"ours": r["ours"][c]["three_looks"] == "recovered",
                             "turboseti": r["turboseti"][c]["three_looks"] == "recovered"
                             and r["turboseti_on_hits"][c] == 3}}
        rows.append({"drift": t["drift"], "s_in": t["s_in"], "bin": t["bin"], "at": at})
    return {"block": k, "class": rec["class"], "smearing": SMEAR, "tones": rows, "kind": "measured"}


OWN = ("tools/setigen_plant.py", "tools/independent_injection.py")


def record_problems(rec, k, cls, matched_rec, smearing, code=records.code_problems):
    """Why a block record is not this block's whole result under the protocol: its block and class, every signal
    the matched record's in order, both cuts with both injectors and pipelines, the smearing it was planted with
    (the first run's records carry no field: off), and the code it was made by."""
    import matched
    name = f"block {k}"
    if not isinstance(rec, dict):
        return [f"{name}: no record"]
    out = []
    if (rec.get("block"), rec.get("class")) != (k, cls):
        out.append(f"{name}: the record is of another block")
    if bool(rec.get("smearing", False)) != smearing:
        out.append(f"{name}: planted with smearing {bool(rec.get('smearing', False))}, not {smearing}")
    tones, want = rec.get("tones", []), matched_rec.get("tones", [])
    if len(tones) != matched.TONES or len(want) != matched.TONES:
        out.append(f"{name}: {len(tones)} signals, not {matched.TONES}")
    elif any((round(t.get("drift", 0), 6), t.get("s_in"), t.get("bin")) != (round(w["drift"], 6), w["s_in"], w["bin"])
             for t, w in zip(tones, want)):
        out.append(f"{name}: the signals are not the matched record's")
    cell = {"own": {"ours", "turboseti"}, "setigen": {"ours", "turboseti"}}
    if any(set(t.get("at", {})) != set(CUTS) or any({h: set(v) for h, v in t["at"][c].items()} != cell for c in CUTS)
           for t in tones):
        out.append(f"{name}: a signal is not scored at both cuts for both injectors and pipelines")
    out += [f"{name}: {x}" for x in code(rec.get("provenance"), own=OWN)]
    return out


def _matched():
    """The matched run's folder and its blocks' classes."""
    import matched
    import store
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, TARGET)
    db.close()
    base = matched.folder(TARGET, session)
    meta = json.loads((base / "blocks.json").read_text(encoding="utf-8"))
    return base, urls, {int(b): c for b, c in meta["chosen"].items()}


def chosen_for(classes, draw):
    """The protocol's blocks for a draw (1 or 2), and the folder its records go in."""
    first = choose(classes)
    if draw == 1:
        return first, OUT
    return choose(classes, SEED_SECOND, exclude=set(first) | {TRIAL_BLOCK}), SECOND


def _whole_block(k, cls, matched_rec, smearing):
    return lambda r: not record_problems(r, k, cls, matched_rec, smearing)


def run(say=print, draw=1):
    import seti
    seti.reading.set_threads(READ_THREADS)
    base, urls, classes = _matched()
    chosen, folder = chosen_for(classes, draw)
    path = folder / "choice.json"
    if path.exists() and {int(b): c for b, c in json.loads(path.read_text(encoding="utf-8"))["chosen"].items()} != chosen:
        raise yoke.Refusal("INVALID_REQUEST", "The recorded choice is not the protocol's draw.")
    if not path.exists():
        yoke.write(path, {"target": TARGET, "seed": SEED if draw == 1 else SEED_SECOND, "draw": draw, "chosen": chosen,
                          "kind": "measured"}, indent=1, stamp=True)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    for k, cls in chosen.items():
        out = folder / f"block_{k:03d}.json"
        rec = json.loads((base / f"block_{k:03d}.json").read_text(encoding="utf-8"))
        if out.exists() and not yoke.whole(out, _whole_block(k, cls, rec, SMEAR)):
            got = record_problems(json.loads(out.read_text(encoding="utf-8")), k, cls, rec, SMEAR)
            raise yoke.Refusal("INVALID_REQUEST", f"{out.name} is not this run's whole result ({'; '.join(got)}): "
                                                  "move it aside")
        if yoke.whole(out, _whole_block(k, cls, rec, SMEAR)):
            continue
        work = folder / "work"
        try:
            got = one_block(k, rec, seti.read_looks(urls, *block_list[k]), urls, work)
        finally:
            yoke.remove_tree(work) if work.exists() else None
        yoke.write(out, got, indent=None, stamp=True)
        n = lambda who, how: sum(t["at"]["10"][how][who] for t in got["tones"])  # noqa: E731
        say(f"block {k} ({cls}): at 10, own planting ours {n('ours', 'own')} turboSETI {n('turboseti', 'own')}; "
            f"setigen ours {n('ours', 'setigen')} turboSETI {n('turboseti', 'setigen')}", flush=True)


def _advantage(blocks, cut, how):
    """[ours found, turboSETI found, signals] a block."""
    return np.array([[sum(t["at"][cut][how]["ours"] for t in b["tones"]), sum(t["at"][cut][how]["turboseti"]
                      for t in b["tones"]), len(b["tones"])] for b in blocks], float)


def difference_of_advantages(blocks, cut, seed=SEED, boot=4000):
    """(ours − turboSETI share found) with the project's planting minus the same with setigen's, paired by block,
    95% over blocks drawn again. Above 0: the project's planting favours this search."""
    own, sg = _advantage(blocks, cut, "own"), _advantage(blocks, cut, "setigen")

    def d(i):
        o, s = own[i].sum(axis=0), sg[i].sum(axis=0)
        return (o[0] - o[1]) / o[2] - (s[0] - s[1]) / s[2]
    rng = np.random.default_rng(seed)
    idx = np.arange(len(blocks))
    draws = [d(rng.integers(0, len(blocks), len(blocks))) for _ in range(boot)]
    return {"difference": float(d(idx)), "interval": [float(v) for v in np.percentile(draws, [2.5, 97.5])]}


def tables(say=print, folder=None, smearing=SMEAR, draw=1):
    # the protocol's draw made again here, not taken from the saved choice
    base, _, classes = _matched()
    chosen, home = chosen_for(classes, draw)
    folder = folder or home
    saved = json.loads((home / "choice.json").read_text(encoding="utf-8"))
    if {int(b): c for b, c in saved["chosen"].items()} != chosen:
        raise yoke.Refusal("INVALID_REQUEST", "The recorded choice is not the protocol's draw.")
    blocks = []
    for k, cls in chosen.items():
        p = folder / f"block_{k:03d}.json"
        rec = json.loads((base / f"block_{k:03d}.json").read_text(encoding="utf-8"))
        if not yoke.whole(p, _whole_block(k, cls, rec, smearing)):
            got = record_problems(json.loads(p.read_text(encoding="utf-8")), k, cls, rec, smearing) if p.exists() else []
            raise yoke.Refusal("INVALID_REQUEST", f"block {k} not done or not whole (smearing {smearing})"
                                                  + (f": {'; '.join(got)}" if got else ""))
        blocks.append(json.loads(p.read_text(encoding="utf-8")))
    out = {"blocks": len(blocks), "draw": draw, "signals": sum(len(b["tones"]) for b in blocks), "smearing": smearing,
           "cuts": {},
           "kind": "measured"}
    for c in CUTS:
        cell = {}
        for how in ("own", "setigen"):
            a = _advantage(blocks, c, how).sum(axis=0)
            cell[how] = {"ours": int(a[0]), "turboseti": int(a[1]), "signals": int(a[2]),
                         "ratio": round(a[0] / a[1], 2) if a[1] else None}
        by = {}
        for b in blocks:
            for t in b["tones"]:
                x = by.setdefault(str(t["bin"]), {h: {"ours": 0, "turboseti": 0} for h in ("own", "setigen")})
                for h in ("own", "setigen"):
                    for who in ("ours", "turboseti"):
                        x[h][who] += t["at"][c][h][who]
        cell["by_drift_bin"] = dict(sorted(by.items()))
        cell["own_minus_setigen_advantage"] = difference_of_advantages(blocks, c)
        lo = cell["own_minus_setigen_advantage"]["interval"][0]
        cell["reading"] = ("the project's planting favours this search" if lo > 0 else
                           "not shown that the project's planting favours this search")
        out["cuts"][c] = cell
    yoke.write(folder / "tables.json", out, indent=1, stamp=True)
    for c, cell in out["cuts"].items():
        say(f"at {c}: own {cell['own']}, setigen {cell['setigen']}; {cell['reading']}")
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    draw = 2 if "--draw" in sys.argv and sys.argv[sys.argv.index("--draw") + 1:][:1] == ["2"] else 1
    if cmd == "run":
        run(draw=draw)
    elif cmd == "tables":
        tables(draw=draw)
    elif cmd == "tables-first":
        tables(folder=FIRST, smearing=False)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
