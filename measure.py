#!/usr/bin/env python3
"""How well the search does on real noise: signals planted as the sky makes
them, close pairs, spectral kurtosis, false hits, and the SNR scale
against turboSETI's. Each answer is kept in data/measurements/.

    ./measure.py desmear FILE...    planted drifting signals through each way of summing
    ./measure.py pairs FILE...      two signals close together: two hits, or one?
    ./measure.py kurtosis FILE...   how many quiet channels spectral kurtosis flags
    ./measure.py false FILE...      hits at the cut in scrambled looks, where no signal can line up
    ./measure.py scale FILE...      this search's SNR against turboSETI's for the same planted signals
    ./measure.py noise FILE...      the planting's noise estimate against the search's own
    ./measure.py cadence [FILE...]  signals planted in whole cadences (six files each; default: the saved ones)
                                    through the search and the cadence test
    ./measure.py vetting            a lone planted signal and a planted look-alike family through the checks
    ./measure.py setigen            the planted signals against setigen's (run in turboSETI's environment)

FILE is a slice saved by `seti.py search --keep` (data/reference/ has six
looks of block 153 and data/reference/blocks/ four more blocks).

A planted signal is made as the sky makes one: a tone moving at its drift
through each 18 s spectrum, its power spread over every channel it crosses
(32 steps a spectrum) with the sinc-squared response of an FFT channel, at a
random place within a channel. Its strength is set from the raw spectra
alone, not from the search: S_in = h x sqrt(16) / sigma, where h is the
power the tone adds to a spectrum and sigma one channel's noise in one
spectrum there, measured by its own method (differences between
neighbouring channels), not the search's. S_in is the SNR a
search would give if it collected every bit of the power and the noise
were ideal; what a search gives is measured against it.
"""
import argparse
import math
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

import onoff
import searching
import seti
import yoke

DRIFT_BINS = ((0.0, 0.15), (0.15, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 4.0))   # Hz/s, as Phase 6 reports
STRENGTHS = (15, 30, 60, 120)                                              # S_in
SUBSTEPS = 32
NEIGHBOURS = 4          # channels either side a tone's sinc-squared response is spread over


# --- signals as the sky makes them ---------------------------------------------------

def plant(raw, tones, tsamp, foff, substeps=SUBSTEPS):
    """`raw` (time, channel) with drifting tones added: each (x0, drift Hz/s,
    h), x0 the fractional channel at the look's start, h the power added to
    each spectrum, spread over the channels crossed with sinc^2 leakage."""
    out = raw.copy()
    n_t, n_f = out.shape
    per_channel = foff * 1e6                          # Hz a channel, negative when the band runs downward
    offsets = np.arange(-NEIGHBOURS, NEIGHBOURS + 2)
    for x0, drift, h in tones:
        for t in range(n_t):
            tau = (t + (np.arange(substeps) + 0.5) / substeps) * tsamp
            x = x0 + drift * tau / per_channel
            base = np.floor(x).astype(int)
            cells = base[:, None] + offsets[None, :]
            weight = np.sinc(cells - x[:, None]) ** 2 * (h / substeps)
            ok = (cells >= 0) & (cells < n_f)
            np.add.at(out[t], cells[ok], weight[ok])
    return out


def channel_noise(raw, block=1024):
    """One channel's noise in one spectrum, by channel (raw units), by its
    own method, not the search's: in each spectrum the differences between
    neighbouring channels (which cancel the band's smooth shape), their
    1.4826 x MAD over sqrt(2) per block of channels, the median over the
    spectra. If neighbouring channels' noise were correlated this would
    read low; `measure.py noise` sets it against the search's own
    estimate."""
    n_t, n_f = raw.shape
    d = np.diff(raw, axis=1)
    whole = (n_f - 1) // block
    rows = d[:, :whole * block].reshape(n_t, whole, block)
    med = np.median(rows, axis=2, keepdims=True)
    spread = 1.4826 * np.median(np.abs(rows - med), axis=2) / math.sqrt(2)
    per_block = np.median(spread, axis=0)
    centres = np.arange(whole) * block + block / 2
    return np.interp(np.arange(n_f), centres, per_block)


def search_noise(raw):
    """The search's own estimate of the same (searching.flatten): each
    block's 1.4826 x MAD after the band's shape is taken out."""
    _, noise = searching.flatten(raw, details=True)
    spread = np.median(noise["spreads"], axis=0)
    return np.interp(np.arange(raw.shape[1]), noise["centres"], spread)


