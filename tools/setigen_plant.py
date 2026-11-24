"""Signals planted by setigen (Brzycki et al. 2022), an injector independent of this project's measure.plant: run in
its own environment (docs/environments/setigen-windows.txt), called by tools/independent_injection.py.

    python setigen_plant.py IN.npz OUT.npz

IN holds `looks` (n, time, channel) float, `fch1` (MHz, channel 0), `foff` (MHz), `tsamp` (s), `x` (n, signals): each
signal's channel at each look's start (fractional), `drift` (Hz/s), `snr` (setigen's own S/N, integrated over the
look). setigen is given the data in ascending frequency, as its frames are indexed, and the result is turned back.
OUT holds `looks` with the signals added.
"""
import sys

import numpy as np
import setigen as stg


def plant(looks, fch1, foff, tsamp, x, drift, snr):
    out = np.empty_like(looks)
    width = abs(foff) * 1e6
    n_f = looks.shape[2]
    for j, data in enumerate(looks):
        flip = foff < 0
        asc = data[:, ::-1] if flip else data
        low = (fch1 + (n_f - 1) * foff) if flip else fch1            # MHz of ascending channel 0
        frame = stg.Frame.from_data(df=width, dt=tsamp, fch1=low * 1e6, ascending=True, data=asc.astype(float).copy())
        if not np.isclose(frame.fs[0], low * 1e6):
            raise SystemExit("setigen_plant.py: the frame's frequencies are not the data's")
        for xi, d, s in zip(x[j], drift, snr):
            f_hz = (fch1 + xi * foff) * 1e6
            frame.add_signal(stg.constant_path(f_start=f_hz, drift_rate=float(d)),
                             stg.constant_t_profile(level=frame.get_intensity(snr=float(s))),
                             stg.sinc2_f_profile(width=2 * width), stg.constant_bp_profile(level=1))
        got = frame.get_data()
        out[j] = got[:, ::-1] if flip else got
    return out


def main():
    data = np.load(sys.argv[1])
    looks = plant(data["looks"], float(data["fch1"]), float(data["foff"]), float(data["tsamp"]), data["x"],
                  data["drift"], data["snr"])
    np.savez(sys.argv[2], looks=looks)


if __name__ == "__main__":
    main()
