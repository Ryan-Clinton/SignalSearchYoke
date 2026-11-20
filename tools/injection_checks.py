"""How far the planted signals stand for real ones (comparable.md; the
injection audit, docs/audits.md 2). New experiments, beside the finished
ones: nothing here changes how steps 4, 10 and 12 planted their signals or
their verdicts. Each writes data/analysis/injection_<name>.json.

    python tools/injection_checks.py substeps   the sub-steps a spectrum is planted in: 32 (in use), 51, 128, 256
    python tools/injection_checks.py voltage    power added to the spectra (in use) against a tone added to the
                                                voltages before they are squared, on synthetic noise
    python tools/injection_checks.py dc         signals crossing the DC bin, planted before and after it is blanked
    python tools/injection_checks.py power      a fixed S_in in every ON look (in use) against one injected power
                                                in all three (instrument units), on real blocks of the 2017 session
    python tools/injection_checks.py all

- **substeps**: measure.plant spreads a spectrum's power over the channels
  the tone crosses at SUBSTEPS (32) instants; the spectrometer sums 51 FFTs.
  The profiles at 32, 51, 128 and 256 against 256, and the detector's S/N
  on the planted track in noise near the cut, by drift and start within a
  channel.
- **voltage**: power added to the summed spectra is the signal's mean power
  without the signal-noise cross term that squaring signal plus noise
  makes. Synthetic voltages: complex Gaussian noise in each channel of each
  of 51 FFTs a spectrum; a tone's complex amplitude in the channels near it
  (sinc, its phase random from FFT to FFT), added before squaring. The same
  noise and the same tones made three ways: power at 32 sub-steps (as in
  use), power at 51 (one an FFT, to tell sampling from the cross term), and
  voltage. Then again with two polarizations summed, as Stokes I is (the
  tone's power split equally between them, each with its own phase: an
  unpolarized or circular signal). Both pipelines, three-look recovery at
  their cuts. A simplified noise model: no polyphase filterbank, no 8-bit
  requantization, a flat receiver response.
- **dc**: seti.blank_dc replaces each coarse channel's middle channel with
  the mean of its neighbours when a slice is read, and signals are planted
  after, so a planted signal crossing it keeps its power there, where a
  real one would lose it. Signals placed to cross the DC bin, planted
  before blanking (as the sky would) and after (as in use); both pipelines.
  And how many of the finished experiments' planted signals cross a DC bin
  in any ON look.
- **flux** (constant injected power): matched.plant scales each ON look's
  signal to that look's noise, so its S_in is the same in each; a
  transmitter's flux does not follow the noise. Eight blocks of the 2017
  session, four crowded and four clean drawn at random (seed 12), planted
  again with one power in all three ON looks, in the spectra's own units
  (the mean of the three looks' noise, so the same S_in on average). The
  spectra are not flux-calibrated, so this is constant injected power, not
  constant received flux in Jy; both pipelines, and the looks' noise
  against each other.

Every comparison is paired: the same signals in both variants, recorded
one by one (both found, first only, second only, neither) for each
pipeline and cut, overall and by strength and drift, so equal totals
cannot hide signals found in one and lost in the other.
"""
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matched  # noqa: E402
import measure  # noqa: E402
import pipelines  # noqa: E402
import searching  # noqa: E402
import seti  # noqa: E402
import store  # noqa: E402
import yoke  # noqa: E402

OUT = yoke.DATA / "analysis"
WORK = yoke.DATA / "analysis" / "injection_work"
FOFF = -2.7939677238464355e-06
TSAMP = 18.253611008
N_T = 16
N_FFT = 51                       # FFTs summed in a spectrum of Green Bank's finest product
CUTS = (10, 30)
SUBSTEP_GRID = (32, 51, 128, 256)
NEAR_CUT = {1.0: 12, 2.0: 20, 4.0: 40}     # S_in a signal is found at about half the time, by drift (the box widens with it)


def _say(*a):
    print(*a, flush=True)


# --- the pipelines on a cadence ------------------------------------------------------------