def places(n_f, count, apart, avoid, edge, rng):
    """`count` channels at least `apart` from each other and from `avoid`."""
    taken = list(avoid)
    out = []
    for _ in range(200 * count):
        if len(out) == count:
            break
        c = int(rng.integers(edge, n_f - edge))
        if all(abs(c - b) > apart for b in taken):
            out.append(c)
            taken.append(c)
    return out


def matched(hits, x0, drift, step, used):
    """The hit at the cut that is this planted tone, or None: its start
    within 3 channels and its box of the tone's, its drift within three
    drift steps or 10%."""
    for i, h in enumerate(hits):
        if i in used or h["shadow"]:
            continue
        if abs(h["channel"] - x0) <= searching.WINDOW_CHANNELS + h["box_channels"] and \
                abs(h["drift_hz_s"] - drift) <= max(3 * step, 0.1 * abs(drift)):
            used.add(i)
            return h
    return None


def wilson(k, n, z=1.96):
    """A proportion's 95% interval (Wilson)."""
    if n == 0:
        return (None, None)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3))


def poisson_interval(n, cl=0.95):
    """A count's exact (Garwood) interval, by bisection on the Poisson sums."""
    def cdf(k, mu):
        term, total = math.exp(-mu), math.exp(-mu)
        for i in range(1, k + 1):
            term *= mu / i
            total += term
        return total

    def solve(f, lo, hi):
        for _ in range(200):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
        return (lo + hi) / 2
    a = 1 - cl
    # lower: P(X >= n | mu) = a/2; upper: P(X <= n | mu) = a/2
    lower = solve(lambda mu: a / 2 - (1 - cdf(n - 1, mu)), 0.0, n + 50.0) if n else 0.0
    upper = solve(lambda mu: cdf(n, mu) - a / 2, float(n), n + 50.0 + 10 * math.sqrt(n + 1))
    return (round(lower, 3), round(upper, 3))


def _load(path):
    s = seti.read_slice(path, -1e12, 1e12)
    return s, s["spectra"]


def _keep(name, record):
    path = yoke.DATA / "measurements" / f"{name}.json"
    yoke.write(path, record, stamp=True)
    return path


# --- the measurements ------------------------------------------------------------------

