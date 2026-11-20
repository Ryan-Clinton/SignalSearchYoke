"""Run in turboSETI's environment: diagnostics of turboSETI 2.3.2 on one
block, for tools/turbo_checks.py (the turboSETI comparison audit). Nothing
here changes tools/turbo_curves.py, which the published comparison runs.

    python tools/turbo_diag.py IN.json OUT.json

IN: {"planted": [six .h5], "plain": [six .h5], "cuts": [...],
     "ours": {"planted": [six lists], "plain": [six lists]}}, each of ours a
     list of this search's hits {"freq_mhz" (at the look's start), "drift_hz_s",
     "snr"} in the order turboSETI would number them (channel index rising:
     turbo_checks.turbo_order).

For the planted six (the true choice of ON looks only) and the plain six
(all 20 choices, for the false-candidate controls), OUT holds:
- "native": as turbo_curves runs it (FindDoppler at SNR 5, max drift 4, its
  default min_drift 1e-5, each table cut to SNR > X, find_events at filter 3):
  every look's hits, and the events at each cut;
- "zero_drift" (true choice): the same with the zero-drift trial searched
  (FindDoppler searches only |drift| > min_drift and refuses a negative
  min_drift, so min_drift is set to -1 on the object after it is made);
- "direct" (planted): FindDoppler run at SNR 30 itself, against the SNR 5
  run cut to > 30;
- "ours_judged": this search's hits through find_events, written as
  turboSETI writes its own: numbered in channel order as tophitsearch numbers
  its hits, the frequency at the first spectrum's middle, freq_start/freq_end
  the top-hit window, 2 * ceil(max_drift / drift step) channels either side;
- "ours_judged_snr_numbering" (planted, true choice): the same hits numbered
  strongest first instead, to measure how much find_events' deduplication by
  TopHitNum (numbered afresh in each look) depends on the numbering alone.

An event row: its look, its event (find_events' Hit_ID, which
matched._turbo_kept groups rows by) as "hit_id", its own TopHitNum as
"top_hit_num", frequency, window, drift and SNR.
"""
import contextlib
import io
import itertools
import json
import math
import os
import sys
import tempfile
from pathlib import Path

from turbo_seti.find_doppler.find_doppler import FindDoppler
import blimpy.io.base_reader as _blimpy_reader

_reader_init = _blimpy_reader.Reader.__init__


def _reader_init_with_floor(self):        # as tools/turbo_curves.py: blimpy's load limit follows free memory
    _reader_init(self)
    self.max_data_array_size = max(self.max_data_array_size, 4 * _blimpy_reader.GIGA)


_blimpy_reader.Reader.__init__ = _reader_init_with_floor
from turbo_seti.find_event import find_event  # noqa: E402

TRUE = (0, 2, 4)
ALL = list(itertools.combinations(range(6), 3))
MAX_DRIFT = 4.0


def search(files, snr, tmp, zero=False):
    """FindDoppler on each file: (tables, .dat paths)."""
    tables, dats = [], []
    for f in files:
        f = Path(f).resolve()
        os.chdir(f.parent)
        out = Path(tmp) / ("zero" if zero else "native") / str(int(snr))
        out.mkdir(parents=True, exist_ok=True)
        fd = FindDoppler(f.name, max_drift=MAX_DRIFT, snr=snr, out_dir=str(out), n_coarse_chan=1, log_level_int=40)
        if zero:
            fd.min_drift = -1.0       # the loops test abs(drift) > min_drift: now 0 too
        fd.search()
        dat = out / (f.stem + ".dat")
        with contextlib.redirect_stdout(io.StringIO()):
            t = find_event.read_dat(str(dat))
        t["Source"] = "cadence"
        tables.append(t)
        dats.append(dat)
    return tables, dats


def above(t, cut):
    return t[t["SNR"] > cut] if "SNR" in t else t


def hits(t):
    if "SNR" not in t:
        return []
    return [{"freq_mhz": float(r["Freq"]), "drift_hz_s": float(r["DriftRate"]), "snr": float(r["SNR"]),
             "top_hit_num": int(r["TopHitNum"])} for _, r in t.iterrows()]


