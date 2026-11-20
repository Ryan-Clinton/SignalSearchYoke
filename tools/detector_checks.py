"""Checks of the core detector, searching.py (docs/audits.md 9). The
production search is not changed: the checks run its own code
(searching.search, searching.Plane) or the diagnostic copy
(tools/search_variants.py, identical at its defaults), and write
supplementary records only.

    python tools/detector_checks.py synthetic   refresh reach, noise spread, non-finite input (minutes)
    python tools/detector_checks.py blocks      the same on blocks read again, with candidates (hours)

- **refresh** (F9-01): after a pick, searching.search sums again the line
  starts within its margin (most + widest box) of the blanked track; a
  blanked pixel in the last spectrum lies on lines of the opposite extreme
  drift starting up to 2 x most away, whose scores keep power already
  blanked. Hits with the margin (as published) against hits with the full
  reach (search_variants refresh_reach="full").
- **noise** (F9-05): each box width's noise is the MAD of 1,024 adjacent
  summed lines; at wide boxes neighbouring sums share most of their
  channels. The spread of that estimate over blocks of pure Gaussian noise.
- **direction** (F9-02): each width's noise is measured on a positive drift
  and used for both signs. The same measured on the negative drift
  (searching.Plane with its sample drift negated), block by block.
- **nonfinite** (F9-04): one NaN in a look: what searching.search returns.
- **rounding** (F9-06): hits whose SNR is under a cut but rounds to it
  (matched.py compares the rounded value).
- **blocks**: eight 2017 blocks (seed 12, clean and crowded, as
  turbo_checks) and four crowded 2016 blocks (as completeness_checks
  shadow), plain and planted: hits, false candidates (19 wrong choices) and
  planted signals found at 30, with the margin and with the full reach; the
  rounding flips at every cut; the noise each way; non-finite samples.
"""
import hashlib
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import matched  # noqa: E402
import matched_tables  # noqa: E402
import searching  # noqa: E402
import seti  # noqa: E402
import store  # noqa: E402
import yoke  # noqa: E402
import onoff_checks  # noqa: E402
import search_variants as sv  # noqa: E402

OUT = yoke.DATA / "analysis"
TSAMP = 18.253611008      # the GBT high-resolution product's
FOFF = -2.7939677238464355e-06
FCH1 = 2000.0
CUTS = matched.CUTS_OURS


def _say(*a):
    print(*a, flush=True)


DEPENDS = ("searching.py", "tools/search_variants.py", "tools/detector_checks.py", "tools/onoff_checks.py",
           "matched.py", "onoff.py", "seti.py",
           "measure.py", "matched_tables.py", "injection.py", "store.py", "tools/turbo_checks.py")


def fingerprint(source=""):
    """The code the results rest on, and (`source`) what was read."""
    h = hashlib.sha256()
    for f in DEPENDS:
        h.update((ROOT / f).read_bytes().replace(b"\r\n", b"\n"))
    h.update(source.encode())
    return h.hexdigest()[:16]


class NegPlane(searching.Plane):
    """searching.Plane measuring each width's noise on the negative drift of the one it uses."""

    def _sample(self, group):
        k = super()._sample(group)
        return -k if k else 0


def _noise(n_t, n_f, rng):
    return rng.normal(100.0, 1.0, (n_t, n_f)).astype(np.float32)


def _tone(x, n_t, f0, drift_hz_s, amp, only=None):
    """A tone into spectra x at channel f0, drifting; `only`: the spectra it is in."""
    per = abs(FOFF) * 1e6
    for t in range(n_t):
        if only is not None and t not in only:
            continue
        c = f0 + drift_hz_s * t * TSAMP / per * (1 if FOFF > 0 else -1)
        i = int(math.floor(c))
        fr = c - i
        x[t, i] += amp * (1 - fr)
        x[t, i + 1] += amp * fr
    return x


def _keys(hits):
    return {(h["channel"], round(h["drift_hz_s"], 4)) for h in hits}


