"""The hit store: every hit of every look, every cadence result, every
check and every planted signal, in one SQLite file (data/ssy.sqlite).

Rejected hits are the evidence for every later check (recurrence across
targets and sessions, look-alikes, the OFF test below the threshold), so
none is thrown away. One transaction per block: a block is in the store
whole, or not at all, and the `blocks` table is the sweep's resume ledger.

A block searched again (a changed search) does not delete its earlier
hits and events: they are marked `superseded_run` (the run that replaced
them) and kept, with the checks made on them. The current results are the
rows whose `superseded_run` is NULL. Each new event names the event it
replaces (`supersedes_event_id`: the earlier current event at the same
place and drift), so a check made on a candidate follows it through a
re-search. Each run records its `search_version`.

NULL means not measured, never zero or false: `flagged_fraction` is NULL
until the spectral-kurtosis flags exist, and a NULL there says nothing
about interference. `power` and `noise` are in the file's own data units
(Breakthrough Listen's uncalibrated spectrometer output, not Jy):
`noise` is one spectrum's robust standard deviation at the hit's channel
(1.4826 x the median absolute deviation, the median over the look's
spectra), and `power` is SNR x sqrt(spectra) x noise, the excess summed
along the line. They become physical units only with the calibration of
Phase 3.

    sqlite3 data/ssy.sqlite "select * from blocks"

JSON stays for --json answers and the human-readable sweep record.
"""
import json
import platform
import sqlite3
import socket
from datetime import datetime, timezone