def events(tables, cut, ons):
    """find_events at filter 3 on the six tables with `ons` called ON (ON, OFF pairs as turbo_curves orders them)."""
    offs = [j for j in range(6) if j not in ons]
    order = [x for pair in zip(ons, offs) for x in pair]
    cached = {}
    real = find_event.read_dat
    find_event.read_dat = lambda name: cached[name].copy()
    try:
        names = []
        for j in order:
            name = f"look{j}.dat"
            cached[name] = above(tables[j], cut)
            names.append(name)
        with contextlib.redirect_stdout(io.StringIO()):
            found = find_event.find_events(names, check_zero_drift=True, filter_threshold=3, on_off_first="ON")
    finally:
        find_event.read_dat = real
    rows = []
    if found is not None and len(found):
        for _, r in found.iterrows():
            k = int(str(r["status"]).rsplit("_", 1)[-1])
            rows.append({"look": ons[k - 1], "hit_id": str(r.get("Hit_ID", "")),
                         "top_hit_num": int(r["TopHitNum"]) if "TopHitNum" in r else None,
                         "freq_mhz": float(r["Freq"]), "freq_start_mhz": float(r["FreqStart"]),
                         "freq_end_mhz": float(r["FreqEnd"]), "drift_hz_s": float(r["DriftRate"]),
                         "snr": float(r["SNR"])})
    return rows


def by_choice(tables, cuts, choices):
    return {",".join(map(str, ons)): {str(c): events(tables, c, ons) for c in cuts} for ons in choices}


def write_ours(dat_from, ours, path, native_table, numbering):
    """This search's hits as a turboSETI .dat, the header from turboSETI's own
    for the same file. numbering "channel": in the order given (channel order);
    "snr": strongest first. A look with no hit: turboSETI's own table emptied."""
    if not ours:
        return native_table.iloc[0:0].copy()
    head = Path(dat_from).read_text(encoding="utf-8").splitlines()[:9]
    deltat = float(head[5].split("\t")[0].split(":")[-1])
    deltaf = float(head[5].split("\t")[1].split(":")[-1])            # Hz, signed as the file's foff
    obs_len = float(head[5].split("\t")[3].split(":")[-1])
    distance = 2 * math.ceil(MAX_DRIFT / (abs(deltaf) / obs_len))
    seq = list(ours) if numbering == "channel" else sorted(ours, key=lambda h: -h["snr"])
    lines = []
    for n, h in enumerate(seq, 1):
        f = h["freq_mhz"] + h["drift_hz_s"] * deltat / 2 / 1e6        # turboSETI's reference: the first spectrum's middle
        f_start = f - distance * deltaf / 1e6
        f_end = f + (distance - 1) * deltaf / 1e6
        lines.append(f"{n:06d}\t{h['drift_hz_s']:10.6f}\t{h['snr']:10.6f}\t{f:14.6f}\t{f:14.6f}\t0\t"
                     f"{f_start:14.6f}\t{f_end:14.6f}\t0.0\t{0.0:14.6f}\t0\t{len(ours)}\t")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(head + lines) + "\n", encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        t = find_event.read_dat(str(path))
    t["Source"] = "cadence"
    return t


def main():
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    cuts = [float(c) for c in spec["cuts"]]
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for kind in ("planted", "plain"):
            choices = [TRUE] if kind == "planted" else ALL
            rec = {}
            tables, dats = search(spec[kind], 5.0, Path(tmp) / kind)
            rec["native"] = {"hits": [hits(t) for t in tables], "events": by_choice(tables, cuts, choices)}
            zt, _ = search(spec[kind], 5.0, Path(tmp) / kind, zero=True)
            rec["zero_drift"] = {"hits": [hits(t) for t in zt], "events": by_choice(zt, cuts, [TRUE])}
            if kind == "planted":
                direct, _ = search(spec[kind], 30.0, Path(tmp) / kind / "direct")
                rec["direct"] = {"hits": [hits(t) for t in direct], "events": by_choice(direct, [30.0], [TRUE])}
            ours = [write_ours(dats[j], spec["ours"][kind][j], Path(tmp) / kind / "ours" / f"look{j}.dat",
                               tables[j], "channel") for j in range(6)]
            rec["ours_judged"] = {"events": by_choice(ours, cuts, choices)}
            if kind == "planted":
                snr_n = [write_ours(dats[j], spec["ours"][kind][j], Path(tmp) / kind / "ours_snr" / f"look{j}.dat",
                                    tables[j], "snr") for j in range(6)]
                rec["ours_judged_snr_numbering"] = {"events": by_choice(snr_n, cuts, [TRUE])}
            out[kind] = rec
    Path(sys.argv[2]).write_text(json.dumps(out), encoding="utf-8")
    print("ok")


if __name__ == "__main__":
    main()
