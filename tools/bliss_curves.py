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
masked standard-deviation noise; the drift search desmeared, Ã‚Â±4 Hz/s as the
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
import ctypes
import hashlib
import itertools
import json
import os
import resource
import subprocess
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
    """The slice as a whole coarse channel, with the attribute BLISS reads:
    (its path, how many channels were put in front of the slice's first)."""
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
    return out, offset


def _flagged(path):
    """One look through bliss_find_hits's steps up to its flags: the scan
    and the pipeline object."""
    sc = bliss.scan(str(path), PER_COARSE)
    sc.set_device(DEVICE)
    p = bliss.preprocess.normalize(sc)
    p = bliss.preprocess.equalize_passband_filter(p, RESPONSE)
    p = bliss.flaggers.flag_spectral_kurtosis(p, 0.25, 50, 2)
    p = bliss.flaggers.flag_sigmaclip(p, 5, 3, 4)
    return sc, p


def look_hits(path, cut, unfiltered=False, order="sorted"):
    """One look through bliss_find_hits's steps at one cut: (tstart MJD,
    duration s, hits, and with `unfiltered` the hits before its hit filter).
    order "sorted": by channel, then drift (the event stage's input);
    "native": as BLISS returns them."""
    sc, p = _flagged(path)
    o = bliss.estimators.noise_power_estimate_options()
    o.masked_estimate = True
    o.estimator_method = bliss.estimators.noise_power_estimator.stddev
    p = bliss.estimators.estimate_noise_power(p, o)
    io = bliss.integrate_drifts_options()
    io.desmear, io.low_rate_Hz_per_sec, io.high_rate_Hz_per_sec = True, -MAX_DRIFT, MAX_DRIFT
    p = bliss.drift_search.integrate_drifts(p, io)
    ho = bliss.drift_search.hit_search_options()
    ho.snr_threshold, ho.neighbor_l1_dist = float(cut), 7
    found = bliss.drift_search.hit_search(p, ho)
    h = bliss.drift_search.filter_hits(found, bliss.drift_search.filter_options())

    def listed(x):
        hs = [{k: getattr(y, k) for k in FIELDS} for y in x.hits()]
        if order == "sorted":
            hs.sort(key=lambda y: (y["start_freq_index"], y["rate_index"]))
        return hs
    ntsteps = int(h5py.File(path)["data"].shape[0])
    return float(sc.tstart), float(sc.tsamp) * ntsteps, listed(h), (listed(found) if unfiltered else None)


def track_flags(path, offset, tracks):
    """The share of each track's spectra (tracks: [[channel at the look's
    start in the slice, Hz/s]]) on a channel BLISS's flags mark, in the
    look at `path`; a track's spectra outside the band are left out."""
    sc, p = _flagged(path)
    cc = p.read_coarse_channel(0)
    cc.set_device("cpu")
    m = np.from_dlpack(cc.mask)
    m = m.reshape(m.shape[0], -1)
    n_t, n_f = m.shape
    per_channel = float(sc.foff) * 1e6
    out = []
    for x, drift in tracks:
        ch = np.rint(x + offset + drift * (np.arange(n_t) + 0.5) * float(sc.tsamp) / per_channel).astype(int)
        inside = (ch >= 0) & (ch < n_f)
        out.append(round(float((m[np.arange(n_t)[inside], ch[inside]] != 0).mean()), 4) if inside.any() else None)
    return out


def row(j, h):
    return {"look": j, "channel": int(h["start_freq_index"]), "freq_mhz": float(h["start_freq_MHz"]),
            "drift_hz_s": float(h["drift_rate_Hz_per_sec"]), "snr": float(h["snr"]),
            "bandwidth_hz": float(h["bandwidth"]), "binwidth": int(h["binwidth"])}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]