import yoke

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY,
    started_utc TEXT NOT NULL,
    finished_utc TEXT,
    command TEXT NOT NULL,
    git_commit TEXT,
    uncommitted_changes INTEGER,
    host TEXT,
    python TEXT,
    libraries TEXT,               -- JSON: numpy, h5py, hdf5plugin versions
    params TEXT,                  -- JSON: every search parameter
    search_version TEXT           -- results of different versions are not comparable
);
CREATE TABLE IF NOT EXISTS files (
    file_id INTEGER PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    etag TEXT,
    size INTEGER,
    session TEXT,
    scan TEXT,
    target TEXT,                  -- as the file names it (DIAG_ taken off)
    cadence_target TEXT,          -- the cadence's ON target, for the files of a cadence
    cadence_position INTEGER,     -- 0 to 5: ON, OFF, ON, OFF, ON, OFF
    is_on INTEGER,
    tstart_mjd REAL,
    fch1_mhz REAL,
    foff_mhz REAL,
    tsamp_s REAL,
    nchans INTEGER,
    n_spectra INTEGER,
    ra_hours REAL,
    dec_degrees REAL,
    telescope_id INTEGER,
    attrs TEXT                    -- JSON: the file's own header
);
CREATE TABLE IF NOT EXISTS blocks (
    session TEXT NOT NULL,
    block_idx INTEGER NOT NULL,
    f_lo_mhz REAL,
    f_hi_mhz REAL,
    status TEXT NOT NULL,         -- done
    run_id INTEGER REFERENCES runs(run_id),
    bytes INTEGER,                -- moved over the web for this block
    fetch_s REAL,
    search_s REAL,
    wall_s REAL,                  -- from the end of the last block to the end of this one
    threads INTEGER,
    hits INTEGER,                 -- at the cut, all six looks
    shadow_hits INTEGER,          -- SNR 5 to the cut
    candidates INTEGER,
    interference INTEGER,
    unconfirmed INTEGER,
    searched_utc TEXT,
    PRIMARY KEY (session, block_idx)
);
CREATE TABLE IF NOT EXISTS hits (
    hit_id INTEGER PRIMARY KEY,
    run_id INTEGER REFERENCES runs(run_id),
    file_id INTEGER REFERENCES files(file_id),
    session TEXT,
    block_idx INTEGER,
    channel INTEGER,              -- in the whole file
    f_start_mhz REAL,             -- at the look's start, full precision
    f_end_mhz REAL,               -- along the drift at its end
    drift_hz_s REAL,
    drift_err_hz_s REAL,          -- half a drift step
    drift_norm REAL,              -- drift over frequency, 1/s (x 1e9: nHz/Hz/s)
    snr REAL,
    power REAL,                   -- file's data units: SNR x sqrt(spectra) x noise, the excess along the line
    noise REAL,                   -- file's data units: one spectrum's robust std at the channel (median over spectra)
    width_channels INTEGER,
    smear REAL,                   -- channels crossed within one spectrum: |drift| x tsamp / channel width
    near_edge INTEGER,            -- within 5% of a coarse channel's end
    near_dc INTEGER,              -- within the drift's reach of a coarse channel's middle
    flagged_fraction REAL,        -- spectral kurtosis flags; NULL = not measured (not zero)
    box_channels INTEGER,         -- the desmearing box: channels summed a spectrum
    wide INTEGER,                 -- lit over far more channels than its box
    noise_factor REAL,            -- the summed lines' spread over sqrt(spectra x box): 1 for ideal noise
    origin TEXT NOT NULL,         -- search, shadow (SNR 5 to the cut: evidence, never a candidate), injected
    superseded_run INTEGER        -- NULL: current; else the run whose re-search replaced it
);
CREATE INDEX IF NOT EXISTS hits_frequency ON hits (f_start_mhz);
CREATE INDEX IF NOT EXISTS hits_block ON hits (session, block_idx);
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY,
    run_id INTEGER REFERENCES runs(run_id),
    session TEXT,
    block_idx INTEGER,
    seed_hit_id INTEGER REFERENCES hits(hit_id),
    label TEXT NOT NULL,          -- candidate, interference, unconfirmed
    f_start_mhz REAL,
    drift_hz_s REAL,
    snr REAL,
    looks TEXT,                   -- JSON: per look, found or not, and the matched hit's SNR and drift
    superseded_run INTEGER,       -- NULL: current; else the run whose re-search replaced it
    supersedes_event_id INTEGER   -- the earlier event at the same place this one replaces
);
CREATE INDEX IF NOT EXISTS events_block ON events (session, block_idx);
CREATE TABLE IF NOT EXISTS event_hits (
    event_id INTEGER REFERENCES events(event_id),
    position INTEGER,             -- the look, 0 to 5
    hit_id INTEGER REFERENCES hits(hit_id),
    PRIMARY KEY (event_id, position)
);
CREATE TABLE IF NOT EXISTS checks (
    check_id INTEGER PRIMARY KEY,
    event_id INTEGER,
    lead TEXT,                    -- check.py's lead id
    name TEXT NOT NULL,
    result TEXT,
    strength TEXT,                -- shown, indicated, coincidence possible (Phase 5)
    evidence TEXT,                -- JSON
    version TEXT,
    checked_utc TEXT
);
CREATE TABLE IF NOT EXISTS injections (
    injection_id INTEGER PRIMARY KEY,
    run_id INTEGER REFERENCES runs(run_id),
    file TEXT,
    method TEXT,                  -- how the signal was made
    channel INTEGER,
    f_start_mhz REAL,
    drift_hz_s REAL,
    snr_planted REAL,
    height REAL,                  -- raw units added a spectrum
    found INTEGER,
    hit_snr REAL,
    hit_drift_hz_s REAL
);
"""


def path():
    return yoke.DATA / "ssy.sqlite"


def connect(where=None):
    where = where or path()
    where.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(where), timeout=60)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    _migrate(db)
    db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    return db


MIGRATIONS = [("runs", "search_version", "TEXT"), ("hits", "superseded_run", "INTEGER"),
              ("events", "superseded_run", "INTEGER"), ("events", "supersedes_event_id", "INTEGER"),
              ("hits", "box_channels", "INTEGER"), ("hits", "wide", "INTEGER"), ("hits", "noise_factor", "REAL"),
              ("blocks", "shadow_hits", "INTEGER")]


def _migrate(db):
    """Columns added since a store was made, added to it; nothing removed."""
    with db:
        for table, column, kind in MIGRATIONS:
            if column not in {r[1] for r in db.execute(f"PRAGMA table_info({table})")}:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        db.execute("CREATE INDEX IF NOT EXISTS hits_current ON hits (session, block_idx, superseded_run)")
        db.execute("CREATE INDEX IF NOT EXISTS events_current ON events (session, block_idx, superseded_run)")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start_run(db, command, params, search_version=None):
    p = yoke.provenance()
    with db:
        cur = db.execute(
            "INSERT INTO runs (started_utc, command, git_commit, uncommitted_changes, host, python, libraries, params,"
            " search_version) VALUES (?,?,?,?,?,?,?,?,?)",
            (now(), command, p["git_commit"], p["uncommitted_changes"], socket.gethostname(),
             platform.python_version(), json.dumps(p["libraries"]), json.dumps(params, default=yoke.jsonable),
             search_version))
    return cur.lastrowid


def finish_run(db, run_id):
    with db:
        db.execute("UPDATE runs SET finished_utc=? WHERE run_id=?", (now(), run_id))


def _num(v, cast=float):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return None


def _sexagesimal(v):
    """src_raj / src_dej as Green Bank writes them (hhmmss.s or ddmmss.s
    packed into one number) as hours or degrees."""
    v = _num(v)
    if v is None:
        return None
    sign, v = (-1 if v < 0 else 1), abs(v)
    a, rest = divmod(v, 10000)
    b, c = divmod(rest, 100)
    return sign * (a + b / 60 + c / 3600)


def upsert_file(db, index, session=None, target=None, cadence_target=None, position=None, is_on=None):
    """The file's row, from its chunk index; its id."""
    a = index["attrs"]
    url = index["url"]
    scan = url.rsplit("_", 1)[-1].split(".")[0] if "_" in url else None
    row = (index.get("etag"), index.get("size"), session, scan, target, cadence_target, position,
           None if is_on is None else int(is_on), _num(a.get("tstart")), _num(a.get("fch1")), _num(a.get("foff")),
           _num(a.get("tsamp")), _num(a.get("nchans"), int), index["shape"][0],
           _sexagesimal(a.get("src_raj")), _sexagesimal(a.get("src_dej")), _num(a.get("telescope_id"), int),
           json.dumps(a, default=yoke.jsonable))
    with db:
        db.execute(
            "INSERT INTO files (url, etag, size, session, scan, target, cadence_target, cadence_position, is_on,"
            " tstart_mjd, fch1_mhz, foff_mhz, tsamp_s, nchans, n_spectra, ra_hours, dec_degrees, telescope_id, attrs)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(url) DO UPDATE SET etag=excluded.etag, size=excluded.size,"
            " session=coalesce(excluded.session, session), scan=excluded.scan, target=coalesce(excluded.target, target),"
            " cadence_target=coalesce(excluded.cadence_target, cadence_target),"
            " cadence_position=coalesce(excluded.cadence_position, cadence_position),"
            " is_on=coalesce(excluded.is_on, is_on), tstart_mjd=excluded.tstart_mjd, fch1_mhz=excluded.fch1_mhz,"
            " foff_mhz=excluded.foff_mhz, tsamp_s=excluded.tsamp_s, nchans=excluded.nchans,"
            " n_spectra=excluded.n_spectra, ra_hours=excluded.ra_hours, dec_degrees=excluded.dec_degrees,"
            " telescope_id=excluded.telescope_id, attrs=excluded.attrs",
            (url,) + row)
    return db.execute("SELECT file_id FROM files WHERE url=?", (url,)).fetchone()[0]