def _cadence(spectra_by_look, coarse=None):
    """matched's cadence form for six (time, channel) arrays."""
    out = []
    n_f = spectra_by_look[0].shape[1]
    for j, raw in enumerate(spectra_by_look):
        s = {"spectra": raw, "fch1": 2000.0, "foff": FOFF, "tsamp": TSAMP,
             "tstart": 60000.0 + j * 330.0 / 86400, "target": "SYNTH" if j % 2 == 0 else f"SYNTH_OFF{j}",
             "first_channel": 0, "coarse_channel": coarse or n_f, "nchans": n_f}
        out.append({"s": s, "raw": raw, "spectra": raw, "sigma": measure.channel_noise(raw)})
    return out


class Judge:
    """Both pipelines on one plain cadence and any number of planted versions of it."""

    def __init__(self, cad, work):
        self.cad, self.work = cad, Path(work)
        self.searched = matched.our_search(cad)
        caches = [{} for _ in range(6)]
        self.plain = {}
        for c in CUTS:
            looks, events, order = matched.our_events(cad, self.searched, matched.TRUE, c, caches)
            self.plain[c] = matched._our_kept(looks, events, order)
        paths = [seti.save(x["s"], self.work / "plain" / f"{j}.h5") for j, x in enumerate(cad)]
        pipelines._tool("turbo_curves.py", self.work / "turbo_plain.json", ",".join(map(str, CUTS)), "true", *paths)
        self.turbo_plain = json.loads((self.work / "turbo_plain.json").read_text(encoding="utf-8"))

    def judge(self, name, planted, ts):
        """planted: six arrays; ts: matched-style tones. {pipeline: {cut: found}}, and per tone."""
        cad_p = [dict(c, spectra=p) for c, p in zip(self.cad, planted)]
        ours = matched._ours_true(cad_p, matched.our_search(cad_p))
        paths = [seti.save(dict(c["s"], spectra=p), self.work / name / f"{j}.h5")
                 for j, (c, p) in enumerate(zip(self.cad, planted))]
        out_json = self.work / f"turbo_{name}.json"
        pipelines._tool("turbo_curves.py", out_json, ",".join(map(str, CUTS)), "true", *paths)
        tp = json.loads(out_json.read_text(encoding="utf-8"))

        def at(rec, cut):
            return next(e["rows"] for e in rec["events"] if tuple(e["as_on"]) == matched.TRUE and e["cut"] == cut)
        per = []
        for t in ts:
            t_f = {j: matched.where(self.cad, t, j)[1] for j in matched.TRUE}
            t_ft = {j: f + t["drift"] * TSAMP / 2 / 1e6 for j, f in t_f.items()}
            row = {"s_in": t["s_in"], "drift": t["drift"]}
            for c in CUTS:
                row[f"ours_{c}"] = matched._status(t_f, t["drift"], ours[str(c)], self.plain[c])["three_looks"] \
                    == "recovered"
                tt = matched._status(t_ft, t["drift"], matched._turbo_kept(at(tp, float(c))),
                                     matched._turbo_kept(at(self.turbo_plain, float(c))), turboseti=True)
                row[f"turboseti_{c}"] = tt["three_looks"] == "recovered" and \
                    matched._turbo_on_hits(tp, t_ft, t["drift"], c) == len(matched.TRUE)
            per.append(row)
        shutil.rmtree(self.work / name, ignore_errors=True)
        return per


def _drift_bin(d):
    for lo, hi in measure.DRIFT_BINS:
        if lo <= abs(d) < hi or (hi == measure.DRIFT_BINS[-1][1] and abs(d) <= hi):
            return f"{lo}-{hi}"
    return "other"


