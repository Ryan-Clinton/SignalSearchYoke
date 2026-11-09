"""The checks a candidate goes through after the cadence test, after
Sheikh et al. 2021's framework for blc1: each check scores, none deletes.

Each check's result has a strength, kept apart:

- shown: the same signal is demonstrably elsewhere (an OFF look of this
  cadence; another target close in time, frequency, drift agreeing);
- indicated: a strong sign short of proof (a known band, zero drift, a
  match months away, look-alikes seen in OFF looks);
- coincidence possible: a relation (harmonic, intermodulation, look-alike)
  whose chance rate, at this many hits, is not small; the rate is recorded.

The verdict: "interference (shown: ...)", "likely interference (indicated:
...)", "unexplained, strong" (a hit at the cut in every ON look, the data
sound), or "unexplained, weak". Only a "shown" makes "interference" alone.
"Unexplained" is the end of these checks, not a discovery: blc1 was
unexplained until its look-alikes were found.

| # | check | blc1 step |
|---|---|---|
| 1 | data sanity: every look complete, the stamps finite, no blank spectra | 1 |
| 2 | the OFF looks below the threshold (the cadence test's S/N) | 2 |
| 3 | known interference bands at Green Bank | 3 |
| 4 | zero or very low drift | 4 |
| 5 | drift against the Earth's own (rotation and orbit, toward the target) | 5 |
| 6 | recurrence at other targets and times | 6 |
| 7 | look-alikes: the same drift over frequency elsewhere in the cadence | 7, 9 |
| 8 | harmonics and intermodulation, with their chance rates | 8 |
| 9 | crowding: hits per MHz around it against the band's median | (SETI@home) |
| 10 | the report, with the blc1 checklist | 10: re-observation, not possible here |
"""
import json
import math
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import onoff

VERSION = "3 (9 Nov 2026: check 6 takes its chance from each file's hits over the band searched near the candidate)"
C = 299792458.0
GBT_LAT, GBT_LON = 38.4331, -79.8398            # degrees (north, east)
EARTH_OMEGA, EARTH_R = 7.2921159e-5, 6.371e6    # rad/s, m
SUN_PULL = 5.93e-3                              # m/s^2: the Sun's pull at 1 AU
OBLIQUITY = math.radians(23.439)
CLOCKS_MHZ = (2.000004, 10, 15, 16, 25, 30, 100, 125, 128, 133.333333)
HARMONICS = range(2, 21)
TOLERANCE_HZ = 1000.0                           # harmonics and intermodulation: within 1 kHz (blc1)
RECUR_HZ = 100.0                                # recurrence: within 100 Hz plus the drift's travel
CHANCE_SMALL = 0.05                             # a relation's chance rate under this is "indicated"
CROWDED = 10.0                                  # hits per MHz over the band's median: "indicated"
SHOWN_DAYS = 3.0                                # a recurrence this close in time, drift agreeing, is "shown"

# Bands at Green Bank's L and S band where transmitters are known (ITU Radio
# Regulations Article 5; Price et al. 2020 for the S-band notch filter;
# Margot et al. 2021 for cellular), MHz.
BANDS = [
    (1025.0, 1035.0, "aircraft transponder interrogation (1030 MHz)"),
    (1085.0, 1095.0, "aircraft transponders and ADS-B (1090 MHz)"),
    (1164.0, 1189.0, "GPS L5 / Galileo E5a"), (1189.0, 1214.0, "Galileo E5b / BeiDou B2"),
    (1215.0, 1254.0, "GPS L2 / GLONASS L2"), (1260.0, 1300.0, "Galileo E6 and radar"),
    (1525.0, 1559.0, "Inmarsat and other mobile satellites"), (1559.0, 1610.0, "GPS L1, GLONASS L1, Galileo, BeiDou"),
    (1610.0, 1626.5, "Iridium and Globalstar"), (1670.0, 1710.0, "weather satellites"),
    (1930.0, 1995.0, "cellular (PCS) downlinks"), (2025.0, 2110.0, "space operation and research uplinks"),
    (2200.0, 2290.0, "space operation and research downlinks"),
    (2300.0, 2360.0, "the GBT S-band notch filter (satellite radio, SDARS 2320-2345 MHz)"),
    (2400.0, 2483.5, "Wi-Fi and the ISM band"), (2483.5, 2500.0, "Globalstar downlinks")]

