"""Other pipelines on the same cadence (comparable.md, step 3).

Over every block the sweep searched, each block's six slices are read as
the sweep reads them (the spectrometer's middle spike blanked the same
way), written as filterbank files, run through both pipelines in
turboSETI's own environment, and deleted:

- **turboSETI with its event pipeline**, as Price et al. 2020 ran it
  (tools/turbo_events.py: ±4 Hz/s, SNR 10, filter threshold 3, zero drift
  kept): its .dat files and events.csv;
- **Painter et al. 2025's kurtosis pipeline** (pickles.py at PICKLES_COMMIT,
  fetched once to data/pipelines/pickles/; tools/pickles_block.py): every
  hotspot's kurtosis scores and its levels 1 and 2, with its interference
  bands masked as published and with none masked.

One folder a block under data/pipelines/TARGET-SESSION/; a block with a
block.json is done, so a run that stops goes on where it stopped.

    python pipelines.py run KIC8462852 [--blocks N]
"""
import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

import seti
import store
import yoke

ROOT = yoke.DATA / "pipelines"
PICKLES_COMMIT = "e4539e3066e0486409a3dd4d2acb1b835ff7d006"
PICKLES_URL = f"https://raw.githubusercontent.com/UCBerkeleySETI/pickles/{PICKLES_COMMIT}/pickles.py"


def folder(target, session):
    return ROOT / f"{target}-{session}"


def pickles_source():
    """pickles.py at the pinned commit, fetched once: its path and SHA-256."""
    path = ROOT / "pickles" / PICKLES_COMMIT[:12] / "pickles.py"
    if not path.exists():
        got = requests.get(PICKLES_URL, timeout=60)
        got.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(got.content)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _tool(script, *args):
    done = subprocess.run([str(seti.TURBOSETI_PYTHON), "-I", str(yoke.ROOT / "tools" / script), *map(str, args)],
                          capture_output=True, text=True, timeout=7200)
    if done.returncode:
        raise yoke.Refusal("INTERNAL_ERROR", f"{script} failed: {done.stderr.strip()[-400:]}")
    return done.stdout


def run(target, count=None, say=print):
    """Both pipelines over the target's swept cadence, block by block."""
    db = store.connect()
    kept = store.cadence_files(db, target)
    db.close()
    if not kept:
        raise yoke.Refusal("NOT_FOUND", f"No swept cadence of {target} in the store.")
    session, urls = kept
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    base, work = folder(target, session), ROOT / "work"
    todo_all = [k for k in range(len(block_list)) if not (base / f"block_{k:03d}" / "block.json").exists()]
    todo = todo_all if count is None else todo_all[:count]
    say(f"{target} {session}: {len(block_list) - len(todo_all)} block(s) done before, {len(todo)} to run")
    source, source_sha = pickles_source()
    turbo_version = subprocess.run([str(seti.TURBOSETI_PYTHON), "-c",
                                    "import turbo_seti; print(turbo_seti.__version__)"],
                                   capture_output=True, text=True).stdout.strip()

    def fetch(k):
        started = time.monotonic()
        slices = seti.read_looks(urls, *block_list[k])
        where = work / f"block_{k:03d}"
        shutil.rmtree(where, ignore_errors=True)
        paths = [seti.save(slices[u], where / f"{i}_{Path(u).name.replace('.h5', '')}.h5")
                 for i, u in enumerate(urls)]
        return where, paths, round(time.monotonic() - started, 1)

    with ThreadPoolExecutor(max_workers=1) as ahead:
        coming = ahead.submit(fetch, todo[0]) if todo else None
        for i, k in enumerate(todo):
            where, paths, fetch_s = coming.result()
            coming = ahead.submit(fetch, todo[i + 1]) if i + 1 < len(todo) else None
            low, high = block_list[k]
            out = base / f"block_{k:03d}"
            shutil.rmtree(out, ignore_errors=True)
            try:
                t0 = time.monotonic()
                _tool("turbo_events.py", out / "turboseti", *paths)
                t1 = time.monotonic()
                _tool("pickles_block.py", source, out / "pickles", *paths)
                t2 = time.monotonic()
            finally:
                shutil.rmtree(where, ignore_errors=True)
            text = (out / "turboseti" / "events.csv").read_text(encoding="utf-8")
            events = list(csv.DictReader(text.splitlines())) if text.strip() else []
            hits = sum(len(seti.read_dat(p.read_text(encoding="utf-8", errors="replace")))
                       for p in (out / "turboseti").glob("*.dat"))
            pk = json.loads((out / "pickles" / "pickles.json").read_text(encoding="utf-8"))
            record = {"block": k, "from_mhz": low, "to_mhz": high, "files": urls,
                      "turboseti": {"version": turbo_version, "hits": hits, "events": len(events),
                                    "run_s": round(t1 - t0, 1)},
                      "pickles": {"commit": PICKLES_COMMIT, "sha256": source_sha, **pk, "run_s": round(t2 - t1, 1)},
                      "fetch_s": fetch_s, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            # Written last: its presence marks the block done.
            (out / "block.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
            line = (f"block {k} {low:.3f}-{high:.3f} MHz: turboSETI {hits} hits, {len(events)} event(s) "
                    f"({record['turboseti']['run_s']} s); pickles level 2 {pk['masked']['level2']} masked, "
                    f"{pk['unmasked']['level2']} unmasked (level 0 {pk['unmasked']['level0']}; "
                    f"{record['pickles']['run_s']} s); fetch {fetch_s} s")
            say("  " + line)
            with open(base / "progress.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%dT%H:%M:%S ", time.gmtime()) + line + "\n")
    shutil.rmtree(work, ignore_errors=True)
    finished = len(list(base.glob("block_*/block.json")))
    say(f"{target} {session}: both pipelines done on {finished} of {len(block_list)} blocks")
    return {"done": finished, "of": len(block_list)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="turboSETI's and pickles' pipelines over a swept cadence, block by block")
    r.add_argument("target")
    r.add_argument("--blocks", type=int, help="at most this many blocks (default: all left)")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        run(args.target, args.blocks)


if __name__ == "__main__":
    sys.exit(main())
