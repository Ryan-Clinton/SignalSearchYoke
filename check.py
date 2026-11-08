#!/usr/bin/env python3
"""Look into the sweeps' candidates: each one's signs of interference,
with the evidence, kept as a record and a report.

    ./check.py              every candidate in the sweeps not yet looked into
    ./check.py --all        all of them again
    ./check.py --json

A candidate (seti.py: in every ON look, in no OFF look) is checked against
the bands satellites and ground transmitters use (ITU Radio Regulations,
Article 5) and for a drift of zero, which is what a transmitter fixed to
the ground gives. A sign is not proof: an allocated band does not say
which transmitter made it, and a zero drift is not proof of a ground
transmitter. The verdict is "likely interference" with its signs, or
"unexplained, weak". Only the same signal checked in another session of
the star, in a different star, or against a known transmitter says more.

Records: data/checks/LEAD.json; reports: docs/leads/LEAD.md.
"""
import argparse
import json
from datetime import datetime, timezone

import store
import yoke

REPORTS = yoke.ROOT / "docs" / "leads"
CHECK_VERSION = "1"

# Bands satellites and the ground transmit in (ITU Radio Regulations,
# Article 5), MHz: a hit inside one is most likely one of them.
SATELLITE_BANDS = [
    (1164.0, 1189.0, "GPS L5 / Galileo E5a"), (1215.0, 1240.0, "GPS L2 / Galileo E6"),
    (1525.0, 1559.0, "Inmarsat and other mobile satellites"), (1559.0, 1610.0, "GPS L1, GLONASS, Galileo, BeiDou"),
    (1610.0, 1626.5, "Iridium and Globalstar"), (1670.0, 1710.0, "weather satellites"),
    (2200.0, 2290.0, "space operation and research downlinks"), (2320.0, 2345.0, "satellite radio (SDARS)"),
    (2400.0, 2483.5, "Wi-Fi and the ISM band"), (2483.5, 2500.0, "Globalstar downlinks")]


def lead_id(lead):
    return f"SETI-{lead['target']}-{lead.get('session') or 'unknown'}-{lead['frequency_mhz']:.6f}"


def signal_id(lead):
    """What links detections that may be one signal: the target and the
    frequency to the kHz, whatever session saw it (drift moves a signal by
    well under a kHz over a cadence)."""
    return f"{lead['target']}-{lead['frequency_mhz']:.3f}"


def records_dir():
    return yoke.DATA / "checks"


def done():
    """Every candidate looked into, by its id: its kept record."""
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(records_dir().glob("*.json"))}


def leads():
    """Every candidate in the sweeps' records, strongest first. Hits labelled
    interference or unconfirmed are left in the sweep's record."""
    out = []
    for path in sorted((yoke.DATA / "sweeps").glob("*.json")):
        kept = json.loads(path.read_text(encoding="utf-8"))
        target, session = path.stem.rsplit("-", 1) if "-" in path.stem else (path.stem, "")
        for block in kept.get("done", {}).values():
            for e in block.get("events", []):
                if e.get("label", "candidate") != "candidate":
                    continue
                out.append({"target": target, "session": session, **e, "signal": signal_id({"target": target, **e})})
    return sorted(out, key=lambda e: -e.get("snr", 0))


def check(lead):
    """One candidate's signs of interference, each with its evidence."""
    f = lead["frequency_mhz"]
    band = next((b for b in SATELLITE_BANDS if b[0] <= f <= b[1]), None)
    signs = []
    if band:
        signs.append(f"{f:.6f} MHz is in {band[2]} ({band[0]:g} to {band[1]:g} MHz, ITU Radio Regulations "
                     f"Article 5): such transmitters are common there, though the band alone does not name one")
    drift = lead.get("drift_hz_s", 0.0) or 0.0
    if abs(drift) < 1e-3:
        signs.append(f"a drift of {drift:g} Hz/s: what a transmitter fixed to the ground gives (Breakthrough "
                     "Listen sets zero-drift hits aside for this reason, Enriquez et al. 2017), not proof of one")
    seen = (f"seen in all {len(lead['in_on'])} ON looks and none of the {len(lead.get('in_off', []))} OFF looks"
            if lead.get("in_on") else "passed the ON/OFF test")
    return {"lead": lead_id(lead), "signal": signal_id(lead), "star": lead["target"], "frequency_mhz": f,
            "drift_hz_s": lead.get("drift_hz_s"), "snr": lead.get("snr"), "session": lead.get("session"),
            "band": band and band[2], "verdict": "likely interference" if signs else "unexplained, weak",
            "likely_because": signs,
            "notes": [seen + ".", "to settle it: the same frequency in another session of this star or a "
                      "different star (./seti.py find), and the known transmitters at that frequency"],
            "checked": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def report(r):
    lines = [f"# {r['star']} at {r['frequency_mhz']:.6f} MHz: {r['verdict']}", "",
             f"Looked into by `check.py` on {r['checked'][:10]} (`{r['lead']}`, signal `{r['signal']}`). "
             "\"Unexplained\" is the end of these checks, not a discovery.", "",
             f"- Session {r['session']}, SNR {r['snr']}, drift {r['drift_hz_s']} Hz/s",
             f"- Band (ITU Radio Regulations, Article 5): {r['band'] or 'none listed here'}", "", "## The verdict", "",
             f"**{r['verdict']}**", ""]
    lines += [f"- sign of interference: {why}" for why in r["likely_because"]]
    lines += [f"- {note}" for note in r["notes"]]
    return "\n".join(lines) + "\n"


def run(args, say=print):
    taken = {} if args.all else done()
    fresh = [lead for lead in leads() if lead_id(lead) not in taken]
    out = []
    db = store.connect() if fresh else None
    for lead in fresh:
        r = check(lead)
        yoke.write(records_dir() / f"{r['lead']}.json", r)
        store.save_check(db, r["lead"], "bands and zero drift", r["verdict"],
                         {"band": r["band"], "signs": r["likely_because"]}, CHECK_VERSION, event_id=lead.get("event_id"),
                         strength="indicated" if r["likely_because"] else None)
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"{r['lead']}.md").write_text(report(r), encoding="utf-8")
        say(f"{r['star']} {r['frequency_mhz']:.6f} MHz: {r['verdict']}")
        out.append(r)
    if db:
        db.close()
    if not fresh:
        say("No candidate waiting: every one in the sweeps has been looked into.")
    return {"checked": out, "candidates": len(leads())}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="look into every candidate again")
    ap.add_argument("--json", action="store_true", help="answer in JSON")
    args = ap.parse_args()
    yoke.main("check", lambda: run(args), args.json)


if __name__ == "__main__":
    main()