CHECKLIST = [  # blc1's ten steps: what this project does for each
    (1, "instruments working", "automated (check 1)"),
    (2, "not in the OFF looks below the threshold", "automated (check 2)"),
    (3, "catalogued interference at the frequency", "automated (check 3: a band list, no observatory database)"),
    (4, "drift against human technology's", "automated in part (check 4: zero drift only)"),
    (5, "drift against the target's and the solar system's", "automated (check 5: the Earth's part)"),
    (6, "other instances in the observatory's archive", "automated in part (check 6: this project's store only)"),
    (7, "similar signals at other frequencies, same observation", "automated (check 7)"),
    (8, "whether those are the same phenomenon", "automated in part (checks 7, 8 with chance rates); judged by hand"),
    (9, "those tested for interference with their OFF looks", "automated (check 7)"),
    (10, "re-observation, same and other instruments", "not possible from archive data: the project has no telescope"),
]


class LookInfo:
    """What the checks need of a look: its hits, start, place in the cadence."""

    def __init__(self, hits, tstart, position, step, width_hz, complete=True):
        self.hits, self.tstart, self.position = hits, tstart, position
        self.step, self.width_hz, self.complete = step, width_hz, complete
        self.on = position % 2 == 0


def expected_drift(f_mhz, mjd, ra_hours, dec_deg):
    """The drift the Earth's turning and orbit give a signal fixed in the
    target's frame, at Green Bank, Hz/s: (total, rotation, orbit)."""
    jd = mjd + 2400000.5
    d = jd - 2451545.0
    gmst = (18.697374558 + 24.06570982441908 * d) % 24
    lst = (gmst + GBT_LON / 15) % 24
    h = math.radians((lst - ra_hours) * 15)
    dec, ra = math.radians(dec_deg), math.radians(ra_hours * 15)
    f = f_mhz * 1e6
    rot = -f * EARTH_OMEGA ** 2 * EARTH_R * math.cos(math.radians(GBT_LAT)) * math.cos(dec) * math.cos(h) / C
    g = math.radians((357.528 + 0.9856003 * d) % 360)
    lam = math.radians((280.460 + 0.9856474 * d + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360)
    sun = np.array([math.cos(lam), math.cos(OBLIQUITY) * math.sin(lam), math.sin(OBLIQUITY) * math.sin(lam)])
    to = np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])
    orb = f * SUN_PULL * float(sun @ to) / C
    return rot + orb, rot, orb


def at_least(n, expected):
    """The chance of n or more by accident when `expected` are: Poisson."""
    if n <= 0:
        return 1.0
    term = total = math.exp(-expected)
    for i in range(1, n):
        term *= expected / i
        total += term
    return max(0.0, 1.0 - total)


def _near_any(sorted_values, targets, tol):
    """Whether any target lies within tol of any of the sorted values."""
    if not len(sorted_values) or not len(targets):
        return False
    i = np.clip(np.searchsorted(sorted_values, targets), 1, len(sorted_values) - 1)
    gap = np.minimum(np.abs(sorted_values[i] - targets), np.abs(sorted_values[i - 1] - targets))
    return bool(np.any(gap <= tol))


def _recur_window(drift, dt):
    """The width check 6 accepts a match in, for a file dt seconds away: two
    windows of 100 Hz plus the drift's travel, one where the drift carries
    the signal and one where it started (one only, beyond a day)."""
    within = abs(dt) < 86400
    reach = RECUR_HZ + (abs(drift) * abs(dt) if within else 0.0)
    shift = abs(drift * dt) if within else 0.0
    return 2 * reach + min(shift, 2 * reach)


def _drift_agrees(d, drift, step):
    return abs(d - drift) <= max(2 * step, 0.05 * abs(drift))