def paired(first, second):
    """The same signals in two variants: for each pipeline and cut, both
    found, first only, second only, neither; overall, by S_in and by drift."""
    if len(first) != len(second) or any((a["s_in"], a["drift"]) != (b["s_in"], b["drift"])
                                        for a, b in zip(first, second)):
        raise ValueError("the two variants are not of the same signals in the same order")
    keys = [k for k in first[0] if k.startswith(("ours_", "turboseti_"))] if first else []

    def count(pairs):
        out = {}
        for k in keys:
            c = {"both": 0, "first_only": 0, "second_only": 0, "neither": 0}
            for a, b in pairs:
                c["both" if a[k] and b[k] else "first_only" if a[k] else "second_only" if b[k] else "neither"] += 1
            out[k] = c
        return out
    pairs = list(zip(first, second))
    by_s, by_d = {}, {}
    for a, b in pairs:
        by_s.setdefault(str(a["s_in"]), []).append((a, b))
        by_d.setdefault(_drift_bin(a["drift"]), []).append((a, b))
    return {"all": count(pairs), "by_strength": {k: count(v) for k, v in sorted(by_s.items(), key=lambda kv: float(kv[0]))},
            "by_drift": {k: count(v) for k, v in by_d.items()}}


def _discordant(p):
    """The largest number of signals found in one variant and not the other, over pipelines and cuts."""
    return max(max(c["first_only"], c["second_only"]) for c in p["all"].values())


def _totals(rows):
    keys = [k for k in rows[0] if k.startswith(("ours_", "turboseti_"))] if rows else []
    return {k: int(sum(r[k] for r in rows)) for k in keys} | {"signals": len(rows)}


def _by_strength(rows):
    out = {}
    for r in rows:
        d = out.setdefault(str(r["s_in"]), {"signals": 0})
        d["signals"] += 1
        for k, v in r.items():
            if k.startswith(("ours_", "turboseti_")):
                d[k] = d.get(k, 0) + int(v)
    return dict(sorted(out.items(), key=lambda kv: float(kv[0])))


# --- substeps ------------------------------------------------------------------------------

def substeps(say=_say):
    rows = []
    n_f = 2048
    for drift in (0.15, 1.0, 2.0, 4.0):
        for frac in (0.0, 0.25, 0.5):
            # The whole track, sidelobes and all, inside the array: a positive drift runs to lower channels.
            shift = drift * N_T * TSAMP / abs(FOFF * 1e6)
            x0 = n_f / 2 + shift / 2 + frac
            lo, hi = x0 - shift - measure.NEIGHBOURS - 1, x0 + measure.NEIGHBOURS + 2
            if lo < 0 or hi > n_f:
                raise ValueError(f"the track at {drift} Hz/s leaves the {n_f}-channel test array")
            prof = {k: measure.plant(np.zeros((N_T, n_f)), [(x0, drift, 1.0)], TSAMP, FOFF, substeps=k)
                    for k in SUBSTEP_GRID}
            if abs(prof[256].sum() / N_T - measure.plant(np.zeros((N_T, 4 * n_f)), [(x0 + n_f, drift, 1.0)], TSAMP,
                                                          FOFF, substeps=256).sum() / N_T) > 1e-9:
                raise ValueError("power lost at the array's edge")
            ref = prof[256]
            for k in SUBSTEP_GRID:
                rows.append({"drift": drift, "start_fraction": frac, "substeps": k, "channels": n_f,
                             "max_bin_diff_over_peak": round(float(np.abs(prof[k] - ref).max() / ref.max()), 5),
                             "power_over_256": round(float(prof[k].sum() / ref.sum()), 6)})
    # The detector's S/N on the planted track near the cut, the same noise each time.
    det = []
    rng = np.random.default_rng(12)
    for drift in (1.0, 2.0, 4.0):
        for trial in range(20):
            noise = rng.chisquare(2 * N_FFT, size=(N_T, 16384)) * 1e3
            sigma = float(np.median(measure.channel_noise(noise)))
            x0 = 8000.3 + rng.uniform(0, 1)
            h = NEAR_CUT[drift] * sigma / math.sqrt(N_T)
            row = {"drift": drift, "trial": trial, "s_in": NEAR_CUT[drift]}
            for k in SUBSTEP_GRID:
                p = measure.plant(noise, [(x0, drift, h)], TSAMP, FOFF, substeps=k)
                hits = searching.search(p, FOFF, TSAMP, 2000.0)
                f = 2000.0 + x0 * FOFF
                m = [x["snr"] for x in hits if abs((x["frequency_mhz"] - f) * 1e6) <= matched.TOL_HZ
                     and abs(x["drift_hz_s"] - drift) <= matched.TOL_DRIFT]
                row[str(k)] = max(m) if m else None
            det.append(row)
    summary = {}
    for drift in (1.0, 2.0, 4.0):
        rs = [r for r in det if r["drift"] == drift and all(r[str(k)] is not None for k in SUBSTEP_GRID)]
        summary[str(drift)] = {str(k): {"mean_snr_minus_256": round(float(np.mean([r[str(k)] - r["256"] for r in rs])), 3),
                                        "found_of_20": sum(r[str(k)] is not None for r in det if r["drift"] == drift)}
                               for k in SUBSTEP_GRID} | {"trials_found_at_all": len(rs)}
    rec = {"profiles": rows, "detection_near_the_cut": det, "detection_s_in": {str(k): v for k, v in NEAR_CUT.items()}, "detection_summary": summary, "kind": "measured"}
    yoke.write(OUT / "injection_substeps.json", rec, indent=1, stamp=True)
    worst = max((r for r in rows if r["substeps"] == 32), key=lambda r: r["max_bin_diff_over_peak"])
    say(f"substeps: 32 against 256, worst bin {100 * worst['max_bin_diff_over_peak']:.2f}% of the peak "
        f"(drift {worst['drift']}), power {min(r['power_over_256'] for r in rows if r['substeps'] == 32):.5f} "
        f"at the least; detector S/N at 32 minus 256: "
        + ", ".join(f"{d} Hz/s {v['32']['mean_snr_minus_256']:+.3f}" for d, v in summary.items()))
    return rec


