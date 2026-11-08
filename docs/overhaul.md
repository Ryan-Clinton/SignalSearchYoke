# SignalSearchYoke overhaul: plan and specification

8 November 2026. What the project does now, what the field does better, and
the work, in order, that brings it up to the standard of the published
searches. The evidence is in [research/](research/):

| Notes | What they cover |
|---|---|
| [turboseti-blimpy-setigen.md](research/turboseti-blimpy-setigen.md) | turboSETI's known flaws, its algorithms, setigen injection practice |
| [modern-pipelines.md](research/modern-pipelines.md) | seticore, BLISS, hyperseti, COSMIC, BLUSE, FAST, ATA, UCLA, ML |
| [candidate-vetting-and-rfi.md](research/candidate-vetting-and-rfi.md) | blc1's verification framework, SETI@home, UCLA, SonATA, RFI lists |
| [sensitivity-and-prior-searches.md](research/sensitivity-and-prior-searches.md) | flux and EIRP limits, figures of merit, earlier searches of Tabby's star |
| [data-access-and-engineering.md](research/data-access-and-engineering.md) | timings taken on this PC, storage, packaging, scheduling |

## 1. Where it stands

The search works and has been checked carefully against turboSETI on seven
real looks. But measured against the field it has five problems, two of
which change what its results mean.

1. **Its sensitivity is overstated above 0.15 Hz/s.** A channel is 2.79 Hz
   and a spectrum 18.25 s, so a signal drifting faster than about
   0.153 Hz/s crosses more than one channel within one spectrum; at 4 Hz/s
   it spreads over about 26. `search()` sums one channel per spectrum and
   collects about 1/26 of the power. `plant()` puts each test signal's whole
   power in one channel per spectrum, so the injection test never sees that
   loss: "98% found at SNR 15, drifts to 3.6 Hz/s" holds only for slow
   drifts. This is the field's best-known flaw: Margot et al. 2023 found a
   Breakthrough Listen-style pipeline recovered 5.7% of realistic chirps
   where UCLA's recovered 94%.
