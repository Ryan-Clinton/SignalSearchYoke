#!/usr/bin/env python3
"""A search for radio signals from other civilisations in Breakthrough
Listen's open data, as SETI@home did, one slice of the band at a time.

    ./seti.py find KIC8462852                         the observations of a target, by cadence
    ./seti.py search URL --from 2250 --to 2253        narrowband signals in one scan's slice
    ./seti.py cadence ON1 OFF1 ON2 OFF2 ON3 OFF3 --from 2250 --to 2253 --json

Breakthrough Listen (seti.berkeley.edu/opendata) publishes its telescopes'
recordings: Green Bank, Parkes and others, observed in cadences of three
five-minute looks at a target, each followed by a look at another star
(ON, OFF, ON, OFF, ON, OFF). The finest product of each look
(.gpuspec.0000.h5) splits the band into channels about 3 Hz wide, every
18 seconds; it is about 15 GB, so only the slice asked for is read, over
the web, block by block (HTTP range requests; h5py and hdf5plugin).

A transmitter on a planet drifts in frequency as the planet turns and
orbits. `search` adds each scan's spectra along every drift line up to
MAX_DRIFT Hz a second either way (one channel across the scan between
lines) and keeps each line SNR_MIN times above the noise: a hit. The
noise is measured robustly (the median and its absolute deviation, after
taking out the band's smooth shape) so a few bright signals do not hide
the rest.

`cadence` is the test that matters. Nearly every hit is interference from
our own world: satellites, radar, phones, the telescope's own electronics.
Interference comes in whatever the telescope points at; a signal from the
target comes in only while pointing at it. A hit counts as a candidate
only when it is found in all three ON looks, where its drift says it
should be, and in none of the OFF looks; one also seen OFF is labelled
interference, and one missing from an ON look unconfirmed. A candidate is
then something to check against known interference and the published
searches of the same data, never a signal from anyone: every candidate
Breakthrough Listen has examined so far has turned out to be ours.

`benchmark FILE...` runs the same slices (saved with --keep) through
turboSETI, Breakthrough Listen's own search, and sets the hits side by
side. Only --keep writes slices. `sweep` keeps every hit of every look and
every cadence result in the hit store (data/ssy.sqlite, store.py), with a
readable record in data/sweeps/. Reading over the web is reading.py's.
"""
import argparse
import json
import logging
import logging.handlers
import math
import os
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

import numpy as np
import requests

import reading
import store
import yoke

API = "https://seti.berkeley.edu/opendata/api/query-files"
FINE = ".gpuspec.0000.h5"       # the finest frequency product of a Green Bank look
SNR_MIN = 10.0                  # turboSETI's default: a hit is ten times the noise
MAX_DRIFT = 4.0                 # Hz a second either way: the Earth's own turning gives up to about 0.4 at 1-10 GHz
BLOCK = 1024                    # channels in each piece of the band's smooth shape taken out
WINDOW_CHANNELS = 3             # channels either way a hit may sit from where its drift puts it
CADENCE_DAYS = 0.06             # OFF looks within this long (about 1.5 hours) of the ON looks are the cadence's
MAX_LISTED = 100                # hits or events listed; the counts are of all of them
TIMEOUT = 120
HEADERS = reading.HEADERS
MJD_UNIX = 40587.0              # the MJD of 1970-01-01
EDGE_FRACTION = 0.05            # a hit this near a coarse channel's end (as a share of it) is flagged near_edge
TILE = 131072                   # channels summed at a time: 16 spectra of them fit the processor's cache


def _utc(mjd):
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(days=mjd - MJD_UNIX)).strftime("%Y-%m-%d %H:%M:%S")


# --- finding the observations ---------------------------------------------------

def _session(url):
    """The observing session a file belongs to: the folder after pipeline/."""
    parts = url.split("/")
    return parts[parts.index("pipeline") + 1] if "pipeline" in parts else parts[-2]


def _scan(row, on):
    return {"target": str(row["target"]).removeprefix("DIAG_"), "on": on, "mjd": row["mjd"], "utc": _utc(row["mjd"]), "url": row["url"],
            "size_gb": round(row["size"] / 1e9, 2), "centre_mhz": round(float(row["center_freq"]), 3),
            "telescope": row.get("telescope")}


def query(get=requests.get, **params):
    reply = get(API, params=params, timeout=TIMEOUT, headers=HEADERS)
    reply.raise_for_status()
    return reply.json().get("data") or []


_LOOK = re.compile(r'href="([^"]*guppi_(\d+)_(\d+)_(.+?)_(\d{4})\.gpuspec\.0000\.h5)"')


def _bare(name):
    """A target's name as compared: DIAG_ (a diagnostic look) taken off, any case."""
    return str(name).removeprefix("DIAG_").upper()


def folder(on, get=requests.get):
    """Every finest-resolution look in the session folder an ON look is in,
    from the server's own listing: its target from the file's name (DIAG_
    taken off), its time from the name's MJD and seconds, and the size and
    band of the ON look (the same receiver and set-up all session)."""
    base = on["url"].rsplit("/", 1)[0] + "/"
    reply = get(base, timeout=TIMEOUT, headers=HEADERS)
    reply.raise_for_status()
    out = []
    for name, mjd, seconds, target, _ in _LOOK.findall(reply.text):
        target = unquote(target).removeprefix("DIAG_")
        out.append(dict(on, target=target, mjd=int(mjd) + int(seconds) / 86400, url=base + name))
    return out