# --- voltage ------------------------------------------------------------------------------

def _voltage_look(rng, n_f, tones, n_t=N_T, pols=1):
    """One look: (power of the noise alone, power of noise plus the tones added
    to the voltages), summing N_FFT FFTs a spectrum and `pols` polarizations
    (Stokes I with 2). tones: (x0, drift, h); a tone's power is split equally
    between the polarizations, each with its own random phase."""
    plain = np.zeros((n_t, n_f))
    volt = np.zeros((n_t, n_f))
    per_channel = FOFF * 1e6
    offsets = np.arange(-measure.NEIGHBOURS, measure.NEIGHBOURS + 2)
    for t in range(n_t):
        acc = np.zeros(n_f)
        delta = np.zeros(n_f)
        for f in range(N_FFT):
            tau = (t + (f + 0.5) / N_FFT) * TSAMP
            for _ in range(pols):
                n = (rng.standard_normal(n_f) + 1j * rng.standard_normal(n_f)) * math.sqrt(0.5)
                p = n.real ** 2 + n.imag ** 2
                acc += p
                for x0, drift, h in tones:
                    x = x0 + drift * tau / per_channel
                    cells = int(math.floor(x)) + offsets
                    ok = (cells >= 0) & (cells < n_f)
                    a = math.sqrt(h / (N_FFT * pols)) * np.sinc(cells[ok] - x) * np.exp(1j * rng.uniform(0, 2 * math.pi))
                    v = n[cells[ok]] + a
                    delta[cells[ok]] += (v.real ** 2 + v.imag ** 2) - p[cells[ok]]
        plain[t] = acc
        volt[t] = acc + delta
    return plain, volt


