"""The instrument measured instead of assumed (docs/comparable.md, step 2):

- the fine channel's response, from Voyager 1's drifting carrier;
- the system equivalent flux density (SEFD), from ON-OFF pairs of the flux
  calibrator 3C295 taken with the same S-band setup;
- dropped data in a cadence's files, from their chunk indexes.

Run through `measure.py response`, `measure.py sefd` and
`measure.py dropped TARGET SESSION`; each answer is kept in
data/measurements/.
"""
import hashlib
import math
import re
from pathlib import Path

import numpy as np

import seti
import yoke

# --- the fine channel's response -----------------------------------------------------

# Window shapes a channeliser might use: the power a tone delta channels from
# a channel's centre gives that channel, 1 at the centre.
RESPONSES = {
    "rectangular (no window, sinc^2)": lambda d: np.sinc(d) ** 2,
    "Hann": lambda d: (np.sinc(d) / (1 - d ** 2)) ** 2,
    "Hamming": lambda d: ((0.54 * np.sinc(d) + 0.23 * (np.sinc(d - 1) + np.sinc(d + 1))) / 0.54) ** 2,
}
FFTS_A_SPECTRUM = 51          # Lebofsky et al. 2019, Table 4: 2^20-point FFTs, 51 a spectrum
FIT_HALF = 30                 # channels either side of the carrier fitted
BASELINE = (150, 400)         # channels from the carrier where each spectrum's baseline is taken


def _shape(kind, chan, c0, rate, tsamp, n_t):
    """The model's power in each channel of each spectrum: the response
    averaged over the carrier's place in each of the spectrum's FFTs."""
    fn = RESPONSES[kind]
    out = np.empty((n_t, len(chan)))
    for t in range(n_t):
        centres = c0 + rate * (t * tsamp + (np.arange(FFTS_A_SPECTRUM) + 0.5) * tsamp / FFTS_A_SPECTRUM)
        d = chan[None, :] - centres[:, None]
        d = np.where(np.abs(np.abs(d) - 1) < 1e-9, d + 1e-7, d)
        out[t] = fn(d).mean(axis=0)
    return out


def _fit(kind, data, chan, sigma0, c0, rate, tsamp):
    """chi^2 of one model at (c0, rate), each spectrum's amplitude fitted;
    the noise grows with the power (sigma0 x (1 + model))."""
    n_t = data.shape[0]
    m = _shape(kind, chan, c0, rate, tsamp, n_t)
    chi, amps, n = 0.0, [], 0
    for t in range(n_t):
        sel = np.abs(chan - (c0 + rate * (t + 0.5) * tsamp)) <= FIT_HALF
        mm, dd = m[t, sel], data[t, sel]
        a = float(mm @ dd / (mm @ mm))
        chi += float((((dd - a * mm) / (sigma0[t] * (1 + a * mm))) ** 2).sum())
        amps.append(a)
        n += int(sel.sum())
    return chi, amps, n, m


