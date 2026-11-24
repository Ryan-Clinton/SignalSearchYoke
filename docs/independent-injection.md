# An independent injector: the protocol

Fixed on 24 November 2026, and committed before the first block was run.
Any change after that is logged at the end of this file.

## The question

Every recovery figure in the report comes from signals planted by this
project's own method, `measure.plant`. Could that method suit this search
better than turboSETI, for example through its channel response, how it
smears a drifting tone within a spectrum, or how it sets a signal's
strength from each channel's noise? The test is to plant the same signals
with an injector this project did not write, setigen 2.7.0 (Brzycki et
al. 2022), and see whether the gap between the two pipelines changes.

## What is run

- **The blocks:** 16 blocks of the 2017 session's matched run (8 crowded,
  8 clean), drawn with seed 20261124 from the run's block classes alone.
  This is `tools/independent_injection.py`.
- **The signals:** the matched run's own 110 per block, with the same
  seed, so the same places, drifts and strengths. A block whose signals
  are not the record's is refused. 1,760 signals in all.
- **setigen's planting:** in the three ON looks, a constant drift path,
  constant intensity and a sinc² profile two channels wide. Each signal's
  strength is setigen's own S/N (`Frame.get_intensity`), set equal to the
  signal's S_in. setigen runs in its own environment
  (`docs/environments/setigen-windows.txt`) and is handed the data in
  ascending frequency, which was checked on synthetic data.
- **The pipelines:** this search and turboSETI as in the matched run,
  scored exactly as the matched run scores them (three ON looks, the
  published tolerances, turboSETI's own hits in every ON look).
- **The comparison:** the same signals planted by `measure.plant` are the
  matched records' own results.

## How it is read, fixed now

The measure is this search's share found minus turboSETI's, with the
project's planting, minus the same with setigen's. It is paired by block
and given a 95% interval over blocks resampled, at S/N 10 (primary) and
30.

- If the lower end is above 0, the project's planting favours this search,
  and the report's recovery comparison must say by how much.
- Otherwise it is "not shown that the project's planting favours this
  search".

Both pipelines' recovery under each injector is reported by drift range,
whatever the result. The two injectors define strength differently, so
absolute recovery may differ between them; the question is only the gap
between the pipelines.

## Limits known now

- One session and 16 blocks.
- setigen's S/N comes from its own estimate of the frame's noise, not this
  project's per-channel noise. That is part of being independent, and a
  source of difference.
- Both injectors plant clean tones.

## Trial run before the first block

The tool was tried once on a block outside the draw (block 13, clean), to
show that it runs end to end; it took 14 minutes. At S/N 10:

| Planting | This search | turboSETI |
|---|---|---|
| This project's | 69 | 14 |
| setigen's | 52 | 23 |

At S/N 30: this project's planting 36 and 4, setigen's 39 and 8. That
block is not part of the result, and nothing above was changed after it.

## Changes after this was fixed

None.
