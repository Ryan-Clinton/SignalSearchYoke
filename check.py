#!/usr/bin/env python3
"""The checks on the sweeps' candidates (vetting.py says which and how),
each kept in the store's `checks` table, with a record and a report.

    ./check.py                every current candidate not yet checked by this version of the checks
    ./check.py --all          every current candidate again
    ./check.py --event ID     one event of the store, whatever its label (to see the checks at work)
    ./check.py --json

A candidate (onoff.py: seen in every ON look along its track, nowhere in the
OFF looks) goes through ten checks after blc1's framework: data sanity, the
OFF looks below the threshold, known bands, zero drift, the Earth's drift,
recurrence elsewhere, look-alikes, harmonics and intermodulation, crowding,
and a report. Each check's result is "shown", "indicated", "coincidence
possible" or nothing; none deletes a candidate. The verdict is
"interference", "likely interference", "unexplained, strong" or
"unexplained, weak". "Unexplained" is the end of these checks, not a
discovery.

Records: data/checks/LEAD.json; reports: docs/leads/LEAD.md (with a PNG of
the six looks around the track).
"""
import argparse
import json

import numpy as np

import store
import vetting
import yoke

REPORTS = yoke.ROOT / "docs" / "leads"
BACKGROUND_MHZ = 1.5   # check 6's density: hits within this of the candidate, in the band searched


def lead_id(target, session, f_mhz):
    return f"SETI-{target}-{session}-{f_mhz:.6f}"


def records_dir():
    return yoke.DATA / "checks"


def _cadence(db, session, block_idx):
    """The block's six looks from the store: LookInfo each, and a map from
    hit id to (position, index)."""
    files = {r["file_id"]: dict(r) for r in db.execute(
        "SELECT * FROM files WHERE session=? AND cadence_position IS NOT NULL", (session,))}
    by_pos = {f["cadence_position"]: f for f in files.values()}
    complete = {r["position"]: r["complete"] for r in db.execute(
        "SELECT position, complete FROM looks WHERE session=? AND block_idx=? AND superseded_run IS NULL",
        (session, block_idx))}
    looks, where = [], {}
    for pos in range(6):
        f = by_pos[pos]
        rows = db.execute("SELECT * FROM hits WHERE session=? AND block_idx=? AND file_id=? AND superseded_run IS NULL"
                          " ORDER BY hit_id", (session, block_idx, f["file_id"])).fetchall()
        hits = []
        for i, h in enumerate(rows):
            where[h["hit_id"]] = (pos, i)
            hits.append({"frequency_mhz": h["f_start_mhz"], "drift_hz_s": h["drift_hz_s"], "snr": h["snr"],
                         "shadow": h["origin"] == "shadow", "box_channels": h["box_channels"] or 1})
        width = abs(f["foff_mhz"]) * 1e6
        span = max((f["n_spectra"] or 16) - 1, 1) * f["tsamp_s"]
        looks.append(vetting.LookInfo(hits, f["tstart_mjd"], pos, width / span, width,
                                      bool(complete.get(pos, 1) if complete.get(pos) is not None else True)))
    return looks, where, by_pos


def _event(db, row, where):
    e = {"event_id": row["event_id"], "frequency_mhz": row["f_start_mhz"], "drift_hz_s": row["drift_hz_s"],
         "snr": row["snr"], "label": row["label"], "looks": json.loads(row["looks"] or "[]"),
         "seed_position": row["seed_position"] or 0, "off_snr_max": row["off_snr_max"],
         "on_snr_min": row["on_snr_min"], "dot_max": row["dot_max"], "drift_spread_steps": row["drift_spread_steps"],
         "drift_flag": bool(row["drift_flag"]), "supersedes_event_id": row["supersedes_event_id"]}
    matches = [None] * 6
    for link in db.execute("SELECT position, hit_id FROM event_hits WHERE event_id=?", (row["event_id"],)):
        if link["hit_id"] in where:
            matches[link["position"]] = where[link["hit_id"]][1]
    e["matches"] = matches
    st = db.execute("SELECT shape, data FROM stamps WHERE event_id=?", (row["event_id"],)).fetchone()
    e["stamps"] = np.frombuffer(st["data"], np.float32).reshape(json.loads(st["shape"])) if st else None
    seed = db.execute("SELECT flagged_fraction FROM hits WHERE hit_id=?", (row["seed_hit_id"],)).fetchone()
    e["flagged_fraction"] = seed["flagged_fraction"] if seed else None
    return e


def recurrence_files(db, session):
    """The files check 6 looks in: the session's OFF looks and every look of
    other sessions."""
    return db.execute("SELECT file_id, tstart_mjd, target, session FROM files"
                      " WHERE is_on = 0 OR session != ? OR is_on IS NULL", (session,)).fetchall()


def recurrence_hits(db, e, looks, session):
    """The store's hits check 6 could match: for each file at another
    target or time, the same window vetting.py's check 6 tests (100 Hz, plus
    the drift's travel over the time between when that is under a day,
    around both where the drift carries the signal and where it started),
    so no hit the check would match is left out of the query."""
    f, drift = e["frequency_mhz"], e["drift_hz_s"]
    t0 = looks[e.get("seed_position", 0)].tstart
    out = []
    for fl in recurrence_files(db, session):
        dt = ((fl["tstart_mjd"] or t0) - t0) * 86400
        within = abs(dt) < 86400
        reach = (vetting.RECUR_HZ + (abs(drift) * abs(dt) if within else 0.0)) / 1e6
        moved = f + (drift * dt / 1e6 if within else 0.0)
        for h in db.execute("SELECT hit_id, file_id, f_start_mhz, drift_hz_s, snr, origin FROM hits WHERE file_id=?"
                            " AND superseded_run IS NULL AND (f_start_mhz BETWEEN ? AND ? OR f_start_mhz BETWEEN ? AND ?)",
                            (fl["file_id"], moved - reach, moved + reach, f - reach, f + reach)):
            out.append({"hit_id": h["hit_id"], "file_id": h["file_id"], "frequency_mhz": h["f_start_mhz"], "drift_hz_s": h["drift_hz_s"],
                        "snr": h["snr"], "mjd": fl["tstart_mjd"], "target": fl["target"], "session": fl["session"],
                        "shadow": h["origin"] == "shadow"})
    return out


