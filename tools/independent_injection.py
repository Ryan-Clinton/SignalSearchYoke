"""The matched experiment's signals planted a second way, by setigen, an injector this project did not write
(docs/independent-injection.md is the protocol, committed before the first block ran): does the project's own
planting (measure.plant) favour this search over turboSETI?

    python tools/independent_injection.py run       16 blocks of the 2017 session (hours; resumes)
    python tools/independent_injection.py tables

Each chosen block of the matched run is read again and the same signals (the same seed) are planted by setigen in the
three ON looks; this search and turboSETI are run on them and scored exactly as the matched run scores. The same
signals planted by measure.plant are the matched records' own results.
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

import yoke  # noqa: E402

TARGET = "KIC8462852"
SEED = 20261124
PER_CLASS = 8
CUTS = ("10", "30")
OUT = yoke.DATA / "analysis" / "independent_injection"
SETIGEN_PYTHON = Path(os.environ.get("SSY_SETIGEN_PYTHON") or Path(os.environ.get("LOCALAPPDATA", "")) /
                      "ssy-setigen" / "Scripts" / "python.exe")
READ_THREADS = 4


def choose(classes, seed=SEED, per_class=PER_CLASS):
    """per_class crowded and clean blocks of the matched run ({block: class}), drawn by seed from the classes alone."""
    rng = np.random.default_rng(seed)
    out = {}
    for cls in ("crowded", "clean"):
        pool = sorted(b for b, c in classes.items() if c == cls)
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
             tsamp=s["tsamp"], x=x, drift=np.array([t["drift"] for t in ts]), snr=np.array([t["s_in"] for t in ts], float))
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
    return {"block": k, "class": rec["class"], "tones": rows, "kind": "measured"}


def run(say=print):
    import matched
    import seti
    import store
    seti.reading.set_threads(READ_THREADS)
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, TARGET)
    db.close()
    base = matched.folder(TARGET, session)
    meta = json.loads((base / "blocks.json").read_text(encoding="utf-8"))
    chosen = choose({int(b): c for b, c in meta["chosen"].items()})
    path = OUT / "choice.json"
    if path.exists() and {int(b): c for b, c in json.loads(path.read_text(encoding="utf-8"))["chosen"].items()} != chosen:
        raise yoke.Refusal("INVALID_REQUEST", "The recorded choice is not the protocol's draw.")
    if not path.exists():
        yoke.write(path, {"target": TARGET, "seed": SEED, "chosen": chosen, "kind": "measured"}, indent=1, stamp=True)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    for k, cls in chosen.items():
        out = OUT / f"block_{k:03d}.json"
        if yoke.whole(out, lambda r: len(r.get("tones", [])) == matched.TONES):
            continue
        rec = json.loads((base / f"block_{k:03d}.json").read_text(encoding="utf-8"))
        work = OUT / "work"
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


def tables(say=print):
    import matched
    choice = json.loads((OUT / "choice.json").read_text(encoding="utf-8"))
    blocks = []
    for k in choice["chosen"]:
        p = OUT / f"block_{int(k):03d}.json"
        if not yoke.whole(p, lambda r: len(r.get("tones", [])) == matched.TONES):
            raise yoke.Refusal("INVALID_REQUEST", f"block {k} not done")
        blocks.append(json.loads(p.read_text(encoding="utf-8")))
    out = {"blocks": len(blocks), "signals": sum(len(b["tones"]) for b in blocks), "cuts": {}, "kind": "measured"}
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
    yoke.write(OUT / "tables.json", out, indent=1, stamp=True)
    for c, cell in out["cuts"].items():
        say(f"at {c}: own {cell['own']}, setigen {cell['setigen']}; {cell['reading']}")
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "run":
        run()
    elif cmd == "tables":
        tables()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
