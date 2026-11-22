# Audit plan

Twenty-four audits of the project (two more added on 20 November), set on 19 November 2026 at commit
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
| 2 | Signal injection accuracy | 1 | critical | **re-audited** (20 Nov 2026): the paired reruns finished, no change to either pipeline's recovery beyond 2 signals in 880; see below |
| 3 | turboSETI comparison fairness | 1 | critical | **measured** (21 Nov 2026): the 16 blocks run; turboSETI loses most signals before its event stage, with no hit at SNR 5; the zero-drift trial changes nothing; matched operating points cannot be resolved on 8 blocks a session; see below |
| 4 | False-positive methodology | 1 | critical | **in progress** (21 Nov 2026): record-based checks done; time order changes no wrong choice's candidates; control B (four real cadences of other targets in their own order) chosen by a rule fixed first, running; see below |
| 5 | The 2016 interference failure | 1 | critical | **measured** (21 Nov 2026): all 23 blocks read again; the cap is not the cause (raising it removes 137 of 3,654); the OFF looks hold weak related hits under the veto; two ON hits would cut the false candidates by 86%; see below |
| 6 | Detector completeness and missed signals | 1 | high | **in progress** (21 Nov 2026): the cap, crowding, close pairs and offsets measured; the strong 2017 misses are detected and measured outside the tolerances, which compare frequencies at the look's start; shadow refresh changes nothing that counts; see below |
| 7 | BLISS comparison | 1 | high | **in progress** (21 Nov 2026): provenance enforced, two-ON split measured; on eight blocks chosen beforehand the same-hit control finds no large event-stage effect; see below |
| 8 | Statistical analysis and uncertainty | 1 | high | **done** (20 Nov 2026): `tools/statistical_checks.py` on all three sessions; see below |
| 9 | Core narrowband detection algorithm (`searching.py`) | 2 | high | **measured** (21 Nov 2026): on 12 real blocks none of the confirmed faults changes a false candidate or a planted signal found at 30; the noise direction differs strongly in crowded 2016 looks; see below |
| 10 | Curved Doppler search | 2 | high | **measured** (21 Nov 2026): on ten 2017 blocks first-wins and unmeasured OFF looks change nothing; the two untraced signals are recovered by the matcher, so their loss lies elsewhere; see below |
| 11 | ON/OFF cadence matching (`onoff.py`) | 2 | high | **measured** (21 Nov 2026): no candidate with an unmeasured OFF look on 12 blocks; one-way matches are 14% of close hit pairs; see below |
| 12 | Candidate vetting and ranking | 2 | high | **in progress** (20 Nov 2026): five defects fixed as checks version 5, no recorded verdict changed; the ranking challenge planned; see below |
| 13 | Instrument calibration and sensitivity | 2 | high | **in progress** (20 Nov 2026): calibration records used only where they apply; the coarse-channel response and band-wide sensitivity planned; see below |
| 14 | Data acquisition and integrity | 2 | high | **in progress** (21 Nov 2026): the 2016 DC bins fixed, and the two rules give identical false and found counts on eight 2016 blocks; refusals added; source versions planned; see below |
| 15 | Astronomical signal coverage | 2 | medium | **in progress** (20 Nov 2026): seven kinds of signal measured through the unchanged search; pulses, faster drifts and eccentric orbits planned; see below |
| 16 | End-to-end reproducibility | 3 | critical | **in progress** (20 Nov 2026): reproduction proves each output made again; step 10 replayed from a fresh clone, fresh environments and the evidence package alone, identical (it found the turboSETI pins could not be installed as written, now fixed); another machine planned; see below |
| 17 | Experiment freezing and scientific provenance | 3 | high | **in progress** (21 Nov 2026): frozen configs pinned, deviation history kept, block provenance enforced; a record now names the code its process started with (two results had named a later commit); see below |
| 18 | The report and its claims | 3 | high | **in progress** (20 Nov 2026): version 1.6 written with what the audits found; record checks planned; see below |
| 19 | Public repository and release readiness | 3 | high | **in progress** (20 Nov 2026): documents brought into line with the code, a consistency test; the release, tag and Zenodo deposit left for Ryan's go; see below |
| 20 | Parallel processing and performance | 4 | high | **in progress** (20 Nov 2026): every record written whole, broken records set aside; the shared scheduler planned; see below |
| 21 | Database and evidence storage | 4 | medium | **in progress** (20 Nov 2026): checks saved whole, six looks required, source versions kept, content hashed, integrity checked, indexes added; evidence revisions planned; see below |
| 22 | Distributed volunteer computing (`docs/multiuser.md`) | 4 | high | **in progress** (20 Nov 2026): the plan's constraints written in; occupancy's cache follows the store, a block's scans required; the system itself not built; see below |
| 23 | Testing and regression coverage | 4 | high | **in progress** (20 Nov 2026): tests isolated from any real data folder, the old-version comparison required in CI; the whole-pipeline test built (it found the OFF null could be measured only for the 2017 session), the reader tests planned; see below |
| 24 | Large-scale survey strategy | 4 | medium | **in progress** (20 Nov 2026): cadences have keys of their own (store schema 3), so a second cadence of a session is kept apart instead of refused; coverage searched and searched completely kept apart; the survey protocol planned; see below |
| 25 | Diagnostic and measuring tools | 5 | critical | **in progress** (20 Nov 2026): results' provenance now keeps the command, the script's hash and any uncommitted diff; the evidence ledger checked by `tools/ledger.py`; three equivalence tests found unable to fail and given data that can, the equivalences still holding; planted-fault tests for the BLISS, completeness and DC tools, which found the pin check passing records with a run's provenance missing (21 Nov 2026); see below |
| 26 | Following up a real candidate | 5 | high | **planned** (20 Nov 2026): the steps from a top-ranked candidate to one others can check, and what is kept for it; see below |

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

**Phase 5: the measuring tools and what follows a detection** (added 20 November 2026)

25. **Diagnostic and measuring tools.** Every tool under `tools/` that
    measures the pipeline: independence from the code it measures, its
    matching against the truth, its provenance, and whether it fails on an
    implementation known to be wrong (a planted fault), not only passes on
    the right one. Six of the re-audits found faults in these tools
    themselves (equal totals taken as the same signals, turboSETI's event
    rows grouped by hit number, the wrong event credited, ON looks assumed
    at even positions, recovery by frequency alone, intervals of different
    quantities compared).
26. **Following up a real candidate.** What happens when a candidate ranks
    high: the evidence kept for it, the checks others can repeat, a repeat
    observation and other pointings, other instruments where possible,
    terrestrial interference, independent review. A planted signal shows
    the detector works; it cannot show a real signal is from the sky, let
    alone from a transmitter.

## The status review before the audits (19 November 2026)

| Finding | Verdict |
|---|---|
| The README is behind the research (version 0.1, step 12 not run) | **built**: README brought to report 1.3, step 12's result and the dependence on the cut |
| The evidence package predates step 12 | **built**: the package now takes data/step12 (its choices, deviations and saved archive replies) and makes the operating-point record again. Built afresh at c35afe3 (3,181 records and the store, 238 MB) and reproduced from a clean checkout at that commit: 8 table commands, 70 pages and records the same, none different (docs/releasing.md) |
| Nobody else has reproduced the tables | **not done**: needs a second person; stays on docs/releasing.md as the step before the DOI is announced |
| No formal release (tag, GitHub release, Zenodo) | **not done**: waits for the Zenodo account (put off by Ryan on 19 Nov), so that the release is archived when it is made |

## The review of the plan, 20 November 2026

A review of this file and the commits to 865d3e0, judged point by point
against the repo and the job log.

| Point | Verdict and what was done |
|---|---|
| 2 audits done, 21 open, 1 not started | **correct.** Audit 6 had been skipped between 5 and 7. Its first measurements had run (`tools/completeness_checks.py`, 749c7c2) but were never written up; now they are (section 6). |
| Audit 6 first: the 2,000-hit cap and crowded misses | **correct; done in part** (section 6). The first two 2016 blocks read again with the cap at 20,000 keep 779 of 783 and 728 of 733 false candidates: in those two the cap is not their cause. |
| Finish the prepared experiments for 2, 3, 4, 5, 7, 9, 10, 11 and 14 before re-auditing their code | **correct.** Audit 2's reruns have finished (section 2, results). The rest are running or queued in order: turboSETI's 16 blocks (running), the time-order test, the BLISS control, the detector and curved blocks, the DC comparison; in the second lane the 2016 reread (2 of 23 blocks), then the strong misses and shadow refresh. Their results go in each audit's section and in the ledger as they land. |
| A11-01 (blind OFF looks), CD-01 (first hypothesis wins), F12-03 (checks go stale) | **correct; already recorded** as confirmed with their measurements queued; nothing new. |
| Leave 1 and 8 until the measurements; revisit 1, 4, 8 and 18 together afterwards | **agreed.** |
| A new audit of the diagnostic tools, each shown to fail on a known-bad implementation | **correct**: audit 25. |
| A new audit of following up a real candidate | **correct in part**: audit 26. The checks, evidence and procedure are this project's to build; a repeat observation needs telescope time, which is the person's to ask for. |
| 23: a whole-pipeline test | **correct; built** (section 23). It found a real gap at once: the OFF null could only be measured on the 2017 session's saved cadences, so no other session could be ranked in full. |
| 16: replaying observations on another computer | **correct; planned.** A fresh clone with a fresh environment on this PC, replaying one block from the archive against its record, is the part that can be done here; another machine is the person's. |
| 24: cadence ids and a migration before any survey | **correct; planned** as the next store change. The guard stays until then. |
| 4: independent, time-ordered negative-control observations | **correct; planned**: the controls chosen from the archive's listing and recorded here before any of their spectra are read. |
| A commit, command, result file and verdict for each material finding | **correct; built**: the ledger below, checked by `tools/ledger.py`. Doing it showed that results did not record their command, and that results made with uncommitted changes kept only a hash of the diff; both are now kept (audit 25). |

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