def _run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def provenance():
    """What ran: BLISS's checkout and its local changes, its module, CUDA, the
    GPU, the packages, the response file and this tool's own files."""
    module = Path(bliss.__file__).resolve()
    repo = next((q for q in module.parents if (q / ".git").exists()), None)
    diff = _run("git", "-C", str(repo), "diff") if repo else None
    try:
        rt = ctypes.c_int()
        ctypes.CDLL("libcudart.so").cudaRuntimeGetVersion(ctypes.byref(rt))
        cuda = rt.value
    except OSError:
        cuda = None
    return {"bliss_checkout": _run("git", "-C", str(repo), "rev-parse", "HEAD") if repo else None,
            "bliss_local_changes_sha": hashlib.sha256(diff.encode()).hexdigest()[:16] if diff else None,
            "pybliss": str(module), "cuda_runtime": cuda, "device": DEVICE,
            "gpu": _run("nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"),
            "python": sys.version.split()[0], "numpy": np.__version__, "h5py": h5py.__version__,
            "response": RESPONSE, "response_sha": _sha(RESPONSE),
            "tool_sha": {"bliss_curves.py": _sha(__file__), "bliss_events.py": _sha(HERE / "bliss" / "bliss_events.py")},
            "steps": {"normalize": True, "equalize": "response", "spectral_kurtosis": [0.25, 50, 2],
                      "sigmaclip": [5, 3, 4], "noise": "stddev, masked", "drift_hz_s": [-MAX_DRIFT, MAX_DRIFT],
                      "desmear": True, "hits": "connected components, neighbour distance 7",
                      "filter": "bliss_find_hits's defaults", "event_order": "channel, then drift"}}


SHUFFLES = int(os.environ.get("BLISS_SHUFFLES", "3"))     # extra hit orders the event stage is also run with


def _events(looks, cut, ons, shuffle=None):
    """BLISS's event stage on the looks' hits at `cut` with `ons` as the ON
    looks. shuffle: a seed, to give each look's hits in a random order
    instead (BLISS's GPU returns them in an order that changes from run to
    run, and its event stage pairs greedily, so the order matters)."""
    offs = [j for j in range(6) if j not in ons]
    on = [looks[cut][j][:3] for j in ons]
    for k, (_, _, hs) in zip(ons, on):
        for h in hs:
            h["_look"] = k
    if shuffle is not None:
        rng = np.random.default_rng([shuffle, int(cut * 10)])
        order = {j: rng.permutation(len(looks[cut][j][2])) for j in range(6)}
        on = [(t0, d, [hs[i] for i in order[j]]) for j, (t0, d, hs) in zip(ons, on)]
        off = [[looks[cut][j][2][i] for i in order[j]] for j in offs]
    else:
        off = [looks[cut][j][2] for j in offs]
    return bliss_events.event_search_fast(on, off)


def _rows(found):
    return [{"snr": float(e["average_snr"]), "drift_hz_s": float(e["average_drift_rate_Hz_per_sec"]),
             "freq_mhz": float(e["starting_frequency_Hz"]) / 1e6,
             "hits": [row(h["_look"], h) for h in e["hits"]]} for e in found]