def _recurrence_expected(f, drift, step, t0, others, background):
    """Expected matches by chance for check 6: (all, close at the cut, close
    at any SNR), and how the density was had. `background`: one entry a
    file, {mjd, searched_hz, hits: [(drift_hz_s, shadow)]}, the file's hits
    over the band searched around the candidate, matching or not."""
    if background is not None:
        e6 = e_cut = e_all = 0.0
        searched = n_hits = n_agree = 0
        for b in background:
            if not b["searched_hz"]:
                continue
            dt = (b["mjd"] - t0) * 86400
            per_hz = _recur_window(drift, dt) / b["searched_hz"]
            agree = [s for d, s in b["hits"] if _drift_agrees(d, drift, step)]
            e6 += len(b["hits"]) * per_hz
            if abs(dt) <= SHOWN_DAYS * 86400:
                e_cut += sum(1 for s in agree if not s) * per_hz
                e_all += len(agree) * per_hz
            searched += b["searched_hz"]
            n_hits += len(b["hits"])
            n_agree += len(agree)
        return e6, e_cut, e_all, {"source": "measured: each file's hits over the band searched near the candidate",
                                  "files": len(background), "searched_mhz": round(searched / 1e6, 3),
                                  "hits": n_hits, "drift_agree_share": round(n_agree / n_hits, 4) if n_hits else None}
    # No background given: the supplied hits' own spread, biased high when
    # they were chosen for lying near the candidate; never enough for "shown".
    if not others:
        return 0.0, 0.0, 0.0, None
    span_hz = max(1.0, (max(h["frequency_mhz"] for h in others) - min(h["frequency_mhz"] for h in others)) * 1e6)
    window_hz = float(np.mean([_recur_window(drift, (h["mjd"] - t0) * 86400) for h in others]))
    share = min(1.0, 2 * max(2 * step, 0.05 * abs(drift)) / (2 * onoff.MAX_DRIFT_NULL))
    e6 = len(others) * window_hz / span_hz
    e_cut = sum(1 for h in others if not h.get("shadow")) * window_hz / span_hz * share
    return e6, e_cut, e6 * share, {"source": "the supplied hits' own spread (no background: at most indicated)"}


def _check(n, name, result, strength=None, **evidence):
    return {"n": n, "name": name, "result": result, "strength": strength, "evidence": evidence}