### 2, the paired reruns' results, 20 November 2026

All four finished; each compares the same 880 (or 96) planted signals
signal by signal, both found, the first only, the second only, neither.

| Comparison | This search, SNR 10 / 30 | turboSETI, SNR 10 / 30 | Result |
|---|---|---|---|
| Power at 32 against 51 sub-steps (`injection_voltage.json`) | 580 both, 0 apart / 305, 0 | 389, 0 / 212, 0 | identical signal by signal |
| Power against a tone in the voltages (the cross term) | 570 both, 10 and 11 apart / 299, 6 and 8 | 368, 21 and 23 / 205, 7 and 8 | totals within 2; about 2% of signals swap each way, so equal totals did hide different signals (C2) |
| The same with two polarizations summed | 585, 9 and 10 / 306, 4 and 4 | 355, 25 and 13 / 202, 10 and 7 | within 1 for this search; turboSETI finds 12 fewer at SNR 10 with voltages (380 against 368) |
| Blanked then planted (in use) against planted then blanked (`injection_dc.json`) | 70, 1 and 0 / 37, 1 and 0 of 96 | 52, 0 / 26, 2 and 0 | in use finds at most 2 more, all at the DC bin |
| Fixed S_in against one injected power (`injection_power.json`) | 588, 6 and 5 / 300, 2 and 4 | 121, 1 and 0 / 28, 2 and 0 | within 2 |

So the planting's simplifications move neither pipeline's recovery by more
than 2 signals in 96 to 880, except turboSETI with two polarizations at SNR
10 (12 of 880, 1.4%), and never one pipeline against the other. The
results stand as a measure of recovery at a controlled signal-to-noise.

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
| Searching once at the lowest cut and cutting the tables is the same as searching at each cut | — | **measured: the same signals.** turboSETI's search at SNR 30 itself against the SNR 5 search cut to > 30: hits, event rows and signals found compared (the 16 blocks below). |
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

### 3, the 16 blocks, 21 November 2026

`tools/turbo_checks.py blocks` on 16 blocks (four crowded and four clean of
each of the 2017 and 2016 sessions, seed 12), 1,760 planted signals,
paired signal by signal (`data/analysis/turbo_checks.json`).

| Pipeline | Found at SNR 10 | Found at 30 |
|---|---|---|
| This search as published | 1,166 | 588 |
| turboSETI as published | 220 | 55 |
| turboSETI's hits through this search's cadence test | 259 | 71 |
| This search's hits through turboSETI's event stage | 1,006 | 501 |
| turboSETI with the zero-drift trial searched | 218 | 55 |

| Finding | Severity | Verdict |
|---|---|---|
| Where the gap is | high | **measured: in the detector.** Swapping cadence tests moves each pipeline little (turboSETI 220 to 259; this search 1,166 to 1,006); swapping hits moves it fivefold. Of turboSETI's 1,540 losses at 10, **1,236 have no hit at SNR 5** within tolerances, 187 a matching hit only at or under the cut, 54 a hit measured outside the tolerances (all at 0.5 Hz/s or more, 41 of them at S_in 400), 49 another hit in the top-hit window (crowded blocks only; suppression suspected, not shown), 9 hits over the cut in each ON look but no event, 5 an OFF hit in the window. |
| F3-01: the zero-drift trial | high | **measured: no effect.** With `min_drift` at −1 turboSETI finds 218 against 220 at 10 (2 found only without it, both under 0.15 Hz/s) and 55 against 55 at 30. |
| F3-03: event members | medium | **measured: no disagreement.** Of the ON looks of every credited signal, 331 verified and 329 unknown at 10, 106 and 59 at 30; none disagrees. |
| Searching once at the lowest cut | — | **hits the same, event rows not, signals found the same.** turboSETI's 621 hits over 30 are identical whether searched at 5 and cut or searched at 30 (0 differ in any look of any block). Its event rows are not: 120 from the cut tables against 85 searched at 30, differing in 14 of 16 blocks (43 rows). **No planted signal moves:** of 1,760, 55 are found both ways, 1,705 neither way and none one way only, so the published 55 at 30 stands. 615 of the 621 hits carry a different TopHitNum in the two searches, the number find_events deduplicates by, and every block whose rows differ has renumbered hits; that fits renumbering as the cause of the differing rows but does not isolate it (two blocks have renumbered hits and the same rows). |
| Tolerances scaled with drift | — | **measured.** turboSETI gains 4 signals at 10 (220 to 224), this search 123 (82 of them at 2 to 4 Hz/s) and 42 at 30. The published tolerances cost this search more than turboSETI, since turboSETI finds almost nothing at fast drift either way. |
| find_events' deduplication | — | **measured.** This search's hits through turboSETI's event stage find 253 more signals at 10 when numbered in channel order, as turboSETI numbers its own, than strongest first (1,006 against 753). The published crossed result uses channel order. |
| Matched operating points | high | **not resolvable on these blocks.** Step 4's rule needs a cut with at most 0.1 false candidates a block at every higher cut; with 8 blocks a session one candidate is 0.125. Neither published pipeline reaches it on either session (this search at 100: 2.6 a block in 2016; turboSETI at 100: 0.125). Only the crossed pairs reach it, in 2016. A matched comparison needs the full sessions: **planned**, with the record-based curves step 4 already has. |

