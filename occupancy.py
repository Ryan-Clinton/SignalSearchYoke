"""The interference occupancy of a swept session, measured from its hits
(comparable.md step 6): what the checks' chances are taken against, in
place of the uniform backgrounds they took before.

Two measurements, both from the store's hits of the session (at the cut and
shadow hits, SNR 5 to 10, as said for each), never from a model:

- **Crowding by frequency and drift** (check 9): around a candidate, the
  hits within CROWD_MHZ whose drift is like its own (within
  max(2 drift steps, 10%)), against the same count at every place of a
  grid over the band searched, for the same drift. The chance is the share
  of places with at least as many: a crowded place is unusual only if it is
  crowded *for that drift* compared with the rest of the band. Hits within
  OWN_KHZ of the candidate (or of a grid place) are not counted, so a
  candidate's own hits (in the store for a real one, not for a planted
  one) never count for or against it. Hits SNR 5 and up count (shadow hits
  included): weak members of a family of interference are evidence too.
- **Look-alikes by drift** (check 7): for each block, its OFF looks' hits
  at the cut with the same drift over frequency (drift / frequency, the
  check's own tolerance, mirror drifts included as the check includes
  them); the chance of as many as the candidate's cadence shows is the
  share of the session's other blocks with at least as many. Measured
  over the session's blocks, it holds near zero drift too, where the
  check's old chance (OFF hits' drifts taken as even over +-4 Hz/s) did
  not.

What it does not do:

- **Incomplete blocks:** a look stopped at the 2,000-hit limit (48 of
  1,848 in the KIC 8462852 sweep) holds fewer hits than were there, so its
  counts are lower bounds: a candidate there is marked so, and its
  crowding chance is an upper bound (it may be more crowded).
- **Correlated observations:** the six looks of a block share their
  interference; a place's count adds the six, at the candidate and at
  every grid place alike, so the comparison is like with like, but the
  grid's places are not independent of each other (a share near 1/places
  is no finer than the structure of the band allows; every chance is at
  least 1/places, and the ranking caps every term besides).
- **Recurrence** (check 6) already takes its chance from each file's hits
  near the candidate, with the drift share measured (checks version 3);
  **harmonics** (check 8) from random frequencies over the band against
  the session's hits: neither changed here.
"""
import numpy as np

CROWD_MHZ = 0.5          # check 9's window, each side
OWN_KHZ = 5.0            # hits this close are the candidate's own track (4 Hz/s over 20 minutes is 4.8 kHz)
GRID_MHZ = 0.01          # the places crowding is compared over
DRIFT_TOL_STEPS = 2.0
DRIFT_TOL_FRACTION = 0.1

_cache = {}


def revision(db, session):
    """What the session's current hits, blocks and looks are now: their current hits' count and highest id,
    and a hash of every block row and every current look's completeness (a few hundred rows a session), so a
    block searched again, or a look's completeness changing, makes it different."""
    import hashlib
    h = db.execute("SELECT count(*), max(hit_id) FROM hits WHERE session=? AND superseded_run IS NULL",
                   (session,)).fetchone()
    d = hashlib.sha256()
    for row in db.execute("SELECT * FROM blocks WHERE session=? ORDER BY block_idx", (session,)):
        d.update(repr(tuple(row)).encode())
    for row in db.execute("SELECT block_idx, position, complete FROM looks WHERE session=? AND superseded_run IS NULL"
                          " ORDER BY block_idx, position", (session,)):
        d.update(repr(tuple(row)).encode())
    return tuple(h) + (d.hexdigest()[:16],)


