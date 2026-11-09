"""The ON-OFF cadence test on six looks' hits: which signals come only from
the target.

A cadence is six five-minute looks: ON, OFF, ON, OFF, ON, OFF. A signal
from the target is in the ON looks only, where its drift puts it;
interference is wherever the telescope points. How it is decided:

1. **Every ON look's hits at the cut are seeds**, so a signal that starts in
   the second ON look is still followed.
2. **Hits are matched by one distance.** A hit is projected to the other
   look's start along its drift; the frequency difference, in channels, is
   divided by its tolerance (3 channels, plus half each hit's box, plus the
   drift's own error, half a drift step or 2% of the drift, whichever is
   more, times the time between); the
   drift difference, in drift steps, by its tolerance (2 steps, plus 5% of
   the drift, from the drift errors of planted signals); the distance is
   the root of the sum of their squares, and two hits match at 1 or less.
   Matching is one-to-one, closest first, at most one hit a look in an
   event, so a strong signal cannot claim two partners; and complete:
   two groups join only when every hit of one matches every hit of the
   other, so no chain of near matches (A to B, B to C, A not to C) makes
   one event.
3. **Every look is measured along the event's track,** found or not: the
   S/N of the summed line, against the same sums 60 to 1,900 channels to
   either side, at the projected place and within the matching tolerance
   of it, the best kept. This is the drift measured in each ON look, and
   the power in each OFF look with no threshold.
4. **The OFF test below the threshold:** an OFF look with an S/N along the
   track of OFF_MAX or more, or a hit of any strength (shadow hits
   included) within the matching distance, makes the event interference.
   The OFF track is measured both where the signal's drift would put it
   and where it started (a transmitter fixed in frequency).
5. **The stamps:** a cut of each look around the track, straightened along
   the drift; the largest normalised dot product of an ON stamp with the
   OFF look after it (ATA's DOT score) is recorded as a sign, not a verdict.

A candidate: no OFF evidence, at least one ON look with a hit at the cut,
and every ON look with a hit at the cut or an S/N along the track of
ON_MIN or more. Interference: any OFF evidence. Unconfirmed: the rest.
"""
import math

import numpy as np

# An OFF look this bright along the track makes interference. Set from
# planted signals (9 Nov 2026): the best S/N of noise within the matching
# window reached 5 for 2.7% of signals planted in the ON looks only, 6 for
# 0.5%; planted interference was 11.6 or more. Fainter interference in an
# OFF look is still caught by any hit there, shadow hits (from SNR 5) too.
OFF_MAX = 6.0
ON_MIN = 5.0            # an ON look with no hit must be this bright along the track for a candidate
NULL_TRACKS = 32        # random tracks a cadence on which the OFF test's veto rate is measured
MAX_DRIFT_NULL = 4.0    # Hz/s: the random tracks' drifts, as the search's
REF_OFFSETS = np.concatenate([-np.arange(60, 1960, 60), np.arange(60, 1960, 60)])   # 64 reference lines a side pair
STAMP_HALF = 16         # channels either side of the track in a stamp
DRIFT_FLAG_STEPS = 2    # ON looks' drifts further apart than this are flagged (Ma et al.)
DRIFT_ERROR = 0.02      # a hit's drift error, as a share of its drift, for projecting it to another look


