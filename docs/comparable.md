# Closer to comparable: the plan after the first result

9 November 2026. What it would take for this search to be set beside the
published ones (turboSETI and Breakthrough Listen's surveys, hyperseti,
BLISS, SETI@home's final analysis, UCLA's) and hold up. Written from three
research notes of the same day, in `docs/research/`:
`comparable-pipelines.md`, `published-searches-of-this-star.md` and
`instrument-and-calibration.md`, and from a reading of the code as it
stands (search version 4, checks version 2; check 6 since moved to version 3). It follows
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
| discovery completeness (does a planted signal rank high enough to be looked at?) | step 5: ranked first among this sweep's 11 for 94-100% of kept birdies (87-95% in bands near zero drift); a low bar: held-out wrong-cadence candidates marked only for crowding outrank 44% | SETI@home: top-100 rank, power at 80% uncovered |
| pipelines compared at matched sensitivity | against turboSETI, one session (step 4: 4,520 against 442 of 13,310 at about matched wrong-cadence rates); step 10 tested another, fixed in advance: both failed its false-candidate limit | UCLA: equal injected power and tolerances |
| **against the pipelines made to improve on turboSETI** | **BLISS run** (step 11): as published it reached the matched rate at no cut tested; its hits through this search's ON/OFF test found 4,048 of 13,310. **hyperseti not run** | UCLA against turboSETI only (Margot 2023) |
| **interference history across sessions** | **one cadence's OFF looks** | SETI@home: 14 years of frequency zones; Price: like events at other stars |
| **chance rates** | **check 6: each file's hits near the candidate; checks 7, 8: uniform** | SETI@home: empirical score distributions |
| flux scale | SEFD measured, 10.65 Jy (step 2, 3C295) | assumed (Price, Lebofsky); 12.5 Jy from the Proposer's Guide |
| signal types | steady linear drift only | SETI@home: pulses, triplets, Gaussians, ±100 Hz/s; BLIPSS, Gajjar: periodic and pulsed |
| scale | one cadence | Painter 2025: 9,684 cadences; Price 2020: 1,327 stars |

The detector is no longer the weak link against turboSETI. The gaps (bold)
are in what the results are measured against: ranking, the pipelines built
to improve on turboSETI, interference seen elsewhere, and the kinds of
signal the numbers hold for. The table was brought up to date on 11
November 2026 (steps 2 and 4 done); turboSETI's weakness at drift was
known before this project (Margot et al. 2023), so step 4 confirms it on
this data rather than finding it.

## 2. The steps, in order of value

Each has a **done when**. Steps 1 to 4 belong with the first result; 5 to
11 widen it (10 tests step 4 on another session, 11 against BLISS).

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

**Done** (9 November 2026): `report.search_space` writes it from the
search's parameters, the cadence rules, the usable band, the edge channels
and the measured channel response; the drift-curvature tolerance in it is
an estimate until step 9 measures it.

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

**Done** (9 November 2026; `instrument.py`, docs/seti.md, "The instrument,
measured"): the response is sinc² (Voyager 1, Δχ² 1,950 over Hann); the
SEFD 10.65 Jy (3C295, one steady pair of two; the 3C123 pair above is the
L-band setup), carried to 2017 as the best estimate within the published
bracket of 10 to 12.5 Jy, every EIRP limit given with that range; no spectrum of zeros and no missing node in the cadence,
from the chunk indexes. About 400 MB read in all. Still open: the 2017
cadence's own SEFD (no calibrator in that session), a second steady pair
for repeatability, packets lost within a spectrum (needs the data read: a
per-spectrum power record in a future search version, not this sweep's),
the coarse filterbank's roll-off.

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

**Done, 9 November 2026** (`pipelines.py run`, `pipelines.py compare`;
the result page, "Other pipelines on the same cadence"). On all 308 blocks
of the 2017 cadence: turboSETI 2,744 hits, 0 events; pickles 77 hotspots
with its bands masked (0 kept), 6,424 unmasked (3 at level 1, 1 at level
2); this search 11 candidates. No line was kept by all three.
- The 3 windows pickles kept (masks off) each hold events here called
  interference (OFF S/N 6.0 to 7.4 along the track). Matching by window
  (2.86 kHz) is not matching a signal, so `pipelines.py followup` scores
  each look's window as pickles does, then again with this search's tracks
  there blanked: all 3 then fail level 1. That is track-removal evidence,
  not signal subtraction (the median put in their place changes the
  distribution scored): the tracks are enough to carry each window over
  level 1, not shown to be all that is in it. In the two at 2107 MHz, ON
  look 2's kurtosis is something else: a band about 64 channels wide,
  22-24% over the level, in that look's first two or three spectra only,
  with an apparent movement of about 11 to 29 Hz/s (approximate, from two
  or three spectra), outside both drift searches. pickles' median test
  joined it with a track here in ON look 3: two different features, not
  one in two ON looks. What the band is (drifting interference, a short
  wideband burst, the instrument) is not established; it is a target for
  step 9.
- turboSETI measured at every candidate on its own statistics (its
  comp_stats over the coarse channel, (sum - median) / stddev), not only
  through the 0.227 scale: 10 are under its cut in every ON look (at most
  SNR 6.1). The eleventh, 2197.16 MHz, is SNR 19.1 and 15.7 in ON looks 1
  and 2 but dropped by its top-hit rule (a larger line, SNR 213 to 297,
  2.1 kHz away, inside its ±2.19 kHz window), and 0.2 in ON look 3. The
  noise there is not raised much (1.38 times a quiet block's in ON look 1,
  1.03 to 1.05 in the others): the earlier reading, that interference
  raised its noise, was wrong. Six candidates have zero drift, which
  turboSETI as set never searches (min_drift 0.00001 Hz/s); run with 0 it
  reports none of them either.
- pickles' published masks cover all 11 candidates' frequencies; unmasked,
  7 are hotspots and none reaches level 1 (6 on OFF kurtosis, 1 on ON).
- pickles' code fails on a block with no hotspots (an undefined name at
  line 630); the name is supplied. On blocks 49 and 98 the published code
  and the run here give identical score tables (18 and 76 rows). pickles
  writes scores only: the level cuts are from the paper's text.
- The comparison as first written (948ad77) is kept in git; its record is
  `data/measurements/pipelines-baseline-2026-11-09.json`.

Not shown: that the pipelines agree at matched depth (step 4), since
turboSETI's cut is about SNR 44 on this search's scale.

### Step 4: compare the pipelines at matched sensitivity

The SNR scale (turboSETI's is 0.227 of this search's) says nothing about
which finds more at the same false-alarm rate. Five cadences cannot set
that rate: one distinct false candidate in five gives 0.005 to 1.1 a
block, and a cut tuned until two such counts match would follow the noise.
So the comparison is done in two parts, each measured on its own:

- **Each pipeline's false candidates as a function of its cut,** on the
  blocks of step 7 (at least 100, wrong-ON choices, blocks as the unit, by
  band), with intervals. Its cut is set where that curve gives a chosen
  rate (say 0.1 a block), and the interval on the cut is carried forward.
- **Recovery at those cuts,** from one planting larger than Phase 6's
  (about 10,000 signals over the same blocks, the same signals through
  both): Margot et al. 2023's metric (equal injected power, equal
  tolerances: ±6 Hz, ±0.05 Hz/s), by drift and strength, as recovery
  against injected flux, with the signals one finds and the other misses.
