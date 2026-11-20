# Audit plan

Twenty-four audits of the project, set on 19 November 2026 at commit
5c3fd08 (report version 1.2, steps 4 to 12 done), ordered so that the
questions the results rest on come first. Each audit reads the code, not
only the docs; checks the science against published work; gives concrete
failure cases; and separates confirmed bugs, plausible risks and future
work. Every finding gets a verdict here: **built**, **built in part**,
**planned** (new work, given to a later audit or a new experiment), or
**not done**, with the reason.

Two rules hold throughout. The detector is not changed to improve a
finished result: an improvement is a new, separately versioned detector,
tested on observations chosen independently and fixed in advance. And
the finished experiments (steps 4, 10 and 12) stay as they are: any
reanalysis of their records is labelled supplementary or exploratory and
never enters their frozen verdicts.

Each completed audit is recorded below as it lands, with the commit that
answered it.

## Status

| # | Audit | Phase | Priority | Status |
|---|---|---|---|---|
| 1 | Scientific methodology | 1 | critical | **done** (19 Nov 2026), re-audited the same day; see below |
| 2 | Signal injection accuracy | 1 | critical | **re-audited** (20 Nov 2026): paired reruns running; see below |
| 3 | turboSETI comparison fairness | 1 | critical | **re-audited** (20 Nov 2026): the experiment corrected, 16 blocks queued; see below |
| 4 | False-positive methodology | 1 | critical | **in progress** (20 Nov 2026): record-based checks done, the time-order test queued; see below |
| 5 | The 2016 interference failure | 1 | critical | **in progress** (20 Nov 2026): records analysed, blocks read again queued; see below |
| 6 | Detector completeness and missed signals | 1 | high | to do |
| 7 | BLISS comparison | 1 | high | **in progress** (20 Nov 2026): provenance enforced, two-ON split measured, wider same-hit control queued; see below |
| 8 | Statistical analysis and uncertainty | 1 | high | **done** (20 Nov 2026): `tools/statistical_checks.py` on all three sessions; see below |
| 9 | Core narrowband detection algorithm (`searching.py`) | 2 | high | **in progress** (20 Nov 2026): four findings confirmed with the search's own code, the blocks queued; see below |
| 10 | Curved Doppler search | 2 | high | **in progress** (20 Nov 2026): the two untraced signals found, the matcher's two weaknesses being measured; see below |
| 11 | ON/OFF cadence matching (`onoff.py`) | 2 | high | **in progress** (20 Nov 2026): three findings confirmed with `onoff.py`'s own functions, measured in the queued blocks run; see below |
| 12 | Candidate vetting and ranking | 2 | high | **in progress** (20 Nov 2026): five defects fixed as checks version 5, no recorded verdict changed; the ranking challenge planned; see below |
| 13 | Instrument calibration and sensitivity | 2 | high | **in progress** (20 Nov 2026): calibration records used only where they apply; the coarse-channel response and band-wide sensitivity planned; see below |
| 14 | Data acquisition and integrity | 2 | high | to do |
| 15 | Astronomical signal coverage | 2 | medium | to do |
| 16 | End-to-end reproducibility | 3 | critical | to do |
| 17 | Experiment freezing and scientific provenance | 3 | high | to do |
| 18 | The report and its claims | 3 | high | to do |
| 19 | Public repository and release readiness | 3 | high | to do |
| 20 | Parallel processing and performance | 4 | high | to do |
| 21 | Database and evidence storage | 4 | medium | to do |
| 22 | Distributed volunteer computing (`docs/multiuser.md`) | 4 | high | to do |
| 23 | Testing and regression coverage | 4 | high | to do |
| 24 | Large-scale survey strategy | 4 | medium | to do |

## What each audit covers

**Phase 1: scientific integrity and detector accuracy**

1. **Scientific methodology.** Whether the experiments support the claims;
   the controls; selection bias; whether the tests are independent.
2. **Signal injection accuracy.** Whether planted signals stand for real
   transmissions: noise, drift, the spectrometer's response, observing
   conditions.
3. **turboSETI comparison fairness.** The same data, strengths, cuts,
   matching rules and chances to detect for both; anything that favours
   either.
4. **False-positive methodology.** The 19 wrong ON/OFF choices, their
   dependence, candidate grouping, the rate estimates and intervals, and
   how well they predict real false alarms.
5. **The 2016 interference failure.** The 39.1 false candidates a block,
   satellite interference, the OFF test, and how rejection could improve
   without losing real signals.
6. **Detector completeness and missed signals.** The 2,000-hit cap, strong
   signals missed in crowded spectra, drift and frequency accuracy,
   blanking, unseen failure modes.
7. **BLISS comparison.** The BLISS run and its GPU adapter, the comparison
   with its published event logic, the hybrid, and why the 2019
   supplementary measurement could not run.
8. **Statistical analysis and uncertainty.** Bootstrap validity, correlated
   blocks, Wilson intervals, paired comparisons, multiple testing, how much
   evidence there is for generalising.

**Phase 2: search algorithms and astrophysics**

9. **Core narrowband detection.** `searching.py`: the mathematics, noise
   estimation, smearing, drift sums, thresholds, numerical accuracy, speed.
10. **Curved Doppler search.** Acceleration modelling, recovery, false
    candidates, realistic orbits, parameter coverage, other algorithms.
11. **ON/OFF cadence matching.** `onoff.py`: association across looks,
    weak signals, missing detections, the OFF veto, tolerance edges,
    interference that looks like a candidate.
12. **Candidate vetting and ranking.** The ten checks, their probabilities,
    recurrence, ranking, misleading evidence, how a real signal could be
    wrongly rejected.
13. **Instrument calibration and sensitivity.** Telescope metadata, SEFD,
    channel response, signal strength in physical units, the limits on
    sensitivity claims.
14. **Data acquisition and integrity.** HDF5 reading, HTTP range requests,
    chunk indexes, frequency and time alignment, ETags, corrupt or unusual
    recordings.
15. **Astronomical signal coverage.** What is not searched for: broad
    signals, pulses, periodic transmissions, high drifts, accelerations,
    more complex orbits.

**Phase 3: reproducibility and publication**

16. **End-to-end reproducibility.** Whether another computer reproduces the
    results from a fresh checkout and the evidence package, across systems.
17. **Experiment freezing and provenance.** Steps 10 and 12: fingerprints,
    selection rules, logged deviations, whether a change could move a
    result unseen.
18. **The report and its claims.** Every result, figure and claim in
    `docs/report/report.md` against its records; terminology, statistics,
    limits.
19. **Public repository and release readiness.** README, setup, security,
    licences, dependencies, citation, tags, releases, Zenodo, consistency.

**Phase 4: engineering, performance and scaling**

20. **Parallel processing and performance.** Scheduling, crashes, atomic
    writes, resuming, memory, CPU use, speed without changing results.
21. **Database and evidence storage.** The SQLite schema, consistency,
    indexes, history, superseded results, partial writes, corruption,
    scale.
22. **Distributed volunteer computing.** `docs/multiuser.md`: hostile
    clients, collusion, fabricated or omitted detections, audits,
    duplicates, verification, trust.
23. **Testing and regression coverage.** Which failures could pass CI now;
    adversarial, property-based, synthetic, cross-platform and whole-
    pipeline tests.
24. **Large-scale survey strategy.** Choosing targets, sessions and blocks;
    completeness and bias; candidate priority; the resources the wider
    archive needs.

## The status review before the audits (19 November 2026)

| Finding | Verdict |
|---|---|
| The README is behind the research (version 0.1, step 12 not run) | **built**: README brought to report 1.3, step 12's result and the dependence on the cut |
| The evidence package predates step 12 | **built**: the package now takes data/step12 (its choices, deviations and saved archive replies) and makes the operating-point record again. Built afresh at c35afe3 (3,181 records and the store, 238 MB) and reproduced from a clean checkout at that commit: 8 table commands, 70 pages and records the same, none different (docs/releasing.md) |
| Nobody else has reproduced the tables | **not done**: needs a second person; stays on docs/releasing.md as the step before the DOI is announced |
| No formal release (tag, GitHub release, Zenodo) | **not done**: waits for the Zenodo account (put off by Ryan on 19 Nov), so that the release is archived when it is made |

## 1. Scientific methodology: done, 19 November 2026

