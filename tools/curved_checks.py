"""Checks of the curved second pass (docs/audits.md 10). curved_pass.py is
frozen (steps 10 and 12 fingerprint it): the checks use a diagnostic copy of
its matcher, second_pass_all, which keeps every hypothesis instead of the
first for each set of hits, and notes whether each OFF look could be
measured. Deduplicated first-wins, it gives exactly curved_pass.second_pass
(tests/test_curved_checks.py).

    python tools/curved_checks.py blocks     2017 blocks read again (an hour or two)

- **order** (CD-01): the same hits reached from another pair of ON looks give
  another fitted acceleration and other OFF predictions; second_pass keeps
  the first. Per block and choice: sets of hits whose hypotheses disagree
  on the label, and what keeping a candidate if any hypothesis is one would
  change (false candidates, planted signals found).
- **unmeasured OFF** (CD-02): a candidate whose OFF looks could not be
  measured along its curve (best_track gave nothing) is labelled as clean.
  Per block: candidates with every OFF look unmeasured, and with some.
- **the two signals** (CD-04): the recheck recovered 6,557 at 10⁻³ and cut
  30, the vetting run 6,555; the two are block 36's signal 61 and block
  128's signal 62 (strength 400, drift ±1.84 Hz/s, ±3×10⁻⁴ Hz/s², each by
  two hits and a track). Their hypotheses in both blocks are recorded.

Blocks: 36 and 128, and eight chosen by seed 12 (as turbo_checks). Cut 30,
a_max 10⁻³ (the largest tested).
"""
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import curved  # noqa: E402
import curved_pass  # noqa: E402
import matched  # noqa: E402
import onoff  # noqa: E402
import seti  # noqa: E402
import store  # noqa: E402
import yoke  # noqa: E402

OUT = yoke.DATA / "analysis"
TARGET = "KIC8462852"
CUT = 30
A_MAX = 1e-3
TRACED = {36: 61, 128: 62}


def _say(*a):
    print(*a, flush=True)


DEPENDS = ("curved_pass.py", "curved.py", "matched.py", "onoff.py", "searching.py", "seti.py", "measure.py",
           "injection.py", "store.py", "tools/curved_checks.py", "tools/turbo_checks.py")


def fingerprint(source=""):
    """The code the results rest on, and (`source`) what was read."""
    h = hashlib.sha256()
    for f in DEPENDS:
        h.update((ROOT / f).read_bytes().replace(b"\r\n", b"\n"))
    h.update(source.encode())
    return h.hexdigest()[:16]


def second_pass_all(looks, events, a_max):
    """curved_pass.second_pass, every hypothesis kept (in the order it meets them), each with
    "sig" (its set of hits) and "off_measured" (how many OFF looks gave a measurement)."""
    taken = set()
    for e in events:
        if e["label"] in ("candidate", "interference"):
            taken.update((p, i) for p, i in enumerate(e["matches"]) if i is not None)
    on = [lk for lk in looks if lk.on]
    off = [lk for lk in looks if not lk.on]

    def free(lk):
        return sorted(((h["frequency_mhz"], i, h) for i, h in enumerate(lk.hits)
                       if not h.get("shadow") and (lk.position, i) not in taken), key=lambda x: x[0])
    pool = {lk.position: free(lk) for lk in on}
    out = []
    for la, lb in itertools.combinations(on, 2):
        lr = next(lk for lk in on if lk is not la and lk is not lb)
        span = curved._t(lb, la)
        cands_b = pool[lb.position]
        fb_arr = np.array([x[0] for x in cands_b])
        reach_hz = 4.0 * span + 0.5 * a_max * span * span + 10 * la.width_hz
        for _, ia, ha in pool[la.position]:
            lo = np.searchsorted(fb_arr, ha["frequency_mhz"] - reach_hz / 1e6)
            hi = np.searchsorted(fb_arr, ha["frequency_mhz"] + reach_hz / 1e6, "right")
            for _, ib, hb in cands_b[lo:hi]:
                a = (hb["drift_hz_s"] - ha["drift_hz_s"]) / span
                a_tol = 2 * (curved.D_TOL_STEPS * la.step + 0.05 * abs(ha["drift_hz_s"])) / span
                if abs(a) > a_max + a_tol:
                    continue
                a_use = max(-a_max, min(a_max, a))
                fb, db = curved._track(ha["frequency_mhz"], ha["drift_hz_s"], a_use, lb, la)
                if not curved._on_track(hb, fb, db, lb):
                    continue
                fr, dr = curved._track(ha["frequency_mhz"], ha["drift_hz_s"], a_use, lr, la)
                members = {la.position: ia, lb.position: ib}
                track = None
                mid = [i for i in curved._hits_near(lr, fr, dr) if (lr.position, i) not in taken]
                if mid:
                    members[lr.position] = max(mid, key=lambda i: lr.hits[i]["snr"])
                else:
                    snr, at, d_fit = lr.best_track(lr.channel(fr), dr, curved.F_TOL_CHANNELS, curved.D_TOL_STEPS)
                    if snr is None or snr < onoff.ON_MIN:
                        continue
                    track = (lr.position, at, d_fit, snr)
                off_max, off_hit, offs, measured = -np.inf, False, [], 0
                for lk in off:
                    fo, do = curved._track(ha["frequency_mhz"], ha["drift_hz_s"], a_use, lk, la)
                    snrs = []
                    for f_try in (fo, ha["frequency_mhz"]):
                        snr, _, _ = lk.best_track(lk.channel(f_try), do, curved.F_TOL_CHANNELS, curved.D_TOL_STEPS)
                        snrs.append(None if snr is None else round(snr, 2))
                        if snr is not None:
                            off_max = max(off_max, snr)
                        off_hit = off_hit or bool(curved._hits_near(lk, f_try, do, any_strength=True))
                    measured += any(x is not None for x in snrs)
                    offs.append((lk.position, *snrs))
                label = "interference" if (off_hit or off_max >= onoff.OFF_MAX) else "candidate"
                mhz = {p: looks[p].hits[i]["frequency_mhz"] for p, i in members.items()}
                out.append({"members": members, "track": track, "offs": offs, "label": label, "a": round(a, 7),
                            "sig": frozenset(members.items()), "off_measured": measured, "off_looks": len(off),
                            "mhz": mhz, "pair": (la.position, lb.position)})
    return out


