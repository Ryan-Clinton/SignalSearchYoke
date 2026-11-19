"""Does the code as it is now reproduce step 10's measurement? Two of step
10's chosen blocks (the first crowded and the first clean, in the choice's
order) are measured again by matched.block exactly as matched.run did (same
looks, same per-block seed), into a scratch folder, and each record is
compared with the one step 10 wrote, every field but the timings. A step
12 freeze requires this to pass (comparable.md step 12): it shows the
measurement step 12 would run is the one step 10 ran, not that any result
agrees. Writes data/analysis/regress_step10.json; nothing of step 10's is
changed.

    python tools/regress_step10.py
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matched  # noqa: E402
import measure  # noqa: E402
import pipelines  # noqa: E402
import seti  # noqa: E402
import store  # noqa: E402
import yoke  # noqa: E402

TARGET = "HIP17147"
OUT = yoke.DATA / "analysis" / "regress_step10.json"


def _diff(a, b, path="", out=None, limit=20):
    """Where two records differ (paths), up to `limit`."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in ("times", "finished_utc"):
                continue
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'new' if k in a else 'recorded'}")
            else:
                _diff(a[k], b[k], f"{path}/{k}", out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} items, recorded {len(b)}")
        for n, (x, y) in enumerate(zip(a, b)):
            _diff(x, y, f"{path}[{n}]", out, limit)
    elif a != b:
        out.append(f"{path}: {a!r}, recorded {b!r}")
    return out


def main():
    choice = json.loads((yoke.DATA / "step10" / "choice.json").read_text(encoding="utf-8"))
    chosen = {int(b): c for b, c in choice["chosen"].items()}
    picks = [next(b for b, c in chosen.items() if c == cls) for cls in ("crowded", "clean")]
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, TARGET)
    db.close()
    base = matched.folder(TARGET, session)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    source, _ = pipelines.pickles_source()
    vet = measure.vet_hook()
    results = []
    for k in picks:
        recorded = json.loads((base / f"block_{k:03d}.json").read_text(encoding="utf-8"))
        work = yoke.DATA / "analysis" / "regress_work" / f"block_{k:03d}"
        shutil.rmtree(work, ignore_errors=True)
        try:
            slices = seti.read_looks(urls, *block_list[k])
            rec = matched.block(k, chosen[k], slices, urls, work, source, vet, np.random.default_rng([matched.SEED, k]))
        finally:
            shutil.rmtree(work, ignore_errors=True)
        rec = json.loads(json.dumps(rec))
        diffs = _diff(rec, recorded)
        results.append({"block": k, "class": chosen[k], "identical": not diffs, "differences": diffs})
        print(f"block {k} ({chosen[k]}): {'identical' if not diffs else f'{len(diffs)} difference(s)'}", flush=True)
        for d in diffs:
            print("  " + d, flush=True)
    out = {"target": TARGET, "session": session, "blocks": results,
           "passed": all(r["identical"] for r in results), "kind": "measured"}
    yoke.write(OUT, out, indent=1, stamp=True)
    print(f"regression against step 10: {'passed' if out['passed'] else 'FAILED'}", flush=True)
    return 0           # the verdict is in the record; a failure is a result, not a crash to retry


if __name__ == "__main__":
    sys.exit(main())
