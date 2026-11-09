"""Run in turboSETI's environment (setigen installed there): the planted
signals of measure.py's setigen check, made by setigen on an empty frame.

    python tools/setigen_frame.py OUT.npz
"""
import sys

import numpy as np
import setigen as stg

DF, DT, FCH1 = 2.7939677238464355, 18.253611008, 2269.628903e6   # Green Bank's finest product, block 153
N_F, N_T = 4096, 16
TONES = [(1000.3, 0.05), (1700.7, 0.5), (2400.1, 2.0), (3300.5, -3.5)]   # (start channel, drift Hz/s)

out = {}
for c0, drift in TONES:
    frame = stg.Frame(fchans=N_F, tchans=N_T, df=DF, dt=DT, fch1=FCH1, ascending=False)
    # A start between channels: the path's frequency at the first spectrum's start.
    f0 = FCH1 - c0 * DF
    frame.add_signal(stg.constant_path(f_start=f0, drift_rate=drift),
                     stg.constant_t_profile(level=1.0),
                     stg.sinc2_f_profile(width=2 * DF, width_mode="crossing"),
                     stg.constant_bp_profile(level=1.0),
                     doppler_smearing=True, smearing_subsamples=64)
    out[f"{c0}_{drift}"] = frame.get_data()
np.savez(sys.argv[1], **out)
print("ok", list(out))