def response(say=print):
    """Voyager 1's carrier (drifting -0.378 Hz/s: 2.5 channels a spectrum,
    about 40 in the look) fitted with each window's response, averaged over
    the 51 FFTs of each spectrum; the wings beyond the main lobe against
    sinc^2's."""
    import measure
    path = measure._fetch(measure.VOYAGER_URL, yoke.DATA / "validation" / "Voyager1.single_coarse.fine_res.h5", say)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != measure.VOYAGER_SHA256:
        raise yoke.Refusal("INTERNAL_ERROR", f"{path} is not the file measured on 9 Nov 2026 (SHA-256 {digest}).")
    s = seti.read_slice(path, -1e12, 1e12)
    x = s["spectra"].astype(float)
    foff, tsamp, fch1 = s["foff"], s["tsamp"], s["fch1"]
    n_t = x.shape[0]
    carrier = measure.VOYAGER_PUBLISHED[0]
    c_guess = (carrier["frequency_mhz"] - fch1) / foff
    rate_guess = carrier["drift_hz_s"] / (foff * 1e6)
    y = x / np.median(x, axis=1, keepdims=True) - 1.0
    lo, hi = int(c_guess) - FIT_HALF - 130, int(c_guess) + FIT_HALF + 130
    chan = np.arange(lo, hi)
    # Each spectrum's own baseline, from both sides beyond the wings fitted.
    data = np.empty((n_t, len(chan)))
    sigma0 = np.empty(n_t)
    for t in range(n_t):
        c = c_guess + rate_guess * (t + 0.5) * tsamp
        side = np.r_[int(c) - BASELINE[1]:int(c) - BASELINE[0], int(c) + BASELINE[0]:int(c) + BASELINE[1]]
        base = float(np.median(y[t, side]))
        sigma0[t] = 1.4826 * float(np.median(np.abs(y[t, side] - base)))
        data[t] = y[t, lo:hi] - base
    fits = {}
    for kind in RESPONSES:
        best = None
        for rate in rate_guess * (1 + np.linspace(-0.01, 0.01, 9)):
            for c0 in c_guess + np.linspace(-1.5, 1.5, 31):
                chi = _fit(kind, data, chan, sigma0, c0, rate, tsamp)[0]
                if best is None or chi < best[0]:
                    best = (chi, c0, rate)
        chi, c0, rate = best
        for rate2 in rate * (1 + np.linspace(-0.0015, 0.0015, 7)):
            for c2 in c0 + np.linspace(-0.06, 0.06, 13):
                ch2 = _fit(kind, data, chan, sigma0, c2, rate2, tsamp)[0]
                if ch2 < chi:
                    chi, c0, rate = ch2, c2, rate2
        chi, amps, n, m = _fit(kind, data, chan, sigma0, c0, rate, tsamp)
        resid = {}
        for t in range(n_t):
            d = chan - (c0 + rate * (t + 0.5) * tsamp)
            for k in range(-4, 5):
                sel = np.abs(d - k) < 0.5
                resid.setdefault(k, []).extend(((data[t, sel] - amps[t] * m[t, sel]) / amps[t]).tolist())
        fits[kind] = {"chi2": round(chi, 1), "points": n, "dof": n - n_t - 2,
                      "chi2_per_dof": round(chi / (n - n_t - 2), 3),
                      "drift_hz_s": round(rate * foff * 1e6, 5), "centre_offset_channels": round(c0 - c_guess, 3),
                      "residual_over_peak_by_channel": {str(k): round(float(np.mean(v)), 4) for k, v in sorted(resid.items())},
                      "_c0": c0, "_rate": rate, "_amps": amps}
        say(f"{kind:32}: chi^2/dof {fits[kind]['chi2_per_dof']:.3f} ({fits[kind]['chi2']:.0f} over "
            f"{fits[kind]['dof']}), drift {fits[kind]['drift_hz_s']:+.5f} Hz/s")
    best_kind = min(fits, key=lambda k: fits[k]["chi2"])
    rect = fits["rectangular (no window, sinc^2)"]
    wings = []
    for a, b in ((2, 3), (3, 5), (5, 10), (10, 20), (20, 40), (40, 80), (80, 120)):
        vals = []
        for t in range(n_t):
            d = np.abs(chan - (rect["_c0"] + rect["_rate"] * (t + 0.5) * tsamp))
            sel = (d >= a) & (d < b)
            vals.extend((data[t, sel] / rect["_amps"][t]).tolist())
        k = np.arange(a, b) + 0.5
        wings.append({"channels": [a, b], "observed": round(float(np.mean(vals)), 5),
                      "error": round(float(np.std(vals) / math.sqrt(len(vals))), 5),
                      "sinc2": round(float(np.mean(1 / (math.pi ** 2 * k ** 2))), 5),
                      "hann": round(float(np.mean(RESPONSES["Hann"](k))), 7)})
        say(f"  wing {a}-{b} channels: {wings[-1]['observed']:.5f} ± {wings[-1]['error']:.5f} of the peak; "
            f"sinc^2 {wings[-1]['sinc2']:.5f}, Hann {wings[-1]['hann']:.1e}")
    for f in fits.values():
        for k in ("_c0", "_rate", "_amps"):
            f.pop(k)
    record = {"file": measure.VOYAGER_URL, "sha256": digest, "channel_hz": abs(foff) * 1e6, "tsamp_s": tsamp,
              "ffts_a_spectrum": FFTS_A_SPECTRUM, "fit_half_channels": FIT_HALF, "baseline_channels": list(BASELINE),
              "fits": fits, "best": best_kind,
              "chi2_margin_over_next": round(sorted(f["chi2"] for f in fits.values())[1]
                                             - min(f["chi2"] for f in fits.values()), 1),
              "wings": wings, "kind": "measured"}
    say(f"Best: {best_kind}, by chi^2 {record['chi2_margin_over_next']:.0f} over the next.")
    measure._keep("response", record)
    return record


