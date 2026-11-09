"""Run in turboSETI's environment: Price et al. 2020's own pipeline on a
cadence's six slices. turboSETI's hit search (±4 Hz/s, SNR 10) on each, then
its event pipeline at filter threshold 3 (a hit in all three ON looks, none
in the OFF looks within its window), zero drift kept, as Price et al. did.

    python tools/turbo_events.py OUT_DIR ON1.h5 OFF1.h5 ON2.h5 OFF2.h5 ON3.h5 OFF3.h5

Writes OUT_DIR/events.csv (empty when there are none) and the .dat files.
"""
import os
import sys
from pathlib import Path

from turbo_seti.find_doppler.find_doppler import FindDoppler
from turbo_seti.find_event.find_event_pipeline import find_event_pipeline

out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
files = [Path(p).resolve() for p in sys.argv[2:]]
dats = []
for f in files:
    # From the file's folder with its bare name: turboSETI joins its output
    # folder to the name it is given, which breaks on Windows with a full path.
    os.chdir(f.parent)
    FindDoppler(f.name, max_drift=4.0, snr=10.0, out_dir=str(out), n_coarse_chan=1, log_level_int=40).search()
    dats.append(out / (f.stem + ".dat"))
os.chdir(out)
(out / "dats.lst").write_text("\n".join(str(d) for d in dats) + "\n")
(out / "h5s.lst").write_text("\n".join(str(f) for f in files) + "\n")
found = find_event_pipeline(str(out / "dats.lst"), str(out / "h5s.lst"), check_zero_drift=True, filter_threshold=3,
                            on_off_first="ON", number_in_cadence=6, saving=True, csv_name=str(out / "events.csv"))
if found is None or len(found) == 0:
    (out / "events.csv").write_text("")
print("ok", 0 if found is None else len(found))
