"""Signals planted by setigen (Brzycki et al. 2022), an injector independent of this project's measure.plant: run in
its own environment (docs/environments/setigen-windows.txt), called by tools/independent_injection.py.

    python setigen_plant.py IN.npz OUT.npz

IN holds `looks` (n, time, channel) float, `fch1` (MHz, channel 0), `foff` (MHz), `tsamp` (s), `x` (n, signals): each
signal's channel at each look's start (fractional), `drift` (Hz/s), `snr` (setigen's own S/N, integrated over the
look), and `smear` (optional, default off): setigen's Doppler smearing, which spreads each spectrum's tone over
the channels it crosses while the spectrum is taken, as a real tone is. Without it setigen puts the tone where it is at
the spectrum's start, half a spectrum's drift from where the scoring looks (docs/independent-injection.md). setigen is
given the data in ascending frequency, as its frames are indexed, and the result is turned back. OUT holds `looks`
with the signals added.
"""
import sys

import numpy as np
import setigen as stg

BOUND_CHANNELS = 200


AXIS_TOL_HZ = 1e-3      # the frame's axis must be the data's to a millihertz (the scoring's tolerance is 6 Hz)


def axis_problem(fs, low_hz, width_hz, n_f):
    """Refuses a frame whose frequency axis is not the data's: both ends and the channel width, absolutely, with no
    relative tolerance (at 1.4 GHz a relative 1e-5 would allow 14 kHz)."""
    want = (low_hz, low_hz + (n_f - 1) * width_hz)
    got = (float(fs[0]), float(fs[-1]))
    step = float(fs[1] - fs[0]) if len(fs) > 1 else width_hz
    if len(fs) != n_f or any(abs(g - w) > AXIS_TOL_HZ for g, w in zip(got, want)) or abs(step - width_hz) > 1e-5:
        raise SystemExit(f"setigen_plant.py: the frame's frequencies are not the data's: {got} against {want}, "
                         f"channels {step} Hz against {width_hz}")


def plant(looks, fch1, foff, tsamp, x, drift, snr, smear=False):
    out = np.empty_like(looks)
    width = abs(foff) * 1e6
    n_f = looks.shape[2]
    for j, data in enumerate(looks):
        flip = foff < 0
        asc = data[:, ::-1] if flip else data
        low = (fch1 + (n_f - 1) * foff) if flip else fch1            # MHz of ascending channel 0
        frame = stg.Frame.from_data(df=width, dt=tsamp, fch1=low * 1e6, ascending=True, data=asc.astype(float).copy())
        axis_problem(frame.fs, low * 1e6, width, n_f)
        for xi, d, s in zip(x[j], drift, snr):
            f_hz = (fch1 + xi * foff) * 1e6
            # With smearing, setigen works each signal out over the whole frame unless bounded: bound it to the
            # channels its track crosses and BOUND_CHANNELS either side (checked: the same placement and power)
            end = f_hz + float(d) * data.shape[0] * tsamp
            bound = ({"bounding_f_range": (min(f_hz, end) - BOUND_CHANNELS * width, max(f_hz, end) + BOUND_CHANNELS * width)}
                     if smear else {})
            frame.add_signal(stg.constant_path(f_start=f_hz, drift_rate=float(d)),
                             stg.constant_t_profile(level=frame.get_intensity(snr=float(s))),
                             stg.sinc2_f_profile(width=2 * width), stg.constant_bp_profile(level=1),
                             doppler_smearing=bool(smear), **bound)
        got = frame.get_data()
        out[j] = got[:, ::-1] if flip else got
    return out


def main():
    data = np.load(sys.argv[1])
    looks = plant(data["looks"], float(data["fch1"]), float(data["foff"]), float(data["tsamp"]), data["x"],
                  data["drift"], data["snr"], bool(data["smear"]) if "smear" in data else False)
    np.savez(sys.argv[2], looks=looks)


if __name__ == "__main__":
    main()
