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
    python pipelines.py followup KIC8462852    what drives each pickles window; turboSETI's own noise at a candidate
"""
import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests

import seti
import store
import yoke

ROOT = yoke.DATA / "pipelines"
PICKLES_COMMIT = "e4539e3066e0486409a3dd4d2acb1b835ff7d006"
PICKLES_SHA256 = "a1089030762b6ea898a6afee35584987d2c2d08fe3d4644ae8ca307f8d4258d4"   # read 9 Nov 2026
PICKLES_URL = f"https://raw.githubusercontent.com/UCBerkeleySETI/pickles/{PICKLES_COMMIT}/pickles.py"


def folder(target, session):
    return ROOT / f"{target}-{session}"


def pickles_source():
    """pickles.py at the pinned commit, fetched once: its path and SHA-256.
    It is someone else's code and is run, so a copy (fetched or cached) that
    is not byte for byte the one pinned is refused."""
    path = ROOT / "pickles" / PICKLES_COMMIT[:12] / "pickles.py"
    if not path.exists():
        got = requests.get(PICKLES_URL, timeout=60)
        got.raise_for_status()
        if hashlib.sha256(got.content).hexdigest() != PICKLES_SHA256:
            raise yoke.Refusal("INTERNAL_ERROR", f"{PICKLES_URL} is not the pickles.py pinned (SHA-256 "
                               f"{PICKLES_SHA256[:12]}...); nothing written or run")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(got.content)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if sha != PICKLES_SHA256:
        raise yoke.Refusal("INTERNAL_ERROR", f"{path} is not the pickles.py pinned (SHA-256 {sha[:12]}..., "
                           f"want {PICKLES_SHA256[:12]}...); delete it to fetch it again")
    return path, sha


def _tool(script, *args):
    seti.need_turboseti()
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
    seti.need_turboseti()
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


QUIET_BLOCK = 153       # the reference block: a quiet coarse channel of every look, for turboSETI's noise there
TRACK_HALF = 3          # channels either side of a track blanked when testing what drives a pickles window


def _kurtosis(x):
    """Fisher's kurtosis, biased (scipy.stats.kurtosis's default, as pickles uses it)."""
    x = np.asarray(x, dtype=np.float64).ravel()
    d = x - x.mean()
    m2 = (d * d).mean()
    return float((d ** 4).mean() / (m2 * m2) - 3.0) if m2 > 0 else float("nan")


def _window_png(panels, path, yscale=8):
    """Waterfalls, six looks each, side by side (each a list of (16, n) arrays): greyscale, no dependencies."""
    import struct
    import zlib
    cols = []
    for looks in panels:
        st = np.asarray(looks, dtype=np.float64)
        lo, hi = np.percentile(st, 1), np.percentile(st, 99.7)
        norm = np.clip((st - lo) / max(hi - lo, 1e-12), 0, 1)
        rows = [np.kron((norm[k] * 255).astype(np.uint8), np.ones((yscale, 1), np.uint8)) for k in range(len(st))]
        gap = np.full((3, st.shape[2]), 0, np.uint8)
        col = rows[0]
        for r in rows[1:]:
            col = np.vstack([col, gap + 255, r])
        cols.append(255 - col)
    sep = np.full((cols[0].shape[0], 12), 255, np.uint8)
    img = cols[0]
    for c in cols[1:]:
        img = np.hstack([img, sep, c])
    raw = b"".join(b"\x00" + img[r].tobytes() for r in range(img.shape[0]))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", img.shape[1], img.shape[0],
                                                                           8, 0, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    return path


def followup(target, say=print):
    """The comparison taken to the signal: for each window pickles kept, which
    of this search's tracks make its kurtosis (each look's window scored as
    pickles scores it, then again with every track this search found there
    blanked), with the waterfalls and what is left in each look; for every
    candidate of this search, what turboSETI's own statistics give at the
    line in each ON look, the largest line its top-hit rule weighs beside it,
    and what it reports there at a low cut with and without its smallest
    drift; and
    pickles' score table with and without the one change made to run it.
    Re-reads only the blocks needed; writes data/measurements/pipelines-followup.json
    and docs/pipelines/*.png."""
    p = yoke.DATA / "measurements" / "pipelines.json"
    comp = json.loads(p.read_text(encoding="utf-8"))
    db = store.connect()
    session, urls = store.cadence_files(db, target)
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    windows = [e for e in comp["their_events"] if e["pipeline"] == "pickles"]
    # Every candidate measured on turboSETI's own statistics, not only through the 0.227 scale.
    loud = comp["our_candidates"]

    def block_of(f):
        return next(k for k, (lo, hi) in enumerate(block_list) if lo <= f < hi)

    need = sorted({block_of(w["f_mhz"] - 1e-6) for w in windows} | {block_of(o["f_mhz"]) for o in loud}
                  | ({QUIET_BLOCK} if loud else set()))
    keep = ROOT / "followup" / f"{target}-{session}"
    slices, paths = {}, {}
    for k in need:
        paths[k] = [keep / f"block_{k:03d}" / f"{i}_{Path(u).name.replace('.h5', '')}.h5" for i, u in enumerate(urls)]
        if all(q.exists() for q in paths[k]):
            # Saved by an earlier follow-up: read from disk, not the archive.
            slices[k] = [seti.read_slice(q, -1e12, 1e12) for q in paths[k]]
            continue
        got = seti.read_looks(urls, *block_list[k])
        slices[k] = [got[u] for u in urls]
        paths[k] = [seti.save(got[u], q) for u, q in zip(urls, paths[k])]
        say(f"  block {k} read ({block_list[k][0]:.3f}-{block_list[k][1]:.3f} MHz)")
    pics = yoke.ROOT / "docs" / "pipelines"
    pics.mkdir(parents=True, exist_ok=True)
    out_windows = []
    for w in windows:
        k = block_of(w["f_mhz"] - 1e-6)
        looks = slices[k]
        fch1, foff, tsamp = looks[0]["fch1"], looks[0]["foff"], looks[0]["tsamp"]
        lower = int(round((w["f_mhz"] - fch1) / foff))
        cut = [s["spectra"][:, lower:lower + PICKLES_CHANNELS].astype(np.float64) for s in looks]
        hits = db.execute("SELECT h.*, f.cadence_position FROM hits h JOIN files f USING(file_id) WHERE h.session=? "
                          "AND h.superseded_run IS NULL AND h.block_idx=? AND h.f_start_mhz BETWEEN ? AND ?",
                          (session, k, w["to_mhz"] - 0.002, w["f_mhz"] + 0.002)).fetchall()
        blanked = [c.copy() for c in cut]
        n_t = cut[0].shape[0]
        touched = [0] * 6
        for h in hits:
            pos = h["cadence_position"]
            c = blanked[pos]
            med = float(np.median(cut[pos]))
            for t in range(n_t):
                ch = (h["f_start_mhz"] + h["drift_hz_s"] * t * tsamp / 1e6 - fch1) / foff - lower
                a, b = int(math.floor(ch)) - TRACK_HALF, int(math.ceil(ch)) + TRACK_HALF + 1
                if b > 0 and a < c.shape[1]:
                    c[t, max(a, 0):min(b, c.shape[1])] = med
                    touched[pos] += 1
        k_before = [_kurtosis(c / max(np.max(x) for x in cut)) for c in cut]
        k_after = [_kurtosis(c / max(np.max(x) for x in blanked)) for c in blanked]
        on_med = lambda ks: sorted([ks[0], ks[2], ks[4]])[1]  # noqa: E731
        # Where a look keeps its kurtosis with this search's tracks gone, what is left: each spectrum's
        # strongest 64-channel excess over the look's own level in each channel, and where it is.
        residual = {}
        for pos in range(6):
            if k_after[pos] < 0.25:
                continue
            level = np.median(blanked[pos], axis=0)
            excess = blanked[pos] / np.where(level > 0, level, 1) - 1
            smooth = np.array([np.convolve(row, np.ones(64) / 64, "same") for row in excess])
            residual[pos] = [{"spectrum": t, "excess": round(float(smooth[t].max()), 3),
                              "channel": int(smooth[t].argmax())} for t in range(n_t)]
        name = f"pickles-{w['f_mhz']:.6f}.png"
        _window_png([cut, blanked], pics / name)
        out_windows.append({
            "f_mhz": w["f_mhz"], "to_mhz": w["to_mhz"], "level": w["level"], "block": k,
            "k_published": w["k_on"][:1] + w["k_off"][:1] + w["k_on"][1:2] + w["k_off"][1:2] + w["k_on"][2:] + w["k_off"][2:],
            "k_here": k_before, "k_tracks_blanked": k_after,
            "level1_here": on_med(k_before) >= 0.5 and max(k_before[1::2]) <= 0.25,
            "level1_tracks_blanked": on_med(k_after) >= 0.5 and max(k_after[1::2]) <= 0.25,
            "residual": residual,
            "tracks": [{"position": h["cadence_position"], "f_mhz": h["f_start_mhz"], "drift_hz_s": h["drift_hz_s"],
                        "snr": h["snr"], "shadow": h["origin"] == "shadow"} for h in hits],
            "png": f"docs/pipelines/{name}"})
        say(f"  pickles window {w['f_mhz']:.6f}: ON kurtosis {[round(x, 2) for x in k_before[0::2]]} -> "
            f"{[round(x, 2) for x in k_after[0::2]]} with {len(hits)} track(s) of this search blanked")
    out_loud = []
    for o in loud:
        k = block_of(o["f_mhz"])
        rows = []
        members = {r["position"]: r["f_start_mhz"] for r in db.execute(
            "SELECT eh.position, h.f_start_mhz FROM event_hits eh JOIN hits h USING(hit_id) WHERE eh.event_id=?",
            (o["event_id"],))}
        for i in (0, 2, 4):
            tmp = keep / f"turbo_local_{o['f_mhz']:.6f}_{i}.json"
            # Each look at its own hit's start where it has one, else the event's.
            _tool("turbo_local.py", tmp, members.get(i, o["f_mhz"]), o["drift_hz_s"], 3, paths[k][i],
                  paths[QUIET_BLOCK][i])
            rows.append({"position": i, **json.loads(tmp.read_text(encoding="utf-8"))})
        out_loud.append({**{x: o[x] for x in ("event_id", "f_mhz", "drift_hz_s", "snr", "turboseti_expected_snr")},
                         "block": k, "quiet_block": QUIET_BLOCK, "looks": rows})
        say(f"  turboSETI at {o['f_mhz']:.6f}: SNR on its own statistics "
            + ", ".join(f"{r['files'][0]['line']['snr']:.1f}" for r in rows)
            + "; noise (stddev/median) here " + ", ".join(f"{r['files'][0]['stddev_over_median']:.2e}" for r in rows)
            + ", quiet " + ", ".join(f"{r['files'][1]['stddev_over_median']:.2e}" for r in rows))
    source, _ = pickles_source()
    checks = []
    for k in sorted({w["block"] for w in out_windows}):
        tmp = keep / f"pickles_check_{k:03d}.json"
        _tool("pickles_check.py", source, tmp, *paths[k])
        checks.append({"block": k, **json.loads(tmp.read_text(encoding="utf-8"))})
        say(f"  pickles as published against as run, block {k}: {checks[-1]}")
    db.close()
    record = {"target": target, "session": session, "pickles_windows": out_windows, "turboseti_local": out_loud,
              "pickles_equivalence": checks, "track_half_channels": TRACK_HALF,
              "levels_from": "Painter et al. 2025's text: pickles.py writes the scores and flags only, no level cuts",
              "kind": "measured"}
    yoke.write(yoke.DATA / "measurements" / "pipelines-followup.json", record, stamp=True)
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="turboSETI's and pickles' pipelines over a swept cadence, block by block")
    r.add_argument("target")
    r.add_argument("--blocks", type=int, help="at most this many blocks (default: all left)")
    c = sub.add_parser("compare", help="every event of each pipeline set against the others' (pipelines.json)")
    c.add_argument("target")
    f = sub.add_parser("followup", help="the comparison taken to the signal: pickles' windows, turboSETI's own noise")
    f.add_argument("target")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        run(args.target, args.blocks)
    elif args.cmd == "compare":
        compare(args.target)
    elif args.cmd == "followup":
        followup(args.target)


if __name__ == "__main__":
    sys.exit(main())
