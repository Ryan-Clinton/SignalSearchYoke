"""searching.search with switches, for the detector-completeness audit
(docs/audits.md 6): a diagnostic copy, never used to make a published
result. With every switch at its default it gives exactly what
searching.search gives (tests/test_search_variants.py checks it), so a
difference between the two runs is the switch's alone.

- corridor (default True): after each pick, searching.search excludes the
  line starts within the pick's box of its channel from being picked again,
  whatever their drift; False excludes only the picked start itself.
- refresh_shadow (default False): searching.search sums the lines near a
  pick again only after a hit at the cut (or a wide one); a shadow hit's
  track is blanked but the scores around it are not summed again. True sums
  them again after every pick.
- region (default None): (channels, cap): instead of one cap for the whole
  slice, each region of that many channels may hold at most `cap` hits; a
  full region stops being picked from, the rest go on.
"""
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from searching import (MAX_DRIFT, MAX_HITS, METHOD, SHADOW_MIN, SK_FLAG, SNR_MIN, WIDE_MIN,  # noqa: E402
                       WINDOW_CHANNELS, Plane, flatten, kurtosis)


def search_variant(spectra, foff, tsamp, fch1, snr_min=SNR_MIN, shadow_min=SHADOW_MIN, max_drift=MAX_DRIFT,
                   method=METHOD, sk=True, max_hits=MAX_HITS, details=None, corridor=True, refresh_shadow=False,
                   region=None):
    n_t, n_f = spectra.shape
    flags = kurtosis(spectra) > SK_FLAG if sk else None
    flat, noise = flatten(spectra, details=True)
    plane = Plane(flat, tsamp, foff, max_drift, method, flags)
    if details is not None:
        details["flat"] = flat.astype(np.float32)
    del flat
    best, best_k = plane.search()
    best = best[:n_f]
    best_k = best_k[:n_f]
    edge = plane.most + plane.wmax + WINDOW_CHANNELS
    best[:edge] = -np.inf
    best[n_f - edge:] = -np.inf
    span, width_hz = plane.span, plane.width_hz
    step_hz_s = width_hz / span if span else 0.0
    hits, crowded = [], 0
    per_region = {}
    region_full = []
    while True:
        i = int(np.argmax(best))
        snr = float(best[i])
        if not np.isfinite(snr) or snr < shadow_min:
            break
        if region is None and len(hits) >= max_hits:
            crowded = int((best >= shadow_min).sum())
            break
        if region is not None:
            rg = i // region[0]
            if per_region.get(rg, 0) >= region[1]:
                lo_r, hi_r = rg * region[0], min(n_f, (rg + 1) * region[0])
                crowded += int((best[lo_r:hi_r] >= shadow_min).sum())
                best[lo_r:hi_r] = -np.inf
                region_full.append(rg)
                continue
            per_region[rg] = per_region.get(rg, 0) + 1
        k = int(best_k[i])
        w = plane.width[k]
        lit = plane.lit(i, k)
        spans = [b - a + 1 for a, b in (x for x in lit if x)]
        across = int(np.median(spans)) if spans else w
        wide = across > max(WIDE_MIN, 2 * w)
        drift = float(k * foff * 1e6 / span) if span else 0.0
        f0 = fch1 + i * foff
        sigma = float(np.median([np.interp(i, noise["centres"], row) for row in noise["spreads"]]))
        s_sum = plane.spread_at(k, i)
        track_flags = None
        if flags is not None:
            back = w - 1 if k < 0 else 0
            cells = [flags[max(0, min(n_f - 1, c))] for t, s in enumerate(plane.shifts[k])
                     for c in range(i + s - back, i + s - back + w)]
            track_flags = float(np.mean(cells)) if cells else None
        hits.append({"channel": i, "frequency_mhz": round(f0, 6), "drift_hz_s": round(drift, 4),
                     "snr": round(snr, 1), "width_channels": across, "box_channels": w, "wide": bool(wide),
                     "shadow": snr < snr_min,
                     "end_frequency_mhz": round(f0 + drift * span / 1e6, 6),
                     "drift_error_hz_s": round(step_hz_s / 2, 4),
                     "drift_norm": drift / (f0 * 1e6) if f0 else None,
                     "noise": sigma, "power": snr * s_sum * sigma,
                     "noise_factor": round(s_sum / math.sqrt(n_t * w), 3),
                     "smear": round(abs(drift) * tsamp / width_hz, 3) if width_hz else None,
                     "flagged_fraction": track_flags})
        if wide:
            for t, x in enumerate(lit):
                if x:
                    plane.padded[t, plane.margin + x[0]:plane.margin + x[1] + 1] = 0.0
            lo = min(x[0] for x in lit if x)
            hi = max(x[1] for x in lit if x) + 1
        else:
            plane.blank(i, k, 1)
            lo, hi = i - w - 1, i + w + 2
        if snr >= snr_min or wide or refresh_shadow:
            a = max(0, lo - plane.margin)
            b = min(n_f, hi + plane.margin)
            new, new_k = plane.search(a, b, measure=False)
            new[:max(0, edge - a)] = -np.inf
            if b > n_f - edge:
                new[max(0, n_f - edge - a):] = -np.inf
            best[a:b], best_k[a:b] = new[:b - a], new_k[:b - a]
        if corridor:
            best[max(0, i - w - 1):i + w + 2] = -np.inf
        else:
            best[i] = -np.inf
    if details is not None:
        details.update(noise_ratio={str(w): round(r, 3) for w, r in sorted(plane.ratio.items())},
                       flagged_channels=int(flags.sum()) if flags is not None else None,
                       unpicked=crowded, complete=crowded == 0, method=method,
                       regions_full=sorted(set(region_full)))
    return hits