def voltage(blocks=8, n_f=1048576, say=_say):
    """One polarization: power at 32 and 51 sub-steps and voltage, on the
    same noise. Two polarizations (Stokes I): power at 32 and voltage."""
    rows = {"power, 32 sub-steps (in use)": [], "power, 51 sub-steps": [], "voltage, 51 FFTs": [],
            "two polarizations: power, 32 sub-steps (in use)": [], "two polarizations: voltage, 51 FFTs": []}
    for b in range(blocks):
        rng = np.random.default_rng([12, 51, b])
        # The tones first, on a flat cadence of the right size, so the voltages can carry them.
        shape_cad = _cadence([np.ones((N_T, n_f))] * 6)
        ts = matched.tones(shape_cad, rng)
        for pols in (1, 2):
            sigma = math.sqrt(N_FFT * pols)            # one channel's noise in the summed power
            looks_plain, looks_volt = [], []
            for j in range(6):
                here = []
                if j in matched.TRUE:
                    for t in ts:
                        x, _ = matched.where(shape_cad, t, j)
                        here.append((x, t["drift"], t["s_in"] * sigma / math.sqrt(N_T)))
                pl, vo = _voltage_look(rng, n_f, here, pols=pols)
                looks_plain.append(pl)
                looks_volt.append(vo)
            cad = _cadence(looks_plain)
            judge = Judge(cad, WORK / f"voltage_{b}_{pols}")
            pre = "" if pols == 1 else "two polarizations: "
            for k in ((32, 51) if pols == 1 else (32,)):
                planted = []
                for j, raw in enumerate(looks_plain):
                    if j not in matched.TRUE:
                        planted.append(raw)
                        continue
                    here = [(matched.where(cad, t, j)[0], t["drift"], t["s_in"] * sigma / math.sqrt(N_T)) for t in ts]
                    planted.append(measure.plant(raw, here, TSAMP, FOFF, substeps=k))
                name = pre + ("power, 32 sub-steps (in use)" if k == 32 else "power, 51 sub-steps")
                rows[name] += judge.judge(f"p{k}", planted, ts)
            rows[pre + "voltage, 51 FFTs"] += judge.judge("v", looks_volt, ts)
            shutil.rmtree(WORK / f"voltage_{b}_{pols}", ignore_errors=True)
        say(f"voltage block {b}: " + "; ".join(f"{k}: {_totals(v)}" for k, v in rows.items()))
    pairs = {"power 32 against power 51 (sampling)": paired(rows["power, 32 sub-steps (in use)"],
                                                            rows["power, 51 sub-steps"]),
             "power 51 against voltage (the cross term)": paired(rows["power, 51 sub-steps"], rows["voltage, 51 FFTs"]),
             "power 32 against voltage": paired(rows["power, 32 sub-steps (in use)"], rows["voltage, 51 FFTs"]),
             "two polarizations: power 32 against voltage": paired(
                 rows["two polarizations: power, 32 sub-steps (in use)"], rows["two polarizations: voltage, 51 FFTs"])}
    rec = {"blocks": blocks, "channels": n_f, "fft_per_spectrum": N_FFT,
           "model": "complex Gaussian noise a channel an FFT; tone added before squaring; one or two polarizations; "
                    "no polyphase filterbank, no requantization, flat receiver response",
           "totals": {k: _totals(v) for k, v in rows.items()}, "paired": pairs,
           "largest_discordance": {k: _discordant(v) for k, v in pairs.items()},
           "by_strength": {k: _by_strength(v) for k, v in rows.items()}, "kind": "measured"}
    yoke.write(OUT / "injection_voltage.json", rec, indent=1, stamp=True)
    return rec


# --- dc ---------------------------------------------------------------------------------------

