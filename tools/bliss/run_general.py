"""tools/bliss_curves.py with its slice padding made general (pad.py), for
sessions whose slices are not the 2017 session's layout (step 12's, the
BLISS audit). Run in BLISS's environment in place of bliss_curves.py, with
the same arguments; bliss_curves.py itself is not changed, so the 2017
records keep their configuration. matched.py runs this when
SSY_BLISS_GENERAL=1 and records its hash in the configuration."""
import sys
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import bliss_curves  # noqa: E402
from pad import pad_to_coarse  # noqa: E402


def padded(src, out):
    """bliss_curves.padded for any slice inside one coarse channel."""
    with h5py.File(src) as s, h5py.File(out, "w") as d:
        for k, v in s.attrs.items():
            d.attrs[k] = v
        x = s["data"][:]
        first = int(s["data"].attrs.get("first_channel", 0))
        x, front = pad_to_coarse(x, first, bliss_curves.PER_COARSE)
        ds = d.create_dataset("data", data=x)
        for k, v in s["data"].attrs.items():
            ds.attrs[k] = v
        ds.attrs["nchans"] = x.shape[2]
        if front:
            ds.attrs["fch1"] = float(s["data"].attrs["fch1"]) - front * float(s["data"].attrs["foff"])
            ds.attrs["first_channel"] = first - front
        ds.attrs["DIMENSION_LABELS"] = np.array([b"time", b"feed_id", b"frequency"], dtype=object)
    return out, front


bliss_curves.padded = padded

if __name__ == "__main__":
    bliss_curves.main()
