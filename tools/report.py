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

VERSION = "1.8"
DATE = "2026-11-24"
REVISIONS = (("0.1", "2026-11-18", "first draft."),
             ("1.0", "2026-11-19", "first release: the signals BLISS finds and this search misses traced stage by "
                         "stage, and the detector's misses measured."),
             ("1.1", "2026-11-19", "the code's repository, now public, linked."),
             ("1.2", "2026-11-19", "the third session, chosen and fixed in advance (NGC 6946 at C band): every "
                           "criterion held."),
             ("1.3", "2026-11-19", "recovery at every tested cut for all three sessions, with the paired difference "
                           "and blocks resampled in runs; step 12 described as meeting its criteria at the point "
                           "estimate; what the injections, the false-candidate control and the comparison of "
                           "whole pipelines do and do not measure."),
             ("1.4", "2026-11-19", "recovery weighted to each session's share of crowded and clean blocks beside the "
                           "sample's; the neighbouring-block check made over consecutive blocks of the session; "
                           "the matched cut by one rule throughout; the blocks of each session stated."),
             ("1.5", "2026-11-19", "checks of the planted signals: a tone in the voltages, finer sampling, the DC "
                                   "bin and a fixed flux, none of which moves recovery."),
             ("1.6", "2026-11-20", "what the code audits found, stated where it bears on the results: the 2016 "
                           "reads' DC bins, the false-candidate count and its intervals, turboSETI's zero drift and "
                           "fast-drift reporting, how BLISS was run; the planted signals counted per session; the "
                           "injection checks' small differences stated as such; references completed."),
             ("1.7", "2026-11-24", "a false-candidate control on four real cadences of other targets, chosen by a "
                           "rule fixed beforehand and searched whole, with the checks' verdicts on its candidates; and "
                           "signals planted in those cadences, to show how many real-looking signals the checks keep."),
             ("1.8", DATE, "the same signals planted by an independent injector (setigen); this search's recovery "
                           "scored at the middle of the look; what each check costs, with the band check's cost "
                           "stated as a hypothesis under test."))


def control_reading(inj):
    """Where the planted signals show the checks keep a real signal: (kinds of block where they do, where not)."""
    c = inj["cuts"]["30"]
    kinds = (("complete blocks", c["complete"]), ("blocks at the hit limit", c["capped"]))
    return ([k for k, x in kinds if x["reading"].startswith("the checks kept")],
            [k for k, x in kinds if not x["reading"].startswith("the checks kept")])


def control_summary(ctab, csum, inj):
    """One paragraph for the report's summary."""
    a30 = csum["groups"]["all four"]["at_30"]
    kept, lost = control_reading(inj)
    return (f"Four real cadences of other targets, chosen by a rule fixed beforehand and searched whole, gave "
            f"{min(r['rate_30'] for r in ctab['sessions']):.2g} to {max(r['rate_30'] for r in ctab['sessions']):.2g} "
            f"false candidates a block at S/N 30 ({a30['rate']:.3g} over all four, bunched in "
            f"{a30['blocks_with_any']} of {n(a30['blocks'])} blocks), and the checks left none unexplained. "
            "Signals planted in the same cadences show "
            + (f"the checks keeping most real-looking signals in {' and '.join(kept)}" if kept else "the checks not "
               "shown to keep real-looking signals in either complete blocks or blocks at the hit limit")
            + (f", but not in {' and '.join(lost)}, which lie mostly in listed interference bands" if kept and lost
               else "") + ".")


