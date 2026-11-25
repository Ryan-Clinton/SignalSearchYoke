"""Checks of tools/setigen_plant.py, run inside setigen's own environment (docs/environments/setigen-windows.txt)
by tests/test_setigen_plant.py, which reads the JSON this prints. Synthetic noise only: nothing is read.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import setigen_plant as sp  # noqa: E402

DF_HZ = 2.7939677238464355
DT = 18.253611008
N_T, N_F = 16, 4096
FCH1 = 1400.0                       # MHz of channel 0


def noise(seed=1):
    return np.random.default_rng(seed).normal(10.0, 1.0, (1, N_T, N_F))


def added(looks, fch1, foff, x, drift, snr, smear):
    return sp.plant(looks, fch1, foff, DT, np.array([x], float), np.array(drift, float), np.array(snr, float),
                    smear)[0] - looks[0]


def centroid_offsets(a, x0, drift, foff_mhz):
    """Each spectrum's power-weighted channel, as Hz from the start-of-spectrum path f0 + drift * i * dt."""
    c = np.arange(a.shape[1])
    ch = (a * c).sum(1) / a.sum(1)
    return [float((ch[i] - x0) * foff_mhz * 1e6 - drift * i * DT) for i in range(a.shape[0])]


def main():
    out = {}
    looks = noise()
    asc = (FCH1, DF_HZ / 1e6)
    # the same data written in descending frequency: channel 0 is the top
    desc_fch1 = FCH1 + (N_F - 1) * DF_HZ / 1e6
    looks_desc = looks[:, :, ::-1].copy()
    x0 = 1500.0
    for smear in (False, True):
        tag = "smeared" if smear else "unsmeared"
        a = added(looks, *asc, [x0], [2.0], [200.0], smear)
        d = added(looks_desc, desc_fch1, -DF_HZ / 1e6, [N_F - 1 - x0], [2.0], [200.0], smear)
        out[f"{tag}_orientation_max_diff"] = float(np.abs(a - d[:, ::-1]).max())
        out[f"{tag}_offsets_hz"] = centroid_offsets(a, x0, 2.0, DF_HZ / 1e6)
        neg = added(looks, *asc, [x0 + 800], [-2.0], [200.0], smear)
        out[f"{tag}_negative_offsets_hz"] = centroid_offsets(neg, x0 + 800, -2.0, DF_HZ / 1e6)
        still = added(looks, *asc, [x0], [0.0], [200.0], smear)
        out[f"{tag}_power_ratio_drift_to_still"] = float(a.sum() / still.sum())
    # the strength setigen sets is the frame's noise estimate, made once: the same signals in either order, alone or
    # together, add the same
    xs, drifts, snrs = [500.0, 1500.0, 2500.0, 3500.0], [0.3, -1.5, 2.5, -3.5], [30.0, 400.0, 60.0, 200.0]
    for smear in (False, True):
        tag = "smeared" if smear else "unsmeared"
        fwd = added(looks, *asc, xs, drifts, snrs, smear)
        rev = added(looks, *asc, xs[::-1], drifts[::-1], snrs[::-1], smear)
        alone = sum(added(looks, *asc, [x], [d], [s], smear) for x, d, s in zip(xs, drifts, snrs))
        out[f"{tag}_order_max_diff"] = float(np.abs(fwd - rev).max())
        out[f"{tag}_alone_max_diff"] = float(np.abs(fwd - alone).max())
        out[f"{tag}_peak"] = float(fwd.max())
    # bounding each smeared signal changes nothing that matters
    keep = sp.BOUND_CHANNELS
    try:
        sp.BOUND_CHANNELS = 10 ** 7
        wide = added(looks, *asc, xs, drifts, snrs, True)
    finally:
        sp.BOUND_CHANNELS = keep
    bounded = added(looks, *asc, xs, drifts, snrs, True)
    out["bounded_max_diff"] = float(np.abs(wide - bounded).max())
    out["bounded_power_ratio"] = float(bounded.sum() / wide.sum())
    # a frame whose axis is off by more than a millihertz is refused
    import setigen as stg
    frame = stg.Frame.from_data(df=DF_HZ, dt=DT, fch1=FCH1 * 1e6 + 0.01, ascending=True, data=looks[0].copy())
    try:
        sp.axis_problem(frame.fs, FCH1 * 1e6, DF_HZ, N_F)
        out["axis_off_refused"] = False
    except SystemExit:
        out["axis_off_refused"] = True
    print(json.dumps(out))


if __name__ == "__main__":
    main()
