"""BLISS's event stage (bliss/drift_search/event_search.cpp at commit
2b98afe), ported line for line to run on hits found once.

Its own event_search asks a scan for its hits again for each candidate, and
a scan does not keep them, so the drift search runs again each time; called
once for each choice of ON looks at each cut, that is hours a block. This
port runs on hits already found. It keeps the original's arithmetic and its
quirks: the distance takes the second hit's duration for both hits' ends,
the first look's matched hits are removed from the later looks' lists as it
goes, and an event needs a hit in at least two ON looks and none within
distance 50 of it, on average, in any OFF look. The distance cache is left
out: it only saves recomputing.

Hits are dicts with the fields of BLISS's hit: start_freq_MHz,
drift_rate_Hz_per_sec, snr, power, bandwidth, start_time_sec, duration_sec
(plus anything else, carried along). Run against BLISS's own event_search
on the same hits in tools/bliss_curves.py's selftest.
"""

SECONDS_PER_DAY = 24 * 60 * 60
FREQ_LOCALIZATION_WEIGHT = 0.01
DRIFT_ERROR_WEIGHT = 10.0
SNR_DIFFERENCE_WEIGHT = 0.0
EPS = 1e-8
MATCH = 50.0       # "Made up number that looks good when staring at distances"


def distance(a, b):
    snr_difference = abs(a["snr"] - b["snr"])
    da, db = a["drift_rate_Hz_per_sec"], b["drift_rate_Hz_per_sec"]
    drift_difference = abs(da - db) / (EPS + da * da + db * db)
    drift_error = drift_difference * drift_difference
    first = min(a["start_time_sec"], b["start_time_sec"])
    last = max(a["start_time_sec"] + b["duration_sec"], b["start_time_sec"] + b["duration_sec"])
    rendezvous = (last + first) / 2
    fa = a["start_freq_MHz"] * 1e6 + da * (rendezvous - a["start_time_sec"])
    fb = b["start_freq_MHz"] * 1e6 + db * (rendezvous - b["start_time_sec"])
    return (FREQ_LOCALIZATION_WEIGHT * abs(fa - fb) + DRIFT_ERROR_WEIGHT * drift_error
            + SNR_DIFFERENCE_WEIGHT * snr_difference)


def event_search(on_scans, off_scans):
    """on_scans: [(tstart_mjd, tduration_s, [hit, ...]), ...] in time order;
    off_scans: [[hit, ...], ...]. The events, as BLISS's event_search."""
    on_hits = [list(h) for _, _, h in on_scans]
    events = []
    for i, (tstart, tdur, _) in enumerate(on_scans):
        for start in list(on_hits[i]):
            ev = {"hits": [start], "average_power": start["power"], "average_snr": start["snr"],
                  "average_drift_rate_Hz_per_sec": start["drift_rate_Hz_per_sec"],
                  "event_start_seconds": tstart * SECONDS_PER_DAY,
                  "starting_frequency_Hz": start["start_freq_MHz"] * 1e6,
                  "event_end_seconds": tstart * SECONDS_PER_DAY + tdur}
            for j in range(i + 1, len(on_scans)):
                check = on_hits[j]
                best, best_k = float("inf"), None
                for k, cand in enumerate(check):
                    low = min(distance(h, cand) for h in ev["hits"])
                    if low < best:
                        best, best_k = low, k
                if best < MATCH:
                    ev["hits"].append(check.pop(best_k))
            in_off = 0
            for off in off_scans:
                for oh in off:
                    if sum(distance(oh, h) for h in ev["hits"]) / len(ev["hits"]) < MATCH:
                        in_off += 1
            if len(ev["hits"]) > 1 and in_off == 0:
                n = len(ev["hits"])
                ev["average_drift_rate_Hz_per_sec"] = sum(h["drift_rate_Hz_per_sec"] for h in ev["hits"]) / n
                ev["average_power"] = sum(h["power"] for h in ev["hits"]) / n
                ev["average_bandwidth"] = sum(h["bandwidth"] for h in ev["hits"]) / n
                ev["average_snr"] = sum(h["snr"] for h in ev["hits"]) / n
                events.append(ev)
    return events