def find(target, get=requests.get, say=print):
    """The finest-resolution looks at `target`, by session, each session
    with the OFF looks taken between and after them where the archive lists
    them; `complete` when ON, OFF, ON, OFF, ON, OFF are all there."""
    # The archive matches the name anywhere (KIC8462852 brings KIC8462852_OFF
    # too) and files some looks as DIAG_ NAME: only the name itself is ON.
    rows = [r for r in query(get, target=target) if str(r.get("url", "")).endswith(FINE)
            and _bare(r["target"]) == _bare(target)]
    sessions = {}
    for r in rows:
        sessions.setdefault(_session(r["url"]), []).append(r)
    out = []
    for name, ons in sorted(sessions.items()):
        ons.sort(key=lambda r: r["mjd"])
        first, last = ons[0]["mjd"], ons[-1]["mjd"]
        # The archive is asked by target only, and an OFF look is filed under
        # its own target (KIC8462852_OFF, or another star), so the OFF looks
        # are read from the session's own folder: every look there between
        # and just after the ON looks that is not the target.
        try:
            near = folder(ons[0], get)
        except (requests.RequestException, ValueError):
            near = []
        offs = [r for r in near if _bare(r["target"]) != _bare(target)
                and first - CADENCE_DAYS <= r["mjd"] <= last + CADENCE_DAYS]
        scans = sorted([_scan(r, True) for r in ons] + [_scan(r, False) for r in offs], key=lambda s: s["mjd"])
        pattern = "".join("A" if s["on"] else "B" for s in scans)
        out.append({"session": name, "scans": scans, "complete": "ABABAB" in pattern,
                    "command": ("./seti.py cadence " + " ".join(s["url"] for s in scans[pattern.index("ABABAB"):][:6])
                                + f" --from {scans[0]['centre_mhz'] - 1:.3f} --to {scans[0]['centre_mhz'] + 1:.3f}")
                    if "ABABAB" in pattern else None})
    say(f"{len(rows)} finest-resolution looks at {target} in {len(out)} session(s)")
    for s in out:
        on = sum(sc["on"] for sc in s["scans"])
        say(f"  {s['session']}: {on} ON, {len(s['scans']) - on} OFF, {'a whole cadence' if s['complete'] else 'no whole cadence listed'}"
            f" ({s['scans'][0]['utc']} UTC, {s['scans'][0]['centre_mhz']:.0f} MHz, {s['scans'][0]['size_gb']:g} GB a look)")
    return {"target": target, "looks": len(rows), "sessions": out, "kind": "measured"}


# --- reading a slice ------------------------------------------------------------

def channels(fch1, foff, nchans, low, high):
    """The channel range [first, last) covering low to high MHz."""
    a, b = sorted(((low - fch1) / foff, (high - fch1) / foff))
    first, last = max(0, int(math.floor(a))), min(nchans, int(math.ceil(b)) + 1)
    if first >= last:
        raise yoke.Refusal("INVALID_REQUEST", f"{low:g} to {high:g} MHz is outside this file's band "
                                f"({min(fch1, fch1 + foff * nchans):.3f} to {max(fch1, fch1 + foff * nchans):.3f} MHz).")
    return first, last


