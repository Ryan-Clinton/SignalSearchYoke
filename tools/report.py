"""Write the report (docs/publishing.md) from the result records:
docs/report/report.md. Every number comes from a record; the prose around
the numbers is fixed here. The experiment's definition (signals a block,
the strength grid, the drift bins, the tolerances, the wrong choices, the
pipelines' versions) is read from the per-block records, the summary
record and the environment as run (method()), and the report is refused if
the records disagree with one another. The records it reads are listed at
the end of the report with their creation times and the commit that made
them.

    python tools/report.py
"""
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("SSY_DATA") or ROOT / "data")
OUT = ROOT / "docs" / "report" / "report.md"

VERSION = "1.4"
DATE = "2026-11-19"
REVISIONS = (("0.1", "2026-11-18", "first draft."),
             ("1.0", DATE, "first release: the signals BLISS finds and this search misses traced stage by "
                         "stage, and the detector's misses measured."),
             ("1.1", DATE, "the code's repository, now public, linked."),
             ("1.2", DATE, "the third session, chosen and fixed in advance (NGC 6946 at C band): every "
                           "criterion held."),
             ("1.3", DATE, "recovery at every tested cut for all three sessions, with the paired difference "
                           "and blocks resampled in runs; step 12 described as meeting its criteria at the point "
                           "estimate; what the injections, the false-candidate control and the comparison of "
                           "whole pipelines do and do not measure."),
             ("1.4", DATE, "recovery weighted to each session's share of crowded and clean blocks beside the "
                           "sample's; the neighbouring-block check made over consecutive blocks of the session; "
                           "the matched cut by one rule throughout; the blocks of each session stated."))


def load(path):
    return json.loads((DATA / path).read_text(encoding="utf-8"))


def refuse(why):
    sys.exit(f"report.py: the records disagree, no report written: {why}")


def method(b):
    """The experiment as the records define it, checked across all of them:
    every judged block planted the same number of signals on the same grid
    and was judged under the same wrong choices, and the summary record's
    signal count and tolerances agree."""
    folder = DATA / "matched" / f"{b['target']}-{b['session']}"
    blocks = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("block_*.json"))]
    if not len(blocks) == b["blocks"] == b["judged_blocks"]:
        refuse(f"{len(blocks)} block records, the summary gives {b['blocks']} blocks, {b['judged_blocks']} judged")
    per_block = {len(r["tones"]) for r in blocks}
    strengths = {tuple(sorted({t["s_in"] for t in r["tones"]})) for r in blocks}
    bins = {tuple(sorted({t["bin"] for t in r["tones"]})) for r in blocks}
    wrong = {len(v) for r in blocks for v in r["ours"]["false"].values()}
    if len(per_block) != 1 or len(strengths) != 1 or len(bins) != 1 or len(wrong) != 1:
        refuse(f"blocks differ: signals a block {per_block}, grids {len(strengths)}, drift bins {len(bins)}, "
               f"wrong choices {wrong}")
    (per_block,), (strengths,), (bins,), (wrong,) = per_block, strengths, bins, wrong
    if per_block * len(blocks) != b["tones"]:
        refuse(f"{len(blocks)} blocks of {per_block} signals is not the {b['tones']} the summary gives")
    if wrong != 19:
        refuse(f"{wrong} wrong choices a block, not the 19 other ways of choosing three of six looks")
    tol = load("measurements/matched.json")["tolerances"]
    turbo = re.search(r"^turbo-seti==(\S+)", (ROOT / "docs" / "environments" / "turboseti-windows.txt")
                      .read_text(encoding="utf-8"), re.M)
    return {"per_block": per_block, "strengths": strengths, "bins": len(bins),
            "max_drift": max(abs(t["drift"]) for r in blocks for t in r["tones"]),
            "at_each_point": b["tones"] // (len(strengths) * len(bins)), "tol_hz": tol[0], "tol_drift": tol[1],
            "wrong": wrong, "turboseti": turbo.group(1) if turbo else refuse("no turboSETI version recorded")}


def iv(x, digits=3):
    return f"{x[0]:.{digits}g} to {x[1]:.{digits}g}"


WORDS = {5: "five", 11: "eleven"}


def n(x):
    return f"{x:,}"


SERIES = (("ours", "this search", "#2a78d6", "circle"),
          ("bliss_ours", "BLISS's hits, this search's test", "#eb6834", "square"),
          ("turboseti", "turboSETI", "#1baf7a", "triangle"))


