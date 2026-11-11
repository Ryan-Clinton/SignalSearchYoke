# SignalSearchYoke: handover, 9 November 2026

How this project works and where it stands. It was split out of the
telescopeyoke repository on 8 November 2026; the git history here is the
SETI search's own 12 commits from there, then the split.

## What it does

Searches Breakthrough Listen's published radio recordings for narrowband
signals, as SETI@home did, one slice of the band at a time, and tells
interference from a signal from the target with the ON-OFF cadence test.
It uses no telescope of its own. The first target is Tabby's star,
KIC 8462852.

## Files

| Path | What it is |
|---|---|
| `seti.py` | find, search, cadence, sweep, inject, benchmark |
| `reading.py` | reading the archive's files over the web: chunk index, parallel range requests, retries, the request limit |
| `searching.py` | the search on one look: band shape, desmeared drift sums, noise of the summed lines, hits picked and blanked, shadow hits, spectral kurtosis |
| `onoff.py` | the cadence test: events from every ON look's hits, every look measured along the track, the OFF test with no threshold |
| `vetting.py` | the ten checks on a candidate (after blc1), with strengths, chance rates and a report |
| `injection.py` | signals planted in whole cadences and followed through search, cadence test and checks |
| `measure.py` | the search measured on planted signals and real looks: desmearing, close pairs, kurtosis, false hits, the SNR scale against turboSETI, the cadence test, the checks, setigen; Voyager 1 and Price et al. 2020's HIP 91699 |
| `pipelines.py` | the other pipelines on a swept cadence (comparable.md step 3): turboSETI's event pipeline (`tools/turbo_events.py`) and Painter et al.'s pickles (`tools/pickles_block.py`, fetched at a pinned commit) block by block on the sweep's slices, then `compare` sets each one's events against the others' (data/measurements/pipelines.json, the result page) |
| `instrument.py` | the instrument measured: the fine channel's response (Voyager 1), the SEFD (3C295 ON-OFF pairs, same S-band setup), dropped data from the chunk indexes; via `measure.py response`, `sefd`, `dropped` |
| `tools/setigen_frame.py` | setigen's planted signals, run in turboSETI's environment, for `measure.py setigen` |
| `tools/turbo_events.py` | Price et al. 2020's pipeline (turboSETI hits, then its event pipeline at threshold 3) on a cadence's six slices, for `measure.py price` |
| `store.py` | the hit store, `data/ssy.sqlite`: runs, files, blocks, hits, events, checks, injections |
| `check.py` | the ten checks run on the store's candidates: records, reports in `docs/leads/`; then ranks them |
| `occupancy.py` | the session's interference occupancy by frequency and drift, from its hits: checks 7 and 9's chances (step 6) |
| `curved.py` | EXPERIMENTAL, apart from the search: a cadence test for curved tracks, and curved tracks through turboSETI (step 9) |
| `ranking.py` | comparable.md step 5: the score (the checks' chances), the OFF null, birdies ranked against the real candidates, the held-out wrong-cadence candidates |
| `report.py` | the result of a swept cadence (`seti.py report`): `docs/results/TARGET-SESSION.md`, from the store and the measurements |
| `yoke.py` | the data folder, the `--json` envelope, writing a record whole |
| `docs/seti.md` | how the search works, and everything measured so far |
| `docs/overhaul.md` | the plan to bring the search up to the published searches' standard (8 Nov 2026) |
| `docs/research/` | the research behind it: other pipelines, vetting, sensitivity, speed; the instrument and its calibration; published searches of this star; what comparable pipelines do |
| `docs/comparable.md` | the plan after the first result: what it would take to stand beside the published searches |
| `docs/multiuser.md` | the plan for many people's computers searching: work units, what stays central, double answers and planted signals, the order (not built yet) |
| `schemas/seti.schema.json` | the shape of `seti.py`'s `--json` answers |
| `data/` | not in git: `ssy.sqlite` (every hit), `sweeps/` (readable records), `index/` (each file's chunk index), `reference/` (block 153 of the 2017 cadence and the old search's answer on it), `logs/`, `checks/` |
| `docs/leads/` | a report for each candidate `check.py` has looked into (none yet) |
| `requirements.txt` | numpy, requests, h5py, hdf5plugin |

`SSY_DATA` in the environment moves `data/` elsewhere. There is no
settings file.

## Commands

```
./seti.py find KIC8462852                         the target's looks, by session, with the cadence line
./seti.py search URL --from 2250 --to 2253        narrowband hits in one look's slice
./seti.py cadence ON1 OFF1 ON2 OFF2 ON3 OFF3 --from 2250 --to 2253
./seti.py sweep KIC8462852 --blocks N             the next N blocks of the target's whole cadence (--threads 1-8, default 6)
./seti.py inject                                  signals planted in the saved cadences, through everything (Phase 6)
./seti.py inject --legacy FILE                    the old one-channel planting (superseded)
./seti.py benchmark FILE...                       saved slices through this search and turboSETI
./check.py [--all] [--event ID]                   the ten checks on the store's candidates (or one event)
./seti.py report KIC8462852 AGBT17A_999_68        the result page of a swept cadence (Phase 8)
./pipelines.py run KIC8462852                      turboSETI and pickles over the swept cadence (about 2 hours; resumes)
./pipelines.py compare KIC8462852                  each pipeline's events against the others' (then the report again)
./pipelines.py followup KIC8462852                 taken to the signal: pickles' windows with our tracks blanked, turboSETI's own SNR
./matched.py run KIC8462852                        steps 4 and 7: false candidates (wrong ON choices) and planted-signal recovery, all three pipelines
./matched.py tracks KIC8462852                     blocks recorded before the measured ON tracks were kept: judged again and completed
./matched.py tables KIC8462852                     their curves, matched cuts and recovery tables (docs/results/...-matched.md)
./measure.py WHAT [FILE...]                       desmear, pairs, kurtosis, false, scale, noise, cadence, vetting, setigen, voyager, price,
                                                  response, sefd, dropped TARGET SESSION
```

`search` and `cadence` take `--keep DIR` to save each slice read (a small
HDF5 file in Breakthrough Listen's layout), for `inject` and
`benchmark`. Every command takes `--json`.

## The data

- Breakthrough Listen's open data: `seti.berkeley.edu/opendata`. Green
  Bank, Parkes and others observe in cadences: three five-minute looks at
  the target, each followed by one at another star (ON, OFF, ON, OFF, ON,
  OFF).
- The finest product of each look, `.gpuspec.0000.h5`: channels about
  2.8 Hz wide, one spectrum every 18 seconds, about 15 GB a file. HDF5,
  in blocks, packed with bitshuffle. `seti.py` reads only the blocks of
  the slice asked for, over the web, with HTTP range requests.
- A block is one coarse channel: 1,048,576 fine channels, 2.93 MHz.
- `find` reads the archive's listing; the OFF looks are filed under their
  own name (KIC8462852_OFF), so it reads them from the session's folder.

## How the search works (search version 4, 9 November 2026)

`docs/seti.md` has each step and what it was measured to do.

1. `search` (`searching.py`): each spectrum's band shape taken out and its
   noise measured block by block; every drift line to ±4 Hz/s summed, a
   box of channels wide enough for its smear; the S/N against the noise
   of the summed lines themselves; the strongest picked and its track
   blanked, again and again. Hits at SNR 10 (the cut) and shadow hits from
   SNR 5 are kept; spectral kurtosis is recorded, never used to drop; at
   2,000 hits a look the look is marked not complete.
2. `cadence` (`onoff.py`): every ON look's hits at the cut seed events;
   hits join by one distance, one to one, and only when every hit of a
   group matches every other. Every look is measured along each event's
   track: an OFF look at S/N 6 or more there, or with any hit near, makes
   it interference; a candidate is in every ON look and no OFF look; the
   rest are unconfirmed. In each block 32 random tracks measure how often
   the OFF test would veto a real signal.
3. `sweep`: the target's whole cadence, block by block, continuing where
   the last run stopped; every hit and event kept in `data/ssy.sqlite`,
   one transaction a block, older search versions marked superseded and
   searched again first; a readable record in
   `data/sweeps/TARGET-SESSION.json`.
4. `check.py` (`vetting.py`): ten checks on each candidate, after blc1:
   data sanity, the OFF looks, bands, zero drift, the Earth's drift,
   recurrence, look-alikes, harmonics and intermodulation, crowding, the
   report. Each says shown, indicated or coincidence possible, with its
   chance; none deletes a candidate. Records in `data/checks/`, reports in
   `docs/leads/`. Checks version 3: recurrence (check 6) takes its chance
   from every queried file's hits within 1.5 MHz of the candidate, over the
   band searched there, not from the hits picked for matching.
5. `seti.py report` (`report.py`): the result page. Limits are measured
   (50% and 90% of planted signals kept) and quoted over the usable band:
   the notch and every block with a look stopped at the hit limit left out
   and listed; the SNR-10 figure is labelled nominal.
   The flux scale is the SEFD measured on 3C295 (10.65 Jy), and the page
   opens with what the search can and cannot see.

## turboSETI

Breakthrough Listen's own search, used by `benchmark` to compare. Not an
Ubuntu package: it goes in its own environment that sees the system's
h5py:

```
python3 -m venv --system-site-packages ~/.local/share/signalsearchyoke/seti-venv
~/.local/share/signalsearchyoke/seti-venv/bin/pip install turbo_seti
```

On Windows the default place is
`%LOCALAPPDATA%\signalsearchyoke\seti-venv\Scripts\python.exe`:

```
py -3 -m venv $env:LOCALAPPDATA\signalsearchyoke\seti-venv
& "$env:LOCALAPPDATA\signalsearchyoke\seti-venv\Scripts\python.exe" -m pip install turbo_seti "setuptools<80" "numpy<2" "pandas<2.3" "scipy<1.14" "matplotlib<3.9" "contourpy<1.3" "h5py<3.12" "numba<0.61" "astropy<6.2" "hdf5plugin<5"
```

The pins matter (9 November 2026, Python 3.12): turboSETI 2.3.2 fails on
numpy 2 (`%i` given an array), and blimpy needs `pkg_resources` (missing from
the newest setuptools; 79 has it) and an astropy that still runs on numpy 1. With them,
turbo_seti 2.3.2 and blimpy 2.1.4 run. turboSETI also writes its log beside
a path it joins wrongly on Windows; `seti.py` runs it from the file's own
folder to avoid that.

`SSY_TURBOSETI_PYTHON` names another python; the Windows PC has one at
the default place.

## Results so far (details in docs/seti.md)

- **Planted signals:** the current figures are Phase 6's, through the
  whole pipeline (below, and docs/seti.md, "Completeness through the whole
  pipeline"). The 3 November 2026 single-look figures (98% at SNR 15) were
  made with a one-channel planting that overstates what is found above
  0.15 Hz/s; they are kept in docs/seti.md as history only.
- **Against turboSETI** on seven real looks from two sessions (2017
  cadence, 2266.75-2269.60 MHz; 2018 session AGBT18A_999_30, scan 9,
  1472.20-1475.05 MHz): outside one 110 kHz burst of interference,
  turboSETI found nothing this search missed. The sweep was let loose on
  that evidence, 3 November 2026.
- **The sweep of Tabby's 25 May 2017 cadence** (session AGBT17A_999_68,
  scans 31 to 36, 308 blocks, 1818-2721 MHz), search version 4: done,
  9 November 2026, 07:52 to 12:55 UTC on the Windows PC. 11 candidates;
  `check.py` (checks version 3) calls 2 interference and 9 likely
  interference (indicated, not identified), none unexplained. Searched
  completely 861.3 MHz; usable band 801.3 MHz (the notch and 14
  blocks cut short at the hit limit left out); EIRP at 90% kept
  3.1×10¹⁴ W (slow drifts) to 9.5×10¹⁴ W (2-4 Hz/s). The result page is
  `docs/results/KIC8462852-AGBT17A_999_68.md`, the candidates' reports
  `docs/leads/`. Every hit is in `data/ssy.sqlite`; the readable record is
  `data/sweeps/KIC8462852-AGBT17A_999_68.json`.
- **The reference block** (block 153, all six looks) is in
  `data/reference/`, with the first search's answer (8 November 2026).
  The fast reading gave the same hits 9× faster; the search rewritten
  since (search version 2, Phase 3) finds more, and docs/seti.md, "A
  correct search", says what changed.

## The state on 9 November 2026

- Phases 0 to 8 of [docs/overhaul.md](docs/overhaul.md) are done on the
  Windows PC (9 November 2026): the reference block, fast reading, the hit
  store, a correct search, the cadence test rebuilt (search version 4),
  the ten checks, completeness measured through the whole pipeline, and
  validation on real signals (Voyager 1; Price et al. 2020's HIP 91699
  event). Every measurement is in `data/measurements/` and written up in
  docs/seti.md; the files read for Phase 7 are in `data/validation/`.
  Phase 8 (the result) is done: the whole cadence swept and its result
  page written (above). A sweep searches blocks done by an older search
  version again first. comparable.md step 3 is done (9 November 2026,
  13:05 to 15:06 UTC): turboSETI and pickles over all 308 blocks, every
  disagreement explained in the result page. Steps 4 and 7 are done (10
  November 2026, `matched.py run`, `tracks`, `tables`; 121 blocks): at 0.1
  false candidates a block both pipelines need SNR 30, and there this
  search recovers 4,520 of 13,310 planted signals in all three ON looks,
  turboSETI 442 (docs/seti.md, "The pipelines at matched sensitivity").
  The cuts were chosen on the same blocks, so step 10 (fixed beforehand:
  SNR 30 both, another session's whole cadence) tests them unchanged.
  Step 5 is done (11 November 2026, `ranking.py`): every candidate
  ranked by the sum of the checks' chances (nothing fitted); planted
  signals rank ahead of every real candidate as often as they are kept,
  except in the bands near zero drift; the 24 held-out wrong-cadence
  candidates, checked with the store's evidence, are all marked
  interference, but the best of four marked only for crowding outranks
  44% of the planted ones. Step 6 is done in part (11 November 2026, `occupancy.py`,
  checks version 4): crowding and look-alikes by measured occupancy and
  drift; the worst held-out case falls from ahead of 44% of the planted
  signals to 15%, three in block 14 unexplained again. Curved tracks
  (step 9) are measured: the cadence test loses signals from 2-3e-5
  Hz/s^2 at slow drifts; `curved.py` is experimental, kept apart. Next:
  step 10 (another session, cuts fixed), and a curved second pass on
  step 4's blocks before any change to `onoff.py`.
- **Real signals:** Voyager 1's carrier and sidebands found at turboSETI's
  published frequencies and drifts, the drift the Earth's; wide signals
  (its 322 Hz sidebands) are tiled with many hits, a known gap. HIP 91699's
  S-band event (Price et al. 2020) found by both pipelines (two
  candidates here, kept as two), and marked likely interference
  (indicated) by the band and by look-alike shadow hits in the third OFF
  look.
- **Completeness through everything** (3,257 planted signals, five
  cadences): at S_in 60 (41 Jy Hz with an assumed SEFD of 10 Jy) 97 to 100%
  are kept at every drift to 4 Hz/s; at S_in 30, 100% under 0.5 Hz/s, 52%
  at 1 to 2, 4% at 2 to 4. No interference planted in all six looks was
  kept. One false candidate in 95 cadences judged with the wrong ON looks,
  marked by the checks; none unexplained. The 95 share five real
  cadences' looks: counted per real cadence, 0.2 a block (95% 0.005 to
  1.1), a wide bound the sweep itself will narrow.
- Nothing runs on a timer.
- SETI has been taken out of telescopeyoke; nothing in this repository
  reads or imports anything from it.

## Machines

- **Windows PC**, where the
  project lives and runs now: AMD Ryzen 9 3950X, 16 cores, 40 GB, GTX 1080,
  Windows 11. `C:\Projects\SignalSearchYoke`, a clone of the GitHub
  repository with the laptop's `data/` copied in on 8 November 2026;
  Python 3.12 in `.venv` with the four requirements from pip. Everything
  above runs there from PowerShell (`.venv\Scripts\python seti.py ...`);
  the hit store, chunk indexes and reference block are in its `data/`.
  Other programs there (a llama-server, WSL, Chrome) hold much of its
  memory commit: on 9 November 2026 a sweep ran out with 5.5 GB of 51 GB
  commit free; it now peaks at about 1.9 GB.
  turboSETI 2.3.2 is in its own venv (above). This is the only machine
  the project runs on; the laptop it was built on (Ubuntu, 4 cores) is no
  longer used for it.

## GitHub

`Ryan-Clinton/SignalSearchYoke`, private.
