#!/usr/bin/env python3
"""The checks on the sweeps' candidates (vetting.py says which and how),
each kept in the store's `checks` table, with a record and a report.

    ./check.py                every current candidate not yet checked by this version of the checks
    ./check.py --all          every current candidate again
    ./check.py --event ID     one event of the store, whatever its label (to see the checks at work)
    ./check.py --rank         rank every current candidate only (ranking.py; done after every check run too)
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

Then every current candidate is ranked (ranking.py: the sum of -log10 of
each check's chance; data/checks/ranking.json).

Records: data/checks/LEAD.json; reports: docs/leads/LEAD.md (with a PNG of
the six looks around the track).
"""
import argparse
import json

import numpy as np

import occupancy
import store
import vetting
import yoke

REPORTS = yoke.ROOT / "docs" / "leads"
BACKGROUND_MHZ = 1.5   # check 6's density: hits within this of the candidate, in the band searched


def lead_id(target, session, f_mhz):
    return f"SETI-{target}-{session}-{f_mhz:.6f}"


def record_for(lead, event_id):
    """The check record of an event: the file named by its lead id, or one of the same lead with the event
    number added (written when another event already held the name); None if neither is this event's."""
    for path in [records_dir() / f"{lead}.json"] + sorted(records_dir().glob(f"{lead}-e*.json")):
        if path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
            if rec.get("event_id") == event_id:
                return path, rec
    return None, None


def records_dir():
    return yoke.DATA / "checks"


def _cadence(db, session, block_idx):
    """The block's six looks from the store: LookInfo each, and a map from
    hit id to (position, index)."""
    by_pos = {f["cadence_position"]: f for f in store.cadence_rows(db, session)}
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
                                      None if complete.get(pos) is None else bool(complete[pos])))
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


def recurrence_files(db, session, on_positions=None):
    """The files check 6 looks in: the cadence's OFF looks and every look of
    other sessions (`session` is the cadence's key). With `on_positions` (a
    candidate judged with other looks as ON), the cadence's looks at the
    other positions instead. Another cadence of the same session counts as
    another session's looks: its files are other scans."""
    own = {f["file_id"]: f["cadence_position"] for f in store.cadence_rows(db, session)}
    archive = store.cadence_session(db, session)
    out = []
    for r in db.execute("SELECT file_id, tstart_mjd, target, session, cadence_position FROM files"):
        pos = own.get(r["file_id"])
        if pos is not None and (pos % 2 == 0 if on_positions is None else pos in on_positions):
            continue                     # the cadence's own ON looks (or the looks taken as ON)
        if pos is None and on_positions is not None and r["session"] == archive and r["cadence_position"] is None:
            continue                     # the session's files outside any cadence, left out as before
        out.append({"file_id": r["file_id"], "tstart_mjd": r["tstart_mjd"], "target": r["target"],
                    "session": r["session"]})
    return out


def recurrence_hits(db, e, looks, session, on_positions=None):
    """The store's hits check 6 could match: for each file at another
    target or time, the same window vetting.py's check 6 tests (100 Hz, plus
    the drift's travel over the time between when that is under a day,
    around both where the drift carries the signal and where it started),
    so no hit the check would match is left out of the query."""
    f, drift = e["frequency_mhz"], e["drift_hz_s"]
    t0 = looks[e.get("seed_position", 0)].tstart
    out = []
    for fl in recurrence_files(db, session, on_positions):
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


def session_hits(db, session):
    """Every current hit at the cut of the session: checks 8 and 9's input."""
    return [{"frequency_mhz": h["f_start_mhz"], "drift_hz_s": h["drift_hz_s"], "snr": h["snr"]}
            for h in db.execute("SELECT f_start_mhz, drift_hz_s, snr FROM hits WHERE session=? AND"
                                " superseded_run IS NULL AND origin='search'", (session,))]


def target_of(db, session):
    on = store.cadence_rows(db, session)[0]
    return {"name": on["cadence_target"] or on["target"], "ra_hours": on["ra_hours"], "dec_deg": on["dec_degrees"]}