False candidates a block at 10 and 30, over the 19 wrong choices: 2016, this
search 239 and 98, turboSETI 2.1 and 0.4, crossed 15.8 and 1.0 (turboSETI's
hits) and 17.1 and 2.6 (this search's); 2017, 7.9 and 0.9, 0.4 and 0.4,
0.8 and 0.4, 0.4 and 0.5. turboSETI's low rates go with its low recovery:
it finds few hits, real or not.

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
| Control B: real, time-ordered negative-control cadences from other directions | — | **chosen and queued** (below): four sessions by a rule fixed first. |

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

### 4, control B chosen, 20 November 2026

Control B is **chosen and queued**, before any of its spectra were read.
The rule (`tools/negative_controls.py`'s docstring, fixed first): targets in
the order of Breakthrough Listen's target list (Isaacson et al. 2017, its
file's SHA-256 recorded), asked of the archive by name; Green Bank
sessions, each one's first run of six looks ON, OFF, ON, OFF, ON, OFF of the
finest product; no session or ON target this project has read; the first
ON file's header in the layout the frozen search was validated on (16
spectra of 18.25 s, 2.79 or 2.84 Hz channels); the first four that pass.
Every archive reply is kept with its hash
(`data/analysis/negative_controls/`).

| Listed under | Session | ON target of its first eligible run | Band | Blocks |
|---|---|---|---|---|
| HIP 2 | AGBT16A_999_224 | GJ 83.1 | 1,024 to 1,926 MHz (L) | 308 |
| HIP 169 | AGBT16B_999_102 | HIP 15638 | 1,024 to 1,926 MHz (L) | 308 |
| HIP 171 | AGBT16A_999_244 | HIP 3419 | 1,024 to 1,926 MHz (L) | 308 |
| HIP 194 | AGBT16B_999_61 | HIP 103256 | 1,798 to 2,803 MHz (S) | 343 |

Sixteen sessions were passed over: 15 for spectra of 17.99 s, one already
read here. The session is the one listed under the catalogue's star; its
first eligible run need not be of that star, and here none is.

What is measured, fixed now: each cadence swept whole by the frozen search
in its real time order, in a store of its own; the primary measure is
cadence candidates (before the checks) with SNR at least 30 a block, by
session with its exact Poisson 95% interval and a bootstrap over blocks,
and over the four; secondary, the same at 10 and, after the checks, the
unexplained only. Beside each, the rate one wrong ON/OFF choice gives
(F4-01). Three of the four are L band, the band of 2016's failure, so the
control also tells whether that failure belongs to L-band cadences in
their real order or to the wrong-choice stand-in. Nothing in steps 4, 10
or 12 changes with the result.

### 4, the time-order test, 21 November 2026

F4-02's measurement (`tools/false_checks.py chronological`, 16 blocks):
every wrong choice judged with its looks in time order beside the published
ON, OFF pairs. **No choice's count or candidates differ**, at 10 or at 30
(1,977 and 787 distinct candidates over all choices both ways; 45 and 13
choices with any). So for this search the order of the looks does not
change the false-candidate count. Exchangeability with the real choice
remains control B's (running).

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

### 5, the blocks read again, 21 November 2026

`tools/rfi2016.py reread` on all 23 blocks: the seven holding 3,654 of
2016's false candidates at 30, eight other 2016 blocks and eight of 2017.
Every block at OFF_MAX 6 gives its record's own false and found counts.

| Finding | Severity | Verdict |
|---|---|---|
| A5-06: the hit cap | high | **not the cause.** With the cap at 20,000 the seven blocks keep 3,161 of 3,654 false candidates unchanged and 356 with other member hits, lose 137 (3.7%), and gain 1,180 new (1,144 in block 171, whose three raised looks were still capped): 4,697 in all. More hits make more candidates here, not fewer. |
| Related OFF hits | high | **measured.** Of 3,709 candidates in the seven blocks, **2,464 have a hit in an OFF look within 3 kHz**, 1,514 one drifting alike; the strongest OFF evidence along their tracks has a median S/N of about 3 to 4.4 by block, under the veto (6). The OFF looks see the interference, too weakly to veto it. |
| The OFF threshold | medium | **measured.** 2016, 15 blocks, at 30: OFF_MAX 5, 6 (published), 7, 8, 10 give 3,006, 3,701, 4,188, 4,643, 5,382 false candidates and 435, 455, 461, 465, 466 of 1,650 planted signals found. A stricter veto removes a fifth of the false candidates for 4% of the signals; no setting comes near passing. 2017 (8 blocks): 7 to 10 false, 293 to 303 found. |
| A5-02: more ON hits, counted exactly | high | **measured** by the event that recovers each signal. 2016 at 30: one ON hit or more, 3,701 false, 455 found; two, **521 and 405**; three, 88 and 354. At 10: 8,289 / 840, 1,878 / 805, 122 / 691. 2017 at 30: 7 / 302, 4 / 284, 0 / 272. Two ON hits would cut 2016's false candidates by 86% for 11% of the signals found at 30: the measurement for a new detector version, tested on sessions chosen beforehand. |

## 6. Detector completeness and missed signals: 20 November 2026

**Verdict:** the hit cap costs recovery in crowded looks and hides signals
below 2,000 stronger hits, but in the 2016 blocks read again so far it is
not what makes the false candidates; close signals at fast drift are lost
beside each other far more than the grid of planted signals shows. Every
number is from the block records or from the search's own code
(`tools/completeness_checks.py`, its diagnostic copy identical to the search
at its defaults, tested; `tools/detector_misses.py`; `tools/rfi2016.py`).
The search is frozen: what these suggest is a new detector version.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| A6-01: the 2,000-hit cap costs recovery | high | **measured.** Planted signals recovered at SNR 30, blocks with an ON look stopped at the cap against blocks complete: 2016 **23.2% (587 of 2,530) against 34.8%** (3,750 of 10,780); 2017 30.0% (429 of 1,430) against 34.5%; 2019 had no capped look. By the block's hits at the sweep's cut, 2016 blocks over 1,000 hits recover 22.7%, those with 5 to 20 hits 35.2%. Of the 8 signals BLISS found and this search missed for a reason in the detector, **6 are the cap**: S/N 12.3 to 40.6 on their own tracks, below 2,000 stronger hits, picked once the cap is 5,000 or more, their noise not inflated (0.77 to 1.42 of the look's median) and untouched by other hits' blanking (`detector_misses.json`). |
| A6-02: the cap as the cause of 2016's false candidates | high | **not the cause in the two blocks read so far.** 3,899 of 3,938 false candidates at SNR 30 lie in blocks with a capped ON look (169.5 a block, against 0.40 in complete blocks), which made the cap the first suspect. With the cap at 20,000, block 195 keeps 779 of 783 (4 gone, none new) and block 59 keeps 728 of 733 (5 gone, 24 new, so 752). In block 59 all 753 have a hit in an OFF look within 3 kHz and 717 a hit drifting alike there: the OFF looks hold related hits that the OFF test does not connect. The other 21 blocks are running (`rfi2016.py reread`). |
| A6-03: crowding and close pairs | high | **measured.** Two signals 1 to 100 channels apart at 2 to 4 Hz/s, the second found alone in 425 of 864 cases: **177 of those (42%) are lost beside the first**, nearly all within 16 channels (8 of 52 at 32, 3 of 58 at 64, 5 of 51 at 100). Without the corridor of excluded line starts 73 of the 177 are found; refreshing the scores after shadow hits finds 4 (`completeness_pairs.json`). The planted grid keeps its signals apart, so the recovery tables do not include this loss; it is a limit stated with them. |
| A6-04: a global cap against a budget a region | medium | **measured** (scaled: 200 hits a slice of 262,144 channels). A lone signal far from a crowd is found under the global cap up to a crowd of 250 and lost at 400 and 800; with the same budget a region it is found at every size (`completeness_cluster.json`). A per-region budget is **planned** for the next detector version. |
| A6-05: frequency and drift accuracy | medium | **measured.** Recovered signals' nearest event member is well inside the tolerances (6 Hz, 0.05 Hz/s) at every drift: 99th percentile 1.6 to 3.6 Hz and 0.011 to 0.028 Hz/s, largest 5.6 Hz and 0.038 Hz/s (2016, 2 to 4 Hz/s). Missed signals have no near miss: their nearest event is a median 25 to 33 kHz away. Two of BLISS's 8 are the exception: found at S/N 52 and 90 but 2 to 4 channels and 0.05 Hz/s off at about 2 Hz/s, just outside. At fast drift a 6 Hz tolerance is about two channels, so tolerances that grow with drift are **planned** for the comparison, not for the frozen results. |
| A6-06: blanking | medium | **measured in part.** No other hit's blanking touched the six capped misses. The re-sum's reach after a pick (F9-01) is the related fault, measured in audit 9. |
| A6-07: failure modes not yet seen | medium | **in part.** A non-finite sample is now refused when a look is read, not left to end its search silently (F9-04). The whole-pipeline test (audit 23) is the guard for faults between the stages. The strong 2017 misses at 2 to 4 Hz/s, traced stage by stage, are queued (`completeness_checks.py strong`), and shadow refresh on four crowded 2016 blocks after them (`shadow`). |

### 6, the strong misses and shadow refresh, 21 November 2026

**The strong 2017 misses** (`completeness_checks.py strong`): the 67
signals planted at S_in 400 drifting at 2 Hz/s or more and not recovered in
all three ON looks at 30. **59 are detected in every ON look**, but in one
(50) or two (9) looks the hit is measured outside the tolerances: 6 to 24
Hz off in frequency (median 9.5) and 0.03 to 0.10 Hz/s in drift (median
0.056). The rest: 3 called interference by the cadence test, 2 with an ON
look capped, 2 scored against an event holding a matching hit, 1 with no
matching hit.

The frequency error is the drift error times about 175 s (10th to 90th
percentile 139 to 227 s): the measured track pivots on the true one near
the middle of the 292 s look, and the tolerance compares frequencies at its
start. Compared at the middle, **66 of the 68 looks are within 6 Hz** and 57
of the 59 signals match in every look by frequency; the drift is still over
0.05 Hz/s in 44 looks. At 2 to 4 Hz/s a signal crosses 18 to 36 channels
within each spectrum, so its drift is measured coarsely.

| Finding | Severity | Verdict |
|---|---|---|
| A6-08: fast strong signals counted lost were detected | high | **measured.** The recovery tables count these 59 as missed; they are detected and measured imprecisely. Recovery at 2 to 4 Hz/s is a lower bound for detection. A scoring that compares at the middle of the look, with tolerances that grow with drift (A6-05), is **planned** as a new version beside the published tables, with a planted-fault test. No frozen verdict uses this scoring. |
| A6-07: shadow refresh | medium | **measured: no effect that counts.** On four crowded 2016 blocks (59, 150, 210, 221), refreshing the scores after shadow picks changes up to 1,142 hits in a block but the false candidates at 30 by one (733 to 732 in block 59) and the planted signals found by none. |

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

### 7, the same-hit control on eight blocks, 21 November 2026

BL-06's control on the eight 2017 blocks chosen beforehand (49, 79, 131,
139, 166, 185, 221, 231): distinct false candidates at 30 over the 19 wrong
choices, BLISS's hits at 30 through each logic. BLISS's event stage **13**;
this search's cadence test on the same hits **18**, 18 with shadow hits from
5; this search's test on BLISS's hits grouped at 5, **10**. The earlier runs'
counts are repeated exactly (13 and 10). On blocks 35 and 129, chosen for
their false candidates, the event stage gave 1,610 and 2,627 against 85 and
205: the large difference is confined to the most crowded blocks, and on
these eight neither logic gives many. Step 11's conclusion that the event
stage counts far more holds for those two blocks only, as it said.

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

### 9, the blocks run, 21 November 2026

`tools/detector_checks.py blocks` on 12 blocks (eight of 2017, four crowded
of 2016), with the search's own code:

| Finding | Verdict |
|---|---|
| F9-01: the refresh reach | **no effect on candidates.** A full-reach re-sum changes 437 of 45,456 hits (1%) and no false candidate or planted signal found at 30 (785 and 433 both ways). |
| F9-02: noise by drift direction | **larger on real data than on noise, in crowded looks.** Over each look's noise blocks the median difference is 8% (noise alone: 3 to 13%), but in crowded 2016 looks single noise blocks differ by up to **10 times** (blocks 59 and 221). Where that happens negative drifts are scaled by the positive drift's noise. Its effect on candidates is not separated here: a new version measuring both signs is the test. |
| F9-03: one search for every cut | **holds closely.** Searched at each cut against one search at 10 relabelled: at 30, 786 against 785 false and 433 found both ways; at 8, 2,537 against 2,553 false and 916 found both ways. |
| F9-04: non-finite samples | **none** in the 72 looks. |
| F9-06: rounding at the cut | **small.** Hits whose rounded SNR reaches a cut their exact value misses: 71 at 10, 7 at 30, in 12 blocks. |

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

### 10, the blocks run, 21 November 2026

`tools/curved_checks.py blocks` on ten 2017 blocks (36, 128 and eight by
seed 12), at 30. False candidates 9 and planted signals found 548 under
every rule: as published, any hypothesis a candidate, and one, two or all
three OFF looks required to be measured.

| Finding | Verdict |
|---|---|
| CD-01: first hypothesis wins | **no effect here.** Of 265 sets of planted hits, 81 were reached by more than one fit; none disagreed, and no set had an interference first hypothesis and a candidate later. The wrong choices made no curved hypotheses on these blocks. |
| CD-02: unmeasured OFF looks | **none.** No curved candidate had an OFF look unmeasured. |
| CD-04: the two signals | **recovered by the matcher.** Block 36's signal 61 and block 128's signal 62 are recovered under every rule, by two hits and a track, each from one hypothesis (ON looks 0 and 4, acceleration ±3.6 ×10⁻⁴ Hz/s²). So the vetting run's miss does not come from the matcher's choice among hypotheses; where it does come from is **open**. |

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

### 11, the blocks run, 21 November 2026

Measured in the same 12 blocks as audit 9:

| Finding | Verdict |
|---|---|
| A11-01: unmeasured OFF looks | **none.** Of 808 candidates of the wrong choices, 524 planted and 52 of the true choice unplanted, none had an OFF look unmeasured. On these blocks the gap is not reached. |
| A11-02: a weak ON look passing on the best of the tolerances | **rare and never both.** At 2,400 random places with nothing planted, one other ON look reached ON_MIN at about 1% of places; both never did, so no one-hit candidate was made this way. |
| A11-03: one-way matches | **measured.** Of 2,374 hit pairs matching one way or both, 2,041 match both ways, 191 forward only and 142 backward only: 14% depend on the direction. |

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

### 12, re-audited at 8a59ebb, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F12-06's guard wrote a record ranking could not find, and still overwrote a superseded event's record | high | **confirmed; fixed.** The event number is now the record's identity: `check.record_for` finds an event's record under its lead id or the lead id with its event number added, ranking uses it, and an event never takes over another event's record, superseded or not (tested). |
| Check 6's background still counted the same target's files | medium | **confirmed; fixed.** The background takes the same files as the matches. |
| Check 8 still let one tone be both parents | medium | **confirmed; fixed.** Strong hits within the tolerance of the candidate (its own tone, however often detected) are left out, and f2 may not be the tone f1 is; two other tones still make the relation (tested). The scan-every-hit reference in `tools/check8_equivalence.py` carries the same rule pair by pair, and still gives what the indexed version gives. |
| Partial ranking not reachable; the OFF null not checked for the session | medium | **confirmed; fixed.** `ranking.py rank --partial` ranks without it and says so; otherwise an OFF null measured on another session's cadences is refused like a missing one (tested), and the message names the real command (`offnull`). |
| The version 4 against 5 comparison checked results only for checks 1 and 6 | medium | **confirmed; fixed.** It now compares every check's result and strength: all 11 candidates are the same in every check under version 5 as recorded. |

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

### 13, re-audited at 342045e, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| A report without applicable completeness crashed, and still showed 2017's completeness | high | **confirmed; fixed.** The completeness, candidate sensitivity and sensitivity sections are written only where the completeness record applies; otherwise the report says it was not measured for the session. Building the 2019 C-band report end to end also hit an older crash (the CWTFM and the Harp et al. comparison need a target distance and a measured EIRP), now guarded. The 2017 report comes out as committed, bar its header's date and checks version. |
| The SEFD counted as covering the band if its end bins did | high | **confirmed; fixed.** Every 50 MHz the band touches must have a measured bin, bar the notch (2,300 to 2,360 MHz, searched but not counted); a gap anywhere refuses it (tested). The 2017 band (1,818 to 2,721 MHz) is covered bin by bin. |
| Completeness matched by target and day | high | **confirmed; fixed.** It now needs every scan its files name (guppi_<MJD>_<seconds>) to be one of the session's own; another scan of the same target on the same day is refused (tested). On the store: 2017 applies, 2016 and 2019 do not. |
| The channel response matched by width and sampling only | medium | **agreed; stated.** The spectrometer's set-up is not in the files' headers; the response is recorded as the same product's (Voyager 1, 2016), not shown to be the session's. |

## 14. Data acquisition and integrity: 20 November 2026

**Verdict:** A14-01 was worse than stated, and it is fixed. The 2016 session's
coarse channels are 1,033,216 channels wide (its file holds exactly 308),
while its storage chunks are 2^20; the web reader blanked the DC bin at each
chunk's middle. Read raw, the 2016 file's real DC spikes stand 21,000 to
27,000 times the median at the coarse channels' middles, and the chunks'
middles are ordinary channels. So every 2016 read left the DC spikes in and
smoothed one ordinary channel a chunk. 2017 and 2019 are not affected (coarse
channels and chunks both 2^20). The effect on step 10: of 4,016 false events
at cut 30 over the 19 wrong choices, none lies within 50 Hz of a DC channel.
A spike in every look is vetoed by its OFF looks, so the 2016 failure does not
rest on it. Step 10's records stand as made; its verdict is frozen.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| A14-01: the two readers blank the DC bin in different places | high | **confirmed, larger than stated; fixed.** Both now take the coarse channel's width from the instrument (`seti.coarse_width`: at Green Bank the coarse channel's 187.5/64 MHz over the channel width), which gives 2^20 in 2017 and 2019, as before, and 1,033,216 in 2016 (tested, with the DC bin blanked at the coarse middle). `SSY_DC_BY_CHUNK=1` keeps the old rule for remaking records made before (set by `tools/regress_step10.py`; reruns of `tools/rfi2016.py reread` need it to reproduce step 10's records). |
| A14-02: a changed source file can leave old results current | high | **agreed; planned.** Every file read so far carries an ETag; binding each block's record to the file's ETag and size, and refusing to resume across a change, comes with the survey runs (audit 22). |
| A14-03: decode rebuilds only the first of several filters | high | **confirmed; guarded.** `reading.direct_ready` now refuses a file with more than one filter (tested), so it is never read wrongly. All 31 files indexed have one. |
| A14-04: a missing start time became MJD 0 | high | **confirmed; fixed.** Both readers refuse a look without `tstart` (tested). Checking a cadence's order and pointing against its target is **planned** (the matched runs take the order from the store's cadence positions). |
| A14-05: no ETag means no If-Match | medium | **agreed; planned.** Every file read so far had one; refusing a file without one would stop the 3C295 calibration files, so the total length is to be checked instead. |
| A14-06: damaged spectra enter the search | medium | **built in part.** A look with any non-finite sample is now refused rather than searched (audit 9 found one NaN empties a search; tested). Zero-filled and dropped-data checks stay in `instrument.dropped`, run apart. |
| A14-07: no reader regression tests | medium | **built in part**: `tests/test_reading_integrity.py`; local against web byte for byte on a fixture is **planned**. |

