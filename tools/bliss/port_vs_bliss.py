"""tools/bliss/bliss_events.py against BLISS's own event_search
(comparable.md step 11), on the same hits: segments of a block's six looks,
several cuts, the CPU backend (whose hits come in a fixed order, so both
see them in the same order). Every event's members compared, not counts.

    python tools/bliss/port_vs_bliss.py OUT.json WIDTH CUTS F0.h5 ... F5.h5

Run in BLISS's environment, with its module built with
event_search_off_hits_once.patch (BLISS's own event stage otherwise runs the
drift search again for every candidate and every OFF look). Segments of
WIDTH channels are taken at PORT_SEGMENTS (default 4) places across the block; a whole block
does not fit, as BLISS's event stage keeps every pair of hits it compares.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, os.environ.get("BLISS_PYTHON_DIR", str(Path.home() / "ssy/bliss/build-cuda/bliss/python")))
import bliss_events        # noqa: E402
import pybliss as bliss    # noqa: E402

FIELDS = ("start_freq_index", "start_freq_MHz", "start_time_sec", "duration_sec", "rate_index",
          "drift_rate_Hz_per_sec", "power", "time_span_steps", "snr", "bandwidth", "binwidth")


def segment(src, out, start, width):
    with h5py.File(src) as s, h5py.File(out, "w") as d:
        for k, v in s.attrs.items():
            d.attrs[k] = v
        ds = d.create_dataset("data", data=s["data"][:, :, start:start + width])
        for k, v in s["data"].attrs.items():
            ds.attrs[k] = v
        ds.attrs["nchans"] = width
        ds.attrs["fch1"] = float(s["data"].attrs["fch1"]) + start * float(s["data"].attrs["foff"])
        ds.attrs["DIMENSION_LABELS"] = np.array([b"time", b"feed_id", b"frequency"], dtype=object)
    return str(out)


def run(files, width, cut):
    cad = bliss.cadence([[files[0], files[2], files[4]], [files[1]], [files[3]], [files[5]]], width)
    cad.set_device("cpu")
    w = bliss.flaggers.flag_spectral_kurtosis(cad, .05, 25)
    o = bliss.estimators.noise_power_estimate_options()
    o.masked_estimate = True
    o.estimator_method = bliss.estimators.noise_power_estimator.stddev
    w = bliss.estimators.estimate_noise_power(w, o)
    io = bliss.integrate_drifts_options()
    io.desmear, io.low_rate_Hz_per_sec, io.high_rate_Hz_per_sec = True, -4.0, 4.0
    w = bliss.drift_search.integrate_drifts(w, io)
    ho = bliss.drift_search.hit_search_options()
    ho.snr_threshold = cut
    h = bliss.drift_search.hit_search(w, ho)
    t = time.monotonic()
    theirs = bliss.drift_search.event_search(h)
    t_theirs = time.monotonic() - t

    def hits_of(sc):
        return [{k: getattr(x, k) for k in FIELDS} for x in sc.hits()]
    on = [(sc.tstart, sc.tsamp * 16, hits_of(sc)) for sc in h.observations[0].scans]
    off = [hits_of(sc) for ob in h.observations[1:] for sc in ob.scans]
    t = time.monotonic()
    mine = bliss_events.event_search_fast(on, off)
    t_mine = time.monotonic() - t

    def key_theirs(e):
        return [e.starting_frequency_Hz, [(x.start_freq_index, x.rate_index, x.snr) for x in e.hits]]

    def key_mine(e):
        return [e["starting_frequency_Hz"], [(x["start_freq_index"], x["rate_index"], x["snr"]) for x in e["hits"]]]
    a, b = [key_theirs(e) for e in theirs], [key_mine(e) for e in mine]
    return {"hits_on": [len(x[2]) for x in on], "hits_off": [len(x) for x in off], "bliss_events": len(a),
            "port_events": len(b), "identical": a == b, "bliss_s": round(t_theirs, 1), "port_s": round(t_mine, 2)}


def main():
    out, width, cuts = Path(sys.argv[1]), int(sys.argv[2]), [float(x) for x in sys.argv[3].split(",")]
    files = sys.argv[4:10]
    n = h5py.File(files[0])["data"].shape[2]
    starts = [int(x) for x in np.linspace(0, n - width, int(os.environ.get("PORT_SEGMENTS", "4")))]
    res = []
    with tempfile.TemporaryDirectory() as tmp:
        for start in starts:
            seg = [segment(f, Path(tmp) / f"{j}.h5", start, width) for j, f in enumerate(files)]
            for cut in cuts:
                r = dict(run(seg, width, cut), start=start, cut=cut)
                res.append(r)
                print(json.dumps(r), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"{sum(r['identical'] for r in res)} of {len(res)} identical; "
          f"{sum(r['bliss_events'] for r in res)} events in all")


if __name__ == "__main__":
    main()
