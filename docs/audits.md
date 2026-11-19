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
| 1 | Scientific methodology | 1 | critical | **done** (19 Nov 2026), see below |
| 2 | Signal injection accuracy | 1 | critical | to do |
| 3 | turboSETI comparison fairness | 1 | critical | to do |
| 4 | False-positive methodology | 1 | critical | to do |
| 5 | The 2016 interference failure | 1 | critical | to do |
| 6 | Detector completeness and missed signals | 1 | high | to do |
| 7 | BLISS comparison | 1 | high | to do |
| 8 | Statistical analysis and uncertainty | 1 | high | to do |
| 9 | Core narrowband detection algorithm (`searching.py`) | 2 | high | to do |
| 10 | Curved Doppler search | 2 | high | to do |
| 11 | ON/OFF cadence matching (`onoff.py`) | 2 | high | to do |
| 12 | Candidate vetting and ranking | 2 | high | to do |
| 13 | Instrument calibration and sensitivity | 2 | high | to do |
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