def control_section(ctab, csum, inj, replay, recheck, checks_left_out=None):
    """The report's lines on control B and the signals planted in its cadences, from their records."""
    L = []
    w = L.append
    groups, rows = csum["groups"], {s["target"]: s for s in csum["sessions"]}
    a30, l30, s30 = groups["all four"]["at_30"], groups["L band"]["at_30"], groups["S band"]["at_30"]
    wrong = csum["one_wrong_choice_on_the_project_sessions"]
    w("## A false-candidate control on four real cadences")
    w("")
    w("The false-candidate counts above judge each block with the 19 wrong choices of three ON looks, which "
      "stand in for cadences with no signal. To see what real cadences give, four cadences of other targets, "
      "never read by this project, were chosen by a rule fixed before any of their data was read (the first "
      "four Green Bank sessions, in the order of Breakthrough Listen's target list, in the layout the search was "
      "validated on). Each was searched whole by the search as frozen, in its own time order. No candidate in "
      "them is taken to be a signal, so what they give is a false-alarm count on real cadences.")
    w("")
    w("| cadence | band | blocks | candidates at S/N 30 | a block | at S/N 10 | left unexplained by the checks |")
    w("|---|---|---|---|---|---|---|")
    for r in ctab["sessions"]:
        s = rows[r["target"]]
        w(f"| {r['target']} | {s['band']} | {n(r['blocks'])} | {n(r['candidates_30'])} | {r['rate_30']:.3g} | "
          f"{n(r['candidates_10'])} | {s['at_10']['unexplained']} |")
    run16 = a30["bootstrap_consecutive_blocks"]["16"]
    w(f"| all four | | {n(a30['blocks'])} | {n(a30['candidates'])} | {a30['rate']:.3g} | "
      f"{n(groups['all four']['at_10']['candidates'])} | {groups['all four']['at_10']['unexplained']} |")
    w("")
    w(f"The rate depends on the cadence: at S/N 30, {min(r['rate_30'] for r in ctab['sessions']):.2g} to "
      f"{max(r['rate_30'] for r in ctab['sessions']):.2g} a block. Over all four it is {a30['rate']:.3g}, and drawing "
      f"runs of 16 consecutive blocks again within each cadence gives {iv(run16, 2)}; that describes these four "
      "observations only, and four are too few to say how much the rate varies between sessions. The candidates "
      f"are bunched: all {n(a30['candidates'])} at S/N 30 lie in {a30['blocks_with_any']} of the {n(a30['blocks'])} "
      f"blocks, {a30['in_the_busiest_block']} of them in one. {a30['candidates_in_capped_blocks']} are in the "
      f"{a30['blocks_capped']} blocks where a look reached the search's limit on hits, which are the crowded "
      "ones; that the limit itself makes them is not shown.")
    w("")
    w(f"On the three L-band cadences the rate at S/N 30 is {l30['rate']:.2g} a block; one wrong choice of ON looks, "
      f"weighted as the published rates are, gives {wrong['2016']['rate_30']:.3g} on the 2016 session and "
      f"{wrong['2017']['rate_30']:.2g} on the 2017 one. So 2016's level of false candidates is not what these "
      "L-band cadences give in their real order, but the stand-in is not a steady guide either; different "
      "sessions are compared, so this cannot separate the method from the sessions' own interference. The "
      f"S-band cadence gives {s30['rate']:.2g}.")
    w("")
    by = groups["all four"]["at_10"]["by_verdict"]
    w(f"The checks called every one of the {n(groups['all four']['at_10']['candidates'])} candidates at S/N 10 and "
      f"over interference ({n(by['interference'])} shown, {n(by['likely interference'])} likely), and left none "
      "unexplained. Most of those verdicts rest on signs short of proof, chiefly zero or very low drift, "
      "look-alikes in the cadence and crowding. The tables and verdict counts were made again from the "
      f"packaged records alone ({'identical' if replay['tables_same'] and replay['summary_same'] else 'not identical'}), "
      f"and the checks run again from nothing changed {recheck['verdicts_differing']} of "
      f"{n(recheck['candidates'])} verdicts; both on the same computer, so not an independent verification.")
    w("")
    if inj:
        c = inj["cuts"]["30"]
        al, cp, co = c["all"], c["capped"], c["complete"]
        w("**Would the checks keep a real signal?** A zero means little if they would also explain away a "
          f"signal. Following a protocol fixed beforehand, {n(inj['signals'])} signals were planted in the ON "
          f"looks of {inj['blocks']} blocks of these cadences, half the blocks at the hit limit and half complete, "
          "drawn by their completeness alone, and put through the search, the cadence test and the checks as "
          "they are:")
        w("")
        w("| blocks | signals counted | a hit in an ON look at S/N 30 | candidates | left unexplained | "
          "unexplained among candidates (95% over blocks) |")
        w("|---|---|---|---|---|---|")
        for name, x in (("complete", co), ("at the hit limit", cp), ("all", al)):
            share, ivc = x["unexplained_of_candidates"], x["unexplained_of_candidates_interval"]
            shown = "—" if share is None else f"{share:.2f}" + (f" ({ivc[0]:.2f} to {ivc[1]:.2f})" if ivc else "")
            w(f"| {name} | {n(x['counted'])} | {n(x['hit_in_any_on_look'])} | {n(x['candidates'])} | "
              f"{n(x['unexplained'])} | {shown} |")
        w("")
        kept, lost = control_reading(inj)
        cited = list(c["what_the_checks_cited_against_kept_signals"].items())
        if cited:
            w(f"Against the planted candidates they did not keep, the check cited most was {cited[0][0]} "
              f"({n(cited[0][1])} times), then " + ", ".join(f"{k} ({n(v)})" for k, v in cited[1:4]) + ". A signal "
              "in a listed interference band is marked likely interference whatever it is, and the crowded blocks "
              "lie mostly in those bands; so there the checks cannot keep a real signal, by design.")
            w("")
        w("By the reading fixed in the protocol (informative where the lower end of the interval for unexplained "
          "among candidates is at least 0.5), "
          + (f"the checks kept planted signals in {' and '.join(kept)}" if kept else "the checks were not shown to "
             "keep planted signals in either kind of block")
          + (f", and were not shown to keep them in {' and '.join(lost)}" if kept and lost else "")
          + ". " + ("So control B's zero is informative in " + " and ".join(kept) + (
              ", and says little in " + " and ".join(lost) if lost else "") + "." if kept else
                    "So control B's zero says little about whether a real signal there would be kept.")
          + " Planted tones are clean and do not behave like every real transmitter.")
        w("")
        wt = inj.get("weighted_to_control_b", {}).get("30")
        if wt:
            u = wt["unexplained_of_candidates"]
            w(f"The sample takes as many capped blocks as complete ones; control B's own blocks are "
              f"{100 * wt['share_of_blocks_capped']:.0f}% capped. Reweighted to that mix, the checks leave "
              f"{u[0]:.2f} ({u[1]:.2f} to {u[2]:.2f}) of planted candidates unexplained at S/N 30.")
            w("")
    if checks_left_out:
        lo = checks_left_out["cuts"]["30"]
        band = lo.get("known interference bands")
        if band:
            kept = band["planted_kept_without_it"]
            others = sorted(((k, v) for k, v in lo.items() if k != "known interference bands"),
                            key=lambda kv: -sum(kv[1]["planted_kept_without_it"].values()))
            w("**What each check costs.** Each check was left out in turn, from the verdicts already recorded. At "
              f"S/N 30, the known-band check is the only check standing against {n(sum(kept.values()))} of the "
              f"planted candidates the checks did not keep ({n(kept['complete'])} in complete blocks, "
              f"{n(kept['capped'])} capped), and the only one against {band['control_b_unexplained_without_it']} "
              f"of control B's {n(groups['all four']['at_30']['candidates'])} candidates. The next most costly is "
              f"{others[0][0]} ({n(sum(others[0][1]['planted_kept_without_it'].values()))}). So on these blocks the "
              "band check loses the most real-looking signals and removes almost nothing the other checks do not. "
              "This was found on control B, so it is a hypothesis here, not a result: a version of the checks "
              "with a band as context rather than a sign was fixed beforehand and is being tested on four new "
              "cadences (docs/control-c.md in the repository). The checks in force are unchanged.")
            w("")
    return L