### 14, re-audited at fc76dd2, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| A14-02 should not wait for the survey | high | **agreed; built.** `store.upsert_file` now refuses a file whose ETag or size differs from the store's (SOURCE_CHANGED): its hits and blocks belong to the version recorded, and a changed file has to be kept apart rather than relabelled (tested). |
| The DC switch was not recorded, and the 2016 reread did not choose it | high | **confirmed; fixed.** Every run's parameters now record `dc_bins` (coarse channel, or storage chunk under the switch); where the two rules differ for a session's files (its chunks are not its coarse channels, as in 2016), a sweep resumes only blocks read under the rule in force. The search version is unchanged: for 2017 and 2019 the rules agree, and bumping it would have thrown away their current blocks. `tools/rfi2016.py` and `tools/regress_step10.py` now choose the old rule explicitly, since they check step 10's records (tested). |
| The 2016 effect needs a comparison, not only the false candidates' frequencies | medium | **agreed; queued**: `tools/dc_checks.py` reads eight 2016 blocks (four crowded, four clean, seed 12) both ways and compares false candidates, planted signals found and hits. |
| End-to-end reader tests | medium | **planned**: local against web on a fixture, and a source changed between runs. |

### 14, the DC comparison, 21 November 2026

`tools/dc_checks.py` on eight 2016 blocks (four crowded, four clean, seed
12), DC bins blanked by storage chunk (as step 10 ran) and by coarse channel
(now): **false candidates and planted signals found at 30 identical in every
block** (780 and 286 in all); 80 of about 33,000 hits differ. The published
2016 results do not rest on where the DC bins were blanked.

## 15. Astronomical signal coverage: 20 November 2026