def first_wins(hyps):
    """second_pass's output from second_pass_all's: the first hypothesis for each set of hits."""
    seen, out = set(), []
    for h in hyps:
        if h["sig"] in seen:
            continue
        seen.add(h["sig"])
        out.append({k: h[k] for k in ("members", "track", "offs", "label", "a")})
    return out


def any_candidate(hyps):
    """For each set of hits, its first candidate hypothesis if any is one, else its first."""
    by = {}
    for h in hyps:
        cur = by.get(h["sig"])
        if cur is None or (cur["label"] != "candidate" and h["label"] == "candidate"):
            by[h["sig"]] = h
    return [{k: h[k] for k in ("members", "track", "offs", "label", "a")} for h in by.values()]


def measured_only(hyps):
    """first_wins, a candidate with no OFF look measured made 'unmeasured' (not kept)."""
    out = []
    seen = set()
    for h in hyps:
        if h["sig"] in seen:
            continue
        seen.add(h["sig"])
        e = {k: h[k] for k in ("members", "track", "offs", "label", "a")}
        if e["label"] == "candidate" and h["off_measured"] == 0:
            e["label"] = "unmeasured"
        out.append(e)
    return out


def order_stats(hyps):
    by = {}
    for h in hyps:
        by.setdefault(h["sig"], []).append(h)
    conflicting = [v for v in by.values() if len({x["label"] for x in v}) > 1]
    first = [v[0] for v in by.values()]
    return {"hypotheses": len(hyps), "sets_of_hits": len(by),
            "sets_with_more_than_one_fit": sum(len(v) > 1 for v in by.values()),
            "sets_disagreeing": len(conflicting),
            "first_is_interference_another_candidate": sum(v[0]["label"] != "candidate" for v in conflicting),
            "candidates_first": sum(h["label"] == "candidate" for h in first),
            "candidates_no_off_measured": sum(h["label"] == "candidate" and h["off_measured"] == 0 for h in first),
            "candidates_some_off_unmeasured": sum(h["label"] == "candidate" and 0 < h["off_measured"] < h["off_looks"]
                                                  for h in first)}


WAYS = {"as published": first_wins, "any hypothesis a candidate": any_candidate,
        "unmeasured OFF not clean": measured_only}


def _judge(cad, searched, ons, caches):
    looks, events, order = matched.our_events(cad, searched, ons, CUT, caches)
    prod = matched._our_kept(looks, events, order)
    hyps = second_pass_all(looks, events, A_MAX)
    kept = {name: prod + curved_pass._kept_pass(looks, fn(hyps), order) for name, fn in WAYS.items()}
    for lk in looks:
        lk.flat = None
    return kept, hyps