# --- the flux scale ----------------------------------------------------------------------

# Perley & Butler 2017 (ApJS 230, 7), Table 5: log S[Jy] = sum a_i (log nu[GHz])^i,
# 0.05 to 50 GHz; 3C295 shows no sign of variability (their section 7.4).
PB2017_3C295 = (1.4701, -0.7658, -0.2780, -0.0347, 0.0399)
C3C295 = {"ra_hours": 14.18906388888889, "dec_deg": 52.2025186111111}
# ON-OFF pairs of 3C295 (Green Bank's OnOff: the OFF 1 degree north) in
# Breakthrough Listen's S-band setup, 1818.5 to 2720.8 MHz, the cadence's own.
SEFD_PAIRS = [
    ("https://bldata.berkeley.edu/bl_tess/s_band/spliced_blc0001020304050607_guppi_58819_72038_3C295_0091.gpuspec.0002.h5",
     "https://bldata.berkeley.edu/bl_tess/s_band/spliced_blc0001020304050607_guppi_58819_72177_3C295_0092.gpuspec.0002.h5"),
    ("https://bldata.berkeley.edu/bl_tess/s_band/spliced_blc7071727374757677_guppi_58814_43898_3C295_0129.gpuspec.0002.h5",
     "https://bldata.berkeley.edu/bl_tess/s_band/spliced_blc7071727374757677_guppi_58814_44040_3C295_0130.gpuspec.0002.h5"),
]
NOTCH_GUARD_MHZ = (2290.0, 2370.0)
STEADY_DRIFT = 0.02           # a scan whose total power moves more than this first to last is not steady
STEADY_SCATTER = 0.01         # nor one whose total power scatters more than this over its spectra
POINTING_SLOPE = 0.3          # |d log SEFD / d log f| over this: the source was off the beam's centre


def flux_3c295(f_mhz):
    lg = np.log10(np.asarray(f_mhz, dtype=float) / 1000.0)
    return 10 ** sum(a * lg ** i for i, a in enumerate(PB2017_3C295))


def elevation(mjd, ra_hours, dec_deg):
    """Degrees above the horizon at Green Bank."""
    import vetting
    gmst = (18.697374558 + 24.06570982441908 * (mjd + 2400000.5 - 2451545.0)) % 24
    h = math.radians(((gmst + vetting.GBT_LON / 15) % 24 - ra_hours) * 15)
    lat, dec = math.radians(vetting.GBT_LAT), math.radians(dec_deg)
    return math.degrees(math.asin(math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(h)))


def _calibrator_file(url, say):
    import measure
    path = measure._fetch(url, yoke.DATA / "calibration" / url.rsplit("/", 1)[-1], say)
    return path