2. **Its SNR is not on the published scale.** Noise is measured per spectrum
   (median absolute deviation) and divided by √16; that assumption is off by
   up to 3× on real Green Bank data (setigen issue #32). turboSETI's own
   "SNR 10" is about 33 in true noise (Choza et al. 2024, §III.1.5). The
   docs' "SNR 10, turboSETI's default" is therefore not an equal threshold,
   and no limit can yet be quoted against published ones.
3. **It throws the evidence away.** The sweep record keeps candidates and
   only *counts* everything else. Every professional vetting method (blc1's
   look-alikes, SonATA's 7-day database, SETI@home's zone filter, recurrence
   across targets) works from the hits already rejected. None can run on
   what is kept now; the 12 blocks swept so far have no hits to reuse.
4. **The cadence test and vetting are thin.**
   - Only hits of the first ON look are followed.
   - OFF looks count only above the ON threshold, so faint interference in
     an OFF look passes (Price 2020; blc1 step 2).
   - Drift agreement is ±50% of the drift.
   - `check.py` has a hand-made band list and a zero-drift test.
   - Run-chaining merges anything within about 1 kHz into one hit, without
     limit, so a real signal beside interference disappears (turboSETI issue
     #296, worse).
5. **It is about 40× slower than it need be.** Measured on this PC:
   - `requests.get` without a session pays a fresh TLS handshake per request
     (0.9 s against 0.165 s).
   - A 4 MB read buffer turns small HDF5 index reads into 4 MB downloads:
     880 MB moved per block for 300 MB of data.
   - `np.roll` in float64 takes 52 s a look where float32 slice-adds take
     3.8 s.
   - Remaining 296 blocks: about 4–5 days now; about 2–2.5 hours after.

What it already does better than turboSETI, and keeps:

- an exact-line brute-force drift sum (no Taylor-tree path errors);
- the band shape and noise measured block by block (turboSETI's whole-channel
  noise is the source of its 3.25× error);
- the coarse channel's edges masked and its DC spike blanked;
- zero drift searched, not dropped;
- drift agreement required across ON looks (turboSETI's `find_event` checks
  frequency only);
- range-request reading with a strict check on what the server returns;
- the `--json` envelope and atomic record writes.

## 2. Goals

- **G1. Say true things.** Every figure the project states (SNR, completeness,
  limits) means what it says, measured through the whole pipeline.
- **G2. Keep every hit.** Rejected hits are the evidence for every later
  check.
- **G3. Vet like blc1.** A candidate leaves the tool with the automatable
  steps of Sheikh et al.'s framework done and recorded.
- **G4. Fast enough to finish.** A cadence of 308 blocks in an evening, on
  this PC, without a GPU.
- **G5. Produce a result.** A published-standard limit on narrowband
  transmitters at Tabby's star in 1.8–2.7 GHz. No published radio limit
  from Breakthrough Listen's Green Bank data on this star was found (Harp et
  al. 2016's ATA limit is about 20–30× shallower); whether Painter et al.
  2025 included it is to be checked.

**Not goals, and why:**

- **GPU code.** The search is about 4 s a look in numpy. The GTX 1080 is
  Pascal, which CUDA 13 dropped, so cupy is a dependency with a short
  future.
- **Adopting seticore or BLISS.** Both are Linux builds (WSL2 at best). Their
  ideas are taken instead: desmearing, flag counts per hit, typed hits.
- **ML classifiers.** Ma et al.'s 8 signals were all later found without ML;
  a post-filter needs a hit store and stamps first (later phase).
- **Pulse searches, or drifts to ±50 Hz/s, on the `.0000` product.** One
  spectrum per 18 s cannot see pulses, and at 50 Hz/s a signal is smeared
  over 300+ channels. Both need the `.0002` product (2.86 kHz × 1.07 s), a
  separate later phase.
- **Rewriting what works.** The command line, `--json` envelope and file
  layout stay; `seti.py` may split into modules.

## 3. The work, in order

Each phase ends with something checkable, and is committed and pushed when
done. Phases 1 and 2 come first because every later phase needs fast reads
and kept hits.

### Phase 0: a fixed reference

- Save one block of all six looks with `--keep` (the 2266.75–2269.60 MHz
  slice already benchmarked) to `data/reference/`. All equivalence checks
  run against it offline.
- Record the current `search` and `cadence` output on it as the baseline.
- Fix `provenance()`: hdf5plugin's version is `hdf5plugin.version`, not
  `__version__`; sweep records are stamped.

**Done when:** the reference slices and baseline output are on disk, and
`provenance()` lists all three libraries.

### Phase 1: fast, polite reading

1. **Session and buffer:** `Remote` uses one `requests.Session` with urllib3
   `Retry` (back-off on 429/5xx); the 4 MB `BufferedReader` is replaced by a
   64 KB block cache.
2. **Chunk index:** once per file, the byte offset and size of every chunk
   (via h5py `dataset.id.chunk_iter` over a 64 KB-cached remote file, 17 s a
   file), stored in `data/index/` keyed by URL and ETag; rebuilt if the ETag
   changes.
3. **Direct chunk reads:** a block's 16 chunks per look fetched by their
   ranges, 6 looks × 16 = 96 requests, through a pool of 6 threads (4 already
   reach 11 MB/s; no more than 8, for the server's sake); decoded with
   bitshuffle via an in-memory HDF5 (`write_direct_chunk`), 0.1 s per block.
4. **Search in float32 with slice-adds** in place of `np.roll`.
5. **Pipelining:** block k+1 is fetched while block k is searched.

**Done when:**

- the reference block gives the same hits as the baseline, or each
  difference is explained (float32 rounding);
- a block of the live cadence takes 40 s or less, with the bytes moved
  logged;
- `find()` results are cached per run.

### Phase 2: the hit store

SQLite at `data/ssy.sqlite` (WAL mode, one transaction per block). JSON stays
for `--json` answers and a human-readable export.

| Table | Holds |
|---|---|
| `runs` | run id, start time, git commit and dirty flag, host, Python and library versions, every search parameter |
| `files` | URL, ETag, size, session, scan, target, ON/OFF, tstart, fch1, foff, tsamp, RA/Dec, receiver |
| `blocks` | session, block index, MHz range, status, run, bytes moved, fetch and search seconds, time searched (the resume ledger) |
| `hits` | every hit of every look (fields below) |
| `events` | cadence results: label, per-look found/S-N/drift, links to the matched hits |
| `checks` | each vetting check run on an event: name, result, evidence, version |
| `injections` | planted signals and what became of them |

Each hit keeps:

- **Identity:** id, run, file, block, channel.
- **Signal:**
  - start and end frequency at full precision;
  - drift and its error; normalised drift (drift/frequency);
  - SNR and integrated power; local noise; width in channels;
  - smear factor (|drift| × tsamp / channel width).
- **Flags:** near an edge, near the DC bin, flagged-sample fraction.
- **Origin:** shadow-cut hit (see Phase 3) or injected.

**Migration:** the 12 blocks already swept kept no hits, so they are searched
again (about 6 minutes after Phase 1); their old counts are kept in the
export for comparison.

**Done when:** a sweep of 5 blocks fills all tables, and one SQL query lists
hits within ±200 Hz of each other across different files.

### Phase 3: a correct search

1. **SNR on the true scale.**
   - Noise is measured on the drift-summed output, a robust standard
     deviation of each block's summed rows, not per spectrum × √16.
   - Checked with signals of known power planted into the reference slices.
   - The docs state the scale and its relation to turboSETI's (×3.25).
2. **Desmearing.**
   - For drift lines faster than one channel per spectrum, each spectrum's
     contribution is a boxcar of ⌈|drift| × tsamp / channel width⌉ channels
     along the line (hyperseti and BLISS), which recovers about √N of the
     lost sensitivity.
   - Alternative, chosen by measurement: scrunch adjacent channels per drift
     octave (Breakthrough Listen's Kepler search).
   - Whichever recovers more of the planted signals in Phase 6 is kept.
3. **Hit selection without run-chaining.**
   - Local maxima in the (frequency, drift) plane, then iterative blanking:
     blank the strongest track, search again.
   - Weak signals beside interference survive.
   - A wide burst is recorded as one hit with its width, flagged as wide, not
     merged with its neighbours.
4. **A shadow cut.** Hits down to SNR 5 kept in the store, marked; they are
   not candidates, only evidence for the OFF test and recurrence.
5. **Spectral kurtosis per channel** (hyperseti's log-SK, std 2/√N). Flagged
   samples stay in the data, out of the noise statistics, and each hit
   carries its flagged fraction as an interference sign.
6. **Drift range:** ±4 Hz/s stays. Earth's own motion gives at most about
   0.36 Hz/s at 2.7 GHz, and Li et al. 2023 put 99% of plausible signals for
   a Kepler-like star within about 1.2 Hz/s here. Completeness is reported
   by drift bin, not as one number.

**Done when:**

- the reference slices give the same strong hits as before (2267.509 MHz
  tone, burst at 2266.79–2266.91 MHz);
- planted smeared signals at 1 and 4 Hz/s are found at a stated, measured
  rate;
- a quiet slice gives no false hits at the cut.

### Phase 4: a stronger cadence test

1. **Seed from every ON look**, not just the first; a signal that starts in
   ON 2 is still followed.
2. **One matching distance:**
   - both hits extrapolated to a common time;
   - frequency and drift differences combined in consistent units (channels
     and drift steps);
   - one-to-one matching, so a strong signal cannot claim two partners
     (UCLA's pairing).
   - BLISS's version mixes units and calls its cutoff "made up"; this one
     states its own.
3. **Per-look drift fit:** a candidate's drift measured in each ON look
   separately; disagreement beyond 2 drift steps is flagged (Ma et al.). The
   ±50% tolerance goes.
4. **The OFF test below the threshold:**
   - power measured along the candidate's projected track in each OFF look,
     with no threshold (blc1 step 2; UCLA's main remaining failure);
   - recorded as an S/N even when it is 2;
   - an OFF S/N above a stated level (to be set from injections, about 5)
     makes the event interference.
5. **ON/OFF stamp correlation:** the normalised dot product of the ON and OFF
   time–frequency cuts around the track (ATA NbeamAnalysis's DOT score), as a
   recorded sign.

**Done when:**

- signals planted in all three ON looks of the reference cadence come out as
  candidates at the measured rate;
- signals planted in ON and OFF alike come out as interference, every time
  above the OFF level;
- the reference cadence's known interference (2267.509 MHz) is still
  interference.

### Phase 5: vetting (`check.py` rebuilt)

Each candidate is run through these checks in order. Every result is stored
in `checks` with its evidence; no check deletes a candidate, they score it.
The verdict is "interference (named reason)", "unexplained, weak", or
"unexplained, strong".

| # | Check | From |
|---|---|---|
| 1 | Data sanity: block complete, no NaN or zero runs, flagged fraction small | blc1 step 1 |
| 2 | Sub-threshold OFF power (Phase 4) | blc1 step 2, UCLA |
| 3 | Known Green Bank interference bands: GPS, GLONASS, Iridium, Inmarsat, satellite radio, the notch filters, cellular near 1930 MHz (Price 2020, Margot 2021); a weight, not a verdict | blc1 step 3, SETI@home |
| 4 | Zero or very low drift (below one drift step) | UCLA, SonATA |
| 5 | Drift against Earth's expected: rotation and orbit at Green Bank for this star, hour angle and frequency; observed minus expected recorded | blc1 steps 4–5 |
| 6 | Recurrence: any hit within about 100 Hz (plus drift × time apart) in a look at a different target, any session, means interference; the same target in another session is carried forward as support | SonATA, blc1 step 6 |
| 7 | Look-alikes in the same cadence: hits with the same normalised drift (and its mirror); if they show in OFF looks, the candidate inherits their verdict | blc1 step 7 |
| 8 | Harmonics and intermodulation: n × f₀ within 1 kHz; spacings that are integer multiples of common clocks (2.000004, 10, 15, 16, 25, 30, 100, 125, 128, 133.33 MHz); a·f₁ ± b·f₂ against strong zero-drift hits | blc1 §4.4 |
| 9 | Crowding: hits per MHz per hour around the candidate against the band's median | SETI@home, Ma |
| 10 | Report: waterfalls of all six looks around the track, the stamp, every check's evidence, the blc1 10-step checklist marked done or not, a Rio 2.0 score | blc1, Rio 2.0 |

- **Recurrence needs other data.** The OFF looks of this cadence point at
  other stars, so the same session's own OFF looks are the first "other
  target". After that, other sessions and targets on the archive (Phase 8)
  grow the history. There is no public machine-readable Green Bank
  interference list; the archive itself becomes this project's list.
- **Stamps, not instead of hits:** a small time–frequency cut of all six
  looks per candidate is saved with it. blc1's authors warn that keeping
  only stamps loses the context that showed it was ours.

**Done when:** a planted candidate and a planted look-alike family produce
reports with every check filled, and the family is caught by check 7 or 8.

### Phase 6: completeness, measured properly

`inject` rebuilt to plant realistic signals and follow them through the
whole pipeline.

- **Signals as the sky makes them:**
  - power spread over every channel crossed within each spectrum (setigen's
    `doppler_smearing`, sub-stepped);
  - a sinc² channel response;
  - a random position within the channel.
- **Through everything:**
  - the same signal planted in all three ON looks at its drift-consistent
    frequency, none in the OFF looks;
  - search, cadence and vetting run;
  - counted at the end;
  - also planted in OFF looks to measure how often the vetting wrongly
    keeps interference;
  - SETI@home's target: vetting loses under 10% of planted signals.
- **Reported by bin:**
  - SNR;
  - drift (0–0.15, 0.15–0.5, 0.5–1, 1–2, 2–4 Hz/s);
  - position in the coarse channel (edges, DC bin);
  - with the loss at each stage (search, cadence, each check).
- **Checked against setigen** on one saved slice, once, to confirm the
  planted signals match its output.
- **turboSETI comparison pinned:** version 2.3.2, with its known open bugs
  (#296 top-hit suppression, #319 level-3 de-duplication) noted in each
  record; treated as a reference with known flaws, not as truth. It runs in
  WSL if it does not install on Windows.

**Done when:** a completeness table by SNR × drift is in `docs/seti.md`,
measured on the reference cadence through the whole pipeline, replacing the
single-look table.

### Phase 7: the result

`seti.py report TARGET SESSION` writes `docs/results/TARGET-SESSION.md`
stating everything Section 5 of the sensitivity notes lists:

- **The observation:**
  - target and distance with its uncertainty (Gaia DR3);
  - session, scans, UTC times, file URLs and ETags;
  - receiver, SEFD (10 Jy at S-band, Price 2020), frequency covered, fraction
    masked.
- **The search:**
  - channel width, integration, spectra, drift range and step;
  - SNR definition and its relation to true noise and to turboSETI's;
  - the cut, cadence rules, every check and its version.
- **What it achieved:**
  - completeness by SNR and drift, through the whole pipeline;
  - S_min and EIRP_min at the cut and at 50% and 90% completeness, with the
    1 Hz transmitter width stated;
  - CWTFM, and the limit on the fraction of such stars with a transmitter,
    including efficiency (Margot 2023's form).
- **What it found:** hit counts at each stage, every candidate and its
  disposition.
- **How:** git commit, library versions.
- **Context:** set against Harp et al. 2016 (ATA, 1–10 GHz, (4–7)×10¹⁵ W).
  Rough expectation: about 2×10¹⁴ W at the cut, before the drift efficiency
  is folded in.

**Done when:** the Tabby's star 2017 report exists from a complete sweep, and
a second person could repeat it from the report alone.

### Phase 8: beyond one cadence

In order of value:

1. **Validate on a known signal:** Voyager 1 or another spacecraft in the
   open archive (Enriquez 2017's check), found with the right drift. Whether
   the file is public needs checking.
2. **Reproduce a published result:** one star of Price et al. 2020 at S-band,
   comparing hits and events to theirs.
3. **Grow the interference history:** the OFF looks of other sessions near in
   time, searched in the same bands, feeding check 6.
4. **More targets:** the other Tabby sessions (2016, 2018: no full cadence
   listed, still useful for recurrence); then the Exotica catalogue's
   anomalies, TESS and Kepler targets with published BL searches.
5. **The `.0002` product** (2.86 kHz × 1.07 s) for drifts beyond ±4 Hz/s and
   short signals: a separate search, specified when this one is done.
6. **An ML post-filter on stamps** (Ma et al.'s method), only once there are
   enough labelled hits in the store to train on.

## 4. Engineering throughout

- **Package:**
  - `pyproject.toml` gains a build system and entry points, so `seti` and
    `ssy-check` are commands (`.venv\Scripts\seti.exe`);
  - `seti.py` splits into modules (`reading`, `search`, `cadence`,
    `vetting`, `inject`, `store`, `report`) behind the same command line.
- **Logs:**
  - `data/logs/sweep.log` (rotating), one line per block: bytes, fetch and
    search seconds, counts;
  - a lock file stops two sweeps running at once.
- **Unattended runs:**
  - a Windows scheduled task for overnight sweeps (`schtasks`, "run whether
    logged on or not", the PC kept awake);
  - with Phase 1 a full cadence is about 2–2.5 hours.
- **Checks kept short:**
  - a self-check command of a few seconds on tiny synthetic arrays;
  - what it covers: a planted tone found at the right drift; `judge`'s
    labels; channel arithmetic; the direct chunk decode matching h5py; the
    new search matching the old on the reference block;
  - no long test suites, no CI.
- **Politeness:**
  - at most 6–8 concurrent requests, the User-Agent kept, back-off on errors;
  - Lebofsky et al. 2019 cited in the README;
  - there is no published rate limit to keep to, so the project keeps to a
    modest one.
- **Docs follow the code:**
  - `docs/seti.md` and `HANDOVER.md` corrected as each phase lands;
  - first corrections: "SNR 10, turboSETI's default" (not equal); "880 MB a
    block" (300 MB of data); the single-look completeness table (smearing).

## 5. Size and order

| Phase | Depends on | Rough size |
|---|---|---|
| 0 Reference | — | small |
| 1 Fast reading | 0 | medium |
| 2 Hit store | 1 | medium |
| 3 Correct search | 0, 2 | large |
| 4 Cadence test | 3 | medium |
| 5 Vetting | 2, 4 | large |
| 6 Completeness | 3, 4, 5 | medium |
| 7 Result | 6 | small |
| 8 Beyond | 7 | open-ended |

The sweep should not be run further until Phases 1–2 are in: every block
searched now loses its hits and takes 40 times longer.

## 6. Decisions for the owner

1. **Running overnight from this PC**, at up to 6–8 parallel requests to
   Breakthrough Listen's server. No rate limit is published; a short note
   to them first is an option.
2. **The self-check command** (a few seconds) in place of no checks at all.
3. **Whether a result is to be published** (diary, arXiv note, or a message
   to Breakthrough Listen) once Phase 7 gives one; it changes how much
   Phase 6 has to cover.
