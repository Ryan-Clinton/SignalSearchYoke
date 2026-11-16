"""Why BLISS's CPU and GPU backends give different hits on the same look
(comparable.md step 11): its SNR plane rebuilt from the drift plane and the
noise it estimates (protohit_search.cpp's formula), the regions of cells
above half the cut joined at its neighbour distance (both backends grow a
hit through such cells), and each backend's hits placed in those regions.

    python tools/bliss/backend_components.py LOOK.h5 NCHANS [CUT] [NEIGHBOUR]

Run in BLISS's environment. It reports, per region holding any hit, how
many hits each backend puts there: one hit per region on the CPU and
several on the GPU is the CPU flooding a region whole where the GPU's
parallel labelling splits it.
"""
import sys
from collections import deque

import numpy as np
import os
from pathlib import Path

sys.path.insert(0, os.environ.get("BLISS_PYTHON_DIR", str(Path.home() / "ssy/bliss/build-cuda/bliss/python")))
import pybliss as bliss   # noqa: E402


def pipeline(path, n, device, cut, neighbour):
    sc = bliss.scan(path, n)
    sc.set_device(device)
    w = bliss.flaggers.flag_spectral_kurtosis(sc, .05, 25)
    o = bliss.estimators.noise_power_estimate_options()
    o.masked_estimate = True
    o.estimator_method = bliss.estimators.noise_power_estimator.stddev
    w = bliss.estimators.estimate_noise_power(w, o)
    io = bliss.integrate_drifts_options()
    io.desmear, io.low_rate_Hz_per_sec, io.high_rate_Hz_per_sec = True, -4.0, 4.0
    w = bliss.drift_search.integrate_drifts(w, io)
    ho = bliss.drift_search.hit_search_options()
    ho.snr_threshold, ho.neighbor_l1_dist = cut, neighbour
    hits = [(x.start_freq_index, x.rate_index, x.snr) for x in bliss.drift_search.hit_search(w, ho).hits()]
    return w, hits


def main():
    path, n = sys.argv[1], int(sys.argv[2])
    cut = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
    neighbour = int(sys.argv[4]) if len(sys.argv) > 4 else bliss.drift_search.hit_search_options().neighbor_l1_dist
    w, cpu = pipeline(path, n, "cpu", cut, neighbour)
    _, gpu = pipeline(path, n, "cuda:0", cut, neighbour)
    cc = w.read_coarse_channel(0)
    cc.set_device("cpu")
    dp = cc.integrated_drift_plane()
    q = dp.integrated_drifts
    q.set_device("cpu") if hasattr(q, "set_device") else None
    plane = np.from_dlpack(q).astype(np.float64)
    ne = cc.noise_estimate
    steps = int(np.from_dlpack(cc.data).shape[0]) if hasattr(cc.data, "__dlpack__") else 16
    info = dp.drift_rate_info() if callable(dp.drift_rate_info) else dp.drift_rate_info
    bins = np.array([d.desmeared_bins for d in info], dtype=np.float64)
    noise = ne.noise_power / np.sqrt(steps * bins)
    snr = (plane - ne.noise_floor) / noise[:, None]
    print(f"plane {plane.shape}, {steps} steps; CPU {len(cpu)} hits, GPU {len(gpu)}; neighbour distance {neighbour}")
    for name, hs in (("CPU", cpu), ("GPU", gpu)):
        ok = sum(abs(snr[r, c] - s) / s < 1e-3 for c, r, s in hs)
        print(f"{name}: the rebuilt SNR plane gives {ok} of its {len(hs)} hits' SNR within 0.1%")
    above = snr > cut / 2
    # BLISS's neighbourhood: |df| < d and |dr| < d - |df| (connected_components_cpu.cpp's loops)
    offs = [(dr, df) for df in range(-neighbour, neighbour) for dr in range(-neighbour + abs(df), neighbour - abs(df))]
    label = np.full(snr.shape, -1, dtype=np.int64)
    regions = 0
    for c, r, _ in sorted(cpu + gpu):
        if label[r, c] >= 0 or not above[r, c]:
            continue
        queue = deque([(r, c)])
        label[r, c] = regions
        while queue:
            y, x = queue.popleft()
            for dr, df in offs:
                yy, xx = y + dr, x + df
                if 0 <= yy < snr.shape[0] and 0 <= xx < snr.shape[1] and above[yy, xx] and label[yy, xx] < 0:
                    label[yy, xx] = regions
                    queue.append((yy, xx))
        regions += 1
    per = {}
    for name, hs in (("CPU", cpu), ("GPU", gpu)):
        for c, r, s in hs:
            per.setdefault(int(label[r, c]), {"CPU": [], "GPU": []})[name].append((c, r, round(s, 2)))
    split = {k: v for k, v in per.items() if len(v["CPU"]) != len(v["GPU"])}
    print(f"{len(per)} regions hold a hit; the backends put the same number of hits in {len(per) - len(split)}")
    for k, v in sorted(split.items(), key=lambda kv: -len(kv[1]["GPU"])):
        cells = int((label == k).sum()) if k >= 0 else 0
        print(f"  region {k}: {cells} cells above half the cut; CPU {len(v['CPU'])} hit(s) {v['CPU'][:3]}, "
              f"GPU {len(v['GPU'])} hit(s) {v['GPU'][:3]}{' ...' if len(v['GPU']) > 3 else ''}")


if __name__ == "__main__":
    main()
