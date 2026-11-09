# What comparable searches do that this one does not

Research of 9 November 2026: SETI@home's final analysis, hyperseti,
BLISS, seticore, the pipeline comparisons published, searches for other
signal types, ranking with planted signals, and interference histories.
UNVERIFIED marks what could not be confirmed.

## Bottom line

1. **Discovery completeness is measured by SETI@home only:** planted
   "birdies" counted as uncovered when they rank in the top 100 of the
   real multiplets; candidate sensitivity is the power at which 80% are
   uncovered. This search measures detection completeness (kept to the
   end), not where a planted signal would rank.
2. **The published pipeline comparison closest to this data** is Margot
   et al. 2023: 10,000 chirps in raw voltages, turboSETI on 2.98 Hz × 51
   spectra (about 17.1 s, close to these files) recovered 5.7% against
   UCLA's 94%, at equal injected power and equal tolerances. This search's
   desmearing makes that comparison directly testable here.
3. **Cross-session interference histories** (SETI@home's frequency zones
   over 14 years, Price 2020's similar events at other stars, Margot's
   dense and permanent interference bands) are how professional searches
   reject what one cadence cannot.
4. **Other signal types** need other products or other paths: BLIPSS and
   Gajjar 2022 work on coarse, fast products; setigen can plant
   non-linear and intermittent signals in this product.

## 1. SETI@home (front end arXiv:2506.14718, back end 2506.14737)

- **Drift:** ±100 Hz/s, "as many as 123 000 drift rates" a workunit; steps
  0.0009 Hz/s under 50 Hz/s and 0.015 Hz/s from 50 to 100 (about 114,000
  by that arithmetic; the gap to 123,000 is not explained). Coherent
  dedrifting (each trial chirp mixed to baseband): not transferable to
  filterbank data as it stands.
- **Resolutions:** 15 DFT lengths, 2³ to 2¹⁷ (1,221 Hz to 0.075 Hz); the
  128k length, 13.4 s, matches the 13.7 s beam crossing.
- **Signal types:** spike (power over 24× the mean); Gaussian (the beam's
  shape in time: reduced χ² < 1.42, null fit > 2.256); pulse (folded, 1.6
  ms to 35.79 s, about one false alarm a workunit); triplet (about 9× the
  mean); autocorrelation (delays to ±6.7 s, 17.8× the mean).
- **Interference:** Arecibo's radar blanked (about 2.5% lost); frequency
  and period zones over 14 years (a 30-point median on a log-period
  histogram); drifting "triangle fans"; pulse and triplet filters within
  10 minutes; multi-beam coincidence (1 ms to 13 s); spikes under 0.086
  Hz/s drift flagged. 10.8% of detections flagged; 11.5% of birdie spikes
  lost.
- **Birdies:** 3,000 (1,500 barycentric, 1,500 with planetary orbits), 100
  per DFT length per class, power 18-33 or 18-50, added as detections
  before interference removal. Spikes only; Gaussian and pulsed birdies
  left as future work.
- **Scoring:** multiplets grouped by HEALPix NSIDE 2¹¹ (a 0.05° disk), 250
  Hz barycentric or 308 kHz non-barycentric; three −log P scores (power,
  density, time), each scaled so its 25th and 75th percentiles are ±1;
  seven combinations examined.
- **Ranking efficiency:** a birdie is "uncovered" if its multiplet ranks in
  the top 100 non-birdie multiplets; candidate sensitivity is the power at
  which ≥80% are uncovered (Table 8). The paper argues for quoting
  candidate sensitivity, not detection sensitivity.
- **Follow-up:** about 1,000 top multiplets inspected, about 200 chosen,
  92 FAST slots, 80 re-observed when written; outcome not in the sections
  read.

## 2. hyperseti and BLISS