class Look:
    """One look as the cadence test needs it: its hits, its start (MJD),
    its channels, its spectra flattened, and its place in the cadence."""

    def __init__(self, hits, tstart, fch1, foff, tsamp, flat, position):
        self.hits, self.tstart, self.fch1, self.foff, self.tsamp = hits, tstart, fch1, foff, tsamp
        self.flat, self.position = flat, position
        self.n_t, self.n_f = flat.shape
        self.width_hz = abs(foff) * 1e6
        self.span = max(self.n_t - 1, 1) * tsamp
        self.step = self.width_hz / self.span          # Hz/s: one drift step
        self.on = position % 2 == 0

    def channel(self, f_mhz):
        return (f_mhz - self.fch1) / self.foff

    def k(self, drift):
        """The drift as channels across the look (the search's k)."""
        return drift * self.span / (self.foff * 1e6)

    def box(self, k):
        d = abs(k) / max(self.n_t - 1, 1)
        return 1 if d <= 1 else math.ceil(d - 1e-9)

    def sums(self, start, k, offsets):
        """The summed line (box included) from channel `start` + each offset."""
        w = self.box(k)
        back = w - 1 if k < 0 else 0
        out = np.zeros(len(offsets))
        steps = np.arange(self.n_t) / max(self.n_t - 1, 1)
        cols = np.arange(w)
        for t in range(self.n_t):
            pos = start + int(round(k * steps[t])) - back + offsets
            idx = pos[:, None] + cols[None, :]
            ok = (idx >= 0) & (idx < self.n_f)
            vals = np.where(ok, self.flat[t, np.clip(idx, 0, self.n_f - 1)], np.nan)
            out += vals.sum(axis=1)
        return out

    def track_snr(self, start, k):
        """The S/N of the line from channel `start` at drift k, against the
        same line at REF_OFFSETS channels to either side."""
        offsets = np.concatenate([[0], REF_OFFSETS])
        s = self.sums(int(round(start)), k, offsets)
        ref = s[1:][np.isfinite(s[1:])]
        if len(ref) < 16 or not np.isfinite(s[0]):
            return None
        med = np.median(ref)
        spread = 1.4826 * np.median(np.abs(ref - med))
        return float((s[0] - med) / spread) if spread > 0 else None

    def best_track(self, start, drift, f_tol, d_tol):
        """The best S/N within the tolerances around a projected track:
        (S/N, its start channel, its drift Hz/s). The reference lines are
        the same for every place tried: REF_OFFSETS from the projection."""
        best = (None, None, None)
        start = int(round(start))
        k0 = int(round(self.k(drift)))
        dk = max(1, int(round(d_tol)))
        reach = int(math.ceil(f_tol))
        tries = np.arange(-reach, reach + 1)
        offsets = np.concatenate([tries, REF_OFFSETS])
        for k in range(k0 - dk, k0 + dk + 1):
            s = self.sums(start, k, offsets)
            ref = s[len(tries):]
            ref = ref[np.isfinite(ref)]
            if len(ref) < 16:
                continue
            med = np.median(ref)
            spread = 1.4826 * np.median(np.abs(ref - med))
            if spread <= 0:
                continue
            snr = (s[:len(tries)] - med) / spread
            if not np.isfinite(snr).any():
                continue
            j = int(np.nanargmax(snr))
            if best[0] is None or snr[j] > best[0]:
                best = (float(snr[j]), start + int(tries[j]), k * self.foff * 1e6 / self.span)
        return best

    def stamp(self, start, k):
        """The look's cut around the track, straightened: (spectra, channels)."""
        steps = np.arange(self.n_t) / max(self.n_t - 1, 1)
        out = np.zeros((self.n_t, 2 * STAMP_HALF + 1), np.float32)
        for t in range(self.n_t):
            c = int(round(start + k * steps[t]))
            lo, hi = c - STAMP_HALF, c + STAMP_HALF + 1
            a, b = max(lo, 0), min(hi, self.n_f)
            if a < b:
                out[t, a - lo:b - lo] = self.flat[t, a:b]
        return out


def _tolerance(a, b, la, lb, dt):
    """The frequency tolerance in channels and the drift tolerance in steps
    for matching hit a (look la) to hit b (look lb), dt seconds apart."""
    # The drift's error carries the projection off: half a step, or 2% of a
    # fast (boxed) drift, whichever is more, times the time between.
    drift_error = max(la.step / 2, DRIFT_ERROR * abs(a["drift_hz_s"]))
    f_tol = 3 + (a.get("box_channels", 1) + b.get("box_channels", 1)) / 2 + abs(dt) * drift_error / la.width_hz
    d_tol = 2 + 0.05 * abs(a["drift_hz_s"]) / la.step
    return f_tol, d_tol


def distance(a, b, la, lb, fixed=False):
    """The matching distance of hit a in look la to hit b in look lb; with
    `fixed`, b is looked for where a started (a transmitter that does not
    move in frequency between looks)."""
    dt = (lb.tstart - la.tstart) * 86400
    predicted = a["frequency_mhz"] + (0 if fixed else a["drift_hz_s"] * dt / 1e6)
    f_tol, d_tol = _tolerance(a, b, la, lb, dt)
    df = abs(b["frequency_mhz"] - predicted) * 1e6 / la.width_hz
    dd = abs(b["drift_hz_s"] - a["drift_hz_s"]) / la.step
    return math.hypot(df / f_tol, dd / d_tol)