def desmear(paths, runs=10, per_cell=2, seed=1, methods=("boxcar", "scrunch", "none"), say=print):
    """Planted signals in each drift bin and strength, through each way of
    summing (and boxcar without kurtosis flags): how many are found at the
    cut at the right place and drift, their SNR against S_in, and their
    flagged fraction."""
    rng = np.random.default_rng(seed)
    variants = list(methods) + ["boxcar, no kurtosis"]
    tally = {}
    extra = {v: 0 for v in variants}
    for path in paths:
        s, raw = _load(path)
        n_t, n_f = raw.shape
        width_hz = abs(s["foff"]) * 1e6
        span = (n_t - 1) * s["tsamp"]
        step = width_hz / span
        sigma = channel_noise(raw)
        own = seti.at_cut(searching.search(raw, s["foff"], s["tsamp"], s["fch1"]))
        margin = int(searching.MAX_DRIFT * span / width_hz) + 30
        for run in range(runs):
            tones, cells = [], []
            for b, (lo, hi) in enumerate(DRIFT_BINS):
                for strength in STRENGTHS:
                    for _ in range(per_cell):
                        cells.append((b, strength))
            where = places(n_f, len(cells), 2 * margin + 60, [h["channel"] for h in own], margin + 500, rng)
            for c, (b, strength) in zip(where, cells):
                lo, hi = DRIFT_BINS[b]
                drift = float(rng.uniform(lo, hi)) * (1 if rng.random() < 0.5 else -1)
                x0 = c + float(rng.uniform(-0.5, 0.5))
                h = strength * sigma[c] / math.sqrt(n_t)
                tones.append((x0, drift, h, b, strength))
            planted = plant(raw, [(x0, d, h) for x0, d, h, _, _ in tones], s["tsamp"], s["foff"])

            def one(variant):
                method = "boxcar" if variant.startswith("boxcar") else variant
                hits = searching.search(planted, s["foff"], s["tsamp"], s["fch1"], method=method,
                                        sk=not variant.endswith("no kurtosis"))
                return variant, hits
            with ThreadPoolExecutor(max_workers=len(variants)) as pool:
                results = list(pool.map(one, variants))
            for variant, hits in results:
                used = set()
                for x0, drift, h, b, strength in tones:
                    hit = matched(hits, x0, drift, step, used)
                    cell = tally.setdefault((variant, b, strength), {"planted": 0, "found": 0, "snr_over_in": [],
                                                                      "flagged": []})
                    cell["planted"] += 1
                    if hit:
                        cell["found"] += 1
                        cell["snr_over_in"].append(hit["snr"] / strength)
                        if hit["flagged_fraction"] is not None:
                            cell["flagged"].append(hit["flagged_fraction"])
                near_own = {i for i, h in enumerate(hits) if any(abs(h["channel"] - o["channel"]) <= margin for o in own)}
                extra[variant] += sum(1 for i, h in enumerate(hits)
                                      if not h["shadow"] and i not in used and i not in near_own)
        say(f"{Path(path).name}: {runs} runs of {len(cells)} signals")
    rows = []
    for (variant, b, strength), cell in sorted(tally.items(), key=lambda kv: (variants.index(kv[0][0]), kv[0][1], kv[0][2])):
        n, k = cell["planted"], cell["found"]
        rows.append({"method": variant, "drift_hz_s": list(DRIFT_BINS[b]), "s_in": strength, "planted": n, "found": k,
                     "completeness": round(k / n, 3), "interval": wilson(k, n),
                     "snr_over_s_in": round(float(np.median(cell["snr_over_in"])), 3) if cell["snr_over_in"] else None,
                     "flagged_fraction": round(float(np.median(cell["flagged"])), 3) if cell["flagged"] else None})
    record = {"files": [str(p) for p in paths], "runs": runs, "per_cell": per_cell, "seed": seed,
              "rows": rows, "unmatched_hits_at_cut": extra, "kind": "measured"}
    _keep("desmear", record)
    for variant in variants:
        say(f"\n{variant}: found (of {rows[0]['planted']} each), by drift bin (Hz/s) and S_in")
        say("  drift      " + "".join(f"S_in {s:>4} " for s in STRENGTHS))
        for b, (lo, hi) in enumerate(DRIFT_BINS):
            line = [r for r in rows if r["method"] == variant and r["drift_hz_s"] == [lo, hi]]
            say(f"  {lo:4.2f}-{hi:4.2f}  " + "".join(f"{r['completeness']:>8.0%}  " for r in line)
                + "  SNR/S_in " + " ".join(f"{r['snr_over_s_in'] or 0:.2f}" for r in line))
        say(f"  hits at the cut matching nothing planted or already there: {extra[variant]}")
    return record