- At the published cuts as well (turboSETI SNR 10, this search's 10), so
  the comparison can be read either way. A claim that one pipeline finds
  more holds only where the recovery intervals at matched rates do not
  overlap.
- **A recovery is a match in frequency and drift both** (±6 Hz, ±0.05
  Hz/s, the same for every pipeline), never a hit somewhere near the
  planting. A match that the same block without the planting already had
  (the same frequency and drift there before) is a false association,
  counted apart from the recoveries and not as one.
- **Clean and crowded bands apart:** every rate and recovery is given for
  the blocks in clean bands and for those in crowded ones (by the band's
  hit density), as well as together.
- **pickles by the windows it keeps,** not an SNR cut: its kurtosis score
  is not a dedoppler detector's. A planting is found by pickles if a
  window holding it passes level 1 (and, apart, level 2) where the same
  window without the planting did not; its false windows are counted the
  same way, per block. It is compared with the others on what each keeps
  and finds, not on a matched SNR.

**Done when:** a matched-recovery table is in `docs/seti.md`, with each
pipeline's false-candidate curve, the cut each needed for the chosen rate
and its interval. Needs step 7 first.

**Done, 10 November 2026** (with step 7): the table, the curves, the cuts
and their intervals are in `docs/seti.md`, "The pipelines at matched
sensitivity". At 0.1 false candidates a block both pipelines need SNR 30;
there, of 13,310 planted signals, this search recovers 4,520 in all three
ON looks and turboSETI 442, and at every estimated rate both reach in the
cuts tested (0.026 to 0.26 a block) this search recovers more on these
blocks. The rates' intervals reach about 0.13 at that cut, so the rates are
about matched, not shown equal; the cuts were chosen on the blocks they are
judged on; and the result is one session's (step 10 tests it on another).
The tenfold count is of this planted population: in signal strength, near
zero drift this search reaches 80% recovery at S_in 50 and turboSETI at
400, and above 0.15 Hz/s turboSETI never reaches it. turboSETI's false
rate does not fall at every step of its cut (a higher cut removes OFF
vetoes too: block 129), so the cut taken is the lowest from which the rate
stays under 0.1 at every higher cut tested (the same cuts here).

**How it was run,** with step 7, as `matched.py run`: 121 blocks
(the 61 crowded, more than 20 hits at the cut in the six looks, and 60 of
the 247 clean at random), each read once, then judged by all three
pipelines with the 19 wrong choices of ON looks (this search at cuts 8 to
100, turboSETI 5 to 100, pickles at its levels) and again with 110 signals
planted in the true ON looks (S_in 10 to 400, drifts to 4 Hz/s);
`matched.py tables` writes the page
`docs/results/KIC8462852-AGBT17A_999_68-matched.md`. How it is measured:

- **One signal, in the false counts:** wrong choices share their looks, so
  candidates are merged per block. The count depends on how: in block 34,
  158 candidate frequencies under 13 wrong choices were 21 signals merged
  within 3 kHz (combs of zero-drift lines 100 Hz apart, switching between
  looks; the checks called every one likely interference); merged by
  shared hits they stay 158, since the comb's lines share none. The curves
  count connected groups of candidates sharing a member hit (no tolerance;
  joined through any chain of shared hits, so a group need not be one
  physical signal); merging by frequency and drift, by frequency within
  6 Hz, 100 Hz and 3 kHz, and no merging are shown beside it.
- **What the false rate is:** the wrong choices give real looks of the
  target the wrong roles, not empty sky, so the rate is a wrong-cadence
  control (how often the cadence logic keeps something when the roles are
  wrong), not a probability of false detection in other observations.
- **Recovery, four ways** (±6 Hz, ±0.05 Hz/s): **in all three ON looks**,
  the main one, an event matching in each ON look, by its hit there or,
  where it has no hit at the cut, by the track this search measured there
  (a candidate needs a hit or a track of S/N 5 in each ON look, so strict
  alone did not show the signal was followed through all three); **three
  hits**, a matching hit in each; **strict**, every ON member hit matching;
  **lenient**, any member. On block 6 at the published cut: 75, 72, 77 and
  81 of 110. turboSETI's event needs a hit in each ON look within its own
  follow window, but its table of an event's hits leaves out a look whose
  first hit number (`TopHitNum`, counted afresh in each look) it has
  already written. So for it, all three looks is strict together with its
  own hit tables at the cut holding a hit matching by the same tolerances
  in each ON look (which hits its event used is not recorded), and three
  hits cannot be told. On block 6, every turboSETI recovery under strict
  also had a matching hit in all three ON looks, at cuts 5 and 10. Blocks
  run before the tracks and those hit counts were kept get them from
  `matched.py tracks`: it plants the recorded signals again, judges the
  true choice and runs turboSETI again, and writes nothing unless what was
  recorded comes out the same (block 6: the same). It ends by naming any
  block still without them, and the page gives the number of blocks the
  false rates and the recovery each come from. Each pipeline is matched at its own reference time:
  turboSETI's frequency is the channel of its first spectrum, half a
  spectrum (about 9 s) after the look's start, which at 1 Hz/s is 9 Hz
  from this search's.
- **turboSETI at a cut:** its hit search is run once at SNR 5 and its tables
  cut to the SNR before its event stage, ON and OFF alike (its own SNR_cut
  would cut only the ON table and keep every weaker OFF hit as a veto). On
  blocks 35 and 45, the 504 hits so cut are exactly those of its search run
  at 10 (frequency, drift and SNR): checked on those two, not shown for
  every block.
- **No matched rate is invented:** if no cut in the range tested gives 0.1
  false candidates a block, the page says so and makes no matched table;
  if the lowest cut tested already does, that cut is an upper bound. A rate
  under 0.1 whose interval reaches above it is said to be so: where the
  intervals are wide, the comparison is unresolved, and neither pipeline
  is shown the better.
- **Kept as test cases:** two wrong-choice candidates the checks left
  unexplained, block 6 judged with looks (0, 1, 2) as ON, 1837.510106 and
  1837.510134 MHz at −1.3674 Hz/s (SNR 30.1 and 15.9): what the checks
  pass though the roles were wrong, for testing better checks against.
- **The intervals** describe this sample of blocks from one session: blocks
  near each other share interference, so they are not fully independent.
- **Speed:** `onoff.py`'s track sums and hit matching now work on arrays,
  with the same additions in the same order (old and new judge give
  identical events on blocks 6 and 50, about twice as fast), and the run
  remembers each look's measured tracks across choices and cuts. Its most
  memory so far is 3.4 GB, on block 35 (12,000 hits a look). A first
  run in a format without each event's member hits (42 blocks) is kept in
  `data/matched/KIC8462852-AGBT17A_999_68/v1/`.

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

- **A held-out set:** the 24 wrong-choice candidates step 4 left
  unexplained (its result page lists them) are not used to set the score's
  terms or scales; they test it afterwards, with the false candidates of
  step 10's session, which the score has never seen. A score tuned until
  these 24 rank last would show nothing.

**Done when:** `check.py` ranks every candidate, and the result page
quotes candidate sensitivity beside detection sensitivity.

**Done, 11 November 2026** (`ranking.py`; docs/seti.md, "Candidates ranked,
and candidate sensitivity"). The score is the sum of −log10 of each
check's chance, capped at 4 a term; nothing is fitted, so there was nothing
to tune on the held-out set. Two departures from the plan above, both
said there: each term is capped rather than scaled by its spread (the
sweep has 11 candidates, too few to measure spreads), and check 7's
chance is used only from 0.1 Hz/s (nearer zero it assumes even drifts and
gave every real candidate the cap). Of 1,400 birdies in five saved
cadences, 1,057 were kept; every one ranked within the first 10, and 94
to 100% ahead of every real candidate, except in the bands near zero
drift (154 of 167): candidate sensitivity equals detection sensitivity
against this sweep. The held-out 24, checked with the store's evidence,
are all marked interference (6 shown, 18 likely), but four in block 14,
marked only for crowding, score 1.07 to 4.05; the best is ahead of every
real candidate and of 44% of the kept birdies. The bar of this sweep's
11 is low; the crowding term is weak (step 6). The score is a heuristic
ranking, not a calibrated probability, and every ranked list keeps its
calibration (`ranking.py`). Taking terms out one at a time (seti.md):
no single term carries the planted signals; crowding and recurrence carry
the held-out interference down.
- **What step 5 has not shown:** discovery completeness at survey scale.
  It ranked planted signals against one cadence's 11 candidates, a weak
  population. **Still to do, after steps 6 and 8:** a ranking challenge
  with many realistic false candidates from several sessions (wrong-cadence
  candidates and real ones), independent of anything that set the score:
  how many planted signals reach the first 10, 50 and 100, how many
  interference candidates fill those places, and how that changes by
  session and band.
- **The held-out 24 stay regression cases** through step 6: whether the
  measured occupancy moves them down is measured, without any rule or
  weight chosen for them.
- **Measured:** the OFF null from 10,000 random tracks (`ranking.py
  offnull`, about 18 minutes); 1,400 birdies (`ranking.py birdies --runs
  8`, about 93 minutes, mostly the checks at about 5 s a candidate); the
  held-out 24 re-read and re-judged (`ranking.py heldout`, 7 blocks, about
  70 minutes, block 35 alone 28).

### Step 6: chance rates from the measured sky, not a uniform one

Check 6 takes its chance from each file's own hits within 1.5 MHz, with
the drift share counted (checks version 3, 9 November 2026: before, from
the spread of the hits picked for lying near the candidate, which made the
chance meaningless). That density is still flat over the 3 MHz, and checks
7 and 8 take a uniform one. Interference clusters by service and
oscillator. After the sweep, the store
holds every hit of 900 MHz: the occupancy (hits at the cut and shadow hits
per kHz, by drift) is measured from it and the checks draw their expected
counts from the occupancy where the candidate lies. The OFF test's veto
rate from random tracks (`blocks.off_null_*`, about 9,800 in a sweep)
replaces the 0.5% from planted signals.

**Done when:** checks 6 to 8 use the measured occupancy, and checks
version 3 is run on the sweep's candidates.

**Done in part, 11 November 2026** (`occupancy.py`, checks version 4;
docs/seti.md, "The measured occupancy"): checks 7 and 9 take their chances
from the session's occupancy by frequency and drift, shadow hits included,
and version 4 is run on the sweep's candidates. The ranking against the
same planted signals: the worst held-out wrong-cadence candidate goes from
ahead of 44% of them to 15%, the planted signals' own scores and verdicts
hardly change; three held-out candidates in block 14 become unexplained
again (by drift their place is not unusually crowded). **Still to do:**
check 6's background is flat over its 3 MHz and check 8 draws random
frequencies uniformly over the band (both measured in kind, not by
occupancy); the OFF test's veto rate from random tracks does not yet
replace the 0.5% from planted signals in the completeness; the occupancy
is one session's, so a candidate is compared only with its own session's
band.

### Step 7: false candidates from many cadences

One distinct false candidate in five cadences (0.2 a block, 95% 0.005 to
1.1) does not predict a sweep. The wrong-ON test is run on many blocks:
every swept block whose six slices are read again for step 3 or step 4 is
judged with the 19 wrong choices too, at no extra reading, and the
distinct false candidates counted per block with the blocks (not the
choices) as the unit, by band.

**Done when:** the false-candidate rate per block is measured on at least
100 blocks, with the clean bands apart from the crowded ones.

**Done, 10 November 2026,** in step 4's run: 121 blocks (61 crowded, 60
clean). At the cut of 10, this search keeps 0.13 false candidates a block
in clean bands (0 to 0.33) and 16 in crowded ones (6.2 to 30), 3.3 a
block over the cadence weighted by class; turboSETI none in clean bands
and 1.4 in crowded ones. Both fall to about 0.05 to 0.07 a block by SNR
30. The curves are in `docs/seti.md`.

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

**Recurrence across sessions is a research question, not only a
matching rule.** A transmitter on an orbiting planet moves far more than a
channel between sessions months apart, so same-frequency matching cannot
find it, and widening the window lets chance matches in. Defensible
intermediate tests, once the history exists: whether weak features recur
when the telescope points at the same sky position more than at controls
(other targets, the same frequencies), and whether a family of weak
signals fits some bounded acceleration model, with the number of
trajectories tried paid for. Neither would show an artificial origin.

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

**Curved tracks measured, 11 November 2026** (docs/seti.md, "Curved
tracks", corrected the same evening: the first count took only the first
event of a signal split into several, and overstated the loss). At S_in
60 the cadence test raises a candidate at 97 of 100 at an acceleration of
10⁻⁴ Hz/s², 49 at 3×10⁻⁴, 1 at 10⁻³; the search itself loses the hits
from about 10⁻³. By step 4's three-look standard (every ON look on the
signal's own track, 12 November, below) far fewer are verified at 10⁻⁴,
and the comparison with turboSETI there (26 of 40 against our 40 raised)
was not like for like. Run again on the same 14,520 signals by the same
standard (12 November): at 10⁻⁴ turboSETI does not keep what production
loses (level at S_in 400 and cut 10, 268 and 269 of 605; fewer below that
and at the matched cut); at 3×10⁻⁴ and S_in 400 it keeps more than
production (181 against 11 at cut 10), and the second pass 498. In all at
cut 30: turboSETI 613, production 4,078, the pass 6,557.

**A curved second pass at matched rates, 11 November 2026**
(`curved_pass.py`, experimental, apart from the search; docs/seti.md,
"a second pass over step 4's blocks"): after the production test, on what
it left unsettled, over step 4's 121 blocks, every wrong-choice hit
through it. Every configuration is matched at 0.1 false candidates a block
at the same cut (30); the false rate there goes from 0.068 to 0.071 at
a_max 10⁻³. Recovered at that cut: at 3×10⁻⁴, 54% to 97% (S_in 400) and
32% to 78% (120); at 10⁻³, 8% to 86% and 0% to 59%; 5,567 to 7,119 of
14,520 planted in all (strict: every formal member hit on the track). By
step 4's three-look standard (each ON look on the signal by its member hit
or its measured track; 12 November, the same plantings judged again):
4,078 to 6,557 (+61%); at 10⁻⁴ 29-44% to 65-78% (S_in 120, 400), at
3×10⁻⁴ 0-2% to 70-82%, at 10⁻³ 0% to 55-81%; the pass's recoveries there
all held by two or three formal hits. Production's own recovery of curved
signals was overstated by the strict test. **Orbital paths** (12
November; a_pk cos(ωt − φ) with the Earth's motion, periods 10 hours to
10 days, 18,150 signals): at cut 30 production 3,607 of 16,335 orbital
signals, the pass at 10⁻³ 9,118; at 3×10⁻⁴ and S_in 120, 15% to 68%; at
10⁻³, 4% to 60%; no false associations, and the controls hold (6 Hz only:
53% at 10⁻³, S_in 120; the mirror path recovers 0.7%, the same signals
under every configuration). **Before any change to `onoff.py`:** the same
on step 10's session (measuring). The checks on the pass's candidates are
measured: no unexplained false candidate added, and the checks keep the
same share of its curved recoveries as of production's (42% against 43%,
full checks, cut 30; docs/seti.md).
The setigen paths (random walk, partial looks) remain.