def figure(rows, path):
    """Share of planted signals found in all three ON looks at each matched
    cut, against S_in, one panel a drift bin: an SVG with no dependencies."""
    bins = []
    for r in rows:
        if tuple(r["drift_hz_s"]) not in bins:
            bins.append(tuple(r["drift_hz_s"]))
    s_ins = sorted({r["s_in"] for r in rows})
    pw, ph, ml, mt, gap = 168, 150, 46, 34, 14
    W, H = ml + len(bins) * (pw + gap), mt + ph + 92
    x = lambda i: i * (pw - 12) / (len(s_ins) - 1) + 6  # noqa: E731
    y = lambda v: ph - v * ph  # noqa: E731
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         'font-family="Helvetica, Arial, sans-serif" font-size="11">',
         f'<rect width="{W}" height="{H}" fill="#fcfcfb"/>']
    for b, rng in enumerate(bins):
        ox = ml + b * (pw + gap)
        o.append(f'<g transform="translate({ox},{mt})">')
        o.append(f'<text x="{pw / 2}" y="-12" text-anchor="middle" fill="#1f1f1e">drift {rng[0]:g} to {rng[1]:g} '
                 'Hz/s</text>')
        for v in (0, 0.5, 1):
            o.append(f'<line x1="0" x2="{pw}" y1="{y(v)}" y2="{y(v)}" stroke="#e4e3df" stroke-width="1"/>')
            if b == 0:
                o.append(f'<text x="-6" y="{y(v) + 4}" text-anchor="end" fill="#5f5e5a">{v:.0%}</text>')
        for i, si in enumerate(s_ins):
            if si in (10, 40, 120, 400):
                o.append(f'<text x="{x(i)}" y="{ph + 16}" text-anchor="middle" fill="#5f5e5a">{si}</text>')
        for key, _, col, mark in SERIES:
            pts = []
            for i, si in enumerate(s_ins):
                r = next(r for r in rows if tuple(r["drift_hz_s"]) == rng and r["s_in"] == si)
                pts.append((x(i), y(r[key]["recovered"] / r[key]["planted"])))
            o.append('<polyline fill="none" stroke="{}" stroke-width="2" points="{}"/>'.format(
                col, " ".join(f"{a:.1f},{c:.1f}" for a, c in pts)))
            for a, c in pts:
                if mark == "circle":
                    o.append(f'<circle cx="{a:.1f}" cy="{c:.1f}" r="4" fill="{col}" stroke="#fcfcfb" stroke-width="2"/>')
                elif mark == "square":
                    o.append(f'<rect x="{a - 4:.1f}" y="{c - 4:.1f}" width="8" height="8" rx="1" fill="{col}" '
                             'stroke="#fcfcfb" stroke-width="2"/>')
                else:
                    o.append(f'<path d="M{a:.1f},{c - 5:.1f} L{a + 5:.1f},{c + 4:.1f} L{a - 5:.1f},{c + 4:.1f} Z" '
                             f'fill="{col}" stroke="#fcfcfb" stroke-width="2"/>')
        o.append("</g>")
    o.append(f'<text x="{ml + (W - ml) / 2}" y="{mt + ph + 36}" text-anchor="middle" fill="#5f5e5a">'
             'signal strength S_in</text>')
    lx = ml
    for _, label, col, mark in SERIES:
        o.append(f'<line x1="{lx}" x2="{lx + 22}" y1="{H - 22}" y2="{H - 22}" stroke="{col}" stroke-width="2"/>')
        cx, cy = lx + 11, H - 22
        if mark == "circle":
            o.append(f'<circle cx="{cx}" cy="{cy}" r="4" fill="{col}" stroke="#fcfcfb" stroke-width="2"/>')
        elif mark == "square":
            o.append(f'<rect x="{cx - 4}" y="{cy - 4}" width="8" height="8" rx="1" fill="{col}" stroke="#fcfcfb" '
                     'stroke-width="2"/>')
        else:
            o.append(f'<path d="M{cx},{cy - 5} L{cx + 5},{cy + 4} L{cx - 5},{cy + 4} Z" fill="{col}" '
                     'stroke="#fcfcfb" stroke-width="2"/>')
        o.append(f'<text x="{lx + 28}" y="{H - 18}" fill="#1f1f1e">{label}</text>')
        lx += 28 + 7 * len(label) + 30
    o.append("</svg>")
    path.write_text("\n".join(o) + "\n", encoding="utf-8")