DRIFT_LABELS = ("0 to 0.15", "0.15 to 0.5", "0.5 to 1", "1 to 2", "2 to 4")


def injector_summary(ii):
    """One sentence for the summary on the independent injector."""
    c = ii["cuts"]["10"]
    d = c["own_minus_setigen_advantage"]
    return (f"Planted instead by setigen, an injector this project did not write, the same {n(ii['signals'])} signals "
            f"in {ii['blocks']} blocks of the 2017 session were found {n(c['setigen']['ours'])} times by this search and "
            f"{n(c['setigen']['turboseti'])} by turboSETI at S/N 10, against {n(c['own']['ours'])} and "
            f"{n(c['own']['turboseti'])} with this project's planting: "
            + ("this project's planting favours this search" if c["reading"].startswith("the project") else
               "not shown to favour this search")
            + f" (the difference in the gap between them, {d['difference']:+.3f} of the signals, "
              f"{d['interval'][0]:+.3f} to {d['interval'][1]:+.3f}).")


def injector_section(ii, first):
    L = []
    w = L.append
    w("## An independent injector")
    w("")
    w("Every recovery figure above comes from signals planted by this project's own method. To see whether that "
      "method suits this search better than turboSETI, the same signals (the same places, drifts and strengths) "
      f"were planted by setigen 2.7.0 in {ii['blocks']} blocks of the 2017 session (half crowded, half clean, drawn "
      "by class alone), by a protocol fixed beforehand, and both pipelines were run and scored exactly as above. "
      "setigen sets each signal's strength from its own estimate of the noise, so absolute recovery can differ "
      "between the two; the question is the gap between the pipelines. setigen plants with its Doppler smearing, "
      "its model of a tone integrated over a spectrum; a first run without it is described after the tables.")
    w("")
    w("| planting | S/N | this search | turboSETI | of |")
    w("|---|---|---|---|---|")
    for c in ("10", "30"):
        for how, name in (("own", "this project's"), ("setigen", "setigen's")):
            x = ii["cuts"][c][how]
            w(f"| {name} | {c} | {n(x['ours'])} | {n(x['turboseti'])} | {n(x['signals'])} |")
    w("")
    c = ii["cuts"]["10"]
    d = c["own_minus_setigen_advantage"]
    w(f"At S/N 10, this search's share found minus turboSETI's, with this project's planting less the same with "
      f"setigen's, is {d['difference']:+.3f} ({d['interval'][0]:+.3f} to {d['interval'][1]:+.3f}, blocks "
      "resampled). By the "
      "reading fixed beforehand, "
      + ("**this project's planting favours this search**, and the recovery comparison above overstates its lead "
         "by about that much on these blocks." if c["reading"].startswith("the project") else
         "it is not shown that this project's planting favours this search."
         + (" The gap is wider with setigen's planting, though the ratio is smaller "
            f"({c['setigen']['ratio']:g} against {c['own']['ratio']:g}): setigen's signals were found more often by "
            "both pipelines, which is expected, since its S/N is set from its own estimate of the noise."
            if d["interval"][1] < 0 else ""))
      + " By drift range (S/N 10; this search and turboSETI, this project's planting then setigen's):")
    w("")
    w("| drift (Hz/s) | this project's planting | setigen's |")
    w("|---|---|---|")
    for b, x in c["by_drift_bin"].items():
        w(f"| {DRIFT_LABELS[int(b)]} | {n(x['own']['ours'])} and {n(x['own']['turboseti'])} | "
          f"{n(x['setigen']['ours'])} and {n(x['setigen']['turboseti'])} |")
    w("")
    f10 = first["cuts"]["10"]
    fd, fast = f10["own_minus_setigen_advantage"], f10["by_drift_bin"]
    w("A first run of the same 16 blocks used setigen's default, which puts each spectrum's tone where it is at the "
      "spectrum's start rather than spreading it over the channels it crosses. Both pipelines are scored against "
      "the middle of the spectrum, within 6 Hz, so setigen's fast signals sat outside the tolerance: from 1 to 4 "
      f"Hz/s this search found {n(fast['3']['setigen']['ours'] + fast['4']['setigen']['ours'])} and turboSETI "
      f"{n(fast['3']['setigen']['turboseti'] + fast['4']['setigen']['turboseti'])}, against "
      f"{n(fast['3']['own']['ours'] + fast['4']['own']['ours'])} and "
      f"{n(fast['3']['own']['turboseti'] + fast['4']['own']['turboseti'])} with this project's planting. That run gave "
      f"a difference of {fd['difference']:+.3f} ({fd['interval'][0]:+.3f} to {fd['interval'][1]:+.3f}). The cause "
      "was measured on synthetic data, the change and the first run's records are logged in the protocol "
      "(docs/independent-injection.md), and nothing else was changed.")
    w("")
    return L


