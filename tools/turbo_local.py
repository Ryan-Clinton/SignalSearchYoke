"""Run in turboSETI's environment: what turboSETI itself measures at one
line of one slice, with its own code (find_doppler.helper_functions.comp_stats
on the time-summed spectrum of the whole coarse channel, then (sum - median)
/ stddev), and what it reports there when run again with a low cut.

    python tools/turbo_local.py OUT.json F_MHZ DRIFT_HZ_S SNR_LOW FILE [QUIET_FILE]

QUIET_FILE, a slice of a quiet block of the same look, gives the same
statistics where nothing is crowding the channel, for comparison.
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import h5py
import hdf5plugin  # noqa: F401  (the slices are plain, but blimpy may want it)
import numpy as np
from turbo_seti.find_doppler.find_doppler import FindDoppler
from turbo_seti.find_doppler.helper_functions import comp_stats

out, f_mhz, drift, snr_low = Path(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
files = [Path(p).resolve() for p in sys.argv[5:]]


def stats(path, f=None, d=0.0):
    with h5py.File(path, "r") as h:
        data = h["data"]
        spectra = np.asarray(data[:, 0, :], dtype=np.float32)
        a = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in data.attrs.items()}
    fch1, foff, tsamp = float(a["fch1"]), float(a["foff"]), float(a["tsamp"])
    summed = spectra.sum(axis=0)
    median, stddev = comp_stats(summed, xp=np)
    rec = {"file": path.name, "median": float(median), "stddev": float(stddev),
           "stddev_over_median": float(stddev / median), "channels": int(spectra.shape[1])}
    if f is not None:
        n_t = spectra.shape[0]
        c0 = (f - fch1) / foff
        best = None
        for shift in range(-6, 7):          # the line's start to within six channels
            idx = [int(round(c0 + shift + d * t * tsamp / (foff * 1e6))) for t in range(n_t)]
            line = float(sum(spectra[t, i] for t, i in enumerate(idx)))
            snr = (line - float(median)) / float(stddev)
            if best is None or snr > best["snr"]:
                best = {"shift_channels": shift, "line_sum": line, "snr": snr}
        rec["line"] = best
        rec["line_over_median"] = best["line_sum"] / float(median)
        # What turboSETI's cut of 10 asks of a line here, as a multiple of the band's level.
        rec["cut10_over_median"] = (float(median) + 10 * float(stddev)) / float(median)
        # Its top-hit rule keeps a channel only if no channel within `distance` has a larger SNR (over all
        # drifts; the zero-drift SNR here is a lower bound on that). The largest beside the line:
        c = int(round(c0)) + best["shift_channels"]
        lo, hi = max(0, c - DISTANCE), min(spectra.shape[1], c + DISTANCE + 1)
        zero = (summed[lo:hi] - float(median)) / float(stddev)
        mask = np.abs(np.arange(lo, hi) - c) > 3
        j = int(np.argmax(np.where(mask, zero, -np.inf)))
        rec["largest_beside"] = {"snr_zero_drift": float(zero[j]), "offset_channels": lo + j - c,
                                 "offset_hz": (lo + j - c) * abs(foff) * 1e6}
    return rec


DRIFT_RES = 0.010204255741040042
DISTANCE = 2 * math.ceil(4.0 / DRIFT_RES)       # turboSETI's top-hit window, in channels


record = {"f_mhz": f_mhz, "drift_hz_s": drift, "files": []}
main = files[0]
here = stats(main, f_mhz, drift)
width_mhz = DISTANCE * 2.7939677238464355e-06
# turboSETI run again on the slice at a low cut, with its default smallest drift and with none:
# does it report the line, and what is beside it.
for label, min_drift in (("default_min_drift", 0.00001), ("min_drift_0", 0.0)):
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(main.parent)
        FindDoppler(main.name, max_drift=4.0, min_drift=min_drift, snr=snr_low, out_dir=tmp, n_coarse_chan=1,
                    log_level_int=40).search()
        rows = []
        for line in (Path(tmp) / (main.stem + ".dat")).read_text(errors="replace").splitlines():
            cols = line.split()
            if cols and not line.lstrip().startswith("#") and cols[0].isdigit():
                rows.append({"drift_hz_s": float(cols[1]), "snr": float(cols[2]), "frequency_mhz": float(cols[3])})
    near = sorted(rows, key=lambda r: abs(r["frequency_mhz"] - f_mhz))
    here[label] = {"snr_cut": snr_low, "min_drift": min_drift, "hits": len(rows), "nearest": near[:3],
                   "within_6_channels": [r for r in rows if abs(r["frequency_mhz"] - f_mhz) <= 6 * 2.794e-6]}
here["top_hit_window_mhz"] = width_mhz
record["files"].append(here)
for q in files[1:]:
    record["files"].append({"quiet": True, **stats(q)})
out.write_text(json.dumps(record, indent=1), encoding="utf-8")
print("ok")
