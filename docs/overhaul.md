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
   "SNR 10" is about 33 in true noise (Choza et al. 2024, §III.1.5, measured
   on their data; the ratio depends on band shape and noise, so it is not a
   fixed conversion). The docs' "SNR 10, turboSETI's default" is therefore
   not an equal threshold, and no limit can yet be quoted against published
   ones.
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
   - Remaining 296 blocks: about 4–5 days now; estimated 2–2.5 hours
     after (about 92 GB at the 11–14 MB/s measured; not yet run end to
     end).

What it already does better than turboSETI, and keeps:

- an exact-line brute-force drift sum (no Taylor-tree path errors);
- the band shape and noise measured block by block (turboSETI's whole-channel
  noise is the source of the 3.25× error Choza et al. measured);
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
- **G5. Produce a result.** A measured limit on narrowband transmitters at
  Tabby's star in 1.8–2.7 GHz: the EIRP reached, the band covered and the
  completeness, checked first on a known real signal. Not claimed as the
  first: Painter et al. 2025 searched the whole Green Bank archive at
  Berkeley as of July 2023, which holds these cadences, though they publish
  no per-star limit and do not name this star. The value is in what this
  search measures (completeness through the whole pipeline, drift loss,
  kept hits) and in any candidate it finds that theirs missed. Harp et al.
  2016's ATA limit is about 20–30× shallower.

**Not goals, and why:**

- **GPU code, for now.** The measurements do not justify it: the search is
  about 4 s a look in numpy, and the network sets the pace. The GTX 1080 is
  Pascal, which CUDA 13 dropped (`cupy-cuda12x` still serves it). If a later
  method (wider drifts, the `.0002` product) becomes compute-bound, this is
  looked at again.
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