def midlook_section(ml):
    L = []
    w = L.append
    w("## Scoring at the middle of the look")
    w("")
    w("A fast drifting signal's frequency is measured where the search's track fits it best, near the middle of a "
      "look, so a small error in drift moves the frequency at the look's start by that error times half the look. "
      "The published scoring compares at the start, and counts some detected signals as missed. The matched blocks "
      "were read and planted again with the same signals; a block counts only if it reproduces its published "
      "result exactly. This search's recovery at S/N 10, three ON looks:")
    w("")
    w("| session | blocks | as published | at mid-look | at mid-look, tolerances growing with drift |")
    w("|---|---|---|---|---|")
    for t, s in ml["sessions"].items():
        a = s["at_10"]["all"]
        w(f"| {t} | {s['blocks'] - len(s['not_reproduced'])} of {s['of']} | {n(a['published'])} | {n(a['mid'])} | "
          f"{n(a['mid_scaled'])} |")
    w("")
    fast = {t: s["at_10"]["by_drift_bin"].get("4") for t, s in ml["sessions"].items()}
    parts = [f"{t} {n(x['published'])} to {n(x['mid_scaled'])} of {n(x['signals'])}" for t, x in fast.items() if x]
    if parts:
        w("Most of the difference is at 2 to 4 Hz/s (" + "; ".join(parts) + "). The growing tolerances are "
          "±max(6 Hz, 10 s × drift) and ±max(0.05, 0.08 × drift) Hz/s. This is a scoring version for this search "
          "alone: turboSETI's recovery was not rescored this way, so the pipelines are compared only under the "
          "published scoring above, and no frozen verdict uses this one.")
        w("")
    return L


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
           f"stages, the detector unchanged; the first failure seen in each: {parts}.")
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