def _events(looks):
    """ON hits at the cut grouped into events, one-to-one, closest first:
    each event a dict {position: hit index}."""
    seeds = [(lk.position, i) for lk in looks if lk.on for i, h in enumerate(lk.hits) if not h.get("shadow")]
    pairs = []
    for x, (pa, ia) in enumerate(seeds):
        for pb, ib in seeds[x + 1:]:
            if pa == pb:
                continue
            d = distance(looks[pa].hits[ia], looks[pb].hits[ib], looks[pa], looks[pb])
            if d <= 1:
                pairs.append((d, (pa, ia), (pb, ib)))
    pairs.sort(key=lambda p: p[0])
    close = {frozenset((a, b)) for _, a, b in pairs}
    group = {s: {s[0]: s[1]} for s in seeds}          # each seed starts as its own event
    owner = {s: s for s in seeds}
    for d, a, b in pairs:
        ga, gb = owner[a], owner[b]
        if ga == gb:
            continue
        A, B = group[ga], group[gb]
        if set(A) & set(B):                            # one hit a look in an event
            continue
        if any(frozenset(((pa, ia), (pb, ib))) not in close for pa, ia in A.items() for pb, ib in B.items()):
            continue                                   # every member matches every other, no chains
        A.update(B)
        for pos, i in B.items():
            owner[(pos, i)] = ga
        del group[gb]
    return list(group.values())


def null_off(looks, n=NULL_TRACKS, seed=0):
    """The OFF test on tracks where no signal was put: n random starts in
    the first ON look (clear of the slice's ends) at random drifts, each
    measured in the OFF looks as judge measures an event's (projected and
    fixed, over the matching window, and any hit within the distance).
    The share vetoed is how often a real signal at a random place would be
    called interference by the noise and interference already there:
    {tracks, vetoed, over_off_max, with_hit, off_snr_max: [...]}."""
    rng = np.random.default_rng(seed)
    l0 = looks[0]
    margin = int(REF_OFFSETS.max()) + 4 * l0.n_t + 64
    if l0.n_f <= 2 * margin:
        return {"tracks": 0, "vetoed": 0, "over_off_max": 0, "with_hit": 0, "off_snr_max": []}
    out = {"tracks": n, "vetoed": 0, "over_off_max": 0, "with_hit": 0, "off_snr_max": []}
    for _ in range(n):
        c = int(rng.integers(margin, l0.n_f - margin))
        drift = float(rng.uniform(-MAX_DRIFT_NULL, MAX_DRIFT_NULL))
        k = abs(drift) / l0.step
        top = {"frequency_mhz": l0.fch1 + c * l0.foff, "drift_hz_s": drift, "snr": 0.0,
               "box_channels": max(1, math.ceil(k / max(l0.n_t - 1, 1)))}
        best, hit = -np.inf, False
        for lk in looks:
            if lk.on:
                continue
            dt = (lk.tstart - l0.tstart) * 86400
            f_tol, d_tol = _tolerance(top, top, l0, lk, dt)
            s1, _, _ = lk.best_track(lk.channel(top["frequency_mhz"] + drift * dt / 1e6), drift, f_tol, d_tol)
            s2, _, _ = lk.best_track(lk.channel(top["frequency_mhz"]), drift, f_tol, d_tol)
            best = max([best] + [x for x in (s1, s2) if x is not None])
            hit = hit or any(min(distance(top, h, l0, lk), distance(top, h, l0, lk, fixed=True)) <= 1
                             for h in lk.hits)
        over = bool(best >= OFF_MAX)
        out["over_off_max"] += over
        out["with_hit"] += hit
        out["vetoed"] += over or hit
        out["off_snr_max"].append(round(float(best), 2) if np.isfinite(best) else None)
    return out


