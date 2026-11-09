# Closer to comparable: the plan after the first result

9 November 2026. What it would take for this search to be set beside the
published ones (turboSETI and Breakthrough Listen's surveys, hyperseti,
BLISS, SETI@home's final analysis, UCLA's) and hold up. Written from three
research notes of the same day, in `docs/research/`:
`comparable-pipelines.md`, `published-searches-of-this-star.md` and
`instrument-and-calibration.md`, and from a reading of the code as it
stands (search version 4, checks version 2). It follows
[overhaul.md](overhaul.md), whose Phases 0 to 7 are done and Phase 8 (the
Tabby's star result) is under way; this replaces that plan's Phase 9.

Nothing here needs anything bought or built: every step uses the archive,
the code and this PC. Steps that read many GB say so, and run only on the
owner's go.

## 1. Where it stands against the others

| | this search | the published searches |
|---|---|---|
| drift sums, ±4 Hz/s, desmeared | yes: a box as wide as the smear | turboSETI: no (5.7% recovered by UCLA's test on near-identical data); hyperseti, BLISS: yes |
| noise of the summed lines | measured, true σ | turboSETI: 5% trimmed, SNR 10 ≈ 3.3 σ (Choza 2024) |
| hits below the cut kept | shadow hits from SNR 5 | not kept by BL pipelines |
| ON-OFF test | every ON look seeds; every look measured along the track | turboSETI: hits only; BLISS: distance cut "made up" |
| vetting | ten checks after blc1, with chance rates | blc1 by hand; SETI@home and UCLA by filters and scores |
| completeness | 3,257 planted, end to end, by drift | SETI@home: birdies through the back end; UCLA: 10,000 chirps in voltages; BL: none in Price 2020 |
| **discovery completeness** (does a planted signal rank high enough to be looked at?) | **not measured** | SETI@home: top-100 rank, power at 80% uncovered |
| **pipelines compared at matched sensitivity** | **no** (SNR scale only) | UCLA: equal injected power and tolerances |
| **interference history across sessions** | **one cadence's OFF looks** | SETI@home: 14 years of frequency zones; Price: like events at other stars |
| **chance rates** | **uniform density** | SETI@home: empirical score distributions |
| **flux scale** | **assumed SEFD 10 Jy** | assumed too (Price, Lebofsky); 12.5 Jy from the Proposer's Guide |
| signal types | steady linear drift only | SETI@home: pulses, triplets, Gaussians, ±100 Hz/s; BLIPSS, Gajjar: periodic and pulsed |
| scale | one cadence | Painter 2025: 9,684 cadences; Price 2020: 1,327 stars |

The detector is no longer the weak link. The gaps (bold) are in what the
results are measured against: ranking, other pipelines on the same data,
interference seen elsewhere, the flux scale, and the kinds of signal the
numbers hold for.

## 2. The steps, in order of value

Each has a **done when**. Steps 1 to 4 belong with the first result; 5 to
9 widen it.

### Step 1: say what was searched for

The completeness tables hold for a tone of steady linear drift, present
through each five-minute ON look, at most 1 Hz wide, with a sinc² channel
response. The result page states this search space in one place (drift
range and model, duty cycle, width, the product's time and frequency
resolution) and lists what lies outside it: pulsed and intermittent
signals, non-linear drift, wide signals (Voyager's 322 Hz sidebands were
tiled with 34 hits), drifts beyond ±4 Hz/s.

**Done when:** `report.py` writes a "What this search can and cannot see"
section from the search parameters and the planting model.

### Step 2: measure the instrument instead of assuming it

- **The fine channel's response,** from data: Voyager 1's carrier drifts
  −0.378 Hz/s, crossing about 40 channels in a look, so its power in each
  spectrum against its place within a channel traces the response (sinc²
  if the FFT is unwindowed, as in rawspec; gpuspec's windowing is
  UNVERIFIED). If it is not sinc², `measure.plant` takes the measured shape
  and Phase 6's completeness is run again.
- **The flux scale:** an ON-OFF pair of a flux calibrator in the archive
  (`DIAG_3C123` and `DIAG_3C123_OFF`, session AGBT17B_999_50, all three
  products; others: 3C48, 3C147, 3C286, 3C295) gives the data units in Jy
  through the calibrator's known flux (Perley & Butler 2017) and the
  radiometer equation, hence an SEFD measured at S-band. If the receiver
  or band does not match, the report quotes the range 10 to 12.5 Jy
  (Price 2020's 20 K and 25 K at 2.0 K/Jy) and scales every EIRP by it.
  About 1 to 2 GB read: on the owner's go.
- **Dropped data:** each block's looks checked for spectra of zeros
  (rawspec fills lost packets with zeros: Lebofsky 2019) and for the `zz`
  and `oo` marks of missing and dropped nodes; counted in the store and on
  the result page.

**Done when:** the channel response is measured and written up; the SEFD
is measured, or the range is carried through; zero spectra are counted.

### Step 3: run the other pipelines on the same cadence

No published search of these files lists its hits (Price 2020, Painter
2025 and Ma 2023 publish none; nothing on KIC 8462852 from Green Bank is
published). Their code is public, so they are run here, as Price's was for
HIP 91699:

- **turboSETI with its event pipeline** (`tools/turbo_events.py`) over the
  whole cadence (each 187.5 MHz node written as a file; the sweep's reads
  again, about 100 GB: on the owner's go, or block by block beside a
  future sweep).
- **Painter et al.'s kurtosis screen** (`pickles.py`,
  github.com/UCBerkeleySETI/pickles) on the same cadence.
- Every event any of the three finds is set against the others': found by
  all, by two, by one only, each with the reason the others missed it
  (below the cut, smeared, vetoed in an OFF look, filtered).

**Done when:** a table of every event by pipeline is in the result page,
with each disagreement explained.

### Step 4: compare the pipelines at matched sensitivity

The SNR scale (turboSETI's is 0.227 of this search's) says nothing about
which finds more at the same false-alarm rate. On the five saved cadences:

- the same planted signals (the Phase 6 set) through turboSETI's pipeline
  and this one;
- each pipeline's cut set so both give the same false candidates on the
  wrong-ON choices (step 6's measurement), then recovery compared by drift
  and strength: Margot et al. 2023's metric (equal injected power, equal
  tolerances: ±6 Hz, ±0.05 Hz/s);
- reported as recovery against injected flux for each, and the signals one
  finds and the other misses.

**Done when:** a matched-recovery table is in `docs/seti.md`, with the
cut each pipeline needed for the same false-candidate rate.

### Step 5: rank, and measure discovery completeness

Being kept is not being looked at: 62% of planted candidates were marked
likely interference (mostly for their band). SETI@home's measure is
whether a planted signal ranks among the top few real ones.

- **A score for every candidate:** −log P terms from what the checks
  measure (OFF S/N against the measured OFF distribution, the hit density
  where it lies against the band's, recurrence, look-alikes, drift against
  the Earth's), each scaled by its spread over all candidates, summed; the
  band mark a term, not a veto.
- **Birdies:** signals planted into the swept cadence's real hit lists and
  looks (Phase 6's planting), scored with the real candidates; a birdie
  is uncovered if it ranks in the top N (N = 10 for one cadence). Candidate
  sensitivity: the S_in (and Jy Hz) at which 80% are uncovered, by drift,
  inside and outside the known bands.

**Done when:** `check.py` ranks every candidate, and the result page
quotes candidate sensitivity beside detection sensitivity.

### Step 6: chance rates from the measured sky, not a uniform one

Checks 6 to 8 take a coincidence's chance from a uniform density of hits.
Interference clusters by service and oscillator. After the sweep, the store
holds every hit of 900 MHz: the occupancy (hits at the cut and shadow hits
per kHz, by drift) is measured from it and the checks draw their expected
counts from the occupancy where the candidate lies. The OFF test's veto
rate from random tracks (`blocks.off_null_*`, about 9,800 in a sweep)
replaces the 0.5% from planted signals.

**Done when:** checks 6 to 8 use the measured occupancy, and checks
version 3 is run on the sweep's candidates.

### Step 7: false candidates from many cadences

One distinct false candidate in five cadences (0.2 a block, 95% 0.005 to
1.1) does not predict a sweep. The wrong-ON test is run on many blocks:
every swept block whose six slices are read again for step 3 or step 4 is
judged with the 19 wrong choices too, at no extra reading, and the
distinct false candidates counted per block with the blocks (not the
choices) as the unit, by band.

**Done when:** the false-candidate rate per block is measured on at least
100 blocks, with the clean bands apart from the crowded ones.

### Step 8: an interference history across sessions and targets

Recurrence (check 6) sees what the store holds: one cadence. Price 2020
and SETI@home reject what recurs at other stars and times. The sessions
near this one (Green Bank, May 2017: `find` lists them; HIP 91699's
AGBT17A_999_67 was three days earlier) are searched in the bands where
candidates or crowding lie, their hits kept as the history check 6 and the
occupancy draw on. The retrieval already covers each file's drift window
(`check.recurrence_hits`, since 9 November 2026); beyond a day it looks
within 100 Hz of where the signal started.

**Done when:** at least three other sessions' OFF looks are in the store
in the bands of every candidate, and check 6 is run with them.

### Step 9: other kinds of signal

- **Planted beyond the model** (setigen in turboSETI's environment, as for
  `measure.py setigen`): sine and quadratic drift paths, a random walk,
  and signals on for part of a look (`sine_t_profile`), through this
  pipeline: how much each loses, stated with the result.
- **A drift beyond ±4 Hz/s** in the `.0002` product (2.86 kHz × 1.07 s:
  drifts to about 2.7 kHz/s before a channel a spectrum), with its own
  completeness. A separate search, specified when steps 1 to 8 are done.
- **Pulsed and periodic signals** (BLIPSS-style folding, Suresh et al.
  2023) need the coarse, fast products: listed, not planned.

**Done when:** the losses for the setigen paths are measured and on the
result page; the `.0002` search has its own spec.

## 3. What this plan does not do

- No GPU code: one cadence takes about three hours on this PC; the
  throughput a GPU buys matters for thousands of cadences (Painter 2025's
  scale), not one.
- No machine-learning filter until the store holds enough labelled hits to
  train and test on (overhaul.md's Phase 9 item 4 stands).
- No claim of a population limit from one star (Margot 2023: 0.95/(η·D),
  which says nothing).
- No beam localisation: the archive's Green Bank files are single-beam.