def vet(event, looks, target=None, others=(), session_hits=(), report_dir=None, lead=None, background=None):
    """The checks on one candidate. `event` as onoff.judge gives it (with
    `matches` and `stamps`); `looks` its cadence (LookInfo or onoff.Look);
    `target` {ra_hours, dec_deg, name}; `others` hits at other targets
    from the store [{frequency_mhz, drift_hz_s, snr, mjd, target, shadow}];
    `session_hits` every current hit at the cut of the session (frequency,
    drift, snr, position) for harmonics, intermodulation and crowding;
    `background` the hits of each file `others` came from over the band
    searched near the candidate, for check 6's chance (see
    `_recurrence_expected`; check.recurrence_background builds it)."""
    f, drift = event["frequency_mhz"], event["drift_hz_s"]
    l0 = looks[event.get("seed_position", 0)]
    step = l0.step
    checks = []

    # 1. data sanity
    stamps = event.get("stamps")
    blank = int(sum((np.abs(st).sum(axis=1) == 0).sum() for st in stamps)) if stamps is not None else None
    finite = bool(np.isfinite(stamps).all()) if stamps is not None else None
    complete = all(getattr(lk, "complete", True) for lk in looks)
    sound = complete and finite is not False and not blank
    flagged = event.get("flagged_fraction")
    checks.append(_check(1, "data sanity", "sound" if sound else "not sound", None, every_look_complete=complete,
                         stamps_finite=finite, blank_stamp_spectra=blank, flagged_fraction=flagged))

    # 2. the OFF looks below the threshold
    off_max = event.get("off_snr_max")
    shown = any(e.get("off_evidence") for e in event.get("looks", []) if not e.get("on"))
    checks.append(_check(2, "OFF looks below the threshold",
                         f"OFF evidence (S/N {off_max})" if shown else f"nothing in the OFF looks (brightest S/N {off_max})",
                         "shown" if shown else None, off_snr_max=off_max, threshold=onoff.OFF_MAX,
                         per_look=[{k: e.get(k) for k in ("position", "track_snr", "track_snr_fixed", "hit_snr")}
                                   for e in event.get("looks", []) if not e.get("on")]))

    # 3. known bands
    band = next((b for b in BANDS if b[0] <= f <= b[1]), None)
    checks.append(_check(3, "known interference bands", band[2] if band else "in no listed band",
                         "indicated" if band else None, band=band and list(band)))

    # 4. zero or very low drift
    low = abs(drift) < step
    checks.append(_check(4, "zero or very low drift", f"{drift:+.4f} Hz/s" + (" (under one drift step)" if low else ""),
                         "indicated" if low else None, drift_hz_s=drift, one_step_hz_s=round(step, 4)))

    # 5. drift against the Earth's
    if target and target.get("ra_hours") is not None:
        total, rot, orb = expected_drift(f, l0.tstart, target["ra_hours"], target["dec_deg"])
        checks.append(_check(5, "drift against the Earth's", f"observed {drift:+.4f}, Earth's {total:+.4f} Hz/s, "
                             f"difference {drift - total:+.4f}", None, observed=drift, expected=round(total, 4),
                             rotation=round(rot, 4), orbit=round(orb, 4), difference=round(drift - total, 4)))
    else:
        checks.append(_check(5, "drift against the Earth's", "target position unknown", None))

    # 6. recurrence at other targets and times
    matches_ = []
    for h in others:
        dt = (h["mjd"] - l0.tstart) * 86400
        # Within a day, the drift carries the signal; further apart, its
        # frequency then says nothing of now, so 100 Hz about where it was.
        travel = abs(drift) * abs(dt) if abs(dt) < 86400 else 0.0
        reach = (RECUR_HZ + travel) / 1e6
        moved = f + (drift * dt / 1e6 if abs(dt) < 86400 else 0.0)
        if abs(h["frequency_mhz"] - moved) <= reach or abs(h["frequency_mhz"] - f) <= reach:
            agree = abs(h["drift_hz_s"] - drift) <= max(2 * step, 0.05 * abs(drift))
            matches_.append(dict(h, days=round(abs(dt) / 86400, 3), drift_agrees=agree))
    close = [m for m in matches_ if m["days"] <= SHOWN_DAYS and m["drift_agrees"]]
    close_cut = [m for m in close if not m.get("shadow")]
    # The chance of as many by accident. The hits in `others` were picked for
    # lying near the candidate, so their own spread says nothing of how
    # crowded the sky is there. The density comes from `background`: each
    # file's hits over the band searched around the candidate, whether they
    # match or not, with the share whose drift agrees measured, not assumed.
    expected6, expected_close, expected_close_all, how = _recurrence_expected(
        f, drift, step, l0.tstart, others, background)
    chance6 = at_least(len(matches_), expected6)
    chance_close = at_least(len(close_cut), expected_close)
    # "Shown" needs a match at the cut, close in time, drift agreeing, that
    # chance would rarely give, against a measured background; shadow hits
    # (SNR 5 to 10), a crowded band or no background give at most "indicated".
    if close_cut and chance_close < CHANCE_SMALL and background is not None:
        strength6 = "shown"
    elif (close and at_least(len(close), expected_close_all) < CHANCE_SMALL) or \
            (matches_ and chance6 < CHANCE_SMALL):
        strength6 = "indicated"
    else:
        strength6 = "coincidence possible" if matches_ else None
    checks.append(_check(6, "recurrence at other targets and times",
                         f"{len(matches_)} match(es) in {len(others)} hits elsewhere"
                         + (f", {len(close)} within {SHOWN_DAYS:g} days with the drift agreeing"
                            f" ({len(close_cut)} at the cut)" if close else ""),
                         strength6, matches=matches_[:20], hits_searched=len(others),
                         expected_by_chance=round(expected6, 4), chance=chance6,
                         close_at_cut=len(close_cut), expected_close_at_cut=round(expected_close, 5),
                         chance_close=chance_close, background=how))

    # 7. look-alikes in the same cadence: the same drift over frequency
    nu = drift / (f * 1e6)
    tol = 2 * step / (f * 1e6)
    own = {(p, i) for p, i in enumerate(event.get("matches", [])) if i is not None}
    alike, alike_off = [], []
    off_count = 0
    for lk in looks:
        for i, h in enumerate(lk.hits):
            # Hits at the cut only: ~750 OFF shadow hits a cadence would make
            # any drift a likely coincidence.
            if (lk.position, i) in own or h.get("shadow"):
                continue
            if not lk.on:
                off_count += 1
            if abs(h["frequency_mhz"] - f) * 1e6 < 3 * lk.width_hz + abs(drift) * 1800:
                continue                              # itself, or its own track
            hnu = h["drift_hz_s"] / (h["frequency_mhz"] * 1e6)
            if abs(hnu - nu) <= tol or (abs(drift) >= step and abs(hnu + nu) <= tol):
                entry = {"position": lk.position, "frequency_mhz": h["frequency_mhz"], "drift_hz_s": h["drift_hz_s"],
                         "snr": h["snr"], "shadow": bool(h.get("shadow")), "mirror": abs(hnu - nu) > tol}
                alike.append(entry)
                if not lk.on:
                    alike_off.append(entry)
    span_nu = 2 * 4.0 / (f * 1e6)
    expected7 = off_count * (2 * tol * (2 if abs(drift) >= step else 1)) / span_nu
    chance7 = at_least(len(alike_off), expected7)          # this many in OFF looks, by accident
    if alike_off:
        strength7 = "indicated" if chance7 < CHANCE_SMALL and abs(drift) >= 0.1 else "coincidence possible"
    else:
        strength7 = None
    checks.append(_check(7, "look-alikes in the cadence",
                         f"{len(alike)} look-alike(s), {len(alike_off)} in OFF looks", strength7,
                         normalised_drift=nu, tolerance=tol, lookalikes=alike[:30], in_off=len(alike_off),
                         expected_by_chance=round(expected7, 4), chance=chance7, off_hits=off_count,
                         note="chance assumes OFF hits' drifts spread evenly over +-4 Hz/s; near zero drift, where "
                              "interference crowds, it is called a possible coincidence"))

    # 8. harmonics and intermodulation, against the session's hits
    freqs = np.array([h["frequency_mhz"] for h in session_hits]) if session_hits else np.array([])
    strong0 = np.array([h["frequency_mhz"] for h in session_hits
                        if abs(h["drift_hz_s"]) < step and h["snr"] >= 20]) if session_hits else np.array([])
    strong_sorted = np.sort(strong0)
    lo_band = float(freqs.min()) if len(freqs) else f - 1
    hi_band = float(freqs.max()) if len(freqs) else f + 1

    def relations(x):
        found = []
        if len(freqs):
            tol_mhz = TOLERANCE_HZ / 1e6
            for n in HARMONICS:
                for target_f, kind in ((x * n, f"x{n}"), (x / n, f"/{n}")):
                    if lo_band <= target_f <= hi_band and np.any(np.abs(freqs - target_f) <= tol_mhz):
                        found.append(kind)
            for clock in CLOCKS_MHZ:
                m = np.round(np.abs(freqs - x) / clock)
                ok = (m >= 1) & (np.abs(np.abs(freqs - x) - m * clock) <= tol_mhz)
                if ok.any():
                    found.append(f"{clock:g} MHz spacing")
            if len(strong0) >= 2:
                # a·f1 − b·f2 = x or a·f1 + b·f2 = x: for each f1 the f2 it
                # needs, looked up in the sorted list (the same test as every
                # pair, without the N×N tables a whole sweep makes too big).
                for a in (1, 2, 3):
                    for b in (1, 2, 3):
                        need = np.concatenate([(a * strong_sorted - x) / b, (x - a * strong_sorted) / b])
                        if _near_any(strong_sorted, need, tol_mhz / b):
                            found.append(f"{a}f1+-{b}f2")
        return found
    rel = relations(f)
    rng = np.random.default_rng(int(f * 1e6) % (2 ** 32))
    trials = 200
    chance8 = (sum(bool(relations(float(rng.uniform(lo_band, hi_band)))) for _ in range(trials)) / trials
               if len(freqs) else 0.0)
    strength8 = ("indicated" if rel and chance8 < CHANCE_SMALL else "coincidence possible" if rel else None)
    checks.append(_check(8, "harmonics and intermodulation", ", ".join(rel) if rel else "none found", strength8,
                         relations=rel, chance=round(chance8, 3), hits_compared=int(len(freqs)),
                         strong_zero_drift=int(len(strong0)), trials=trials))

    # 9. crowding
    if len(freqs):
        near = int(np.sum(np.abs(freqs - f) <= 0.5))
        edges = np.arange(lo_band, hi_band + 1, 1.0)
        counts = np.histogram(freqs, bins=edges)[0] if len(edges) > 1 else np.array([near])
        median = float(np.median(counts)) if len(counts) else 0.0
        ratio = near / max(median, 1.0)
        checks.append(_check(9, "crowding", f"{near} hits in the MHz around it, band median {median:g} a MHz",
                             "indicated" if ratio >= CROWDED else None, hits_near=near, median_per_mhz=median,
                             ratio=round(ratio, 2)))
    else:
        checks.append(_check(9, "crowding", "no session hits given", None))

    shown_ = [c for c in checks if c["strength"] == "shown"]
    indicated = [c for c in checks if c["strength"] == "indicated"]
    all_on = all(e.get("found") for e in event.get("looks", []) if e.get("on"))
    if shown_:
        verdict = "interference (shown: " + "; ".join(c["name"] for c in shown_) + ")"
    elif indicated:
        verdict = "likely interference (indicated: " + "; ".join(c["name"] for c in indicated) + ")"
    elif all_on and sound:
        verdict = "unexplained, strong"
    else:
        verdict = "unexplained, weak"
    checks.append(_check(10, "report", verdict, None, checklist=[{"step": n, "what": w, "here": h}
                                                                for n, w, h in CHECKLIST],
                         rio="to be scored by hand" if verdict == "unexplained, strong" else "not needed"))
    out = {"verdict": verdict, "reasons": [c["name"] for c in shown_ + indicated], "checks": checks,
           "version": VERSION, "checked": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if report_dir is not None and lead:
        out["report"] = write_report(out, event, lead, Path(report_dir), target)
    return out


def png(stamps, path, scale=6):
    """The six stamps one above the other as a greyscale PNG (no
    dependencies): each look a panel of spectra by channels."""
    n, rows, cols = stamps.shape
    lo, hi = np.percentile(stamps, 1), np.percentile(stamps, 99.7)
    norm = np.clip((stamps - lo) / max(hi - lo, 1e-9), 0, 1)
    gap = 3
    height = n * rows * scale + (n - 1) * gap
    img = np.full((height, cols * scale), 255, np.uint8)
    for k in range(n):
        panel = np.kron((norm[k] * 255).astype(np.uint8), np.ones((scale, scale), np.uint8))
        img[k * (rows * scale + gap):k * (rows * scale + gap) + rows * scale] = 255 - panel
    raw = b"".join(b"\x00" + img[r].tobytes() for r in range(img.shape[0]))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", img.shape[1], img.shape[0], 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    Path(path).write_bytes(data)
    return path


def write_report(result, event, lead, folder, target=None):
    folder.mkdir(parents=True, exist_ok=True)
    picture = None
    if event.get("stamps") is not None:
        picture = png(np.asarray(event["stamps"]), folder / f"{lead}.png")
    lines = [f"# {lead}: {result['verdict']}", "",
             f"Checked by `check.py` (vetting {result['version']}) on {result['checked'][:10]}. \"Unexplained\" is "
             "the end of these checks, not a discovery.", "",
             f"- {event['frequency_mhz']:.6f} MHz, drift {event['drift_hz_s']:+.4f} Hz/s, SNR {event['snr']}"
             + (f", target {target.get('name')}" if target else ""),
             f"- OFF looks' brightest S/N along the track: {event.get('off_snr_max')}; faintest ON look: "
             f"{event.get('on_snr_min')}; DOT score {event.get('dot_max')}; ON drifts spread "
             f"{event.get('drift_spread_steps')} steps" + (" (flagged)" if event.get("drift_flag") else ""), ""]
    if picture:
        lines += [f"![The six looks around the track, ON, OFF, ON, OFF, ON, OFF, top to bottom]({picture.name})", ""]
    lines += ["## The checks", "", "| # | check | result | strength |", "|---|---|---|---|"]
    lines += [f"| {c['n']} | {c['name']} | {c['result']} | {c['strength'] or ''} |" for c in result["checks"]]
    lines += ["", "## blc1's ten steps", "", "| step | what | here |", "|---|---|---|"]
    lines += [f"| {n} | {w} | {h} |" for n, w, h in CHECKLIST]
    lines += ["", "## The evidence", "", "```json",
              json.dumps({c["name"]: c["evidence"] for c in result["checks"]}, indent=1, default=str)[:20000], "```", ""]
    path = folder / f"{lead}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