**Verdict:** the findings are about coverage, not defects: the published
completeness is for continuous narrowband signals on straight tracks within
±4 Hz/s, and the report says so. What the search does with other kinds was
not measured, and now is in part: `tools/coverage_checks.py` plants seven
kinds through the search and cadence test unchanged, on synthetic cadences
(noise only; Green Bank's channel width and sampling), six signals a
cadence, three cadences, at S_in 30, 60 and 120, cut 10. Signals recovered
in all three ON looks on their straight track, of 18 each (a first pass, superseded by the corrected measurement in the re-audit below: its hop and wide signals were looked for on the straight track, and its "candidate within 200 Hz" was too loose):

| kind | S_in 30 | S_in 60 | S_in 120 |
|---|---|---|---|
| continuous (as the completeness plants them) | 18 | 18 | 18 |
| on for half of each ON look | 10 | 18 | 18 |
| on for a quarter of each ON look | 0 | 10 | 18 |
| missing from one ON look | 0 | 0 | 0 |
| hopping 100 Hz at each ON look | 0 | 0 | 0 (no candidate near either) |
| wandering 0.5 Hz a spectrum about its drift | 18 | 18 | 18 |
| 16 channels wide, same power | 0 | 0 | 1 (a candidate within 200 Hz of all 18) |

So a signal on for part of each look needs the strength its duty cycle
takes away (half the time, about twice the strength); a signal absent from
one ON look, or hopping beyond the matching tolerance, is never a candidate
by design; a wide signal is found at S_in 120 but not on its own track. Kinds
not planted are untested, not missed.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| A15-01: intermittent and partial-look signals | high | **measured** (above). Every ON look must show the signal, by design; what that costs is now a number. |
| A15-02: pulses and periodic trains | high | **agreed; outside this search.** 18.25 s spectra cannot show sub-second structure; a periodic search on another product (0001, 349.5 μs) is a separate search, **planned**. |
| A15-03: broadband and modulated signals | medium | **measured in part** (16 channels, above); wider and modulated ones **planned**. |
| A15-04: drift beyond ±4 Hz/s | high | **agreed; planned**: recovery at 10, 20 and 50 Hz/s on the medium-resolution product, with its own completeness; the published limit stays ±4 Hz/s. |
| A15-05: the curved pass needs two straight hits | high | **agreed**; audit 10 measures it (CD-03). |
| A15-06: eccentric orbits, hopping, wandering | medium | **measured in part** (hopping and wandering, above); eccentric orbits **planned**. |
| A15-07: one table of what is covered | medium | **built** here; it goes into the report's next revision. |

### 15, re-audited at 2c065ef, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| R15-01: hops and wide signals were looked for on the straight track | high | **confirmed; fixed.** Each signal is now measured where it was planted in each ON look (`coverage_checks.true_x`: the hop, the wide signal's centre), tested. |
| R15-02: a candidate within 200 Hz counted as finding the signal | high | **confirmed; fixed.** A signal is found only when one kept candidate holds a hit at its true place in all three ON looks (tested: a candidate 60 channels off, or in two ON looks, does not count). The straight-track recovery is kept apart as the published standard. |
| R15-03: too small, and Wilson's interval assumes independent signals | medium | **agreed; enlarged and labelled.** Five cadences, random places, drifts ±0.3 and ±2 Hz/s (60 signals a cell, 30 a drift); each cell's count by cadence is recorded; still synthetic noise, so exploratory. |
| R15-04: the walk and wide models are narrow | medium | **agreed.** A wide walk (a channel a spectrum) is added; the wide signal is described as 16 adjacent tones. |
| R15-05: no tests | medium | **built**: `tests/test_coverage_checks.py`. |

The corrected measurement, signals found on their true places in all three
ON looks, of 30 at each drift (±0.3 Hz/s / ±2 Hz/s):

| kind | S_in 30 | S_in 60 | S_in 120 |
|---|---|---|---|
| continuous | 29 / 0 | 30 / 29 | 30 / 29 |
| on for half of each ON look | 0 / 0 | 22 / 0 | 26 / 20 |
| wandering 0.5 Hz a spectrum | 27 / 0 | 28 / 28 | 27 / 29 |
| wandering a channel a spectrum | 0 / 0 | 1 / 11 | 2 / 11 |
| 16 channels wide | 0 / 0 | 0 / 19 | 3 / 29 |

On for a quarter of each look: 1 of 60 at S_in 60 and 15 at 120. Missing
from one ON look: none. Hopping 100 Hz between looks: hit in every ON look
for 60 of 60 at S_in 120, but never joined into a candidate (the cadence
test matches within its tolerance by design). A wide signal is never
recovered on a narrowband track; found on its true places it is, at 2 Hz/s,
where its power crosses channels anyway.

## 16. End-to-end reproducibility: 20 November 2026

**Verdict:** two real defects in the reproduction check, both fixed; the
rest is the step from rebuilding tables to replaying experiments on another
machine, which is planned, not claimed.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F16-01: `evidence.py reproduce` passed if a table command wrote nothing | high | **confirmed; fixed.** Every output is given an old time before the tables run; each command must rewrite at least one, and every page whose header names a table command must have been rewritten by it, or the reproduction fails (`evidence.not_made_again`, tested with a command that writes nothing). |
| F16-02: the comparison ignored the whole provenance and every UTC time on a page | high | **confirmed; fixed.** A record's provenance is compared but for when, by which commit and on which machine's Python and libraries it was written; on a page only the time on its "written by" line and the time and commit after "written" or "finished" are taken out; an observation's time elsewhere is compared (tested, both ways). |
| F16-03: CI does not run a reproduction | high | **agreed; planned**: a small evidence fixture through extract, rebuild and compare on Linux and Windows. |
| F16-04: rebuilding tables is not replaying experiments | high | **agreed; stated and planned**: one block a session replayed from the archive with tolerances, then a full replay. |
| F16-05: the environment is recorded, not rebuilt | high | **agreed; planned**: setup and version-check scripts; BLISS's CUDA set-up documented with tolerances. |
| F16-06: the store and the records are not one snapshot | medium | **agreed; planned**: packaging refused while a run writes, or from a locked copy. |
| F16-07: step 12's replay is not in the reproduction guide | medium | **agreed; planned.** |
| F16-08: extraction filters need Python 3.11.4 | low | **confirmed; fixed**: refused with a message on a Python without them. |

### 16, re-audited at 1829094, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| A command could rewrite one output and leave another stale | high | **confirmed; fixed.** `evidence.EXPECTED` names what each table command writes (from a run that wrote them); every one must be rewritten, or the reproduction fails (a test keeps the map in step with the commands). The full reproduction of the e325c72 package passes under it: 101 pages and records the same. |
| Python and library differences ignored silently | medium | **fixed**: they are reported as notes, not failures. |

### 16, the replay from a fresh clone, 20 November 2026

F16-04 and F16-05 are **built in part**: `tools/fresh_replay.py` clones the
public repository from GitHub, builds new core and turboSETI environments
from the pinned versions, unpacks the evidence package as an empty data
folder, and runs `tools/regress_step10.py` there. That reads two of step
10's blocks again from the archive, measures them with the clone's code
and compares them field by field with step 10's records. **Result,
20 November 2026: passed.** From a clone of the public repository at
4b9dd4c, a core environment of 8 packages and a turboSETI environment of 37
built afresh from the pins, and the evidence package as the only data,
blocks 3 (crowded) and 72 (clean) read again from the archive are
**identical** to step 10's records in every field but the timings
(`data/analysis/fresh_replay.json`). It is the same PC, Windows and Python:
another machine is still the step after.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| The published turboSETI environment could not be installed | high | **found by the replay; fixed.** `pip install -r docs/environments/turboseti-windows.txt` fails to resolve. The environment that made the records has sigpyproc 2.0.0, which asks for numpy 2, beside numpy 1.26.4, and setigen and sigpyproc lack some packages they list (`pip check`). It came about through the documented install, which forces `numpy<2` afterwards; turboSETI, setigen and blimpy import and run without the rest. The exact environment is made with `pip install --no-deps -r` the freeze, now in `docs/reproducing-results.md`; the replay does that and keeps `pip check`'s output in its record. |

## 17. Experiment freezing and scientific provenance: 20 November 2026

**Verdict:** the five high findings are real in the code and fixed; none
shows a published result was made otherwise than stated. Step 10's and step
12's configs are as frozen (their SHA-256s match the configs at the freeze
commits), and each step's two recorded deviations stand as published.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F17-01: a committed edit could redefine a frozen experiment | high | **confirmed; fixed.** `independent.FROZEN_CONFIGS` pins each config's SHA-256 at its freeze commit (359359d for step 10, 27f35d5 for step 12); a config that differs is a deviation, refused without `--deviation` and logged (tested). |
| F17-02: logged deviations could drop out of the verdict | high | **confirmed; fixed.** The verdict carries the whole log (`deviation_history`) and its page lists every entry; restoring the code does not take one back. |
| F17-03 and F17-04: block records reused whatever made them; the DC rule not bound | high | **confirmed; fixed for new records.** `matched.run` writes `made_with` (the config's and the code's SHA-256 and the DC rule) into each record and refuses to resume over a record made with something else. Records from before carry none and stand as made. The curved pass's records are **planned** the same way. |
| F17-05: the step 12 runner gave its deviation to any change | high | **confirmed; fixed.** It now runs only when every changed fingerprint is the one its deviation explains (`tools/turbo_curves.py` as committed in f161e25); otherwise it refuses and a deviation must be given by hand. With today's changes it refuses, as it should: step 12 is finished. |
| F17-06: the regression was required only by the runner | medium | **confirmed; fixed.** Step 12's verdict itself refuses unless `data/analysis/regress_step10.json` passed (tested). Widening the regression beyond two blocks is **planned**. |
| F17-07: the selection gate trusted its cached baseline | medium | **confirmed; fixed.** A cached Green Bank gate made with another geometry, blocks, seed or cut is made again, and each gate result records the baseline record's SHA-256. |

### 17, re-audited at 1829094, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| Records made before `made_with` were taken on trust, and the curved pass had none | high | **confirmed; fixed.** The verdict now checks every chosen block's record in both folders: one with `made_with` must have this run's, one without must be byte for byte the record the newest evidence package listed (`independent.provenance_problems`, tested both ways). All 370 records of steps 10 and 12 (121 and 64 blocks, measured and curved) match their package. `curved_pass.run` now writes and checks `made_with` as `matched.run` does. |
| The runner's standing deviation could cover a changed config | high | **confirmed; fixed.** A config that differs from the frozen one is never the change it explains. |
| The source files' versions were not in the block provenance | high | **confirmed; fixed.** `made_with` holds the six files' ETags and sizes as the store keeps them (a changed file is refused there, audit 14). |
| A regression that passed with other code counted | medium | **confirmed; fixed.** The regression records the code's hash and the step 12 verdict refuses one made with other code, or none, with or without a deviation (tested). |
| The gate's baseline checked by its parameters, not its contents | medium | **confirmed; fixed.** The baseline record's SHA-256 is pinned in code; any other content is made again. |

### 17, provenance of long runs, 21 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F17-08: a record named the code current when it was written, not the code its process ran | high | **found while writing up; fixed.** `yoke.provenance` read the checkout's commit at each write. A run's modules are loaded when it starts, so a long run that straddles commits recorded a later commit than the code it ran. Two results here: turboSETI's 16 blocks (`turbo_checks.json`, since rerun from a clean start with the same findings; the affected record is kept as `turbo_checks-as-of-d3e5699.json`) and the 2016 reread (`rfi2016_reread.json`) started early on 20 November, turboSETI's at 08:05 at `865d3e0` and the reread's lane at 04:41, before `3cf9d43`; both record `d3e5699`, committed while they ran (neither carries the `command` field `3cf9d43` added, which shows their code was older). Whether the checkout had local changes when they started is not known. The block records each carry a fingerprint of the code that made them, which is unaffected. **Fixed:** the commit, state and diff are now taken when `yoke` is imported, and a record written after the checkout changed carries `code_changed_while_running` with what it holds then (tested); the ledger refuses such a record unless its row says so (tested). Control B's sweep, started before this, records as before. |

## 18. The report and its claims: 20 November 2026

