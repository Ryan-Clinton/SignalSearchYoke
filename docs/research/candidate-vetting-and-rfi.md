# Research: candidate vetting and interference

Research notes for the overhaul ([../overhaul.md](../overhaul.md)), 8 November
2026. Each claim carries its source; UNVERIFIED marks what could not be
confirmed.

## Bottom line

Four programmes reach the same conclusion: **rejected hits are the evidence.**

- blc1 was ruled out using 111 hits that turboSETI had already thrown away as
  RFI.
- SonATA ruled out 61% of its signals with a 7-day database of past hits.
- UCLA's main remaining failure is a counterpart in another direction that
  sits below the detection threshold.

SignalSearchYoke's sweep record keeps only candidate events and counts the
rest (`seti.py` `sweep()`). That rules out every test below except a fixed
list of bands. The first change has to be the hit store; the checks come
after it.

## 1. blc1 (Sheikh et al. 2021, Nature Astronomy)

Read in full from Breakthrough Listen's own copy,
http://seti.berkeley.edu/blc1/BLC1_NatAstron_arXiv_sheikh.pdf (arXiv
2111.06350).

**The 10-step framework (Section 5), in substance:**

1. Check that the instruments were working correctly.
2. Check that the signal was not in the OFF looks **at a lower S/N
   threshold**.
3. Check for catalogued RFI at that frequency at the observatory.
4. Compare the drift evolution with known accelerational and electronic
   drifts of human technology (satellites, deep-space probes).
5. Compare the drift evolution with that expected in the target system and
   the solar system.
6. Search the same observatory's archive for other instances.
7. Search for similar signals at other frequencies in the same observation.
8. Judge, quantitatively if possible, whether those signals come from the
   same phenomenon.
9. If they do, test them for RFI using their OFF looks.
10. Re-observe with the same instrument and with others.

Public flowchart: https://seti.berkeley.edu/blc1/flowchart.html

**How the look-alikes were found (Section 4.2):**

- A frequency-normalised drift (drift/frequency), since transmitters in the
  same environment drift in proportion.
- The turboSETI hit catalogue searched for hits (a) at the same time as blc1
  and (b) at the same normalised drift within its error.
- 112 hits: blc1 and 111 already rejected as RFI because they showed in OFF
  looks.
- By eye, 36 of the 111 (32%) were look-alikes: monotonic drift, a slope
  flattening over time, spanning several looks, no extra structure.
- With negative drift, 310 hits, 27 of them "mirrored" look-alikes.
- blc1 matched the look-alike population in |drift|, frequency and S/N.

**Archive search (Section 4.1):**

- Waterfall and "butterfly" (drift vs frequency) plots at
  982.002–982.004 MHz for every ON and OFF look in the campaign; about 7,000
  archival observations checked.
- 4 blc1-like signals **below turboSETI's threshold**, present in OFF looks.

**What ruled it out (Section 4.4):**

- Harmonic test: the first 20 harmonics of fundamentals 100–1000 MHz in 1 kHz
  steps, 1 kHz tolerance. blc1 was not harmonic; a family of other
  look-alikes was ("x.y99").
- Intermodulation: look-alike spacings were integer multiples of clock
  frequencies (133.33 MHz, 15 MHz, 128 MHz, and a 2.000004 MHz oscillator);
  spacings such as 16.000038 MHz were exact multiples within ±4 Hz.
- blc1 was tied by those spacings (to about 100 Hz) to look-alikes near 712,
  856 and 1062 MHz.
- Conclusion: an intermodulation product of a roughly 2 MHz clock mixed with
  zero-drift RFI, whose duty cycle happened to match the ON/OFF cadence.
- The paper warns that keeping only "postage stamps" around events loses the
  context needed to show a signal is RFI.

**Automatable versions:** a normalised-drift twin search over all hits in the
cadence; the harmonic grid; a pairwise spacing histogram against common clock
values; a sub-threshold OFF check.

## 2. SETI@home final analysis (arXiv 2506.14737; front end 2506.14718)

