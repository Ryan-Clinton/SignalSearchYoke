"""Run in BLISS's environment (WSL): BLISS's hits and events on a cadence's
six slices at several cuts and with several choices of which three looks
are ON (comparable.md step 11), as tools/turbo_curves.py does for turboSETI.

    python tools/bliss_curves.py OUT.json CUTS CHOICES F0.h5 F1.h5 F2.h5 F3.h5 F4.h5 F5.h5

F0..F5 in time order (the true cadence: ON, OFF, ON, OFF, ON, OFF), each a
block as seti.save writes it: one Green Bank coarse channel less its last
channel. CUTS: comma-separated SNRs. CHOICES: "all" (the 20 choices of three
ON looks) or "true" (0,2,4 only).

Each slice is copied with the coarse channel's missing channel padded (a
copy of its neighbour; the last, or the first with fch1 moved back a
channel, as the block was read) and the DIMENSION_LABELS attribute BLISS reads, the
spectra otherwise unchanged. Each look then goes through bliss_find_hits's
own steps and defaults on the GPU (normalize; the passband equalized with
the Green Bank response from bliss_generate_channelizer_response -f 1048576
-N 12 -M 256; spectral kurtosis 0.25/50/2 and sigma-clip 5/3/4 flags; the
masked standard-deviation noise; the drift search desmeared, ±4 Hz/s as the
other pipelines; connected components at neighbour distance 7; its hit
filter), once for each cut: its hit grouping depends on the cut (a hit grows
through cells above half of it), so a higher cut is not the lower one's hits
cut. Its event stage is tools/bliss/bliss_events.py (its event_search, run
on the hits found once), with each look's hits in a fixed order (channel,
then drift), the three ON looks of the choice in time order and the other
three as OFF.

The record keeps every look's hits at every cut (for this search's cadence
test on them) and BLISS's events for every choice and cut.
"""
import itertools
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "bliss"))
sys.path.insert(0, os.environ.get("BLISS_PYTHON_DIR", str(Path.home() / "ssy/bliss/build-cuda/bliss/python")))
import pybliss as bliss          # noqa: E402
import bliss_events              # noqa: E402

RESPONSE = os.environ.get("BLISS_RESPONSE", str(Path.home() / "ssy/gbt_response.f32"))
DEVICE = os.environ.get("BLISS_DEVICE", "cuda:0")
PER_COARSE = 1 << 20
MAX_DRIFT = 4.0
FIELDS = ("start_freq_index", "start_freq_MHz", "start_time_sec", "duration_sec", "rate_index",
          "drift_rate_Hz_per_sec", "power", "time_span_steps", "snr", "bandwidth", "binwidth")


def padded(src, out):
    """The slice as a whole coarse channel, with the attribute BLISS reads."""
    with h5py.File(src) as s, h5py.File(out, "w") as d:
        for k, v in s.attrs.items():
            d.attrs[k] = v
        x = s["data"][:]
        assert x.shape[2] == PER_COARSE - 1, f"{src}: {x.shape[2]} channels, not one coarse channel less one"
        # seti.blocks gives a block as MHz; read back, it starts on the coarse channel's first channel or one
        # after (the rounding differs by block), so the missing channel is the last or the first
        offset = int(s["data"].attrs.get("first_channel", 0)) % PER_COARSE
        assert offset in (0, 1), f"{src}: starts {offset} channels into its coarse channel"
        x = np.concatenate([x, x[:, :, -1:]] if offset == 0 else [x[:, :, :1], x], axis=2)
        ds = d.create_dataset("data", data=x)
        for k, v in s["data"].attrs.items():
            ds.attrs[k] = v
        ds.attrs["nchans"] = x.shape[2]
        if offset:
            ds.attrs["fch1"] = float(s["data"].attrs["fch1"]) - float(s["data"].attrs["foff"])
            ds.attrs["first_channel"] = int(s["data"].attrs["first_channel"]) - 1
        ds.attrs["DIMENSION_LABELS"] = np.array([b"time", b"feed_id", b"frequency"], dtype=object)
    return out


