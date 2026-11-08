# Research: turboSETI, blimpy and setigen

Research notes for the overhaul ([../overhaul.md](../overhaul.md)), 8 November
2026. Each claim carries its source; UNVERIFIED marks what could not be
confirmed. "SSY" is SignalSearchYoke.

## Headline finding

SSY's injection test overstates completeness at high drift, and its "SNR 10,
as turboSETI" may not mean what turboSETI's 10 means.

- **Smearing in the search.** One channel is 2.79 Hz and one spectrum
  18.25 s, so a signal moves one channel per spectrum at about 0.153 Hz/s
  (the "unit drift rate"). At 4 Hz/s a real tone spreads over about 26
  channels within each spectrum. `search()` sums one channel per spectrum,
  so it collects roughly 1/N of the power (N channels crossed per spectrum).
- **Smearing missing from the test signals.** `plant()` puts all of a tone's
  power into one channel per spectrum, so a planted signal never shows that
  loss.
- **Result.** "98% at SNR 15, drifts up to 3.6 Hz/s" holds only below about
  0.15 Hz/s; the same effect is behind the Margot 2023 result below. Sources:
  https://hyperseti.readthedocs.io/en/latest/pipeline/dedoppler.html,
  https://ar5iv.labs.arxiv.org/html/1709.03491,
  https://arxiv.org/html/2312.03943

## Pain points

**1. Doppler smearing above the unit drift rate** (turboSETI's biggest known
flaw).

- A maintainer (telegraphic) called the missing frequency-scrunching one of
  the two biggest issues; issue #296 is tagged "Deferred to Hyperseti" and
  still open. https://github.com/UCBerkeleySETI/turbo_seti/issues/296
- Margot et al. 2023 injected 10,000 linear chirps (±8.86 Hz/s, target SNR
  about 20) into raw voltages
  (https://ar5iv.labs.arxiv.org/html/2308.02712):
  - UCLA pipeline: 94.0% recovered (98.7% outside dense RFI).
  - A BL-like pipeline (51-spectrum product plus turboSETI): 5.7%, 99.1% of
    them below 1 Hz/s.
  - Scaled to narrower drift ranges: about 12.7% for ±4 Hz/s, 25.3% for
    ±2 Hz/s.
  - Predicted dechirping efficiency about 62% at 0.25 Hz/s, 31% at 0.5 Hz/s,
    16% at 1 Hz/s.
- Choza 2024 recovered 100% at SNR 1000 but "with greatly attenuated S/N at
  high drift rates": flat to about 0.16 Hz/s, then falling about as 1/N.
  https://arxiv.org/html/2312.03943
- The usual workaround is scrunching: add adjacent channel pairs, then search
  the next drift octave with a doubled step. One BL search did this 12 times
  to reach ±614 Hz/s, with a recorded sensitivity loss of 1 to 90.5.
  https://arxiv.org/html/2212.05137
- hyperseti applies a drift-dependent boxcar across channels
  (`apply_smearing_correction`), winning back √N of the lost sensitivity.
  https://hyperseti.readthedocs.io/en/latest/pipeline/dedoppler.html

**2. turboSETI's SNR is not a true SNR.**

- `comp_stats` takes the median of the time-summed spectrum and the standard
  deviation after dropping values outside the 5th–95th percentile, once per
  coarse channel, with no bandpass removal.
  https://raw.githubusercontent.com/UCBerkeleySETI/turbo_seti/master/turbo_seti/find_doppler/helper_functions.py,
  https://raw.githubusercontent.com/UCBerkeleySETI/turbo_seti/master/turbo_seti/find_doppler/find_doppler.py
- Choza 2024 found turboSETI's noise estimate differs from sigma-clipped
  noise by about 3.25 (mode over 1,280 X-band coarse channels), blamed on
  coarse-channel roll-off; turboSETI's SNR 10 is effectively about SNR 33 in
  true noise ("corresponds to a detection threshold of 33 times the true
  noise", §III.1.5; checked 8 Nov 2026), and they corrected their limits for
  it. https://arxiv.org/html/2312.03943
- It fits SSY's own benchmark (a burst at SNR 157 in turboSETI against 17.8 in
  SSY; extra weak hits only SSY found). "SNR 10, turboSETI's default" in
  docs/seti.md is not an equivalent threshold.

**3. The √N noise assumption fails on real GBT data.** setigen issue #32
(open): the sigma-trimmed standard deviation of a real GBT frame after
integration differs "by over 3x" from per-spectrum σ/√N.
https://github.com/bbrzycki/setigen/issues/32

- SSY's `flatten` measures noise per spectrum and `search` divides by √n_t.
- SSY's `inject` sizes signals with the same assumption, so the completeness
  test agrees with itself but its SNR is not absolute.

**4. Top-hit suppression.**

- `tophitsearch` keeps a hit only if it is the strongest within
  ±2·ceil(max_drift/drift_resolution) channels. With a larger max drift, real
  weaker hits vanish: on the Voyager 1 file, 3 hits fall to 1 as max drift
  goes from 54 to 56, while a noise spike is kept. Issue #296 (open).
- `hitsearch` kept the best SNR per channel at any drift, so an out-of-range
  strong hit could hide a valid one; patched in 2.1.19, with the maintainer
  calling hyperseti's iterative blanking the real fix.
  https://github.com/UCBerkeleySETI/turbo_seti/issues/290
- SSY's run-chaining (`reach` = most + WINDOW, about 390 channels or 1 kHz,
  chaining without limit) is a stronger version of the same suppression: a
  110 kHz burst becomes one hit, and any real signal inside it is lost.

