"""The narrowband search on one look: the band's shape taken out, every
drift line summed, its SNR measured against the noise of the summed lines
themselves, and the hits picked out one at a time.

A look is 16 spectra of about a million 2.79 Hz channels, 18.25 s apart.
A signal drifting faster than one channel a spectrum (2.79 Hz / 18.25 s, about
0.153 Hz/s) spreads its power, within each spectrum, over every channel it
crosses: about 26 at 4 Hz/s. Summing one channel a spectrum collects a
fraction of that power. Three ways of summing are kept, so that they can
be compared on planted signals:

- "boxcar": each spectrum's contribution is the sum of the N channels the
  line crosses during it, N = ceil(|drift| x tsamp / channel width)
  (hyperseti and BLISS). The noise grows as sqrt(N), the signal as N.
- "scrunch": adjacent channels summed in fixed bins of 2^j for drifts of
  2^j to 2^(j+1) channels a spectrum, searched on that coarser grid
  (Breakthrough Listen's Kepler search), emulated here on the same sums.
- "none": one channel a spectrum, as turboSETI and this search before
  9 November 2026.

The SNR of a line is its sum, less the median of the summed lines, over
their robust spread (1.4826 x the median absolute deviation), both measured
per block of 1024 channels and per box width on the summed output itself,
not assumed from each spectrum's noise. Hits are picked strongest first;
each hit's track is blanked and the lines around it summed again, so a weak
signal beside a strong one is found on its own, and a signal much wider
than its box is recorded once, as wide, with its width.

Spectral kurtosis (the variance over the 16 spectra over the mean squared,
per channel, over its block's median) marks channels whose power comes and
goes. Only the high side is used, and only as a recorded sign: a steady
tone has low kurtosis, and a drifting signal raises it in each channel it
crosses, so a flag is never a verdict.
"""
import math

import numpy as np

SNR_MIN = 10.0          # the cut: a hit at or above it is a hit
SHADOW_MIN = 5.0        # hits from here to the cut are kept, marked shadow: evidence, never candidates
MAX_DRIFT = 4.0         # Hz a second either way
BLOCK = 1024            # channels in each piece of the band's shape, and of the noise of the summed lines
TILE = 131072           # channels summed at a time: a tile's spectra stay in the processor's cache
WINDOW_CHANNELS = 3     # channels either way a hit may sit from where its drift puts it
SK_FLAG = 3.0           # spectral kurtosis above this (1 for noise) flags a channel: 0.02% of a quiet look's
WIDE_LEVEL = 3.0        # a channel is lit in a spectrum when its flattened power is this many times the noise
WIDE_MIN = 8            # a hit lit over more than this many channels, and twice its box, is wide
MAX_HITS = 2000         # hits picked from one look at most (the rest of a crowded look is counted, not kept)
METHODS = ("boxcar", "scrunch", "none")
METHOD = "boxcar"       # chosen 9 November 2026 by planted signals (docs/seti.md)


# --- the band's shape --------------------------------------------------------------

def block_medians(x, block=BLOCK):
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
    levels = block_medians(spectra, block)
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
    # The noise too is measured block by block, one spectrum at a time: near
    # a coarse channel's edges the band rolls off and the noise with it.
    spreads = np.empty((n_t, len(starts)))
    for t in range(n_t):
        row = out[t:t + 1]
        middle = np.repeat(block_medians(row, block), block, axis=1)[:, :n_f]
        spreads[t] = 1.4826 * block_medians(np.abs(row - middle), block)[0]
    for t in range(n_t):
        spread = spreads[t]
        spread[spread <= 0] = np.median(spread[spread > 0]) if (spread > 0).any() else 1.0
        out[t] /= np.interp(every, centres, spread) if len(spread) > 1 else spread[0]
    return (out, {"spreads": spreads, "centres": centres}) if details else out