**Verdict:** the report's numbers match the results pages and Figure 1's 165
values check out; what had fallen behind was its reading of them. Version
1.6 states, in a new section "What the code audits found that bears on these
results", each finding that does, and fixes the wording points.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F18-01: the 2016 DC bins | high | **done**: stated, with the false candidates' distance from the DC channels and the comparison running; step 10's verdict stands. |
| F18-02: "95%" without its limit | high | **done**: called nominal block-bootstrap intervals, with the simulated 2016-like coverage (about 41%). |
| F18-03: what the false-candidate count counts | high | **done**: the union of the 19 wrong choices, up to about 19 times one choice's rate, a control, not a false-alarm rate. |
| F18-04: turboSETI's caveats | high | **done**: zero drift never searched, fast-drift frequency and drift outside the tolerances (60 detected, 5 credited), whole pipelines compared. |
| F18-05: "BLISS as published" | high | **done**: "BLISS run as its own pipeline", with how it was run, the port's checking and the two-ON events. |
| F18-06: 13,310 called the whole | medium | **done**: counted per session (13,310, 13,310 and 7,040). |
| F18-07: "none changes" against differences of up to two | medium | **done**: "a few signals at most, not changing one pipeline against the other". |
| F18-08: the report's records not checked against each other | medium | **agreed; planned**: a check of each record's session, provenance and counts before writing, with tests that mix records. |
| F18-09: references and Figure 1's axis | low | **done in part**: Enriquez et al. 2017, Isaacson et al. 2017, turboSETI 2.3.2 and BLISS at 2b98afe added; the axis is described in the caption. |

### 18, re-audited at 5f1b83d, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F18-02's wording joined two claims and misdescribed the intervals | high | **confirmed; fixed.** The report now says the false-candidate intervals are a bootstrap over blocks within each class (a Poisson upper limit where a class has none), that under correlated interference they hold the rate far less often than 95% (about 41% for 2016-like) and nothing tried fixes it, and, apart, that the window-resampled recovery intervals are a supplementary check that also falls short under strong correlation. |
| F18-08: records not checked against each other | medium | **built.** `tools/report.py` refuses to write unless the BLISS comparison is the 2017 session's, steps 10 and 12 are their sessions' under their frozen configs' SHA-256s, and the operating points name only the report's sessions (`tests/test_report_records.py` mixes records and is refused). |

## 19. Public repository and release readiness: 20 November 2026

**Verdict:** the repository is fit to be public as research software; the
findings are documents that lagged the code, and the release itself, which
is Ryan's decision (a tag, a GitHub release and a Zenodo DOI are permanent),
is not made here.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F19-01: no tag, release or changelog | high | **agreed; left for Ryan's go.** No tag or release is made without it. |
| F19-02: Zenodo described as done | high | **confirmed; fixed.** docs/publishing.md and docs/reproducing-results.md now say the deposits are planned and none is made yet. |
| F19-03: README behind the code | medium | **confirmed; fixed** (report 1.6, checks version 5, all three sessions), with `tests/test_docs_consistency.py` checking the README against the code's versions. |
| F19-04: release checks dated 19 November | medium | **agreed; planned** at the release commit, with that commit recorded. |
| F19-05: dependencies unpinned | medium | **built**: `requirements-tested.txt`, the versions the tests and runs were made with, usable as constraints; requirements.txt stays loose for ordinary installs. |
| F19-06: security checks historical | medium | **agreed; planned** at the release (history scan, Gitleaks, dependency checks). |
| F19-07: the report generator moved past 1.5 | medium | **done**: version 1.6 is written with the changes, a new revision, not a replacement (audit 18). |
| F19-08: "et al." as a name suffix in CITATION.cff | low | **confirmed; fixed.** Release date and DOI are added only when they exist. |

### 19, re-audited at fcbcc9d, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| The README still said "BLISS as published" | medium | **confirmed; fixed**, and the consistency test now refuses that wording. |
| The tested constraints pin four packages, are not linked, and CI does not use them | medium | **fixed in part.** The README now points at the complete recorded environment (`docs/environments/core-windows.txt`, every package) as constraints for an exact install; using it in CI is **planned**. |

## 20. Parallel processing and performance: 20 November 2026

**Verdict:** the records were the risk, and they are fixed first, as the
audit asks; the shared scheduler and its measured speed-up come after, with
equivalence tests.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| P20-01: block records written straight to their names | high | **confirmed; fixed.** Every block and run record of `matched.py` and `curved_pass.py` (the runs, the recheck, the tracks added, the orbit, vetting and turboSETI stages) goes through `yoke.write`: a temporary file, flushed, then replaced whole. The bytes are the same as before (tested), so records stay comparable with the packaged ones. |
| P20-02: a record counted done because it exists | high | **confirmed; fixed in part.** A record that does not parse is moved aside (`<name>.bad-<utc>`, kept to look at) and its block made again (`yoke.whole`, tested); provenance on resume and at the verdict is audit 17's. |
| P20-03: every shard rewrote blocks.json | high | **fixed for torn writes** (written whole, only when it differs); writing it once before the workers start comes with the scheduler. |
| P20-04: rechecks rewrote records in place | high | **confirmed; fixed** by the same whole writes. |
| P20-05: fixed shards idle | medium | **agreed; planned**: the shared queue of docs/parallel.md, longest blocks first. |
| P20-06: archive requests and memory not limited across workers | medium | **agreed; planned.** Seen here too: with WSL holding 12 GB, a third lane was not started tonight. |
| P20-07: one temporary name for every writer | medium | **confirmed; fixed.** Each writer has its own temporary file; on Windows a replace refused while another writer replaces the same file is tried again, and no temporary file is left (tested: six threads writing one record). |
| P20-08: the queue rewrites jobs.txt in place | medium | **agreed; planned.** |
| P20-09: no scheduler fault tests | high | **agreed; planned** with the scheduler. |

### 20, re-audited at 135c2b0, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| A broken record stopped the run before it could be set aside | high | **confirmed; fixed.** Both runners now test each record first (`yoke.whole`), then check provenance on the whole ones. |
| A record that parses counted as done | high | **confirmed; fixed.** A record counts only if it is this block's, with its format and its signals (`_record_ok`); otherwise it is set aside and the block made again (tested). None of the records on disk would be set aside. |
| The concurrency test missed failed writers | medium | **confirmed; fixed.** It collects every thread's failure, and a second test writes one record from four processes; no failure, no temporary file left. |
| The curved pass rewrote its run metadata each time | medium | **confirmed; fixed.** It writes `blocks.json` only when it differs, and refuses another choice or settings once blocks exist, as `matched.run` does. |
| Quarantine names could collide; unreadable taken for broken | medium | **confirmed; fixed.** Names carry a random suffix; a record that cannot be read at all raises rather than being moved. |
| `pipelines.py` still wrote its block record directly | medium | **confirmed; fixed** (`yoke.write`). |

## 21. Database and evidence storage: 20 November 2026

**Verdict:** the lifecycle defects are real in the code and fixed where they
can be without moving the store's history; the store itself passes SQLite's
own checks. Tests: `tests/test_store_lifecycle.py`.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| A21-01: checks go stale as the store grows | high | **agreed; planned** with the evidence revisions of audit 22 (also F12-03). |
| A21-02: checks saved one by one, so part of a set looked done | high | **confirmed; fixed.** A candidate's checks are saved in one transaction (`store.save_checks`), and a candidate counts as checked only with a whole set (`store.checked_events`: all ten), tested with a set cut off at three. |
| A21-03: a known ETag could be replaced by none | high | **confirmed; fixed.** Where the store knows a file's ETag or size, a read without one, or with another, is refused (tested). Separating a file from its place in a cadence is **planned**. |
| A21-04: a block with fewer than six looks could be saved | high | **confirmed; fixed.** `store.save_block` refuses, with nothing changed, unless it has six files (all different), six hit lists and six scans (tested). |
| A21-05, A21-06: block history and event lineage | medium | **agreed; planned.** |
| A21-07: the store's content compared by counts | medium | **confirmed; fixed.** `store.content` adds a hash of every row of every table, so a changed value shows (tested). |
| A21-08, A21-09: schema versions and references | medium | **agreed; planned.** |
| A21-10: no integrity check on the packaged store | medium | **confirmed; fixed.** The evidence package refuses a store that fails SQLite's `integrity_check` or `foreign_key_check`; the store as it stands passes both. |
| A21-11: the store and the records not one snapshot | medium | as F16-06, **planned**. |
| A21-12: indexes for vetting a growing store | high | **built**: a file's current hits by frequency, a candidate's checks, a session's current events by frequency. Measuring them at 1 to 50 million hits is **planned**. |

### 21, re-audited at a097087, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| R21-01: checks complete in the store with their record never written | high | **confirmed; fixed.** A candidate counts as checked only with a whole evaluation in the store **and** its record written at this checks version (`check.record_for`); otherwise it is checked again. |
| R21-02: parts of two evaluations counted as one | medium | **confirmed; fixed.** Checks are counted within one evaluation (event, lead and the time `save_checks` gives them all); a test writes three checks, then seven from another evaluation, and the event is not counted. |
| R21-03: the six scans' contents not checked | medium | **planned** with the cadence-membership table. |
| R21-04: file headers and cadence membership updated in place | medium | **agreed; planned** (the source version itself is fixed). |
| R21-05: hashing the whole store costs | medium | **measured**: 24.5 s for the whole store (0.7 GB, 1.9 million hits); fine at this size, and it grows with the store, so a sampled or per-table option is **planned** before the survey. |

## 22. Distributed volunteer computing: 20 November 2026