**Verdict:** a credible foundation; the results do not establish a general
sensitivity ratio over turboSETI, and the false-candidate control is not a
calibrated false-alarm probability.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F1: the recovery ratio depends on the cut (2019: ×9.7 at 30 each, ×4.9 at 10, ×2.95 at the lowest cuts whose rate is at most 0.1, 8 and 5) | high | **built.** Checked against the block records: 5,049 against 1,714 and 4,702 against 952, as stated. `tools/operating_points.py` gives every session's recovery at every tested cut and three operating points; the report (1.3) has the table and states no single ratio. The paired difference in share is the steadier measure: it grows as the cuts fall (+0.31 to +0.47 in 2019) while the ratio falls. |
| F2: the 19 wrong-cadence choices are a control rate, not a calibrated false-alarm probability; their looks are put in ON, OFF order, not time order | high | **built in part.** Confirmed in code (`matched.py`, the order of a choice's looks is ON, OFF pairs). The report's method now says what the rate is and is not. Measuring how well it predicts false candidates in real cadences is new work: **planned** in audit 4. |
| F3: the frozen recovery criterion compares Wilson intervals, treating signals as independent | high | **built in part.** The frozen criterion stays as frozen. The paired difference with a bootstrap over blocks, and over runs of 4 and 16 adjacent blocks, is now given for every session and operating point: runs of 4 barely widen it (2019 at 30: 0.302 to 0.311 either way). Runs of 16 leave only 4 to 8 groups and are kept in the record, not the report. Correlation across larger frequency regions and between sessions: **planned** in audit 8. |
| F4: the quiet 2019 band does not resolve the crowded 2016 failure | high | **built**: already stated; the summary, the 2019 section and the limits say it again. A crowded session, fixed in advance, is the test still needed: **planned** in audit 5. |
| F5: planted signals are scaled to each look's measured noise, a controlled signal-to-noise experiment, not a fixed received flux | medium | **built in part.** Confirmed in `matched.plant`. The report's method now says so. A separate fixed-flux experiment: **planned** in audit 2. |
| F6: the 2019 selection rule was revised once after an empty metadata search, and the gate uses this project's own synthetic recovery | medium | **built**: already documented (comparable.md step 12); the report's 2019 section says it. Checked: the choice was written at 03:02, the config frozen at 03:07 and the sweep started at 03:18 UTC on 19 Nov, so no spectrum of the session was read before the freeze. |
| This search's candidates and turboSETI's are built differently (a hit at the cut in one ON look and the track in the others, against a hit in each), so whole pipelines are compared, not detectors | medium | **built in part**: the report's method says so. A common event-judging control on each pipeline's hits: **planned** in audit 3 (BLISS's hybrid already does this for BLISS). |
| Step 12 "every criterion holds" says more than its false-rate intervals do | — | **built**: the report now says every criterion was met at its point estimate, with the false-rate intervals reaching above the limit. |

Commit: see `git log -- docs/audits.md`.

### 1, re-audited at 21a919e, 19 November 2026

The first round's findings stood as: F1 addressed; F2, F3 and F5 in part
(their remaining work is the planned experiments above); F4 acknowledged;
F6 satisfactory for its scope. Three new findings, each checked before
anything was built:

| Finding | Severity | Verdict and what was done |
|---|---|---|
| R1: the false rates are weighted by each class's share of the session, the recovery counts and paired differences are not, though the 2017 sample is 61 crowded of 121 against 61 of 308 in the session (2016: 61 of 121 against 184 of 304) | high | **built.** Confirmed in `matched_tables.py` and `tools/operating_points.py`. Every operating point now has the recovery and the paired difference weighted to the session (each class's share found, weighted by its share of the session's blocks; a bootstrap over blocks within each class), beside the sample's. The effect is at most 0.009 in the difference (2017 at 30 each: +0.306 in the sample, +0.309 weighted; 2016: +0.294, +0.290; 2019: the sample is the session). The report (1.4) gives both and says no conclusion rests on the sampling. |
| R2: the runs of 4 and 16 were of measured blocks sorted by frequency, not consecutive blocks of the session, so they skipped unmeasured blocks | medium | **built.** Confirmed: the old grouping took the sorted sample four at a time. The windows are now of consecutive block numbers of the session, gaps kept (2017: 64 windows of 4, 20 of 16; 2016: 68 and 19; 2019: 16 and 4). An interval from fewer than 20 windows is marked in the record and left out of the report. The report now says this tests correlation between neighbouring blocks only, not robustness to frequency correlation in general. |
| R3: the matched cut had two definitions (step 4's: the rate within the target at every higher cut; the new script's: the lowest single passing cut) | medium | **built.** The script now uses `matched_tables._matched_cut`, and the operating point is named "matched (step 4's rule)". No published cut changes: the two rules gave the same cuts on all three sessions. |
| The method said 121 blocks per session and did not say the weighting is of the false rates only | low | **built**: the method gives each session's blocks (121, 121, 64) from the records and says which estimates are weighted. |
| Focused tests for the calculations | — | **built**: `tests/test_operating_points.py` (the weighting against the sample, an absent class, windows by block number with gaps, few windows marked, the interval around the estimate). |

Effect on the conclusions: none. The frozen verdicts are unchanged; the
weighted and window estimates agree with the sample's to within 0.009.

## 2. Signal injection accuracy: 19 November 2026

**Verdict:** no error that makes the planted-signal results unusable; the
planting is a controlled signal-to-noise experiment in real spectra, not
yet a validated model of what the telescope records from a transmitter.
Every finding was checked in the code first; all seven stand.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| SI-01: power is added to the finished spectra, so there is no signal-noise cross term from squaring signal plus noise | high | **built.** Confirmed in `measure.plant`. `tools/injection_checks.py voltage`: the same synthetic noise voltages (complex Gaussian, 51 FFTs a spectrum, as Green Bank's finest product) and the same 110-signal grid made three ways, power at 32 sub-steps (as in use), power at 51, and the tone added to the voltages before squaring; both pipelines, three-look recovery at SNR 10 and 30, 8 blocks of 1,048,576 channels. Result: power at 32 sub-steps this search 580 and 305, turboSETI 389 and 212 of 880 (SNR 10 and 30); at 51 the same; in the voltages this search 581 and 307, turboSETI 391 and 213 of 880. The cross term moves no pipeline's recovery by more than 2 of 880, and not one more than the other. |
| SI-02: signals are planted after the DC bin is blanked, so one crossing it keeps power a real one would lose | high (for DC claims) | **built.** Confirmed: `seti.blank_dc` runs when a slice is read, `matched.plant` after. Of the finished experiments' planted signals, **2 of 13,310 (2017), 4 of 13,310 (2016) and 2 of 7,040 (2019) cross a DC bin in any ON look** (`injection_checks.py dc`, census), so the order cannot have moved those results. The same tool plants signals made to cross the DC bin both ways (before blanking, as the sky would; after, as in use), both pipelines: planted then blanked this search 70 and 37, turboSETI 52 and 26 of 96; blanked then planted this search 71 and 38, turboSETI 52 and 28 of 96. A real signal on the DC bin loses up to 2 of 96 more than a planted one; with 8 such signals in all the finished experiments, nothing there moves. docs/seti.md's 20 signals "near the DC bin" are near it, not across it. |
| SI-03: the setigen comparison used setigen's default truncation (sidelobes cut at the first zero) against our 4 channels of sidelobes | medium | **built.** Confirmed (`sinc2_f_profile` defaults to `trunc=True`). `measure.py setigen` now runs both: untruncated, the profiles correlate at 0.998 to 0.9999 and **the 8.5% power gap is gone** (ours/setigen 0.980, ours/h 0.980: the gap was the truncation). Truncated stays as the control. Our planting carries 98% of h (the tails beyond 4 channels are dropped): both pipelines get the same spectra, so it weakens every signal by 2% alike. |
| SI-04: 32 sub-steps a spectrum against the spectrometer's 51 FFTs; the profile differs at high drift | medium | **built.** `tests/test_injection.py` checks power and convergence at 32, 51 and 128 against 256. `injection_checks.py substeps` gives the profile differences by drift and start, and the detector's S/N on the planted track near the cut at each: at 32 against 256 the largest single-channel difference is 6.7% of the peak (at 4 Hz/s), the power the same to six figures, and the detector's S/N on the track identical at every count wherever it found the signal. The production count is not changed. |
| SI-05: a fixed S_in in each ON look is not a fixed received flux | medium | **built.** Already stated in the report (1.3). `injection_checks.py flux`: 8 blocks of the 2017 session read again and planted both ways with their own recorded signals, both pipelines, and the spread of the looks' noise against each other: the three ON looks' noise is within 2.1% and 2.5% of their mean (5th to 95th percentile), and recovery is fixed S_in this search 593 and 305, turboSETI 119 and 29 of 880, fixed flux this search 594 and 307, turboSETI 118 and 29 of 880. |
| SI-06: flux in Jy Hz uses an SEFD of 10 Jy measured for L and S band, also on the C-band session | medium | **built.** The results pages' column now reads "Jy Hz (nominal: SEFD 10 Jy assumed)"; the report gives no flux. A C-band SEFD would need a calibrator observation at C band: **planned** in audit 13. |
| SI-07: the grid keeps planted signals apart, so crowding and confusion between signals are not tested | medium | **planned** in audit 6 (the planted signals still sit in real interference; `measure.py pairs` covers close pairs). |
| The tests check the planting only through the detector | — | **built**: `tests/test_injection.py` checks the planting itself (power, convergence, drift direction with the band running down, what blanking does to a signal on the DC bin). A voltage reference, constant-flux and crowding tests follow the measurements above. |

Effect on the conclusions: none of the four checks moves either
pipeline's recovery by more than 2 signals in 96 to 880, nor one pipeline
against the other. The planted signals' results stand as a measure of
recovery at a controlled signal-to-noise; what remains for physical
sensitivity is a calibrated SEFD at C band (audit 13) and confusion
between signals (audit 6).

### 2, re-audited at 782bf3c, 20 November 2026

The first round's work stood (SI-03 resolved, SI-06 labelled, the rest
addressed with limits). Six new points, each checked before building:

| Finding | Severity | Verdict and what was done |
|---|---|---|
| C1: the sub-step profile test started its track at channel 200 of 600, so at 2 and 4 Hz/s the signal ran off the array | high | **built.** Confirmed (a positive drift runs to lower channels; at 4 Hz/s the track moves 392 channels). The test now uses 2,048 channels with the track centred, refuses if any of it or its sidelobes would leave, and checks no power is lost at the edge. The worst single-channel difference, 32 against 256 sub-steps, is **6.72% of the peak at 4 Hz/s, as before**: the edge had cut both alike. The detector's S/N part now plants near the cut at every drift (S_in 12, 20 and 40 at 1, 2 and 4 Hz/s, found in 6, 10 and 11 of 20 trials): 32 against 256 sub-steps differs by at most 0.01 in S/N. |
| C2: equal totals do not show the same signals were found | high | **built; reruns running.** `Judge.judge` had the per-signal results and the records kept only totals. Every comparison is now paired: both found, first only, second only, neither, for each pipeline and cut, overall and by strength and drift (`injection_checks.paired`, tested in `tests/test_injection_checks.py`, including equal totals made of different signals). The voltage, DC and constant-power experiments are run again to record it. |
| C3: the voltage model has one polarization; Stokes I sums two | medium | **built; running.** The voltage experiment now also runs with two polarizations summed, the tone's power split equally between them with independent phases (an unpolarized or circular signal), its own noise and both pipelines. Recorded as what it is: a simplified noise model, no polyphase filterbank, no 8-bit requantization, a flat receiver response. |
| C4: "fixed flux" is constant injected power in uncalibrated units, on the first four blocks of each class | medium | **built; running.** Renamed throughout (`injection_checks.py power`, `injection_power.json`, "one injected power in all three ON looks"); the blocks are now four crowded and four clean drawn at random (seed 12). |
| The DC census assumed the coarse channel's size and the DC bin's place | low | **built.** The census now reads each session's DC bins from its own header (fch1, foff, the HDF5 chunk) and each signal's frequency through each ON look from its record, a channel either side: **2, 4 and 2 signals, as before**. |
| The macOS CI job was cancelled before it ran | — | **done**: rerun requested (`gh run rerun --failed`). |

## 3. turboSETI comparison fairness: 20 November 2026

**Verdict:** a fair comparison of two whole pipelines on the same data and
signals; not yet a controlled comparison of the detectors. Each finding
was checked against turboSETI 2.3.2's own source as installed here.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F3-01: turboSETI never searches the zero-drift trial | high | **confirmed; measurement queued.** `FindDoppler` defaults to `min_drift=1e-5` and both its search loops test `abs(drift_rate) > fd.min_drift`; it also refuses a negative `min_drift` (its line 151), so the trial cannot be switched on from the call. `check_zero_drift` in the event stage cannot bring back hits never found. turbo_curves.py and turbo_events.py said zero drift was kept: corrected. `tools/turbo_diag.py` runs a variant with `min_drift` set to -1 on the object after it is made; `tools/turbo_checks.py blocks` compares it with the published run, paired, by drift. |
| F3-02: the OFF vetoes differ (this search's at S/N 6 along the track and shadow hits from 5; turboSETI's from its hits over the cut in a frequency window), so the false-candidate curves compare cadence tests as well as detectors | high | **built; queued.** The crossed experiment on 16 real blocks (8 of 2017, 8 of 2016, crowded and clean at random): turboSETI's hits through this search's cadence test (its hits from SNR 5 as shadow hits), and this search's hits through turboSETI's event stage (written as turboSETI writes its own, the top-hit window as freq_start/freq_end), beside both as published; paired, signal by signal. |
| F3-03: turboSETI's event table can drop a look's row when two looks' hits share a TopHitNum, and recovery is credited from its event and its hit tables together | medium | **built; queued.** For each signal credited, whether its event has a row in each ON look and whether the hit matched in each hit table is the event's own (the same TopHitNum in that look). |
| F3-04: where turboSETI loses signals | high | **built; queued.** The first stage lost: no hit at SNR 5; another hit in its top-hit window (2 * ceil(max drift / drift step) channels, about 2.3 kHz here, confirmed in `tophitsearch`); found at SNR 5 but measured outside the tolerances; a matching hit only under the cut; vetoed by an OFF hit in the window; not associated; a false association; by class, drift and S_in. |
| Searching once at the lowest cut and cutting the tables is the same as searching at each cut | — | **built; queued.** turboSETI's search at SNR 30 itself against the SNR 5 search cut to > 30: hits and event rows compared. |
| The frequency reference correction | — | **built and measured** (`turbo_checks.py reference`, 102 strong synthetic tones over -4 to +4 Hz/s and six places within a channel). turboSETI finds every one, but at fast drifts reports the frequency up to 36 Hz from where the comparison matches it (the first spectrum's middle) and the drift up to 0.23 Hz/s off: the published +-6 Hz, +-0.05 Hz/s credit **5 of 60 at 2 to 4 Hz/s and 15 of 24 at 1 to 2 Hz/s**, all at 0.5 Hz/s and under; matching along the track instead credits 7 and 19. So the tolerances are part of why turboSETI finds little at fast drifts in the comparison. The block experiment scores both pipelines also with tolerances that scale with drift, the same for each (+-max(6 Hz, 10 s x drift), +-max(0.05, 0.08 x drift)), beside the published ones. |

On one block (2017, a smoke run before the queue), at SNR 10 of 110
signals: this search as published 75, turboSETI 17; turboSETI's hits
through this search's test 19, this search's hits through turboSETI's test
48; the zero-drift trial changed nothing; with the scaled tolerances this
search 82, turboSETI 18. turboSETI's losses there: 82 with no hit at SNR 5
within its window, 8 under the cut, 3 found but measured outside the
tolerances. None of turboSETI's credited events had a row in each ON look,
but where a row was there it was the hit the tables matched. Searching at
30 gave the same hits as the cut tables. These are one block's numbers;
the 16-block results follow.

### 3, re-audited at 03f5836, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| This search's hits written for turboSETI's event stage were numbered strongest first; turboSETI numbers its own in channel order, and find_events deduplicates by that number | high | **built.** Confirmed (`tophitsearch` walks the channels in order). Now numbered in channel order (`turbo_checks.turbo_order`, tested). It mattered: on the smoke block this search's hits through turboSETI's test found **67** at SNR 10 numbered by channel against **48** by SNR; the strongest-first numbering is kept as a measurement of how much find_events' deduplication depends on numbering alone (20 signals on that block). |
| (found here) Event rows were grouped by TopHitNum, not by the event | high | **built.** `matched._turbo_kept` groups by `hit_id`, which in the published adapter is find_events' Hit_ID; the diagnostic had put TopHitNum there. Now Hit_ID as `hit_id`, TopHitNum as `top_hit_num`. |
| The crossed pipelines had no false-candidate control, and equal cuts are not matched operating points across SNR scales | high | **built.** All four detector and cadence-test pairs now run the 19 wrong choices on the unplanted blocks at a grid of cuts (5 to 100), distinct candidates by shared hits as matched.py counts them; each pair's matched cut by step 4's rule on these blocks, by session, and its recovery there. Eight blocks a session: exploratory. |
| The frequency and drift discrepancy | high | **built**: measured on synthetic tones (above); the mechanism read from turboSETI's code (drift blocks rolled by whole channels, a Taylor tree of one channel a spectrum, no sum over a smeared signal's channels), stated as an inference; the blocks score both pipelines also with drift-scaled tolerances. |
| Event members: a missing row was counted as verified | medium | **built.** Per ON look: verified, disagrees or unknown, within the event the signal matches best (rows grouped by Hit_ID). Smoke block: 19 looks verified, 0 disagreeing, 32 unknown. |
| A hit in the top-hit window does not show suppression | medium | **built in part**: renamed "suppression suspected, not shown". Showing it would need turboSETI's rejected candidates, which it does not output. |
| Block results reused whatever code made them | medium | **built**: each block's record holds a fingerprint of the code (the tools and the modules they use) and is made again when it differs. |
| Offline tests | medium | **built**: `tests/test_turbo_checks.py` (numbering order, verified, disagreeing and unknown members, each loss stage, the scaled tolerances put back). |

## 4. False-positive methodology: 20 November 2026

**Verdict:** the false-candidate count is a reproducible stress test of
many wrong ON/OFF assignments, not a calibrated false-alarm rate for real
cadences. Every finding was checked against the code and the records.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F4-01: the rate is distinct candidates over all 19 wrong choices, not one assignment | high | **built** (`tools/false_checks.py assignments`, from the records, unweighted by class). One wrong choice yields about a nineteenth of the union: 2017 this search at 30, 0.0091 a block for one choice against 0.1736 over 19 (x19.0); 2016 at 30, 1.7468 against 32.5455 (x18.63); turboSETI x19 throughout. Almost every candidate appears in one wrong choice only (98.4% in 2016 at 30), so the union is the sum of 19 nearly separate draws. The published rate keeps its name and definition; the report now calls it what it is. |
| F4-02: the wrong choices are not exchangeable with the real one, and a choice's looks are put in ON, OFF pairs, not time order | high | **built in part.** Confirmed in `matched.our_events`. This search's verdict reads only each look's ON flag, and its projections use each look's own start time, so the order should matter little to it; measured rather than assumed: `false_checks.py chronological` judges every wrong choice of 16 blocks in time order beside the published order (queued). turboSETI's event stage needs ON and OFF to alternate, so it is not run in time order. Exchangeability itself cannot be shown from these six looks: **planned** (control B below). |
| F4-03: the combined interval drops a class with no candidates unless every class has none | high | **built** (`false_checks.py interval`). Confirmed in `matched_tables._rate`. Mended: a class with none drawn from the posterior of a Poisson rate over its blocks, flat prior (Gamma(1, 1/blocks), whose 97.5% point is the exact upper limit `_rate` already gives the class). Coverage simulation, 1,000 trials each: 2019 layout: 61 clean, 3 crowded; clean 0.01, crowded 0.3: published 0.992, mended 0.989; 2019 layout: clean 0.03, crowded 1.0: published 0.851, mended 0.982; 2017 layout: 60 clean, 61 crowded; clean 0.005, crowded 0.3: published 0.917, mended 0.983; 2017 layout: clean 0.05, crowded 0.5: published 0.912, mended 0.922. Mended intervals: 2019 this search at 8, [0.0014, 0.0801] (published [0.0, 0.0469]); at 30, [0.0034, 0.0848] (published [0.0, 0.1153]); 2017 at 30, [0.0309, 0.1477] (published [0.0227, 0.13]), turboSETI [0.0052, 0.1499]. With three crowded blocks (2019) no block bootstrap describes the crowded tail; the simulation shows how far that costs. `_rate` and the frozen verdicts are unchanged. |
| F4-04: what counts as one false signal | high | **built** (`false_checks.py grouping`). By frequency and drift within the tolerances, the groups are almost those of shared hits (2016 this search at 30: 3938 by shared hits, 3937 by frequency and drift, none split); within 3 kHz they merge heavily (1235 groups, 3261 shared-hit groups joined with others). So the published count is stable to a physical-looking rule and the 3 kHz count is a different unit; which is one transmitter is not shown. |
| F4-05: concentrated interference and correlated blocks | high | **built in part** (`false_checks.py windows`): the false rate's interval with windows of 4 and 16 consecutive blocks resampled within each class; 2016 this search at 30: by block [14.6185, 69.675], by 4 [11.4274, 70.4456], by 16 [2.7473, 80.3749]. A tail absent from a session cannot be drawn from it; the three sessions' rates (0.068, 39.1 and 0 at 30) are the measure of session-to-session spread so far: **planned**, more sessions (audit 24). |
| F4-06: the matched cuts are chosen on the blocks they are judged on | high | **stated; in part already held out.** The frozen cut of steps 10 and 12, 30, was step 4's matched cut on the 2017 session, then tested on 2016 (failed) and 2019 (held): that is the out-of-sample test of one threshold. Choosing thresholds on some sessions and testing them on others more widely: **planned** (control C, audit 24). |
| F4-07: cadence candidates before vetting are not vetted false alarms | medium | **built**: the report names the count a cadence-candidate yield before vetting. Measuring the yield after vetting, and how often vetting rejects planted signals: **planned** in audits 5 and 12. |
| Control B: real, time-ordered negative-control cadences from other directions | — | **planned**: a new experiment, sessions chosen beforehand as steps 10 and 12 were. |

### 4, re-audited at d441e00, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| R4-01: the time-order test called a candidate's ON looks by position (`matched._our_kept` took even places as ON), so with ON looks at odd places their members and tracks were dropped and shared-hit identity broke | high | **built.** Confirmed: `_our_kept` read `p % 2 == 0` twice. It now reads each look's own ON flag. For the published orderings the flag is set from the position (`Look.on = position % 2 == 0`), so nothing published changes: tested (`tests/test_false_checks.py`, alternating looks give the members they gave before, ON looks at odd places now give theirs) and the step 10 regression, two published blocks measured again, is identical in every field. The time-order test runs after this fix (queued), and compares the candidates of every choice by their member hits as well as their numbers, by choice and by class. |
| R4-02: the replacement interval mixes a bootstrap with a posterior; its docstring still said Jeffreys; it is not shown to be a 95% interval, and its lower end above zero says nothing | high | **built.** The wording fixed; it is labelled a hybrid, exploratory, neither a confidence nor a credible interval. A third, conservative interval added: each class's interval the wider of its bootstrap and the exact Poisson interval of its total (0 when none), weighted and added end to end. Coverage, 1,000 trials each, now with correlated, overdispersed crowded blocks too: 2019 layout: 61 clean, 3 crowded; clean 0.01, crowded 0.3: published 0.991, hybrid 0.989, conservative 0.996; 2019 layout: clean 0.03, crowded 1.0: published 0.833, hybrid 0.974, conservative 0.996; 2017 layout: 60 clean, 61 crowded; clean 0.005, crowded 0.3: published 0.905, hybrid 0.976, conservative 0.994; 2017 layout: clean 0.05, crowded 0.5: published 0.922, hybrid 0.927, conservative 1.0; 2017 layout, crowded correlated in runs of 4: clean 0.005, crowded 0.3: published 0.741, hybrid 0.872, conservative 0.932; 2016 layout, crowded correlated in runs of 8: clean 0.5, crowded 60: published 0.416, hybrid 0.413, conservative 0.411. So the conservative interval holds in every independent or mildly correlated case, and **no block-level interval holds when heavy interference comes in correlated runs** (the 2016-like case, about 41% for all three): 2016's published interval should be read as far too narrow. On the records, conservative: 2019 this search at 30 [0.0, 0.1153] (published [0.0, 0.1153]), at 8 [0.0, 0.1447]; 2017 at 30 [0.0227, 0.1759], turboSETI [0.0, 0.1792]. No session's rate is shown under 0.1 by an interval that holds; none of this replaces the published intervals or the frozen verdicts. |
| More tests | — | **built**: the union and recurrence of the 19 choices, windows by block number, single-link grouping within reach, the conservative interval at zero, the kept candidates with ON looks at odd places. |
| The windows' uneven groups | medium | **built in part**: the number of windows by class is recorded and fewer than 20 marked; the coverage case "correlated in runs of 4" above is the validation of block against window resampling that the data allow. |
| The new records in the evidence package | — | **planned at the next build**: data/analysis is in the package and its records carry the commit that made them. |
| Independent negative-control cadences | — | **planned** (control B), as before: the rearranged looks of one cadence are not a substitute. |

### 4, re-audited again at 4f3ff26, 20 November 2026

R4-01 accepted as fixed. Remaining points:

| Finding | Severity | Verdict and what was done |
|---|---|---|
| R4-03: "wider than a joint 95% interval by construction" is not guaranteed: marginal intervals added are not a joint 95% interval, and the exact Poisson part assumes a count model correlated interference breaks | medium | **built**: the conservative interval is now described as an exploratory envelope whose coverage depends on the interference and is measured, not assumed; the simulations above are that measurement. |
| An end-to-end test of the time-order control | — | **built**: `tests/test_false_checks.py` makes a synthetic cadence with a tone in looks 1, 3 and 5 only and runs this search and its cadence test both ways: called ON as (1, 3, 5), the published ON, OFF pairs and time order keep the same one candidate with the same member hits (in looks 1, 3 and 5); called ON as (0, 2, 4), neither keeps it. |
| The DOT diagnostic paired stamps by positions 0, 2 and 4 | low | **built**: `onoff.judge` now pairs each ON look with the OFF look just after it by the looks' own flags; in the published ON, OFF pairs that selects exactly positions 0, 2 and 4, as before. It is recorded, not part of the verdict. |
| The new records in the evidence package | — | **planned**: built and reproduced when the queued runs finish. |
| Independent negative controls | — | **planned**, a new experiment. |

## 5. The 2016 interference failure: 20 November 2026

**Verdict:** the failure is real and stays a failure. Its shape is now
measured: almost all of it is candidates seeded by one ON look's hit, the
other two ON looks only measured along the track, in blocks crowded enough
that their hit lists were cut. Every finding was checked against the code
and the records (`tools/rfi2016.py records`; the blocks read again are queued).

| Finding | Severity | Verdict and what was done |
|---|---|---|
| A5-01: "no candidate left unexplained" is not a selective filter: 1,273 of 3,729 recovered planted signals (34%) were marked interference, 913 by the band list alone, and only 39 of 3,938 false candidates were shown to be interference, the rest indicated | high | **correct; stated.** The figures are docs/seti.md's own. The checks keep shown, indicated and unexplained apart; what was missing is the reading: an indication is not an identified transmitter, and the checks' cost to real signals is a third of them at 2016's band list. Measuring each verdict's yield and cost separately is **planned** in audit 12. |
| A5-02: the cadence test lets one ON hit and two measured tracks make a candidate, which is where crowded interference gets through | high | **confirmed and measured.** At SNR 30, of 3,938 false candidates **3409 are one hit and two tracks**, 441 two hits and a track, 88 three hits. Requiring more ON hits, from the records (false rate a block; planted signals found): 2016 at 30, one hit 39.0608, 4337; two 5.2489, 4068; three 0.8732, 3757. 2017 at 30: 0.0682 / 4520, 0.013 / 4268, 0.0 / 4031. 2019 at 30, found 2404, 2291, 2192 (no false candidates). So two ON hits would cut 2016's rate by seven-eighths for about 6% of the planted signals, three hits by 98% for 11 to 13%, still above 0.1 in 2016. Chosen on the failure it explains, so not adopted: it is a rule for a new detector version, tested on sessions chosen beforehand. |
| A5-03: masking the listed bands would not pass 2016 | high | **confirmed and measured** (rate a block at 30): in listed bands 38.5714; in the GPS L3 annotation 0.2679 (27, block 119); elsewhere in crowded blocks 0.1488 (15); within 10 MHz of a band 0.0595 (6); clean 0.0132 (2). Outside the bands and L3 together, 0.22 a block: still above 0.1. |
| A5-04: GPS L3 (1,381.05 MHz) is missing from the band list, and block 119's cluster at 1,378.4 to 1,378.6 MHz lies in 1,376 to 1,386 MHz | medium | **built**: `vetting.KNOWN_RFI`, an annotation used to describe candidates, never a mask or a verdict. Its source is NRAO's VLA and VLBA RFI tables (GPS L3, intermittent); no Green Bank table listing it was found, so at the GBT it is a likely source, not a measured one. |
| A5-05: the matched runs vetted every session's candidates at KIC 8462852's place on the sky | medium | **built.** Confirmed: `matched.run` called `measure.vet_hook()` without a target. It now reads the session's ON target from the store (`matched.session_target`, tested with two targets). The supplementary checks already recorded for HIP 17147 and NGC 6946 were made with KIC 8462852's coordinates; check 5 (the expected drift from the Earth's motion) is informational, not a rejection, and the counts and frozen verdicts never used them. |
| A5-06: the hit cap | medium | **measured in part; running.** 3899 of 3,938 false candidates at 30 lie in blocks where some look's hit list stopped at the cap, so OFF hits that would veto them may be missing. `rfi2016.py reread` searches the seven blocks holding 3654 of them again with the cap at 20,000 and compares their false candidates by identity. Not called the cause before that. |
| The seven blocks, the OFF threshold, related OFF hits | — | **running** (`rfi2016.py reread`): the seven blocks (195, 59, 171, 53, 60, 54, 55) and eight others of 2016 and eight of 2017 read again: OFF_MAX at 5, 6, 7, 8 and 10 against both the false candidates and the planted signals, and for each candidate of the seven blocks the hits within 3 kHz in its OFF looks. |
| A detector v2 validated on new sessions chosen beforehand | — | **planned**: whatever these suggest is a new version with its own frozen test, including crowded L-band data. |

### 5, re-audited at f3f50bb, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| The planted signals kept under a stricter ON-hit rule were counted from the event matching most of a signal's ON hits, which need not be the event that recovers it in all three looks | high | **confirmed; corrected.** `matched._status` credits recovery to any event matching in all three ON looks (tracks included) but records `members` for the event with most matching hits. So the records give an upper bound, now named so (`found_at_most`). For **three** ON hits the bound is exact: it equals the records' own `three_hits` status (an event whose three ON members all match): 4,031 (2017), 3,757 (2016) and 2,192 (2019) at SNR 30. For **two**, the exact count comes from the blocks read again, by the event that recovers each signal (`rfi2016.recovered_with`: the same event must match in all three looks and hold at least two ON hits; tested with two competing events, the one with most hits not the one that recovers). Until then 2016's 4,068 at two hits is at most. |
| The raised-cap comparison matched candidates by hit numbers | medium | **confirmed, and worse:** hit numbers index each search's own hit list, so they cannot be compared between a capped and an uncapped search at all. Candidates are now matched by frequency and drift within the tolerances: kept, kept with other member hits, gone, new (`rfi2016.match_groups`, tested). |
| The blocks read again were reused whatever code made them | medium | **built**: each holds a fingerprint of the code and is made again when it differs; at OFF_MAX 6 each block must give its record's own false and found counts (`reproduces_record`), and the run says whether all did. |
| The record took its session from the block choice, which does not hold it | low | **built**: from `matched_tables.load`. |
| Tests for the analysis | — | **built**: `tests/test_rfi2016.py`. |

## 7. BLISS comparison: 20 November 2026

**Verdict:** the comparison stands as measured: BLISS's own event stage
reaches no cut at 0.1 false a block on the 2017 session, and its hits under
this search's cadence test recover 4,048 planted signals against this
search's 4,520. Two points were defects and are fixed (the pins were
recorded, not enforced; the loss table claimed causes). The two-ON rule was
measured and does not explain BLISS's failure. Checked against the upstream
event stage as ported (`tools/bliss/bliss_events.py`), the records and the
adapter.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| BL-01: BLISS keeps an event with hits in two ON looks; this search's recovery needs three | high | **confirmed and measured** (`tools/bliss_checks.py events`, from the records; members are one hit per ON look). False a block, all / exactly two ON / three ON: at 30, 19.70 / 12.71 / 7.28; at 50, 14.99 / 9.25 / 5.94; at 100, 4.54 / 3.02 / 1.61. Counting only three-ON events, BLISS still reaches no cut near 0.1, so the two-ON rule is not why it fails. Planted signals are credited only by three-ON events already, so recovery is the same either way. The published comparison is unchanged. |
| BL-02: the port was checked against upstream without the production preprocessing | high | **confirmed as a limit; stated.** `port_vs_bliss.py` compares every event's members on the hits it gives both, on CPU segments without normalization, equalization, sigma clipping or the hit filter, and with other kurtosis settings. It shows the event code agrees on the hits supplied, not that the whole production chain does. A run with the production steps on segments is **planned** (it needs the patched CPU build in BLISS's environment); whole crowded blocks do not fit upstream's event stage, which is said wherever the port is described. |
| BL-03: the pinned BLISS commit and response file were recorded but not enforced | high | **confirmed; built.** `matched.BLISS_PINS` (checkout 2b98afe, local change 6d80c82f, response file 143f61d1) is checked before any BLISS record is written (the comparison, the hybrid and the same-hit control); a run that differs is refused. `tools/bliss_checks.py pins`: all 242 recorded runs (121 blocks, plain and planted) match. |
| BL-04: the 2019 BLISS run was blocked by the adapter's 2017 layout, and any failure was recorded as not possible | high | **confirmed; built.** `tools/bliss/pad.py` pads any slice inside one coarse channel; it gives the same array as the published padding on the 2017 layout (`tests/test_bliss_pad.py`). It runs through `tools/bliss/run_general.py` with `SSY_BLISS_GENERAL=1`, whose hashes join the configuration, so the 2017 records keep theirs (checked). `step12_run.py` now records only an input the adapter does not take as not possible; any other failure is left not done and tried again. The 2019 BLISS run is a supplementary experiment for later; step 12's verdict is frozen. |
| BL-05: hit order: three shuffles, and the shuffle seed depends on the cut | medium | **confirmed; planned.** The seed is `[shuffle, cut]`, so orders differ between cuts. More orders on crowded blocks, with a seed fixed across cuts, are planned as a robustness check; the sorted order stays the reference. |
| BL-06: the same-hit control covered two blocks chosen for their false candidates | medium | **confirmed; running.** The control is queued on eight blocks chosen beforehand by seed 12 (49, 79, 131, 139, 166, 185, 221, 231), clean and crowded. The hybrid stays an exploratory combination. |
| BL-07: the BLISS loss table called its categories causes | medium | **confirmed; corrected.** The table and `_bliss_loss` now say first failure seen in the order checked, not a cause shown; the report's detector sentence likewise. |

### 7, re-audited at c6388b4, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| The regenerated BLISS page lost the hybrid (0 of 121 blocks) | high | **confirmed; fixed.** The hybrid's records carry the hash of an earlier `onoff.py`; 3ed45b4 changed only which looks the DOT score pairs. `matched.our_events` always lays the looks out ON, OFF, ON, OFF, ON, OFF, so both versions pick the same pairs. `tests/test_onoff_equivalent.py` runs both versions on all 20 choices at two cuts and finds every event identical; that hash is now accepted by name (`matched.ONOFF_EQUIVALENT`), not by dropping the check. The page is back to its earlier form (4,048 found, the same tables), the loss wording the only change. |
| Existing records were accepted without the pin check | medium | **built**: `bliss_done` counts a record only with the pinned checkout, local change and response file in both its runs (tested); all 121 records still count. |
| The general adapter wrote into the 2017 folder; a done status blocked a retry; failures classed by a text match | medium | **built**: its records go to `bliss_general/` and its status to its own file. Each failure is recorded with a kind (`matched.failure_kind`: incompatible input from the adapter's own refusals, a timeout, or a failure to run; tested); only an incompatible input is permanent, and step 12's runner calls BLISS not possible only when every block's record says so. |
| BL-01: the two-ON and three-ON rates do not add to the whole | low | **stated**: each is counted distinct by shared hits within its own events, so they are not a decomposition. |
| BL-02, BL-05, the 2019 BLISS run | — | **planned**, as above; BL-06's control is queued. |

## 8. Statistical analysis and uncertainty: 20 November 2026

**Verdict:** the recovery difference is large and holds under every
interval tried; what was overstated is precision, and for the operating
points, stability. All of it is from the records (`tools/statistical_checks.py`,
2,000 resamples, seed 8; tests in `tests/test_statistical_checks.py`).
Nothing changes a cut, a record or a frozen verdict.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| ST-01: Wilson's interval treats planted signals as independent | high | **confirmed and measured.** In simulation, with blocks sharing an effect Wilson's 95% interval holds the true share 36% of the time (12% with blocks correlated along frequency), the block-clustered interval 92%. On the sessions, this search's share at 30: 2017 Wilson 0.332 to 0.348, clustered 0.340 to 0.348; 2016 Wilson 0.318 to 0.334, clustered 0.309 to 0.332 (1.5 times as wide); 2019 0.330 to 0.353 against 0.338 to 0.345. The clustered figure is the class-weighted share, so it can be narrower where the classes differ. Wilson's intervals stay as descriptions of the sample, not of precision. |
| ST-02: the bootstraps say nothing about other sessions | high | **confirmed; stated.** Within-session intervals only. The paired difference at 30 is 0.309 (0.305 to 0.314) in 2017, 0.290 (0.279 to 0.301) in 2016 and 0.306 (0.302 to 0.311) in 2019: side by side, not pooled, and three sessions from one telescope give no between-session interval. Wider claims need sessions chosen beforehand (audit 24). |
| ST-03: the false-rate intervals fail under strong correlation | high | **confirmed** (audit 4's simulation: about 41% for every interval tried in the 2016-like case). Not repeated: those intervals are labelled as not holding 95% there. |
| ST-04: the matched cuts' own uncertainty is left out | high | **confirmed and measured.** Step 4's rule applied again to each resample of the 2017 blocks: this search's cut is 30 in 86% (50 in 11%, 100 in 2%, 20 in 1%); turboSETI's is 30 in only 54%, and 5 to 12 in 37%. The paired difference at the cuts chosen is 0.306 at the median but 0.048 to 0.328 over 95% of resamples: when turboSETI's cut falls low its recovery rises. So 2017's matched comparison is unstable for turboSETI, and the fixed cut of 30 tested on 2016 and 2019 is the confirmatory evidence. In 2016 neither pipeline reaches 0.1 in any resample (this search) or in 95% of them (turboSETI). In 2019 the rule picks 8 and 5 every time. This measures instability, not out-of-sample performance. |
| ST-05: false rates compared unpaired | medium | **built.** Paired by block, this search minus turboSETI at 30: 2017 +0.020 a block (−0.075 to +0.091, so no difference shown); 2016 +37.8 (13.0 to 67.7); 2019 0 (no false candidates in either). No ratio where a count is zero. |
| ST-06: windows of 4 and 16 blocks not justified | medium | **measured.** Correlation of the per-block recovery difference between blocks one apart: 0.16 (2017), 0.63 (2016), −0.02 (2019); in 2016 it stays 0.35 to 0.41 at 8 and 16 apart. Interval width with windows of 1 to 32 blocks: flat in 2017 (0.011 to 0.014), doubling in 2016 (0.020 to 0.042), flat in 2019 until too few windows remain (8 or fewer). So 2016's within-session intervals need the widest window, and at 32 blocks only 10 windows remain, too few to trust. |
| ST-07: multiplicity; ratios without intervals | medium | **built in part.** The ratio of signals found at 30, with a block-clustered interval: 10.2 (9.7 to 10.8) in 2017, 10.4 (9.6 to 11.3) in 2016, 9.7 (9.1 to 10.4) in 2019: a count ratio at these cuts, not a ratio of sensitivity. Labelling each reported comparison prespecified, supplementary or exploratory is **planned** with the report's next revision. |
| ST-08: recovery intervals' coverage untested | medium | **built.** Six simulated cases (300 experiments each): the block-clustered interval held the true difference 91% (independent signals), 92% (shared block effect), 95% (unequal class sampling), 93% (rare recoveries), 97% (each finding some the other misses) and **62% with blocks correlated along frequency**: blocks resampled singly do not cover that case, which is what the window resampling is for. Bias under 0.002 throughout. A test fails if the pairing is broken. |

### 8, re-audited at 8199c56, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| Wilson's interval was set beside a clustered one on another quantity (pooled against class-weighted) | high | **confirmed; fixed.** Both now on the sample's pooled share; the weighted share keeps its own clustered interval. This search's share at 30, Wilson against clustered: 2017 0.332 to 0.348 against 0.334 to 0.344 (0.6 as wide); 2016 0.318 to 0.334 against 0.316 to 0.336 (1.2 times); 2019 0.330 to 0.353 against 0.338 to 0.345 (0.33). The clustered interval comes out narrower where it does because each block holds the same planned grid of strengths and drifts, so block totals vary less than independent draws would; in 2016, where blocks differ most, it is wider. |
| The window bootstrap dropped the class weighting | high | **confirmed; fixed.** Windows are now drawn within each class and the difference weighted as the main estimate (tested: a case where pooled and weighted differ). The paired difference at 30 by window of 1, 4, 16 and 32 blocks: 2017 0.0092, 0.0083, 0.0073, 0.0086 wide; 2016 0.0227, 0.0281, 0.0345, 0.0402 (widening, the correlation found before); 2019 flat, with as few as 2 windows in its crowded class. |
| The window bootstrap's coverage was not tested | high | **built.** Simulated blocks correlated along frequency (AR(1), 120 blocks in two classes, 200 experiments each): at correlation 0.5, windows of 1, 4, 8 and 16 cover 88%, 91%, 90%, 85%; at 0.8, 65%, 80%, 82%, 80%; at 0.95, 34%, 46%, 54%, 60%. So windows of 4 to 8 blocks restore most of the coverage under moderate correlation, and nothing tried reaches 95% under strong correlation. 2016's neighbouring blocks correlate at 0.63, between the first two cases: its window intervals are the ones to quote, read as about 80 to 90% intervals. |
| 2019's false-rate difference shown as [0, 0] | medium | **confirmed; fixed.** With no false candidate in either it is now no interval and a note that it says nothing about a difference in the underlying rates (tested). |

## 9. Core narrowband detection algorithm: 20 November 2026

**Verdict:** four of the seven findings are confirmed with `searching.py`'s
own code (not a reimplementation), one is smaller than claimed, and none
changes the production search: it is frozen, and what these suggest goes
into a new detector version tested on sessions chosen beforehand. The
checks: `tools/detector_checks.py` (synthetic, run; blocks, queued) and the
diagnostic copy's two new switches (`tools/search_variants.py`
`refresh_reach`, `exact`; still identical to the search at their defaults,
tested); `tests/test_detector_checks.py` pins each behaviour down.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F9-01: after a pick, only line starts within the margin are summed again, so scores holding blanked power survive | high | **confirmed.** The re-sum reaches `most + wmax` either side; a blanked pixel in the last spectrum lies on lines of the opposite extreme drift starting up to `2 x most` away. With the search's own code and a full-reach re-sum beside it: a strong tone at +2 Hz/s leaves one extra pick at SNR 18.2, at −3.9 Hz/s one at 51.3, a wide tone one at 43.6; a pulse in one spectrum leaves none. So a strong signal can bring one stale hit beside it. Its effect on candidates is being measured on 12 blocks (2017 and 2016, chosen by seed 12): hits, false candidates and planted signals found at 30, as published against full reach. |
| F9-02: each width's noise is measured on a positive drift and used for both signs | high | **confirmed in the code; smaller than claimed in effect.** Measuring each width's noise on the negative drift as well (`searching.Plane` with its sample drift negated): on pure Gaussian noise the two differ block by block by a median of 3% (width 1) to 13% (width 27), and with a doubling step in the noise by about the same, 3% to 14%. So the difference seen is mostly the estimate's own scatter (F9-05), not direction; the twofold figure did not reappear with the search's own measurement. Real blocks are in the queued run. |
| F9-03: the hit list depends on the cut, since a shadow pick does not trigger the re-sum | high | **confirmed; already being measured.** This is `refresh_shadow` in the diagnostic copy (audit 6): the second lane is running it on four crowded 2016 blocks, with false candidates and planted signals found. matched.py's assumption that one search serves every cut holds for the hits at and over the search's cut, not for those under it. |
| F9-04: one non-finite sample ends the search | medium | **confirmed.** With one NaN in an unrelated channel the search returns no hits and the tone it found without it is lost, silently. No block of the three sessions lost every planted signal (the fewest found at 10: 17 in 2017, 5 in 2016, 67 in 2019), so no ON look of these runs was emptied this way; the queued run counts non-finite samples in its blocks. A check before the search belongs in the next version; the frozen search is not changed. |
| F9-05: the noise estimate scatters more at wide boxes | high | **confirmed.** On Gaussian noise, the measured spread over its expected value: standard deviation 3.6% at width 1, 5.0% at 4, 7.4% at 10, 11.7% at 27 (512 blocks each); 5th to 95th percentile 0.94 to 1.06 at width 1 and 0.80 to 1.18 at 27. A signal at the cut at fast drift is therefore over or under it by up to a fifth from block to block. |
| F9-06: the SNR is rounded before matched.py compares it with the cut | medium | **confirmed in the code.** A hit at 9.96 is shadow to the search but counts at 10 in matched.py. The queued run counts, per cut, the hits whose exact SNR is under it and rounded value at it. Records keep the rounded value only. |
| F9-07: the exhaustive drift search is costly | low | **noted.** The records time each stage per block (search, judging, planting); a stepped drift grid would be a new detector version with completeness measured again. |

### 9, re-audited at 8eed705, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| The direction test on real blocks left out the kurtosis flags the search measures its noise without | medium | **confirmed; fixed.** Each of the six looks is measured both ways with the flags the search makes from it (`searching.kurtosis` over `SK_FLAG`). |
| Blocks read again were not checked against their records | medium | **confirmed; fixed**, in these checks and the curved ones: the looks' start times must be the record's, or the block is refused. |
| The cache fingerprint left out code the checks use | medium | **confirmed; fixed**, in both: it now covers every module they call and what was read (the files and the block's channels). |
| F9-03 needs the search run at each cut, not the shadow-refresh stand-in | high | **agreed; built.** Each block is also searched at cut 8 (the lowest tested) and 30 and judged at that cut, beside the one search at 10 relabelled as the comparison does: hits differing, false candidates and planted signals found. At 10 the two are the same by construction. |

## 10. Curved Doppler search: 20 November 2026

**Verdict:** the two weaknesses in the matcher are real in the code, and
how much they matter is being measured; the two signals left untraced
between the curved runs are found. `curved_pass.py` is frozen (steps 10 and
12 fingerprint its matcher), so the checks run a diagnostic copy that keeps
every hypothesis (`tools/curved_checks.py`; deduplicated first-wins it gives
`second_pass` exactly, tested on a cadence with eight curved signals and all
20 choices). Nothing published changes.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| CD-01: the first hypothesis for a set of hits wins, before its OFF evidence is judged | high | **confirmed in the code; being measured.** The same three hits reached from another pair of ON looks give another fitted acceleration and other OFF predictions. On ten 2017 blocks read again (36, 128 and eight chosen by seed 12) the run counts sets of hits whose hypotheses disagree, and false candidates and planted signals found at 30 and 10⁻³ when any hypothesis being a candidate is enough. |
| CD-02: an OFF look that cannot be measured counts as clean | high | **confirmed in the code; being measured.** `off_max` starts at −∞ and an unmeasured look adds nothing, so a candidate with no OFF look measured passes. The run counts candidates with no OFF look measured and with some, and what not taking them would change. |
| CD-03: the pass needs hits in two ON looks to start | high | **confirmed; a limit by design.** A census of misses by stage and a one-hit start are **planned** as a new version with its own false-candidate control. |
| CD-04: 6,555 against 6,557, and the exploratory runs' checks | medium | **traced in part.** Signal by signal, the two are block 36's signal 61 and block 128's signal 62: both strength 400, drift +1.83 and −1.84 Hz/s, acceleration +3 and −3 ×10⁻⁴ Hz/s², each recovered in the recheck by two hits and a track and missed in the vetting run. The blocks run records every hypothesis near each. Fingerprints and completeness checks on the exploratory runs' records are **planned**; `run` and `tables` are fingerprinted functions of a frozen file, so this goes in a wrapper, not the file. |
| CD-05, CD-06: curvature and orbits covered only in part | high / medium | **agreed; stated.** Results are recovery over the tested acceleration range and orbital grid, not completeness for accelerating transmitters. A completeness map over drift, acceleration and strength, and eccentric orbits, are **planned**. |
| CD-07: the pass's extra false candidates are not general | high | **agreed.** Paired block-level intervals for the pass's increments use audit 8's tools; **planned** with the blocks run's results. |
| CD-08: no comparison with a truly curved search | medium | **planned**, on the same planted signals and controls. |

### 10, re-audited at 8b836f4, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| The OFF-coverage check asked only for one measured OFF look | medium | **agreed; built.** The run now compares requiring one, two and all three OFF looks measured, beside the published rule and any-hypothesis-a-candidate. |
| The wrong-choice tallies included the true choice | low | **confirmed; fixed.** The true choice's tallies are kept apart. |
| No end-to-end case of two fits from the same hits | medium | **built in part.** On a synthetic cadence with eight curved signals, the same three ON hits reached from two pairs of ON looks give two fitted accelerations (for example −7.58 and −7.81 ×10⁻⁴ Hz/s²) and different OFF measurements, and the published matcher keeps the first (tested). A case where the veto itself flips was not found on synthetic data; the blocks run counts such sets on real data. |
| The two signals are located, not explained | medium | **open**: the run records every hypothesis near each, in both blocks. |

## 11. ON/OFF cadence matching: 20 November 2026

**Verdict:** three mechanisms are confirmed with `onoff.py`'s own functions;
how much each matters on real data is measured in the queued blocks run
(`tools/detector_checks.py blocks`, which now also runs
`tools/onoff_checks.py`'s measurements on each block, so blocks are read
once). `onoff.py` is frozen; changes to the rules belong to a new version.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| A11-01: an OFF look that cannot be measured counts as clear | high | **confirmed in the code; being measured.** `best_track` gives nothing with fewer than 16 reference lines or no spread, and `judge` then sets no OFF evidence. The run counts candidates with an OFF look neither measured (projected or fixed) nor holding a hit, and with every OFF look so, on the wrong choices and the planted signals (`onoff_checks.unmeasured`, tested). The curved pass has the same gap (CD-02, audit 10). |
| A11-02: an ON look without a hit passes on the best of every place and drift in the tolerances | high | **confirmed; being measured.** At random places where nothing was planted, the run measures how often the other ON looks reach ON_MIN that way (each, both, and both with the OFF looks clear: a one-hit candidate), by drift band. On pure noise none of 60 places reached it, so what reaches it on real data is the data's, not the maximisation's alone. The 2016 cost of one hit and two tracks is audit 5's. |
| A11-03: the matching distance is not symmetric | medium | **confirmed.** It predicts and sets its tolerance from the first hit's drift, and pairs are made from the earlier look to the later. With `onoff.distance` itself, two hits 1,320 s apart at 3.4372 and 3.6141 Hz/s, the second exactly where the first predicts: 0.92 forward (a match), 2.36 backward (none) (tested). The run counts real hit pairs matching one way only. |
| A11-04: greedy grouping is not the best assignment | medium | **agreed; planned**: an exact assignment on ambiguous synthetic cadences beside it. |
| A11-05: an incomplete hit list does not stop a candidate | high | **confirmed; being measured** in audit 5's raised-cap reread (running). |
| A11-06: interference changing drift between looks escapes the OFF test | high | **agreed; planned**: injected interference that changes drift, with a wider occupancy check as a flag, not a veto. |
| A11-07: the OFF veto rate is measured at random places, not where candidates arise | medium | **agreed; planned**: null tracks matched to candidates' frequencies, drifts and crowding. |

### 11, re-audited at 529ebf4, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| The asymmetry count could never see a backward-only pair: `onoff._close` screens on the forward distance | high | **confirmed; fixed.** Candidate pairs are now screened from both sides and both distances taken (tested with a pair within 1 only backward). |
| The unmeasured-OFF count left out the unplanted cadence at its true choice, and was tested only on made-up events | medium | **confirmed; fixed.** The true choice's own candidates are counted too; an end-to-end test runs a cadence with one OFF look that has nothing to measure through `onoff.judge`: the tone is called a candidate and the blind OFF look is named. |
| The weak-ON measurement is not calibrated | medium | **agreed; labelled.** It is marked exploratory (random places, not detected hits) and each rate carries its Wilson interval; 60 places on noise say only that the rate there is under about 6%. |

## 12. Candidate vetting and ranking: 20 November 2026

**Verdict:** five of the defects are real in the code and fixed, as checks
version 5; none had touched a recorded result. Every stored candidate was
checked again with version 5 without writing anything, and all 11 verdicts,
and every check's result and strength, are the same
(`tools/vetting_checks.py`). The stored records stay as made (version 4);
they are checked again under version 5 before the next ranking. Tests:
`tests/test_vetting_v5.py`, each on an event the pipeline judged.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F12-01: a repeat at the same target in another session counts as interference | high | **confirmed in the code; fixed.** Check 6 searched every other session's looks, the same target's ON looks among them. Version 5 keeps hits at the same target apart (`same_target_hits_left_out`) and does not count them: a transmitter at the target would repeat too. The store holds one session a target, so no record had one; the two "shown" recurrences are at the KIC 8462852 OFF pointings, a different target, and stand. |
| F12-02: check 8 can make a candidate its own intermodulation product | high | **confirmed; fixed.** The strong zero-drift hits include the candidate's own, and every a·f1 − b·f2 with a − b = 1 is met by f1 = f2 = f. Version 5 leaves the candidate's own hits out (tested: "2f1+-1f2" from the candidate alone is gone). Measured on the records: one candidate (2,197.16 MHz) had own hits in the list, and its relations stand without them, from other hits; every chance stays 1.0 and every check 8 "coincidence possible". |
| F12-03: checks go stale as the store grows | high | **agreed; planned.** Checks 6 to 9 read the store; a fingerprint of the evidence each read, and re-checking when it changes, come with the next survey runs (audit 22). |
| F12-04: missing evidence can pass the sanity check | medium | **confirmed; fixed.** A look with no completeness record was taken as complete, and a missing stamp as sound. Version 5 calls either not sound (tested). No record was sound without stamps. |
| F12-05: check 8's chance draws from the band between the session's lowest and highest hits | medium | **agreed; planned**: drawing from the blocks searched, and its effect on the 2016 checks. |
| F12-06: two events can share a report | medium | **confirmed in the code; guarded.** The lead id is the frequency to 1 Hz; a later event with the same id now gets its event number added instead of replacing the other's record. No two candidate events in the store share one. |
| F12-07: a real signal in a listed band can never be unexplained | high | **agreed; by design, stated.** The band is an annotation and an indication, never a deletion; the cost is measured (0 of 1,914 planted signals in bands left unexplained at cut 30). A ranking where strong independent evidence can outweigh it is **planned** as a new version. |
| F12-08: ranking validated against 11 weak candidates | high | **agreed; planned**: a ranking challenge on observations chosen beforehand, with precision in the first 1, 10, 100 and 1,000. |
| F12-09: ranking scored without its OFF null | medium | **confirmed; fixed.** `ranking.context` now refuses without `off_null.json` unless a partial ranking is asked for, which says the OFF term is left out. The null is recorded for the session ranked. |

## 13. Instrument calibration and sensitivity: 20 November 2026

**Verdict:** the conversion from SNR to flux and EIRP is right under its
stated assumptions (ChatGPT's own figures agree: 7.4 Jy Hz at S_in 10 and
3.1×10¹⁴ W at 18.7 for 434.6 pc). The report used its calibration records
for any session, which is fixed. The rest is about what the calibration
covers, which the report states and later work extends.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| 1: the report used one setup's calibration for any session | high | **confirmed; fixed.** `report.py` took the SEFD, the completeness table, the channel response and the dropped-data record whatever the session. Each is now used only where it applies: the SEFD over its measured band (1,800 to 2,750 MHz), completeness on its own cadence (the 2017 files), the response with the product's channel width and sampling, the dropped data for its session; otherwise the flux is marked assumed (10 Jy) and no completeness thresholds are given (`tests/test_report_calibration.py`, with the real records: they apply to 2017 and not to the 2019 C-band session). The published 2017 figures are unchanged. |
| 2: the 2017 SEFD comes from a 2019 calibrator | high | **agreed; stated.** 10.65 Jy is a reference scale from one accepted 3C295 pair (2 December 2019), not a calibration of the 2017 session; the 10 to 12.5 Jy bracket is published values, not an interval. The report's next revision says so where the EIRP figures are given. |
| 3: completeness measured on 5 blocks (14.65 MHz) of 801.3 usable | high | **agreed; stated** in the next revision: the thresholds are measured on those blocks; band-wide sensitivity by region, on blocks chosen beforehand, is **planned**. |
| 4: the coarse-channel response is not calibrated | high | **agreed; planned**: recovery at fixed injected power across positions in a coarse channel. |
| 5: flux values carry no record of the SEFD assumed | medium | **agreed; planned**: a calibration manifest beside the records (SEFD, band, polarizations, formula, nominal or calibrated); the stored values stay. |
| 6: the fine-channel response from one Voyager 1 file | medium | **agreed; stated** (reduced χ² 3.72, wings above sinc²); a second carrier is **planned**. |
| 7: frequency dependence of the SEFD | medium | **agreed; planned**: the measured 50 MHz values (9.97 to 13.5 Jy) used where measured. |
