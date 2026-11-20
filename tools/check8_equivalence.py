"""Check 8 before and after its lookups were indexed (commit bce4704): the
same relations, in the same order, the same chance rate and the same label,
on both sessions' hits from the store (opened read-only).

    python tools/check8_equivalence.py [--chance N] [--relations M]

`old()` is the check as vetting.vet ran it before bce4704, copied unchanged
from that version (it was inline in vet(); only its inputs are made
arguments). Compared on, per session and for two drift steps:

- N frequencies with the full check (relations, the 200-trial chance rate,
  "indicated" / "coincidence possible" / none): the session's candidates
  from its vetting run, then random frequencies in its band;
- M more for the relations alone (the old chance rate takes minutes a
  candidate at L band's 445,000 hits);
- edge cases, relations alone: a frequency exactly at, just inside and just
  outside the 1 kHz tolerance of a hit, of a harmonic and of a clock
  spacing, and the band's two ends; and with the chance rate: no hits, one
  hit, repeated frequencies.

Any difference is printed; the exit status is the number of differences.
"""
import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check      # noqa: E402
import store      # noqa: E402
import vetting    # noqa: E402

CLOCKS_MHZ, HARMONICS, TOLERANCE_HZ = vetting.CLOCKS_MHZ, vetting.HARMONICS, vetting.TOLERANCE_HZ
CHANCE_SMALL, _near_any = vetting.CHANCE_SMALL, vetting._near_any


def old(f, session_hits, step, trials=200, chance=True):
    """Check 8 as it was before bce4704 (vetting.py, inside vet()), a scan of every hit, with the parents
    rule of checks version 5 written out pair by pair: f1 and f2 strong hits not within the tolerance of
    the candidate, and f2 not the same tone as f1."""
    freqs = np.array([h["frequency_mhz"] for h in session_hits]) if session_hits else np.array([])
    strong0 = np.array([h["frequency_mhz"] for h in session_hits
                        if abs(h["drift_hz_s"]) < step and h["snr"] >= 20]) if session_hits else np.array([])
    strong_sorted = np.sort(strong0)
    lo_band = float(freqs.min()) if len(freqs) else f - 1
    hi_band = float(freqs.max()) if len(freqs) else f + 1

    def relations(x):
        found = []
        if len(freqs):
            tol_mhz = TOLERANCE_HZ / 1e6
            for n in HARMONICS:
                for target_f, kind in ((x * n, f"x{n}"), (x / n, f"/{n}")):
                    if lo_band <= target_f <= hi_band and np.any(np.abs(freqs - target_f) <= tol_mhz):
                        found.append(kind)
            for clock in CLOCKS_MHZ:
                m = np.round(np.abs(freqs - x) / clock)
                ok = (m >= 1) & (np.abs(np.abs(freqs - x) - m * clock) <= tol_mhz)
                if ok.any():
                    found.append(f"{clock:g} MHz spacing")
            parents = strong_sorted[np.abs(strong_sorted - x) > tol_mhz]
            if len(parents) >= 2:
                for a in (1, 2, 3):
                    for b in (1, 2, 3):
                        t = tol_mhz / b
                        hit = False
                        for f1 in parents:
                            for need in ((a * f1 - x) / b, (x - a * f1) / b):
                                if abs(need - f1) > t and np.any(np.abs(parents - need) <= t):
                                    hit = True
                        if hit:
                            found.append(f"{a}f1+-{b}f2")
        return found
    rel = relations(f)
    if not chance:
        return rel, None, None
    rng = np.random.default_rng(int(f * 1e6) % (2 ** 32))
    chance8 = (sum(bool(relations(float(rng.uniform(lo_band, hi_band)))) for _ in range(trials)) / trials
               if len(freqs) else 0.0)
    strength8 = ("indicated" if rel and chance8 < CHANCE_SMALL else "coincidence possible" if rel else None)
    return rel, round(chance8, 3), strength8