def load(db, session):
    """The session's hits (current runs), and its searched blocks and
    cut-short looks; kept in memory for the process while the session's
    hits and blocks stay as they were (revision), made again when they change."""
    key = (session, revision(db, session))
    if key in _cache:
        return _cache[key]
    rows = db.execute("SELECT h.f_start_mhz, h.drift_hz_s, h.snr, h.origin, h.block_idx, f.cadence_position"
                      " FROM hits h JOIN files f USING(file_id) WHERE h.session=? AND h.superseded_run IS NULL",
                      (session,)).fetchall()
    f = np.array([r[0] for r in rows])
    d = np.array([r[1] for r in rows])
    cut = np.array([r[3] == "search" for r in rows])
    block = np.array([r[4] for r in rows])
    pos = np.array([-1 if r[5] is None else r[5] for r in rows])
    blocks = {r[0]: (min(r[1], r[2]), max(r[1], r[2])) for r in db.execute(
        "SELECT block_idx, f_lo_mhz, f_hi_mhz FROM blocks WHERE session=? AND status='done'", (session,))}
    short = {r[0] for r in db.execute("SELECT DISTINCT block_idx FROM looks WHERE session=? AND"
                                      " superseded_run IS NULL AND complete=0", (session,))}
    grid = np.concatenate([np.arange(lo, hi, GRID_MHZ) for lo, hi in blocks.values()]) if blocks else np.array([])
    # OFF looks' hits at the cut, by block, as drift over frequency (check 7's quantity)
    off = (pos % 2 == 1) & cut
    nu_by_block = {}
    for k in blocks:
        m = off & (block == k)
        nu_by_block[k] = np.sort(d[m] / (f[m] * 1e6))
    occ = {"session": session, "f": f, "d": d, "cut": cut, "blocks": blocks, "short": short,
           "grid": grid, "nu_by_block": nu_by_block, "hits": len(f), "hits_at_cut": int(cut.sum())}
    for k in [k for k in _cache if k[0] == session]:
        del _cache[k]
    _cache[key] = occ
    return occ


def drift_tol(drift, step):
    return max(DRIFT_TOL_STEPS * step, DRIFT_TOL_FRACTION * abs(drift))


def _annulus_counts(fs, centres):
    """Hits of sorted `fs` within CROWD_MHZ of each centre, those within
    OWN_KHZ left out."""
    own = OWN_KHZ / 1e3
    return (np.searchsorted(fs, centres + CROWD_MHZ, "right") - np.searchsorted(fs, centres - CROWD_MHZ)
            - (np.searchsorted(fs, centres + own, "right") - np.searchsorted(fs, centres - own)))


def crowding(occ, f_mhz, drift, step):
    """Hits like it near the candidate, and the share of the band's places
    with as many at that drift: {near, near_at_cut, places, chance,
    median_per_place, cut_short}."""
    tol = drift_tol(drift, step)
    like = np.abs(occ["d"] - drift) <= tol
    fs = np.sort(occ["f"][like])
    fs_cut = np.sort(occ["f"][like & occ["cut"]])
    near = int(_annulus_counts(fs, np.array([f_mhz]))[0])
    near_cut = int(_annulus_counts(fs_cut, np.array([f_mhz]))[0])
    counts = _annulus_counts(fs, occ["grid"])
    places = len(counts)
    over = int(np.sum(counts >= near))
    block = next((k for k, (lo, hi) in occ["blocks"].items() if lo <= f_mhz <= hi), None)
    return {"near": near, "near_at_cut": near_cut, "drift_tolerance_hz_s": round(tol, 4), "places": places,
            "places_as_crowded": over, "chance": max(over, 1) / places if places else 1.0,
            "median_per_place": float(np.median(counts)) if places else None,
            "cut_short": bool(block in occ["short"]) if block is not None else None,
            "hits": "SNR 5 and up (shadow hits included), within 0.5 MHz, own 5 kHz left out"}


def lookalikes(occ, f_mhz, drift, step, observed, block=None):
    """The share of the session's other blocks whose OFF looks hold at least
    `observed` hits at the cut with this drift over frequency (or its mirror,
    away from zero drift), check 7's tolerance."""
    nu = drift / (f_mhz * 1e6)
    tol = 2 * step / (f_mhz * 1e6)
    mirror = abs(drift) >= step
    counts = []
    for k, arr in occ["nu_by_block"].items():
        if k == block:
            continue
        n = np.searchsorted(arr, nu + tol, "right") - np.searchsorted(arr, nu - tol)
        if mirror:
            n += np.searchsorted(arr, -nu + tol, "right") - np.searchsorted(arr, -nu - tol)
        counts.append(int(n))
    counts = np.array(counts)
    over = int(np.sum(counts >= observed)) if len(counts) else 0
    return {"observed": int(observed), "blocks": len(counts), "blocks_with_as_many": over,
            "chance": max(over, 1) / len(counts) if len(counts) else 1.0,
            "median_per_block": float(np.median(counts)) if len(counts) else None}


def block_of(occ, f_mhz):
    return next((k for k, (lo, hi) in occ["blocks"].items() if lo <= f_mhz <= hi), None)