def refresh_cases(rng, n_t=16, n_f=16384, max_drift=searching.MAX_DRIFT):
    cases = {
        "strong tone, +2 Hz/s": lambda x: _tone(x, n_t, 8000, 2.0, 400.0),
        "strong tone, -3.9 Hz/s": lambda x: _tone(x, n_t, 8000, -3.9, 400.0),
        "a pulse in the last spectrum": lambda x: _tone(x, n_t, 8000, 0.0, 4000.0, only=[n_t - 1]),
        "a pulse in the first spectrum": lambda x: _tone(x, n_t, 8000, 0.0, 4000.0, only=[0]),
        "a wide strong tone": lambda x: [_tone(x, n_t, 8000 + d, 0.5, 300.0) for d in range(6)][-1],
    }
    out = {}
    for name, put in cases.items():
        x = put(_noise(n_t, n_f, rng))
        a = sv.search_variant(x, FOFF, TSAMP, FCH1, max_drift=max_drift, exact=True)
        b = sv.search_variant(x, FOFF, TSAMP, FCH1, max_drift=max_drift, exact=True, refresh_reach="full")
        ka, kb = _keys(a), _keys(b)
        only_a = [h for h in a if (h["channel"], round(h["drift_hz_s"], 4)) not in kb]
        out[name] = {"hits_as_published": len(a), "hits_full_reach": len(b),
                     "at_10_as_published": sum(h["snr"] >= 10 for h in a),
                     "at_10_full_reach": sum(h["snr"] >= 10 for h in b),
                     "only_as_published": len(only_a), "only_full_reach": len(kb - ka),
                     "only_as_published_snr": sorted((round(h["snr_exact"], 2) for h in only_a), reverse=True)[:10]}
    return out


def noise_spread(rng, n_t=16, n_f=131072, reps=4):
    """searching.Plane's measured spread over its expected value (sqrt(spectra x width)) on Gaussian
    noise, block by block, for each box width."""
    by = {}
    for _ in range(reps):
        flat = rng.normal(0.0, 1.0, (n_t, n_f)).astype(np.float32)
        plane = searching.Plane(flat, TSAMP, FOFF, searching.MAX_DRIFT, searching.METHOD, None)
        plane.search()
        nb = n_f // searching.BLOCK
        for (w, zero), (_, spread) in plane.norm.items():
            if zero:
                continue
            by.setdefault(w, []).extend((spread[:nb] / math.sqrt(n_t * w)).tolist())
    out = {}
    for w in sorted(by):
        r = np.array(by[w])
        out[str(w)] = {"blocks": len(r), "mean": round(float(r.mean()), 3), "sd": round(float(r.std()), 3),
                       "p5": round(float(np.percentile(r, 5)), 3), "p95": round(float(np.percentile(r, 95)), 3)}
    return out


