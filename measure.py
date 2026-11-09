#!/usr/bin/env python3
"""How well the search does on real noise: signals planted as the sky makes
them, close pairs, spectral kurtosis, false hits, and the SNR scale
against turboSETI's. Each answer is kept in data/measurements/.

    ./measure.py desmear FILE...    planted drifting signals through each way of summing
    ./measure.py pairs FILE...      two signals close together: two hits, or one?
    ./measure.py kurtosis FILE...   how many quiet channels spectral kurtosis flags
    ./measure.py false FILE...      hits at the cut in scrambled looks, where no signal can line up
    ./measure.py scale FILE...      this search's SNR against turboSETI's for the same planted signals

FILE is a slice saved by `seti.py search --keep` (data/reference/ has six
looks of block 153 and data/reference/blocks/ four more blocks).

A planted signal is made as the sky makes one: a tone moving at its drift
through each 18 s spectrum, its power spread over every channel it crosses
(32 steps a spectrum) with the sinc-squared response of an FFT channel, at a
random place within a channel. Its strength is set from the raw spectra
alone, not from the search: S_in = h x sqrt(16) / sigma, where h is the
power the tone adds to a spectrum and sigma one channel's noise in one
spectrum there (1.4826 x the median absolute deviation). S_in is the SNR a
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


def channel_noise(raw):
    """One channel's noise in one spectrum, by channel (raw units): the
    median over spectra of each block's 1.4826 x MAD."""
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
              "kind": "measured"}
    _keep("scale", record)
    say(f"\nturboSETI's SNR over this search's: {record['median_of_files']} at the median of files, "
        f"{record['spread_of_files']} across them")
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", choices=("desmear", "pairs", "kurtosis", "false", "scale"))
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", action="store_true", help="answer in JSON")
    args = ap.parse_args()
    work = {"desmear": desmear, "pairs": pairs, "kurtosis": kurtosis, "false": false, "scale": scale}[args.what]
    yoke.main("measure", lambda: work(args.files), args.json)


if __name__ == "__main__":
    main()