def blank_dc(spectra, first, per):
    """Blank the receiver's spike at the middle of each coarse channel (the
    "DC bin": one channel of every `per`, made by the instrument, not the
    sky), with the mean of the channels either side. `first` is the slice's
    first channel in the whole file. Both this search and turboSETI found it
    at 2268.1641 and 1473.6328 MHz in Tabby's looks, each a coarse channel's
    middle (3 November 2026)."""
    n_f = spectra.shape[1]
    if per >= n_f + first or per < 4:
        centre = per // 2 - first
        spikes = [centre] if 0 < centre < n_f - 1 else []
    else:
        spikes = [c - first for c in range(per // 2, first + n_f, per) if first < c < first + n_f - 1]
    for c in spikes:
        spectra[:, c] = (spectra[:, c - 1] + spectra[:, c + 1]) / 2
    return spikes


def _web(source):
    return str(source).startswith(("http://", "https://"))


def read_looks(urls, low, high):
    """Several looks' spectra between low and high MHz, read over the web
    at once (reading.py: each file's chunk index, then the chunks by their
    byte ranges, in parallel): {url: slice}, as read_slice gives."""
    indexes = reading.prepare(urls)
    want = {}
    for url, index in zip(urls, indexes):
        if not reading.direct_ready(index):
            raise yoke.Refusal("INTERNAL_ERROR", f"{url} is not laid out as Green Bank's finest product "
                                                 f"(shape {index['shape']}, chunks {index['chunk_shape']}).")
        a = index["attrs"]
        want[url] = channels(float(a["fch1"]), float(a["foff"]), int(a.get("nchans", index["shape"][2])), low, high)
    got, moved = reading.read_many(want)
    out = {}
    for url, index in zip(urls, indexes):
        a, first = index["attrs"], want[url][0]
        per = index["chunk_shape"][2]
        spectra = got.pop(url).astype(np.float64)
        blank_dc(spectra, first, per)
        out[url] = {"spectra": spectra, "fch1": float(a["fch1"]) + first * float(a["foff"]), "foff": float(a["foff"]),
                    "tsamp": float(a["tsamp"]), "first_channel": first, "coarse_channel": per,
                    "tstart": float(a.get("tstart", 0.0)), "target": str(a.get("source_name", "")),
                    "fetched_mb": round(moved[url] / 1e6, 1)}
    return out


def read_slice(source, low, high):
    """One look's spectra between low and high MHz: (time, channel) and its header."""
    if _web(source):
        return read_looks([str(source)], low, high)[str(source)]
    h5py = reading.h5()
    with h5py.File(source, "r") as f:
        data = f["data"]
        attrs = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in data.attrs.items()}
        fch1, foff, nchans = float(attrs["fch1"]), float(attrs["foff"]), int(attrs.get("nchans", data.shape[-1]))
        first, last = channels(fch1, foff, nchans, low, high)
        spectra = np.asarray(data[:, 0, first:last], dtype=np.float64)
        # A slice saved here keeps where it sat in its file and its coarse
        # channels' width, so its spikes are blanked in the same places.
        per = int(attrs.get("coarse_channel", (data.chunks or data.shape)[-1]))
        whole_first = int(attrs.get("first_channel", 0)) + first
    blank_dc(spectra, whole_first, per)
    return {"spectra": spectra, "fch1": fch1 + first * foff, "foff": foff, "tsamp": float(attrs["tsamp"]),
            "first_channel": whole_first, "coarse_channel": per,
            "tstart": float(attrs.get("tstart", 0.0)), "target": str(attrs.get("source_name", "")),
            "fetched_mb": None}


def save(s, path):
    """A slice as a filterbank HDF5 file of the layout Breakthrough Listen's
    own files and its tools (blimpy, turboSETI) read: one `data` set of
    (time, 1, channel) float32 with the header as its attributes."""
    h5py = reading.h5()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n_t, n_f = s["spectra"].shape
    with h5py.File(path, "w") as f:
        f.attrs["CLASS"], f.attrs["VERSION"] = "FILTERBANK", "1.0"
        data = f.create_dataset("data", data=s["spectra"].astype(np.float32).reshape(n_t, 1, n_f))
        header = {"fch1": s["fch1"], "foff": s["foff"], "nchans": n_f, "tsamp": s["tsamp"], "tstart": s["tstart"],
                  "nbits": 32, "nifs": 1, "data_type": 1, "telescope_id": 6, "machine_id": 10,
                  "source_name": s["target"] or "unknown", "src_raj": 0.0, "src_dej": 0.0,
                  "az_start": 0.0, "za_start": 0.0, "ibeam": 0, "nbeams": 1,
                  "first_channel": s.get("first_channel", 0), "coarse_channel": s.get("coarse_channel", n_f)}
        for key, value in header.items():
            data.attrs[key] = value
    return path


# --- the search -----------------------------------------------------------------

def _block_medians(x, block):
    """The median of each run of `block` channels of each row: (rows,
    blocks), the last block shorter if the channels do not divide."""
    n_r, n_f = x.shape
    whole = n_f // block
    out = np.empty((n_r, -(-n_f // block)))
    if whole:
        out[:, :whole] = np.median(x[:, :whole * block].reshape(n_r, whole, block), axis=2)
    if whole * block < n_f:
        out[:, -1] = np.median(x[:, whole * block:], axis=1)
    return out


def flatten(spectra, block=BLOCK, details=False):
    """Each spectrum over its own noise, with the band's smooth shape taken
    out: the median of each BLOCK channels, joined up, and the median
    absolute deviation of what is left. A narrow signal stands out of it.
    With `details`, also each spectrum's noise by block and the blocks'
    centres, to give a hit's noise in the file's own units."""
    n_t, n_f = spectra.shape
    out = np.empty_like(spectra)
    starts = np.arange(0, n_f, block)
    centres = np.minimum(starts + block / 2, n_f - 1)
    every = np.arange(n_f)
    levels = _block_medians(spectra, block)
    for t in range(n_t):
        level = levels[t]
        if len(level) > 1:
            # Carried on to both ends along the slope of the blocks nearest them:
            # held flat there, a sloping band would leave a ramp that adds up to hits.
            xs = np.concatenate([[0.0], centres, [n_f - 1.0]])
            first = level[0] - (level[1] - level[0]) * centres[0] / (centres[1] - centres[0])
            last = level[-1] + (level[-1] - level[-2]) * (n_f - 1 - centres[-1]) / (centres[-1] - centres[-2])
            out[t] = spectra[t] - np.interp(every, xs, np.concatenate([[first], level, [last]]))
        else:
            out[t] = spectra[t] - level[0]
    # The noise too is measured block by block: near a coarse channel's
    # edges the band rolls off and the noise with it, and one figure for
    # the whole spectrum made hits of the quieter edges (3 November 2026,
    # Tabby's 2017 data: four of five hits only this search found).
    middle = np.repeat(_block_medians(out, block), block, axis=1)[:, :n_f]
    spreads = 1.4826 * _block_medians(np.abs(out - middle), block)
    del middle
    for t in range(n_t):
        spread = spreads[t]
        spread[spread <= 0] = np.median(spread[spread > 0]) if (spread > 0).any() else 1.0
        out[t] /= np.interp(every, centres, spread) if len(spread) > 1 else spread[0]
    return (out, {"spreads": spreads, "centres": centres}) if details else out


def search(spectra, foff, tsamp, fch1, snr_min=SNR_MIN, max_drift=MAX_DRIFT, block=BLOCK):
    """The hits in one look: each drift line whose sum is snr_min times its
    noise, the best drift for each channel, and only the strongest within
    the widest drift searched of it (as turboSETI keeps its top hits): one
    strong burst lights every drift line near it, and is one hit, not
    dozens. A hit's frequency is where it was at the start of the look.

    The lines are summed in float32 by adding each spectrum's slice, shifted
    by its drift, onto the total, a cache-sized tile of the band at a time
    (about 3 s a look of 16 x 1,048,575 channels, against 39 s by np.roll in
    float64): the same sums, rounded to float32. On the reference block the
    hits are the same as np.roll's, to the last figure kept."""
    n_t, n_f = spectra.shape
    flat, noise = flatten(spectra, block, details=True)
    width_hz = abs(foff) * 1e6
    span = max(n_t - 1, 1) * tsamp
    most = int(max_drift * span / width_hz) if n_t > 1 else 0
    # Padded with `most` zeros each side, so every shifted slice is in range;
    # what the padding touches is masked below, as np.roll's wrap was.
    padded = np.zeros((n_t, n_f + 2 * most), np.float32)
    padded[:, most:most + n_f] = flat
    del flat
    best, best_k = np.full(n_f, -np.inf, dtype=np.float32), np.zeros(n_f, np.int32)
    steps = np.arange(n_t) / max(n_t - 1, 1)
    scale = np.float32(1 / math.sqrt(n_t))
    shifts = [(k, [int(round(k * steps[t])) for t in range(n_t)]) for k in range(-most, most + 1)]
    # The band is taken a tile at a time, every drift for one tile before the
    # next: a tile's spectra stay in the processor's cache, where the whole
    # band's would stream from memory for every drift (memory-bound: six
    # looks searched side by side took no less time than one after another).
    for lo in range(0, n_f, TILE):
        hi = min(lo + TILE, n_f)
        total, tile_best, tile_k = np.empty(hi - lo, np.float32), best[lo:hi], best_k[lo:hi]
        for k, ss in shifts:
            total[:] = 0
            for t, s in enumerate(ss):
                # total[i] += flat[t, i + s], in order of t: the same sums as before
                total += padded[t, most + lo + s:most + hi + s]
            total *= scale
            if k > 0 and hi > n_f - k:
                total[max(n_f - k, lo) - lo:] = -np.inf     # would have wrapped round the end of the slice
            elif k < 0 and lo < -k:
                total[:min(-k, hi) - lo] = -np.inf
            better = total > tile_best
            np.copyto(tile_k, k, where=better)
            np.maximum(tile_best, total, out=tile_best)
    del padded
    # The slice's ends: a drift line starting there runs off the slice, so
    # what lies within the widest drift of either end is not searched.
    edge = most + WINDOW_CHANNELS
    best[:edge] = best[n_f - edge:] = -np.inf
    over = np.flatnonzero(best >= snr_min)
    # One hit for each run of bright channels no further apart than the
    # widest drift: a burst of interference lights a wide run of them and is
    # one hit, not one for every drift line (turboSETI keeps one top hit in
    # each such window too).
    reach = most + WINDOW_CHANNELS
    step_hz_s = width_hz / span if span else 0.0
    hits, run = [], []
    for i in list(over) + [None]:
        if run and (i is None or i - run[-1] > reach):
            top = max(run, key=lambda c: best[c])
            drift = float(best_k[top] * foff * 1e6 / span) if span else 0.0
            f0 = fch1 + top * foff
            sigma = float(np.median([np.interp(top, noise["centres"], row) for row in noise["spreads"]]))
            snr = float(best[top])
            hits.append({"channel": int(top), "frequency_mhz": round(f0, 6),
                         "drift_hz_s": round(drift, 4), "snr": round(snr, 1),
                         "width_channels": int(run[-1] - run[0] + 1),
                         "end_frequency_mhz": round(f0 + drift * span / 1e6, 6),
                         "drift_error_hz_s": round(step_hz_s / 2, 4),
                         "drift_norm": drift / (f0 * 1e6) if f0 else None,
                         "noise": sigma, "power": snr * math.sqrt(n_t) * sigma,
                         "smear": round(abs(drift) * tsamp / width_hz, 3) if width_hz else None})
            run = []
        if i is not None:
            run.append(i)
    return hits


def describe(hits, s):
    """Where each hit sits in its file: its channel there, and whether it is
    near a coarse channel's end (the band rolls off) or its middle (the
    blanked spike)."""
    n_t = s["spectra"].shape[0]
    width_hz, span = abs(s["foff"]) * 1e6, max(n_t - 1, 1) * s["tsamp"]
    reach = (int(MAX_DRIFT * span / width_hz) if n_t > 1 else 0) + WINDOW_CHANNELS
    first, per = int(s.get("first_channel") or 0), int(s.get("coarse_channel") or 0)
    for h in hits:
        h["file_channel"] = first + h["channel"]
        if per:
            within = h["file_channel"] % per
            h["near_edge"] = min(within, per - 1 - within) < EDGE_FRACTION * per
            h["near_dc"] = abs(within - per // 2) <= reach
    return hits


def look(source, low, high, say=print, read=read_slice, keep=None):
    """`search` on one look's slice, read from a file here or on the web;
    with `keep` (a folder) the slice is also saved there, for a second look
    or the benchmark, without reading it over the web again."""
    s = read(source, low, high)
    if keep:
        save(s, Path(keep) / (Path(str(source)).name.replace(".h5", "") + f"_{low:g}-{high:g}.h5"))
    hits = describe(search(s["spectra"], s["foff"], s["tsamp"], s["fch1"]), s)
    n_t, n_f = s["spectra"].shape
    answer = {"source": str(source), "target": s["target"], "from_mhz": low, "to_mhz": high, "channels": n_f,
              "channel_hz": round(abs(s["foff"]) * 1e6, 3), "spectra": n_t, "seconds": round(n_t * s["tsamp"], 1),
              "tstart": s["tstart"], "max_drift_hz_s": MAX_DRIFT, "snr_min": SNR_MIN, "fetched_mb": s["fetched_mb"],
              "hit_count": len(hits), "hits": sorted(hits, key=lambda h: -h["snr"])[:MAX_LISTED], "kind": "measured"}
    say(f"{s['target'] or source}: {n_f} channels of {answer['channel_hz']:g} Hz, {n_t} spectra over "
        f"{answer['seconds']:g} s; {len(hits)} hit(s) at {SNR_MIN:g} times the noise or more, drifts up to "
        f"±{MAX_DRIFT:g} Hz/s" + (f" ({s['fetched_mb']:g} MB read)" if s["fetched_mb"] else ""))
    for h in answer["hits"][:10]:
        say(f"  {h['frequency_mhz']:.6f} MHz  drift {h['drift_hz_s']:+.4f} Hz/s  SNR {h['snr']:g}")
    return answer, hits, s


def _near(hits, frequency, window_mhz, drift=None, drift_tolerance=None):
    """The first hit near `frequency` (and `drift`): its index, or None."""
    for i, h in enumerate(hits):
        if abs(h["frequency_mhz"] - frequency) <= window_mhz and (
                drift is None or abs(h["drift_hz_s"] - drift) <= drift_tolerance):
            return i
    return None


def judge(looks):
    """The ON, OFF, ON, OFF, ON, OFF test on six looks' hits. `looks` are
    (hits, tstart MJD, channel width Hz, seconds) in cadence order; each
    hit of the first ON look is followed to where its drift puts it in each
    later look. Found in every ON and no OFF: a candidate. Each event keeps
    `matches`: for each look, the index of the hit matched there, or None."""
    first_hits, t0, width_hz, seconds = looks[0]
    events = []
    for seed, h in enumerate(first_hits):
        drift = h["drift_hz_s"]
        tolerance = max(0.5 * abs(drift), 2 * width_hz / max(seconds, 1e-9))
        in_on, in_off, matches = [True], [], [seed]
        for j, (hits, tstart, _, secs) in enumerate(looks[1:], start=1):
            later = (tstart - t0) * 86400
            expected = h["frequency_mhz"] + drift * later / 1e6
            window = (WINDOW_CHANNELS * width_hz + abs(drift) * secs) / 1e6
            if j % 2:   # an OFF look: anything near where it should be, or where it started, is ours
                m = _near(hits, expected, window)
                m = m if m is not None else _near(hits, h["frequency_mhz"], window)
                in_off.append(m is not None)
            else:
                m = _near(hits, expected, window, drift, tolerance)
                in_on.append(m is not None)
            matches.append(m)
        label = "interference" if any(in_off) else "candidate" if all(in_on) else "unconfirmed"
        events.append(dict(h, label=label, in_on=in_on, in_off=in_off, matches=matches))
    return events


def cadence(sources, low, high, say=print, read=read_slice, keep=None, every_hit=False):
    """The six looks searched, then judged together. Read over the web, the
    six are fetched at once; the six searches run side by side. With
    `every_hit`, the answer also carries each look's every hit (`_looks`)."""
    if len(sources) != 6:
        raise yoke.Refusal("INVALID_REQUEST", "A cadence is six looks: ON, OFF, ON, OFF, ON, OFF.")
    if read is read_slice and all(_web(s) for s in sources):
        fetched = read_looks([str(s) for s in sources], low, high)
        read = lambda source, *_: fetched.pop(str(source))  # noqa: E731
    with ThreadPoolExecutor(max_workers=6) as pool:
        done = list(pool.map(lambda source: look(source, low, high, say=lambda *_: None, read=read, keep=keep),
                             sources))
    scans, looks = [], []
    for k, (source, (answer, hits, s)) in enumerate(zip(sources, done)):
        scans.append({"source": str(source), "target": s["target"], "on": k % 2 == 0, "hit_count": len(hits),
                      "fetched_mb": s["fetched_mb"]})
        looks.append((hits, s["tstart"], abs(s["foff"]) * 1e6, answer["seconds"]))
    events = judge(looks)
    count = {label: sum(e["label"] == label for e in events) for label in ("candidate", "interference", "unconfirmed")}
    note = ("A candidate is found in every ON look where its drift puts it and in no OFF look. It is then checked "
            "against known interference and the published searches of these data: a candidate is never a signal "
            "from anyone until all of that is done, and so far every one has been ours.")
    say(f"{low:g} to {high:g} MHz, {len(events)} hit(s) in the first ON look: {count['candidate']} candidate(s), "
        f"{count['interference']} seen in an OFF look too (interference), {count['unconfirmed']} not in every ON look")
    for e in [e for e in events if e["label"] == "candidate"][:10]:
        say(f"  candidate {e['frequency_mhz']:.6f} MHz  drift {e['drift_hz_s']:+.4f} Hz/s  SNR {e['snr']:g}")
    say(note)
    order = {"candidate": 0, "unconfirmed": 1, "interference": 2}
    answer = {"from_mhz": low, "to_mhz": high, "scans": scans, "candidates": count["candidate"],
              "interference": count["interference"], "unconfirmed": count["unconfirmed"],
              "events": [{k: v for k, v in e.items() if k != "matches"}
                         for e in sorted(events, key=lambda e: (order[e["label"]], -e["snr"]))[:MAX_LISTED]],
              "note": note, "kind": "measured"}
    if every_hit:
        answer["_looks"], answer["_events"] = [lk[0] for lk in looks], events
    return answer


# --- the sweep: a cadence searched block by block, carried on from run to run -----

def blocks(index):
    """A file's blocks as (from, to) MHz, lowest first, from its chunk
    index: each is one chunk of its HDF5 data (for Green Bank's finest
    product, one coarse channel of 1,048,576 channels, 2.93 MHz), so a slice
    that keeps inside one is read in the fewest pieces. A channel is left
    off each side of a block."""
    a = index["attrs"]
    fch1, foff = float(a["fch1"]), float(a["foff"])
    nchans, per = index["shape"][-1], index["chunk_shape"][-1]
    out = []
    for start in range(0, nchans, per):
        lo, hi = fch1 + (start + 1) * foff, fch1 + (min(start + per, nchans) - 2) * foff
        out.append((round(min(lo, hi), 6), round(max(lo, hi), 6)))
    return sorted(out)


def sweep_store(target, session):
    return yoke.DATA / "sweeps" / f"{target}-{session}.json"


class _Lock:
    """One sweep at a time: an OS lock on data/sweep.lock, let go when the
    process ends however it ends."""

    def __enter__(self):
        path = yoke.DATA / "sweep.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.f.close()
            raise yoke.Refusal("INVALID_REQUEST", "Another sweep is running (data/sweep.lock is held).")
        return self

    def __exit__(self, *_):
        try:
            if os.name == "nt":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        self.f.close()


def _log():
    log = logging.getLogger("ssy.sweep")
    if not log.handlers:
        (yoke.DATA / "logs").mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(yoke.DATA / "logs" / "sweep.log", maxBytes=1 << 20,
                                                       backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%dT%H:%M:%S"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    return log


def _peak_memory_mb():
    """The process's peak memory so far, MB, or None."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            c = Counters()
            c.cb = ctypes.sizeof(c)
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.windll.psapi
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
                return round(c.PeakWorkingSetSize / 1e6)
            return None
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3)
    except (OSError, ImportError, AttributeError):
        return None


def _cpu_seconds():
    t = os.times()
    return t.user + t.system


def search_params():
    return {"snr_min": SNR_MIN, "max_drift_hz_s": MAX_DRIFT, "block": BLOCK, "window_channels": WINDOW_CHANNELS,
            "edge_fraction": EDGE_FRACTION, "cadence_days": CADENCE_DAYS, "threads": reading.threads(),
            "search": "brute-force drift sum, float32 slice-adds, run-chained hits"}


def _cadence_files(db, target, get, say):
    """The cadence's six files: from the store if a sweep kept them, or
    found in the archive (and then kept)."""
    kept = store.cadence_files(db, target)
    if kept:
        return kept[0], kept[1], None
    found = find(target, get=get, say=lambda *_: None)
    session = next((s for s in found["sessions"] if s["complete"]), None)
    if not session:
        raise yoke.Refusal("INVALID_REQUEST", f"No whole ON-OFF cadence of {target} is listed.")
    pattern = "".join("A" if sc["on"] else "B" for sc in session["scans"])
    scans = session["scans"][pattern.index("ABABAB"):][:6]
    return session["session"], [sc["url"] for sc in scans], scans


def export(db, target, session, block_list):
    """The readable sweep record, data/sweeps/TARGET-SESSION.json, from the
    store: each block searched, with its counts and its candidates (what
    check.py reads). The counts of the blocks searched before the hit store
    kept hits are carried as `before_hit_store`."""
    path = sweep_store(target, session)
    before = None
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        before = old.get("before_hit_store") if "store" in old else old.get("done")
    done = {}
    for k, b in store.done_blocks(db, session).items():
        events = []
        for e in db.execute("SELECT * FROM events WHERE session=? AND block_idx=? AND label='candidate'"
                            " ORDER BY snr DESC", (session, k)):
            looks = json.loads(e["looks"])
            events.append({"event_id": e["event_id"], "frequency_mhz": e["f_start_mhz"], "drift_hz_s": e["drift_hz_s"],
                           "snr": e["snr"], "label": e["label"],
                           "in_on": [lk["found"] for lk in looks if lk["position"] % 2 == 0],
                           "in_off": [lk["found"] for lk in looks if lk["position"] % 2 == 1]})
        done[str(k)] = {"from_mhz": b["f_lo_mhz"], "to_mhz": b["f_hi_mhz"], "hits": b["hits"],
                        "candidates": b["candidates"], "interference": b["interference"],
                        "unconfirmed": b["unconfirmed"], "events": events, "searched": b["searched_utc"],
                        "bytes": b["bytes"], "fetch_s": b["fetch_s"], "search_s": b["search_s"]}
    record = {"store": "ssy.sqlite", "blocks": [list(b) for b in block_list], "done": done}
    if before:
        record["before_hit_store"] = before
    yoke.write(path, record, stamp=True, record_version=2)
    return record


def sweep(target, count=1, say=print, get=requests.get):
    """Search the target's first whole cadence `count` blocks further than
    the runs before got, keeping every hit of every look and every cadence
    result in the hit store, so the whole band is covered over many runs:
    what is done, and every candidate found so far. The next block is
    fetched while this one is searched."""
    with _Lock():
        db = store.connect()
        session, urls, scans = _cadence_files(db, target, get, say)
        indexes = reading.prepare(urls)
        file_ids = [store.upsert_file(db, index, session=session,
                                      target=(scans[i]["target"] if scans else None), cadence_target=target,
                                      position=i, is_on=i % 2 == 0) for i, index in enumerate(indexes)]
        block_list = blocks(indexes[0])
        done = store.done_blocks(db, session)
        todo = [k for k in range(len(block_list)) if k not in done][:count]
        run_id = store.start_run(db, f"sweep {target} --blocks {count} --threads {reading.threads()}", search_params())
        log = _log()

        def fetch(k):
            started = time.monotonic()
            slices = read_looks(urls, *block_list[k])
            return slices, {"fetch_s": round(time.monotonic() - started, 1),
                            "bytes": int(sum(s["fetched_mb"] for s in slices.values()) * 1e6)}

        this_run = []
        with ThreadPoolExecutor(max_workers=1) as ahead:
            coming = ahead.submit(fetch, todo[0]) if todo else None
            last_end = time.monotonic()
            for i, k in enumerate(todo):
                slices, timing = coming.result()
                coming = ahead.submit(fetch, todo[i + 1]) if i + 1 < len(todo) else None
                low, high = block_list[k]
                cpu0, started = _cpu_seconds(), time.monotonic()
                answer = cadence(urls, low, high, read=lambda source, *_: slices.pop(str(source)),
                                 say=lambda *_: None, every_hit=True)
                timing["search_s"] = round(time.monotonic() - started, 1)
                looks, events = answer.pop("_looks"), answer.pop("_events")
                now = time.monotonic()
                timing.update(wall_s=round(now - last_end, 1), threads=reading.threads())
                last_end = now
                store.save_block(db, run_id, session, k, low, high, file_ids, looks, events, timing)
                cpu = round(_cpu_seconds() - cpu0, 1)
                hits = sum(len(h) for h in looks)
                log.info(f"{target} {session} block {k} {low:.3f}-{high:.3f} MHz: {timing['bytes'] / 1e6:.0f} MB, "
                         f"fetch {timing['fetch_s']} s, search {timing['search_s']} s, block {timing['wall_s']} s, "
                         f"threads {timing['threads']}, cpu {cpu} s, peak {_peak_memory_mb()} MB; {hits} hits, "
                         f"{answer['candidates']} candidate(s), {answer['interference']} interference, "
                         f"{answer['unconfirmed']} unconfirmed")
                say(f"  block {k + 1} of {len(block_list)}, {low:.3f} to {high:.3f} MHz: {hits} hits; "
                    f"{answer['candidates']} candidate(s), {answer['interference']} interference, "
                    f"{answer['unconfirmed']} unconfirmed ({timing['bytes'] / 1e6:.0f} MB, fetch "
                    f"{timing['fetch_s']} s, search {timing['search_s']} s, {timing['wall_s']} s a block)")
                this_run.append({"block": k, "from_mhz": low, "to_mhz": high, "hits": hits,
                                 "candidates": answer["candidates"], "interference": answer["interference"],
                                 "unconfirmed": answer["unconfirmed"],
                                 "events": [e for e in answer["events"] if e["label"] == "candidate"], **timing})
        store.finish_run(db, run_id)
        record = export(db, target, session, block_list)
        db.close()
    done = record["done"]
    candidates = [dict(e, block=int(k)) for k, d in done.items() for e in d["events"]]
    covered = sum(d["to_mhz"] - d["from_mhz"] for d in done.values())
    say(f"{target}, session {session}: {len(done)} of {len(block_list)} blocks searched "
        f"({covered:.1f} MHz), {len(candidates)} candidate(s) so far; every hit in {store.path()}")
    return {"target": target, "session": session, "blocks": len(block_list), "searched": len(done),
            "searched_mhz": round(covered, 3), "this_run": this_run, "candidates_so_far": candidates[:MAX_LISTED],
            "store": str(store.path()), "run_id": run_id, "kind": "measured"}


# --- completeness: signals planted in real noise ---------------------------------

INJECT_SNRS = (10, 12, 15, 20, 30, 50)   # the strengths planted, in times the noise of the summed line
INJECT_COUNT = 40                        # signals planted at each strength


def plant(spectra, tones, tsamp, width_hz):
    """`spectra` with drifting tones added: (channel at the start, drift Hz/s,
    height in raw units a spectrum), each on its nearest channel in time."""
    out = spectra.copy()
    for channel, drift, height in tones:
        for t in range(out.shape[0]):
            # foff is negative: a rising frequency moves to lower channels
            at = int(round(channel - drift * t * tsamp / width_hz))
            if 0 <= at < out.shape[1]:
                out[t, at] += height
    return out


def inject(path, snrs=INJECT_SNRS, count=INJECT_COUNT, seed=0, say=print, read=read_slice, record=False):
    """How complete the search is, and how clean, in a real look's own noise:
    `count` drifting signals of each strength in `snrs` planted at random
    places and drifts (away from the slice's ends and its own hits), the
    look searched again, and each planted signal counted found when a hit
    lies within its drift's reach with its drift within two steps. Hits
    that are neither planted nor in the look before are false."""
    s = read(path, -1e12, 1e12)
    spectra, foff, tsamp, fch1 = s["spectra"], s["foff"], s["tsamp"], s["fch1"]
    n_t, n_f = spectra.shape
    width_hz, span = abs(foff) * 1e6, max(n_t - 1, 1) * tsamp
    most = int(MAX_DRIFT * span / width_hz)
    reach, step = most + WINDOW_CHANNELS, width_hz / span
    before = search(spectra, foff, tsamp, fch1)
    sigma = float(np.median(np.abs(np.diff(spectra, axis=1)))) / (0.6745 * math.sqrt(2))   # a spectrum's noise
    rng = np.random.default_rng(seed)
    rows, planted_rows = [], []
    for snr in snrs:
        busy = [h["channel"] for h in before]
        tones = []
        for _ in range(200 * count):              # random places, each clear of the others
            if len(tones) == count:
                break
            c = int(rng.integers(2 * reach, n_f - 2 * reach))
            if all(abs(c - b) > 2 * reach for b in busy):
                drift = float(rng.uniform(-0.9, 0.9) * MAX_DRIFT)
                tones.append((c, drift, snr * sigma / math.sqrt(n_t)))
                busy.append(c)
        hits = search(plant(spectra, tones, tsamp, width_hz), foff, tsamp, fch1)
        found, errors, used = 0, [], set()
        for c, drift, height in tones:
            h = next((h for h in hits if abs(h["channel"] - c) <= reach and id(h) not in used
                      and abs(h["drift_hz_s"] - drift) <= 2 * step + 0.05 * abs(drift)), None)
            if h:
                found += 1
                used.add(id(h))
                errors.append(abs(h["drift_hz_s"] - drift))
            planted_rows.append({"channel": int(s.get("first_channel", 0)) + c, "frequency_mhz": fch1 + c * foff,
                                 "drift_hz_s": drift, "snr": snr, "height": height, "found": bool(h),
                                 "hit_snr": h and h["snr"], "hit_drift_hz_s": h and h["drift_hz_s"]})
        old = [h for h in hits if any(abs(h["channel"] - b["channel"]) <= reach for b in before)]
        false = len(hits) - len(used) - len(old)
        planted = len(tones)
        rows.append({"snr": snr, "planted": planted, "found": found, "completeness": round(found / max(planted, 1), 3),
                     "drift_error_hz_s": round(float(np.median(errors)), 4) if errors else None,
                     "false_hits": max(false, 0)})
        say(f"  SNR {snr:>3}: {found} of {planted} found ({100 * found / max(planted, 1):.0f}%), "
            f"drift off by {rows[-1]['drift_error_hz_s']} Hz/s at the median, {rows[-1]['false_hits']} false")
    say(f"{Path(str(path)).name}: {len(before)} hit(s) of its own; signals planted in its noise, {count} at each strength")
    if record:
        # Every planted signal and what became of it, in the hit store. The
        # method is named: these are one channel a spectrum, with no Doppler
        # smearing, so they overstate what is found above 0.15 Hz/s.
        db = store.connect()
        run_id = store.start_run(db, f"inject {path}", dict(search_params(), snrs=list(snrs), count=count, seed=seed))
        store.save_injections(db, run_id, path, "plant: one channel a spectrum, no smearing", planted_rows)
        store.finish_run(db, run_id)
        db.close()
    return {"file": str(path), "own_hits": len(before), "injected": rows, "max_drift_hz_s": MAX_DRIFT,
            "snr_min": SNR_MIN, "kind": "measured"}


# --- the benchmark: the same slices through turboSETI ----------------------------
# turboSETI (github.com/UCBerkeleySETI/turbo_seti) is Breakthrough Listen's
# own narrowband search. It is not an Ubuntu package, so it lives in its own
# environment that sees the system's h5py;
# TURBOSETI_PYTHON is that environment's python (a venv's layout differs on
# Windows: %LOCALAPPDATA%\signalsearchyoke\seti-venv\Scripts\python.exe).
if os.name == "nt":
    _TURBO_VENV = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "signalsearchyoke/seti-venv"
    _TURBO_DEFAULT = _TURBO_VENV / "Scripts/python.exe"
else:
    _TURBO_DEFAULT = Path.home() / ".local/share/signalsearchyoke/seti-venv/bin/python"
TURBOSETI_PYTHON = Path(os.environ.get("SSY_TURBOSETI_PYTHON", _TURBO_DEFAULT))
_TURBO = """
import sys
from turbo_seti.find_doppler.find_doppler import FindDoppler
FindDoppler(sys.argv[1], max_drift=float(sys.argv[2]), snr=float(sys.argv[3]), out_dir=sys.argv[4],
            n_coarse_chan=1, log_level_int=40).search()
"""


def read_dat(text):
    """turboSETI's hits from its .dat table: frequency (MHz), drift (Hz/s), SNR."""
    out = []
    for line in text.splitlines():
        cols = line.split()
        if not cols or line.lstrip().startswith("#") or not cols[0].isdigit():
            continue
        out.append({"drift_hz_s": float(cols[1]), "snr": float(cols[2]), "frequency_mhz": float(cols[3])})
    return out


def turboseti(path, run_it=subprocess.run):
    """turboSETI's hits on a slice file, at the same limits as ours."""
    if not TURBOSETI_PYTHON.exists():
        python = "py -3" if os.name == "nt" else "python3"
        raise yoke.Refusal("INVALID_REQUEST", f"turboSETI is not installed: {python} -m venv "
                                f"--system-site-packages {TURBOSETI_PYTHON.parent.parent} && "
                                f"{TURBOSETI_PYTHON} -m pip install turbo_seti")
    with tempfile.TemporaryDirectory() as out:
        done = run_it([str(TURBOSETI_PYTHON), "-c", _TURBO, str(path), str(MAX_DRIFT), str(SNR_MIN), out],
                      capture_output=True, text=True, timeout=3600)
        if done.returncode:
            raise yoke.Refusal("INTERNAL_ERROR", f"turboSETI failed on {path}: {done.stderr.strip()[-400:]}")
        dat = next(Path(out).glob("*.dat"), None)
        return read_dat(dat.read_text(encoding="utf-8", errors="replace")) if dat else []


def compare(ours, theirs, width_hz, seconds):
    """Hits matched between the two searches: the same place within a few
    channels and the drift's smear, and the drift within one step."""
    step = width_hz / max(seconds, 1e-9)
    matched, theirs_left = [], list(theirs)
    for h in ours:
        window = (WINDOW_CHANNELS * width_hz + abs(h["drift_hz_s"]) * seconds) / 1e6
        twin = next((t for t in theirs_left if abs(t["frequency_mhz"] - h["frequency_mhz"]) <= window
                     and abs(t["drift_hz_s"] - h["drift_hz_s"]) <= 2 * step), None)
        if twin:
            theirs_left.remove(twin)
            matched.append({"ours": h, "turboseti": twin})
    only_ours = [h for h in ours if not any(m["ours"] is h for m in matched)]
    return {"both": len(matched), "only_ours": only_ours, "only_turboseti": theirs_left, "matched": matched}


def benchmark(paths, say=print, turbo=turboseti):
    """Each saved slice searched by this program and by turboSETI, and the
    hits set side by side: what both find, and what only one does."""
    out = []
    for path in paths:
        s = read_slice(path, -1e12, 1e12)
        n_t, n_f = s["spectra"].shape
        seconds = n_t * s["tsamp"]
        ours = search(s["spectra"], s["foff"], s["tsamp"], s["fch1"])
        theirs = turbo(path)
        # turboSETI reads the file as saved, spike and all; a hit of its on a
        # coarse channel's middle, which this search blanks, is set aside.
        n_t, n_f = s["spectra"].shape
        middles = [s["fch1"] + c * s["foff"] for c in range(n_f)
                   if (s.get("first_channel", 0) + c) % s.get("coarse_channel", n_f + 1) == s.get("coarse_channel", 0) // 2]
        spike = [t for t in theirs if any(abs(t["frequency_mhz"] - m) <= 2 * abs(s["foff"]) for m in middles)]
        theirs = [t for t in theirs if t not in spike]
        c = compare(ours, theirs, abs(s["foff"]) * 1e6, seconds)
        out.append({"file": str(path), "target": s["target"], "ours": len(ours), "turboseti": len(theirs),
                    "turboseti_on_dc_spike": len(spike),
                    "both": c["both"], "only_ours": c["only_ours"][:MAX_LISTED],
                    "only_turboseti": c["only_turboseti"][:MAX_LISTED]})
        say(f"{Path(path).name}: ours {len(ours)}, turboSETI {len(theirs)}, both {c['both']}, "
            f"only ours {len(c['only_ours'])}, only turboSETI {len(c['only_turboseti'])}")
    return {"benchmark": out, "max_drift_hz_s": MAX_DRIFT, "snr_min": SNR_MIN, "kind": "measured"}


def run(args, say=print):
    reading.set_threads(args.threads)
    if args.action == "find":
        if len(args.what) != 1:
            raise yoke.Refusal("INVALID_REQUEST", "find takes one target, as Breakthrough Listen names it (KIC8462852).")
        return find(args.what[0], say=say)
    if args.action == "sweep":
        if len(args.what) != 1:
            raise yoke.Refusal("INVALID_REQUEST", "sweep takes one target (KIC8462852).")
        return sweep(args.what[0], args.blocks, say=say)
    if args.action == "inject":
        return [inject(p, say=say, record=True) for p in args.what][-1] if len(args.what) == 1 else \
            {"files": [inject(p, say=say, record=True) for p in args.what], "kind": "measured"}
    if args.action == "benchmark":
        return benchmark(args.what, say=say)
    if args.low is None or args.high is None:
        raise yoke.Refusal("INVALID_REQUEST", "Give the slice: --from MHZ --to MHZ (a few MHz at most: "
                                "each MHz is about 360,000 channels).")
    if args.action == "search":
        if len(args.what) != 1:
            raise yoke.Refusal("INVALID_REQUEST", "search takes one look: a file here or its URL.")
        return look(args.what[0], args.low, args.high, say=say, keep=args.keep)[0]
    return cadence(args.what, args.low, args.high, say=say, keep=args.keep)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("find", "search", "cadence", "sweep", "benchmark", "inject"))
    ap.add_argument("what", nargs="+", help="find: a target; search: one look (file or URL); cadence: six looks")
    ap.add_argument("--from", dest="low", type=float, help="MHz: the bottom of the slice")
    ap.add_argument("--to", dest="high", type=float, help="MHz: the top of the slice")
    ap.add_argument("--blocks", type=int, default=1, help="sweep: blocks of 2.9 MHz to search this run (default 1)")
    ap.add_argument("--keep", help="search, cadence: save each slice read in this folder (for benchmark)")
    ap.add_argument("--threads", type=int, default=reading.THREADS,
                    help=f"requests to the archive in flight at once (default {reading.THREADS}, "
                         f"at most {reading.MAX_THREADS})")
    ap.add_argument("--json", action="store_true", help="answer in JSON")
    args = ap.parse_args()
    yoke.main("seti", lambda: run(args), args.json)


if __name__ == "__main__":
    main()
