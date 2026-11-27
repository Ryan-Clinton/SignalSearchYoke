"""A candidate's dossier: the ten checks run again on one candidate of a
control's store, by the checks in force and by the candidate version 6, through
a connection that cannot write, so its recorded verdicts stay as they are.

    python tools/lead_dossier.py --control c --event 390050

Writes, beside each other in docs/leads/control-c/: each version's report as
check.py writes one (LEAD.md, with a PNG of the six looks around the track),
and LEAD-dossier.md, which sets the two verdicts side by side with what each
check found, the verdicts recorded in the store, and what has not been done.
The record goes to data/analysis/negative_controls_c/lead_EVENT.json.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import yoke  # noqa: E402

NOT_DONE = (
    "No other pipeline has been run on this block: turboSETI and BLISS were run on the project's sessions, "
    "not on the controls' cadences.",
    "No other observation of this target, and no follow-up, has been looked at beyond what check 6 reads "
    "(the store's other sessions).",
    "No list of satellites has been searched: check 3 names the listed band, and the band names the services "
    "allocated there, not a transmitter.",
)


def dossier(control, event_id, say=print):
    os.environ["SSY_CONTROL"] = control            # before the tools are imported: their paths are the control's
    import check
    import negative_controls as nc
    import store
    import vetting
    db = store.connect_readonly(nc.CONTROLS / "ssy.sqlite")
    try:
        row = db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        if row is None:
            raise yoke.Refusal("INVALID_REQUEST", f"No event {event_id} in control {control}'s store.")
        session, block_idx = row["session"], row["block_idx"]
        looks, where, _ = check._cadence(db, session, block_idx)
        e = check._event(db, row, where)
        target = check.target_of(db, session)
        own = {r["hit_id"] for r in db.execute("SELECT hit_id FROM event_hits WHERE event_id=?", (event_id,))}
        lead = check.lead_id(target["name"], session, e["frequency_mhz"])
        out_dir = ROOT / "docs" / "leads" / f"control-{control}"
        out_dir.mkdir(parents=True, exist_ok=True)
        hits = check.session_hits(db, session)
        runs = {}
        for name, version, context in (("5", vetting.VERSION_5, False), ("6", vetting.VERSION_BANDS_AS_CONTEXT, True)):
            res = check.vet_from_store(db, e, looks, session, target, own, hits=hits, report_dir=out_dir,
                                       lead=f"{lead}-v{name}", bands_as_context=context)
            runs[name] = {"version": version, "verdict": res["verdict"], "checks": res["checks"]}
        recorded = {name: [r[0] for r in db.execute(
            "SELECT result FROM checks WHERE event_id=? AND version=? AND name='10. report'", (event_id, version))]
            for name, version in (("5", vetting.VERSION_5), ("6", vetting.VERSION_BANDS_AS_CONTEXT))}
    finally:
        db.close()
    same = {k: runs[k]["verdict"] in recorded[k] for k in runs}
    rec = {"control": control, "event_id": event_id, "lead": lead, "session": session, "block": block_idx,
           "target": target.get("name"), "frequency_mhz": e["frequency_mhz"], "drift_hz_s": e["drift_hz_s"],
           "snr": e["snr"], "runs": runs, "recorded_verdicts": recorded, "run_again_gives_the_recorded": same,
           "not_done": list(NOT_DONE), "kind": "measured"}
    yoke.write(yoke.DATA / "analysis" / f"negative_controls_{control}" / f"lead_{event_id}.json", rec, indent=1,
               stamp=True)
    (out_dir / f"{lead}-dossier.md").write_text(page(rec), encoding="utf-8")
    say(f"{lead}: version 5 {runs['5']['verdict']}, version 6 {runs['6']['verdict']}; the store's verdicts "
        f"{'are' if all(same.values()) else 'are NOT'} what running the checks again gives")
    return rec


def _result(c):
    return " ".join(str(x) for x in (c.get("result") or "—", f"({c['strength']})" if c.get("strength") else "") if x)


def page(rec):
    """The dossier as a page: who, where, both versions' checks side by side, what is not done."""
    r5, r6 = rec["runs"]["5"], rec["runs"]["6"]
    by6 = {c["name"]: c for c in r6["checks"]}
    lines = [f"# Control {rec['control'].upper()} candidate {rec['lead']}: dossier", "",
             "Written by `tools/lead_dossier.py`. The ten checks run again on one real candidate of control "
             f"{rec['control'].upper()}, by both versions, through a connection to its store that cannot write. "
             "The verdicts the store recorded are not changed: this page records what was found later, beside them.",
             "",
             f"- **Where:** {rec['target']}, session {rec['session']}, block {rec['block']}, "
             f"{rec['frequency_mhz']:.6f} MHz, drift {rec['drift_hz_s']:+.4f} Hz/s, S/N {rec['snr']:.1f}.",
             f"- **Version 5 (in force):** {r5['verdict']}. **Version 6:** {r6['verdict']}.",
             f"- **Recorded in the store:** version 5 {', '.join(rec['recorded_verdicts']['5']) or 'none'}; version 6 "
             f"{', '.join(rec['recorded_verdicts']['6']) or 'none'}. Running the checks again gives "
             + ("the same." if all(rec["run_again_gives_the_recorded"].values()) else "something else: see the record."),
             f"- **Each version's full report:** [{rec['lead']}-v5.md]({rec['lead']}-v5.md) and "
             f"[{rec['lead']}-v6.md]({rec['lead']}-v6.md), each with a PNG of the six looks around the track.",
             "", "| check | version 5 | version 6 |", "|---|---|---|"]
    for c in r5["checks"]:
        lines.append(f"| {c['name']} | {_result(c)} | {_result(by6.get(c['name'], {}))} |")
    lines += ["", "## Not done", ""] + [f"- {x}" for x in rec["not_done"]] + [
        "", "\"Unexplained\" is where these checks end, not a discovery.", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--control", default="c")
    ap.add_argument("--event", type=int, required=True)
    args = ap.parse_args(argv)
    dossier(args.control.lower(), args.event)


if __name__ == "__main__":
    main()