def dc_census():
    """How many of the finished experiments' planted signals cross a DC bin
    in any ON look: the DC bins' frequencies from the session's own header
    (fch1, foff and the coarse channel, one HDF5 chunk), each signal's
    frequency through each ON look from its record, a channel's width either
    side."""
    out = {}
    for target in ("KIC8462852", "HIP17147", "NGC6946"):
        db = store.connect_readonly()
        kept = store.cadence_files(db, target)
        db.close()
        if not kept:
            continue
        session, urls = kept
        idx = seti.reading.prepare(urls[:1])[0]
        a = idx["attrs"]
        fch1, foff = float(a["fch1"]), float(a["foff"])
        per, nchans = int(idx["chunk_shape"][-1]), int(idx["shape"][-1])
        dcs = np.array([fch1 + (k * per + per // 2) * foff for k in range(nchans // per)])
        width = abs(foff)
        base = matched.folder(target, session)
        n = crossing = 0
        for p in sorted(base.glob("block_*.json")):
            r = json.loads(p.read_text(encoding="utf-8"))
            t0 = r["tstarts"][0]
            here = dcs[(dcs >= r["from_mhz"] - 1) & (dcs <= r["to_mhz"] + 1)]
            for t in r["tones"]:
                n += 1
                hit = False
                for j in matched.TRUE:
                    dt = (r["tstarts"][j] - t0) * 86400
                    f_a = t["f_mhz"] + t["drift"] * dt / 1e6
                    f_b = f_a + t["drift"] * N_T * TSAMP / 1e6
                    if np.any((here >= min(f_a, f_b) - width) & (here <= max(f_a, f_b) + width)):
                        hit = True
                crossing += hit
        out[target] = {"signals": n, "crossing_dc_in_an_on_look": crossing, "coarse_channel": per,
                       "from": "the session's own header"}
    return out


def dc(blocks=6, n_f=1048576, per=65536, say=_say):
    """Each block: n_f channels in coarse channels of `per`, a tone crossing
    each coarse channel's DC bin in one ON look; planted then blanked (as the
    sky would be), and blanked then planted (as in use)."""
    rows = {"planted then blanked (as a real signal)": [], "blanked then planted (as in use)": []}
    strengths = matched.STRENGTHS
    drifts = (0.05, 0.1, 0.3, 0.8, 1.5, 3.0)
    for b in range(blocks):
        rng = np.random.default_rng([12, 0xDC, b])
        noise = [rng.chisquare(2 * N_FFT, size=(N_T, n_f)) * 1e3 for _ in range(6)]
        shape_cad = _cadence(noise, coarse=per)
        sig = [measure.channel_noise(x) for x in noise]
        ts = []
        for k in range(n_f // per):
            dc_ch = k * per + per // 2
            j_cross = matched.TRUE[k % 3]
            drift = float(drifts[(k + b) % len(drifts)]) * (1 if rng.random() < 0.5 else -1)
            dt = (shape_cad[j_cross]["s"]["tstart"] - shape_cad[0]["s"]["tstart"]) * 86400
            mid = dt + rng.uniform(0.2, 0.8) * N_T * TSAMP
            x0 = dc_ch - drift * mid / (FOFF * 1e6) + rng.uniform(-0.5, 0.5)
            ts.append({"x0": x0, "drift": drift, "s_in": strengths[(k + 3 * b) % len(strengths)], "dc_look": j_cross})
        # Both orders from the same noise; blank_dc on a whole-file layout (first channel 0, coarse `per`).
        real, in_use = [], []
        for j, raw in enumerate(noise):
            here = [(matched.where(shape_cad, t, j)[0], t["drift"], t["s_in"] * float(np.median(sig[j])) / math.sqrt(N_T))
                    for t in ts] if j in matched.TRUE else []
            a = measure.plant(raw, here, TSAMP, FOFF) if here else raw.copy()
            seti.blank_dc(a, 0, per)
            real.append(a)
            c = raw.copy()
            seti.blank_dc(c, 0, per)
            in_use.append(measure.plant(c, here, TSAMP, FOFF) if here else c)
        plain = []
        for raw in noise:
            c = raw.copy()
            seti.blank_dc(c, 0, per)
            plain.append(c)
        cad = _cadence(plain, coarse=per)
        judge = Judge(cad, WORK / f"dc_{b}")
        rows["planted then blanked (as a real signal)"] += judge.judge("real", real, ts)
        rows["blanked then planted (as in use)"] += judge.judge("in_use", in_use, ts)
        shutil.rmtree(WORK / f"dc_{b}", ignore_errors=True)
        say(f"dc block {b}: " + "; ".join(f"{k}: {_totals(v)}" for k, v in rows.items()))
    pr = paired(rows["blanked then planted (as in use)"], rows["planted then blanked (as a real signal)"])
    rec = {"blocks": blocks, "channels": n_f, "coarse_channel": per,
           "totals": {k: _totals(v) for k, v in rows.items()},
           "paired": {"in use against as a real signal": pr}, "largest_discordance": _discordant(pr),
           "by_strength": {k: _by_strength(v) for k, v in rows.items()},
           "census": dc_census(), "kind": "measured"}
    yoke.write(OUT / "injection_dc.json", rec, indent=1, stamp=True)
    say(f"dc census: {rec['census']}")
    return rec


# --- flux --------------------------------------------------------------------------------------

def flux(n_blocks=8, say=_say):
    """Constant injected power: eight blocks of the 2017 session, four crowded
    and four clean drawn at random (seed 12), read again and planted two ways
    with the same tones (their records' own)."""
    target = "KIC8462852"
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, target)
    db.close()
    base = matched.folder(target, session)
    meta = json.loads((base / "blocks.json").read_text(encoding="utf-8"))
    chosen = {int(b): c for b, c in meta["chosen"].items()}
    rng = np.random.default_rng(12)
    picks = sorted(int(b) for cls in ("crowded", "clean")
                   for b in rng.choice(sorted(b for b, c in chosen.items() if c == cls), n_blocks // 2, replace=False))
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    rows = {"fixed S_in in each ON look (in use)": [], "one injected power in all three ON looks": []}
    ratios = []
    for b in picks:
        rec = json.loads((base / f"block_{b:03d}.json").read_text(encoding="utf-8"))
        cad = matched._cadence(seti.read_looks(urls, *block_list[b]), urls)
        if [c["s"]["tstart"] for c in cad] != rec["tstarts"]:
            raise yoke.Refusal("INVALID_REQUEST", f"block {b} read again is not the one recorded")
        ts = rec["tones"]
        in_use = [p["spectra"] for p in matched.plant(cad, ts)]
        fixed = []
        t0 = cad[0]["s"]["tstart"]
        for j, look in enumerate(cad):
            if j not in matched.TRUE:
                fixed.append(look["raw"])
                continue
            s, raw = look["s"], look["raw"]
            dt = (s["tstart"] - t0) * 86400
            here = []
            for t in ts:
                x = t["x0"] + t["drift"] * dt / (s["foff"] * 1e6)
                c = int(min(max(round(x), 0), raw.shape[1] - 1))
                sig_on = [cad[i]["sigma"][min(max(int(round(t["x0"] + t["drift"] * (cad[i]["s"]["tstart"] - t0) * 86400
                                                            / (s["foff"] * 1e6))), 0), raw.shape[1] - 1)]
                          for i in matched.TRUE]
                ratios.append(float(look["sigma"][c] / np.mean(sig_on)))
                here.append((x, t["drift"], t["s_in"] * float(np.mean(sig_on)) / math.sqrt(raw.shape[0])))
            fixed.append(measure.plant(raw, here, s["tsamp"], s["foff"]))
        judge = Judge(cad, WORK / f"flux_{b}")
        rows["fixed S_in in each ON look (in use)"] += judge.judge("in_use", in_use, ts)
        rows["one injected power in all three ON looks"] += judge.judge("fixed", fixed, ts)
        shutil.rmtree(WORK / f"flux_{b}", ignore_errors=True)
        say(f"flux block {b} ({chosen[b]}): " + "; ".join(f"{k}: {_totals(v)}" for k, v in rows.items()))
    r = np.array(ratios)
    pr = paired(rows["fixed S_in in each ON look (in use)"], rows["one injected power in all three ON looks"])
    rec = {"target": target, "session": session, "blocks": picks, "sample": "4 crowded and 4 clean at random, seed 12",
           "what": "constant injected power in the spectra's own units, not calibrated flux",
           "paired": {"in use against one power": pr}, "largest_discordance": _discordant(pr),
           "noise_over_mean_of_on_looks": {"median": round(float(np.median(r)), 4),
                                           "p5_p95": [round(float(np.percentile(r, 5)), 4),
                                                      round(float(np.percentile(r, 95)), 4)]},
           "totals": {k: _totals(v) for k, v in rows.items()},
           "by_strength": {k: _by_strength(v) for k, v in rows.items()}, "kind": "measured"}
    yoke.write(OUT / "injection_power.json", rec, indent=1, stamp=True)
    return rec


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = {"substeps": substeps, "voltage": voltage, "dc": dc, "power": flux}
    todo = list(steps) if what == "all" else [what]
    for name in todo:
        if (OUT / f"injection_{name}.json").exists() and what == "all":
            _say(f"{name}: done before")
            continue
        steps[name]()


if __name__ == "__main__":
    main()