def kurtosis(spectra, block=BLOCK):
    """Each channel's spectral kurtosis over the look: the variance of its
    power over the spectra over its mean squared, over the median of that
    in its block (so 1 for noise; about chi-squared on 15 degrees over 15
    for 16 spectra, whose 99.99th percentile is 2.84)."""
    mean = spectra.mean(axis=0)
    v = spectra.var(axis=0, ddof=1) / np.where(mean != 0, mean * mean, np.inf)
    norm = block_medians(v[None, :], block)[0]
    norm[norm <= 0] = np.median(norm[norm > 0]) if (norm > 0).any() else 1.0
    return v / np.repeat(norm, block)[:len(v)]


# --- every drift line, summed and measured ---------------------------------------

class Plane:
    """The drift lines of one look, set up for summing: the flattened
    spectra padded either side, the drift steps, and for each drift its
    box width and the grid it is searched on."""

    def __init__(self, flat, tsamp, foff, max_drift=MAX_DRIFT, method=METHOD, flags=None):
        if method not in METHODS:
            raise ValueError(method)
        self.n_t, self.n_f = flat.shape
        self.method, self.tsamp, self.foff = method, tsamp, foff
        self.width_hz = abs(foff) * 1e6
        self.span = max(self.n_t - 1, 1) * tsamp
        self.most = int(max_drift * self.span / self.width_hz) if self.n_t > 1 else 0
        self.steps = np.arange(self.n_t) / max(self.n_t - 1, 1)
        ks = range(-self.most, self.most + 1)
        self.width = {k: self._width(k) for k in ks}
        self.ks = [k for k in ks if method != "scrunch" or k % self.width[k] == 0]
        self.wmax = max(self.width.values())
        self.margin = self.most + self.wmax
        self.n_pad = -(-self.n_f // BLOCK) * BLOCK
        self.padded = np.zeros((self.n_t, self.n_pad + 2 * self.margin + self.wmax), np.float32)
        self.padded[:, self.margin:self.margin + self.n_f] = flat
        self.shifts = {k: [int(round(k * s)) for s in self.steps] for k in ks}
        self.flags = flags
        self.norm = {}             # (width, zero drift or not) -> (median, spread) per block of the band
        self.ratio = {}            # width -> the spread over sqrt(spectra x width), median over blocks

    def _width(self, k):
        d = abs(k) / max(self.n_t - 1, 1)          # channels crossed in one spectrum
        if self.method == "none" or d <= 1:
            return 1
        if self.method == "boxcar":
            return math.ceil(d - 1e-9)
        return 1 << int(math.floor(math.log2(d)))  # scrunch: 2^j for d in [2^j, 2^(j+1))

    def _group(self, k):
        return (self.width[k], k == 0)

    def _sample(self, group):
        """The drift whose summed lines give a group's noise."""
        w, zero = group
        if zero:
            return 0
        if w == 1:
            return min(8, self.most)
        return min(k for k in self.ks if k > 0 and self.width[k] == w)

    def _sum(self, k, lo, hi, box, out):
        """The line sums starting at channels [lo, hi) for drift k, from
        `box` (this drift's box width, for the region lo - margin on)."""
        back = self.width[k] - 1 if k < 0 else 0
        out[:] = 0
        n = hi - lo
        for t, s in enumerate(self.shifts[k]):
            a = self.margin + s - back
            out += box[t, a:a + n]
        return out

    def _measure(self, group, lo, hi, box, total):
        """The summed lines' median and spread, per block, for one group of
        drifts, on channels [lo, hi); flagged channels left out of both."""
        nb = (hi - lo) // BLOCK
        self._sum(self._sample(group), lo, hi, box, total)
        rows = total.reshape(nb, BLOCK).astype(np.float64)
        holes = np.zeros(hi - lo, bool)
        if hi > self.n_f:
            holes[self.n_f - lo:] = True
        if self.flags is not None:
            f = self.flags[lo:min(hi, self.n_f)]
            holes[:len(f)] |= f
        bad = holes.reshape(nb, BLOCK).any(axis=1)
        if bad.any():
            rows.reshape(-1)[holes] = np.nan
        med = np.zeros(nb)
        spread = np.zeros(nb)
        if (~bad).any():
            good = rows[~bad]
            med[~bad] = np.median(good, axis=1)
            spread[~bad] = 1.4826 * np.median(np.abs(good - med[~bad][:, None]), axis=1)
        if bad.any():
            part = rows[bad]
            with np.errstate(all="ignore"), __import__("warnings").catch_warnings():
                __import__("warnings").simplefilter("ignore")
                m = np.nanmedian(part, axis=1)
                med[bad] = m
                spread[bad] = 1.4826 * np.nanmedian(np.abs(part - m[:, None]), axis=1)
        spread[~np.isfinite(spread) | (spread <= 0)] = math.sqrt(self.n_t * group[0])
        med[~np.isfinite(med)] = 0.0
        if group not in self.norm:
            n = self.n_pad // BLOCK
            self.norm[group] = (np.zeros(n, np.float32), np.ones(n, np.float32))
        self.norm[group][0][lo // BLOCK:hi // BLOCK] = med
        self.norm[group][1][lo // BLOCK:hi // BLOCK] = spread

    def search(self, lo=0, hi=None, measure=True):
        """The best SNR and its drift for each line start in [lo, hi). The
        full pass (`measure`) goes a tile at a time and measures each tile's
        noise of the summed lines first; a re-sum of a blanked region (not
        `measure`) uses the noise measured then."""
        hi = self.n_pad if hi is None else hi
        if measure:
            tiles = [(a, min(a + TILE, self.n_pad)) for a in range(0, self.n_pad, TILE)]
        else:
            tiles = [((lo // BLOCK) * BLOCK, min(self.n_pad, -(-hi // BLOCK) * BLOCK))]
        best = np.full(hi - lo, -np.inf, np.float32)
        best_k = np.zeros(hi - lo, np.int32)
        by_width = {}
        for k in self.ks:
            by_width.setdefault(self.width[k], []).append(k)
        for a, b in tiles:
            n = b - a
            region = n + 2 * self.margin
            src = self.padded[:, a:a + region + self.wmax]
            box = src[:, :region].copy()
            total = np.empty(n, np.float32)
            nb = n // BLOCK
            cut_lo, cut_hi = max(lo, a), min(hi, b)
            for w in range(1, self.wmax + 1):
                if w > 1:
                    box += src[:, w - 1:w - 1 + region]       # box[t, j]: w channels from a - margin + j
                if w not in by_width:
                    continue
                if measure:
                    for group in sorted({self._group(k) for k in by_width[w]}):
                        self._measure(group, a, b, box, total)
                keep = None
                if self.method == "scrunch" and w > 1:
                    keep = np.zeros(n, bool)
                    keep[(-a) % w::w] = True
                for k in by_width[w]:
                    med, spread = self.norm[self._group(k)]
                    snr = self._sum(k, a, b, box, total).reshape(nb, BLOCK)
                    snr -= med[a // BLOCK:b // BLOCK, None]
                    snr /= spread[a // BLOCK:b // BLOCK, None]
                    snr = snr.reshape(-1)
                    if keep is not None:
                        snr[~keep] = -np.inf
                    part = snr[cut_lo - a:cut_hi - a]
                    tb, tk = best[cut_lo - lo:cut_hi - lo], best_k[cut_lo - lo:cut_hi - lo]
                    better = part > tb
                    np.copyto(tk, k, where=better)
                    np.maximum(tb, part, out=tb)
        if measure:
            for (w, zero), (_, spread) in self.norm.items():
                if not zero:
                    used = spread[:-(-self.n_f // BLOCK)]
                    self.ratio[w] = float(np.median(used)) / math.sqrt(self.n_t * w)
        return best, best_k

    def spread_at(self, k, channel):
        return float(self.norm[self._group(k)][1][channel // BLOCK])

    def blank(self, channel, k, width):
        """The track's pixels set to zero (the flattened noise's level)."""
        w = self.width[k]
        back = w - 1 if k < 0 else 0
        for t, s in enumerate(self.shifts[k]):
            a = self.margin + channel + s - back
            self.padded[t, max(a - width, 0):a + w + width] = 0.0

    def lit(self, channel, k, reach=50000):
        """The channels lit around the track in each spectrum: (first, last)
        channel of the run of lit channels the track is in, or None where
        the track is not lit."""
        w = self.width[k]
        back = w - 1 if k < 0 else 0
        out = []
        for t, s in enumerate(self.shifts[k]):
            a = self.margin + channel + s - back
            lo_win, hi_win = max(0, a - reach), min(self.padded.shape[1], a + w + reach)
            on = self.padded[t, lo_win:hi_win] > WIDE_LEVEL
            here = np.flatnonzero(on[a - lo_win:a - lo_win + w])
            if not len(here):
                out.append(None)
                continue
            first = a - lo_win + int(here[0])
            last = a - lo_win + int(here[-1])
            dark_before = np.flatnonzero(~on[:first])
            dark_after = np.flatnonzero(~on[last + 1:])
            lo = (int(dark_before[-1]) + 1) if len(dark_before) else 0
            hi = (last + int(dark_after[0])) if len(dark_after) else len(on) - 1
            out.append((lo + lo_win - self.margin, hi + lo_win - self.margin))
        return out


def search(spectra, foff, tsamp, fch1, snr_min=SNR_MIN, shadow_min=SHADOW_MIN, max_drift=MAX_DRIFT,
           method=METHOD, sk=True, max_hits=MAX_HITS, details=None):
    """The hits in one look, strongest first, each picked, recorded and its
    track blanked before the lines around it are summed again. A hit's
    frequency is where it was at the start of the look; hits from
    shadow_min to snr_min are kept as shadow hits. `details` (a dict), if
    given, is filled with the noise of the summed lines against
    sqrt(spectra x box) by box width, the kurtosis flags and counts."""
    n_t, n_f = spectra.shape
    flags = kurtosis(spectra) > SK_FLAG if sk else None
    flat, noise = flatten(spectra, details=True)
    plane = Plane(flat, tsamp, foff, max_drift, method, flags)
    if details is not None:
        # The flattened spectra before any blanking: the cadence test
        # measures tracks in them (float32, 67 MB a look).
        details["flat"] = flat.astype(np.float32)
    del flat
    best, best_k = plane.search()
    best = best[:n_f]
    best_k = best_k[:n_f]
    # The slice's ends: a line starting there runs off the slice.
    edge = plane.most + plane.wmax + WINDOW_CHANNELS
    best[:edge] = -np.inf
    best[n_f - edge:] = -np.inf
    span, width_hz = plane.span, plane.width_hz
    step_hz_s = width_hz / span if span else 0.0
    hits, crowded = [], 0
    while True:
        i = int(np.argmax(best))
        snr = float(best[i])
        if not np.isfinite(snr) or snr < shadow_min:
            break
        if len(hits) >= max_hits:
            crowded = int((best >= shadow_min).sum())
            break
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
        # Blank what was found, and sum the lines near it again.
        if wide:
            for t, x in enumerate(lit):
                if x:
                    plane.padded[t, plane.margin + x[0]:plane.margin + x[1] + 1] = 0.0
            lo = min(x[0] for x in lit if x)
            hi = max(x[1] for x in lit if x) + 1
        else:
            plane.blank(i, k, 1)
            lo, hi = i - w - 1, i + w + 2
        if snr >= snr_min or wide:
            a = max(0, lo - plane.margin)
            b = min(n_f, hi + plane.margin)
            new, new_k = plane.search(a, b, measure=False)
            new[:max(0, edge - a)] = -np.inf
            if b > n_f - edge:
                new[max(0, n_f - edge - a):] = -np.inf
            best[a:b], best_k[a:b] = new[:b - a], new_k[:b - a]
        best[max(0, i - w - 1):i + w + 2] = -np.inf
    if details is not None:
        # `unpicked`: line starts still at or over shadow_min when max_hits
        # was reached. A look with any is not a complete list of its hits,
        # and nothing later may treat it as one.
        details.update(noise_ratio={str(w): round(r, 3) for w, r in sorted(plane.ratio.items())},
                       flagged_channels=int(flags.sum()) if flags is not None else None,
                       unpicked=crowded, complete=crowded == 0, method=method)
    return hits