def cadence_files(db, target):
    """The six files of the target's cadence, if a sweep has kept them:
    (session, [url, ...]) in cadence order, or None."""
    rows = db.execute("SELECT url, session FROM files WHERE cadence_target=? ORDER BY cadence_position",
                      (target,)).fetchall()
    if len(rows) != 6 or len({r["session"] for r in rows}) != 1:
        return None
    return rows[0]["session"], [r["url"] for r in rows]


def done_blocks(db, session, search_version=None):
    """The blocks of a session searched; with `search_version`, only those
    searched by that version of the search (the rest are to be searched
    again)."""
    rows = db.execute("SELECT b.*, r.search_version FROM blocks b LEFT JOIN runs r ON r.run_id = b.run_id"
                      " WHERE b.session=? AND b.status='done' ORDER BY b.block_idx", (session,))
    return {r["block_idx"]: dict(r) for r in rows
            if search_version is None or r["search_version"] == search_version}


def _flag(v):
    return None if v is None else int(v)


def _hit_row(run_id, file_id, session, block_idx, h, origin=None):
    origin = origin or ("shadow" if h.get("shadow") else "search")
    return (run_id, file_id, session, block_idx, h.get("file_channel", h["channel"]), h["frequency_mhz"],
            h.get("end_frequency_mhz"), h["drift_hz_s"], h.get("drift_error_hz_s"), h.get("drift_norm"), h["snr"],
            h.get("power"), h.get("noise"), h.get("width_channels"), h.get("smear"), _flag(h.get("near_edge")),
            _flag(h.get("near_dc")), h.get("flagged_fraction"), h.get("box_channels"), _flag(h.get("wide")),
            h.get("noise_factor"), origin)