Source: https://arxiv.org/html/2506.14737v1

**RFI stages:**

- Frequency-zone RFI: removes zones with an excess of detections over the 14
  years, counted by time window, so a zone flagged at one time does not
  remove a signal there at another.
- Drifting RFI: time/frequency triangles holding detections from distant sky
  positions.
- Multi-beam RFI: the same frequency in very different directions at nearly
  the same time.
- Low drift: |drift| < 0.086 Hz/s flagged.
- Duration consistency: a detection must last about as long as the beam takes
  to cross the source.
- Total flagged: 10.8% of all detections, 17.5% of spikes.

**Birdies (synthetic signals injected before RFI removal):**

- 11.5% of birdie spikes were lost, mostly to the zone filter (8.8%); the
  design goal is under about 10%.
- Sensitivity: the power at which at least 80% of 3,000 birdies rank in the
  top 100.

**Multiplets and scoring:**

- Grouped by barycentric frequency (250 Hz window), sky pixel (0.05°) and
  non-overlapping times.
- Score = power factor + density factor + time factor, each a negative log
  probability.

**Selection and follow-up:**

- About 1,000 top multiplets inspected by hand; rejected for recurrence when
  the telescope pointed elsewhere, spans under 0.15 days, or barycentric drift
  of 0.7 Hz/s or more.
