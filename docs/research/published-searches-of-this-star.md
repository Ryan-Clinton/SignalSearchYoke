# Published searches this result can be set against

Research of 9 November 2026: what has been published on KIC 8462852 from
radio data, whether Painter et al. 2025's archive search covered this
cadence, and which archive re-analyses publish per-star results.
UNVERIFIED marks what could not be confirmed.

## Bottom line

- **No published radio result on KIC 8462852 from Breakthrough Listen or
  Green Bank was found**, for any session, AGBT17A_999_68 included, and no
  public hit, event or candidate list for it. Harp et al. 2016 (ATA) is the
  published radio limit.
- **Painter et al. 2025 publishes no target, cadence or candidate list**,
  so whether its archive search covered this cadence cannot be checked from
  what is public (UNVERIFIED either way).
- **No archive re-analysis found publishes per-star hit tables** for this
  star or session. A signal-by-signal comparison with a published search of
  these files is not possible; a pipeline-against-pipeline comparison on
  the same files is.

## 1. Painter et al. 2025, "A Novel Technosignature Search in the Breakthrough Listen Green Bank Telescope Archive"

- C. Painter, S. Croft, M. Lebofsky, A. Andersson, C. Choza, V. Gajjar,
  D. Price, A. Siemion. AJ 169(4), 222, 24 March 2025,
  doi:10.3847/1538-3881/adbc5e; arXiv:2412.05786 (v1 8 Dec 2024, v2 5 Aug
  2025). https://arxiv.org/abs/2412.05786;
  https://iopscience.iop.org/article/10.3847/1538-3881/adbc5e
- **Sample:** AJ and v1: 9,684 cadences of 3,077 stars; v2: 6,630 cadences
  of 2,623 stars (its own Table 1 sums to 6,330). The whole GBT archive at
  the Berkeley data centre as of July 2023 (not data held at Green Bank).
- **Data:** the fine .h5 product (2.79 Hz for 96.4%, 2.84 Hz for the rest,
  about 18 s); 187.5 MHz node files (67.8%) or spliced full-band files
  (32.2%); L, S (1.8-2.8 GHz, 710 MHz usable), C and X; cadences of 3 ON
  and 3 OFF five-minute scans.
- **Method ("pickles", not turboSETI):** Fisher kurtosis in overlapping
  1,024-channel blocks (2.86 kHz). Level 0: a hotspot (MAD > 5σ) in at
  least two ON scans, dense interference bands masked. Level 1: median ON
  kurtosis ≥ 0.5 and maximum OFF kurtosis ≤ 0.25. Level 2: drops drift
  under 0.01 Hz/s, broadband signals and blips. Drift ±4 Hz/s. Limits
  quoted at SNR 10 (the pipeline said to work to about SNR 6 with fewer
  signals found).
- **Results:** every Level 2 block inspected by eye (14,168 blocks in v2;
  679 targets in v1, 838 in v2); 75 drifting signals ON and absent OFF,
  all judged likely interference. Transmitters brighter than about 0.3
  Arecibo-radar equivalents ruled out at fewer than 1% of stars. EIRP_min
  about 8.2×10¹⁴ W (L) to 1.2×10¹⁵ W (X) at 1,000 pc, about 2×10¹² W at
  50 pc. (Scaled to 434.6 pc by d², 8.2×10¹⁴ W is about 1.5×10¹⁴ W, the
  same order as this search's 1.6×10¹⁴ W at the cut: this project's
  arithmetic, not the paper's.)
- **What is public:** Tables 1-7 as machine-readable ASCII on the AJ page
  (band statistics, interference masks, figures of merit), none listing
  targets, cadences or candidates; no data statement, no Zenodo deposit.
  A few candidate stars named in the text (HIP and GJ names). The code,
  https://github.com/UCBerkeleySETI/pickles, holds only `pickles.py` and a
  licence.
- **KIC 8462852:** "8462852", "Boyajian", "Tabby", "KIC" and "Kepler"
  searched in the full text of arXiv v1, v2 and the AJ HTML: not found.

## 2. Radio searches of KIC 8462852

- **Harp et al. 2016, ApJ 825, 155 (ATA)**, arXiv:1511.01606: 1-10 GHz in
  40 MHz steps, 0.7 Hz channels, drifts ±1 Hz/s in 0.007 Hz/s steps, 6.5σ,
  454 pc. Narrowband: about 180-300 Jy in a 1 Hz channel, EIRP (4-7)×10¹⁵
  W. Moderate band: 10 Jy in 100 kHz, about 10¹⁹ W. Narrowband runs in
  October 2015 (Table 1; the text's dates conflict).
  https://iopscience.iop.org/article/10.3847/0004-637X/825/2/155
- **Breakthrough Listen's 2016 Green Bank campaign** (eight hours a night
  on three nights, 1-12 GHz) was announced in the press
  (https://earthsky.org/space/tabbys-star-greenbank-telescope-breakthrough-listen/);
  no BL paper or web release of its radio results found. A "Penn State
  study" with BL instruments at GBT in 2016-17 was mentioned in a search
  snippet; not found (UNVERIFIED).
- **Breakthrough Listen in print on this star is optical:** Lipman et al.
  2019, PASP 131, 034202 (arXiv:1812.10161), 177 APF spectra searched for
  laser lines.
- **Lacki et al. 2021, "One of Everything"** (ApJS 257, 42;
  arXiv:2006.11304): Boyajian's star is Exotica 696 (450.8 pc), in the
  Anomaly sample, marked "+": "not part of I17 sample but has been observed
  in Breakthrough Listen campaign". So it is not in Isaacson et al. 2017's
  list, from which Price 2020, Ma 2023 and others drew. No results
  reported. http://seti.berkeley.edu/exotica/;
  https://doi.org/10.5281/zenodo.4726253
- The star's name searched in the full text and not found: Price 2020
  (arXiv:1906.07750), Traas 2021 (2101.11137), Ma 2023 (2301.12670), Choza
  2024 (2312.03943), the blc1 verification (2111.06350), UCLA/Margot
  (1802.01081, 2011.05265, 2308.02712, 2605.05408). Franz 2022 and Gajjar
  not checked (TESS and Galactic Centre samples; UNVERIFIED).
- An ATA 2017 follow-up: none found (UNVERIFIED that none exists).

## 3. Archive re-analyses with per-star output

- **Ma et al. 2023** (820 stars, ML): eight named signals of interest (for
  example HIP 13402, 62207, 56802, 118212); no public machine-readable hit
  table found.
- **Choza et al. 2024:** turboSETI at SNR 10, ±4 Hz/s.
- **UCLA (Margot et al.):** L-band only (1.15-1.73 GHz), no overlap with
  this S-band cadence; interesting signals go to the citizen-science site
  arewealone.earth; no downloadable hit table found.
- None publishes a hit list for KIC 8462852 or for AGBT17A_999_68.