def judge(looks):
    """The six looks judged together: a list of events, each with its label,
    its matched hit in each look (index into that look's hits, or None),
    and what each look showed along its track."""
    events = []
    for members in _events(looks):
        top_pos, top_i = max(members.items(), key=lambda m: looks[m[0]].hits[m[1]]["snr"])
        top, ltop = looks[top_pos].hits[top_i], looks[top_pos]
        drift = top["drift_hz_s"]
        per_look, matches = [], [None] * len(looks)
        off_snr, on_snrs, drifts, stamps = [], [], [], []
        for lk in looks:
            dt = (lk.tstart - ltop.tstart) * 86400
            f_here = top["frequency_mhz"] + drift * dt / 1e6
            start = lk.channel(f_here)
            f_tol, d_tol = _tolerance(top, top, ltop, lk, dt)
            entry = {"position": lk.position, "on": lk.on}
            if lk.position in members:
                h = lk.hits[members[lk.position]]
                matches[lk.position] = members[lk.position]
                entry.update(found=True, snr=h["snr"], drift_hz_s=h["drift_hz_s"])
                snr, at, d_fit = lk.best_track(lk.channel(h["frequency_mhz"]), h["drift_hz_s"], 1, 1)
                entry["track_snr"] = snr
                drifts.append(h["drift_hz_s"])
            else:
                snr, at, d_fit = lk.best_track(start, drift, f_tol, d_tol)
                entry.update(found=False, track_snr=None if snr is None else round(snr, 2),
                             track_drift_hz_s=None if d_fit is None else round(d_fit, 4))
                if not lk.on:
                    # Also where it started: a transmitter fixed in frequency.
                    s2, _, _ = lk.best_track(lk.channel(top["frequency_mhz"]), drift, f_tol, d_tol)
                    entry["track_snr_fixed"] = None if s2 is None else round(s2, 2)
                    snr = max(x for x in (snr, s2, -np.inf) if x is not None)
                    # Any hit of any strength near either projection.
                    near = [i for i, h in enumerate(lk.hits)
                            if min(distance(top, h, ltop, lk), distance(top, h, ltop, lk, fixed=True)) <= 1]
                    if near:
                        best = max(near, key=lambda i: lk.hits[i]["snr"])
                        matches[lk.position] = best
                        entry.update(hit_snr=lk.hits[best]["snr"], hit_shadow=bool(lk.hits[best].get("shadow")))
                elif d_fit is not None and snr is not None and snr >= ON_MIN:
                    drifts.append(d_fit)
            if lk.on:
                on_snrs.append(entry["snr"] if entry.get("found") else (entry.get("track_snr") or -np.inf))
            else:
                off_snr.append(snr if snr is not None else -np.inf)
                entry["off_evidence"] = bool((snr is not None and snr >= OFF_MAX) or entry.get("hit_snr"))
            stamps.append(lk.stamp(start, lk.k(drift)))
            per_look.append(entry)
        for e in per_look:
            e["seen"] = (bool(e.get("found") or (e.get("track_snr") or -np.inf) >= ON_MIN) if e["on"]
                         else e["off_evidence"])
        off_evidence = any(e.get("off_evidence") for e in per_look if not e["on"])
        on_ok = all(e.get("found") or (e.get("track_snr") or -np.inf) >= ON_MIN for e in per_look if e["on"])
        label = "interference" if off_evidence else "candidate" if on_ok else "unconfirmed"
        step = ltop.step
        spread = (max(drifts) - min(drifts)) / step if len(drifts) > 1 else 0.0
        dot = []
        for p in (0, 2, 4):
            if p + 1 < len(stamps):
                a, b = stamps[p] - stamps[p].mean(), stamps[p + 1] - stamps[p + 1].mean()
                na, nb = np.linalg.norm(a), np.linalg.norm(b)
                if na > 0 and nb > 0:
                    dot.append(float((a * b).sum() / (na * nb)))
        events.append(dict(top, label=label, seed_position=top_pos, matches=matches, looks=per_look,
                           in_on=[bool(e.get("found") or (e.get("track_snr") or -np.inf) >= ON_MIN)
                                  for e in per_look if e["on"]],
                           in_off=[e["off_evidence"] for e in per_look if not e["on"]],
                           off_snr_max=round(max(off_snr), 2) if off_snr and np.isfinite(max(off_snr)) else None,
                           on_snr_min=round(min(on_snrs), 2) if on_snrs and np.isfinite(min(on_snrs)) else None,
                           drift_spread_steps=round(spread, 2), drift_flag=spread > DRIFT_FLAG_STEPS,
                           dot_max=round(max(dot), 3) if dot else None, stamps=np.stack(stamps)))
    return events
