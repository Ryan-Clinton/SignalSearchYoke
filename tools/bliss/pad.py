"""A slice made one whole coarse channel for BLISS, for any slice inside one
coarse channel (tools/bliss/run_general.py; the BLISS audit, docs/audits.md
7). tools/bliss_curves.py's own padded() takes only the 2017 session's
layout, one channel short of a coarse channel starting at its first or
second channel; this takes any, and gives the same array as padded() on that
layout (tests/test_bliss_pad.py)."""
import numpy as np


def pad_to_coarse(x, first_channel, per):
    """x (time, feed, channel), its first channel in the file and the coarse
    channel's size: (the array of `per` channels, channels put in front). The
    channels added repeat the slice's first and last, as padded() does.
    Refuses a slice that runs past its coarse channel's end."""
    n = x.shape[2]
    front = int(first_channel) % per
    back = per - front - n
    if back < 0:
        raise ValueError(f"{n} channels from {front} into a coarse channel of {per}: past its end")
    parts = []
    if front:
        parts.append(np.repeat(x[:, :, :1], front, axis=2))
    parts.append(x)
    if back:
        parts.append(np.repeat(x[:, :, -1:], back, axis=2))
    return (np.concatenate(parts, axis=2) if len(parts) > 1 else x), front