def recurrence_background(db, e, file_ids):
    """Check 6's background: for every file the matches could come from
    (matched or not, so none drops out of the expected count), its
    hits (matching or not) within BACKGROUND_MHZ of the candidate and the
    band searched there (its session's searched blocks; failing those, the
    span its hits cover, which overstates the density)."""
    f = e["frequency_mhz"]
    lo, hi = f - BACKGROUND_MHZ, f + BACKGROUND_MHZ
    out = []
    for fid in sorted(file_ids):
        fl = db.execute("SELECT session, tstart_mjd FROM files WHERE file_id=?", (fid,)).fetchone()
        hits = db.execute("SELECT f_start_mhz, drift_hz_s, origin FROM hits WHERE file_id=? AND superseded_run IS NULL"
                          " AND f_start_mhz BETWEEN ? AND ?", (fid, lo, hi)).fetchall()
        blocks = db.execute("SELECT f_lo_mhz, f_hi_mhz FROM blocks WHERE session=? AND status='done'"
                            " AND f_hi_mhz > ? AND f_lo_mhz < ?", (fl["session"], lo, hi)).fetchall()
        if blocks:
            searched = sum(min(b["f_hi_mhz"], hi) - max(b["f_lo_mhz"], lo) for b in blocks)
        else:
            searched = (max(h["f_start_mhz"] for h in hits) - min(h["f_start_mhz"] for h in hits)) if len(hits) > 1 else 0.0
        out.append({"mjd": fl["tstart_mjd"], "searched_hz": max(searched, 0.0) * 1e6,
                    "hits": [(h["drift_hz_s"], h["origin"] == "shadow") for h in hits]})
    return out


def check_event(db, row, say=print, report_dir=REPORTS):
    session, block_idx = row["session"], row["block_idx"]
    looks, where, by_pos = _cadence(db, session, block_idx)
    e = _event(db, row, where)
    on = by_pos[0]
    target = {"name": on["cadence_target"] or on["target"], "ra_hours": on["ra_hours"], "dec_deg": on["dec_degrees"]}
    own = {h for h in (r["hit_id"] for r in db.execute("SELECT hit_id FROM event_hits WHERE event_id=?",
                                                         (row["event_id"],)))}
    others = [h for h in recurrence_hits(db, e, looks, session) if h.pop("hit_id") not in own]
    for h in others:
        h.pop("file_id")
    background = recurrence_background(db, e, [fl["file_id"] for fl in recurrence_files(db, session)])
    session_hits = [{"frequency_mhz": h["f_start_mhz"], "drift_hz_s": h["drift_hz_s"], "snr": h["snr"]}
                    for h in db.execute("SELECT f_start_mhz, drift_hz_s, snr FROM hits WHERE session=? AND"
                                        " superseded_run IS NULL AND origin='search'", (session,))]
    lead = lead_id(target["name"], session, e["frequency_mhz"])
    result = vetting.vet(e, looks, target, others, session_hits, report_dir=report_dir, lead=lead,
                         background=background)
    for c in result["checks"]:
        store.save_check(db, lead, f"{c['n']}. {c['name']}", c["result"], c["evidence"], vetting.VERSION,
                         event_id=row["event_id"], strength=c["strength"])
    record = {"lead": lead, "event_id": row["event_id"], "session": session, "block": block_idx,
              "frequency_mhz": e["frequency_mhz"], "drift_hz_s": e["drift_hz_s"], "snr": e["snr"],
              "label": e["label"], "supersedes_event_id": e["supersedes_event_id"], **result}
    yoke.write(records_dir() / f"{lead}.json", record)
    say(f"{lead} (event {row['event_id']}, {e['label']}): {result['verdict']}")
    return record


def run(args, say=print):
    db = store.connect()
    if args.event:
        rows = db.execute("SELECT * FROM events WHERE event_id=?", (args.event,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM events WHERE label='candidate' AND superseded_run IS NULL"
                          " ORDER BY snr DESC").fetchall()
        if not args.all:
            done = {r["event_id"] for r in db.execute("SELECT DISTINCT event_id FROM checks WHERE version=?",
                                                       (vetting.VERSION,))}
            rows = [r for r in rows if r["event_id"] not in done]
    out = [check_event(db, r, say) for r in rows]
    if not rows:
        say("No candidate waiting: every current candidate has been checked by this version of the checks.")
    count = db.execute("SELECT count(*) FROM events WHERE label='candidate' AND superseded_run IS NULL").fetchone()[0]
    db.close()
    return {"checked": out, "candidates": count}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="check every current candidate again")
    ap.add_argument("--event", type=int, help="check this one event of the store, whatever its label")
    ap.add_argument("--json", action="store_true", help="answer in JSON")
    args = ap.parse_args()
    yoke.main("check", lambda: run(args), args.json)


if __name__ == "__main__":
    main()
