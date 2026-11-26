# Control C and a candidate version of the checks: the protocol

Fixed on 24 November 2026, and committed before control C's sessions were
chosen or any of their data read. Any change after that is logged at the
end of this file with its reason.

## Why

On control B's cadences, signals planted in the ON looks showed that the
checks keep about three in four real-looking candidates in complete
blocks, but one in five in blocks at the hit cap (docs/audits.md, audit 4).
Left out in turn, the known-band check (check 3) stood alone against 298
of the 493 planted candidates the checks did not keep at S/N 30, and alone
against none of control B's 158 false candidates.

That was found on control B, so control B can't also be the test of a
change made because of it. Control C is that test.

## The candidate version: checks 6

Version 5, the checks in force, with one change. Check 3 still names any
listed band a candidate lies in, but being in one is **context, not a sign
of interference**: it no longer makes a candidate "likely interference" on
its own. Every other check, threshold and rule is unchanged
(`vetting.vet(..., bands_as_context=True)`, version label
`VERSION_BANDS_AS_CONTEXT`). It is not in force: the checks of steps 4, 10
and 12, and of report 1.7, stay version 5 unless the rule below adopts
version 6.

## Control C

- **The cadences:** the next four sessions by control B's own rule
  (`tools/negative_controls.py`'s docstring), never a session or ON target
  that control B or this project has read: `negative_controls.py select
  --control c`.
- **The sweep:** each searched whole by the search as frozen, in a store of
  its own (`data/controls_c/`).
- **The checks:** both version 5 and version 6 on every candidate, kept
  apart by version.
- **Planted signals:** `docs/control-injection.md`'s protocol unchanged on
  these cadences, with seed 20261125. That is 32 blocks, four capped and
  four complete in each cadence, and 3,520 signals. Every planted candidate
  is judged by both versions.

## The rule for adopting version 6, fixed now

Version 6 becomes the checks' next version only if, on control C, both of
these hold:

1. **It keeps more real-looking signals.** Among planted candidates at S/N
   30, the share left unexplained is higher under version 6 than under
   version 5:
   - in capped blocks; and
   - weighted to control C's own mix of capped and complete blocks.

   In both cases the lower end of a 95% interval for the paired
   difference, with blocks resampled, must be above 0.
2. **It does not let interference through.** Control C's real candidates
   at S/N 30 left unexplained by version 6 must be at most 0.02 a block
   over all four cadences. The upper end of the interval from resampled
   runs of 16 consecutive blocks must be at most 0.05.

`tools/control_c_verdict.py` applies this rule. It was written and tested
before any of control C's results existed.

If either fails, version 5 stays, and the result is reported as measured.
Either way the outcome is written up, failure included. Nothing about
either version, or any threshold, is changed after control C's data is
read. Version 6 was also evaluated on control B, where it was designed;
that result is reported as descriptive only.

## Limits known now

- Four more cadences, still from one telescope.
- Clean planted tones, and the project's own planting method.
- Under version 6, a real transmitter in a listed band can only be caught
  by the other checks. The second part of the rule measures what that
  costs, on four cadences.

## Changes after this was fixed

- 24 November 2026, before any spectra were read: the first draw chose the
  same session, AGBT16B_999_09, under three catalogue stars (HIP 400, 428
  and 443), because the rule skipped targets already chosen but not
  sessions. A control holds a session once, so the rule now passes over a
  session already chosen, and the draw was made again. Only the archive
  listing and the first file's header had been read. Control B's draw is
  unaffected: its four sessions were all different.
- 24 November 2026, while control C's sweep ran and before any of its
  results existed:
  - Planted records now name version 6's version as well as version 5's,
    and are refused if either differs.
  - A record made before versions were recorded is checked against the
    versions its commit's code held.
  - The rule decides on full-precision values, rounding only what is shown.
  - Beside the rule's interval, an exact Poisson upper limit is reported,
    because resampled runs give 0 to 0 when nothing is left unexplained,
    whatever the true rate.
  - A supplementary estimate weighted by cadence and class together is
    given.

  The rule's criteria and limits are unchanged.
- 25 November 2026, after the first cadence's sweep, with none of the
  sweep's tables, checks or planted signals made: the remaining three
  cadences are swept side by side on lanes, not one after another. The
  sweep's lock is now one a target, not one a data folder, and the queue's
  `run` waits for a cadence another lane is sweeping rather than failing.
  The search, its parameters, the cadences, the store and every rule above
  are unchanged; each block is searched and kept exactly as before. Only
  the wall time changes.

## The result (26 November 2026)

All four cadences were swept whole by the frozen search, 1,267 blocks in
all, and every step that follows ran unchanged:
- the checks, by both versions, on every candidate;
- the summary, the context, the package and its replay;
- the 32 planted blocks; and
- the verdict.

Every record is at `332866d`, clean.

**Version 6 is adopted**, by the rule above
(`tools/control_c_verdict.py`, `data/analysis/negative_controls_c/verdict.json`):

| Criterion, at S/N 30 | Required | Measured |
|---|---|---|
| Planted candidates left unexplained, version 6 less version 5, capped blocks | lower end above 0 | +0.422 (0.246 to 0.585) |
| The same, weighted to control C's mix (20.3% of its blocks capped) | lower end above 0 | +0.289 (0.135 to 0.456) |
| Control C's real candidates left unexplained by version 6 | at most 0.02 a block; upper end at most 0.05 | 1 in 1,267 blocks: 0.0008 a block (0 to 0.0023; exact Poisson upper 0.0044) |

**The false-candidate rate** (`tables.json`, `summary.json`): at S/N 30,
96 cadence candidates, 0.076 a block. That is 0.061 to 0.093 exact Poisson,
or 0.027 to 0.140 resampling runs of 16 blocks. By cadence it ranged from
0.044 to 0.107.

They bunch as in control B:
- 93 of the 96 are in the 257 blocks at the hit limit;
- 3 are in the 1,010 complete blocks;
- 23 blocks hold any, and the busiest holds 20.

Under version 5, the checks in force, none is left unexplained (6
interference, 90 likely interference). At S/N 10 there are 1,081 (0.85 a
block), and version 5 leaves 3 unexplained, all weak.

**Planted signals** (`injection.json`): 3,520 signals were planted in 32
blocks, four capped and four complete in each cadence. At S/N 30, 1,111
became candidates.

| Planted candidates left unexplained | Version 5 | Version 6 |
|---|---|---|
| Capped blocks | 117 of 502 (23%) | 329 of 502 (66%) |
| Complete blocks | 395 of 609 (65%) | 554 of 609 (91%) |
| All | 512 of 1,111 (46%) | 883 of 1,111 (79%) |

**What it means.** Version 5 calls most real-looking signals in crowded,
capped blocks interference, because they lie in a known band. Version 6,
which treats the band as context, keeps far more of them. On control C's
real candidates it let one through in 1,267 blocks, against a limit of
0.02 a block.

**What it does not mean:**
- Four more cadences, from one telescope, chosen by the same rule as
  control B's.
- The planted signals are this project's planting, in 32 blocks.
- Adopting version 6 changes the checks from here on. Results already
  published were judged by version 5 and stand as they were, until they are
  judged again and that is reported.
