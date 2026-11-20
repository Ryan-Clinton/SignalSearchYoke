"""Control B (docs/audits.md 4): real cadences of other targets, in their own
time order, searched and judged by the frozen search and cadence test as
published. No candidate in them is taken to be a signal, so their yield is
a false-alarm rate measured on cadences as they are observed, which the 19
wrong ON/OFF choices only stand in for. Supplementary: no verdict of steps
4, 10 or 12 changes.

    python tools/negative_controls.py select        choose the sessions (archive listing and headers only)
    python tools/negative_controls.py run           sweep each chosen cadence whole (hours; resumes)
    python tools/negative_controls.py tables        the rates from the swept cadences

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
    for c in _choice()["chosen"]:
        rec_path = CONTROLS / "sweeps" / f"{c['target']}-{c['session']}.json"
        if not rec_path.exists():
            say(f"{c['session']}: not swept yet")
            continue
        done = json.loads(rec_path.read_text(encoding="utf-8"))["done"]
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
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
