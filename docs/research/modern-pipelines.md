# Research: modern narrowband search pipelines

Research notes for the overhaul ([../overhaul.md](../overhaul.md)), 8 November
2026. Each claim carries its source; UNVERIFIED marks what could not be
confirmed. Hardware here: Ryzen 9 3950X, 40 GB, GTX 1080 8 GB (CUDA compute
6.1, Pascal).

> **Checked 8 Nov 2026:** Choza et al. 2024 (Section III.1.5,
> https://arxiv.org/html/2312.03943) find turboSETI's noise estimate about
> 3.25 times the sigma-clipped noise, so its SNR is deflated: a turboSETI
> threshold of 10 "actually corresponds to a detection threshold of 33 times
> the true noise".

## seticore (Kevin Lacker, C++/CUDA)

- **What it is.** A C++/CUDA reimplementation of turboSETI's dedoppler: .h5 in,
  .dat or Cap'n Proto hits out. It also beamforms filterbanks from .raw plus
  .bfr5 files and writes "stamp" files of raw data around each hit. Runs at
  MeerKAT, the VLA and Berkeley. https://github.com/lacker/seticore
- **Dedoppler.** A Taylor tree on the GPU, run once per "drift block" (slopes
  between k and k+1 channels per timestep), with timesteps padded to a power
  of two. Paths up to 32 long are summed in shared memory, then global memory;
  loop unrolling gave about 20%.
  https://raw.githubusercontent.com/lacker/seticore/master/taylor.cu
- **Noise and hits.**
  - Noise from column sums: the median, plus the mean and standard deviation
    of the 5th–95th percentiles; SNR = (sum − median)/std.
  - The band is cut into windows 2·max_drift·T channels wide, "just large
    enough so that a single bright pixel cannot cause multiple hits"; each
    window keeps its top path only if no neighbour is larger.
  - A min_drift cut.
  - https://raw.githubusercontent.com/lacker/seticore/master/dedoppler.cu
- **Hit merging.** Hits closer than `margin` columns within a coarse channel
  form a group; each group keeps its top hit; groups are sorted by score.
  https://raw.githubusercontent.com/lacker/seticore/master/dedoppler_hit_group.cpp
- **Cadences and beams.** No ON-OFF logic in the code read; arrays reject
  interference by comparing beams (see COSMIC).
- **Performance.** No published benchmark (speed-up over turboSETI
  UNVERIFIED).
- **Maintenance.** Last push 2024-08-13.
- **Runs here?** Linux only (apt, meson, Boost, HDF5); on Windows only through
  WSL2 with CUDA (GTX 1080 under WSL2 CUDA UNVERIFIED). Build with CUDA 12.x:
  CUDA 13.0 dropped compilation for Pascal (sm_61); NVIDIA says stay on 12.9.
  https://developer.nvidia.com/blog/navigating-gpu-architecture-support-a-guide-for-nvidia-cuda-developers

## BLISS (Nathan West; UCBerkeleySETI/bliss)

- **What it is.** C++17 with CUDA kernels and Python bindings, built on
  "bland", a device-aware ndarray that shares memory with numpy and cupy
  through dlpack; stages run with deferred execution and memoization.
  https://github.com/UCBerkeleySETI/bliss, https://av.tib.eu/media/71205
- **Stages.**
  - Filter-rolloff correction (the coarse channel's edges).
  - Flaggers: spectral kurtosis (low and high), sigma-clip, magnitude.
  - Noise estimated over unflagged ("masked") samples.
  - `integrate_drifts` with desmearing.
  - `hit_search` by connected components or local maxima.
  - `event_search` across the cadence.
  - Hits written as Cap'n Proto (`bliss/file_types/hit.capnp`).
  - https://github.com/n-west/bliss
- **Dedrift kernel.** Brute force, one thread per channel. At each timestep it
  averages a boxcar of channels that widens with drift rate, recovering power
  that fast drift smears. It counts flagged samples along each path, so every
  hit carries how much of it was flagged.
  https://raw.githubusercontent.com/UCBerkeleySETI/bliss/main/bliss/drift_search/kernels/drift_integration_cuda.cu
- **Hit model.** Start frequency, start time, duration, drift, power, SNR,
  bandwidth, coarse channel. https://bliss.readthedocs.io/en/latest/
- **Event model.**
  - Distance between two hits = 0.01 × (frequency difference after both are
    extrapolated to a common time) + 10 × (normalised drift difference).
  - Greedy matching across the ON looks with a cutoff of 50, which the code
    calls a "made up number"; any OFF hit within that distance vetoes the
    event.
  - Weak points: mixed units in the cutoff, an apparent duration_sec typo,
    order-dependent matching.
  - https://raw.githubusercontent.com/UCBerkeleySETI/bliss/main/bliss/drift_search/event_search.cpp
- **Memory.** One coarse channel (2^20 channels × 16 steps) with 1000 drift
  trials needs about 11.6 GB on the GPU, more than a GTX 1080 holds without
  chunking the drifts.
  https://bliss.readthedocs.io/en/latest/theory_of_operation.html
- **What it does better than turboSETI** (the ATA antisolar survey's reasons
  for choosing it, https://iopscience.iop.org/article/10.3847/1538-3881/aeaa59):
  - turboSETI underestimates SNR (citing Choza et al.; see the conflict
    above).
  - turboSETI's top-hit window hides overlapping signals.
  - turboSETI cannot measure bandwidths wider than one channel.
  - turboSETI loses power at channel edges and at high drift.
  - bliss is slower than a tree but faster than real time. The survey used
    ±4 Hz/s and SNR 15.
- **Maintenance.** Active: last push 2026-06-02, 27 open issues.
- **Runs here?** No pip or conda wheels yet ("runtime issue with bitshuffle").
  Builds from source with CMake ≥ 3.28. Ubuntu documented, Windows not
  (UNVERIFIED); WSL2 is the likely route.
  https://bliss.readthedocs.io/en/latest/install.html

## hyperseti (Danny Price, cupy)

- **Pipeline.**
  1. Preprocess: spectral-kurtosis flagging; normalisation (x − mean)/std with
     flagged points left out of the statistics; optional polynomial bandpass
     fit; edge blanking; `blank_extrema`.
  2. Dedoppler: a brute-force kernel ("ddsk") that also records spectral
     kurtosis along each drift path.
  3. Hit search: local maxima, then merging of boxcar trials.
  4. Optional iterative blanking: blank the strongest hits and search again
     for weaker neighbours.
  5. Hits in a HitDatabase, browsed in a HitBrowser.
  - https://hyperseti.readthedocs.io/en/latest/pipeline/preprocessing.html,
    https://hyperseti.readthedocs.io/en/latest/pipeline/hitsearch.html,
    https://github.com/UCBerkeleySETI/hyperseti
- **Drift plans.** "Optimal" steps of df/T (0.01 Hz/s for 300 s at 3 Hz
  channels); "stepped" doubles the step every T trials and pairs with
  smearing correction. Memory is N_drift × N_chan × 4 bytes, about 4 GB for
  2^20 channels to 10 Hz/s.
- **Bottlenecks.** Brute force beats a Taylor tree on a GPU once the drift
  range exceeds T channels; disk I/O and peak-finding, not dedoppler, are
  named as what to optimise.
  https://hyperseti.readthedocs.io/en/latest/pipeline/dedoppler.html
- **Maintenance.** Last push 2025-12-15.
- **Runs here?** Probably natively on Windows: pure Python plus cupy, which
  ships Windows wheels (UNVERIFIED). Use `cupy-cuda12x`; CUDA 13 cannot
  target Pascal.

## GPU turboSETI (SciPy proceedings)

- Ported to cupy with Numba on the CPU side, on a GTX 1070 Ti.
- 6.8–9.3× faster in double precision, 7.5–10.6× in single; a 105 GB file
  took about 12 h on the CPU and 1 h 45 min on the GPU.
- float32 is enough because the input is 8-bit; dedoppler plus hit search are
  about 90% of the run time.
- https://proceedings.scipy.org/articles/majora-212e5952-004
- turboSETI itself has not been pushed to since 2022-05.

## COSMIC (VLA) and BLUSE (MeerKAT)

- **COSMIC** (https://arxiv.org/html/2501.17997v1):
  - seticore at ±50 Hz/s, SNR > 10, on 7.63 Hz channels and 8 s segments.
  - CRICKETS flags bins with excess kurtosis above 5, about 30% of
    frequencies.
  - Spatial test: a hit in every coherent beam and the incoherent beam is not
    localised and is rejected; a hit in a single coherent beam is
    interesting. The coherent/incoherent power ratio should be about the
    number of antennas.
  - Hits go to an SQL database; voltage stamps are saved.
  - In one test 29,390 hits fell to 9,708 after flagging and SNR; none was
    confined to a single beam.
- **BLUSE** (https://arxiv.org/html/2607.23651):
  - Upchannelises to about 1 Hz, forms 64 coherent beams plus one incoherent,
    runs a seticore Taylor search at ±10 Hz/s with initial SNR 6.
  - The SNR threshold is set by how fast storage fills; raw stamps are capped
    in interference-crowded bands.
  - Redis holds state so the pipeline can resume.
  - Drift range justified from Li et al.: ±44 Hz/s covers 99% of known
    exoplanets.
- **Drift range for Tabby's star.** Li et al. find ±0.44 nHz covers 99% of
  signals for a Kepler-like star with no known planet. At 2.7 GHz that is
  about 1.2 Hz/s, so the current ±4 Hz/s already has margin.
  https://arxiv.org/pdf/2311.01427

## Other pipelines

- **ATA NbeamAnalysis** (https://github.com/SETIatHCRO/ATA-Utils/tree/master/NbeamAnalysis,
  https://arxiv.org/html/2409.08313v1). Filters turboSETI hits from two
  simultaneous beams in four steps:
  1. Drop exact frequency matches within 2 Hz with on/off attenuation below 4
     (24 M hits to 6 M).
  2. A "DOT score": the normalised dot product of the on and off
     time-frequency stamps. Near 0, only one beam saw it; near 1,
     interference.
  3. An SNR ratio from the middle-90% noise.
  4. Keep signals above an empirical cutoff curve.
- **FAST (19-beam).** Off-axis beams as simultaneous OFF references (MBCM);
  turboSETI at SNR 10, ±4 Hz/s, the two polarisations searched separately to
  catch instrument interference. https://arxiv.org/pdf/2208.02421,
  https://arxiv.org/pdf/2309.15377
- **FAST wavelet (MSWNet).** A learned extractor followed by a multi-beam
  veto; notes up to about 2.7 M spurious detections under heavy interference.
  https://arxiv.org/abs/2605.23739 (code release UNVERIFIED)
- **UCLA.** The doom and dechirping_efficiency repos; 94.0% of injected
  signals recovered (98.7% outside dense interference); efficiency should be
  folded into the Drake figure of merit. https://astrobiology.com/?p=19423,
  https://zenodo.org/record/5598190
- **Peter Ma.** A β-VAE plus Random Forest over spectrogram snippets from
  whole cadences, 820 stars; a post-filter, not a detector.
  https://github.com/PetchMa/ML_GBT_SETI. A later unsupervised method for
  anomaly detection and interference classification:
  https://arxiv.org/pdf/2411.16556
- **Not found:** a standalone "nbeam" or "Energy Detection" ATA repository.

## Ideas to borrow, ranked

1. **Drift search on the GPU with cupy (or Numba CUDA) in float32**, as
   hyperseti does.
   - One block is 16 × 2^20 floats, 64 MB per look; ±4 Hz/s at df/T ≈
     0.0103 Hz/s is about 780 trials; the output plane is about 3.3 GB, which
     fits in 8 GB.
   - Reduce to a per-channel maximum on the GPU, as seticore's
     findTopPathSums does.
   - Use `cupy-cuda12x`, not CUDA 13.
   - Measure first whether HTTP or compute dominates the 20–25 min; hyperseti
     names I/O as the real bottleneck. The GPU sum is estimated at about a
     second per look (UNVERIFIED).
2. **Desmeared / boxcar drift sums** (bliss; hyperseti
   `apply_smearing_correction`). Above 0.155 Hz/s a signal crosses more than
   one 2.79 Hz channel per 18 s spectrum; summing one channel per spectrum
   loses power; boxcar desmearing recovers about √N.
3. **A richer hit model in a typed, versioned format.** Start frequency,
   drift, SNR, power, bandwidth, coarse channel, look, flagged fraction,
   spectral kurtosis along the path. Keep JSON for `--json`; Parquet or
   Cap'n Proto for bulk hits.
4. **Spectral-kurtosis flagging before the noise estimate** (hyperseti's
   log-SK thresholds, std = 2/√N_acc). Flagged samples stay in the data but
   out of the statistics; every hit gets an interference sign.
5. **Calibrate the SNR against injected signals** and report the threshold in
   true noise units and the recovery efficiency, as UCLA does.
6. **Better hit selection.**
   - Per-window maxima with a neighbour check (seticore).
   - Connected components so crossing signals are not merged (bliss).
   - Iterative blanking of the strongest hits (hyperseti).
7. **A scored cadence test** in place of fixed windows.
   - Extrapolate both hits to a common time and combine frequency and drift
     differences into one distance (bliss), in consistent units.
   - Add a stamp-correlation (DOT) and SNR-ratio check of ON and OFF data
     (NbeamAnalysis).
8. **Save stamps**: a small time-frequency cut around each candidate in all
   six looks, as seticore and COSMIC do.
9. **Parallel I/O with resume**: fetch the six looks' ranges concurrently
   while the GPU searches the previous block; keep resume state per block
   (BLUSE uses Redis).
10. **Later:** an ML post-filter (Ma; arXiv 2411.16556) over the stamps.

## Not read

- The FOSDEM 2024 BLISS talk (404):
  https://fosdem.org/schedule/event/fosdem-2024-2574-searching-the-cosmic-haystack-with-software-radio-the-breakthrough-listen-search-for-narrowband-doppler-drifting-signals-and-combatting-radio-frequency-interference
- BLISS's event_search, hit_search and dedrift docs pages are empty
  placeholders; the source code was read instead.