**hyperseti** (https://github.com/UCBerkeleySETI/hyperseti,
https://hyperseti.readthedocs.io/en/latest/): spectral kurtosis flags;
normalisation (x − mean)/std; a polynomial bandpass fit; edge and extrema
blanking; brute-force GPU dedoppler. An optional "ddsk" kernel measures
kurtosis along each drift path (Voyager's carrier 0.385, its sidebands
about 4 to 5). Drift plans: "optimal" (steps of df/t_obs) or "stepped"
(doubling every T trials); `max_dd` 10 Hz/s in the example. Smearing: a
boxcar of 2 up to `smearing_nchan_max`, scaled by √N. Hits: local maxima
with an exclusion distance, then iterative blanking (`n_blank`) and search
again; `merge_boxcar_trials`; SNR 20 in the example. No ON/OFF stage; no
published speed or injection figures.

**BLISS** (https://github.com/UCBerkeleySETI/bliss; documentation pages
empty, read from source): filter roll-off flagged at 0.2, spectral
kurtosis (0.05, 25); noise by standard deviation or MAD over unflagged
data; `desmear=true`, rates −500 to 500 drift steps; hits by connected
components (default) or local maxima, SNR 10, `neighbor_l1_dist=7`.
`event_search`, an ON/OFF stage: ON hits linked by 0.01 × the frequency
difference at a "rendezvous" time plus 10 × the drift difference squared,
cut at 50 (a "made up number" in the code's comments); an event is
rejected if any OFF hit lies within that distance; at least 2 ON hits. No
benchmarks found.

## 3. seticore (https://github.com/lacker/seticore)

A GPU Taylor-tree dedoppler (turboSETI's algorithm); noise from the median
and standard deviation of the central 90% of drift sums; one hit per
window of `2*ceil(max_drift*timesteps)` channels, merged by
`makeHitGroups`. At MeerKAT (BLUSE, arXiv:2607.23651): upchannelised to
about 1 Hz, beamformed, ±10 Hz/s (±44 Hz/s cited as the 99% target), SNR
6, voltage "stamps" kept for each hit; validated on JWST at S-band; no
injection test, no comparison with turboSETI. Green Bank use: UNVERIFIED.

## 4. Comparisons of pipelines at matched sensitivity

- **Margot et al. 2023** (arXiv:2308.02712): 10,000 linear chirps in raw
  voltages, ±8.86 Hz/s, S/N about 20; recovered if within ±6 Hz and ±0.05
  Hz/s. UCLA: 94.0% (98.7% outside dense interference). turboSETI (2.98 Hz,
  51 spectra, ±8.88 Hz/s, SNR 10): 5.7%, 99.1% of them under 1 Hz/s;
  smearing blamed. Metric: recovery at equal injected amplitude and equal
  tolerances.
- **Choza et al. 2024** (arXiv:2312.03943): two runs of 640 setigen
  signals; efficiency falls about as 1/N beyond the unit drift (0.153
  Hz/s); turboSETI 2.3.2 skips zero drift (a factor of 2); its 5% trimming
  makes SNR 10 about 3.3 true σ. Recommends a drift-dependent boxcar
  (this search has one).
- **Margot et al. 2021** (arXiv:2011.05265): a BL-style ±600 Hz blanking
  run on their hits kept 10× fewer (1.05 M of 10.1 M); hit density 2.2×10⁻²
  against Price 2020's 1.1×10⁻⁴ hits per hour per Hz.
- A "GPU turboSETI" paper: not found (UNVERIFIED).

## 5. Non-linear, pulsed and wide signals

- **BLIPSS** (Suresh et al. 2023, arXiv:2305.18527): a fast folding search
  on kHz-wide dynamic spectra, periods 11-100 s, duty cycles 10-50%, 7σ;
  needs coarse channels at high time resolution, not the 2.79 Hz product.
- **Gajjar et al. 2022** (arXiv:2205.02964): broadband pulsed beacons,
  negative dispersion included, 1,883 stars, GPU pipeline and ML
  classifier; fewer than 1 in 1,000 stars at ≥10⁵ W/Hz with periods ≤500 s.
- **setigen** (https://setigen.readthedocs.io/en/main/basics.html): paths
  `sine_path`, `squared_path`, `simple_rfi_path` (a random walk) and custom
  ones; `sine_t_profile` for intermittent signals; Gaussian and
  multi-Gaussian frequency profiles. These plant signals beyond the linear
  drift.
- A published curvature (non-linear drift) search of BL data: none found
  (UNVERIFIED).

## 6. Ranking with planted signals

- **SETI@home:** the top-100 rank and the 80%-uncovered power (section 1):
  the only full measure of discovery completeness found.
- **Margot 2021:** of 18,093 injected signals detected, 99.73% passed the
  filters; those lost mostly crossed dense interference. Pairing: the
  propagated difference F = (f_i − f_j) + mean drift × Δt, minimised by
  stable matching (Gale-Shapley), one partner a scan; drifts within 2 ×
  0.0173 Hz/s; zero drift rejected.
- **GLOBULAR** (Jacobson-Bell et al. 2025, arXiv:2411.16556): 100 planted
  events (300 hits) at SNR 10³-10⁴; turboSETI kept 86 events, GLOBULAR's
  clustering 69; removes 93.1% of false hits and 99.3% of false events, 13
  features, HDBSCAN.
- **Ma et al. 2023** (arXiv:2301.12670): 8 candidates from 820 targets;
  ranking metrics and re-observation outcome UNVERIFIED from the abstract.

## 7. Interference histories

- **Price 2020:** hit density per MHz; events grouped in 125 kHz bins; OFF
  veto within ±600 Hz; events rejected by hand when like events recur at
  other stars (22 events at 2200.04-2200.5 MHz).
- **SETI@home:** frequency zones with persistent excess over 14 years
  removed.
- **GLOBULAR:** occupancy clusters line up with GPS L3/L5, Iridium and
  1420 MHz.
- **Margot:** "dense" and "permanent" interference bands (Margot 2021
  Table 2; Pinchuk 2019); no numeric occupancy threshold in what was read.
- A Breakthrough Listen GBT interference database paper: not found
  (UNVERIFIED).