def look_hits(path, cut):
    """One look through bliss_find_hits's steps at one cut: (tstart MJD, duration s, hits)."""
    sc = bliss.scan(str(path), PER_COARSE)
    sc.set_device(DEVICE)
    p = bliss.preprocess.normalize(sc)
    p = bliss.preprocess.equalize_passband_filter(p, RESPONSE)
    p = bliss.flaggers.flag_spectral_kurtosis(p, 0.25, 50, 2)
    p = bliss.flaggers.flag_sigmaclip(p, 5, 3, 4)
    o = bliss.estimators.noise_power_estimate_options()
    o.masked_estimate = True
    o.estimator_method = bliss.estimators.noise_power_estimator.stddev
    p = bliss.estimators.estimate_noise_power(p, o)
    io = bliss.integrate_drifts_options()
    io.desmear, io.low_rate_Hz_per_sec, io.high_rate_Hz_per_sec = True, -MAX_DRIFT, MAX_DRIFT
    p = bliss.drift_search.integrate_drifts(p, io)
    ho = bliss.drift_search.hit_search_options()
    ho.snr_threshold, ho.neighbor_l1_dist = float(cut), 7
    h = bliss.drift_search.filter_hits(bliss.drift_search.hit_search(p, ho), bliss.drift_search.filter_options())
    hits = [{k: getattr(x, k) for k in FIELDS} for x in h.hits()]
    hits.sort(key=lambda x: (x["start_freq_index"], x["rate_index"]))
    ntsteps = int(h5py.File(path)["data"].shape[0])
    return float(sc.tstart), float(sc.tsamp) * ntsteps, hits


def row(j, h):
    return {"look": j, "channel": int(h["start_freq_index"]), "freq_mhz": float(h["start_freq_MHz"]),
            "drift_hz_s": float(h["drift_rate_Hz_per_sec"]), "snr": float(h["snr"]),
            "bandwidth_hz": float(h["bandwidth"]), "binwidth": int(h["binwidth"])}


def main():
    out = Path(sys.argv[1]).resolve()
    cuts = sorted(float(x) for x in sys.argv[2].split(","))
    which = sys.argv[3]
    files = [Path(p).resolve() for p in sys.argv[4:]]
    assert len(files) == 6
    choices = list(itertools.combinations(range(6), 3)) if which == "all" else [(0, 2, 4)]
    started = time.monotonic()
    looks = {}
    with tempfile.TemporaryDirectory() as tmp:
        paths = [padded(f, Path(tmp) / f"{j}.h5") for j, f in enumerate(files)]
        for cut in cuts:
            looks[cut] = [look_hits(p, cut) for p in paths]
    search_s = time.monotonic() - started
    record = {"cuts": cuts, "search_s": round(search_s, 1), "device": DEVICE,
              "hits": {str(c): [[row(j, h) for h in looks[c][j][2]] for j in range(6)] for c in cuts},
              "events": []}
    started = time.monotonic()
    for ons in choices:
        offs = [j for j in range(6) if j not in ons]
        for cut in cuts:
            on = [looks[cut][j] for j in ons]
            for k, (_, _, hs) in zip(ons, on):
                for h in hs:
                    h["_look"] = k
            found = bliss_events.event_search_fast(on, [looks[cut][j][2] for j in offs])
            rows = [{"snr": float(e["average_snr"]), "drift_hz_s": float(e["average_drift_rate_Hz_per_sec"]),
                     "freq_mhz": float(e["starting_frequency_Hz"]) / 1e6,
                     "hits": [row(h["_look"], h) for h in e["hits"]]} for e in found]
            record["events"].append({"as_on": list(ons), "cut": cut, "rows": rows})
    record["event_s"] = round(time.monotonic() - started, 1)
    out.write_text(json.dumps(record), encoding="utf-8")


if __name__ == "__main__":
    main()
