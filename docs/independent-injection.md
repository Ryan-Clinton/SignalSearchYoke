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

**24 November 2026, after the first run of all 16 blocks: setigen's
Doppler smearing turned on, and the 16 blocks run again.**

- **What the first run showed.** Under setigen's planting, almost no
  signal drifting faster than 1 Hz/s was found by either pipeline. At
  S/N 10, 1 to 2 Hz/s: this search 8 and turboSETI 0, against 202 and 6
  with this project's planting. At 2 to 4 Hz/s: 2 and 0, against 95 and 0.
- **The cause.** By default (`doppler_smearing=False`), setigen puts each
  spectrum's tone where it is at the spectrum's start and does not spread
  it over the channels it crosses while the spectrum is taken. A real tone
  integrated over a spectrum, and `measure.plant`, are centred half a
  spectrum later. Both pipelines are scored against that centre, within
  6 Hz. setigen's tones were therefore drift × 9.1 s away from it, which
  is 18 Hz at 2 Hz/s, so they were scored as missed.
- **How it was measured.** One tone drifting at 2 Hz/s was planted in an
  empty frame with the session's channel width and sampling. The centre
  of each spectrum lay 0.0 Hz from the start-of-spectrum path with
  setigen's default, 16.3 Hz with its Doppler smearing, and 18.3 Hz with
  `measure.plant`.
- **The change.** setigen plants with `doppler_smearing=True`, its own
  model of a tone integrated over a spectrum. With it the centre falls
  within 2 Hz of the scoring's at 2 Hz/s, and within about 4 Hz at
  4 Hz/s. Nothing else changes: not the blocks, the signals, the scoring,
  the measure or how it is read.
- **Bounding each signal.** With smearing on, setigen works each signal
  out over the whole frame of about a million channels, and one look took
  over 30 minutes. Each signal is therefore bounded to the channels its
  track crosses, plus 200 either side (`bounding_f_range`). On a test
  frame this gave the same placement and power to the printed precision.
  One look of 110 signals then takes 4 s.
- **What is kept.** The first run's records are kept in
  `data/analysis/independent_injection/unsmeared/`, and the report gives
  both runs.
- **Why this is not a choice made after seeing the result.** It corrects
  where the signals were planted relative to where they are scored, and
  that error is shown on synthetic data. The direction of its effect on
  the measure was not known beforehand: it removed fast signals from both
  pipelines.

## A second draw, fixed before it ran (25 November 2026)

The change above was made after the first run's result was seen. It was
justified by a fault measured on synthetic data, but the corrected
protocol has so far been judged only on blocks that had already been
looked at. So it is repeated, unchanged, on blocks nobody has looked at
under it.

- **The blocks:** 16 more blocks of the same matched run, drawn with seed
  20261126 by class alone. The draw leaves out the first draw's 16 and
  the trial block 13 (`independent_injection.py run --draw 2`).
  - Crowded: 14, 34, 47, 48, 53, 98, 104 and 181.
  - Clean: 155, 160, 184, 186, 238, 265, 299 and 302.
- **What stays the same:** the signals, setigen with its Doppler smearing
  and bounding, the scoring, the measure, and the reading fixed above. The
  only change is the folder, `second/`.
- **How it is reported:** beside the first draw, not pooled with it. If
  the two readings differ, both are given. The second is the one not
  chosen after a result.

## A third draw, from another session, fixed before it ran (25 November 2026)

Both draws above come from one observation, the 2017 session. They are
separate blocks, not separate observations. So the same protocol is run
once more on the 2016 session (HIP 17147, AGBT16A_999_192, L band),
whose interference is very different: it is crowded with satellite
bands, and both pipelines failed its false-candidate limit.

- **The blocks:** 16 blocks of the 2016 matched run, 8 crowded and 8
  clean, drawn with seed 20261127 by class alone
  (`independent_injection.py run --draw 3`).
  - Crowded: 41, 63, 66, 70, 119, 172, 183 and 189.
  - Clean: 107, 109, 163, 164, 216, 230, 251 and 260.
- **What stays the same:** the signals (the matched run's, the same seed
  for each block), setigen with its Doppler smearing and bounding, the
  scoring, the measure, and the reading fixed above. The blocks are read
  under the DC rule the 2016 matched records were made with, as their
  mid-look rescoring was. The records go in `hip17147/`.
- **What is added:** each record carries each signal's place (`x0`), and
  the project's own planting's results in it must equal the matched
  record's (`record_problems`, tested). Several lanes may work the draw
  at once, one block each, by claim.
- **How it is reported:** beside the two 2017 draws, not pooled with
  them. If its reading differs from theirs, all are given, and the
  difference is a finding about the session, not a reason to choose.

### Its result

The 16 blocks ran unchanged at `177861f`, and their records pass
`record_problems`, including the check against the matched records'
results and places. From this draw on, a record without each signal's
place is refused (`PLACES_FROM`); the first two draws' records carry
none, and their places were checked against the seed when they ran. The tables (`independent_injection.py tables
--draw 3`, `hip17147/tables.json`) were made at `96ec09d`, from a clean
tree.

| Planting | This search, S/N 10 / 30 | turboSETI, S/N 10 / 30 |
|---|---|---|
| This project's | 1,105 / 584 | 221 / 61 |
| setigen's | 1,331 / 853 | 351 / 115 |

The difference is −0.055 at S/N 10 (−0.081 to −0.030) and −0.122 at 30
(−0.144 to −0.101). By the reading fixed above, it is **not shown that
the project's planting favours this search**. This is the same reading as
both 2017 draws. Both intervals lie below 0, so this search's lead in
share is again wider under setigen's planting, and its lead as a ratio
is again smaller: 3.8 against 5.0 at S/N 10. Under both injectors, this
search finds more at every drift range. turboSETI finds 6 signals faster
than 1 Hz/s with the project's planting and none with setigen's, which
is what the 2017 draws also showed.

## Checks of the planting (25 November 2026)

`tests/test_setigen_plant.py` runs `setigen_plant.py` in setigen's own
environment, on synthetic noise.

- **Orientation:** both frequency orders plant identical spectra.
- **Placement:**
  - Without smearing, each spectrum's centre sits within 0.4 Hz of the
    start-of-spectrum path (the first run's fault).
  - With smearing, it sits within 2.5 Hz of the spectrum's middle, on
    the side of the drift's sign.
- **Strength:** setigen sets a signal's strength from its noise estimate,
  which it makes once, when the frame is made. Adding signals does not
  change it. The same signals added in either order, or one at a time,
  give identical spectra.
- **Bounding:** it changes nothing, to 1e-9.
- **The frequency axis:** it is now checked at both ends to 1 mHz, with
  no relative tolerance, and in its channel width. The earlier check's
  default relative tolerance would have passed 14 kHz at 1.4 GHz.
- **Power, a limit found here:** a drifting tone carries about 91% of a
  still tone's power, with or without smearing. setigen's sinc² profile is
  cut at its first zeros by default, and that cuts more from a tone that
  lies between channels. Both pipelines get the same spectra, so the
  comparison stands, but setigen's fast signals are about 9% weaker than
  their nominal strength.
