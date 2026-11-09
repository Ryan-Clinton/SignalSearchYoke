# The Green Bank instrument: what the files are, and what calibrates them

Research of 9 November 2026, to replace the search's assumptions (the
fine channel's sinc² response, SEFD 10 Jy) with instrument facts.
UNVERIFIED marks what no source found confirms.

Sources: Lebofsky et al. 2019 (https://arxiv.org/abs/1906.07391);
MacMahon et al. 2018 (https://arxiv.org/abs/1707.06024); Price et al.
2020 (https://arxiv.org/abs/1906.07750); the GBT Proposer's Guide, 25 June
2026 (https://www.gb.nrao.edu/scienceDocs/GBTpg.pdf); code read on GitHub:
rawspec a5cc3b0, turbo_seti 7d9b4fd, blimpy 4dd6414.

## Bottom line

- **SEFD 10 Jy is at the low end.** Price 2020's text gives Tsys 20 K,
  its Table 1 25 K, both with SEFD 10 Jy; the Proposer's Guide gives the
  S-band gain as 2.0 K/Jy, so 25 K is 12.5 Jy. Every flux and EIRP here
  could be 25% higher.
- **The fine channels are an unwindowed FFT in rawspec**, so a tone's
  response is sinc² there (a tone at a channel's edge keeps 0.405 of its
  power, −3.92 dB: arithmetic, not a quoted figure). Whether gpuspec (the
  program named in the files) windows its FFT is UNVERIFIED.
- **The coarse polyphase filterbank's taps and window are not published**
  (MacMahon: "8x overlapped"; 8 taps UNVERIFIED); nor is its roll-off.
- **The archive holds flux calibrators** (3C123 ON and OFF in session
  AGBT17B_999_50, among others): a session's data could be calibrated to
  Jy here.

## 1. How the fine channels are made

- The FPGA splits the band into "512 frequency channels using an 8x
  overlapped Polyphase Filter Bank (PFB) from the CASPER DSP library"
  (MacMahon §3), each 2.93 MHz; each compute node takes 64 coarse
  channels, 187.5 MHz (Lebofsky §2.2). Taps and window: UNVERIFIED.
- rawspec: the load callback (`rawspec_gpu.cu` about line 133) only turns
  int8 into float, so no window (rectangular); FFTs do not overlap; powers
  summed; defaults `-f 1048576,8,1024 -t 51,128,3072`. The output is
  fftshifted (about lines 1660-1680), putting the DC bin at each coarse
  channel's centre.
- gpuspec: Lebofsky says only "three different FFTs … NVIDIA cufft";
  windowing UNVERIFIED.
- Lebofsky Table 4 (Rev 2A): the finest product is a 1,048,576-point FFT
  times 51 integrations, i.e. 2.79 Hz and 18.25 s. Older revisions used
  1,033,216 or 999,424 points.
- **DC spike:** each coarse channel has "a spike in the DC bin at the
  center"; "There are no corrections for these in the public data"
  (Lebofsky §2.5.2). Cause not stated (UNVERIFIED). turboSETI blanks it by
  default (`find_doppler.py` about line 417, `blank_dc=True`, the mean of
  the two neighbours), as this search does.
- **Coarse passband:** "a reduction in sensitivity toward the channel
  edges" (Lebofsky Fig. 10); no usable fraction or curve published. Price
  2020 sets noise from the central 90th percentile of powers, partly for
  "rolloff imparted by the shape of the polyphase filter".

## 2. The S-band receiver

- Proposer's Guide Table 3: 1.73-2.60 GHz; gain 2.0 K/Jy; aperture
  efficiency 72%; beam FWHM 5.8′; up to 970 MHz at once; a superconducting
  notch filter "permanently installed immediately after the first
  amplifiers", 2300-2360 MHz (Sirius/XM); selectable RF filters 1.68-2.65
  and 2.1-2.4 GHz; two noise diodes, about 10% and 100% of Tsys. Tsys only
  as a figure (not read off).
- Price 2020: text "system temperature of 20 K, resulting in … SEFD of 10
  Jy"; Table 1 S-band 1.80-2.80 GHz, Tsys 25 K, SEFD 10 Jy. MacMahon Table
  1: S-band Tsys 25 K.
- Lebofsky: S-band public files trimmed to 1820-2720 MHz (the sweep here
  covers 1818.5-2720.9 MHz).
- **Calibration:** the files are in instrument units; "Flux calibration is
  not currently a part of our standard reduction pipeline … or perform an
  approximate calibration using the radiometer equation" (Lebofsky §2.1).
  BL observes a bright pulsar and a flux calibrator at the start of each
  session. MacMahon calibrated PSR B0329+54 with the switched noise diode
  and 3C138, from raw voltages, not the SETI filterbanks. Whether the
  noise diode was on during target scans: UNVERIFIED (raw headers carry
  CAL_MODE, CAL_DCYC).
- Calibrators in the archive (opendata API): 3C123, 3C147, 3C286, 3C295,
  3C48, 3C353, CAL3_3C_286 and others. `DIAG_3C123` and `DIAG_3C123_OFF`
  are in session AGBT17B_999_50 (MJD 58060) with all three products, e.g.
  http://blpd13.ssl.berkeley.edu/ETZ/AGBT17B_999_50/GUPPI/BLP00/blc00_guppi_58060_20295_DIAG_3C123_0001.gpuspec.0000.fil
  (node centre 2157.7 MHz); its receiver UNVERIFIED.

## 3. SEFD from the data itself

No BL paper found measures a per-session SEFD or Tsys from the filterbank
data; Price 2020 and Lebofsky use nominal values (not an exhaustive
negative).

## 4. Artefacts in the .0000 product

- Stokes I: "Squares the channelized output, add the two polarizations
  together"; 32-bit floats (Lebofsky §2.3).
- DC spike and coarse-channel roll-off (above); the notch at 2300-2360 MHz.
- Dropped packets: lower sensitivity in rectangles one node (187.5 MHz)
  wide (Lebofsky Fig. 12); rawspec fills missing blocks with zeros
  (`rawspec.c` about line 941), so affected spectra have less power, not
  NaNs.
- A whole node missing: zero-padded in spliced files, marked `zz` in the
  name; unused overlapping nodes dropped, marked `oo`.
- Older products put the first channel's centre, not its edge, in the
  header: half a channel, fixed in the HDF5 conversion.
- Strong interference spreads "due to analog saturation and digital
  overflow".
- Node boundaries in spliced files: nothing documented beyond the above
  (UNVERIFIED).

## 5. Products of each look

| product | suffix | FFT × integrations (Rev 2A) | resolution |
|---|---|---|---|
| high spectral resolution | `.gpuspec.0000` | 1048576 × 51 | 2.79 Hz, 18.25 s |
| high time resolution | `.gpuspec.0001` | 8 × 128 | 366 kHz, 349.5 µs |
| medium resolution | `.gpuspec.0002` | 1024 × 3072 | 2.86 kHz, 1.07 s |

All three are in the archive for each look, as .fil or .h5 (e.g.
https://bldata.berkeley.edu/pipeline/AGBT16B_999_39/holding/spliced_blc0001020304050607_guppi_57668_28900_HIP17147_0009.gpuspec.0002.h5).
Raw voltages are mostly deleted after reduction; DIAG targets keep them.
The `.0002` product follows drifts to about 2.7 kHz/s before a signal
crosses a channel a spectrum (arithmetic); `.0001` suits short pulses.
Query: `http://seti.berkeley.edu/opendata/api/query-files?target=…&telescope=GBT`.