def direction(flat, flags=None):
    """Each width's spread measured on the positive drift (as searched) and on the negative one: per
    width, the median and the 95th percentile over blocks of |log(negative / positive)|, and the
    largest ratio either way."""
    pos = searching.Plane(flat, TSAMP, FOFF, searching.MAX_DRIFT, searching.METHOD, flags)
    pos.search()
    neg = NegPlane(flat, TSAMP, FOFF, searching.MAX_DRIFT, searching.METHOD, flags)
    neg.search()
    nb = -(-flat.shape[1] // searching.BLOCK)
    out = {}
    for g in sorted(pos.norm):
        if g[1]:
            continue
        r = np.log(neg.norm[g][1][:nb].astype(float) / pos.norm[g][1][:nb].astype(float))
        r = np.abs(r[np.isfinite(r)])
        if len(r):
            out[str(g[0])] = {"median_abs_log": round(float(np.median(r)), 4),
                              "p95_abs_log": round(float(np.percentile(r, 95)), 4),
                              "max_ratio": round(float(np.exp(r.max())), 3)}
    return out


def nonfinite(rng, n_t=16, n_f=16384):
    x = _tone(_noise(n_t, n_f, rng), n_t, 12000, 0.3, 200.0)
    clean = searching.search(x.copy(), FOFF, TSAMP, FCH1)
    y = x.copy()
    y[5, 3000] = np.nan
    try:
        bad = searching.search(y, FOFF, TSAMP, FCH1)
        return {"hits_clean": len(clean), "hits_with_one_nan": len(bad), "raised": None,
                "tone_found_clean": any(abs(h["channel"] - 12000) < 20 for h in clean),
                "tone_found_with_one_nan": any(abs(h["channel"] - 12000) < 20 for h in bad)}
    except Exception as e:      # noqa: BLE001 (what it does is the finding)
        return {"hits_clean": len(clean), "raised": f"{type(e).__name__}: {e}"[:200]}


def rounding_flips(hits, cuts=CUTS):
    """Per cut: hits under it whose rounded SNR is at or over it."""
    return {matched.ck(c): sum(h["snr_exact"] < c <= h["snr"] for h in hits) for c in cuts}


def synthetic(say=_say):
    rng = np.random.default_rng(9)
    rec = {"code": fingerprint(), "kind": "measured", "tsamp": TSAMP, "foff_mhz": FOFF}
    rec["refresh"] = refresh_cases(rng)
    for k, v in rec["refresh"].items():
        say(f"refresh, {k}: {v}")
    rec["noise_spread"] = noise_spread(rng)
    for w, v in rec["noise_spread"].items():
        say(f"noise, width {w}: {v}")
    flat = rng.normal(0.0, 1.0, (16, 65536)).astype(np.float32)
    flat[:, 32768:] *= 2.0                                  # a step in the noise
    rec["direction_step"] = direction(flat)
    say(f"direction, a step in the noise: {rec['direction_step']}")
    rec["direction_gaussian"] = direction(rng.normal(0.0, 1.0, (16, 65536)).astype(np.float32))
    rec["nonfinite"] = nonfinite(rng)
    say(f"non-finite: {rec['nonfinite']}")
    yoke.write(OUT / "detector_checks_synthetic.json", rec, indent=1, stamp=True)
    return rec


# --- blocks read again -----------------------------------------------------------------

def _picks():
    import turbo_checks
    out = [("KIC8462852", b) for b in turbo_checks._picks("KIC8462852")[4]]
    _, _, recs = matched_tables.load("HIP17147")
    crowded = sorted(int(r["block"]) for r in recs if r["class"] == "crowded")
    out += [("HIP17147", int(b)) for b in sorted(np.random.default_rng(12).choice(crowded, 4, replace=False))]
    return out


def _searched(cad, **kw):
    """The six looks through the diagnostic copy (kw: its switches, or snr_min for a search at another cut)."""
    from concurrent.futures import ThreadPoolExecutor

    def one(j):
        s, raw = cad[j]["s"], cad[j]["spectra"]
        d = {}
        hits = seti.describe(sv.search_variant(raw, s["foff"], s["tsamp"], s["fch1"], details=d, exact=True, **kw),
                             dict(s, spectra=raw))
        return hits, d["flat"], bool(d["complete"])
    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(one, range(6)))


def _judged(cad, cad_p, su, sp, ts, cut=30, blind=None):
    """(false candidates over the 19 wrong choices, planted signals found); `blind`, a dict, gets the
    candidates with OFF looks left unmeasured (onoff_checks.unmeasured), wrong choices and planted."""
    caches = [{} for _ in range(6)]
    by = {}
    tally = {}
    for ons in itertools.combinations(range(6), 3):
        if ons == matched.TRUE:
            continue
        looks, events, order = matched.our_events(cad, su, ons, cut, caches)
        by[str(ons)] = matched._our_kept(looks, events, order)
        for k, v in onoff_checks.unmeasured(events).items():
            tally[k] = tally.get(k, 0) + v
    looks, events, order = matched.our_events(cad_p, sp, matched.TRUE, cut, [{} for _ in range(6)])
    kp = matched._our_kept(looks, events, order)
    if blind is not None:
        blind.update(wrong_choices=tally, planted=onoff_checks.unmeasured(events))
    looks, events, order = matched.our_events(cad, su, matched.TRUE, cut, [{} for _ in range(6)])
    ku = matched._our_kept(looks, events, order)
    found = sum(matched._status({j: matched.where(cad, t, j)[1] for j in matched.TRUE}, t["drift"], kp, ku)
                ["three_looks"] == "recovered" for t in ts)
    return len(matched.shared_hits(by)), found