def _read_power(path):
    """Each coarse channel's power: the median over time of the mean over
    its central 80% of channels (the middle 5 left out for the DC spike)."""
    h5py = seti.reading.h5()
    with h5py.File(path, "r") as f:
        a = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in f["data"].attrs.items()}
        d = np.asarray(f["data"][:, 0, :], dtype=np.float64)
    fch1, foff, n = float(a["fch1"]), float(a["foff"]), d.shape[1]
    per = int(round(seti.GBT_COARSE_MHZ / abs(foff)))
    lo, hi = per // 10, per - per // 10
    keep = np.r_[lo:per // 2 - 2, per // 2 + 3:hi]
    power, freq = [], []
    for c in range(n // per):
        power.append(float(np.median(d[:, c * per + keep].mean(axis=1))))
        freq.append(fch1 + foff * (c * per + per / 2))
    # How steady the scan was: its total power over time (the median over
    # coarse channels, so interference does not move it).
    each = np.stack([d[:, c * per + keep].mean(axis=1) for c in range(n // per)])
    series = np.median(each / np.median(each, axis=1, keepdims=True), axis=0)
    series = series / np.median(series)
    k = max(1, len(series) // 20)
    steady = {"drift": round(float(series[-k:].mean() / series[:k].mean() - 1), 4),
              "scatter": round(float(series.std()), 4)}
    return np.array(freq), np.array(power), a, d.shape[0], steady


def sefd(say=print):
    """SEFD = S(3C295) / (P_on / P_off - 1) in each coarse channel, from each
    ON-OFF pair; interference-struck coarse channels (a ratio over 15% from
    its neighbours' median) and the notch left out."""
    pairs = []
    for on_url, off_url in SEFD_PAIRS:
        got = {}
        for url in (on_url, off_url):
            path = _calibrator_file(url, say)
            freq, power, a, n_t, steady = _read_power(path)
            got[url] = {"path": path, "freq": freq, "power": power, "attrs": a, "spectra": n_t, "steady": steady,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "etag": path.with_suffix(".etag").read_text(encoding="utf-8").strip()
                        if path.with_suffix(".etag").exists() else None}
        # Which is ON: the one pointed at 3C295 (the OFF is a degree away).
        sep = {u: abs(float(g["attrs"]["src_dej"]) - C3C295["dec_deg"]) + abs(float(g["attrs"]["src_raj"])
                                                                              - C3C295["ra_hours"]) * 15
               for u, g in got.items()}
        on, off = (got[u] for u in sorted(got, key=sep.get))
        if not np.allclose(on["freq"], off["freq"]):
            raise yoke.Refusal("INTERNAL_ERROR", "The ON and OFF scans are not on the same channels.")
        ratio = on["power"] / off["power"]
        s = flux_3c295(on["freq"])
        value = np.where(ratio > 1, s / np.maximum(ratio - 1, 1e-9), np.nan)
        local = np.array([np.nanmedian(ratio[max(0, i - 4):i + 5]) for i in range(len(ratio))])
        clean = (np.abs(ratio / local - 1) <= 0.15) & ~((on["freq"] > NOTCH_GUARD_MHZ[0])
                                                       & (on["freq"] < NOTCH_GUARD_MHZ[1]))
        bins = []
        for lo in range(1800, 2750, 50):
            sel = clean & (on["freq"] >= lo) & (on["freq"] < lo + 50)
            if sel.sum():
                bins.append({"from_mhz": lo, "to_mhz": lo + 50, "coarse_channels": int(sel.sum()),
                             "flux_jy": round(float(flux_3c295(lo + 25)), 2),
                             "ratio": round(float(np.median(ratio[sel])), 3),
                             "sefd_jy": round(float(np.median(value[sel])), 2)})
        t_on, t_off = float(on["attrs"]["tstart"]), float(off["attrs"]["tstart"])
        el_on = elevation(t_on, float(on["attrs"]["src_raj"]), float(on["attrs"]["src_dej"]))
        el_off = elevation(t_off, float(off["attrs"]["src_raj"]), float(off["attrs"]["src_dej"]))
        p = {"on": on["path"].name, "off": off["path"].name, "on_sha256": on["sha256"], "off_sha256": off["sha256"],
             "on_etag": on["etag"], "off_etag": off["etag"], "mjd": round(t_on, 5),
             "utc": seti._utc(t_on), "elevation_on_deg": round(el_on, 1), "elevation_off_deg": round(el_off, 1),
             "off_offset_deg": round(float(off["attrs"]["src_dej"]) - float(on["attrs"]["src_dej"]), 3),
             "spectra": on["spectra"], "coarse_channels": len(ratio), "clean": int(clean.sum()),
             "sefd_jy_median": round(float(np.nanmedian(value[clean])), 2),
             "sefd_jy_16_84": [round(float(x), 2) for x in np.nanpercentile(value[clean], [16, 84])],
             "notch_ratio": round(float(np.median(ratio[(on["freq"] > 2305) & (on["freq"] < 2355)])), 3),
             "by_50_mhz": bins, "_freq": on["freq"], "_value": value, "_clean": clean}
        # Kept only if both scans were steady (no gain change, no slewing)
        # and the SEFD does not climb with frequency, as it does when the
        # source sits off the beam's centre (the beam narrows as 1/f).
        ok = clean & np.isfinite(value)
        slope = float(np.polyfit(np.log(on["freq"][ok]), np.log(value[ok]), 1)[0])
        p.update(on_power=on["steady"], off_power=off["steady"], sefd_slope_with_frequency=round(slope, 3))
        why = [f"{name} scan's power moved {100 * g['steady']['drift']:+.1f}% (scatter "
               f"{100 * g['steady']['scatter']:.1f}%)" for name, g in (("ON", on), ("OFF", off))
               if abs(g["steady"]["drift"]) > STEADY_DRIFT or g["steady"]["scatter"] > STEADY_SCATTER]
        if abs(slope) > POINTING_SLOPE:
            why.append(f"its SEFD goes as f^{slope:.2f}: the source off the beam's centre")
        p["kept"], p["not_kept_because"] = not why, why
        pairs.append(p)
        say(f"{p['utc']} UTC, elevation {el_on:.0f} deg: SEFD {p['sefd_jy_median']:.2f} Jy (16-84%: "
            f"{p['sefd_jy_16_84'][0]:.2f} to {p['sefd_jy_16_84'][1]:.2f}) over {p['clean']} of "
            f"{p['coarse_channels']} coarse channels; ON/OFF in the notch {p['notch_ratio']:.3f}; "
            + ("kept" if p["kept"] else "NOT KEPT: " + "; ".join(why)))
    # Over the band the cadence was searched in, both pairs together.
    kept = [p for p in pairs if p["kept"]]
    if not kept:
        raise yoke.Refusal("INTERNAL_ERROR", "No calibrator pair was steady enough to measure the SEFD from.")
    values = np.concatenate([p["_value"][p["_clean"]] for p in kept])
    freqs = np.concatenate([p["_freq"][p["_clean"]] for p in kept])
    for p in pairs:
        for k in ("_freq", "_value", "_clean"):
            p.pop(k)
    medians = [p["sefd_jy_median"] for p in kept]
    record = {"calibrator": "3C295", "flux_model": "Perley & Butler 2017, ApJS 230, 7, Table 5",
              "flux_model_coefficients": list(PB2017_3C295), "pairs": pairs,
              "sefd_jy": round(float(np.median(values)), 2),
              "sefd_jy_16_84": [round(float(x), 2) for x in np.percentile(values, [16, 84])],
              "pairs_kept": len(kept), "pairs_apart_jy": round(max(medians) - min(medians), 2) if len(kept) > 1 else None,
              "steadiness_rules": {"drift": STEADY_DRIFT, "scatter": STEADY_SCATTER, "pointing_slope": POINTING_SLOPE},
              "not_used": ["3C286 and 3C353 in AGBT19B_999_128 (2I/Borisov, 1651 to 3151 MHz): the 3C286 'ON' "
                           "header lies about 2 arcmin off the source; 3C353's lobes span arcminutes, partly "
                           "resolved by the beam, so its catalogue flux does not apply",
                           "3C123 in AGBT17B_999_50: the L-band setup (750 to 2250 MHz), not this receiver"],
              "by_50_mhz": [{"from_mhz": lo, "sefd_jy": round(float(np.median(values[(freqs >= lo) & (freqs < lo + 50)])), 2)}
                            for lo in range(1800, 2750, 50) if ((freqs >= lo) & (freqs < lo + 50)).any()],
              "not_measured": ["the 2017 cadence's own SEFD: these pairs are from December 2019, same receiver and "
                               "setup, other epoch and elevation",
                               "the noise diode (not in these files)", "linearity of the 8-bit requantisation",
                               "atmospheric opacity (about 1% at S-band, not corrected)"],
              "kind": "measured"}
    say(f"SEFD {record['sefd_jy']:.2f} Jy (16-84% over the band: {record['sefd_jy_16_84'][0]:.2f} to "
        f"{record['sefd_jy_16_84'][1]:.2f}) from {len(kept)} of {len(pairs)} pairs.")
    import measure
    measure._keep("sefd", record)
    return record


# --- dropped data --------------------------------------------------------------------------

def dropped(target, session, say=print):
    """Spectra of zeros in a cadence's files (rawspec fills lost blocks with
    zeros: Lebofsky et al. 2019), from the compressed size of every chunk
    (one spectrum of one coarse channel) in the files' chunk indexes: a
    chunk of zeros compresses to almost nothing. And the `zz` (missing
    node) and `oo` (dropped node) marks in the spliced files' names. Reads
    only the indexes (kept in data/index/), no data."""
    import store
    db = store.connect()
    files = [dict(r) for r in db.execute("SELECT * FROM files WHERE session=? AND cadence_target=? ORDER BY cadence_position",
                                         (session, target))]
    db.close()
    if len(files) != 6:
        raise yoke.Refusal("INVALID_REQUEST", f"No cadence of {target} in {session} in the store.")
    out = []
    for f in files:
        index = seti.reading.chunk_index(f["url"])
        sizes = np.array([c[4] for c in index["chunks"]])
        med = float(np.median(sizes))
        small = [{"spectrum": c[0], "first_channel": c[2], "bytes": c[4]} for c in index["chunks"] if c[4] < 0.1 * med]
        name = f["url"].rsplit("/", 1)[-1]
        nodes = re.search(r"blc((?:[0-9a-z]{2})+)_guppi", name)
        marks = [nodes.group(1)[i:i + 2] for i in range(0, len(nodes.group(1)), 2)] if nodes else []
        row = {"position": f["cadence_position"], "file": name, "chunks": len(sizes),
               "chunk_bytes_min": int(sizes.min()), "chunk_bytes_median": int(med), "chunk_bytes_max": int(sizes.max()),
               "smallest_over_median": round(float(sizes.min()) / med, 3), "zero_like_chunks": small, "nodes": marks,
               "missing_or_dropped_nodes": [m for m in marks if m in ("zz", "oo")]}
        out.append(row)
        say(f"look {row['position'] + 1}: {len(sizes)} chunks, {row['chunk_bytes_min']:,} to {row['chunk_bytes_max']:,} "
            f"bytes; {len(small)} like zeros; nodes {' '.join(marks)}")
    record = {"target": target, "session": session, "looks": out,
              "zero_like_chunks": sum(len(r["zero_like_chunks"]) for r in out),
              "missing_or_dropped_nodes": sum(len(r["missing_or_dropped_nodes"]) for r in out),
              "not_seen": "packets lost within a spectrum (lower power, not zeros): reading the data would show it",
              "kind": "measured"}
    import measure
    measure._keep("dropped", record)
    return record


def load(name):
    p = Path(yoke.DATA) / "measurements" / f"{name}.json"
    import json
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
