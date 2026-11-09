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
    python pipelines.py compare KIC8462852     each pipeline's events against the others'
"""
import argparse
import csv
import hashlib
import json
import re
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


MATCH_HZ = 500.0        # a turboSETI hit this close to a candidate's start in a look is taken as the same line
TURBO_SCALE = 0.227     # turboSETI's SNR over this search's, for the same signals (docs/seti.md)
PICKLES_CHANNELS = 1024


def _pickles_rows(path):
    return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))


def _pickles_holding(rows, f_mhz, foff_mhz):
    """pickles' rows whose 1,024-channel window holds f (a row's Freq is its window's first, highest, channel)."""
    width = PICKLES_CHANNELS * abs(foff_mhz)
    return [r for r in rows if float(r["Freq"]) - width < f_mhz <= float(r["Freq"]) + 1e-9]


def _pickles_verdict(masked, unmasked):
    """Why pickles did or did not keep a frequency, from its rows there."""
    if not unmasked:
        return "not a hotspot (no channel 10 MADs up in the middle spectrum of two ON looks)"
    best = max(unmasked, key=lambda r: int(r["level"]))
    if int(best["level"]) == 2:
        return "level 2 (kept)" + ("" if masked else "; masked out as published")
    on = sorted(float(best[k]) for k in ("k1", "k3", "k5"))[1]
    off = max(float(best[k]) for k in ("k2", "k4", "k6"))
    why = []
    stage = "a hotspot, not level 1" if int(best["level"]) == 0 else "level 1, not level 2"
    if int(best["level"]) == 0:
        if on < 0.5:
            why.append(f"median ON kurtosis {on:.3g} < 0.5")
        if off > 0.25:
            why.append(f"largest OFF kurtosis {off:.3g} > 0.25")
    else:
        if best["drift1"] != "1" or best["drift2"] != "True":
            why.append("zero drift by its tests")
        if best["blip or broadband"] == "True":
            why.append("broadband or blip")
    return f"{stage} ({'; '.join(why)})" + ("" if masked else "; masked out as published")


