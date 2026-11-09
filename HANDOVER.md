# SignalSearchYoke: handover, 8 November 2026

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
| `measure.py` | the search measured on planted signals and real looks: desmearing, close pairs, kurtosis, false hits, the SNR scale against turboSETI, the cadence test, the checks, setigen |
| `tools/setigen_frame.py` | setigen's planted signals, run in turboSETI's environment, for `measure.py setigen` |
| `store.py` | the hit store, `data/ssy.sqlite`: runs, files, blocks, hits, events, checks, injections |
| `check.py` | the ten checks run on the store's candidates: records, reports in `docs/leads/` |
| `yoke.py` | the data folder, the `--json` envelope, writing a record whole |
| `docs/seti.md` | how the search works, and everything measured so far |
| `docs/overhaul.md` | the plan to bring the search up to the published searches' standard (8 Nov 2026) |
| `docs/research/` | the research behind it: other pipelines, vetting, sensitivity, speed |
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
./measure.py WHAT [FILE...]                       desmear, pairs, kurtosis, false, scale, noise, cadence, vetting, setigen
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

## How the search works

1. `search`: each look's spectra summed along every drift line up to 4 Hz
   a second either way, after the band's smooth shape is taken out; the
   noise measured block by block (median and median absolute deviation);
   lines 10 times above the noise kept as hits (turboSETI's default); one
   hit per run of bright channels; the coarse channel's ends masked; the
   receiver's spike at each coarse channel's middle blanked.
2. `cadence`: each hit of the first ON look followed to where its drift
   puts it in the later looks. In every ON look and no OFF look: a
   candidate. In any OFF look: interference. Missing from an ON look:
   unconfirmed.
3. `sweep`: the target's whole cadence, block by block, continuing where
   the last run stopped; every hit of every look and every cadence result
   kept in `data/ssy.sqlite`, one transaction a block, with a readable
   record in `data/sweeps/TARGET-SESSION.json`. The next block is fetched
   while one is searched.
4. `check.py`: each candidate checked for a frequency in a band
   satellites and ground transmitters use (ITU Radio Regulations,
   Article 5) and for a drift of zero; verdict "likely interference" with
   its signs, or "unexplained, weak". Records in `data/checks/`, reports
   in `docs/leads/`.

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

`SSY_TURBOSETI_PYTHON` names another python. On the laptop where this was
built, turboSETI is in `~/.local/share/telescopeyoke/seti-venv` (the old
name); the Windows PC has one at the default place.

## Results so far (details in docs/seti.md)

- **Planted signals** in real noise (3 November 2026, Tabby's 2017 OFF
  look, scan 32, 2266.75-2269.60 MHz, 40 at each strength): found 30% at
  SNR 10, 82% at 12, 98% at 15, 100% at 20 and above; no false hits in
  240 runs. The same in the 2018 look.
- **Against turboSETI** on seven real looks from two sessions (2017
  cadence, 2266.75-2269.60 MHz; 2018 session AGBT18A_999_30, scan 9,
  1472.20-1475.05 MHz): outside one 110 kHz burst of interference,
  turboSETI found nothing this search missed. The sweep was let loose on
  that evidence, 3 November 2026.
- **One whole cadence slice** (six looks, 880 MB read in 23 minutes on
  the laptop): no candidate.
- **The sweep of Tabby's 25 May 2017 cadence** (session AGBT17A_999_68,
  scans 31 to 36, 308 blocks, 1818-2721 MHz): 18 blocks done,
  1818.46-1871.19 MHz, searched again on 9 November 2026 with search
  version 3 (the new cadence test): 0 candidates, 118 interference events
  (every ON look now seeds events), 4 unconfirmed; 287 hits at the cut
  (version 1 found 123) and 28,321 shadow hits; every look complete; no
  candidate for the checks. Block 6 (1836-1839
  MHz) alone has 190 hits, all interference. The version 1 results are
  kept in the store, marked superseded. About 34 s a block on the Windows
  PC (the search, not the network, sets the pace; 31 s with version 3):
  about 2.7 hours for the whole cadence. Every hit is in `data/ssy.sqlite`; the readable record is
  `data/sweeps/KIC8462852-AGBT17A_999_68.json`.
- **The reference block** (block 153, all six looks) is in
  `data/reference/`, with the old search's answer; the new search gives
  the same hits on it, 9× faster.
- No candidate has been found, so `check.py` has nothing to look into
  yet.

## The state on 8 November 2026

- Phases 0 to 6 of [docs/overhaul.md](docs/overhaul.md) are done on the
  Windows PC (9 November 2026): the reference block, fast reading, the hit
  store, a correct search, the cadence test rebuilt (search version 3),
  the ten checks, and completeness measured through the whole pipeline.
  Every measurement is in `data/measurements/` and written up in
  docs/seti.md. Phase 7 (validation on real signals: Voyager 1, a Price
  2020 star) is next. A sweep searches blocks done by an older search
  version again first.
- **Completeness through everything** (3,257 planted signals, five
  cadences): at S_in 60 (41 Jy Hz with an assumed SEFD of 10 Jy) 97 to 100%
  are kept at every drift to 4 Hz/s; at S_in 30, 100% under 0.5 Hz/s, 52%
  at 1 to 2, 4% at 2 to 4. No interference planted in all six looks was
  kept. One false candidate in 95 cadences judged with the wrong ON looks,
  marked by the checks; none unexplained.
- Nothing runs on a timer.
- SETI has been taken out of telescopeyoke; nothing in this repository
  reads or imports anything from it.

## Machines

- **Laptop** (where this was built): Intel i7-7700HQ, 4 cores, 22 GB,
  Ubuntu; Python 3.14 with numpy, requests, h5py and hdf5plugin from
  Ubuntu's packages.
- **Windows PC** (the desktop; `ssh desktop` from the laptop), where the
  project lives and runs now: AMD Ryzen 9 3950X, 16 cores, 40 GB, GTX 1080,
  Windows 11. `C:\Projects\SignalSearchYoke`, a clone of the GitHub
  repository with the laptop's `data/` copied in on 8 November 2026;
  Python 3.12 in `.venv` with the four requirements from pip. Everything
  above runs there from PowerShell (`.venv\Scripts\python seti.py ...`);
  the hit store, chunk indexes and reference block are in its `data/`.
  Other programs there (a llama-server, WSL, Chrome) hold much of its
  memory commit: on 9 November 2026 a sweep ran out with 5.5 GB of 51 GB
  commit free; it now peaks at about 1.9 GB.
  The laptop is `ssh laptop` from it. turboSETI 2.3.2 is in its own venv (above).
- **brokerblitzer**, the always-on server: a KVM VPS, AMD EPYC Milan, 6
  vCPUs at 2.0 GHz, 7.7 GB RAM with no swap, 221 GB free SSD, Ubuntu
  24.04. It builds and serves ryanclinton.uk and runs sungrazeryoke's
  comet hunt.

## GitHub

`Ryan-Clinton/SignalSearchYoke`, private.
