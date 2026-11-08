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
| `check.py` | the sweeps' candidates checked for signs of interference |
| `yoke.py` | the data folder, the `--json` envelope, writing a record whole |
| `docs/seti.md` | how the search works, and everything measured so far |
| `docs/overhaul.md` | the plan to bring the search up to the published searches' standard (8 Nov 2026) |
| `docs/research/` | the research behind it: other pipelines, vetting, sensitivity, speed |
| `schemas/seti.schema.json` | the shape of `seti.py`'s `--json` answers |
| `data/` | sweep records and candidate checks, not in git (below) |
| `docs/leads/` | a report for each candidate `check.py` has looked into (none yet) |
| `requirements.txt` | numpy, requests, h5py, hdf5plugin |

`SSY_DATA` in the environment moves `data/` elsewhere. There is no
settings file.

## Commands

```
./seti.py find KIC8462852                         the target's looks, by session, with the cadence line
./seti.py search URL --from 2250 --to 2253        narrowband hits in one look's slice
./seti.py cadence ON1 OFF1 ON2 OFF2 ON3 OFF3 --from 2250 --to 2253
./seti.py sweep KIC8462852 --blocks N             the next N blocks of the target's whole cadence
./seti.py inject FILE                             signals planted in a saved slice's noise, counted back
./seti.py benchmark FILE...                       saved slices through this search and turboSETI
./check.py [--all]                                the sweeps' candidates looked into
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
   the last run stopped; each block's answer kept in
   `data/sweeps/TARGET-SESSION.json`, with every candidate found.
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
& "$env:LOCALAPPDATA\signalsearchyoke\seti-venv\Scripts\python.exe" -m pip install turbo_seti
```

`SSY_TURBOSETI_PYTHON` names another python. On the laptop where this was
built, turboSETI is in `~/.local/share/telescopeyoke/seti-venv` (the old
name); the desktop has no turboSETI environment.

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
  scans 31 to 36, 308 blocks, 1818-2721 MHz): 12 blocks done,
  1818.46-1853.61 MHz, last on 6 November 2026 22:26 UTC; 0 candidates,
  11 interference, 1 unconfirmed. Its record is
  `data/sweeps/KIC8462852-AGBT17A_999_68.json`.
- No candidate has been found, so `check.py` has nothing to look into
  yet.

## The state on 8 November 2026

- The code was run from this folder on the laptop: `./seti.py --help`,
  and `./check.py` reads the copied sweep record (12 blocks, no
  candidate waiting).
- Nothing runs on a timer.
- SETI has been taken out of telescopeyoke; nothing in this repository
  reads or imports anything from it.

## Machines

- **Laptop** (where this was built): Intel i7-7700HQ, 4 cores, 22 GB,
  Ubuntu; Python 3.14 with numpy, requests, h5py and hdf5plugin from
  Ubuntu's packages.
- **Desktop** (`ssh desktop` from the laptop): AMD Ryzen 9 3950X, 16
  cores, 35 GB; no Python environment with these libraries set up yet.
- **brokerblitzer**, the always-on server: a KVM VPS, AMD EPYC Milan, 6
  vCPUs at 2.0 GHz, 7.7 GB RAM with no swap, 221 GB free SSD, Ubuntu
  24.04. It builds and serves ryanclinton.uk and runs sungrazeryoke's
  comet hunt.

- **Windows PC** (`C:\Projects\SignalSearchYoke`, set up 8 November
  2026): a clone of the GitHub repository with the laptop's `data/`
  copied in; Python 3.12 in `.venv` with the four requirements from
  pip. `seti.py find` and `check.py` run there. The laptop is
  `ssh laptop` from it. No turboSETI environment yet.

## GitHub

`Ryan-Clinton/SignalSearchYoke`, private.