def main():
    args = sys.argv[1:]
    if args and args[0] == "selftest":
        return selftest(args[1:])
    tones = None
    if args[0] == "--tones":
        tones = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        args = args[2:]
    out = Path(args[0]).resolve()
    cuts = sorted(float(x) for x in args[1].split(","))
    which = args[2]
    files = [Path(p).resolve() for p in args[3:]]
    assert len(files) == 6
    choices = list(itertools.combinations(range(6), 3)) if which == "all" else [(0, 2, 4)]
    started = time.monotonic()
    looks, flags = {}, {}
    with tempfile.TemporaryDirectory() as tmp:
        paths = [padded(f, Path(tmp) / f"{j}.h5") for j, f in enumerate(files)]
        for cut in cuts:
            looks[cut] = [look_hits(p, cut, unfiltered=tones is not None) for p, _ in paths]
        if tones is not None:
            flags = {j: track_flags(*paths[int(j)], tr) for j, tr in tones.items()}
    search_s = time.monotonic() - started
    record = {"cuts": cuts, "search_s": round(search_s, 1), "device": DEVICE,
              "hits": {str(c): [[row(j, h) for h in looks[c][j][2]] for j in range(6)] for c in cuts},
              "events": [], "provenance": provenance()}
    if tones is not None:
        record["hits_unfiltered"] = {str(c): [[row(j, h) for h in looks[c][j][3]] for j in range(6)] for c in cuts}
        record["tones_flagged"] = flags
    started = time.monotonic()
    record["events_shuffled"] = {str(k): [] for k in range(SHUFFLES)}
    for ons in choices:
        for cut in cuts:
            record["events"].append({"as_on": list(ons), "cut": cut, "rows": _rows(_events(looks, cut, ons))})
            for k in range(SHUFFLES):
                record["events_shuffled"][str(k)].append(
                    {"as_on": list(ons), "cut": cut, "rows": _rows(_events(looks, cut, ons, shuffle=k))})
    record["event_s"] = round(time.monotonic() - started, 1)
    record["peak_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    out.write_text(json.dumps(record), encoding="utf-8")


def _key(evs):
    return [[(h["_look"] if "_look" in h else None, h["start_freq_MHz"], h["drift_rate_Hz_per_sec"], h["snr"])
             for h in e["hits"]] for e in evs]


def _random_cadence(rng):
    """Six looks of hits, crowded around a few frequencies so the matching
    and the OFF veto have work to do."""
    looks = []
    centres = rng.uniform(1000, 1001, rng.integers(1, 6))
    for j in range(6):
        hs = []
        for _ in range(int(rng.integers(0, 40))):
            hs.append({"start_freq_MHz": float(rng.choice(centres) + rng.normal(0, 2e-5)),
                       "drift_rate_Hz_per_sec": float(rng.choice([rng.uniform(-4, 4), 0.0, 0.5])),
                       "snr": float(rng.uniform(5, 50)), "power": float(rng.uniform(1, 1e9)),
                       "bandwidth": float(rng.uniform(1, 30)), "start_time_sec": 300.0 * j,
                       "duration_sec": 292.0, "_look": j})
        looks.append((57000 + j * 300 / 86400, 292.0, hs))
    return looks


def selftest(args):
    """python tools/bliss_curves.py selftest OUT.json F0..F5: the GPU's hits
    on repeated runs (every field), the event stage with BLISS's own hit
    order against the sorted order, and the event stage's array version
    against the line-for-line port on random cadences."""
    out, files = Path(args[0]).resolve(), [Path(p).resolve() for p in args[1:7]]
    rng = np.random.default_rng(11)
    res = {"random_cadences": 0, "random_differ": 0}
    for _ in range(300):
        looks = _random_cadence(rng)
        for ons in [(0, 2, 4), tuple(sorted(rng.choice(6, 3, replace=False)))]:
            on = [looks[j] for j in ons]
            off = [looks[j][2] for j in range(6) if j not in ons]
            res["random_cadences"] += 1
            res["random_differ"] += _key(bliss_events.event_search(on, off)) != \
                _key(bliss_events.event_search_fast(on, off))
    if files:
        res["repeat"], res["order"] = {}, {}
        with tempfile.TemporaryDirectory() as tmp:
            paths = [padded(f, Path(tmp) / f"{j}.h5")[0] for j, f in enumerate(files)]
            for cut in (5.0, 10.0):
                a = [look_hits(p, cut, order="native") for p in paths]
                b = [look_hits(p, cut, order="native") for p in paths]
                # time_span_steps differs from run to run in every hit (it looks unset); nothing here reads it
                used = [k for k in FIELDS if k != "time_span_steps"]

                def rows_of(x):
                    return [tuple(h[k] for k in used) for h in x[2]]
                res["repeat"][str(cut)] = {
                    "hits": [len(x[2]) for x in a],
                    "same_set": [sorted(rows_of(x)) == sorted(rows_of(y)) for x, y in zip(a, b)],
                    "same_order": [rows_of(x) == rows_of(y) for x, y in zip(a, b)],
                    "time_span_steps_same": [[h["time_span_steps"] for h in x[2]] == [h["time_span_steps"] for h in y[2]]
                                             for x, y in zip(a, b)]}
                runs = {"native_a": {cut: a}, "native_b": {cut: b},
                        "sorted": {cut: [(t0, d, sorted(h, key=lambda y: (y["start_freq_index"], y["rate_index"])), None)
                                         for t0, d, h, _ in a]}}
                res["order"][str(cut)] = {}
                for ons in itertools.combinations(range(6), 3):
                    ev = {k: {json.dumps(e) for e in _key(_events(v, cut, ons))} for k, v in runs.items()}
                    res["order"][str(cut)][str(ons)] = {
                        "native_a": len(ev["native_a"]), "native_b": len(ev["native_b"]), "sorted": len(ev["sorted"]),
                        "native_a_and_b": len(ev["native_a"] & ev["native_b"]),
                        "native_a_and_sorted": len(ev["native_a"] & ev["sorted"])}
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "order"}))
    if "order" in res:
        for c, by in res["order"].items():
            print(c, "events summed over the 20 choices:",
                  {k: sum(v[k] for v in by.values()) for k in next(iter(by.values()))})


if __name__ == "__main__":
    main()