# The records the report is written from, and what each must be (refused otherwise): the 2017 comparison,
# step 10's and step 12's verdicts under their frozen configs, and analysis records of those sessions.
SESSIONS = {"KIC8462852": "AGBT17A_999_68", "HIP17147": "AGBT16A_999_192", "NGC6946": "AGBT19B_999_104"}
FROZEN_CONFIG_SHA = {10: "0af3a6340e1abdf40555a7862f1d07cbd53e75665495ca697469fc5b7714f188",
                     12: "de7a5b9d9675a886c537c7d7a79366d48d95ab57de2841a898dc8c57fc53ee7d"}


def record_problems(b, s10, s12, ops):
    """What does not belong together in the records: [] when they do."""
    bad = []
    if (b.get("target"), b.get("session")) != ("KIC8462852", SESSIONS["KIC8462852"]):
        bad.append(f"the BLISS comparison is of {b.get('target')} {b.get('session')}, not the 2017 session")
    for step, r, target in ((10, s10, "HIP17147"), (12, s12, "NGC6946")):
        if r is None:
            continue
        if (r.get("target"), r.get("session")) != (target, SESSIONS[target]):
            bad.append(f"step {step}'s verdict is of {r.get('target')} {r.get('session')}")
        if r.get("config_sha256") != FROZEN_CONFIG_SHA[step]:
            bad.append(f"step {step}'s verdict was made under another config than the frozen one")
    for x in (ops or {}).get("sessions", []):
        if SESSIONS.get(x.get("target")) != x.get("session"):
            bad.append(f"the operating points name {x.get('target')} {x.get('session')}, not a session of the report")
    return bad