def save_block(db, run_id, session, block_idx, f_lo, f_hi, file_ids, looks_hits, events, timing, same=None):
    """One block's hits (all six looks) and cadence results, in one
    transaction. An earlier search of the block is kept, marked superseded
    by this run; `same(old_event_row, new_event)` says which earlier event
    a new one replaces."""
    with db:
        earlier = [dict(r) for r in db.execute(
            "SELECT event_id, f_start_mhz, drift_hz_s, label FROM events"
            " WHERE session=? AND block_idx=? AND superseded_run IS NULL", (session, block_idx))]
        db.execute("UPDATE events SET superseded_run=? WHERE session=? AND block_idx=? AND superseded_run IS NULL",
                   (run_id, session, block_idx))
        db.execute("UPDATE hits SET superseded_run=? WHERE session=? AND block_idx=? AND superseded_run IS NULL",
                   (run_id, session, block_idx))
        ids = []
        for file_id, hits in zip(file_ids, looks_hits):
            these = []
            for h in hits:
                cur = db.execute(
                    "INSERT INTO hits (run_id, file_id, session, block_idx, channel, f_start_mhz, f_end_mhz,"
                    " drift_hz_s, drift_err_hz_s, drift_norm, snr, power, noise, width_channels, smear, near_edge,"
                    " near_dc, flagged_fraction, box_channels, wide, noise_factor, origin)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    _hit_row(run_id, file_id, session, block_idx, h))
                these.append(cur.lastrowid)
            ids.append(these)
        for e in events:
            matches = e.get("matches") or [None] * 6
            looks = []
            for pos, m in enumerate(matches):
                hit = looks_hits[pos][m] if m is not None else None
                looks.append({"position": pos, "found": m is not None,
                              "snr": hit and hit["snr"], "drift_hz_s": hit and hit["drift_hz_s"]})
            before = next((o for o in earlier if same and same(o, e)), None)
            if before:
                earlier.remove(before)
            cur = db.execute(
                "INSERT INTO events (run_id, session, block_idx, seed_hit_id, label, f_start_mhz, drift_hz_s, snr,"
                " looks, supersedes_event_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (run_id, session, block_idx, ids[0][matches[0]] if matches[0] is not None else None, e["label"],
                 e["frequency_mhz"], e["drift_hz_s"], e["snr"], json.dumps(looks), before and before["event_id"]))
            e["event_id"], e["supersedes_event_id"] = cur.lastrowid, before and before["event_id"]
            for pos, m in enumerate(matches):
                if m is not None:
                    db.execute("INSERT INTO event_hits (event_id, position, hit_id) VALUES (?,?,?)",
                               (cur.lastrowid, pos, ids[pos][m]))
        count = {label: sum(e["label"] == label for e in events) for label in ("candidate", "interference", "unconfirmed")}
        db.execute(
            "INSERT OR REPLACE INTO blocks (session, block_idx, f_lo_mhz, f_hi_mhz, status, run_id, bytes, fetch_s,"
            " search_s, wall_s, threads, hits, shadow_hits, candidates, interference, unconfirmed, searched_utc)"
            " VALUES (?,?,?,?,'done',?,?,?,?,?,?,?,?,?,?,?,?)",
            (session, block_idx, f_lo, f_hi, run_id, timing.get("bytes"), timing.get("fetch_s"),
             timing.get("search_s"), timing.get("wall_s"), timing.get("threads"),
             sum(1 for hits in looks_hits for h in hits if not h.get("shadow")),
             sum(1 for hits in looks_hits for h in hits if h.get("shadow")),
             count["candidate"], count["interference"], count["unconfirmed"], now()))


def save_injections(db, run_id, path, method, rows):
    with db:
        db.executemany(
            "INSERT INTO injections (run_id, file, method, channel, f_start_mhz, drift_hz_s, snr_planted, height,"
            " found, hit_snr, hit_drift_hz_s) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(run_id, str(path), method, r["channel"], r["frequency_mhz"], r["drift_hz_s"], r["snr"], r["height"],
              int(r["found"]), r.get("hit_snr"), r.get("hit_drift_hz_s")) for r in rows])


def save_check(db, lead, name, result, evidence, version, event_id=None, strength=None):
    with db:
        db.execute("INSERT INTO checks (event_id, lead, name, result, strength, evidence, version, checked_utc)"
                   " VALUES (?,?,?,?,?,?,?,?)",
                   (event_id, lead, name, result, strength, json.dumps(evidence, default=yoke.jsonable), version, now()))


def candidates(db, session):
    """The current candidates of a session (not those of a superseded search)."""
    return [dict(r) for r in db.execute(
        "SELECT * FROM events WHERE session=? AND label='candidate' AND superseded_run IS NULL ORDER BY snr DESC",
        (session,))]
