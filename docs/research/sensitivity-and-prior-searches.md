# Research: sensitivity, figures of merit and prior searches

Research notes for the overhaul ([../overhaul.md](../overhaul.md)), 8 November
2026. Each claim carries its source; UNVERIFIED marks what could not be
confirmed.

**The main correction:** Lipman et al. 2019 is not a Green Bank radio search.
It is an **optical laser-line search** with the Lick Automated Planet Finder
(APF): 177 spectra, 374–970 nm, a limit of about 24 MW, at an assumed 1470 ly
(https://arxiv.org/abs/1812.10161). The project's May 2017 GBT data
(AGBT17A_999_68) are therefore not Lipman's data. No published radio result
from Breakthrough Listen's GBT observations of KIC 8462852 was found; the
observations began 26 Oct 2016
(https://astrobiology.com/2016/10/25/breakthrough-listen-to-observe-tabbys-star-kic-8462852/).
A narrowband limit from this cadence may be the first published for these
data. That is UNVERIFIED: Painter et al. 2025 searched 9,684 GBT cadences of
3,077 stars from the BL archive
(https://iopscience.iop.org/article/10.3847/1538-3881/adbc5e), and whether
KIC 8462852 is among them was not established.

**A flaw that affects the headline numbers:** `plant()` in `seti.py` puts each
tone's full power into one channel per 18 s spectrum, whatever its drift.
Real data spread a drifting signal's power across channels within each
integration.

- One channel per integration is 2.79 Hz / 18.25 s ≈ 0.153 Hz/s (the "unit
  drift").
- At 3.6 Hz/s a real tone crosses about 24 channels per spectrum, so each
  channel gets roughly 1/24 of its power.
- Tones are planted at channel centres, so the loss for a tone between two
  channels (sinc² response) is not measured.

The current completeness figures (30% at SNR 10 … 100% at SNR 20, drifts to
3.6 Hz/s) therefore overstate completeness above about 0.15 Hz/s. Choza et al.
measured exactly this loss in turboSETI (below).

## 1. Sensitivity and figures of merit

- **Narrowband minimum flux density (Enriquez 2017, Eq. 4):**
  S_min = SNR_min · (SEFD/δν_t) · √(δν / (n_pol τ_obs)); EIRP_min = 4π d² S_min;
  SEFD = 2k_B T_sys / A_eff; transmitter bandwidth δν_t taken as 1 Hz
  (https://ar5iv.labs.arxiv.org/html/1709.03491).
- **CWTFM (Enriquez 2017, Eq. 11):** CWTFM = ζ_AO · EIRP / (N_stars · ν_rel),
  with ν_rel = Δν_tot / ν_mid.
  - ζ_AO is set so that CWTFM = 1 at EIRP = 10¹³ W (the Arecibo radar),
    ν_rel = 1/2 and N_stars = 1000.
  - Transmitter rate = (N_stars · ν_rel)⁻¹.
  - Enriquez used SNR 25, ±2 Hz/s and SEFD 10 Jy, and got S_min ≈ 17 Jy and
    "<~0.1% of stars within 50 pc host a 10¹³ W transmitter".
  - No injection tests and no measured drift loss, though it notes smearing
    above about 0.167 Hz/s.
- **Price et al. 2020** (https://ar5iv.labs.arxiv.org/html/1906.07750):
  - F_min = SNR · (2k_B T_sys/A_eff) · √(B/(n_pol t)).
  - TFM = η · (EIRP_min/N_star) · (ν_c/Δν_tot).
  - **GBT SEFD 10 Jy at L-band and S-band (1.8–2.8 GHz)**, T_sys about 20–25 K.
  - SNR ≥ 10, ±4 Hz/s, 16 integrations of 5 minutes.
  - EIRP_min 2.1×10¹² W at 50 pc; GBT S-band limit <0.37% of stars at 95%
    confidence.
  - Detection probability assumed 0.5 per observation; no injection tests.
  - Drake Figure of Merit: DFM = Δν_tot · Ω / F_min^{3/2}.
- **Haystack fraction (Wright, Kanodia & Lubar 2018)**
  (https://ar5iv.labs.arxiv.org/html/1809.07252):
  - Eight dimensions: sensitivity (EIRP ≥ 10¹³ W), frequency (10 MHz–115 GHz),
    distance (0–10 kpc), sky position (4π sr), transmitter bandwidth
    (0–20 MHz), repetition period (continuous to 1 yr), polarization.
  - Fraction = V_scanned / V_total; V_total,6D = (d_max⁵ / 5P₀) · BW_t,max ·
    Δν · 4π, with P₀ = EIRP_min/4π. The 8D volumes multiply by T_scan · η_pol
    (scanned) and T_max (total).
  - Python script: https://doi.org/10.5281/zenodo.1409818.
- **Main critique, Margot et al. 2023**
  (https://ar5iv.labs.arxiv.org/html/2308.02712):
  - 10,000 chirps injected into raw voltages at SNR ≈ 20, drifts to
    ±8.86 Hz/s.
  - The UCLA pipeline recovered 94.0% (98.7% outside dense interference).
  - A BL-style pipeline (2.98 Hz channels, 51 spectra summed, turboSETI)
    recovered only **5.7%**, mainly through drift smearing above about
    0.15 Hz/s (16% efficiency at 1 Hz/s).
  - Scaled to earlier surveys' drift ranges: efficiency about 12.7% (±4 Hz/s)
    or 25% (±2 Hz/s). Enriquez's 0.1% becomes about 1.7%; Price's L-band
    limits rise about 6×.
  - Modified figure of merit: MDFM = η_P · (ν̇_max/c) · B·Ω / S^{3/2}.
  - Limit on the fraction of stars with transmitters:
    f_TX ≤ [1 − (1−CL)^{1/n}] / (η_P · D), D the duty cycle.
- **Worked numbers for this project** (agent's arithmetic; SNR 10, SEFD 10 Jy,
  δν = 2.79 Hz, two polarizations, 300 s, δν_t = 1 Hz):
  - S_min ≈ 6.8 Jy·Hz (6.8×10⁻²⁶ W m⁻²).
  - At 454 pc (Harp et al.'s distance): EIRP ≈ 1.7×10¹⁴ W at SNR 10,
    2.5×10¹⁴ W at SNR 15, 3.4×10¹⁴ W at SNR 20.
  - The distance should come from Gaia DR3 with its uncertainty (Gaia DR1
    gave about 391 pc, UNVERIFIED).
  - Quote EIRP at the measured 50% and 90% completeness, not only at the cut.
    turboSETI's "SNR 10" is about 33 true σ (Choza §III.1.5: its noise
    estimate is about 3.25× too large; this report first read it the other
    way, corrected 8 Nov 2026), so this project's MAD-based SNR should be
    calibrated against true σ before comparing with BL limits.

## 2. Injection-recovery best practice

- **Choza et al. 2024** (97 galaxies; https://ar5iv.labs.arxiv.org/html/2312.03943):
  - setigen `add_signal` with sinc² line profiles.
  - Separate tests of noise estimation (turboSETI's σ about 3.25× the true
    σ), between-channel loss (spectral leakage) and Doppler smearing from
    −5 to +5 Hz/s.
  - Efficiency peaks at drift ≤ 0.153 Hz/s, then falls roughly as 1/N for N
    channels crossed; a zero-drift signal loses half its power at the first
    de-drift step.
  - Tested hit-finding only, **not** the cadence filter (find_event).
- **setigen:** Brzycki et al. 2022, https://arxiv.org/abs/2203.09668.
- **SETI@home "birdies":** about 3,000 synthetic sky-fixed signals, varying in
  power, bandwidth and planetary drift, inserted **before RFI removal** and
  followed through to the final candidate ranking
  (https://arxiv.org/html/2506.14737v1;
  https://setiathome.berkeley.edu/nebula/web/birdies.php).
- **Recommended for this project:**
  - Plant the same signal in all three ON looks at the drift-consistent
    frequency, and none in the OFF looks; run search plus cadence; count
    candidates out the other end.
  - Plant into OFF looks too, to measure the false-veto rate.
  - Use setigen-style smearing and fractional-channel offsets.
  - Report completeness against SNR, drift (bins either side of
    0.153 Hz/s) and position in the coarse channel (edges, the blanked DC
    bin).

## 3. Prior searches of KIC 8462852

- **Harp et al. 2016, ApJ 825:155, Allen Telescope Array**
  (https://arxiv.org/abs/1511.01606;
  https://iopscience.iop.org/article/10.3847/0004-637X/825/2/155):
  - Oct–Nov 2015, 1–10 GHz.
  - Narrowband: 180–300 Jy in a 1 Hz channel, EIRP (4–7)×10¹⁵ W.
    Medium band: 10 Jy in 100 kHz, about 10¹⁹ W. Distance 454 pc.
  - A GBT S-band limit of about 2×10¹⁴ W would be about 20–30× deeper, over
    1.8–2.7 GHz only.
  - A 2017 ATA follow-up (8 Jul–8 Aug 2017, 1419–4303 MHz, 180–300 Jy):
    UNVERIFIED.
- **Schuetz et al. 2016, ApJL 825 L5** (arXiv:1512.02388): optical pulses,
  Boquete, 29 Oct–9 Nov 2015, with simultaneous ATA radio; null. Limit of
  67 photons m⁻² in 25 ns UNVERIFIED.
- **Abeysekara et al. 2016, ApJL 818 L33 (VERITAS)**
  (https://arxiv.org/abs/1602.00987): about 9 h of archival data 2009–2015,
  no optical pulses above about 1 photon m⁻².
- **Lipman et al. 2019:** optical APF, as above.

## 4. Other targets and data products

- **GBT products** (Lebofsky et al. 2019;
  https://ar5iv.labs.arxiv.org/html/1906.07391):

| File suffix | Frequency resolution | Time resolution | Use |
|---|---|---|---|
| `.0000` (FFT 1,048,576) | 2.79 Hz | 18.25 s | narrowband (what the project reads) |
| `.0002` (FFT 1024) | 2.86 kHz | 1.07 s | fast-drift / short-pulse searches |
| `.0001` (FFT 8) | 366 kHz | 349 µs | broadband pulse / dispersion searches |

  - Earlier hardware revisions used 2.84 Hz / 17.98 s and 2.93 Hz / 17.40 s.
  - Raw voltages are public only for a small set of targets.
  - No API is documented in the paper; the project already uses
    `/opendata/api/query-files`.
- **Published results that can be reproduced:**
  - Price 2020: 1327 stars, about 51 M hits, 6154 passing filters.
  - Enriquez 2017: 692 stars, with the Voyager 1 validation.
  - Galactic Centre: Gajjar et al. 2021, AJ
    (https://iopscience.iop.org/article/10.3847/1538-3881/abfd36).
  - TESS targets: Traas et al. 2021, 28 targets
    (https://iopscience.iop.org/article/10.3847/1538-3881/abf649); a 61-target
    follow-up (probably Franz 2022) UNVERIFIED; 27 eclipsing TESS exoplanets
    (arXiv:2506.13459).
  - Choza 2024 (97 galaxies) and Painter 2025 (3,077 stars).
  - Exotica catalog (Lacki et al. 2021, ApJS 257 42, arXiv:2006.11304) lists
    Boyajian's star as an "anomaly".
  - Not verified: Proxima/blc1 (Smith/Sheikh 2021) and TRAPPIST-1.

## 5. What a result page should state

- Target, distance with uncertainty, session, scans and UTC times, file
  names, checksums and archive URLs.
- Receiver, SEFD assumed, frequency covered, and the fraction blanked or
  masked (Price reports 0.2% at GBT S-band).
- Channel width, integration time, number of spectra, drift range and step,
  the SNR definition and how it compares with true σ, and the cut.
- Cadence rules and tolerances.
- Completeness through the **whole pipeline**, binned by SNR and drift, with
  the false-veto rate.
- S_min and EIRP_min at the cut **and** at 50%/90% completeness, with δν_t
  stated; CWTFM / transmitter rate; an f_TX limit including η_P and duty
  cycle (single star, n = 1).
- Hit counts at each stage and every candidate with its disposition.
- Code version (git hash), software versions, and the turboSETI comparison.
