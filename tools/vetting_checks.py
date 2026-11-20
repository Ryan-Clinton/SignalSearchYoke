"""Checks of candidate vetting and ranking (docs/audits.md 12), measured on
the stored check records and the store; supplementary, changing no record.

    python tools/vetting_checks.py

- **self-intermodulation** (F12-02): check 8 tests a·f1 ± b·f2 = f over the
  session's strong zero-drift hits, which include the candidate's own hits;
  with a − b = 1, f1 = f2 = f always satisfies it. Each record's check 8
  recomputed with its own hits left out of the strong list.
- **same-target recurrence** (F12-01): files of the same target in other
  sessions, which check 6 would count as recurrence elsewhere.
- **missing evidence** (F12-04): records called sound without stamps.
- **report identities** (F12-06): candidate events sharing a lead id
  (target, session, frequency to 1 Hz).
- **calibration** (F12-09): sessions with candidates and no OFF null.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import check  # noqa: E402
import store  # noqa: E402
import vetting  # noqa: E402
import yoke  # noqa: E402

OUT = yoke.DATA / "analysis" / "vetting_checks.json"


def own_hits(db, event_id):
    return [dict(r) for r in db.execute(
        "SELECT h.hit_id, h.f_start_mhz AS frequency_mhz, h.drift_hz_s, h.snr FROM event_hits e "
        "JOIN hits h ON h.hit_id = e.hit_id WHERE e.event_id = ?", (event_id,))]


def strong_zero(hits, step):
    return np.array([h["frequency_mhz"] for h in hits if abs(h["drift_hz_s"]) < step and h["snr"] >= 20])


def self_intermod(db, rec, step):
    hits = check.session_hits(db, rec["session"])
    own = own_hits(db, rec["event_id"])
    own_f = {round(h["frequency_mhz"], 9) for h in own}
    freqs = np.array([h["frequency_mhz"] for h in hits])
    s_all = strong_zero(hits, step)
    s_wo = np.array([x for x in s_all if round(x, 9) not in own_f])
    rel_all, ch_all = vetting._relations_and_chance(rec["frequency_mhz"], freqs, s_all)
    rel_wo, ch_wo = vetting._relations_and_chance(rec["frequency_mhz"], freqs, s_wo)
    return {"lead": rec["lead"], "own_hits_strong_zero_drift": int(len(s_all) - len(s_wo)),
            "relations": rel_all, "relations_without_own": rel_wo,
            "lost": sorted(set(rel_all) - set(rel_wo)), "chance": round(ch_all, 3), "chance_without_own": round(ch_wo, 3),
            "strength_recorded": next((c["strength"] for c in rec["checks"] if c["n"] == 8), None)}


def recheck(db, recs, say=print):
    """Each record's candidate checked again with the current checks version, nothing written: its
    verdict and each check's result and strength against the record's."""
    rows = []
    for r in recs:
        row = db.execute("SELECT * FROM events WHERE event_id=?", (r["event_id"],)).fetchone()
        looks, where, _ = check._cadence(db, row["session"], row["block_idx"])
        e = check._event(db, row, where)
        own = {x["hit_id"] for x in db.execute("SELECT hit_id FROM event_hits WHERE event_id=?", (row["event_id"],))}
        new = check.vet_from_store(db, e, looks, row["session"], check.target_of(db, row["session"]), own)
        old_c = {c["n"]: (c["result"], c["strength"]) for c in r["checks"]}
        new_c = {c["n"]: (c["result"], c["strength"]) for c in new["checks"]}
        changed = {n: [old_c.get(n), new_c.get(n)] for n in sorted(set(old_c) | set(new_c))
                   if (old_c.get(n) or (None, None))[1] != (new_c.get(n) or (None, None))[1]
                   or ((old_c.get(n) or (None,))[0] != (new_c.get(n) or (None,))[0] and n in (1, 6))}
        rows.append({"lead": r["lead"], "verdict_recorded": r["verdict"], "verdict_now": new["verdict"],
                     "checks_changed": changed})
        say(f"{r['lead']}: {r['verdict']} -> {new['verdict']}; changed {changed}")
    return {"version_recorded": recs[0]["version"] if recs else None, "version_now": vetting.VERSION,
            "verdicts_changed": sum(x["verdict_recorded"] != x["verdict_now"] for x in rows), "rows": rows}


def main(say=print):
    db = store.connect_readonly()
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(check.records_dir().glob("SETI-*.json"))]
    recs = [r for r in recs if "session" in r and "checks" in r]
    out = {"kind": "measured", "records": len(recs)}
    step = 2.7939677238464355 / (15 * 18.253611008)       # the GBT high-resolution drift step
    out["self_intermodulation"] = [self_intermod(db, r, step) for r in recs]
    for x in out["self_intermodulation"]:
        say(f"{x['lead']}: own strong zero-drift hits {x['own_hits_strong_zero_drift']}; lost without them "
            f"{x['lost']}; chance {x['chance']} -> {x['chance_without_own']}; recorded {x['strength_recorded']}")
    by_target = Counter((r["target"], r["session"]) for r in db.execute(
        "SELECT DISTINCT COALESCE(cadence_target, target) AS target, session FROM files WHERE is_on = 1"))
    targets = Counter(t for t, _ in by_target)
    out["same_target_other_sessions"] = {t: n for t, n in targets.items() if n > 1}
    say(f"targets with ON looks in more than one session: {out['same_target_other_sessions']}")
    unsound = []
    for r in recs:
        c1 = next((c for c in r["checks"] if c["n"] == 1), None)
        ev = (c1 or {}).get("evidence", {})
        if c1 and c1["result"] == "sound" and (ev.get("stamps_finite") is None or ev.get("blank_stamp_spectra") is None):
            unsound.append(r["lead"])
    out["sound_without_stamps"] = unsound
    say(f"records called sound without stamps: {unsound}")
    leads = Counter(check.lead_id(check.target_of(db, r["session"])["name"], r["session"], r["frequency_mhz"])
                    for r in db.execute("SELECT session, f_start_mhz AS frequency_mhz FROM events "
                                        "WHERE label = 'candidate' AND superseded_run IS NULL"))
    out["lead_id_collisions"] = {k: n for k, n in leads.items() if n > 1}
    say(f"candidate events sharing a lead id: {out['lead_id_collisions']}")
    sessions = {r["session"] for r in recs}
    out["off_null_present"] = (yoke.DATA / "measurements" / "off_null.json").exists()
    out["sessions_with_records"] = sorted(sessions)
    say(f"OFF null recorded: {out['off_null_present']} (sessions with check records: {sorted(sessions)})")
    out["recheck"] = recheck(db, recs, say)
    db.close()
    yoke.write(OUT, out, indent=1, stamp=True)
    return out


if __name__ == "__main__":
    main()