def compare(target, say=print):
    """Every event of each pipeline set against the others': this search's
    candidates in turboSETI's hits and pickles' hotspots, and every event or
    level-2 block of theirs in this search's store, each with the reason the
    others did not keep it. Writes data/measurements/pipelines.json."""
    db = store.connect()
    session, urls = store.cadence_files(db, target)
    base = folder(target, session)
    blocks_done = sorted(base.glob("block_*/block.json"))
    records = [json.loads(p.read_text(encoding="utf-8")) for p in blocks_done]
    files = {r["file_id"]: r for r in db.execute("SELECT file_id, cadence_position, tstart_mjd, foff_mhz FROM files "
                                                    "WHERE session=? AND cadence_target=?", (session, target))}
    foff = next(iter(files.values()))["foff_mhz"]
    position = {fid: r["cadence_position"] for fid, r in files.items()}
    cands = db.execute("SELECT * FROM events WHERE session=? AND superseded_run IS NULL AND label='candidate' "
                       "ORDER BY snr DESC", (session,)).fetchall()
    ours = []
    for c in cands:
        out = base / f"block_{c['block_idx']:03d}"
        dats = sorted((out / "turboseti").glob("*.dat"))
        looks = []
        for p in dats:
            hits = seti.read_dat(p.read_text(encoding="utf-8", errors="replace"))
            best = min(hits, key=lambda h: abs(h["frequency_mhz"] - c["f_start_mhz"]), default=None)
            looks.append(None if best is None else {"offset_hz": round((best["frequency_mhz"] - c["f_start_mhz"]) * 1e6, 1),
                                                    "snr": round(best["snr"], 1), "drift_hz_s": best["drift_hz_s"]})
        matched = [lk for lk in looks if lk and abs(lk["offset_hz"]) <= MATCH_HZ]
        expected = round(c["snr"] * TURBO_SCALE, 1)
        if matched:
            turbo = f"hits in {len(matched)} look(s) within {MATCH_HZ:g} Hz; no event (not in every ON look without the OFF)"
        elif expected < 10:
            turbo = f"no hit within {MATCH_HZ:g} Hz in any look: about SNR {expected:g} on its scale, under its cut of 10"
        else:
            # Its noise is taken over the whole coarse channel, so strong lines elsewhere in it raise the cut.
            loud = max((lk["snr"] for lk in looks if lk), default=None)
            turbo = (f"no hit within {MATCH_HZ:g} Hz in any look, though about SNR {expected:g} on its scale on a "
                     "clean band: it measures the noise over the whole coarse channel, raised here by the "
                     + (f"interference beside it (its nearest hits up to SNR {loud:,.0f})" if loud else "band"))
        rows = _pickles_rows(out / "pickles" / "pickles.csv")
        masked = _pickles_holding([r for r in rows if r["masks"] == "True"], c["f_start_mhz"], foff)
        unmasked = _pickles_holding([r for r in rows if r["masks"] == "False"], c["f_start_mhz"], foff)
        ours.append({"event_id": c["event_id"], "f_mhz": c["f_start_mhz"], "drift_hz_s": c["drift_hz_s"],
                     "snr": c["snr"], "turboseti_looks": looks, "turboseti_expected_snr": expected,
                     "turboseti": turbo, "pickles": _pickles_verdict(masked, unmasked)})
    theirs = []
    width = PICKLES_CHANNELS * abs(foff)
    for rec in records:
        out = base / f"block_{rec['block']:03d}"
        for r in _pickles_rows(out / "pickles" / "pickles.csv"):
            if int(r["level"]) < 1:
                continue
            hi = float(r["Freq"])
            evs = db.execute("SELECT event_id, label, f_start_mhz, drift_hz_s, snr, off_snr_max, on_snr_min FROM events"
                             " WHERE session=? AND superseded_run IS NULL AND f_start_mhz BETWEEN ? AND ?",
                             (session, hi - width, hi)).fetchall()
            hits = db.execute("SELECT file_id, f_start_mhz, drift_hz_s, snr, origin FROM hits WHERE session=? AND "
                              "superseded_run IS NULL AND f_start_mhz BETWEEN ? AND ?", (session, hi - width, hi))
            theirs.append({"pipeline": "pickles", "masks": r["masks"] == "True", "level": int(r["level"]),
                           "f_mhz": hi, "to_mhz": hi - width,
                           "k_on": [float(r[k]) for k in ("k1", "k3", "k5")],
                           "k_off": [float(r[k]) for k in ("k2", "k4", "k6")],
                           "drift": [r["drift1"], r["drift2"]], "blip_or_broadband": r["blip or broadband"] == "True",
                           "ours": [dict(e) for e in evs],
                           "our_hits": [{"position": position.get(h["file_id"]), "f_mhz": h["f_start_mhz"],
                                         "drift_hz_s": h["drift_hz_s"], "snr": h["snr"], "shadow": h["origin"] == "shadow"}
                                        for h in hits]})
        text = (out / "turboseti" / "events.csv").read_text(encoding="utf-8")
        for e in (csv.DictReader(text.splitlines()) if text.strip() else []):
            f = float(e["Freq"])
            evs = db.execute("SELECT event_id, label, f_start_mhz, drift_hz_s, snr FROM events WHERE session=? AND "
                             "superseded_run IS NULL AND abs(f_start_mhz - ?) < ?", (session, f, MATCH_HZ / 1e6))
            theirs.append({"pipeline": "turboseti", "f_mhz": f, "drift_hz_s": float(e["DriftRate"]),
                           "snr": float(e["SNR"]), "ours": [dict(x) for x in evs]})
    version = records[0]["turboseti"]["version"] if records else None
    if not version:
        # Its own logs say which version ran.
        for log in base.glob("block_*/turboseti/*.log"):
            m = re.search(r"turbo_seti version (\S+)", log.read_text(encoding="utf-8", errors="replace"))
            if m:
                version = m.group(1)
                break
    record = {"target": target, "session": session, "blocks": len(records),
              "turboseti": {"version": version,
                            "hits": sum(r["turboseti"]["hits"] for r in records),
                            "events": sum(r["turboseti"]["events"] for r in records),
                            "settings": "±4 Hz/s, SNR 10 (its scale), event pipeline at filter threshold 3, zero drift "
                                        "kept (Price et al. 2020)"},
              "pickles": {"commit": PICKLES_COMMIT, "sha256": records[0]["pickles"]["sha256"] if records else None,
                          **{m: {lv: sum(r["pickles"][m][lv] for r in records) for lv in ("level0", "level1", "level2")}
                             for m in ("masked", "unmasked")},
                          "settings": "1,024-channel windows, SNR 10, not sectioned; level 1: median ON kurtosis >= 0.5 "
                                      "and largest OFF <= 0.25; level 2: not zero drift, not broadband or a blip "
                                      "(Painter et al. 2025)"},
              "ours": {"hits": db.execute("SELECT count(*) FROM hits WHERE session=? AND superseded_run IS NULL AND "
                                          "origin='search'", (session,)).fetchone()[0],
                       "candidates": len(cands)},
              "our_candidates": ours, "their_events": theirs, "match_hz": MATCH_HZ, "turbo_scale": TURBO_SCALE,
              "kind": "measured"}
    db.close()
    path = yoke.DATA / "measurements" / "pipelines.json"
    yoke.write(path, record, stamp=True)
    say(f"{len(records)} blocks; turboSETI {record['turboseti']['hits']} hits, {record['turboseti']['events']} events; "
        f"pickles level 2 {record['pickles']['masked']['level2']} masked, {record['pickles']['unmasked']['level2']} "
        f"unmasked; ours {len(cands)} candidates. {path}")
    for o in ours:
        say(f"  ours {o['f_mhz']:.6f} SNR {o['snr']:.1f}: turboSETI {o['turboseti']}; pickles {o['pickles']}")
    for t in theirs:
        say(f"  {t['pipeline']} {t['f_mhz']:.6f} level {t.get('level')} masks {t.get('masks')}: ours "
            + "; ".join(f"{e['label']} {e['f_start_mhz']:.6f} SNR {e['snr']:.1f}" for e in t["ours"]))
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="turboSETI's and pickles' pipelines over a swept cadence, block by block")
    r.add_argument("target")
    r.add_argument("--blocks", type=int, help="at most this many blocks (default: all left)")
    c = sub.add_parser("compare", help="every event of each pipeline set against the others' (pipelines.json)")
    c.add_argument("target")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        run(args.target, args.blocks)
    elif args.cmd == "compare":
        compare(args.target)


if __name__ == "__main__":
    sys.exit(main())