def blocks(say=_say):
    rows = []
    for target, b in _picks():
        session, _, _ = matched_tables.load(target)
        db = store.connect_readonly()
        _, urls = store.cadence_files(db, target)
        db.close()
        block_list = seti.blocks(seti.reading.prepare(urls[:1])[0])
        fp = fingerprint(json.dumps([urls, list(block_list[b])], default=str))
        path = OUT / "detector_checks" / f"{target}_block_{b:03d}.json"
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if old.get("code") == fp:
                rows.append(old)
                continue
        rec = json.loads((matched.folder(target, session) / f"block_{b:03d}.json").read_text(encoding="utf-8"))
        cad = matched._cadence(seti.read_looks(urls, *block_list[b]), urls)
        if [c["s"]["tstart"] for c in cad] != rec["tstarts"]:
            raise yoke.Refusal("INVALID_REQUEST", f"{target} block {b}: the looks read again start at other times "
                                                  "than the record's")
        ts = rec["tones"]
        cad_p = [dict(c, spectra=p["spectra"]) for c, p in zip(cad, matched.plant(cad, ts))]
        row = {"target": target, "block": b, "class": rec["class"], "code": fp,
               "nonfinite_samples": [int((~np.isfinite(c["spectra"])).sum()) for c in cad]}
        keys = {}
        for name, kw in (("as published", {}), ("full reach", {"refresh_reach": "full"})):
            su, sp = _searched(cad, **kw), _searched(cad_p, **kw)
            blind = {} if name == "as published" else None
            false30, found30 = _judged(cad, cad_p, su, sp, ts, blind=blind)
            if blind is not None:
                row["unmeasured_off"] = blind
                looks, _, _ = matched.our_events(cad, su, matched.TRUE, 30, [{} for _ in range(6)])
                row["null_on"] = onoff_checks.null_on(looks)
                row["asymmetry"] = onoff_checks.asymmetry(looks)
            row[name] = {"hits": [len(x[0]) for x in su], "complete": [x[2] for x in su],
                         "false_30": false30, "found_30": found30}
            keys[name] = [_keys(x[0]) for x in su]
            if name == "as published":
                row["rounding_flips"] = {c: sum(rounding_flips(x[0])[c] for x in su) for c in map(matched.ck, CUTS)}
                # each look's noise both ways, with the kurtosis flags the search uses
                row["direction"] = [direction(su[j][1], searching.kurtosis(cad[j]["spectra"]) > searching.SK_FLAG)
                                    for j in range(6)]
                single = (su, sp)
        row["hits_differing"] = [len(keys["as published"][j] ^ keys["full reach"][j]) for j in range(6)]
        # F9-03: the search run at each cut against the one search at 10 relabelled (the same at 10 by construction)
        row["per_cut"] = {}
        for c in (8, 30):
            su_c, sp_c = _searched(cad, snr_min=float(c)), _searched(cad_p, snr_min=float(c))
            f1, n1 = _judged(cad, cad_p, single[0], single[1], ts, cut=c)
            f2, n2 = _judged(cad, cad_p, su_c, sp_c, ts, cut=c)
            row["per_cut"][str(c)] = {
                "one search": {"false": f1, "found": n1}, "searched at this cut": {"false": f2, "found": n2},
                "hits_differing": [len(_keys(single[0][j][0]) ^ _keys(su_c[j][0])) for j in range(6)]}
        path.parent.mkdir(parents=True, exist_ok=True)
        yoke.write(path, row, indent=1)
        rows.append(row)
        a, z = row["as published"], row["full reach"]
        say(f"{target} block {b} ({row['class']}): as published {a['false_30']} false, {a['found_30']} found; full "
            f"reach {z['false_30']} false, {z['found_30']} found; hits differing {row['hits_differing']}; "
            f"rounding flips {row['rounding_flips']}; non-finite {row['nonfinite_samples']}")
    out = {"rows": rows, "code": fingerprint(), "kind": "measured"}
    yoke.write(OUT / "detector_checks_blocks.json", out, indent=1, stamp=True)
    return out


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "synthetic"
    {"synthetic": synthetic, "blocks": blocks}[what]()


if __name__ == "__main__":
    main()