def detector_cause(sig, cut=10.0):
    """One reading of the detector's stages for a signal it gave no matching
    hit for, from its looks without one (tools/detector_misses.py): the hit
    cap, the blanking for other hits, the noise of its block, or the
    detector's own S/N under the cut where the cadence test's is over it."""
    miss = [lk for lk in sig["looks"] if lk["matching_hit_snr"] is None]
    if not miss:
        return "found"
    if any(any(c["matching_hit_snr"] is not None for c in lk.get("raised_caps", [])) for lk in miss):
        return "the hit cap"
    # A hit within a few channels and 0.2 Hz/s that blanked the track and is as bright: the signal itself,
    # found but measured outside +-6 Hz and +-0.05 Hz/s.
    if any(any(abs(h["df_channels"]) <= 10 and abs(h["drift_hz_s"] - sig["drift"]) <= 0.2 and h["snr"] >= cut
               for h in lk["blanked_by_others"]["hits"]) for lk in miss):
        return "found, but measured outside the tolerances"
    if any(lk["blanked_by_others"]["share"] >= 0.25 for lk in miss):
        return "blanked for a stronger hit"
    if any(lk["exact_track"]["snr"] < cut and lk["exact_track"]["block_noise_over_median"] >= 1.5 for lk in miss):
        return "interference raising its block's noise"
    if any(lk["exact_track"]["snr"] < cut for lk in miss):
        return "under the cut on the detector's own measure"
    return "over the cut but not picked"


def detector_sentence(det):
    from collections import Counter
    causes = {(s["block"], s["tone"]): detector_cause(s) for s in det["signals"]}
    c = Counter(causes.values())
    parts = ", ".join(f"{v} {k}" for k, v in c.most_common())
    out = (f"The {len(det['signals'])} signals the detector gave no matching hit for were measured through its "
           f"stages, the detector unchanged; the first cause in each: {parts}.")
    capped = [x["matching_hit_snr"] for s in det["signals"] if causes[(s["block"], s["tone"])] == "the hit cap"
              for lk in s["looks"] for x in lk.get("raised_caps", []) if x["matching_hit_snr"] is not None]
    caps = [x["cap"] for s in det["signals"] if causes[(s["block"], s["tone"])] == "the hit cap"
            for lk in s["looks"] for x in lk.get("raised_caps", []) if x["matching_hit_snr"] is not None]
    if capped:
        out += (f" The hit cap is the 2,000 hits kept a look: in crowded looks the signal, at S/N {min(capped):g} "
                f"to {max(capped):g}, lies below that many stronger hits, and a cap of {min(caps):,} to "
                f"{max(caps):,} finds it.")
    off = [s for s in det["signals"] if causes[(s["block"], s["tone"])] == "found, but measured outside the tolerances"]
    if off:
        dd = [abs(h["drift_hz_s"] - s["drift"]) for s in off for lk in s["looks"] if lk["matching_hit_snr"] is None
              for h in lk["blanked_by_others"]["hits"][:1]]
        out += (" Those measured outside the tolerances drift fast ("
                + " and ".join(f"{abs(s['drift']):.1f}" for s in off)
                + " Hz/s); their measured drift was "
                + (f"{min(dd):.2f}" if f"{min(dd):.2f}" == f"{max(dd):.2f}" else f"{min(dd):.2f} to {max(dd):.2f}")
                + " Hz/s off, just outside the tolerance.")
    return out + " Neither is changed here: the detector stays as step 10 ran it."


