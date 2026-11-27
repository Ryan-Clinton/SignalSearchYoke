# Both pipelines through the same checks: the protocol

Fixed on 27 November 2026, and committed before any block is run. Any
change after that is logged at the end of this file.

## The question

The report compares two whole pipelines up to their candidates: this
search's cadence test and turboSETI's event stage. Only this search's
candidates then go through the ten checks. Does this search's lead in
recovery survive when both pipelines' candidates go through the same
checks, and the two are compared where each leaves the same rate of false
candidates unexplained?

## What is run

- **The blocks:** 16 blocks of the 2017 session's matched run and 16 of
  the 2016 session's, 8 crowded and 8 clean in each, drawn with seed
  20261127 by class alone. The draw leaves out the 16 blocks of
  `tools/turbo_checks.py blocks` (seed 12), which have already been
  looked at.
- **The signals:** each block's own 110 from the matched run, with the
  same seed, so the same places, drifts and strengths.
- **The pipelines:** this search and turboSETI 2.3.2, each whole and as
  published. The cuts are the grid of `tools/turbo_checks.py` (S/N 5 to
  100).
- **The checks:** version 6 (`vetting.py`), the version in force, on every
  candidate of both pipelines, planted and false alike. A turboSETI
  candidate goes to the checks with the frequency and drift turboSETI
  reports. Its six looks are measured along that track by the code that
  measures this search's candidates (`onoff`, `check.py`), with the same
  store of the session's hits behind the checks that need them. So the
  checks, and everything they read, are the same for both pipelines; only
  the candidate differs.
- **False candidates:** the 19 wrong choices of three ON looks on each
  block without its planted signals, distinct candidates joined by shared
  hits as `matched.py` counts them. Each is put through the checks.

## How it is read, fixed now

For each pipeline, session and cut:

- **Kept:** planted signals found in all three ON looks, within the
  published tolerances, whose candidate the checks leave unexplained
  (strong or weak).
- **Left:** wrong-choice candidates the checks leave unexplained, a block.

Each pipeline's matched cut, by session: the lowest cut at which "left"
is at most 0.1 a block, there and at every higher cut (step 4's rule,
`matched_tables._matched_cut`). The measure is this search's share kept
less turboSETI's, each at its matched cut, paired by block, with a 95%
interval over blocks resampled (4,000 draws, seed 20261127).

- If the interval's lower end is above 0 in a session, **this search's
  lead survives the same checks** in that session.
- If its upper end is below 0, **turboSETI keeps more** in that session.
- Otherwise it is **not shown either way** in that session.

The two sessions are reported apart, not pooled. Whatever the result, the
report gives each pipeline's kept and left at every cut, by drift range,
and what the checks called the planted candidates they did not keep.

If a pipeline has no matched cut in a session (its "left" never reaches
0.1 a block), that is the result for that session, and it is stated.

## Limits known now

- 16 blocks a session, so the rates are rough. One unexplained candidate
  in 16 blocks is 0.06 a block.
- The checks are this project's own. "The same checks" means equal
  treatment, not neutral judges: they were built around this search's
  candidates, and a turboSETI candidate is measured again by this search's
  code before they see it.
- The wrong-choice rate stands in for real cadences, as in the report.
- Two sessions from one telescope.

## Changes after this was fixed

None yet.