**Done, 8 November 2026:** block 153 (2266.699–2269.629 MHz, the
benchmarked slice's whole coarse channel) in `data/reference/`, the old
search's hits and events in `baseline.json`; `provenance()` lists numpy,
h5py, hdf5plugin, requests and HDF5; sweep records are stamped.

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

- the direct chunk path gives arrays bit-identical to h5py's on the
  reference block: same values, same shape, same chunk order;
- the reference block gives the same hits as the baseline, or each
  difference is explained (float32 rounding);
- a sustained run of at least 10 consecutive blocks of the live cadence
  averages 40 s a block or less, a target set from the estimate above,
  not yet shown. It logs bytes moved, fetch and search seconds, CPU use
  and peak memory, and is repeated at 4, 6 and 8 threads to pick the
  count;
- `find()` results are cached per run.

**Done, 8 November 2026** (`reading.py`; details in `docs/seti.md`):

- direct reads bit-identical to h5py on all of block 153 of scan 31;
- the reference block's hits and events identical to the baseline, not
  merely within rounding; 4.2 s a look against 39 s. The float32 sums are
  done a cache-sized tile at a time: across the whole band at once they
  were memory-bound, and six looks in threads took no less time than in
  turn;
- 11 consecutive blocks averaged 21.6 s after the first (fetch 17–20 s,
  hidden; search 19–24 s; about 5 cores; 4.2 GB peak); at 4 and 8
  threads the fetch took about 21 s and 17 s, so the run is search-bound
  and 6 stays the default;
- the cadence's six files are kept in the store, so a sweep after the
  first asks the archive nothing but each file's ETag.

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

**Done, 8 November 2026** (`store.py`): the sweep fills `runs`, `files`,
`blocks`, `hits`, `events` (and `event_hits`, linking each event to the
hit it matched in each look); `inject` fills `injections` (240 rows from
one run); `check.py` writes `checks`, empty until there is a candidate.
The 12 old blocks were searched again with the same counts as before, and
the ±200 Hz query finds 140 pairs across files. `power`, `noise` and the
flags are filled; `flagged_fraction` waits for Phase 3's spectral
kurtosis, and is NULL (not measured), never 0, until then.

**Before Phase 3's re-search (done 9 November 2026):** a re-searched
block keeps its earlier hits and events, marked superseded by the new run,
with the checks made on them; each new event links to the one it
replaces; each run records the search's version. Phase 3 must raise
`SEARCH_VERSION`. Phase 3 also states `power` and `noise` in physical
units once the calibration exists; until then they are the file's data
units, as `store.py` says.

### Phase 3: a correct search

1. **SNR on the true scale.**
   - Noise is measured on the drift-summed output, a robust standard
     deviation of each block's summed rows, not per spectrum × √16.
   - Checked with signals of known power planted into the reference slices.
   - The relation to turboSETI's scale is measured, not assumed: `benchmark`
     runs both on the same saved slices, and the ratio of their SNRs for the
     same signals is recorded per block. The docs give the median ratio, its
     spread across blocks and bands, and how it was measured. Choza's 3.25
     is quoted as their figure, for comparison only.
2. **Desmearing.**
   - For drift lines faster than one channel per spectrum, each spectrum's
     contribution is a boxcar of ⌈|drift| × tsamp / channel width⌉ channels
     along the line (hyperseti and BLISS), which recovers about √N of the
     lost sensitivity.
   - Alternative: scrunch adjacent channels per drift octave (Breakthrough
     Listen's Kepler search).
   - Chosen here, in Phase 3, by a small injection test on the reference
     slices: smeared signals in each drift bin of Phase 6, at a few SNRs,
     through both methods. The test counts signals recovered at the right
     frequency and drift, and also whether two signals planted close
     together (a few to a few hundred channels apart) come out as two hits:
     a method that gains one signal's power by merging its neighbour loses.
     Phase 6 then measures the chosen method in full.
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
   carries its flagged fraction as a recorded sign, not a verdict.
   - With only 16 spectra a look, SK is noisy (2/√16 = 0.5); its false-flag
     rate on real noise is measured before it is used.
   - A steady tone has low SK, so a two-sided flag would mark the very
     signal being searched for. Only the high side counts as an
     interference sign, and the injection tests (here and in Phase 6) run
     with SK flagging on, so its effect on planted signals is measured, not
     assumed.
6. **Drift range:** ±4 Hz/s stays. Earth's own motion gives at most about
   0.36 Hz/s at 2.7 GHz, and Li et al. 2023 put 99% of plausible signals for
   a Kepler-like star within about 1.2 Hz/s here. Completeness is reported
   by drift bin, not as one number.

**Done when:**

- the reference slices give the same strong hits as before (2267.509 MHz
  tone, burst at 2266.79–2266.91 MHz);
- planted smeared signals at 1 and 4 Hz/s are found at a stated, measured
  rate, and the desmearing method is chosen;
- the false-hit rate at the cut is measured on signal-free data from
  several blocks and bands (the reference looks time-shuffled or
  frequency-flipped, and quiet slices elsewhere), and stated as a rate per
  block with its interval, not as "none".

**Done, 9 November 2026** (`searching.py`, `measure.py`; every figure in
`docs/seti.md`, "A correct search"; search version 2):

- **Item 1, the SNR scale.** The noise of the summed lines, measured on
  them per block and box width, is √(16N) times a spectrum's noise to
  within 3% at the median (90th percentile of blocks 1.05 to 1.18) in all
  five blocks: the old per-spectrum assumption was right in spread. It was
  wrong in level: the summed lines sit about 0.5 a channel above zero (the
  skew of the power), which read every old SNR about 0.13 high; the median
  is now taken off. Against turboSETI 2.3.2 on 123 planted slow signals in
  five blocks and bands, turboSETI's SNR is 0.227 of this search's
  (0.224 to 0.242 across blocks): its cut of 10 is about 44 here.
- **Item 2, desmearing:** the boxcar, chosen over scrunching and none on
  800 planted signals in four bands per method: at 2 to 4 Hz/s and S_in 60
  it finds 95% (scrunch 45%, none 0%), and it makes no stray hits where
  none made 131. In the close-pair test it resolves everything the other
  methods do except two lines inside one box.
- **Item 3, hits picked and blanked one at a time:** a weak signal beside
  one 20 times stronger found in 48 of 48 pairs at 10 to 300 channels; a
  wide burst recorded as one hit, marked wide.
- **Item 4, shadow hits** from SNR 5: about 250 to 350 a look, kept,
  never used as seeds or matches by the cadence test (Phase 4 uses them).
- **Item 5, spectral kurtosis:** the flag at 3 marks about 0.02% of a
  quiet look's channels (noise alone: 0.008%), and leaving them out of the
  noise changes nothing found. It flags strong slow real signals over most
  of their tracks, as feared: `flagged_fraction` is recorded, never a
  verdict.
- **Done-when:** the reference block gives the same strong hits and the
  same cadence labels; planted smeared signals are found at 22% (S_in 30)
  and 100% (S_in 60) at 1 to 2 Hz/s, and 95% (S_in 60) and 100% (S_in 120)
  at 2 to 4 Hz/s; false hits on scrambled looks: none in 48 looks of four
  quiet blocks (at most 0.46 a block, 95%), 26.5 a block (19.9 to 34.7)
  in the reference block, whose strong tone and burst, scrambled, become
  impulsive interference. False hits depend on interference and are
  quoted with it.
- **The sweep with it:** the 18 swept blocks searched again: 287 hits at
  the cut (123 before), 0 candidates; about 34 s a block, so G4's evening
  for a cadence becomes about 2.9 hours, set by the search.
- **Not yet:** the planted signals here are made with an FFT channel's
  sinc² response; Breakthrough Listen's polyphase filterbank response was
  not modelled (Phase 6). `inject` still uses the old one-channel planting
  until Phase 6 rebuilds it.

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

**Done, 9 November 2026** (`onoff.py`, search version 3; `docs/seti.md`,
"The cadence test"): seeds from every ON look; one-to-one matching by one
stated distance; every look measured along the track; the OFF test with
no threshold, OFF level 6 set from planted signals; the per-look drift fit
and its flag; the DOT score. Planted in five cadences: 359 of 370 ON-only
signals found came out candidates (10 vetoed by noise at the then OFF level
of 5, which then rose to 6; one fast signal unconfirmed); 71 of 71 signals
planted in all six looks came out interference; 2267.509 MHz is still
interference, and 2269.557 MHz, which starts in the second ON look, now is
too.

### Phase 5: vetting (`check.py` rebuilt)

Each candidate is run through these checks in order. Every result is stored
in `checks` with its evidence; no check deletes a candidate, they score it.
Each check's result has one of three strengths, kept apart:

- **shown:** the same signal is demonstrably elsewhere: in an OFF look of
  this cadence, or matched in frequency, drift and shape at another target
  close in time;
- **indicated:** a strong sign short of proof (a known band, zero drift, a
  frequency match in another session months away);
- **coincidence possible:** a relation (harmonic, intermodulation,
  frequency match) whose chance rate, given how many hits there are, is not
  small. The chance rate is computed and recorded with it.

The verdict is "interference (shown, named reason)", "likely interference
(indicated, named reasons)", "unexplained, weak", or "unexplained, strong".
Only a "shown" result makes "interference" on its own.

| # | Check | From |
|---|---|---|
| 1 | Data sanity: block complete, no NaN or zero runs, flagged fraction small | blc1 step 1 |
| 2 | Sub-threshold OFF power (Phase 4) | blc1 step 2, UCLA |
| 3 | Known Green Bank interference bands: GPS, GLONASS, Iridium, Inmarsat, satellite radio, the notch filters, cellular near 1930 MHz (Price 2020, Margot 2021); a weight, not a verdict | blc1 step 3, SETI@home |
| 4 | Zero or very low drift (below one drift step) | UCLA, SonATA |
| 5 | Drift against Earth's expected: rotation and orbit at Green Bank for this star, hour angle and frequency; observed minus expected recorded | blc1 steps 4–5 |
| 6 | Recurrence: hits within about 100 Hz (plus drift × time apart) in looks at other targets. "Shown" only within the same session or days of it, with the drift agreeing too; further apart in time, "indicated", with the chance of a match at that hit density recorded. The same target in another session is carried forward as support | SonATA, blc1 step 6 |
| 7 | Look-alikes in the same cadence: hits with the same normalised drift (and its mirror); if they show in OFF looks, the candidate inherits their verdict | blc1 step 7 |
| 8 | Harmonics and intermodulation: n × f₀ within 1 kHz; spacings that are integer multiples of common clocks (2.000004, 10, 15, 16, 25, 30, 100, 125, 128, 133.33 MHz); a·f₁ ± b·f₂ against strong zero-drift hits. Each match carries the chance of finding one by accident among that many hits (from shuffled frequencies), and is "coincidence possible" unless that chance is small | blc1 §4.4 |
| 9 | Crowding: hits per MHz per hour around the candidate against the band's median | SETI@home, Ma |
| 10 | Report: waterfalls of all six looks around the track, the stamp, every check's evidence, and the blc1 10-step checklist with each step marked automated, reviewed by hand, not possible from archive data (re-observation: the project has no telescope), or awaiting follow-up. A Rio 2.0 assessment only for an "unexplained, strong" candidate, made by hand | blc1, Rio 2.0 |

- **Recurrence needs other data.** The OFF looks of this cadence point at
  other stars, so the same session's own OFF looks are the first "other
  target". After that, other sessions and targets on the archive (Phase 9)
  grow the history. There is no public machine-readable Green Bank
  interference list; the archive itself becomes this project's list.
- **Stamps, not instead of hits:** a small time–frequency cut of all six
  looks per candidate is saved with it. blc1's authors warn that keeping
  only stamps loses the context that showed it was ours.

**Done when:** a planted candidate and a planted look-alike family produce
reports with every check filled, and the family is caught by check 7 or 8.

**Done, 9 November 2026** (`vetting.py`, `check.py`; `docs/seti.md`,
"The checks"): the ten checks with strengths and chance rates, records in
the store's `checks` table, reports with a PNG of the six looks. In block
100 a lone planted signal came out "unexplained, strong" and a look-alike
family's ON-only member "likely interference" by check 7 (12 look-alikes in
the OFF looks where 0.12 were expected); in block 153 both were marked by
the band they sit in (2200-2290 MHz downlinks), the family member by check
7 too. Not automated: re-observation (impossible here), an observatory
interference database (none published), and judging look-alikes by eye.

### Phase 6: completeness, measured properly

`inject` rebuilt to plant realistic signals and follow them through the
whole pipeline.

- **Signals as the sky makes them:**
  - power spread over every channel crossed within each spectrum (setigen's
    `doppler_smearing`, sub-stepped);
  - a sinc² channel response;
  - a random position within the channel.
- **Strength set independently of the search:** each signal's power is set
  per channel per spectrum against the noise of the raw spectra around it
  (not the drift-summed SNR the search reports), and also given in Jy from
  the SEFD, so the detector is not measured with its own ruler.
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
  - with the loss at each stage (search, cadence, each check);
  - every rate with its 95% binomial (Wilson) interval and its number of
    trials; at least 100 trials in each bin quoted.
- **Checked against setigen** on one saved slice, once, to confirm the
  planted signals match its output.
- **turboSETI comparison pinned:** version 2.3.2, with its known open bugs
  (#296 top-hit suppression, #319 level-3 de-duplication) noted in each
  record; treated as a reference with known flaws, not as truth. It runs in
  WSL if it does not install on Windows.

- **False candidates through the whole pipeline:** how often noise or
  interference alone makes a candidate that survives the six looks and
  the checks, measured on whole cadences (Phase 3's scrambled looks test
  one look's detections only).

**Done when:** a completeness table by SNR × drift is in `docs/seti.md`,
measured on the reference cadence through the whole pipeline, with
intervals, replacing the single-look table.

**Done, 9 November 2026** (`injection.py`, `seti.py inject`; `docs/seti.md`,
"Completeness through the whole pipeline"): 3,257 signals through search,
cadence test and checks in five cadences (the reference and four more
bands), 130 to 145 a cell, Wilson intervals, flux from an assumed SEFD of
10 Jy. Kept at S_in 60 (41 Jy Hz): 97 to 100% at every drift; at S_in 30,
100% under 0.5 Hz/s, 52% at 1 to 2, 4% at 2 to 4. Lost almost entirely at
the search; 10 at the cadence test; none at the checks, which mark (band,
zero drift, chance relations) without dropping. No interference planted
in all six looks was kept. False candidates on 95 cadences judged with
the wrong ON looks: 1, marked by the checks; none unexplained. The planting
matches setigen 2.7's. turboSETI 2.3.2 pinned with its known bugs in the
scale record. Short of the plan: the middle-of-channel bin has 20 signals,
not 100; the polyphase filterbank response is not modelled; the SEFD is
assumed.

### Phase 7: validation on real signals

Planted signals test the pipeline against the model of a signal; real
transmissions test it against what the model leaves out. Before any result
is written:

1. **A known spacecraft:** Voyager 1 (Enriquez 2017's check). The file is
   public (checked 8 Nov 2026):
   `blpd0.ssl.berkeley.edu/Voyager_data/Voyager1.single_coarse.fine_res.h5`,
   one coarse channel, 50 MB. Found at the published frequency and drift,
   with its sidebands, and its SNR set against turboSETI's on the same file.
2. **A published result reproduced:** one star of Price et al. 2020 at
   S-band, comparing hits and events to theirs. Wanted before the result;
   if it cannot be done (data or their hit list not public), the report
   says so among its limitations.

**Done when:** Voyager 1 is recovered and written up in `docs/seti.md`, and
the Price reproduction is done or its absence recorded.

**Done, 9 November 2026** (`measure.py voyager`, `measure.py price`,
`tools/turbo_events.py`; `docs/seti.md`, "Real signals"): Voyager 1's
carrier and both sidebands found within one channel and two drift steps
of turboSETI's published hits, the drift matching the Earth's toward
Voyager (−0.3772 predicted, −0.3776 measured); turboSETI's SNR 0.18 to
0.27 of ours. Its wide sidebands are tiled with 34 hits at other drifts:
wide signals are left out of the model. Price et al. published no hit or
event lists; their pipeline, run here on HIP 91699's two S-band cadences
at 2200.0 to 2200.6 MHz, finds the event they show (2200.050 MHz,
−3.83 Hz/s) in one, nothing in the other; this search makes it two
candidates (kept as two: consistent with one transmitter whose drift
changes, not shown), and the checks call both likely interference
(indicated: the band, and look-alike shadow hits in the third OFF look),
as Price et al. judged by eye. Afterwards: "shown" from recurrence now
needs a hit at the cut with a small chance; groups of hits join only when
all match (no chains); false candidates are counted per real cadence
(0.2, 95% 0.005 to 1.1), not per choice of ON looks; the OFF test's veto
rate is measured on random tracks in every block of a sweep; the Voyager
file's SHA-256 is checked.

### Phase 8: the result

`seti.py report TARGET SESSION` writes `docs/results/TARGET-SESSION.md`
stating everything Section 5 of the sensitivity notes lists:

- **The observation:**
  - target and distance with its uncertainty (Gaia DR3);
  - session, scans, UTC times, file URLs and ETags;
  - receiver, SEFD (measured on 3C295: 10.65 Jy; 10 Jy assumed before, Price 2020), frequency covered, fraction
    masked.
- **The search:**
  - channel width, integration, spectra, drift range and step;
  - SNR definition and its relation to true noise and to turboSETI's;
  - the cut, cadence rules, every check and its version.
- **What it achieved:**
  - completeness by SNR and drift, through the whole pipeline;
  - S_min and EIRP_min at 50% and 90% completeness, measured, leading;
    at the cut only as the nominal radiometer-equation threshold, labelled
    so (the faintest planted signals are S_in 15, not 10); the 1 Hz
    transmitter width stated;
  - the usable band: the band searched less the notch and every block
    with a look stopped at the hit limit, those blocks listed; "complete"
    only when every block is searched and none is cut short;
  - CWTFM from the usable band, for comparison with published searches
    only. No limit on the
    fraction of stars with transmitters: for one star, Margot 2023's form
    gives at best 0.95/(η·D) at 95% confidence, which says nothing. That
    waits for a defined sample of many stars (Phase 9).
- **Validation:** Phase 7's results, and each check not done.
- **What it found:** hit counts at each stage, every candidate and its
  disposition. Candidates are reported one by one, never merged: two
  thought to be one transmitter are said to be so only with the evidence,
  as a hypothesis. Those marked only for their band are counted apart
  from those marked by any other check, and the band marks are not read
  as a finding about the signal.
- **The OFF test's veto rate** over the swept band, from the random
  tracks of every block (`blocks.off_null_*`), against the 0.5% measured
  on planted signals.
- **How:** git commit, library versions.
- **Context:** set against Harp et al. 2016 (ATA, 1–10 GHz, (4–7)×10¹⁵ W).
  Rough expectation: about 2×10¹⁴ W at the cut, before the drift efficiency
  is folded in.

**Done when:** the Tabby's star 2017 report exists from a complete sweep, and
a second person could repeat it from the report alone.

**Done, 9 November 2026:** all 308 blocks searched (search version 4),
[results/KIC8462852-AGBT17A_999_68.md](results/KIC8462852-AGBT17A_999_68.md)
written from it: 11 candidates, every one explained by the checks (2
interference, 9 likely interference); usable band 801.3 MHz; EIRP at 90%
kept 3.1×10¹⁴ to 9.5×10¹⁴ W. It is complete in coverage, not in depth:
14 blocks were cut short at the hit limit and are left out of the limits.

### Phase 9: beyond one cadence

**Replaced, 9 November 2026,** by [comparable.md](comparable.md): the steps
that would let this search be set beside the published ones, in order of
value. The list below is kept as it was.

In order of value:

1. **Grow the interference history:** the OFF looks of other sessions near in
   time, searched in the same bands, feeding check 6.
2. **More targets:** the other Tabby sessions (2016, 2018: no full cadence
   listed, still useful for recurrence); then the Exotica catalogue's
   anomalies, TESS and Kepler targets with published BL searches. A
   defined sample of many stars is what a population limit needs.
3. **The `.0002` product** (2.86 kHz × 1.07 s) for drifts beyond ±4 Hz/s and
   short signals: a separate search, specified when this one is done.
4. **An ML post-filter on stamps** (Ma et al.'s method), only once there are
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
- **Unattended runs (optional; decision 1 below):**
  - if wanted, a Windows scheduled task for overnight sweeps (`schtasks`,
    "run whether logged on or not", the PC kept awake); the sweep does not
    depend on it;
  - with Phase 1 a full cadence is estimated at 2–2.5 hours.
- **Checks kept short:**
  - a self-check command of a few seconds on tiny synthetic arrays;
  - what it covers: a planted tone found at the right drift; `judge`'s
    labels; channel arithmetic; the direct chunk decode matching h5py; the
    new search matching the old on the reference block;
  - no long test suites. No CI is planned now; a lint-and-self-check job
    on GitHub can be added later if it earns its place.
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
| 7 Validation | 3, 4 | small to medium |
| 8 Result | 6, 7 | small |
| 9 Beyond | 8 | open-ended |

The sweep should not be run further until Phases 1–2 are in: every block
searched now loses its hits and takes 40 times longer.

## 6. Decisions for the owner

1. **Running overnight from this PC**, at up to 6–8 parallel requests to
   Breakthrough Listen's server. No rate limit is published; a short note
   to them first is an option.
2. **The self-check command** (a few seconds) in place of no checks at all.
3. **Whether a result is to be published** (diary, arXiv note, or a message
   to Breakthrough Listen) once Phase 8 gives one; it changes how much
   Phases 6 and 7 have to cover.