**5. find_event flaws.**

- Hard-coded window constants once assumed 2 Hz/s and 300 s, giving false
  extra events; fixed in PR #248.
  https://github.com/UCBerkeleySETI/turbo_seti/issues/231
- Drift-boundary regressions silently removed events (#150); a drift-range
  gap from about −0.9 to 0 Hz/s existed in 1.x.
  https://github.com/UCBerkeleySETI/turbo_seti/issues/150,
  https://github.com/UCBerkeleySETI/turbo_seti/issues/135
- Level-3 de-duplication (opened October 2026, open): uses file-local
  `TopHitNum`, drops whole support tables, can suppress a qualifying starting
  hit; affects 2.1.17–2.3.2 and master; the reported row count is wrong.
  https://github.com/UCBerkeleySETI/turbo_seti/issues/319
- Price 2020 limitations: signals below threshold visibly present in OFF
  looks yet pass; SNR underestimated for wide signals; poor noise estimates
  in heavy RFI. https://ar5iv.labs.arxiv.org/html/1906.07750

**6. Zero drift and spectral leakage.**

- turboSETI 2.3.2 does not record zero-drift hits.
- Its first dedrift step shifts half the band by one channel, halving the
  power of near-zero-drift signals.
- No window in fine channelisation, so a tone loses sinc² power depending on
  where it sits in its channel.
- https://arxiv.org/html/2312.03943

**7. Maintenance and install.**

- turbo_seti's last PyPI release is 2.3.2 (25 May 2022); dependencies are
  blimpy, numba, dask, pandas, astropy, with cupy for GPU. The README says
  nothing about Windows. https://pypi.org/project/turbo-seti/
- Design flaws are "Deferred to Hyperseti", the GPU (CUDA/cupy) successor;
  hyperseti's CPU support UNVERIFIED. https://github.com/UCBerkeleySETI/hyperseti
- blimpy: open issue on the deprecated hdf5plugin Bitshuffle `lz4` argument
  (#278) and a failed PyPI upload (#283).
  https://github.com/UCBerkeleySETI/blimpy/issues
- setigen's docs say HDF5 saving can fail depending on the bitshuffle
  install. https://setigen.readthedocs.io/en/main/basics.html
- No Windows-specific install issue found (UNVERIFIED either way).

## Algorithms

**Taylor tree.**

- Integer-shift tree summation, O(N log N); time steps zero-padded to a power
  of 2 (a no-op for 16 spectra).
- Drift resolution Δf/((n−1)Δt), about 0.0102 Hz/s, the same as SSY's step.
- Negative drifts searched by mirroring the band.
- Paths are integer approximations of straight lines; hyperseti's docs say
  "not all power is recovered for many drift rates", worse with more time
  steps.
- An IAC-22 talk (Houston) reports "significant indexing errors" in the
  Taylor tree (UNVERIFIED; PDF not readable).
- https://raw.githubusercontent.com/UCBerkeleySETI/turbo_seti/master/turbo_seti/find_doppler/data_handler.py,
  https://hyperseti.readthedocs.io/en/latest/pipeline/dedoppler.html
- SSY's brute-force exact-line sum avoids the tree error; worth keeping.

**Normalisation.** Per coarse channel, on the time-summed spectrum:
SNR = (x − median)/std, std over the 5th–95th percentile. DC bin replaced by
the mean of its neighbours (`blank_dc`). No edge mask (shoulder_size 0).
Default SNR threshold 25; BL surveys use 10.

**find_event.**

- OFF test: window ±|drift|·T_obs around the ON hit, or Δf/Δt at zero drift;
  any OFF hit at any SNR or drift inside it rejects the ON hit.
- Later ONs: window centre f + drift·Δt, half-width |drift|·2·T_obs;
  frequency only, no drift agreement.
- Filters on ONs only: SNR cut (strict >), min/max drift, optional zero-drift
  removal.
- filter_threshold: 1 = those cuts; 2 = also not in any OFF; 3 = also in every
  ON.
- Seeds come only from the first ON look.
- https://raw.githubusercontent.com/UCBerkeleySETI/turbo_seti/master/turbo_seti/find_event/find_event.py
- Enriquez 2017: ±600 Hz OFF test, SNR 25, zero drift removed. Price 2020:
  ±600 Hz, then 125 kHz event groups, then visual inspection.

**setigen.**

- Intensity for a target SNR: I = SNR·σ_b/√N_t, σ_b from 3σ iterative
  sigma-clipping over the whole frame; the paper calls this a weakness when
  the bandpass varies and recommends local estimates.
- Signals are built from a path, a time profile, a frequency profile (sinc²
  for an FFT response) and a bandpass profile.
- `doppler_smearing` (default False) averages `smearing_subsamples` (default
  10) copies between successive centres.
- Spectrogram-level injection lacks true non-central χ² statistics; the
  authors suggest the voltage module for low-SNR claims and PFB scalloping.
- https://arxiv.org/html/2203.09668,
  https://setigen.readthedocs.io/en/main/basics.html,
  https://raw.githubusercontent.com/bbrzycki/setigen/main/setigen/frame.py,
  https://github.com/bbrzycki/setigen/issues/16
- Completeness use: Choza 2024 injected sinc², 2-channel-wide signals at
  ±5 Hz/s into 2.93 MHz frames, re-ran turboSETI, and measured recovery and
  SNR against drift. Margot 2023's recovery criteria: frequency within
  ±6 Hz, drift within ±0.05 Hz/s.

## Best practice to adopt (and turboSETI mistakes to avoid)

1. **Make injected signals realistic.**
   - Smear each signal across every channel it crosses within a spectrum
     (setigen's `doppler_smearing` with sub-steps).
   - A sinc² profile at a random sub-channel offset.
   - Report completeness against drift, in bins split at 0.15, 0.5, 1, 2 and
     4 Hz/s, not one number.
   - Optionally cross-check against setigen on a saved slice.
2. **Recover smeared power.**
   - Scrunch per drift octave (sum 2^k adjacent channels, search the next
     octave with a doubled step; 2212.05137), or
   - a drift-dependent boxcar of width about |drift|·Δt/Δf before
     thresholding (hyperseti).
   - Without either, state that the effective limit is about 0.15–0.3 Hz/s,
     or lower `MAX_DRIFT`.
3. **Measure noise on the dedoppler output.**
   - A robust std (MAD or sigma-clip) of each drift-summed row, or at least
     the zero-drift sum, per block; not per-spectrum MAD × √N, which can be
     about 3× wrong on real data (setigen #32).
   - Keep SSY's per-block bandpass removal and noise; they fix turboSETI's
     roll-off bias.
   - Stop calling SNR 10 turboSETI-equivalent; document both scales (factor
     about 3.25 per Choza).
4. **Replace run-chaining with local maxima or iterative blanking.**
   - Peaks in the 2-D (frequency, drift) plane, or blank the brightest track
     and search again (hyperseti).
   - Keeps weak hits beside strong interference; avoids issue #296.
   - Record width separately so bursts are flagged, not merged.
5. **Strengthen the cadence test.**
   - Check OFF looks along the predicted track at a lower threshold (e.g. 5σ),
     or measure the power there directly (Price 2020).
   - Seed from any ON look, not only ON1.
   - Keep requiring drift agreement in later ONs (SSY's `judge` does;
     turboSETI does not).
   - Avoid file-local IDs when de-duplicating (#319).
6. **Keep what SSY already does better than turboSETI:** exact-line brute
   force (no tree indexing loss), an edge mask, DC blanking, and searching
   zero drift (flagging it as likely interference in `check.py` rather than
   dropping it).
7. **Pin the benchmark environment.** turboSETI is frozen at 2.3.2 (2022) with
   known open bugs: a reference with known flaws, not ground truth. Record its
   version in each benchmark record.

## UNVERIFIED and not read

- The Houston IAC-22 Taylor-tree indexing-error claim (PDF not readable:
  https://p.iafastro.directory/iac/paper/id/68619/abstract-pdf/IAC-22,A4,1,14,x68619.brief.pdf).
- Whether hyperseti runs without a GPU.
- Windows-specific turbo_seti or blimpy install bugs.
- Margot et al. 2021 (arXiv 2011.05265) PDF not fetched by this agent.