def _picks():
    import turbo_checks
    return sorted(set(TRACED) | set(int(b) for b in turbo_checks._picks(TARGET)[4]))


def blocks(say=_say):
    db = store.connect_readonly()
    session, urls = store.cadence_files(db, TARGET)
    db.close()
    chosen = {int(b): c for b, c in json.loads((matched.folder(TARGET, session) / "blocks.json")
                                               .read_text(encoding="utf-8"))["chosen"].items()}
    block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
    rows = []
    for b in _picks():
        fp = fingerprint(json.dumps([urls, list(block_list[b])], default=str))
        path = OUT / "curved_checks" / f"block_{b:03d}.json"
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if old.get("code") == fp:
                rows.append(old)
                continue
        cad = matched._cadence(seti.read_looks(urls, *block_list[b]), urls)
        recorded = json.loads((curved_pass.folder(TARGET, session) / f"block_{b:03d}.json").read_text(encoding="utf-8"))
        if [c["s"]["tstart"] for c in cad] != recorded["tstarts"]:
            raise yoke.Refusal("INVALID_REQUEST", f"block {b}: the looks read again start at other times than the record's")
        searched = matched.our_search(cad)
        caches = [{} for _ in range(6)]
        false = {w: {} for w in WAYS}
        order = {}
        true_plain = None
        for ons in itertools.combinations(range(6), 3):
            kept, hyps = _judge(cad, searched, ons, caches)
            if ons == matched.TRUE:
                true_plain = kept
            else:
                for w in WAYS:
                    false[w][str(ons)] = kept[w]
            for k, v in order_stats(hyps).items():
                order[k] = order.get(k, 0) + v
        ts = curved_pass.tones(cad, np.random.default_rng([curved_pass.SEED, b]))
        cad_p = [dict(c, spectra=p) for c, p in zip(cad, curved_pass.plant(cad, ts))]
        searched_p = matched.our_search(cad_p)
        kept_p, hyps_p = _judge(cad_p, searched_p, matched.TRUE, [{} for _ in range(6)])
        found = {w: sum(curved_pass.statuses(cad, t, kept_p[w], true_plain[w])["three_looks"] == "recovered"
                        for t in ts) for w in WAYS}
        row = {"block": b, "class": chosen[b], "code": fp,
               "false_30": {w: len(matched.shared_hits(false[w])) for w in WAYS}, "found_30": found,
               "order_wrong_choices": order, "order_planted": order_stats(hyps_p)}
        if b in TRACED:
            t = ts[TRACED[b]]
            st = {w: curved_pass.statuses(cad, t, kept_p[w], true_plain[w]) for w in WAYS}
            near = [{"pair": list(h["pair"]), "members": {str(p): i for p, i in h["members"].items()}, "a": h["a"],
                     "label": h["label"], "track": h["track"], "off_measured": h["off_measured"]}
                    for h in hyps_p if _near(cad, t, h)]
            row["traced"] = {"signal": TRACED[b], "s_in": t["s_in"], "drift": t["drift"], "accel": t["accel"],
                             "statuses": st, "hypotheses_near": near}
        path.parent.mkdir(parents=True, exist_ok=True)
        yoke.write(path, row, indent=1)
        rows.append(row)
        say(f"block {b} ({row['class']}): false {row['false_30']}; found {row['found_30']}; order {order}"
            + (f"; traced {row['traced']['statuses']['as published']}" if "traced" in row else ""))
    total = {k: {w: sum(r[k][w] for r in rows) for w in WAYS} for k in ("false_30", "found_30")}
    out = {"target": TARGET, "cut": CUT, "a_max": A_MAX, "blocks": [r["block"] for r in rows], "rows": rows,
           "totals": total, "code": fingerprint(), "kind": "measured"}
    yoke.write(OUT / "curved_checks.json", out, indent=1, stamp=True)
    say(f"totals: {total}")
    return out


def _near(cad, t, h, hz=50.0):
    """A hypothesis with a member hit within `hz` of the signal's expected start in that look
    (positions are the ON looks in order: matched.TRUE)."""
    ons = list(matched.TRUE)
    for p, f in h["mhz"].items():
        if p % 2 == 0 and abs(curved_pass.expected(cad, t, ons[p // 2])[0] - f) * 1e6 < hz:
            return True
    return False


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "blocks"
    {"blocks": blocks}[what]()


if __name__ == "__main__":
    main()