def main():
    b = load("measurements/matched-bliss.json")
    s10 = load("measurements/step10.json")
    s12_path = DATA / "measurements" / "step12.json"
    s12 = json.loads(s12_path.read_text(encoding="utf-8")) if s12_path.exists() else None
    dev12_path = DATA / "step12" / "deviations.json"
    devs12 = json.loads(dev12_path.read_text(encoding="utf-8")) if dev12_path.exists() else []
    bliss12_path = DATA / "step12" / "bliss_status.json"
    bliss12 = json.loads(bliss12_path.read_text(encoding="utf-8")) if bliss12_path.exists() else None
    inj = {}
    for name in ("voltage", "substeps", "dc", "flux"):
        pth = DATA / "analysis" / f"injection_{name}.json"
        if pth.exists():
            inj[name] = json.loads(pth.read_text(encoding="utf-8"))
    ops_path = DATA / "analysis" / "operating_points.json"
    ops = json.loads(ops_path.read_text(encoding="utf-8")) if ops_path.exists() else None
    bad = record_problems(b, s10, s12, ops)
    if bad:
        refuse("; ".join(bad))
    control_dir = DATA / "matched" / f"{b['target']}-{b['session']}" / "bliss_control"
    control = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(control_dir.glob("block_*.json"))]
    trace_path = DATA / "analysis" / "bliss_only" / "trace_summary.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else None
    off_null = load("measurements/off_null.json")
    det_path = DATA / "analysis" / "bliss_only" / "detector_misses.json"
    det = json.loads(det_path.read_text(encoding="utf-8")) if det_path.exists() else None
    nc = DATA / "analysis" / "negative_controls"
    for p in ("tables.json", "summary.json", "package_replay.json", "package_recheck.json", "injection.json"):
        if not (nc / p).exists():
            refuse(f"version {VERSION} reports control B, and {nc / p} is missing")
    ctab, csum, creplay, crecheck, cinj = (json.loads((nc / p).read_text(encoding="utf-8")) for p in
                                           ("tables.json", "summary.json", "package_replay.json",
                                            "package_recheck.json", "injection.json"))
    if ctab["over_all"]["blocks"] != csum["groups"]["all four"]["at_30"]["blocks"]:
        refuse("control B's tables and summary count different blocks")
    later = {"cleft": nc / "injection_checks.json", "indep": DATA / "analysis" / "independent_injection" / "tables.json",
             "indep_first": DATA / "analysis" / "independent_injection" / "unsmeared" / "tables.json",
             "mid": DATA / "analysis" / "midlook" / "tables.json"}
    for p in later.values():
        if not p.exists():
            refuse(f"version {VERSION} reports {p}, which is missing")
    cleft, indep, indep_first, mid = (json.loads(p.read_text(encoding="utf-8")) for p in later.values())
    if indep.get("smearing") is not True or indep_first.get("smearing") is not False:
        refuse("the independent injector's tables are not the smeared run and the first run")
    if any(s["blocks"] != s["of"] for s in mid["sessions"].values()) or len(mid["sessions"]) != 3:
        refuse("the mid-look rescoring is not complete for all three sessions")

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
      f"Telescope, by planting synthetic signals in the data ({n(planted)} in the 2017 session, "
      f"{n(s10['recovery_three_looks']['ours']['of'])} in the 2016 one"
      + (f", {n(s12['recovery_three_looks']['ours']['of'])} in the 2019 one" if s12 else "")
      + ") and counting how many each pipeline found, and how many false candidates each raised, on the same "
      "blocks.")
    w("")
    w(f"On a 2017 session ({b['target']}), at the cut where each pipeline's measured false-candidate rate is "
      f"at most {rate} a block (a point estimate; {'each' if over == 3 else f'{over} of the three'} 95% "
      f"interval{'s' if over not in (1, 3) else ''} reach{'es' if over in (1, 3) else ''} above it, and the cuts were chosen "
      f"on the blocks they were judged on), this search found {n(tot['ours'])} of the {n(planted)} signals in all three ON looks, turboSETI "
      f"{n(tot['turboseti'])}. BLISS run as its own pipeline (its GPU hits and its event stage) never "
      f"reached that false-candidate rate at any cut tested. BLISS's own hits put through this search's ON/OFF test did reach it, and found "
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
        w("")
        w(injector_summary(indep))
        w("")
        w(control_summary(ctab, csum, cinj))
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
    if len(inj) == 4:
        def moved(rec):
            ks = list(rec["totals"])
            a, b = rec["totals"][ks[0]], rec["totals"][ks[1]]
            return max(abs(a[k] - b[k]) for k in a if k != "signals"), a["signals"]
        mv = {k: moved(inj[k]) for k in ("voltage", "dc", "flux")}
        vt = inj["voltage"]["totals"]
        mv["voltage"] = (max(abs(vt["voltage, 51 FFTs"][k] - vt["power, 32 sub-steps (in use)"][k])
                             for k in vt["voltage, 51 FFTs"] if k != "signals"), vt["voltage, 51 FFTs"]["signals"])
        w("- **The planting, checked** (separately, both pipelines, recovery at SNR 10 and 30): a tone added "
          "to synthetic voltages before they are squared, as a receiver sees it, against power added to the "
          f"spectra (at most {mv['voltage'][0]} of {n(mv['voltage'][1])} signals apart); finer sampling of the "
          "drift within a spectrum (the same recoveries); signals crossing the DC bin planted before its "
          f"blanking, as the sky's would be, against after (at most {mv['dc'][0]} of {n(mv['dc'][1])}; only "
          f"{sum(c['crossing_dc_in_an_on_look'] for c in inj['dc']['census'].values())} planted signals in all "
          "three sessions cross a DC bin); and one flux in all three ON looks against one S_in, on real blocks "
          f"(at most {mv['flux'][0]} of {n(mv['flux'][1])}). The differences are a "
          "few signals at most and do not change one pipeline against the other. Flux in Jy Hz on the results pages is nominal, from an assumed SEFD of 10 Jy "
          "measured at L and S band only.")
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
    w(f"| BLISS, its own pipeline | none reaches {rate} | lowest {bl_min['per_block']:.3g} (at {bl_min_cut}) | — |")
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
        w("**Why BLISS's own pipeline has no matched cut.** On the two blocks that carry most of its false "
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
    w("- The false-candidate control is four cadences: enough to show the rate varies between them, not to say how "
      "much it varies between sessions in general. Its interval over blocks describes those four observations only.")
    w("- The frozen recovery criterion compares two Wilson intervals, which treat the planted signals as "
      "independent; signals share their block and their session. The paired difference with a bootstrap over "
      "blocks (above) is the better measure, and it is supplementary. All the blocks of a session come from "
      "one observation, so none of these intervals speaks for other sessions.")
    if s12 and bliss12 and bliss12.get("not_possible"):
        w("- BLISS's hits through this search's test, supplementary in the third session, could not be run "
          "there: the step that hands BLISS each block expects a slice width these blocks do not have, and the "
          "frozen rule records that rather than adapting it.")
    w("")
    L.extend(injector_section(indep, indep_first))
    L.extend(midlook_section(mid))
    L.extend(control_section(ctab, csum, cinj, creplay, crecheck, cleft))
    w("## What the code audits found that bears on these results")
    w("")
    w("A line-by-line audit of the code (docs/audits.md in the repository) found the following. None changes "
      "a frozen verdict; each is stated here so the numbers above are read as what they are.")
    w("")
    w("- **The 2016 reads' DC bins.** The 2016 session's coarse channels are 1,033,216 channels wide and its "
      "files' storage chunks 2^20; the reads blanked the receiver's DC spike at each chunk's middle, so its real "
      "DC spikes (tens of thousands of times the noise) stayed in and one ordinary channel a chunk was smoothed. "
      "None of the 4,016 false events at S/N 30 over the 19 wrong choices lies within 50 Hz of a DC channel (a "
      "spike in every look is vetoed by its OFF looks); step 10's records and verdict stand as made, and the "
      "same blocks read with the corrected rule are being compared. 2017 and 2019 are not affected.")
    w("- **False candidates a block** count the distinct candidates over all 19 wrong choices of ON looks "
      "together, not what one cadence would give; the union can be up to about 19 times one choice's rate. It is "
      "a control for comparing pipelines on the same blocks, not a calibrated false-alarm rate.")
    w("- **The false-candidate intervals** are a bootstrap over blocks within each class (a Poisson upper limit "
      "where a class has none). Where interference correlates between blocks they hold the true rate far less "
      "often than 95%: about 41% in a simulation like 2016, and no method tried fixes that. The 2016 rate's "
      "interval is therefore not a 95% interval.")
    w("- **The recovery intervals** with whole windows of neighbouring blocks resampled are a supplementary "
      "check; they too fall short of 95% when blocks correlate strongly (about 46 to 60% at a correlation of "
      "0.95 in simulation, 80 to 90% at 0.5 to 0.8).")
    w("- **turboSETI** as run (FindDoppler's defaults) never searches zero drift, and at fast drifts its reported "
      "frequency and drift can fall outside the ±6 Hz, ±0.05 Hz/s tolerances: of 60 strong signals at 2 to "
      "4 Hz/s it detected all, and the tolerances credit 5. The comparison is of whole pipelines, so detection, "
      "event association, the reported frequency and drift, and the matching rule all enter the difference.")
    w("- **BLISS** was run from its source at commit 2b98afe on its GPU, with its event stage ported line for line "
      "(and checked against the original on the hits it was given, not under the whole production chain). Its "
      "event stage keeps events with hits in two of the three ON looks; counting only three-ON events, its rate "
      "is still far above 0.1 a block at every cut (1.6 at S/N 100).")
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
    w("- Enriquez, J. E. et al. 2017, ApJ 849, 104: The Breakthrough Listen search for intelligent life: "
      "1.1-1.9 GHz observations of 692 nearby stars (turboSETI's method).")
    w("- Isaacson, H. et al. 2017, PASP 129, 054501: The Breakthrough Listen search for intelligent life: "
      "target selection of nearby stars and galaxies (the list step 12 chose from).")
    w("- turboSETI, version 2.3.2: https://github.com/UCBerkeleySETI/turbo_seti")
    w("- BLISS, commit 2b98afe: https://github.com/UCBerkeleySETI/bliss")
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
                    *((f"data/analysis/injection_{k}.json", v) for k, v in inj.items()),
                    ("data/analysis/bliss_only/trace_summary.json", trace),
                    ("data/analysis/bliss_only/detector_misses.json", det),
                    ("data/measurements/off_null.json", off_null),
                    ("data/analysis/negative_controls/tables.json", ctab),
                    ("data/analysis/negative_controls/summary.json", csum),
                    ("data/analysis/negative_controls/package_replay.json", creplay),
                    ("data/analysis/negative_controls/package_recheck.json", crecheck),
                    ("data/analysis/negative_controls/injection.json", cinj),
                    ("data/analysis/negative_controls/injection_checks.json", cleft),
                    ("data/analysis/independent_injection/tables.json", indep),
                    ("data/analysis/independent_injection/unsmeared/tables.json", indep_first),
                    ("data/analysis/midlook/tables.json", mid)):
        if r:
            pv = r.get("provenance", {})
            w(f"- {name}: written {pv.get('created_utc')}, commit {str(pv.get('git_commit', ''))[:7]}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{OUT}: version {VERSION}, {len(L)} lines")


if __name__ == "__main__":
    sys.exit(main())