### Step 10: the matched comparison on another session, fixed beforehand

Step 4's cuts were chosen on the blocks they were judged on, from one
session at one telescope. They are tested, unchanged, on a whole cadence
from another session (KIC8462852 has no other whole cadence in the
archive: `find` lists one ON look each for AGBT17A_999_67 and
AGBT18A_999_30, so another target's, from a different session and if
possible a different band or year). Fixed now, before any of it is read:

- **The cuts:** SNR 30 for both pipelines; no other cut is chosen on the
  new session (the curves are measured and shown, not used to choose).
- **The blocks:** step 4's sample size, 121: up to 61 crowded blocks at
  random and clean ones at random to make the rest, by the same rule for
  crowded, read once. (First fixed here as at least 40, the crowded up to
  20; changed on 12 November, before any of the session's spectra were
  read, because every false candidate in step 4 was in a crowded block and
  its rate's interval at 61 already reached 0.13.)
- **The same measurement:** the 19 wrong choices; 110 signals a block from
  the same S_in and drift grid; recovery in all three ON looks at ±6 Hz,
  ±0.05 Hz/s; turboSETI checked from its own hit tables.
- **What counts as holding:** both rates at SNR 30 at most 0.1 a block
  (with their intervals), and this search's recovery in all three ON looks
  above turboSETI's with the two intervals apart. If a rate comes out above
  0.1, that is reported as the result, not fixed by a new cut.

- **The curved second pass with it:** `curved_pass.block` unchanged on the
  same blocks; at a_max 10⁻³ its false rate at SNR 30 by the same rule, its
  three-look recovery of the signals at |a| ≥ 10⁻⁴ above production's with
  the intervals apart, and none of production's recoveries lost.

**Frozen, 12 November 2026:** `config/step10.json` holds all of this,
the session (HIP17147, AGBT16A_999_192: L band, 2016, the same telescope;
chosen from the archive's listing alone, its reasons in the file) and a
fingerprint of the code that makes the measurement. `independent.py` runs
it in stages (sweep the whole session, choose the blocks, measure, the
curved pass, the verdict) and refuses any stage while the config has
uncommitted changes or the code differs from its fingerprint, unless told
why, which is logged and printed on the result page. The fingerprint
covers `independent.py` itself and every project module the measurement
imports, whole, and from `seti.py` and `curved_pass.py` the functions used
and everything they reach in their own module; the verdict records the git
commit and the config's hash. The verdict fails closed: it is refused
unless each of the 121 chosen blocks has a whole record of each run (its
class, this session's six looks, 110 and 120 signals, every field the
criteria read) and no other block is there, so 13,310 and 14,520 signals,
every one in the denominator; `verdict --progress` reports how far the
runs are and never gives a verdict. Beside the criteria, not one of them:
the same signals paired (both, either alone, neither), with the difference
in share and a bootstrap over blocks, and the false associations. Run on
step 4's own session as a dry run, its verdict gives step 4's numbers
(4,520 against 442 of 13,310; rates 0.068 and 0.049, their intervals
reaching 0.13; paired, 4,085 by this search alone and 7 by turboSETI
alone, a difference of +0.306, 0.301-0.311), and a block missing, one
extra or a record one signal short is refused. (The freeze was written
again on 12 November with these guards, before any of the session's
spectra were read.)
Sweeping the session also puts a second session in the store, so from then
on check 6 sees another session's looks.

**Run, 12-13 November:** the sweep searched all 304 blocks at the frozen
search version (184 crowded, 120 clean), and the rule chose 61 crowded and
60 clean. **One deviation, logged:** the choosing stage stopped on its
first real run, reading each block's search version from the blocks table,
where the store keeps none (it is the run's). The query was changed to read
it through `store.done_blocks`, as the rest of the code does (commit
3289fe3), which changes `independent.py`'s fingerprint; every stage from
the choice on runs with `--deviation` (data/step10/deviations.json) and the
verdict prints it. The rule, its seed and the measuring code are unchanged,
and the choice follows from the hit counts and seed 10 alone. Measure and
the curved pass run with 3 workers each. Both codes are kept: the frozen
fingerprints in config/step10.json at the commit the verdict names, and the
commit each stage ran at in deviations.json and the verdict. The verdict
page is published as generated; its line "fingerprints as frozen" is read
with the deviation line above it (the code differs from the freeze in that
one query).

**What it can and cannot show:** both sessions are Green Bank's, and both
are Breakthrough Listen's spliced spectra from the same pipeline. A result
that holds has reproduced across two observing sessions of one telescope,
in different bands and years; it says nothing yet of Parkes, MeerKAT or
another receiver, nor of an interference environment unlike Green Bank's.

**Done when:** the new session's page is in `docs/results/` and
`docs/seti.md` says whether step 4's result held there.

**Done, 14 November 2026 (09:41 UTC):** the page is
docs/results/HIP17147-AGBT16A_999_192-step10.md, as generated. Recovery
held (4,337 against 417 of 13,310 in all three ON looks; the curved pass
2,769 against 389 of 7,260, none of production's lost). Both false rates
failed: this search 39.1 a block at SNR 30 (13.6-69.2), turboSETI 1.27
(0.27-2.8), against 0.1; the pass the same as production. This is the
result, as fixed beforehand. Described after it, not a criterion: 3,890 of
this search's 3,938 false candidates are in blocks overlapping the known
satellite bands (GNSS, Inmarsat), 3,654 in 7 blocks (docs/seti.md, "The
pipelines at matched sensitivity"); 3,888 lie inside a listed band by their
own frequencies. The full checks on the same 121 blocks, and again on step
4's with the same code and store, were measured after it (post hoc, apart
from the verdict, which stands; docs/seti.md): the full checks leave 8 of
step 10's false candidates unexplained at SNR 10 and none at SNR 30, and
keep 66% of the recovered planted signals there, against 42-43% on step
4's blocks. No band is masked, and the cadence test is not
changed, until the evidence that separates these signals from planted ones
is known.

### Step 11: against BLISS, at matched rates

Step 4 shows this search ahead of turboSETI, whose loss at drift was already
published (Margot et al. 2023: 5.7% against UCLA's 94%). BLISS
(github.com/UCBerkeleySETI/bliss) was written to improve on turboSETI: it
desmears, searches drift steps to ±500, finds hits by connected components
and has an ON/OFF stage of its own (docs/research/comparable-pipelines.md,
section 2). Whether this search finds anything BLISS would miss, on the
same data, is the open question.

- **Run as its authors set it up:** BLISS built from a pinned commit, in
  WSL's Ubuntu on this computer (CPU, and its CUDA backend on the GTX 1080
  if it builds), with its documented defaults; any setting changed for the
  comparison (the drift range to ±4 Hz/s, the SNR cut) said so.
- **Step 4's method, unchanged:** its 121 blocks and 13,310 planted
  signals (`matched.py` plants them again from the saved tones and checks
  the planting is the same), BLISS added as a third pipeline: its false
  events with the 19 wrong choices against its cut, its cut for 0.1 a
  block, recovery in all three ON looks at ±6 Hz, ±0.05 Hz/s, at its own
  reference time; the signals each finds that the other misses.
- **Its ON/OFF stage and ours apart:** BLISS's hits through this search's
  cadence test as well as through its own `event_search`, so a difference
  can be laid to the detector or to the cadence logic.
- **hyperseti** if it runs (it needs cupy, so the GPU); listed, not
  promised: it has no ON/OFF stage.

**Running it here (so far):** BLISS at commit 2b98afe, built twice in WSL
(CPU only, and with CUDA 12.6 for the GTX 1080, a user-level conda-forge
toolkit). Its own tests: 31 of 32 assertions pass in both builds; the one
failure is the Cap'n Proto hit-file round trip ("bad optional access"),
which is not used here (hits are read through its Python module).
- **Its files need one attribute ours lack:** `DIMENSION_LABELS` on the
  data set; added to BLISS's own copy of each slice, the spectra
  unchanged. A block is one Green Bank coarse channel less one channel:
  `seti.blocks` gives it as MHz, and read back it starts on the coarse
  channel's first channel (block 34's is 273 x 2^20) or one after (block
  13's), as the rounding falls. The missing channel, last or first, is
  padded with a copy of its neighbour (fch1 moved back a channel when it is
  the first), and BLISS is given the whole coarse channel, which lets its
  own channelization and passband equalizer apply.
- **Its authors' pipeline, from `bliss_find_hits` and its defaults:**
  normalize; equalize the passband with the Green Bank channel response
  its own tool makes (`bliss_generate_channelizer_response -f 1048576 -N
  12 -M 256`, the recipe it prints for GBT); flag by spectral kurtosis
  (0.25, 50, 2) and sigma clipping (5 iterations, 3, 4); the noise by its
  masked standard deviation; the drift search desmeared; hits by
  connected components at neighbour distance 7; its hit filter (zero
  drift and sigma-clip filters on). Changed for the comparison: the drift
  range, ±4 Hz/s like the others (its default is ±5). The README's
  Python example (no normalizing or equalizing, the coarse channel
  unrecognised) was tried first: its noise estimate took in the passband's
  shape (the standard deviation 3.3 times a robust one), and no hit on
  block 34's first look passed SNR 13.3; through `bliss_find_hits`'s
  steps the same look gives 402 hits at SNR 10 (162 after its filter),
  the strongest at 51.8, in about 9 s a look and cut on the GPU. The
  backend comparison below was made with the README's example.
- **Its event stage, ported:** its own, on a whole block, held every pair
  of hits it compared in a cache until the 35 GB WSL has ran out (killed
  by the kernel). `tools/bliss/bliss_events.py` is the same algorithm line
  for line, run on hits found once; on block 34 cut to 65,535 channels,
  on the CPU backend, it gives BLISS's own 5 events exactly. It is fed the
  hits in a fixed order (by channel, then drift), so it repeats.
  - **Checked against BLISS's own** (`tools/bliss/port_vs_bliss.py`: the
    CPU backend, whose order is fixed, so both see the hits in the same
    order; every event's member hits compared): four 65,535-channel
    segments across block 34 at SNR 5, 10 and 20, 12 of 12 identical, but
    only 9 events among them. With step 4's 110 signals planted in block
    34, eight segments at SNR 10 and 20: 16 of 16 identical, 59 events,
    OFF hits present in four of the cases
    (data/measurements/bliss-port-vs-own-block034-planted.json). A whole block cannot be compared: BLISS's own stage
    keeps every pair of hits it compares, which on a whole block exceeded
    WSL's 35 GB.
  - **Its array version against the line-for-line one:** identical events
    on block 34 (8 cases: SNR 5 and 10, four choices) and on 600 random
    cadences crowded around a few frequencies so that matching and the OFF
    veto are exercised (`bliss_curves.py selftest`).
- **The run:** `python matched.py bliss KIC8462852 [--shard i/n]` reads
  each of step 4's 121 recorded blocks again (refused unless its MHz range,
  look starts and every planted signal's MHz are the record's), runs
  `tools/bliss_curves.py` on the unplanted looks with all 20 choices and on
  the signals planted again with the true choice, at turboSETI's cuts, and
  scores them as the others (`_status`, TOL_HZ and TOL_DRIFT); one record a
  block under the run's `bliss/` folder, step 4's records only read.
  BLISS's frequency is at the look's start: on block 6 its nearest hits to
  49 planted signals are off by 0.23 Hz per Hz/s of drift (half a spectrum
  would be 9.13) and 0.47 Hz in the median. About 20 minutes a block.
  - **Its records:** written whole or not at all (`yoke.write`), each with
    the comparison's configuration (`matched.bliss_config`: BLISS's commit,
    the cuts, hashes of the adapter, the event stage and the patch) and
    what ran (`bliss_curves.provenance`: BLISS's checkout and a hash of its
    local changes, the module, the CUDA runtime, the GPU and its driver,
    Python and package versions, the response file's hash, the steps). A
    block counts as done only when its record parses and has this
    configuration, so a record cut short or made by other code is run
    again. A block BLISS fails on (an error, or more than 4 hours) is
    recorded as failed with the error and the run goes on; it is tried
    once more on the next run (a failure caused by WSL stopping or the
    machine restarting is not BLISS's), and counts as failed after two;
    the tables name every failed block. Crowded blocks run first.
  - **Stops and restarts:** the run holds an OS lock on `bliss/run_i.lock`
    while it lives (freed however it ends), so a second run beside it is
    refused. Each block's unplanted half is kept under `bliss/partial/`
    until the block is recorded, so a stop loses at most the planted half
    of one block. `tools/jobs.ps1` runs a queue of such commands
    (`data/jobs.txt`) one after another, takes a job off only when it exits
    cleanly, tries a failing one three times, and runs only once at a
    time; with `-Install` it also starts at every logon, so after a power
    cut it picks up at the next logon. bliss-judge skips a block only
    when its record is whole (`matched.judge_whole`: this configuration,
    110 signals each judged at every cut, the 19 wrong choices and the
    true one at every cut), and the tables use only such records. Where it runs (the WSL
    distribution, BLISS's Python, the CUDA libraries) are settings
    (`SSY_BLISS_DISTRO`, `SSY_BLISS_PYTHON`, `SSY_BLISS_LD_PATH`; and
    `BLISS_PYTHON_DIR`, `BLISS_RESPONSE`, `BLISS_DEVICE` for the adapter),
    defaulting to places under `~/ssy` in the distribution, checked before
    a run (docs/reproducing-results.md); they are not part of the
    comparison.
  - **Where BLISS loses a planted signal:** for each, the share of its
    track under BLISS's flags in each ON look, and its matching hits before
    and after BLISS's hit filter, so each loss is put to the flags, the
    search, the filter or the event stage. On block 6 at SNR 10, 17 planted
    signals have matching hits in all three ON looks before its filter and
    none after.
  - **Its hit order:** the event stage is also run with each look's hits in
    three seeded random orders, and the tables give the matched cut and
    recovery for each (below).
  - **The tables:** `python matched_tables.py bliss KIC8462852` writes
    docs/results/TARGET-SESSION-bliss.md: the three pipelines' false
    curves (shared hits, step 4's weights), their matched cuts (or "not
    matched" where no tested cut reaches 0.1 a block), recovery at the
    matched cuts on the same planted signals with the pairs found by one
    and not the other, and BLISS's losses by stage.
- **One change to its code, for speed only:**
  `tools/bliss/event_search_off_hits_once.patch`. A scan does not keep its
  hits, so each `hits()` call runs the drift search again, and its event
  stage asked each OFF scan for its hits once for every candidate: over 3
  hours for one block on the GPU without finishing. The patch finds each
  OFF scan's hits once. On the CPU backend, whose hits come in a fixed
  order, the patched and unpatched builds give identical events on block
  34 cut to 65,535 channels (5 and 5; 191 s against 19,727 s).
- **Its GPU hits repeat; their order does not** (`tools/bliss_curves.py
  selftest`, block 34, SNR 5 and 10, every look twice): every field used
  (channel, frequency, drift, SNR, power, bandwidth, width, times) is the
  same on every run; only `time_span_steps` differs, in every hit, and
  looks unset (nothing here reads it). The order they come in changes, and
  the event stage pairs greedily, so its events change with it: over the
  20 choices at SNR 10, two runs in BLISS's own order give 181 and 182
  events with 129 the same, and the fixed order 178, 96 of them the same
  as the first run's; at SNR 5, 199 each, 195 and 165 the same. The counts
  hardly move; which hits make up the events does. So the fixed order is
  one draw among BLISS's own, not BLISS's answer, and its effect is
  measured in the run (three random orders beside it). The two backends
  also disagree on the same look (78 hits on the CPU at SNR 10, 108 on
  the GPU; 5 events against 26), explained next.
- **Where the backends part (measured on that look):** the same mask, noise
  estimates within a few parts per million, and the same drift plane except
  within about 420 channels of either end, where a track runs off the band
  (the CPU writes zeros there, the GPU a partial sum). The hits differ in
  the grouping: both grow a hit from a cell above the cut through every
  neighbouring cell above half of it, the CPU by flooding each region to
  the end, the GPU by labelling cells in parallel. All 77 CPU hits away
  from the edges are among the GPU's; the GPU's 29 others (one at SNR 20)
  lie between channels 46,000 and 59,600, where the CPU reports a single
  hit, at the band's edge (SNR 31.8). Confirmed
  (`tools/bliss/backend_components.py`, which rebuilds BLISS's SNR plane
  from its drift plane and noise, gets 185 of the two backends' 186 hits'
  SNR within 0.1%, and joins the cells above half the cut at its
  neighbour distance): of the 79 regions holding a hit, the backends put
  the same number in 77; one region of 14 million cells (27% of the
  plane) is one hit on the CPU and 30 on the GPU, and the GPU's last hit
  is in the edge strip the CPU zeroes. That look went through the
  README's example (no passband equalizing), where such regions are
  largest.
- **So the GPU backend is the one compared** (the one `bliss_find_hits`
  runs by default, and the only one fast enough), named as such beside
  its figures; its event stage's dependence on hit order is measured in
  the run. Still to do: its hits through this search's cadence test as
  well as its own event stage.

**Result on KIC8462852 (17 November, the cadence test of BLISS's hits 18
November; 121 of 121 blocks, none failed;
docs/results/KIC8462852-AGBT17A_999_68-bliss.md):**

- **BLISS has no matched cut.** Its false candidates a block (shared hits,
  step 4's weights) are 20.8 at SNR 10, 19.7 at 30 and still 4.5 at 100,
  against 0.1 for the other two at 30 (this search 3.3 at 10, turboSETI
  0.29). On the clean blocks it is low (0.1 a block at SNR 10, 0.017 at
  100); the crowded blocks carry it (105 a block at SNR 10, 22.9 at 100),
  and two most of all: block 35 still gives 1,031 at SNR 100, block 129
  275. In the three random hit orders no cut reaches 0.1 either.
- **Its false count does not fall with the cut:** 5,228 over all blocks at
  SNR 5, 6,482 at 8, 4,408 at 20, 6,059 at 30. Its hit count does not
  either: block 129's first look has 3,800 hits at SNR 5, 13,519 at 10 and
  15,995 at 15 (before its filter, the GPU backend), its other looks
  falling as the cut rises. It is BLISS's own grouping: run on that look
  alone, outside the comparison, the GPU gives the record's counts
  exactly, and its widest hit narrows from 15.9 kHz at SNR 5 to 1.5 kHz at
  15 and 75 Hz at 100. A hit grows through every neighbouring cell above
  half the cut, so at a low cut a stretch of interference is one wide hit,
  and at a higher one it breaks into many narrow ones, each free to make
  an event. The CPU backend, which floods each region whole, makes the
  regions wider still (1.2 MHz at SNR 5, 0.75 MHz at 10), and its hit
  filter then removes every hit on that look at both cuts.
- **BLISS's hits found at SNR 5, through this search's cadence test,
  reach the target.** This is `matched.py bliss-judge`: the hits are found
  once a look at SNR 5, and those under the cut are kept as shadow hits,
  as this search's are. They give 12.4 false a block at SNR 10, 0.37 at 20
  and 0.052 at 30. That is a matched cut of 30 (interval 20 to 100), the
  same cut as this search's (0.068 there): comparable operating points,
  both under 0.1, not equal rates. The crowded blocks fall from 62.4 at
  10 to 0.26 at 30; the clean blocks are 0 from 12.
- **Most of BLISS's false candidates come from its event stage, but its
  hit grouping at the higher cut adds some.** bliss-judge's hits are
  BLISS's grouping at SNR 5, not its grouping at 30, so it did not isolate
  the event stage. The control (`matched.py bliss-control`, 18 November)
  takes one hit list, BLISS's own at SNR 30 (one GPU run on both cuts),
  through each logic, on the two blocks that carry most of the false
  candidates. Both logics run in that one run on the same in-memory hit
  lists: BLISS's event stage is the port, given the hits in its
  documented order (channel, then drift). A fingerprint of each cut's
  hit lists is in the record (bliss_control/). Distinct false candidates at SNR 30 over the 19 wrong
  choices, shared hits:

  | block | BLISS's event stage | this search's test | the same, with shadow hits from SNR 5 | this search's test on the SNR 5 hits |
  |---|---|---|---|---|
  | 35 | 1,610 | 85 | 85 | 1 |
  | 129 | 2,627 | 205 | 130 | 0 |

  With the hit list held the same, this search's test removes 95% of
  them on block 35 and 92 to 95% on block 129. What is left comes from
  the hits being grouped at SNR 30: on these two blocks alone it is
  215, about 18 times step 4's whole budget (0.1 a block, about 12 over 121
  blocks). Grouped at SNR 5, with the cut applied afterwards, it is 1 and
  0.

  BLISS's event stage on the same hits gives exactly the counts of
  add_bliss's earlier run (1,610 and 2,627).
  The run repeats bliss-judge's count on the SNR 5 hits exactly (1 and 0
  again). So both stages count, the event stage far more, and the
  combination that works is BLISS's hits grouped at a low cut with a test
  that needs every ON look and no OFF look, as this search's does. Only
  these two blocks were run.
- **What BLISS's detector costs, at that matched cut (30):** BLISS's hits
  through this search's test recover 4,048 of 13,310, this search 4,520.
  Both recover 3,829, this search alone 691, BLISS's hits alone 219: a
  difference of 0.036 of the planted signals (0.026 to 0.046, a block
  bootstrap as step 10's, the blocks the unit). The gap is mostly at fast drifts (2 to 4 Hz/s at S_in 200: 57 against 131;
  1 to 2 Hz/s at S_in 120: 120 against 167) and at the faintest slow
  signals (S_in 40 under 0.15 Hz/s: 55 against 88). At 0.5 to 1 Hz/s and
  S_in 80 BLISS's hits do better (175 against 158). At SNR 10, not at a
  matched rate, this test recovers 5,726 from BLISS's hits against BLISS's
  own event stage's 4,978.
- **Recovery at each pipeline's published SNR 10** (not at matched rates),
  in all three ON looks, of 13,310: this search 8,706, BLISS 4,978,
  turboSETI 1,709. BLISS at SNR 100, still far above 0.1 false a block,
  recovers 1,175. At the matched cut (30) this search recovers 4,520 and
  turboSETI 442.
- **Where BLISS loses them at SNR 10:** of 8,332 not recovered, 4,827 have
  no matching hit in all three ON looks even before its hit filter (its
  search), 2,859 have them before its filter and not after, 482 have them
  in all three and no event (its event stage), 164 are flagged (more than
  half their track under its flags in some ON look). None is a false
  association.
- **What BLISS finds that this search misses (SNR 10 each):** 135 planted
  signals: 102 strong and fast (S_in 120 or more, drift 1 Hz/s or more),
  where this search's own recovery falls off (step 4's table: 175 of 242
  at 2 to 4 Hz/s and S_in 400), 20 strong and slower, 13 weaker (S_in
  under 120, drift under 1 Hz/s). For 107 of them this search does raise a
  candidate on the signal (recovered by the lenient standard), but not
  within ±6 Hz and ±0.05 Hz/s in every ON look: in 94 its best candidate
  has hits in all three ON looks and two of them match (the third off in
  frequency or drift), in the rest one of three, or two or one of fewer,
  so the three-look standard does not count it. 28 have no candidate from this search at all, mostly in
  crowded blocks (35, 36, 48, 50), where the nearest is kHz away. This search finds 3,863 that BLISS
  misses; both find 4,843.
- **The 28, traced one by one** (`tools/trace_bliss_only.py`: each block
  read and planted again, searched unchanged, judged at SNR 10 with the
  true ON looks; `data/analysis/bliss_only/trace_summary.json`, one
  cause each, with flags beside it for the evidence, which overlaps; the
  summary refuses unless it holds each of the 28 exactly once, and a
  block's saved trace is reused only if it is of that block's signals;
  searching.py, onoff.py and matched.py are unchanged from the commit
  the trace was started at, b426740, to this one):
  - 15: this search finds the signal strongly in all three ON looks, and
    the OFF test calls it interference because one OFF look's S/N along
    the track is just over OFF_MAX (6.0 to 7.3), with no hit there and
    no OFF transmission identified: low-level OFF evidence consistent
    with noise, not proved to be noise. Random tracks reach 6 in 0.66% of
    10,000 (`off_null.json`): a measured rate for the OFF test on
    unplanted tracks, not the chance that any one of these was noise,
    and not a loss rate for these 28, which were picked because BLISS
    found them and this search did not.
  - 2 more the same, with a shadow hit (S/N 5.1, 5.2) in that OFF look.
  - 2 lost to something real in an OFF look (S/N 10.1 along the drift;
    24.2 at a fixed frequency beside interference in the unplanted data).
  - 2 missed by the detector in one or two ON looks (fast drifts, 0.98
    and 1.59 Hz/s); the event the other looks make has the same low-level
    OFF evidence as above, so a detector that found them would still
    leave them vetoed.
  - 5 with no hit in any ON look though the track is bright (S/N 12 to
    66): block 35's three, block 96 (-2.04 Hz/s) and block 129: the
    detector, in crowded blocks.
  - 2 too faint: hits 8.8 to 9.6, just under the cut, and one at S_in 20
    beside strong interference 560 Hz away.

  OFF_MAX is not changed for this: it was set before, from planted
  signals, and moving it after seeing which signals it costs would be
  tuning on the test. The veto's other side is already in the numbers:
  every false rate this search is matched on is measured with it, and
  what it keeps out (step 10's frozen false rates failed even with it)
  would have to be measured again at any other threshold.
  The 8 signals whose stage is the detector (the 7 above and the faint
  one beside interference) are being measured stage by stage
  (`tools/detector_misses.py`), the detector unchanged and watched from
  outside: before any pick, the S/N on the signal's exact track and the
  noise of the summed lines in its block for that drift's width, apart
  from the best S/N in the neighbourhood; the hit cap per look, raised in
  steps (5,000, 10,000, 20,000) only where a look reached it; and the
  pixels of the signal's own track that the detector blanked for other
  hits, spectrum by spectrum. In the summary's flags, an OFF look over
  OFF_MAX is counted only in the events built
  (`off_over_off_max_in_events`), not along every planted track.

**Done when:** BLISS's false curve, matched cut and recovery by drift and
strength are on step 4's page beside the other two, with the signals
BLISS finds that this search misses listed and explained.

### Step 12: a third session, before any broad claim

Two sessions of one telescope do not make a general claim of greater
sensitivity. Before one is made, steps 4 and 10's comparison runs, frozen
the same way, on a third session: another telescope if the archive's
listing has a whole ON-OFF cadence of one (Parkes, MeerKAT), otherwise a
markedly different interference environment, chosen from the listing alone
before any of its spectra are read.

**The protocol, proposed 19 November 2026 for review and revised the same
day (a deterministic selection, a compatibility gate, the block rule for
short sessions, a regression against step 10); not frozen, no session
chosen, no listing for it read.** Four stages, each committed before the
next: this protocol reviewed; the session chosen by the rule below from
the archive's listing alone, the choice and its reasons written down; the
config frozen and committed with the code's fingerprints; then the run.
No spectra of a candidate session are read before the freeze is committed.

- **Choosing the session, from metadata alone.** The rule below is
  applied by a script (`tools/step12_select.py`, written and committed
  after this protocol is reviewed and before it is run), so that the same
  listing gives the same session. Every reply of the archive it uses is
  saved with its SHA-256, and the choice record names them. Read: the
  archive's listing (`seti.berkeley.edu/opendata/api/query-files`, its
  fields target, url, mjd, size, center_freq, telescope) and the session
  folder's own file list (as `seti.py find` reads it); for a candidate
  that passes everything else, the first file's header (or HDF5 index),
  never spectra.
  1. **Telescopes, in order:** Parkes; then any other telescope named in
     the listing other than Green Bank, in alphabetical order of its name;
     then Green Bank. Each is queried by telescope alone. If the archive
     will not answer a query without a target, it is queried by each
     target of the list in 5, in that order.
  2. **Bands at Green Bank,** in order: C (3,950 to 8,000 MHz centre), then
     X (8,000 to 11,600 MHz), by the listed centre frequency. L and S
     (steps 10 and 4) are not eligible.
  3. **A session is eligible** when all of these hold, from the listing,
     the folder and one header:
     - six looks of the same high-resolution product (file name ending
       `.0000.h5` or `.0000.fil`, Breakthrough Listen's finest frequency
       product) in the order ON, OFF, ON, OFF, ON, OFF, the three ON
       looks of one target (its name compared without a DIAG_ prefix,
       any case), each OFF look of another, all within 0.06 days of the
       ON looks (`find`'s rule); the first such run in the session;
     - the six looks share one centre frequency (to 1 kHz) and size (to
       1%);
     - no look of the target, and nothing in the session, has had its
       spectra read by this project (KIC8462852, HIP17147 and HIP91699,
       and the sessions AGBT17A_999_68 and AGBT16A_999_192, are out);
     - the reader opens the first file's header without a refusal, and
       the header gives 61 or more blocks;
     - **the compatibility gate:** from the header's geometry alone
       (channel width and its sign, spectrum time, spectra a look,
       channels a block), 110 signals of step 10's S_in and drift grid
       are planted in synthetic noise of that shape (tests/synth.py's
       generator, seed 12, ten blocks) and searched and judged by the
       frozen code. The session passes if the share recovered in all
       three ON looks is at least 0.9 of the share at Green Bank's
       geometry measured the same way, and every drift of the grid fits
       the look (|drift| x the look's length within the channels either
       side the search keeps). This asks only whether the measurement
       means the same on that layout; no spectra are involved.
  4. **Order within a telescope and band:** sessions by their folder name
     (the identifier after `pipeline/`), ascending, as text; within a
     session, the first eligible run by the first ON look's MJD. The
     first eligible session in this order, telescope by telescope, band
     by band, is the one. Folder names are unique, so there are no ties.
  5. **The target list,** used only if the archive needs a target: step
     10's list as written then, less those already read: HIP39826,
     HIP99427, HIP66704, HIP65352, HIP4436, in that order.
  6. **No session eligible anywhere:** step 12 is not run, and that is
     written down with the saved listings. Nothing is relaxed.
- **Unchanged from step 10** (config/step10.json): SNR 30 for both
  pipelines, no cut chosen on the new session; the 19 wrong choices; 110
  signals a block on the same S_in and drift grid; recovery in all three
  ON looks at ±6 Hz and ±0.05 Hz/s; turboSETI from its own hit tables;
  the curved second pass with it. Only the block seed is new: 12.
- **The blocks:** crowded as before (more than 20 hits at the sweep's cut
  in the six looks). Up to 61 crowded at random, all if fewer; clean at
  random to make 121; if the clean are too few, all of them, and more
  crowded at random to make 121 where there are any. A session of fewer
  than 121 blocks (61 or more, by the gate) gives all its blocks. Rates
  are weighted by each class's share of the session as before, the
  intervals worked out from the blocks actually measured, and the
  criteria are the same whatever the number. A session with no crowded
  or no clean block is measured as it is, the missing class reported as
  absent.
- **What counts as holding,** as step 10: both rates at SNR 30 at most
  0.1 a block, with their intervals; this search's recovery in all three
  ON looks above turboSETI's with the intervals apart; for the curved
  pass, its rate by the same rule, its recovery of the curved signals
  above production's with the intervals apart, none of production's lost.
  A failure is the result and is published as generated, as step 10's
  was; no cut, mask or threshold is changed after the session is read.
- **The code:** as it is at the freeze, fingerprinted as step 10's was,
  and run under the same refusals (`--deviation` logged and printed with
  the verdict). The search and the cadence test are the ones step 10 ran:
  of step 10's 86 fingerprints, those that differ now are independent.py,
  matched.py, matched_tables.py, measure.py, pipelines.py, store.py,
  vetting.py and yoke.py (records, tables, the store, the BLISS
  comparison, refusal messages); searching.py, onoff.py and the functions
  of seti.py and curved_pass.py it fingerprints are unchanged. The freeze
  lists each difference with its commit. File fingerprints do not prove
  the measurement is the same, so the freeze also requires
  `tools/regress_step10.py` to pass at the commit frozen: two of step
  10's blocks (the first crowded and the first clean of its choice)
  measured again, and every field of their records but the timings
  identical to step 10's. `independent.py` reads config/step10.json and
  writes data/step10/ by name; before the freeze it will take the step's
  config, step 10's results unchanged.
- **The detector stays as step 10 ran it.** Whatever the measurement of
  the detector's misses (step 11) finds, step 12 tests the method of
  steps 4 and 10. A fix to the detector would be a new version with its
  own validation, not part of step 12.
- **What each measurement is:**

  | measurement | status |
  |---|---|
  | this search against turboSETI, SNR 30 | the criteria, fixed beforehand |
  | the curved second pass against production | the criteria, fixed beforehand |
  | BLISS's hits (found once at S/N 5) through this search's test, cut 30 | supplementary: fixed before step 12, designed after step 11's result |
  | anything else looked at | exploratory, labelled so |

  If BLISS does not read the session's files unchanged (it refuses, or
  its first block fails), its measurement is recorded as not possible on
  that session and left out; it is not adapted after the files are seen.
- **Not done in it:** no investigation of the session's candidates beyond
  the verdict's own records before the verdict is written.

**Done when:** its verdict is published beside step 10's, as generated.

## 3. What this plan does not do

- No GPU code: one cadence takes about three hours on this PC; the
  throughput a GPU buys matters for thousands of cadences (Painter 2025's
  scale), not one.
- No machine-learning filter until the store holds enough labelled hits to
  train and test on (overhaul.md's Phase 9 item 4 stands).
- No claim of a population limit from one star (Margot 2023: 0.95/(η·D),
  which says nothing).
- No beam localisation: the archive's Green Bank files are single-beam.