def new(f, session_hits, step, trials=200, chance=True):
    """Check 8 as vet() runs it now."""
    freqs = np.array([h["frequency_mhz"] for h in session_hits]) if session_hits else np.array([])
    strong0 = np.array([h["frequency_mhz"] for h in session_hits
                        if abs(h["drift_hz_s"]) < step and h["snr"] >= 20]) if session_hits else np.array([])
    if not chance:
        rel, _ = vetting._relations_and_chance(f, freqs, strong0, trials=1)
        return rel, None, None
    rel, chance8 = vetting._relations_and_chance(f, freqs, strong0, trials)
    strength8 = ("indicated" if rel and chance8 < CHANCE_SMALL else "coincidence possible" if rel else None)
    return rel, round(chance8, 3), strength8


def candidates(session):
    """The session's candidate frequencies from its vetting runs' records."""
    out = []
    for p in glob.glob(str(Path(__file__).resolve().parents[1] / "data" / "curved_pass" / f"vet-*-{session}*"
                           / "block_*.json")):
        r = json.loads(Path(p).read_text(encoding="utf-8"))
        out += [x["f_mhz"] for by in r["false"].values() for rows in by.values() for x in rows]
    return sorted(set(out))


def edges(hits):
    """Frequencies at and around the places a relation starts or stops."""
    fs = np.sort([h["frequency_mhz"] for h in hits])
    tol = TOLERANCE_HZ / 1e6
    base = float(fs[len(fs) // 2])
    out = [float(fs[0]), float(fs[-1])]
    for d in (0.0, tol, tol * (1 - 1e-9), tol * (1 + 1e-9)):
        out += [base + d, base - d]
        out += [(base + d) / 2, (base - d) / 3]                    # x2 and x3 harmonics of a hit
        out += [base + 10 + d, base - 25 - d, base + 2.000004 * 3 + d]   # clock spacings
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chance", type=int, default=10)
    ap.add_argument("--relations", type=int, default=500)
    a = ap.parse_args()
    db = store.connect_readonly()
    sessions = [r[0] for r in db.execute("SELECT DISTINCT session FROM hits WHERE origin='search'")]
    differ = compared = 0
    rng = np.random.default_rng(8)

    def same(f, hits, step, chance):
        nonlocal differ, compared
        x, y = old(f, hits, step, chance=chance), new(f, hits, step, chance=chance)
        compared += 1
        if x != y:
            differ += 1
            print(f"  DIFFER at {f!r} MHz, step {step}: before {x}, now {y}")

    for f, hits in ((1000.0, []), (1000.0, [{"frequency_mhz": 1000.0005, "drift_hz_s": 0.0, "snr": 30.0}]),
                    (1000.0, [{"frequency_mhz": 500.0, "drift_hz_s": 0.0, "snr": 30.0}] * 3),
                    (1500.0, [{"frequency_mhz": 1000.0, "drift_hz_s": 0.0, "snr": 30.0},
                              {"frequency_mhz": 2000.0, "drift_hz_s": 0.0, "snr": 30.0},
                              {"frequency_mhz": 1000.0, "drift_hz_s": 0.0, "snr": 30.0}])):
        same(f, hits, 0.01, True)
    print(f"edge cases with few hits: {compared} compared, {differ} differ")
    for session in sessions:
        hits = check.session_hits(db, session)
        if not hits:
            continue
        fs = np.array([h["frequency_mhz"] for h in hits])
        lo, hi = float(fs.min()), float(fs.max())
        cands = candidates(session)
        full = cands[:a.chance] + [float(x) for x in rng.uniform(lo, hi, max(0, a.chance - len(cands)))]
        rel_only = [float(x) for x in rng.uniform(lo, hi, a.relations)] + cands[a.chance:a.chance + a.relations]
        before = (compared, differ)
        for step in (0.0102, 0.02):
            for f in full:
                same(f, hits, step, True)
            for f in edges(hits):
                same(f, hits, step, False)
            for f in rel_only:
                same(f, hits, step, False)
        print(f"{session}: {len(hits)} hits, {len(cands)} candidates on record; "
              f"{compared - before[0]} compared ({len(full)} with the chance rate, a step), "
              f"{differ - before[1]} differ", flush=True)
    print(f"all: {compared} compared, {differ} differ")
    return differ


if __name__ == "__main__":
    sys.exit(main())