**Verdict:** the plan is not built, so most findings are requirements on its
design; they are now written into docs/multiuser.md ("Constraints from the
audit of this plan"). Two touched code that exists and are fixed.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F22-01: volunteer evidence could bury a confirmed candidate | critical | **agreed; written into the plan**: volunteer-only evidence cannot rank down a project-confirmed candidate until verified; escalation on the candidate's own detection. |
| F22-02: two agreeing answers do not show nothing was missed | critical | **agreed; written in**: coverage reported as verified, agreed or submitted, never agreement as completeness. |
| F22-03: identities need not be independent | high | **agreed; written in**: an attack simulation before pairing is trusted. |
| F22-04: occupancy cached by session only | high | **confirmed; fixed.** `occupancy.load` keys its cache to the session's current hits and blocks (`occupancy.revision`) and makes it again when they change. |
| F22-05: `save_block` could be given no scans | high | **confirmed; fixed.** Six scans are required (the one caller gives them); the strict intake for volunteers is written into the plan. |
| F22-06: tolerant comparison could hide a missing hit | high | **agreed; written in**: one-to-one hit pairing with unmatched counts and event comparison. |
| F22-07: an incomplete look counted as searched coverage | high | **agreed; written in** for the survey; changing check 6's background now would change the checks, so it goes into a checks version with its own comparison. |
| F22-08: redirects and hostile uploads | high | **agreed; written in.** |
| F22-09: the verification computer as the limit | high | **agreed; to be measured** in the simulated deployment. |
| F22-10: comparisons dropped with old submissions | medium | **agreed; written in**: each decision keeps the comparison record. |
| F22-11: the plan behind the code | medium | **confirmed; fixed**: its status lines now give steps 10 and 12 and ranking version 2 as they are. |

### 22, re-audited at 3a51f29, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F22-04: the occupancy revision missed a block searched again with only its completeness changed | medium | **confirmed; fixed.** The revision now hashes every block row and every current look's completeness of the session as well as the current hits' count and highest id (0.46 s for 2016's session); a test changes one block's completeness under the same run and the revision changes. |

## 23. Testing and regression coverage: 20 November 2026

**Verdict:** the two enforcement gaps are real and fixed; the rest is tests
to add. Checked first: no test has touched real records here (SSY_DATA is
set nowhere on this machine, and data/analysis/regress_step10.json is the
real run's of 03:46).

| Finding | Severity | Verdict and what was done |
|---|---|---|
| T23-01: tests kept SSY_DATA if it was set | high | **confirmed; fixed.** tests/synth.py now always gives the tests a fresh folder of their own and refuses if a project module was loaded with another first; `tests/test_isolation.py` passes with SSY_DATA pointed at the real data folder. |
| T23-02: the old onoff.py comparison could skip in CI | high | **confirmed; fixed.** CI checks out the whole history, and the test fails, not skips, in a clone that lacks the commit; it skips only where there is no git at all. |
| T23-03: no whole six-look pipeline test | high | **agreed; planned**: synthetic HDF5 files through reading, search, cadence test, store, checks, ranking and evidence. |
| T23-04: reader not tested against bad servers | high | **agreed; planned**: a mocked range server (200 for 206, 412, wrong Content-Range, truncated) and local HDF5 fixtures compared with h5py. |
| T23-05: one synthetic layout | medium | **agreed; planned** (property-based tests). |
| T23-06: migrations and processes | medium | **in part**: writers from four processes are tested (audit 20); an old-schema fixture is **planned**. |
| T23-07: external pipelines and real records not a release gate | medium | **agreed; planned** as a release workflow. |

### 23, re-audited at a5bd71a, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| T23-01: the guard accepted any folder under the temporary directory | medium | **confirmed; fixed.** tests/synth.py now refuses if a project module was loaded before it at all, so the tests' folder is always their own (checked: importing yoke first is refused); the isolation test also checks the folder is the one set for this run. CI run 87 ran 145 tests a job, the old-onoff comparison and the four-process writers among them. |

### 23, the whole-pipeline test, 20 November 2026

T23-03 is **built**: `tests/test_whole_pipeline.py` runs in CI, about a
minute. Six synthetic files of Green Bank's layout (two chunks of 16,384
channels, 16 spectra) are served over HTTP by a local server that answers
byte ranges and If-Match as the archive does, so the reader runs as it does
on the archive. Two tones are planted in the ON looks only, one in all six
looks and one in the ON looks and an OFF look. The test then runs the sweep
(every hit and event into the store), a second sweep (it resumes, searching
nothing again), `check.py`, the session's OFF null, the ranking, and
`check.py` again (nothing is checked twice). It checks that both ON-only
tones are the only candidates, the all-looks tone is interference, each
candidate has all ten checks and a report, both are ranked with the
session's own OFF null, the store passes its integrity checks and the sweep
record matches the store.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| The OFF null could be measured only on the 2017 session's saved cadences | high | **found by the test; fixed.** `ranking.off_null` always read `data/reference`'s cadences, and `ranking.context` rightly refuses an OFF null from another session, so no other session could be ranked in full, only with `--partial`. `ranking.py offnull --session S` now measures it on the session's own searched blocks (five by default, chosen by seed, read again) and keeps it apart (`off_null-S.json`); the 2017 record is unchanged. |
| A report folder fixed at import | low | **fixed.** `check.check_event` reads `check.REPORTS` when called, so a test can keep its reports out of `docs/leads`. |
| One test's store leaking into another's | medium | **found; fixed.** All tests share one data folder; `test_evidence` leaves a minimal store there, which the new test then found. The new test uses a data folder of its own. |
| Store tests that passed only after another test | medium | **found; fixed.** Two of `test_store_lifecycle`'s tests failed when that file ran alone (checked at the commit before: run 1, which they save blocks under, was made by another test). The file now makes it itself. |
| T23-06: a store of an older schema | medium | **built**: `test_store_lifecycle` makes a store as schema 2 had it and checks the migration to schema 3 (audit 24). |

## 24. Large-scale survey strategy: 20 November 2026

**Verdict:** the next step is a small survey pilot fixed in advance, not a
large sweep, and the store needs cadence identities first. The defect
found is real in the schema and now guarded; nothing has been overwritten
(the store holds one cadence a session).

| Finding | Severity | Verdict and what was done |
|---|---|---|
| F24-01: blocks keyed by session, so a second cadence of a session would supersede the first | critical | **confirmed; guarded.** `store.save_block` refuses files that are not the session's own cadence in the store (tested), so no cadence can supersede another; cadence ids, with the store's records migrated, are **planned** before any survey. |
| F24-02: a sweep finds its cadence at run time | high | **agreed; planned**: survey work from an explicit, fixed manifest. |
| F24-03: no archive-wide population | high | **agreed; planned**: a metadata census, frozen, every exclusion recorded. |
| F24-04: searched width counted blocks cut short | high | **confirmed; fixed in part.** A sweep now reports the width searched completely beside the width searched; coverage masks for edges and DC bins are **planned**. |
| F24-05: choosing sessions by how the search does on them | high | **agreed; stated**: step 12's gate stays a one-off; a survey's population is fixed apart from detections. |
| F24-06: a new session without its OFF null stops the ranking after the checks | high | **confirmed; fixed.** The checks are saved and the run says the ranking waits and why, rather than failing; a per-session calibration state is **planned**. |
| F24-07: survey-scale controls | high | **agreed; planned**: independent negative-control cadences, thresholds fixed beforehand. |
| F24-08: recurrence visits every file per candidate | medium | **agreed; planned**: a benchmark, then set-based retrieval with the same matching. |
| F24-09: no resource budget | medium | **agreed; planned** (about 92 GB and 1.9 hours a 2017-like cadence, measured here). |
| F24-10: the survey's objective | medium | **agreed; planned**: fixed before the first survey observation. |

### 24, re-audited at 3f3d39f, 20 November 2026

| Finding | Severity | Verdict and what was done |
|---|---|---|
| The sweep registered a second cadence's files before the guard refused it, which would then block the session's own cadence | high | **confirmed; fixed.** The sweep now refuses a second cadence of a session before any file is registered; the three sessions' own cadences pass the check unchanged. |
| Unknown completeness counted as complete | medium | **confirmed; fixed.** A sweep counts a block as searched completely only when it is known to be; `save_block` records a block's completeness as unknown when any look's is missing (tested: true, false, missing and null). |
| `check.run` waited on any refusal | medium | **confirmed; fixed.** Only the missing OFF null is waited for; any other refusal still fails the run. The cadence check is `store.cadence_conflict`, tested: its own cadence passes, another of the session is refused, a new session is free. |

### 24, cadence keys, 20 November 2026

F24-01 is **built**: store schema 3. A `cadences` table and its
`cadence_files` keep each cadence's six files in order. Blocks, looks, hits
and events are kept under their cadence's key, in the column that held the
session: for a session's first cadence the key is the session's own name,
so every row of every existing store keeps its meaning and nothing is
rewritten; another cadence of the same session is kept under SESSION-c2,
-c3. The sweep registers its cadence and keeps everything under its key;
given files now win over the target's kept cadence, so another cadence of a
target can be swept. The checks, the recurrence files, the target and the
OFF null find a cadence's files through its key.

| Check | Result |
|---|---|
| A store of schema 2 opened by the new code | migrated: each session's cadence registered under its name (tested) |
| A copy of the real store migrated | the three sessions' cadences registered; for each, its files, check 6's recurrence files both ways and its target **identical** to before; integrity clean |
| Two cadences of one session | each kept under its key, neither superseding the other; one cadence's files refused under the other's key (tested) |
| The whole pipeline with a second cadence of the session | swept, checked and ranked under SESSION-c2 with its own OFF null; the first cadence's blocks untouched (`test_whole_pipeline`) |

The real store migrates the first time a process opens it with this code;
the migration only adds tables and rows.

## 25. Diagnostic and measuring tools: 20 November 2026

**Verdict:** started. The aim is that every diagnostic is shown to catch a
planted fault in what it measures, not only to agree with the current code.

| Finding | Severity | Verdict and what was done |
|---|---|---|
| D25-01: a result could not be tied to the command that made it | high | **confirmed; fixed.** `yoke.provenance` now records the command and a hash of the script it ran. A new tool can be run before it is committed, and then its commit says nothing about its code. |
| D25-02: a result made with uncommitted changes kept only a hash of the diff | high | **confirmed; fixed.** The diff itself is now kept under `data/provenance/diffs/` (by its hash), so such a result can be made again exactly. Of the result files behind the ledger below, 7 were made with local changes before this; the ledger marks them "diff not kept". |
| D25-03: no check that the evidence named for a finding exists and is what it claims | high | **built.** `tools/ledger.py` checks each row of the ledger against its result file's own provenance: the file there, the commit, the commit in this checkout's history, the state, the command. `tests/test_ledger.py` shows each kind of wrong row failing. |
| D25-04: the six faults the re-audits found in the tools | high | **each has a test that fails if it returns**, written in its re-audit: equal totals with swapped signals (`test_injection_checks`), the wrong event credited (`test_rfi2016`), ON looks at odd places (`test_false_checks`), recovery by frequency alone (`test_coverage_checks`), intervals of different quantities (`test_statistical_checks`), turboSETI's rows and members (`test_turbo_checks`). |
| D25-05: an equivalence test that its data cannot fail | critical | **confirmed in three of them; fixed.** A test that a diagnostic copy equals the frozen code proves nothing where its data never reaches the code that could differ. `tests/test_planted_faults.py` plants a small fault in one side and requires the same comparison to see it. It found: **the cadence test's version comparison** (`test_onoff_equivalent`, the basis on which the BLISS hybrid page's records were accepted, audit 7) could not see OFF_MAX moved, since its cadence's OFF evidence was all far above 6 or absent; **the search copy's** could not see the cut or the re-sum's reach moved (one hit at the cut, no strong tone at extreme drift); **the curved copy's** could not see its acceleration limit (every planted acceleration inside both limits). Each now runs on data that straddles what it compares (`synth.judging_cadence`: an OFF echo at S/N 5.5 under OFF_MAX 6, a third ON look at 5.5 over ON_MIN 5; hits just over the cut and a strong tone at -3.9 Hz/s; a tone accelerating at 2e-3, past the limit 1e-3). Every planted fault is now seen, **and the equivalences still hold on the stronger data**: the earlier onoff.py judges the threshold cadence exactly as the current one, so the hybrid page's acceptance stands. |
| D25-06: the other tools under `tools/` | high | **built in part** (21 Nov 2026). Of the tools behind the ledger's rows, those with no test of their own now have planted-fault tests (`tests/test_tool_faults.py`): `bliss_checks.py pins` (a changed pin, a missing run), `bliss_checks.py events` (a dropped member moves an event from three ON looks to two; a doubled event is not counted twice), `completeness_checks.py records` (a flipped capped flag moves the block, a shifted frequency reaches the errors, swapped occupancy moves the shares). **One was a defect:** the pin check looked only at the runs a record listed, so a record missing one run's provenance, or all of it, passed as pinned; both runs are now required, and all 242 recorded runs still pass. `dc_checks.py`: its two reads of a block are shown to run under the two DC rules (the switch reaches the reader at each read, not once at import), so its identical counts (audit 14) compare two rules, not one twice. `detector_misses.py`'s look: a signal said to be 40 channels from where it is loses its matching hit and its track S/N, and a stronger tone crossing its track shows as blanked pixels. `completeness_checks.py pairs` and `shadow`: the switches they compare are shown to change the answer (without the corridor a second signal lost beside the first is found; shadow refresh changes the hit list), so their comparisons are not of the search against itself. Still to do: the classification in `completeness_checks.py strong`, which reads the archive. |