- 92 sent to FAST; 80 reobserved by publication. Press coverage says no
  repeats in about half
  (https://www.livescience.com/space/extraterrestrial-life/scientists-study-100-possible-alien-radio-signals-from-collapsed-arecibo-observatory-ending-groundbreaking-21-year-search):
  UNVERIFIED in the paper itself.
- The authors' lesson: over-aggressive RFI removal loses real signals.

## 3. Breakthrough Listen ML (Ma et al. 2023; arXiv 2301.12670)

- A β-VAE encoder (β = 1.5) feeding a random forest.
- 1,004 GBT L-band cadences, about 115 million snippets, 2.9 million events.
- 4.97 MHz bins with more than 35,000 events discarded (13 bins, about
  65 MHz, e.g. GPS near 1600 MHz); classifier confidence above 90% left
  20,515 events, inspected by eye.
- Criteria for a signal of interest: narrowband, drifting, in all three ON
  looks, absent in OFF, and **consistent drift across the three ON looks**
  (refit in each ON look separately with setigen; varying drift rejected).
- 8 signals of interest (MLc1-8) around 5 stars; re-observation on 21 May
  2022 found nothing.
- UCLA later detected all 8 natively without ML (arXiv 2308.02712).

## 4. UCLA SETI (Margot et al.)

**Filters (arXiv 2011.05265, Section 3.2):**

- Zero drift rejected.
- Persistence: a signal must pair with one in the second look at the same
  source.
- Direction of origin: any pair across different sources is RFI.
- Gale-Shapley-style one-to-one pairing: frequency projected forward with the
  average drift, ±2.98 Hz bound, drift resolution 0.0173 Hz/s, drifts agree
  within 2 drift bins.
- Known-RFI bands (GPS L5 1155.99–1196.91, GLONASS 1192.02–1212.48,
  1525–1559, GPS L1 1554.96–1595.88, GLONASS 1592.95–1610.48 MHz) held about
  99% of detections.

**What the filters themselves lose:**

- Of 18,093 injected signals the filters wrongly flagged 49 (0.27%), each
  paired with RFI of similar drift in another source's look.
- Detection, not filtering, was the main loss: 92.6% recovered in 2021; 94.0%
  overall and 98.7% outside dense RFI in 2023.

**Why promising signals escaped and were then rejected by eye:**

1. The counterpart in another direction was below S/N 10.
2. Drifts differed by more than the tolerance.
3. The counterpart was hidden by a stronger crossing signal.
4. Bandwidth over 10 Hz.

**Totals (arXiv 2308.02712, 2605.05408):** 41.2 million signals, 99.43%
rejected automatically; of the rest 99.78% in dense-RFI regions; 500 inspected
by eye; none needed follow-up in 82 million detections.

**Drift smearing in the BL product:** in the 2.79 Hz × 18.25 s product, power
smears across channels above 0.15 Hz/s. At 4 Hz/s only about 4% of the power
stays in each channel; the mean efficiency of the Price et al. 2020 search was
about 16.5%. SignalSearchYoke uses the same product to the same drift; its
injection test plants a given S/N on the summed line, so it probably does not
measure this loss (the agent's inference, UNVERIFIED for this code).

**Zooniverse "Are We Alone in the Universe":** 40,000+ volunteers; about
76,000 labelled signals trained a ResNet RFI classifier with F1 ≈ 0.99 (arXiv
2605.05408). Class percentages UNVERIFIED.
https://www.zooniverse.org/projects/ucla-seti-group/are-we-alone-in-the-universe

**BL Kepler-transit search (arXiv 2212.05137):** citizen scientists cut
3.4×10⁵ events to about 0.4%; the rest grouped by frequency and morphology,
dropped if the same signal appeared on two targets or matched a known RFI
signal; 479 left, then 2 signals of interest.

## 5. RFI catalogues

**SonATA/ATA (arXiv 1607.04207):**

- Every hit above threshold stored with: beam and telescope RA/Dec, target,
  beam, type, start frequency, drift, width, power, polarisation,
  classification, reason, false-alarm probability and S/N.
- A new signal within **100 Hz of any database entry from the last 7 days on a
  different target** is RFI: 61% of signals removed.
- The database was primed with 12-hour zenith scans to define permanent RFI
  bands.
- Other outcomes: zero drift 1.3%, drift too high 4%, sent to ON/OFF
  follow-up 31%.

**GBT:**

- RFI scans are public through NRAO DRIFT and rfi.gb.nrao.edu:
  https://greenbankobservatory.org/spectrum/rfi-monitoring/
- The older page is marked outdated and gives only PNG images for L and S
  band: https://greenbankobservatory.org/rfi-scans-and-known-sources/
- Raw fits files are on site only; no offline, machine-readable L or S band
  list was found.

**Price et al. 2020 (arXiv 1906.07750):**

- L-band notch 1.200–1.341 GHz; GPS L5 1.155–1.196, L1 1.555–1.596; GLONASS
  1.592–1.619 and 1.192–1.212; satellite downlink 1.525–1.560 GHz.
- At S-band (1.8–2.8 GHz), 7.36M of 10.1M hits had zero drift. A peak at
  ±3.5 Hz/s came from about **1930.2 MHz cellular** RFI, close to the current
  sweep range of 1818–1853 MHz.
- S-band notch: UNVERIFIED (probably 2.30–2.36 GHz).
- L-band hits are mostly negative drift (13.9M vs 1.37M positive). Expected
  Earth-motion drift limits: ±0.25 Hz/s at 1.9 GHz, ±0.36 Hz/s at 2.7 GHz.

**The practical offline catalogue** is BL's own open data: run the search on
the OFF looks of other targets in the same session and archive.

## 6. Reporting standards

- Rio 2.0 (Forgan et al. 2018, a questionnaire giving R = Q×δ):
  https://en.wikipedia.org/wiki/Rio_scale. Sheikh et al. scored blc1 with it.
- The IAA post-detection declaration, revised 2010 and updated 2026:
  https://astrobiology.com/2026/06/updated-rules-for-evaluating-and-revealing-the-detection-of-extraterrestrial-intelligence.html
  (secondary coverage only).

## 7. Checks for SignalSearchYoke, in order

0. **Keep every hit from every look**, interference and unconfirmed included,
   at the 10σ cut and at a lower "shadow" cut (say 5σ) for OFF looks.
   Without this none of the checks below can run.
1. **Sub-threshold OFF test** (blc1 step 2; UCLA reason 1): re-measure power
   along the candidate's projected track in each OFF look, without a
   threshold, and record the S/N even below the cut.
2. **Per-look drift consistency** (Ma): fit drift separately in each ON look;
   flag or reject disagreement beyond about 2 drift bins. The current
   tolerance of 0.5×|drift| is very loose.
3. **Zero or low drift** (UCLA, SonATA, SETI@home): flag |drift| below about
   one bin (≈0.002–0.003 Hz/s here; SETI@home used 0.086 Hz/s).
4. **Expected topocentric drift**: the drift Earth's rotation and orbit give
   a sidereal source at the GBT for this target, hour angle and frequency
   (about f·ω²R·cosφ·cosδ·cosH/c); record observed minus expected. Evidence,
   not a rejection (Sheikh step 5).
5. **Known-RFI and notch bands**: replace the hand-made ITU list with
   GBT-specific bands from Price 2020 and Margot 2021, including the notches
   and the 1930 MHz cellular peak. A weight, not a verdict (SETI@home
   warning).
6. **Recurrence across sessions and targets** (SonATA, Kepler-transit search,
   blc1 step 6): a hit within about 100 Hz (or 2 channels plus drift×Δt) in a
   look at a different target, in any session, means RFI. Same target,
   different session: carry the hit forward.
7. **Look-alike / twin search in the same cadence** (blc1 step 7): over all
   hits, find ones with the same normalised drift (drift/f within error) and
   the mirrored sign; if the twins appear in OFF looks, the candidate
   inherits the RFI verdict.
8. **Harmonic and intermodulation test** (blc1 Section 4.4):
   - Harmonics: do the candidate and its twins fit n×f₀ within 1 kHz?
   - Spacings: are frequency differences integer multiples of common clock
     values (2.000004, 10, 15, 16, 25, 30, 100, 125, 128, 133.33 MHz) within
     n×(channel error)?
   - Mixing: is f_cand = a·f₁ ± b·f₂ for strong hits f₁, f₂ (often zero-drift)
     in the same look?
9. **Frequency-zone occupancy** (SETI@home, Ma): flag the candidate if hits
   per MHz per hour in its band and time window are far above the median.
10. **Birdie loss accounting**: plant signals before steps 1–9 and report what
    fraction each check removes; SETI@home aims for under 10%.
11. **Report** with a Rio 2.0 score and the 10-step checklist marked done or
    not; then re-observation (outside this tool).

## 8. Fields each hit must keep

**Identity and observation:** hit id; target, session, scan, ON/OFF, look
index, file URL; coarse-channel and block index; tstart (MJD), duration,
telescope, receiver/band; RA/Dec pointed at, hour angle and elevation at
mid-look (for the topocentric check).

**Signal:** start frequency (topocentric, full precision) and end frequency;
drift in Hz/s and its error; normalised drift (drift/f); S/N, integrated
power, local noise (median/MAD), bandwidth or number of channels; per-channel
peak index; smear factor (drift×tsamp/channel width); a flag for the
coarse-channel-edge or DC-spike region.

**Cadence and RFI result:** cadence label (candidate / interference /
unconfirmed); in_on and in_off flags; per-look S/N along the projected track,
including below-threshold values; per-look fitted drift.

**Links and provenance:** ids of matched hits in other looks; ids of twins,
mirrors, harmonics or intermodulation partners; recurrence ids (other targets
and sessions); known-band match, zone occupancy; injected/birdie flag; code
version, search parameters (SNR cut, max drift), time searched.

Optionally a small time-frequency "stamp" of each candidate, but not *instead
of* the full hit list (blc1 warning).

## Gaps

- blc1 Supplementary Table 2 and the exact look-alike drift tolerance not
  read.
- FAST results for SETI@home not confirmed in the paper.
- Zooniverse class percentages and the S-band notch unconfirmed.
- No offline GBT RFI frequency list found.
- Not readable by the fetcher: the Nature article (login redirect; the
  BL-hosted preprint was used), ResearchGate (403), escholarship (empty page),
  rfi.gb.nrao.edu (not tried).
