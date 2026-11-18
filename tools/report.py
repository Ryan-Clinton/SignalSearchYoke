"""Write the report (docs/publishing.md) from the result records:
docs/report/report.md. Every number comes from a record; the prose around
the numbers is fixed here. The records it reads are listed at the end of the
report with their creation times and the commit that made them.

    python tools/report.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "docs" / "report" / "report.md"

VERSION = "0.1"
STATUS = "draft, not released"
DATE = "2026-11-18"


def load(path):
    return json.loads((DATA / path).read_text(encoding="utf-8"))


def iv(x, digits=3):
    return f"{x[0]:.{digits}g} to {x[1]:.{digits}g}"


def n(x):
    return f"{x:,}"


def main():
    b = load("measurements/matched-bliss.json")
    s10 = load("measurements/step10.json")
    control_dir = DATA / "matched" / f"{b['target']}-{b['session']}" / "bliss_control"
    control = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(control_dir.glob("block_*.json"))]

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

    L = []
    w = L.append
    w("# Comparing radio-signal searches on Breakthrough Listen data")
    w("")
    w(f"Ryan Clinton. Version {VERSION}, {DATE} ({STATUS}).")
    w("")
    w("## Summary")
    w("")
    w(f"I compared a narrowband radio-signal search of my own (SignalSearchYoke) with two published "
      f"pipelines, turboSETI and BLISS, on recorded Breakthrough Listen observations from the Green Bank "
      f"Telescope, by planting {n(planted)} synthetic signals in the data and counting how many each "
      f"pipeline found, and how many false candidates each raised, on the same blocks.")
    w("")
    w(f"On a 2017 session ({b['target']}), at the cut where each gives at most {rate} false candidates a "
      f"block, this search found {n(tot['ours'])} of the {n(planted)} signals in all three ON looks, turboSETI "
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
    w(f"- **Data.** Breakthrough Listen's high-resolution spectra (about 2.8 Hz channels) of a whole ON-OFF "
      f"cadence: three ON looks at the target, each followed by an OFF look elsewhere. {b['blocks']} blocks "
      f"of frequency per session: {b['classes']['crowded']} crowded with interference and "
      f"{b['classes']['clean']} clean, chosen at random within each class and weighted by each class's share "
      f"of the session.")
    w("- **Planted signals.** 110 a block, in the ON looks only, across 11 strengths (S_in 10 to 400, the "
      "signal-to-noise a search would give collecting all its power in ideal noise) and five drift bins up "
      "to 4 Hz/s.")
    w("- **Found** means detected in all three ON looks within ±6 Hz and ±0.05 Hz/s of the planted signal "
      "(the tolerances of Margot et al. 2023).")
    w("- **False candidates** are counted by running each pipeline with the wrong looks called ON: the 19 "
      "other ways of choosing three of the six looks. Anything a pipeline keeps under a wrong choice is "
      "interference or noise. Candidates sharing a hit count once.")
    w(f"- **Matched comparison.** Each pipeline's cut (its signal-to-noise threshold) is set where it "
      f"gives at most {rate} false candidates a block, and recovery is compared there.")
    w(f"- **Pipelines.** turboSETI 2.3.2; BLISS at commit {b['config']['bliss_commit'][:7]} with its GPU "
      "backend and its own event stage; this search, which sums along every drift up to ±4 Hz/s with the "
      "smear removed, keeps hits from S/N 5 as shadow hits, and calls a candidate only when every ON look "
      "shows the signal and no OFF look does.")
    w("- **The second session** used criteria frozen before its data was read, with a fingerprint of the "
      "code checked at each stage.")
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
    w(f"All three matched pipelines meet the {rate}-a-block target at the tested cut, with different "
      f"measured false rates. On the same {n(planted)} signals, this search and BLISS's hits through its test "
      f"both found {n(pair['both'])}; this search alone {n(pair['ours_only'])}, BLISS's hits alone "
      f"{n(pair['bliss_ours_only'])}. The difference, {pair['difference in share']:+.3f} of the signals "
      f"({iv(pair['interval'])}, {pair['how']}), holds for this session, these cuts and this signal grid.")
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
    w("## Limitations")
    w("")
    w("- Two observing sessions, one telescope, one recording pipeline. Nothing here speaks for Parkes, "
      "MeerKAT or another receiver, or for an interference environment unlike Green Bank's.")
    w("- Steady drifts within ±4 Hz/s, plus one experiment with curved tracks; no pulsed or broadband "
      "signals.")
    w("- The 2017 session's cuts were chosen on the same blocks they were judged on. Only the 2016 session "
      "was fixed in advance, and there both false rates failed.")
    w("- BLISS's hits through this search's test, and the same-hit control, are combinations of two "
      "pipelines, designed after the main result was seen.")
    w("- Open: the signals BLISS finds that this search misses are being traced one by one.")
    w("")
    w("## Data and code availability")
    w("")
    w("The observations are from the Breakthrough Listen Open Data Archive (Lebofsky et al. 2019, PASP 131, "
      "124505). Breakthrough Listen is managed by the Breakthrough Initiatives. The code and the result "
      "records behind every number here are to be deposited on Zenodo with this version.")
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
    w(f"- {VERSION} ({DATE}): first draft.")
    w("")
    w("## Records this version was written from")
    w("")
    for name, r in (("data/measurements/matched-bliss.json", b), ("data/measurements/step10.json", s10)):
        pv = r.get("provenance", {})
        w(f"- {name}: written {pv.get('created_utc', r.get('written_utc'))}, commit "
          f"{str(pv.get('git_commit', ''))[:7]}")
    for c in control:
        w(f"- bliss_control/block_{c['block']:03d}.json: finished {c['finished_utc']}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{OUT}: version {VERSION}, {len(L)} lines")


if __name__ == "__main__":
    sys.exit(main())