## 26. Following up a real candidate: 20 November 2026

**Planned.** What exists: the ten checks and their report for every
candidate (`docs/leads/`), the stamps of the six looks kept in the store,
the ranking, and `pipelines.py followup` (pickles' windows and turboSETI's
own noise at a candidate). What the audit is to settle: the evidence frozen
for a candidate the moment it ranks high (its looks' raw slices, the code
and records that judged it, with hashes), checks someone else can repeat
from that alone, the other sessions and pointings of the same target in
the archive, interference databases, and what would justify asking for a
repeat observation, which is the person's to ask for.

## Evidence for the material findings

Each material finding with the result it rests on: the file under `data/`,
the commit it was made at and whether the code had local changes, and the
command. `python tools/ledger.py` checks every row against the file's own
provenance. Results still running are not listed until they finish.

| Finding | Audit | Result | Made at | Command |
|---|---|---|---|---|
| The hit cap costs recovery in crowded looks; offsets of found and missed signals | 6 | `data/analysis/completeness_records.json` | `34ed0ed`, clean | `tools/completeness_checks.py records` |
| 42% of close second signals at fast drift lost beside the first | 6 | `data/analysis/completeness_pairs.json` | `c6388b4`, local changes (diff not kept) | `tools/completeness_checks.py pairs` |
| A lone signal lost under a global cap, found under a budget a region | 6 | `data/analysis/completeness_cluster.json` | `749c7c2`, clean | `tools/completeness_checks.py cluster` |
| 6 of BLISS's 8 detector misses are the hit cap, 2 just outside the tolerances | 6, 7 | `data/analysis/bliss_only/detector_misses.json` | `3fd7837`, clean | `tools/detector_misses.py` |
| The voltage cross term and two polarizations move recovery by at most 12 of 880 | 2 | `data/analysis/injection_voltage.json` | `865d3e0`, clean | `tools/injection_checks.py voltage` |
| Planting after DC blanking finds at most 2 more of 96 | 2 | `data/analysis/injection_dc.json` | `03f5836`, clean | `tools/injection_checks.py dc` |
| Fixed S_in against one injected power: within 2 of 880 | 2 | `data/analysis/injection_power.json` | `8477399`, clean | `tools/injection_checks.py power` |
| The step 10 records made again match the evidence package | 17 | `data/analysis/regress_step10.json` | `ea81329`, clean | `tools/regress_step10.py` |
| The false rate's combined interval, mended | 4, 8 | `data/analysis/false_interval.json` | `ea81329`, clean | `tools/false_checks.py interval` |
| One wrong choice against the union of 19 | 4 | `data/analysis/false_assignments.json` | `8477399`, clean | `tools/false_checks.py assignments` |
| What changes identity under other rules of one signal | 4 | `data/analysis/false_grouping.json` | `8477399`, clean | `tools/false_checks.py grouping` |
| The rate's interval with windows of consecutive blocks | 4, 8 | `data/analysis/false_windows.json` | `8477399`, clean | `tools/false_checks.py windows` |
| Intervals' limits on all three sessions | 8 | `data/analysis/statistical_checks.json` | `8eed705`, local changes (diff not kept) | `tools/statistical_checks.py all` |
| 2016's false candidates: one hit and two tracks, crowded, capped | 5 | `data/analysis/rfi2016_records.json` | `f3f50bb`, local changes (diff not kept) | `tools/rfi2016.py records` |
| All 11 candidates' verdicts and checks unchanged under checks version 5 | 12 | `data/analysis/vetting_checks.json` | `342045e`, local changes (diff not kept) | `tools/vetting_checks.py` |
| turboSETI's reported frequency and drift on synthetic tones | 3 | `data/analysis/turbo_reference.json` | `5e29bbd`, clean | `tools/turbo_checks.py reference` |
| Seven kinds of signal through the unchanged search | 15 | `data/analysis/coverage_checks.json` | `b567c6e`, local changes (diff not kept) | `tools/coverage_checks.py` |
| The detector's refresh reach, noise spread and non-finite input, synthetic | 9 | `data/analysis/detector_checks_synthetic.json` | `8199c56`, local changes (diff not kept) | `tools/detector_checks.py synthetic` |
| The cadence test's asymmetry, blind OFF looks and weak ON looks, synthetic | 11 | `data/analysis/onoff_checks_synthetic.json` | `5de5877`, clean | `tools/onoff_checks.py synthetic` |
| BLISS's runs match their pins (all 242, both runs of every record required) | 7 | `data/analysis/bliss_pins.json` | `5b2875e`, clean | `tools/bliss_checks.py pins` |
| Step 10's blocks replayed from a fresh clone, fresh environments and the evidence package alone: identical | 16 | `data/analysis/fresh_replay.json` | `dcc383f`, local changes | `tools/fresh_replay.py` |
| turboSETI's losses are in its detector; the zero-drift trial changes nothing | 3 | `data/analysis/turbo_checks.json` | `b03c828`, clean (rerun; the checkout changed while running, to `71b4d4e`, with `yoke`, `seti`, `matched`, `turbo_checks` and `turbo_diag` unchanged; found, stages, pairs and members equal the earlier record, kept as `turbo_checks-as-of-d3e5699.json`) | `tools/turbo_checks.py blocks` |
| Time order changes no wrong choice's candidates | 4 | `data/analysis/false_chronological.json` | `d3e5699`, clean | `tools/false_checks.py chronological` |
| The hit cap is not the cause of 2016's false candidates; two ON hits would cut them by 86% | 5, 6 | `data/analysis/rfi2016_reread.json` | `d3e5699`, clean (as recorded; the run started before 3cf9d43, commit and state then unknown: F17-08) | `tools/rfi2016.py reread` |
| The strong fast misses are detected and measured outside the tolerances | 6 | `data/analysis/completeness_strong.json` | `d3e5699`, clean | `tools/completeness_checks.py strong` |
| Shadow refresh changes no count that matters | 6 | `data/analysis/completeness_shadow.json` | `d3e5699`, clean | `tools/completeness_checks.py shadow` |
| The detector's confirmed faults change no candidate at 30 on 12 blocks | 9, 11 | `data/analysis/detector_checks_blocks.json` | `d3e5699`, clean | `tools/detector_checks.py blocks` |
| The curved matcher's first-wins and blind OFF looks change nothing on ten blocks | 10 | `data/analysis/curved_checks.json` | `d3e5699`, clean | `tools/curved_checks.py blocks` |
| The two DC rules give identical counts on eight 2016 blocks | 14 | `data/analysis/dc_checks.json` | `d3e5699`, clean | `tools/dc_checks.py` |