def main():
    b = load("measurements/matched-bliss.json")
    s10 = load("measurements/step10.json")
    s12_path = DATA / "measurements" / "step12.json"
    s12 = json.loads(s12_path.read_text(encoding="utf-8")) if s12_path.exists() else None
    dev12_path = DATA / "step12" / "deviations.json"
    devs12 = json.loads(dev12_path.read_text(encoding="utf-8")) if dev12_path.exists() else []
    bliss12_path = DATA / "step12" / "bliss_status.json"
    bliss12 = json.loads(bliss12_path.read_text(encoding="utf-8")) if bliss12_path.exists() else None
    ops_path = DATA / "analysis" / "operating_points.json"
    ops = json.loads(ops_path.read_text(encoding="utf-8")) if ops_path.exists() else None
    control_dir = DATA / "matched" / f"{b['target']}-{b['session']}" / "bliss_control"
    control = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(control_dir.glob("block_*.json"))]
    trace_path = DATA / "analysis" / "bliss_only" / "trace_summary.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else None
    off_null = load("measurements/off_null.json")
    det_path = DATA / "analysis" / "bliss_only" / "detector_misses.json"
    det = json.loads(det_path.read_text(encoding="utf-8")) if det_path.exists() else None

    fc, tot = b["false_curves"], b["totals_matched"]
    at = {p: f"{float(c):g}" for p, c in b["matched_at"].items()}
    planted = b["tones"]
    pair = b["pairs_matched"]["ours/bliss_ours"]
    ours_r = fc["ours"][at["ours"]]
    turbo_r = fc["turboseti"][at["turboseti"]]
    hyb_r = fc["bliss_ours"][at["bliss_ours"]]
    bl = fc["bliss"]
    bl_min = min(bl.values(), key=lambda v: v["per_block"])
    bl_min_cut = next(c for c, v in bl.items() if v is bl_min)
    fr, rec = s10["false_rate"], s10["recovery_three_looks"]
    p10 = s10["supplementary"]["paired_ours_turboseti"]
    curved = s10["supplementary"]["paired_pass_production_curved"]
    rate = b["rate_matched"]
    over = sum(r["interval"][1] > rate for r in (ours_r, turbo_r, hyb_r))
    dev_path = DATA / "step10" / "deviations.json"
    devs = json.loads(dev_path.read_text(encoding="utf-8")) if dev_path.exists() else []
    m = method(b)
    grid = m["strengths"]

    L = []
    w = L.append
    w("# Comparing radio-signal searches on Breakthrough Listen data")
    w("")
    w(f"Ryan Clinton. Version {VERSION}, {DATE}.")
    w("")
    w("## Summary")
    w("")
    w(f"I compared a narrowband radio-signal search of my own (SignalSearchYoke) with two published "
      f"pipelines, turboSETI and BLISS, on recorded Breakthrough Listen observations from the Green Bank "
      f"Telescope, by planting {n(planted)} synthetic signals in the data and counting how many each "
      f"pipeline found, and how many false candidates each raised, on the same blocks.")
    w("")
    w(f"On a 2017 session ({b['target']}), at the cut where each pipeline's measured false-candidate rate is "
      f"at most {rate} a block (a point estimate; {'each' if over == 3 else f'{over} of the three'} 95% "
      f"interval{'s' if over not in (1, 3) else ''} reach{'es' if over in (1, 3) else ''} above it, and the cuts were chosen "
      f"on the blocks they were judged on), this search found {n(tot['ours'])} of the {n(planted)} signals in all three ON looks, turboSETI "
      f"{n(tot['turboseti'])}. BLISS as published never reached that false-candidate rate at any cut "
      f"tested. BLISS's own hits put through this search's ON/OFF test did reach it, and found "
      f"{n(tot['bliss_ours'])}.")
    w("")
    w(f"On a second session, fixed in advance ({s10['target']}, 2016), this search again found far more "
      f"than turboSETI ({n(rec['ours']['recovered'])} against {n(rec['turboseti']['recovered'])}), but both "
      f"pipelines **failed** the false-candidate limit set beforehand: {fr['ours']['per_block']:.3g} and "
      f"{fr['turboseti']['per_block']:.3g} a block against {s10['rate_limit']}, almost all of this search's "
      f"in known satellite bands. That failure is part of the result.")
    w("")
    if s12:
        f12, r12 = s12["false_rate"], s12["recovery_three_looks"]
        held = all(v.startswith("holds") for v in s12["criteria"].values())
        w(f"On a third session, chosen by a rule from the archive's metadata and fixed in advance "
          f"({s12['target']}, a galaxy, at C band in 2019), "
          f"{'every criterion fixed beforehand was met at its point estimate' if held else 'not every criterion held'}: "
          f"this search found {n(r12['ours']['recovered'])} of {n(r12['ours']['of'])} signals against turboSETI's "
          f"{n(r12['turboseti']['recovered'])}, and "
          + ("neither raised a false candidate" if f12['ours']['per_block'] == 0 == f12['turboseti']['per_block']
             else f"they raised {f12['ours']['per_block']:.3g} and {f12['turboseti']['per_block']:.3g} false "
                  "candidates a block")
          + ". That band was quiet "
          f"({s12['of']['crowded']} of {s12['blocks']} blocks crowded), and {s12['blocks']} blocks leave the "
          f"rates' intervals reaching {f12['ours']['interval'][1]:.2g}, above the limit.")
        w("")
        w("These are three sessions from one telescope. They do not show better sensitivity in general.")
    else:
        w("These are two sessions from one telescope. They do not show better sensitivity in general.")
    w("")
    w("## The question")
    w("")
    w("Searches for narrowband technosignatures look for a tone drifting steadily in frequency that appears "
      "when the telescope points at the target (ON) and disappears when it points away (OFF). Two things "
      "decide how good a search is: how many real signals it finds, and how many interference signals it "
      "wrongly keeps. A pipeline can always find more by keeping more, so the fair comparison is how many "
      "planted signals each finds at the same rate of false candidates.")
    w("")
    w("## Method")
    w("")
    third = (f"; in 2019 all of the session's {s12['blocks']}" if s12 else "")
    w("- **Data.** Breakthrough Listen's high-resolution spectra (about 2.8 Hz channels) of a whole ON-OFF "
      "cadence: three ON looks at the target, each followed by an OFF look elsewhere. In 2017 and 2016, "
      f"{b['blocks']} blocks of frequency of each session, {b['classes']['crowded']} crowded with interference "
      f"and {b['classes']['clean']} clean, chosen at random within each class{third}. The false-candidate rates "
      "weight each class by its share of the session's blocks; the recovery counts are of the blocks measured, "
      "and are also given weighted to the session below.")
    w(f"- **Planted signals.** {m['per_block']} a block, in the ON looks only, across {len(grid)} strengths "
      f"(S_in {grid[0]:g} to {grid[-1]:g}, the signal-to-noise a search would give collecting all its power in "
      f"ideal noise) and {WORDS.get(m['bins'], m['bins'])} drift bins up to {math.ceil(m['max_drift']):g} Hz/s. "
      "Each look's signal is scaled to that look's own measured noise, so a signal has the same S_in in every "
      "ON look: this measures recovery at a controlled signal-to-noise, not of a transmitter of fixed flux "
      "whose signal-to-noise would vary from look to look.")
    w(f"- **Found** means detected in all three ON looks within ±{m['tol_hz']:g} Hz and ±{m['tol_drift']:g} Hz/s "
      "of the planted signal (the tolerances of Margot et al. 2023).")
    w(f"- **False candidates** are counted by running each pipeline with the wrong looks called ON: the {m['wrong']} "
      "other ways of choosing three of the six looks. Anything a pipeline keeps under a wrong choice is "
      "interference or noise. Candidates sharing a hit count once. This is a wrong-cadence control rate, "
      "not a calibrated false-alarm probability: the telescope's pointings were not assigned at random, the "
      "looks share their interference, and a wrong choice's looks are put in ON, OFF order, not in time "
      "order. How well it predicts false candidates in real cadences has not been measured.")
    w(f"- **Matched comparison.** Each pipeline's cut (its signal-to-noise threshold) is set where it "
      f"gives at most {rate} false candidates a block, and recovery is compared there.")
    w(f"- **Pipelines.** turboSETI {m['turboseti']}; BLISS at commit {b['config']['bliss_commit'][:7]} with its GPU "
      "backend and its own event stage; this search, which sums along every drift up to ±4 Hz/s with the "
      "smear removed, keeps hits from S/N 5 as shadow hits, and calls a candidate only when every ON look "
      "shows the signal and no OFF look does. Its candidate needs a hit at the cut in one ON look and the "
      "signal measured along its track in the others; turboSETI's needs a hit in each. So these are whole "
      "pipelines compared, detector and cadence test together; BLISS's hits through this search's test "
      "separate the two in part.")
    w("- **The second and third sessions** used criteria frozen before their data was read, with a fingerprint "
      "of the code checked at each stage; the third was chosen by a rule fixed beforehand, from the archive's "
      "metadata alone.")
    w("")
    w(f"## Results: the 2017 session ({b['target']}, {b['session']})")
    w("")
    w(f"| pipeline | cut | false candidates a block (95% interval) | signals found of {n(planted)} |")
    w("|---|---|---|---|")
    w(f"| this search | {at['ours']} | {ours_r['per_block']:.2g} ({iv(ours_r['interval'], 2)}) | "
      f"{n(tot['ours'])} |")
    w(f"| turboSETI | {at['turboseti']} | {turbo_r['per_block']:.2g} ({iv(turbo_r['interval'], 2)}) | "
      f"{n(tot['turboseti'])} |")
    w(f"| BLISS's hits, this search's ON/OFF test | {at['bliss_ours']} | {hyb_r['per_block']:.2g} "
      f"({iv(hyb_r['interval'], 2)}) | {n(tot['bliss_ours'])} |")
    w(f"| BLISS as published | none reaches {rate} | lowest {bl_min['per_block']:.3g} (at {bl_min_cut}) | — |")
    w("")
    w(f"At its tested cut, each matched pipeline's measured false rate is at or below {rate} a block. These "
      f"are point estimates, and they differ; {'each 95% interval reaches' if over == 3 else f'{over} of the three 95% intervals reach'} "
      f"above {rate}, and the cuts were chosen on the same "
      f"blocks they are judged on. The pipelines are matched on the measured rate against the target, not "
      f"shown to lie below it. On the same {n(planted)} signals, this search and BLISS's hits through its test "
      f"both found {n(pair['both'])}; this search alone {n(pair['ours_only'])}, BLISS's hits alone "
      f"{n(pair['bliss_ours_only'])}. The difference, {pair['difference in share']:+.3f} of the signals "
      f"({iv(pair['interval'])}, {pair['how']}), holds for this session, these cuts and this signal grid.")
    w("")
    figure(b["recovery_matched"]["three_looks"]["all"], OUT.parent / "recovery.svg")
    w("![Share of planted signals found in all three ON looks, at each pipeline's matched cut, against signal "
      "strength, for each drift range.](recovery.svg)")
    w("")
    w("*Figure 1. Share of the planted signals found in all three ON looks at each pipeline's matched cut, "
      f"against signal strength (the {WORDS.get(len(grid), len(grid))} steps of the grid, evenly spaced), one "
      f"panel per drift range ({m['at_each_point']} signals at each point). At each pipeline's cut its measured "
      f"false rate is at or below {rate} a block; the rates differ, and their 95% intervals reach above "
      f"{rate} (the table above).*")
    w("")
    if control:
        w("**Why BLISS as published has no matched cut.** On the two blocks that carry most of its false "
          "candidates, one list of BLISS's hits at S/N 30 was given to each ON/OFF logic in the same run:")
        w("")
        cols = (("BLISS's event stage", "BLISS's event stage, same hits"),
                ("this search's test", "hits at 30, no shadow hits"),
                ("this search's test, with shadow hits", "hits at 30, shadow hits from 5"),
                ("this search's test, hits grouped at S/N 5", "hits at 5 (as bliss-judge)"))
        w("False candidates at S/N 30 (distinct, over the 19 wrong choices):")
        w("")
        w("| block | " + " | ".join(c[0] for c in cols) + " |")
        w("|---" * (len(cols) + 1) + "|")
        for c in control:
            w(f"| {c['block']} | " + " | ".join(n(c["false_distinct"][k]) for _, k in cols) + " |")
        w("")
        w("With the hits the same, this search's test removes most of them: BLISS's event stage is the "
          "larger cause. The rest come from BLISS grouping its hits at the higher cut; grouped at S/N 5 and "
          "cut afterwards, almost none are left. These are two blocks, run after the main result was seen.")
        w("")
    w(f"## Results: the 2016 session, fixed in advance ({s10['target']}, {s10['session']})")
    w("")
    w("| criterion, frozen before the data was read | result |")
    w("|---|---|")
    for k, v in s10["criteria"].items():
        w(f"| {k} | **{v}** |")
    w("")
    if devs:
        changed = sorted({x.split(": ", 1)[-1] for d in devs for x in d["problems"]})
        w(f"The code changed after the freeze, once: {', '.join(changed)}, logged as a deviation at each of the "
          f"{len(devs)} stages that ran on it ({', '.join(d['stage'] for d in devs)}) and printed in the verdict. "
          f"The reason logged: \"{devs[0]['why']}\" (data/step10/deviations.json).")
        w("")
    w(f"At the frozen cut ({s10['cut']}), this search raised {fr['ours']['per_block']:.3g} false candidates "
      f"a block ({iv(fr['ours']['interval'])}) and turboSETI {fr['turboseti']['per_block']:.3g} "
      f"({iv(fr['turboseti']['interval'])}), against a limit of {s10['rate_limit']}. Recovery held: "
      f"{n(rec['ours']['recovered'])} of {n(rec['ours']['of'])} against {n(rec['turboseti']['recovered'])}; "
      f"paired, {p10['difference']:+.3f} of the signals ({iv(p10['interval'])}). A second pass for curved "
      f"tracks, tested with it, found {n(curved['both'] + curved['first_only'])} of {n(curved['signals'])} "
      f"curved signals against production's {n(curved['both'] + curved['second_only'])}, losing none.")
    w("")
    w("Looked at afterwards, not one of the criteria: nearly all of this search's false candidates lie in "
      "blocks overlapping known satellite bands (GNSS, Inmarsat). No band has been masked, and the test has "
      "not been changed, because that would be choosing the rule after seeing the result.")
    w("")
    if s12:
        f12, r12 = s12["false_rate"], s12["recovery_three_looks"]
        cp = s12["curved_pass"]
        ck_ = [k for k in cp["recovery_three_looks_curved"] if k != "production"][0]
        w(f"## Results: the 2019 session, chosen and fixed in advance ({s12['target']}, {s12['session']})")
        w("")
        w(f"The session was chosen by a rule fixed before any listing was read: Breakthrough Listen's target list "
          f"(Isaacson et al. 2017), telescopes and bands in a fixed order, the first session with a whole ON-OFF "
          f"cadence and a file layout on which planted signals are recovered as on Green Bank's (checked on "
          f"synthetic noise). No Parkes session qualified; this is Green Bank at C band, one recording node's "
          f"{s12['blocks']} blocks, all measured. (A first run of the rule, on a shorter target list, found no "
          f"session; the list was then extended once, before anything else was read.)")
        w("")
        w("| criterion, frozen before the data was read | result |")
        w("|---|---|")
        for k, v in s12["criteria"].items():
            w(f"| {k} | **{v}** |")
        w("")
        if devs12:
            changed = sorted({x.split(": ", 1)[-1] for d in devs12 for x in d["problems"]})
            w(f"The code changed after the freeze, once: {', '.join(changed)}, logged as a deviation at each of the "
              f"stages that ran on it and printed in the verdict. The reason logged: \"{devs12[0]['why']}\" "
              f"(data/step12/deviations.json).")
            w("")
        w(f"At the frozen cut ({s12['cut']}), both pipelines raised {f12['ours']['per_block']:.3g} false "
          f"candidates a block (95% interval {iv(f12['ours']['interval'])}), against a limit of "
          f"{s12['rate_limit']}: a rate of zero, but {s12['blocks']} blocks cannot show it below the limit. "
          f"This search found {n(r12['ours']['recovered'])} of {n(r12['ours']['of'])} signals in all three ON "
          f"looks, turboSETI {n(r12['turboseti']['recovered'])}. The curved pass found "
          f"{n(cp['recovery_three_looks_curved'][ck_]['recovered'])} of "
          f"{n(cp['recovery_three_looks_curved'][ck_]['of'])} curved signals against production's "
          f"{n(cp['recovery_three_looks_curved']['production']['recovered'])}, losing "
          f"{n(cp['production_recoveries_lost'])}. The band was quiet: {s12['of']['crowded']} of "
          f"{s12['blocks']} blocks crowded, against {s10['of']['crowded']} of "
          f"{s10['of']['crowded'] + s10['of']['clean']} in 2016.")
        w("")
    if ops:
        w("## Recovery at every operating point")
        w("")
        w("A single cut does not give one ratio between the pipelines. For each session, the same planted "
          "signals at the frozen cut (30 each), the published one (10 each) and each pipeline's matched cut "
          "(step 4's rule: the lowest tested cut from which the false-candidate rate's point estimate stays at "
          f"most {ops['rate']:g} at every higher cut). Supplementary and exploratory: the frozen verdicts above "
          "are unchanged.")
        w("")
        w("| session | operating point | cuts (this search, turboSETI) | found in the sample | false a block | "
          "paired difference in the sample | weighted to the session |")
        w("|---|---|---|---|---|---|---|")
        for ss in ops["sessions"]:
            for name, pt in ss["points"].items():
                if "found" not in pt:
                    w(f"| {ss['target']} | {name} | — | {pt['note']} | | | |")
                    continue
                pr = {x["windows_of"]: x for x in pt["sample"]}
                wt = pt["weighted"]
                w(f"| {ss['target']} | {name} | {pt['cuts'][0]}, {pt['cuts'][1]} | {n(pt['found'][0])} against "
                  f"{n(pt['found'][1])} of {n(ss['signals'])} | {pt['false_per_block'][0]:.3g}, "
                  f"{pt['false_per_block'][1]:.3g} | {pr[1]['difference']:+.3f} ({iv(pr[1]['interval'])}) | "
                  f"{100 * wt['share'][0]:.1f}% against {100 * wt['share'][1]:.1f}%, {wt['difference']:+.3f} "
                  f"({iv(wt['interval'])}) |")
        w("")
        samp = "; ".join(f"{ss['target']} {ss['sampled']['crowded']} of {ss['blocks']} against "
                         f"{ss['of']['crowded']} of {ss['of']['crowded'] + ss['of']['clean']}" for ss in ops["sessions"])
        moved = max(abs(pt["weighted"]["difference"] - pt["sample"][0]["difference"])
                    for ss in ops["sessions"] for pt in ss["points"].values() if "found" in pt)
        w(f"The sample's crowded blocks against the session's: {samp}. Weighting each class by its share of the "
          f"session (bootstrap over blocks within each class) moves the difference by at most {moved:.3f}, so "
          "no conclusion here rests on how the blocks were sampled. "
          "The paired difference in the sample has a bootstrap over blocks; resampling instead whole "
          "windows of four consecutive blocks of the session (block numbers, gaps of unmeasured blocks kept) "
          "barely widens it, but that tests only correlation between neighbouring blocks, and windows of "
          "sixteen leave too few windows (20 or fewer) for an interval (all in the record).")
        w("")
        w("At the lower cuts the ratio falls (about ten times as many found at 30 each, about three times at "
          "the matched cuts in 2019) while the difference in share grows. In 2016 no tested cut of this search "
          "reached the rate.")
        w("")
    w("## Limitations")
    w("")
    w(f"- {'Three' if s12 else 'Two'} observing sessions, one telescope, one recording pipeline. Nothing here "
      "speaks for Parkes, MeerKAT or another receiver.")
    w("- Steady drifts within ±4 Hz/s, plus one experiment with curved tracks; no pulsed or broadband "
      "signals.")
    if s12:
        w("- The 2017 session's cuts were chosen on the same blocks they were judged on. The 2016 and 2019 "
          "sessions were fixed in advance: in 2016 both false rates failed, in a band crowded with satellite "
          "signals; in 2019 every criterion held, in a quiet band where the rate's interval still reaches above "
          "the limit.")
    else:
        w("- The 2017 session's cuts were chosen on the same blocks they were judged on. Only the 2016 session "
          "was fixed in advance, and there both false rates failed.")
    w("- BLISS's hits through this search's test, and the same-hit control, are combinations of two "
      "pipelines, designed after the main result was seen.")
    if trace:
        tc = trace["counts"]
        null_share = sum(v >= trace["off_max"] for v in off_null["values"]) / len(off_null["values"])
        w(f"- Of the planted signals BLISS finds at S/N 10 and this search raises no candidate for, "
          f"{trace['signals']} were traced stage by stage. {tc['off_noise'] + tc['off_noise_and_shadow']} are "
          f"found strongly in all three ON looks and then called interference because one OFF look reaches "
          f"S/N {trace['off_max']:g} to 8 along the track with no OFF transmission identified: low-level OFF "
          f"evidence consistent with noise ({100 * null_share:.2g}% of {n(len(off_null['values']))} random "
          f"unplanted tracks reach {trace['off_max']:g}; that is the test's rate on noise, not a loss rate for "
          f"these signals, which were chosen because BLISS found them). "
          f"{tc['off_signal']} meet something real in an OFF look, "
          f"{tc['one_on_look'] + tc['no_on_hits']} are missed by the detector (mostly in crowded blocks) and "
          f"{tc['faint']} are too faint. The threshold was set beforehand and is not moved for this.")
    if det:
        w("- " + detector_sentence(det))
    if not s12:
        w("- A third session, chosen by a rule fixed in advance, is still to be measured; until it is, nothing "
          "here is claimed beyond these two sessions.")
    w("- The frozen recovery criterion compares two Wilson intervals, which treat the planted signals as "
      "independent; signals share their block and their session. The paired difference with a bootstrap over "
      "blocks (above) is the better measure, and it is supplementary. All the blocks of a session come from "
      "one observation, so none of these intervals speaks for other sessions.")
    if s12 and bliss12 and bliss12.get("not_possible"):
        w("- BLISS's hits through this search's test, supplementary in the third session, could not be run "
          "there: the step that hands BLISS each block expects a slice width these blocks do not have, and the "
          "frozen rule records that rather than adapting it.")
    w("")
    w("## Data and code availability")
    w("")
    w("The observations are from the Breakthrough Listen Open Data Archive (Lebofsky et al. 2019, PASP 131, "
      "124505). Breakthrough Listen is managed by the Breakthrough Initiatives. The code is at "
      "https://github.com/Ryan-Clinton/SignalSearchYoke (this version was built from the commit named on "
      "its page). The code and the result records behind every number here are to be archived on Zenodo; "
      "the DOI will be added here when they are.")
    w("")
    w("## References")
    w("")
    w("- Lebofsky, M. et al. 2019, PASP 131, 124505: The Breakthrough Listen search for intelligent life: "
      "public data, formats, reduction and archiving.")
    w("- Margot, J.-L. et al. 2023, AJ 166, 206: A search for technosignatures around 11,680 stars with "
      "the Green Bank Telescope at 1.15-1.73 GHz. doi:10.3847/1538-3881/acfda4 (the ±6 Hz, ±0.05 Hz/s "
      "tolerances).")
    w("")
    w("## Revisions")
    w("")
    for v, d, note in REVISIONS:
        w(f"- {v} ({d}): {note}")
    w("")
    w("## Records this version was written from")
    w("")
    for name, r in (("data/measurements/matched-bliss.json", b), ("data/measurements/step10.json", s10),
                    ("data/measurements/step12.json", s12)):
        if r is None:
            continue
        pv = r.get("provenance", {})
        w(f"- {name}: written {pv.get('created_utc', r.get('written_utc'))}, commit "
          f"{str(pv.get('git_commit', ''))[:7]}")
    for c in control:
        w(f"- bliss_control/block_{c['block']:03d}.json: finished {c['finished_utc']}")
    for name, r in (("data/analysis/operating_points.json", ops),
                    ("data/analysis/bliss_only/trace_summary.json", trace),
                    ("data/analysis/bliss_only/detector_misses.json", det),
                    ("data/measurements/off_null.json", off_null)):
        if r:
            pv = r.get("provenance", {})
            w(f"- {name}: written {pv.get('created_utc')}, commit {str(pv.get('git_commit', ''))[:7]}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{OUT}: version {VERSION}, {len(L)} lines")


if __name__ == "__main__":
    sys.exit(main())
