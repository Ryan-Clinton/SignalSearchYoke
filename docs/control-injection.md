# Planted signals in control B's cadences: the protocol

Fixed on 24 November 2026, and committed before the first planted block of
this experiment was run. Any change after that is logged at the end of this
file with its reason.

## The question

Control B's four real cadences gave 1,187 candidates, and the checks left
none unexplained. That result means little if the checks would also have
explained away a real signal in the same data. So: **of signals planted in
these cadences' ON looks, how many reach each stage, and how many do the
checks leave unexplained?**

## What is run

- **Search, cadence test and checks as they are:** search version 4 and
  checks version 5. No threshold, mask, band or rule is changed for this.
- **The cadences:** control B's four (HIP 2, HIP 169, HIP 171 and HIP 194),
  each in its own real time order.
- **The blocks, chosen once by `tools/control_injection.py choose`:** for
  each cadence, four blocks at the hit cap and four complete blocks, drawn
  with seed 20261124 from the sweep's completeness flags alone. 32 blocks.
  What a block holds is not looked at, so block 42 of HIP 194 is in only if
  the draw picks it. Capped blocks are kept in and reported, never dropped.
- **The signals:** the project's existing planting (`matched.tones` and
  `matched.plant`): 110 a block, in the three ON looks only, two in each
  drift bin and strength (S_in 10 to 400, the published grid and drift
  bins). 3,520 signals. Each block has its own seed.
- **The cuts:** SNR 30, the frozen cut, is primary. SNR 10 is secondary.

## What is measured

For each planted signal, at each cut:

1. **Detector:** in how many ON looks a hit at the cut matches it (6 Hz and
   0.05 Hz/s, the published tolerances).
2. **Cadence test:** whether a candidate matches it in all three ON looks,
   by a member hit or the track measured there.
3. **Checks:** that candidate's verdict from the full checks, with the
   control store's other looks as their evidence. A signal survives only as
   "unexplained, strong" or "unexplained, weak". "Likely interference" counts
   as not surviving, and is not treated as confirmed interference.

A signal matching a candidate the unplanted block already held is counted
apart and credited at no stage.

## How it is reported

- The **primary measure** is the share of counted signals left unexplained
  at SNR 30, over all 32 blocks, with a 95% interval from resampling blocks.
- The same is given for capped and complete blocks apart, for each cadence,
  each drift bin and each strength, with which checks stood against the
  signals they did not keep.
- **The reading, fixed now.** Control B's "none unexplained" is called
  informative about a stage of the data only where the lower end of the 95%
  interval for *unexplained among candidates* is at least 0.5. Otherwise the
  report says the checks were not shown to keep real signals there, and the
  zero says little. Zero-drift-like signals are expected to be marked by
  check 4, and that is reported as measured, not excused.
- The result is reported whichever way it falls, including a failure. It
  changes no verdict of steps 4, 10 or 12, and no check is tuned on it.

## Limits known now

- 32 blocks of four cadences are a sample, not a survey.
- Planted tones are clean and do not behave like every real transmitter.
- This uses the project's own planting, so it cannot rule out a bias of that
  method; an independent injector would be a separate experiment.

## Trial run before the first block

The tool was tried once on a block outside the draw (HIP 169, block 0,
complete, with no candidates of its own), to show that it runs end to end.
At SNR 30 it gave 37 candidates of 110 planted signals, 16 of them left
unexplained. That block is not part of the result, and nothing above was
changed after it.

## Changes after this was fixed

None.
