"""Every candidate of the project's own store judged by checks version 5 and version 6, side by side: what putting
version 6 into force changes. From the store's verdicts alone (both made by `negative_controls.py checks-here` and
`checks-here-context` on this store, each kept under its own version).

    python tools/checks_v6.py tables     data/analysis/checks_v6/tables.json

By session and cut (S/N 10 and 30): candidates, what each version calls them, how many change, and every candidate
version 6 leaves unexplained with both verdicts.
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import yoke  # noqa: E402

OUT = yoke.DATA / "analysis" / "checks_v6" / "tables.json"
CUTS = (10, 30)


def compare(v5, v6):
    """{session: {cut: counts}} and the candidates version 6 leaves unexplained, from two lists of verdicts (each
    candidate's one whole evaluation by that version, as negative_controls.candidate_verdicts gives them)."""
    import negative_controls as nc
    a, b = {e["event_id"]: e for e in v5}, {e["event_id"]: e for e in v6}
    if set(a) != set(b):
        raise yoke.Refusal("INVALID_REQUEST", "The two versions have not judged the same candidates.")
    sessions = {}
    for s in sorted({e["session"] for e in a.values()}):
        sessions[s] = {}
        for cut in CUTS:
            ids = [k for k, e in a.items() if e["session"] == s and e["snr"] >= cut]
            c5 = Counter(nc.verdict_class(a[k]["verdict"]) for k in ids)
            c6 = Counter(nc.verdict_class(b[k]["verdict"]) for k in ids)
            sessions[s][str(cut)] = {
                "candidates": len(ids), "version_5": dict(sorted(c5.items())), "version_6": dict(sorted(c6.items())),
                "unexplained_5": sum(v for k, v in c5.items() if k.startswith("unexplained")),
                "unexplained_6": sum(v for k, v in c6.items() if k.startswith("unexplained")),
                "changed": sum(nc.verdict_class(a[k]["verdict"]) != nc.verdict_class(b[k]["verdict"]) for k in ids)}
    left = [{"event_id": k, "session": e["session"], "block": e["block"], "frequency_mhz": e["frequency_mhz"],
             "drift_hz_s": e["drift_hz_s"], "snr": e["snr"], "version_5": e["verdict"], "version_6": b[k]["verdict"]}
            for k, e in sorted(a.items()) if nc.verdict_class(b[k]["verdict"]).startswith("unexplained")]
    return sessions, left


def tables(say=print):
    import negative_controls as nc
    import store
    import vetting
    db = store.connect_readonly()
    try:
        v5 = nc.candidate_verdicts(db, vetting.VERSION_5, vetting.N_CHECKS)
        v6 = nc.candidate_verdicts(db, vetting.VERSION_6, vetting.N_CHECKS)
    finally:
        db.close()
    sessions, left = compare(v5, v6)
    out = {"versions": {"5": vetting.VERSION_5, "6": vetting.VERSION_6}, "sessions": sessions,
           "unexplained_by_version_6": left, "kind": "measured"}
    yoke.write(OUT, out, indent=1, stamp=True)
    for s, cuts in sessions.items():
        for cut, c in cuts.items():
            say(f"{s} at {cut}: {c['candidates']} candidates, unexplained {c['unexplained_5']} by version 5, "
                f"{c['unexplained_6']} by version 6, {c['changed']} changed")
    return out


if __name__ == "__main__":
    if sys.argv[1:] != ["tables"]:
        sys.exit(__doc__)
    tables()
