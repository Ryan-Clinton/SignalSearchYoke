"""Run in turboSETI's environment: turboSETI's events on a cadence's six
slices at several cuts and with several choices of which three looks are ON
(comparable.md steps 4 and 7).

    python tools/turbo_curves.py OUT.json CUTS CHOICES F0.h5 F1.h5 F2.h5 F3.h5 F4.h5 F5.h5

F0..F5 in time order (the true cadence: ON, OFF, ON, OFF, ON, OFF). CUTS:
comma-separated SNRs, e.g. 5,6,8,10,15. CHOICES: "all" (the 20 choices of
three ON looks) or "true" (0,2,4 only).

Its hit search (FindDoppler, ±4 Hz/s, its default min_drift 1e-5: it searches
only |drift| > min_drift, so not the zero-drift trial; check_zero_drift in the
event stage cannot bring back hits never found) runs once per file at the lowest
cut. At a higher cut X every table is
cut to SNR > X before its event stage, ON and OFF alike: the same as its hit
search run at X, since its top-hit rule compares each channel with its
neighbours' largest SNR whatever the cut. (Its own SNR_cut would cut only the
ON table and keep every lower OFF hit as a veto.) Its event stage
(find_event.find_events, filter threshold 3) then runs on the six tables in
the chosen order: the three ON looks in time order, each followed by the
next OFF look in time order.
"""
import contextlib
import io
import itertools
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from turbo_seti.find_doppler.find_doppler import FindDoppler
import blimpy.io.base_reader as _blimpy_reader  # noqa: E402

# blimpy sizes what it loads by the memory free when a file is opened (less 1 GB); with another
# program holding most of the RAM it keeps the data on disk and turboSETI then sees one spectrum
# ("data shape = (1,)", 19 Nov 2026). A slice here is tens of MB, so a floor of 4 GB only stops that
# refusal: what is read, and every hit, is unchanged.
_reader_init = _blimpy_reader.Reader.__init__


def _reader_init_with_floor(self):
    _reader_init(self)
    self.max_data_array_size = max(self.max_data_array_size, 4 * _blimpy_reader.GIGA)


_blimpy_reader.Reader.__init__ = _reader_init_with_floor
from turbo_seti.find_event import find_event

out = Path(sys.argv[1]).resolve()
cuts = sorted(float(x) for x in sys.argv[2].split(","))
which = sys.argv[3]
files = [Path(p).resolve() for p in sys.argv[4:]]
assert len(files) == 6
choices = list(itertools.combinations(range(6), 3)) if which == "all" else [(0, 2, 4)]

started = time.monotonic()
tables = []
with tempfile.TemporaryDirectory() as tmp:
    for f in files:
        os.chdir(f.parent)      # turboSETI joins its output folder to the bare name (breaks with a full path on Windows)
        FindDoppler(f.name, max_drift=4.0, snr=cuts[0], out_dir=tmp, n_coarse_chan=1, log_level_int=40).search()
        with contextlib.redirect_stdout(io.StringIO()):
            t = find_event.read_dat(str(Path(tmp) / (f.stem + ".dat")))
        t["Source"] = "cadence"    # one name: its event stage refuses ON tables of two sources
        tables.append(t)
search_s = time.monotonic() - started

def above(t, cut):
    return t[t["SNR"] > cut] if "SNR" in t else t


cached = {}
real_read = find_event.read_dat
find_event.read_dat = lambda name: cached[name].copy()
record = {"cuts": cuts, "search_s": round(search_s, 1),
          "hits": {str(c): [len(above(t, c)) for t in tables] for c in cuts}, "events": []}
for ons in choices:
    offs = [j for j in range(6) if j not in ons]
    order = [x for pair in zip(ons, offs) for x in pair]
    for cut in cuts:
        names = []
        for j in order:
            name = f"look{j}.dat"
            cached[name] = above(tables[j], cut)
            names.append(name)
        with contextlib.redirect_stdout(io.StringIO()):
            found = find_event.find_events(names, check_zero_drift=True, filter_threshold=3, on_off_first="ON")
        rows = []
        if found is not None and len(found):
            for _, r in found.iterrows():
                k = int(str(r["status"]).rsplit("_", 1)[-1])         # on_table_1..3: the k-th ON look of the choice
                rows.append({"look": ons[k - 1], "hit_id": str(r.get("Hit_ID", "")), "freq_mhz": float(r["Freq"]),
                             "freq_start_mhz": float(r["FreqStart"]), "freq_end_mhz": float(r["FreqEnd"]),
                             "drift_hz_s": float(r["DriftRate"]), "snr": float(r["SNR"])})
        record["events"].append({"as_on": list(ons), "cut": cut, "rows": rows})
find_event.read_dat = real_read
if which == "true":     # a planted run: every hit too, to see where a planted signal was lost
    record["look_hits"] = [[{"freq_mhz": float(r["Freq"]), "drift_hz_s": float(r["DriftRate"]), "snr": float(r["SNR"])}
                            for _, r in t.iterrows()] if "SNR" in t else [] for t in tables]
record["total_s"] = round(time.monotonic() - started, 1)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(record), encoding="utf-8")
print("ok", record["total_s"])