def pairs(paths, per_config=12, seed=2, methods=("boxcar", "scrunch", "none"), say=print):
    """Two signals planted close together: whether both come out, as two hits."""
    rng = np.random.default_rng(seed)
    configs = []
    for apart in (3, 10, 30, 100, 300):
        configs.append(("equal, 0.05 Hz/s", apart, (0.05, 40), (0.05, 40)))
        configs.append(("equal, 1 Hz/s", apart, (1.0, 80), (1.0, 80)))
        configs.append(("equal, +1 and -1 Hz/s", apart, (1.0, 80), (-1.0, 80)))
    for apart in (10, 30, 100, 300):
        configs.append(("weak (S_in 30, 0.3 Hz/s) beside strong (S_in 600, 0.05 Hz/s)", apart, (0.05, 600), (0.3, 30)))
    tally = {}
    for path in paths:
        s, raw = _load(path)
        n_t, n_f = raw.shape
        width_hz = abs(s["foff"]) * 1e6
        span = (n_t - 1) * s["tsamp"]
        step = width_hz / span
        sigma = channel_noise(raw)
        own = seti.at_cut(searching.search(raw, s["foff"], s["tsamp"], s["fch1"]))
        margin = int(searching.MAX_DRIFT * span / width_hz) + 30
        todo = [c for c in configs for _ in range(per_config // len(paths) or 1)]
        while todo:
            batch, todo = todo[:30], todo[30:]
            where = places(n_f, len(batch), 2 * margin + 400, [h["channel"] for h in own], margin + 500, rng)
            tones, pairs_here = [], []
            for c, (name, apart, (d1, s1), (d2, s2)) in zip(where, batch):
                x1 = c + float(rng.uniform(-0.5, 0.5))
                x2 = x1 + apart
                tones += [(x1, d1, s1 * sigma[c] / math.sqrt(n_t)), (x2, d2, s2 * sigma[c] / math.sqrt(n_t))]
                pairs_here.append((name, apart, x1, d1, x2, d2))
            planted = plant(raw, tones, s["tsamp"], s["foff"])

            def one(method):
                return method, searching.search(planted, s["foff"], s["tsamp"], s["fch1"], method=method)
            with ThreadPoolExecutor(max_workers=len(methods)) as pool:
                results = list(pool.map(one, methods))
            for method, hits in results:
                used = set()
                for name, apart, x1, d1, x2, d2 in pairs_here:
                    a = matched(hits, x1, d1, step, used)
                    b = matched(hits, x2, d2, step, used)
                    cell = tally.setdefault((method, name, apart), {"pairs": 0, "both": 0, "first": 0, "second": 0})
                    cell["pairs"] += 1
                    cell["both"] += bool(a and b)
                    cell["first"] += bool(a)
                    cell["second"] += bool(b)
        say(f"{Path(path).name}: pairs planted")
    rows = [{"method": m, "pair": name, "apart_channels": apart, **cell, "interval_both": wilson(cell["both"], cell["pairs"])}
            for (m, name, apart), cell in sorted(tally.items(), key=lambda kv: (methods.index(kv[0][0]), kv[0][1], kv[0][2]))]
    record = {"files": [str(p) for p in paths], "seed": seed, "rows": rows, "kind": "measured"}
    _keep("pairs", record)
    for m in methods:
        say(f"\n{m}: both found / pairs (first, second found), by channels apart")
        for name in dict.fromkeys(r["pair"] for r in rows):
            line = [r for r in rows if r["method"] == m and r["pair"] == name]
            say(f"  {name}: " + ", ".join(f"{r['apart_channels']}: {r['both']}/{r['pairs']} ({r['first']},{r['second']})"
                                         for r in line))
    return record


def kurtosis(paths, say=print):
    """The share of channels spectral kurtosis flags in each look, against
    what noise alone gives (chi-squared on 15 degrees over 15)."""
    rng = np.random.default_rng(3)
    noise_only = float((rng.chisquare(15, 10_000_000) / 15 > searching.SK_FLAG).mean())
    rows = []
    for path in paths:
        s, raw = _load(path)
        sk = searching.kurtosis(raw)
        rows.append({"file": str(path), "flagged": round(float((sk > searching.SK_FLAG).mean()), 5),
                     "percentiles": {str(q): round(float(np.percentile(sk, q)), 2) for q in (50, 90, 99, 99.9, 99.99)}})
        say(f"{Path(path).name}: {rows[-1]['flagged']:.3%} of channels flagged; percentiles {rows[-1]['percentiles']}")
    say(f"noise alone (chi-squared 15 / 15 > {searching.SK_FLAG:g}): {noise_only:.4%}")
    record = {"threshold": searching.SK_FLAG, "noise_only": noise_only, "rows": rows, "kind": "measured"}
    _keep("kurtosis", record)
    return record


def noise(paths, say=print):
    """The planting's noise estimate (neighbour differences) against the
    search's (band shape taken out, MAD), per look: their ratio's median
    and spread over the band's blocks."""
    rows = []
    for path in paths:
        _, raw = _load(path)
        ratio = channel_noise(raw) / search_noise(raw)
        blocks = ratio[512::1024]
        rows.append({"file": str(path), "median": round(float(np.median(blocks)), 4),
                     "percentiles_5_95": [round(float(np.percentile(blocks, q)), 4) for q in (5, 95)]})
        say(f"{Path(path).name}: planting's noise over the search's {rows[-1]['median']} "
            f"(5th to 95th percentile of blocks {rows[-1]['percentiles_5_95']})")
    medians = [r["median"] for r in rows]
    record = {"rows": rows, "median": round(float(np.median(medians)), 4),
              "range": [round(min(medians), 4), round(max(medians), 4)], "kind": "measured"}
    _keep("noise", record)
    say(f"\nmedian over looks {record['median']}, range {record['range']}")
    return record


def scramble(raw, rng):
    """Each spectrum turned round the band by its own random amount: every
    spectrum keeps its noise and its interference, but no signal lines up
    from one spectrum to the next."""
    out = np.empty_like(raw)
    for t in range(raw.shape[0]):
        out[t] = np.roll(raw[t], int(rng.integers(0, raw.shape[1])))
    return out


def false(paths, repeats=2, seed=4, say=print):
    """Hits at the cut (and shadow hits) in scrambled looks, per look and
    per block of six looks, with their intervals."""
    rng = np.random.default_rng(seed)
    rows = []
    for path in paths:
        s, raw = _load(path)
        for r in range(repeats):
            hits = searching.search(scramble(raw, rng), s["foff"], s["tsamp"], s["fch1"])
            cut = seti.at_cut(hits)
            rows.append({"file": str(path), "repeat": r, "hits_at_cut": len(cut), "shadow": len(hits) - len(cut),
                         "snrs": sorted((h["snr"] for h in cut), reverse=True)[:20]})
            say(f"{Path(path).name} scrambled #{r + 1}: {len(cut)} hit(s) at the cut, {len(hits) - len(cut)} shadow"
                + (f"; SNRs {rows[-1]['snrs']}" if cut else ""))
    looks = len(rows)
    total = sum(r["hits_at_cut"] for r in rows)
    lo, hi = poisson_interval(total)
    per_look = (round(lo / looks, 4), round(hi / looks, 4))
    shadow = sum(r["shadow"] for r in rows)
    record = {"files": [str(p) for p in paths], "repeats": repeats, "looks_searched": looks, "hits_at_cut": total,
              "per_look": round(total / looks, 4), "per_look_interval": per_look,
              "per_block_of_six": round(6 * total / looks, 3), "per_block_interval": (round(6 * per_look[0], 3),
                                                                                     round(6 * per_look[1], 3)),
              "shadow_per_look": round(shadow / looks, 1), "rows": rows, "kind": "measured"}
    _keep("false", record)
    say(f"\n{total} hit(s) at the cut in {looks} scrambled looks: {record['per_block_of_six']} a block of six looks "
        f"(95% interval {record['per_block_interval'][0]} to {record['per_block_interval'][1]}); "
        f"{record['shadow_per_look']} shadow hits a look")
    return record


def scale(paths, count=30, seed=5, say=print):
    """This search's SNR and turboSETI's for the same planted signals
    (slow, |drift| under 0.15 Hz/s, so smearing plays no part), per file."""
    rng = np.random.default_rng(seed)
    rows = []
    for path in paths:
        s, raw = _load(path)
        n_t, n_f = raw.shape
        width_hz = abs(s["foff"]) * 1e6
        span = (n_t - 1) * s["tsamp"]
        step = width_hz / span
        sigma = channel_noise(raw)
        own = seti.at_cut(searching.search(raw, s["foff"], s["tsamp"], s["fch1"]))
        margin = int(searching.MAX_DRIFT * span / width_hz) + 30
        where = places(n_f, count, 2 * margin + 60, [h["channel"] for h in own], margin + 500, rng)
        tones = []
        for c in where:
            # Strong enough that turboSETI, whose SNR runs about a quarter of
            # this search's, finds them too at its cut of 10.
            strength = float(np.exp(rng.uniform(math.log(60), math.log(300))))
            drift = float(rng.uniform(-0.15, 0.15))
            tones.append((float(c), drift, strength * sigma[c] / math.sqrt(n_t), strength))
        planted = plant(raw, [t[:3] for t in tones], s["tsamp"], s["foff"])
        ours = searching.search(planted, s["foff"], s["tsamp"], s["fch1"])
        with tempfile.TemporaryDirectory() as tmp:
            file = seti.save(dict(s, spectra=planted), Path(tmp) / (Path(path).stem + "_planted.h5"))
            started = time.monotonic()
            theirs = seti.turboseti(file)
            turbo_s = round(time.monotonic() - started, 1)
        pairs_found = []
        used = set()
        for x0, drift, h, strength in tones:
            a = matched(ours, x0, drift, step, used)
            f0 = s["fch1"] + x0 * s["foff"]
            b = next((t for t in theirs if abs(t["frequency_mhz"] - f0) * 1e6 <= 3 * width_hz
                      and abs(t["drift_hz_s"] - drift) <= 3 * step), None)
            if a and b:
                pairs_found.append({"s_in": round(strength, 1), "ours": a["snr"], "turboseti": b["snr"],
                                    "ratio": round(b["snr"] / a["snr"], 3)})
        ratios = [p["ratio"] for p in pairs_found]
        row = {"file": str(path), "planted": len(tones), "both_found": len(pairs_found),
               "turboseti_over_ours_median": round(float(np.median(ratios)), 3) if ratios else None,
               "quartiles": [round(float(np.percentile(ratios, q)), 3) for q in (25, 75)] if ratios else None,
               "ours_over_s_in_median": round(float(np.median([p["ours"] / p["s_in"] for p in pairs_found])), 3)
               if pairs_found else None,
               "turboseti_seconds": turbo_s, "signals": pairs_found}
        rows.append(row)
        say(f"{Path(path).name}: {row['both_found']} of {count} found by both; turboSETI's SNR over ours "
            f"{row['turboseti_over_ours_median']} (quartiles {row['quartiles']}); ours over S_in "
            f"{row['ours_over_s_in_median']}; turboSETI took {turbo_s} s")
    medians = [r["turboseti_over_ours_median"] for r in rows if r["turboseti_over_ours_median"]]
    record = {"rows": rows, "median_of_files": round(float(np.median(medians)), 3) if medians else None,
              "spread_of_files": [round(min(medians), 3), round(max(medians), 3)] if medians else None,
              "turboseti": subprocess.run([str(seti.TURBOSETI_PYTHON), "-c",
                                           "import importlib.metadata as m; print(m.version('turbo_seti'))"],
                                          capture_output=True, text=True).stdout.strip(),
              "turboseti_known_bugs": ["#296: top-hit suppression drops hits beside a stronger one",
                                       "#319: level-3 de-duplication in find_event"],
              "turboseti_note": "a reference with known flaws, not the truth; run on Windows from the file's folder "
                                "with pinned dependencies (HANDOVER.md)",
              "kind": "measured"}
    _keep("scale", record)
    say(f"\nturboSETI's SNR over this search's: {record['median_of_files']} at the median of files, "
        f"{record['spread_of_files']} across them")
    return record


CADENCES = None


def cadences():
    """The saved cadences: block 153 (the reference) and blocks 40, 100,
    200 and 280, six looks each, in cadence order."""
    import glob
    import json as _json
    ref = _json.load(open(yoke.DATA / "reference" / "reference.json"))["files"]
    out = [ref]
    for k in sorted({int(Path(p).name[5:8]) for p in glob.glob(str(yoke.DATA / "reference" / "blocks" / "block*.h5"))}):
        out.append([str(yoke.DATA / "reference" / "blocks" / f"block{k:03d}_{scan:04d}.h5") for scan in range(31, 37)])
    return out


def cadence(paths=None, runs=2, n_on=32, n_all=8, seed=6, say=print):
    """Signals planted in whole cadences, in the ON looks only or in all
    six, through the search and the cadence test: how many ON-only signals
    come out as candidates, how many in-all signals as interference, and
    the OFF looks' S/N along ON-only signals' tracks (the false veto)."""
    import injection
    rng = np.random.default_rng(seed)
    groups = cadences() if not paths else [paths[i:i + 6] for i in range(0, len(paths), 6)]
    rows = []
    for files in groups:
        cad = injection.load(files)
        for r in range(runs):
            tones = injection.tones_for(cad, n_on, n_all, rng)
            out, _ = injection.trial(cad, tones)
            for t in out:
                rows.append(dict(t, cadence=Path(files[0]).name))
            say(f"{Path(files[0]).name}: run {r + 1} of {runs}: {sum(t['label'] == 'candidate' for t in out if t['where'] == 'on')}"
                f" of {n_on} ON-only signals candidates, {sum(t['label'] == 'interference' for t in out if t['where'] == 'all')}"
                f" of {n_all} in-all signals interference", flush=True)
    table = []
    for where in ("on", "all"):
        for b, (lo, hi) in enumerate(DRIFT_BINS):
            for st in STRENGTHS:
                cell = [t for t in rows if t["where"] == where and t["bin"] == b and t["s_in"] == st]
                n = len(cell)
                if not n:
                    continue
                want = "candidate" if where == "on" else "interference"
                k = sum(t["label"] == want for t in cell)
                seen = sum(t["found_on_looks"] > 0 for t in cell)
                table.append({"where": where, "drift_hz_s": [lo, hi], "s_in": st, "planted": n,
                              "found_in_a_look": seen, "labelled": want, "count": k, "rate": round(k / n, 3),
                              "interval": wilson(k, n),
                              "of_found": round(k / seen, 3) if seen else None})
    on = [t for t in rows if t["where"] == "on" and t["label"] is not None]
    off_snrs = [t["off_snr_max"] for t in on if t["off_snr_max"] is not None]
    vetoed = [t for t in on if t["label"] == "interference"]
    allr = [t for t in rows if t["where"] == "all" and t["label"] is not None]
    record = {"cadences": [Path(g[0]).name for g in groups], "runs": runs, "seed": seed,
              "off_max": onoff.OFF_MAX, "on_min": onoff.ON_MIN, "table": table,
              "on_only_off_snr_percentiles": {str(q): round(float(np.percentile(off_snrs, q)), 2)
                                              for q in (50, 90, 99, 100)} if off_snrs else None,
              "on_only_vetoed": len(vetoed), "on_only_with_event": len(on),
              "on_only_veto_interval": wilson(len(vetoed), len(on)),
              "all_interference": sum(t["label"] == "interference" for t in allr), "all_with_event": len(allr),
              "all_missed": [{k: t[k] for k in ("s_in", "drift", "label", "off_snr_max")} for t in allr
                             if t["label"] != "interference"],
              "rows": rows, "kind": "measured"}
    _keep("cadence", record)
    say("\nON-only signals labelled candidate, by drift bin and S_in (of those planted; of those found in a look):")
    for b, (lo, hi) in enumerate(DRIFT_BINS):
        line = [t for t in table if t["where"] == "on" and t["drift_hz_s"] == [lo, hi]]
        say(f"  {lo:4.2f}-{hi:4.2f}  " + "  ".join(f"S_in {t['s_in']}: {t['rate']:.0%} ({t['of_found'] if t['of_found'] is not None else '-'})" for t in line))
    say(f"ON-only signals with an event wrongly labelled interference: {len(vetoed)} of {len(on)} "
        f"{record['on_only_veto_interval']}; their OFF S/N percentiles {record['on_only_off_snr_percentiles']}")
    say(f"in-all signals with an event labelled interference: {record['all_interference']} of {len(allr)}")
    return record


KIC8462852 = {"name": "KIC8462852", "ra_hours": 20.104292, "dec_deg": 44.456833}   # 20h06m15.45s +44d27m24.6s


def vet_hook(target=KIC8462852, report_dir=None, prefix="PLANTED"):
    """The checks as injection.trial calls them on a candidate, the cadence's
    own hits standing in for the session's."""
    import vetting

    def hook(event, looks):
        session_hits = [h for lk in looks for h in lk.hits if not h.get("shadow")]
        lead = f"{prefix}-{event['frequency_mhz']:.6f}"
        return vetting.vet(event, looks, target, (), session_hits, report_dir=report_dir, lead=lead)
    return hook


def vetting_demo(seed=7, say=print, which=(0, 2)):
    """Phase 5's test: in the reference cadence, a lone signal in the ON
    looks only, and a family of signals sharing one drift over frequency
    (as harmonics of one oscillator would): four in all six looks, as
    interference, and one more in the ON looks only. The lone one should
    come out unexplained; the family's ON-only member should be caught by
    its look-alikes (check 7) or its relations (check 8)."""
    import injection
    rows, folder = [], yoke.DATA / "measurements" / "vetting"
    for w in which:
        rows += _vetting_one(injection, injection.load(cadences()[w]), np.random.default_rng(seed + w), folder, say)
    record = {"rows": rows, "reports": sorted(str(p) for p in folder.glob("*.md")), "kind": "measured"}
    _keep("vetting", record)
    return record


def _vetting_one(injection, cad, rng, folder, say):
    s = cad[0]["s"]
    n_f = s["spectra"].shape[1]
    f_of = lambda c: s["fch1"] + c * s["foff"]  # noqa: E731
    nu = 0.45 / (f_of(n_f // 2) * 1e6)                        # the family's drift over frequency, 1/s
    family = [int(n_f * q) for q in (0.18, 0.33, 0.62, 0.71, 0.86)]
    lone = int(n_f * 0.45)
    tones = [{"x0": lone + 0.2, "drift": -0.83, "s_in": 80, "bin": 2, "where": "on", "position": "middle",
              "role": "lone"}]
    for k, c in enumerate(family):
        tones.append({"x0": c + float(rng.uniform(-0.5, 0.5)), "drift": nu * f_of(c) * 1e6, "s_in": 60, "bin": 1,
                      "where": "on" if k == 2 else "all", "position": "middle",
                      "role": "family, ON only" if k == 2 else "family, in all"})
    out, events = injection.trial(cad, tones, vet=vet_hook(report_dir=folder))
    rows = []
    say(f"block at {s['fch1']:.3f} MHz:")
    for t in out:
        rows.append({k: t.get(k) for k in ("role", "x0", "drift", "s_in", "where", "found_on_looks", "label",
                                           "off_snr_max", "verdict", "reasons")})
        rows[-1]["block_fch1_mhz"] = s["fch1"]
        say(f"{t['role']:>16}: drift {t['drift']:+.4f} Hz/s, found in {t['found_on_looks']} ON look(s), "
            f"cadence {t['label']}, checks: {t['verdict']}")
    return rows


def setigen_check(say=print):
    """Our planted signals against setigen's (Brzycki et al. 2022) for the
    same tones on an empty frame: tools/setigen_frame.py makes setigen's in
    turboSETI's environment (setigen 2.7 is installed there); here each
    spectrum's profile, centroid and power are compared. setigen's data run
    upward in frequency, Green Bank's downward, so its channels are turned
    round first."""
    import re
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "setigen.npz"
        done = subprocess.run([str(seti.TURBOSETI_PYTHON), "-I", str(yoke.ROOT / "tools" / "setigen_frame.py"),
                               str(out)], capture_output=True, text=True, timeout=600)
        if done.returncode:
            raise yoke.Refusal("INTERNAL_ERROR", f"setigen failed: {done.stderr.strip()[-300:]}")
        frames = dict(np.load(out))
    version = subprocess.run([str(seti.TURBOSETI_PYTHON), "-c",
                              "import importlib.metadata as m; print(m.version('setigen'))"],
                             capture_output=True, text=True).stdout.strip()
    src = (yoke.ROOT / "tools" / "setigen_frame.py").read_text(encoding="utf-8")
    df, dt = (float(x) for x in re.search(r"DF, DT, FCH1 = ([\d.]+), ([\d.]+),", src).groups())
    rows = []
    for key, sg in frames.items():
        c0, drift = (float(x) for x in key.split("_"))
        sg = sg[:, ::-1]
        ours = plant(np.zeros(sg.shape), [(c0, drift, 1.0)], dt, -df / 1e6)
        corr = [float(np.corrcoef(a, b)[0, 1]) for a, b in zip(ours, sg)]
        ch = np.arange(sg.shape[1])
        cen = [float((a * ch).sum() / a.sum() - (b * ch).sum() / b.sum()) for a, b in zip(ours, sg)]
        rows.append({"start_channel": c0, "drift_hz_s": drift, "correlation_min": round(min(corr), 4),
                     "correlation_median": round(float(np.median(corr)), 4),
                     "centroid_offset_channels": [round(min(cen), 3), round(max(cen), 3)],
                     "power_ours_over_setigen": round(float(ours.sum() / sg.sum()), 4),
                     "power_ours_over_h": round(float(ours.sum(axis=1).mean()), 4)})
        say(f"start {c0}, {drift:+} Hz/s: profiles correlate {rows[-1]['correlation_min']} at the least; centroids "
            f"{rows[-1]['centroid_offset_channels']} channels apart; power ours/setigen "
            f"{rows[-1]['power_ours_over_setigen']}, ours/h {rows[-1]['power_ours_over_h']}")
    record = {"setigen": version, "rows": rows, "kind": "measured",
              "note": "setigen's sinc2_f_profile at level 1 carries about 8.5% less power than h; ours carries 0.96 "
                      "to 1.00 of h (the sinc^2 tails beyond 4 channels are dropped): a difference of convention "
                      "in setigen's profile, not of shape."}
    _keep("setigen", record)
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", choices=("desmear", "pairs", "kurtosis", "false", "scale", "noise", "cadence",
                                     "vetting", "setigen"))
    ap.add_argument("files", nargs="*")
    ap.add_argument("--json", action="store_true", help="answer in JSON")
    args = ap.parse_args()
    work = {"desmear": desmear, "pairs": pairs, "kurtosis": kurtosis, "false": false, "scale": scale,
            "noise": noise, "cadence": cadence, "vetting": lambda _files: vetting_demo(),
            "setigen": lambda _files: setigen_check()}[args.what]
    yoke.main("measure", lambda: work(args.files), args.json)


if __name__ == "__main__":
    main()