def vet_from_store(db, e, looks, session, target, own=(), on_positions=None, hits=None, report_dir=None,
                   lead=None, bands_as_context=False):
    """The checks on an event with the store's evidence, as every candidate
    of a sweep gets them: recurrence in the files `recurrence_files` names
    (the store's hits `own` left out), check 6's background, and the
    session's hits for checks 8 and 9 (`hits`, from `session_hits`, may be
    passed in to save reading them again). Planted signals and candidates
    judged with other ON looks (ranking.py) go through this too, so their
    checks see what a real candidate's see."""
    others = [h for h in recurrence_hits(db, e, looks, session, on_positions) if h.pop("hit_id") not in own]
    for h in others:
        h.pop("file_id")
    # The same eligibility for the background as for the matches: check 6 leaves the same target's other
    # sessions out of its matches, so their files are left out of the background too.
    background = recurrence_background(db, e, [fl["file_id"] for fl in recurrence_files(db, session, on_positions)
                                               if fl["target"] != target.get("name")])
    own_f = [r["f_start_mhz"] for r in db.execute(
        f"SELECT f_start_mhz FROM hits WHERE hit_id IN ({','.join('?' * len(own))})", tuple(own))] if own else []
    return vetting.vet(e, looks, target, others, hits if hits is not None else session_hits(db, session),
                       report_dir=report_dir, lead=lead, background=background,
                       occupancy=occupancy.load(db, session), own_mhz=own_f, bands_as_context=bands_as_context)


def check_event(db, row, say=print, report_dir=None):
    report_dir = REPORTS if report_dir is None else report_dir    # read when called, so a test can move it
    session, block_idx = row["session"], row["block_idx"]
    looks, where, by_pos = _cadence(db, session, block_idx)
    e = _event(db, row, where)
    target = target_of(db, session)
    own = {h for h in (r["hit_id"] for r in db.execute("SELECT hit_id FROM event_hits WHERE event_id=?",
                                                         (row["event_id"],)))}
    lead = lead_id(target["name"], session, e["frequency_mhz"])
    # Two events can share a lead id (the frequency to 1 Hz): an event whose name another event's record
    # already holds (one it supersedes too, so that record is kept) gets its event number added.
    # record_for finds either.
    path = records_dir() / f"{lead}.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")).get("event_id") not in (None, row["event_id"]):
        lead = f"{lead}-e{row['event_id']}"
    result = vet_from_store(db, e, looks, session, target, own, report_dir=report_dir, lead=lead)
    store.save_checks(db, lead, result["checks"], vetting.VERSION, row["event_id"])
    record = {"lead": lead, "event_id": row["event_id"], "session": session, "block": block_idx,
              "frequency_mhz": e["frequency_mhz"], "drift_hz_s": e["drift_hz_s"], "snr": e["snr"],
              "label": e["label"], "supersedes_event_id": e["supersedes_event_id"], **result}
    yoke.write(records_dir() / f"{lead}.json", record)
    say(f"{lead} (event {row['event_id']}, {e['label']}): {result['verdict']}")
    return record


def run(args, say=print):
    import ranking
    if args.rank:
        return ranking.rank(say)
    db = store.connect()
    if args.event:
        rows = db.execute("SELECT * FROM events WHERE event_id=?", (args.event,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM events WHERE label='candidate' AND superseded_run IS NULL"
                          " ORDER BY snr DESC").fetchall()
        if not args.all:
            # done: a whole evaluation in the store and its record written (ranking reads the record)
            in_store = store.checked_events(db, vetting.VERSION, vetting.N_CHECKS)
            name = {}

            def recorded(r):
                if r["session"] not in name:
                    name[r["session"]] = target_of(db, r["session"])["name"]
                rec = record_for(lead_id(name[r["session"]], r["session"], r["f_start_mhz"]), r["event_id"])[1]
                return rec is not None and rec.get("version") == vetting.VERSION
            rows = [r for r in rows if not (r["event_id"] in in_store and recorded(r))]
    out = [check_event(db, r, say) for r in rows]
    if not rows:
        say("No candidate waiting: every current candidate has been checked by this version of the checks.")
    count = db.execute("SELECT count(*) FROM events WHERE label='candidate' AND superseded_run IS NULL").fetchone()[0]
    db.close()
    ranked, waiting = None, None
    if count and not args.event:
        try:
            ranked = ranking.rank(say)
        except yoke.Refusal as e:
            # the checks are saved; the ranking waits for a session's OFF null, said, not hidden. Anything else
            # is still a failure.
            if e.code_name != "NOT_FOUND" or "OFF null" not in e.message:
                raise
            waiting = e.message
            say(f"checks saved; not ranked: {waiting}")
    return {"checked": out, "candidates": count, "ranked": ranked is not None, "ranking_waits_for": waiting}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="check every current candidate again")
    ap.add_argument("--event", type=int, help="check this one event of the store, whatever its label")
    ap.add_argument("--rank", action="store_true", help="only rank every current candidate")
    ap.add_argument("--json", action="store_true", help="answer in JSON")
    args = ap.parse_args()
    yoke.main("check", lambda: run(args), args.json)


if __name__ == "__main__":
    main()
