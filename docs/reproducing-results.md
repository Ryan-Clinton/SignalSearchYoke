# Reproducing the results

Three levels, from cheapest to dearest:

1. **Check a number against its record.** Every number in the report and
   the result pages is read from a JSON record, never typed. The records
   are in the evidence package (below).
2. **Make the tables again from the records,** without reading a spectrum:
   minutes, with only the core environment.
3. **Run the search and the comparisons again** from Breakthrough Listen's
   archive: hours to days, with turboSETI's environment and, for BLISS, a
   CUDA build in WSL or Linux.

## The environments

| Environment | For | What it is |
|---|---|---|
| Core | the search, the cadence test, the checks, planting, the tables | `requirements.txt`: numpy, requests, h5py, hdf5plugin. The versions that made the published records: [environments/core-windows.txt](environments/core-windows.txt), usable as constraints (`pip install -r requirements.txt -c docs/environments/core-windows.txt`) |
| Development | ruff and the offline tests | `requirements-dev.txt`; `python -m unittest discover -s tests -v` |
| turboSETI | turboSETI, pickles and setigen comparisons | its own venv (below); versions in [environments/turboseti-windows.txt](environments/turboseti-windows.txt) |
| BLISS | step 11 | BLISS built from source with CUDA, in WSL or Linux (below); its Python packages in [environments/bliss-wsl.txt](environments/bliss-wsl.txt) |

The records say which ran: each carries the commit, whether the tree had
changes, the Python and library versions (`yoke.write` with `stamp`);
BLISS's records add its checkout, a hash of its local changes, the CUDA
runtime, the GPU and driver, and the response file's hash
(`tools/bliss_curves.py`, `provenance`).

The published records were made on one Windows 11 PC (Ryzen 9 3950X,
40 GB, GTX 1080) with Python 3.12.10; BLISS in WSL's Ubuntu 24.04.

### turboSETI

turboSETI 2.3.2 does not run on numpy 2, so it has its own environment. The default places, used when `SSY_TURBOSETI_PYTHON` is
not set:

- Windows: `%LOCALAPPDATA%\signalsearchyoke\seti-venv\Scripts\python.exe`
- Linux: `~/.local/share/signalsearchyoke/seti-venv/bin/python`

```
py -3 -m venv $env:LOCALAPPDATA\signalsearchyoke\seti-venv
& "$env:LOCALAPPDATA\signalsearchyoke\seti-venv\Scripts\python.exe" -m pip install turbo_seti setigen "setuptools<80" "numpy<2" "pandas<2.3" "scipy<1.14" "matplotlib<3.9" "contourpy<1.3" "h5py<3.12" "numba<0.61" "astropy<6.2" "hdf5plugin<5"
```

The pins (9 November 2026, Python 3.12): turboSETI 2.3.2 fails on numpy 2
(`%i` given an array); blimpy needs `pkg_resources`, missing from the
newest setuptools (79 has it), and an astropy that still runs on numpy 1.
With them turbo_seti 2.3.2 and blimpy 2.1.4 run. turboSETI writes its log
beside a path it joins wrongly on Windows, so `seti.py` runs it from the
file's own folder. Without the environment, every command that needs it
stops and says how to install it.

### BLISS

BLISS at commit 2b98afe960f13ee7e467aca499576d87ee7502f5, built from
source; [comparable.md](comparable.md), step 11, has why each choice was
made. What was done here (WSL, Ubuntu 24.04.5, GCC 13.3, CMake 3.28):

1. `sudo apt-get install -y cmake libhdf5-dev build-essential`
2. The CUDA 12.6 toolkit, user-level from conda-forge (the GTX 1080 is
   Pascal, which CUDA 13 dropped):
   `micromamba create -p ~/ssy/cuda126 -c conda-forge cuda-version=12.6 cuda-nvcc cuda-cudart-dev cuda-cccl`
3. BLISS cloned to `~/ssy/bliss` at that commit, with
   `tools/bliss/event_search_off_hits_once.patch` applied (`git apply`).
4. Configured in `~/ssy/bliss/build-cuda` as a Release build with
   `WITH_CUDA=ON`, the toolkit's `nvcc` as the CUDA compiler, and built;
   the Python module lands in `build-cuda/bliss/python` (`pybliss`).
5. A Python venv at `~/ssy/blissenv` with numpy and h5py
   ([environments/bliss-wsl.txt](environments/bliss-wsl.txt)).
6. The Green Bank channel response made with BLISS's own tool, the recipe
   it prints for GBT (`bliss_generate_channelizer_response -f 1048576 -N 12
   -M 256`), saved as `~/ssy/gbt_response.f32`; its hash is in every BLISS
   record.

Where it runs are settings, not part of the comparison: `SSY_BLISS_DISTRO`
(default `Ubuntu`), `SSY_BLISS_PYTHON` and `SSY_BLISS_LD_PATH` (default
under `~/ssy` in that distribution), and for the adapter
`BLISS_PYTHON_DIR`, `BLISS_RESPONSE`, `BLISS_DEVICE` (default `cuda:0`).
Without WSL, the distribution or BLISS's Python, `matched.py bliss` stops
and says which is missing.

## The evidence package

`python tools/evidence.py build` writes one zip of everything the published
numbers are made from, with a manifest (each file's SHA-256 and size, the
commit):

- the summary records: `data/measurements/` (for example `matched.json`,
  step 4; `matched-bliss.json`, step 11; `step10.json`, the verdict;
  `curved-pass.json`, `curved-orbits.json`), `data/step10/` (the choice and
  the logged deviations), `data/results/`;
- the per-block records they are built from: `data/matched/`
  (each block's planted signals, every pipeline's outcome on each, the
  wrong-choice candidates), `data/curved_pass/`, `data/analysis/`;
- a consistent copy of the hit store `data/ssy.sqlite` (every hit, event,
  check and run; the table commands read the chosen blocks from it).

Left out: the raw spectra (about 15 GB a look; they stay in the archive,
and the records name each file's URL), chunk indexes, caches, unfinished
work, locks and logs. About 1.3 GB before compression. It is deposited on
Zenodo with each version of the report (docs/publishing.md).

The package's copies have the names of the machine that made them taken
out, and nothing else changed: every home folder is written `~` (BLISS's
records name its module and response file under one, in their provenance)
and every computer name the store's runs give is written `COMPUTER`, in
the records and in the store's copy, where the old values are wiped from
the file, not just unlinked. The build is refused if anything packaged
still names the machine. The records on the machine itself are not
changed. The manifest gives each file's SHA-256 and size as packaged, and
its original SHA-256 where the substitution changed it; the store's
SHA-256 (packaged and original), size and tables (every column, every row
count); and what was substituted, by count. Nothing else in the store is
about the machine: the rest is the archive's file URLs, the blocks, hits,
events, checks, planted signals and the search's parameters and library
versions.

- `python tools/evidence.py check ZIP` refuses a copy with a record missing
  or changed, an entry the manifest does not list, or a store that is
  missing or differs.
- `python tools/evidence.py reproduce ZIP` is the level-2 test from the
  package alone: the code of the commit the package was built at (`git
  archive`; a package built from a tree with changes is refused, as no
  commit holds its code) in a new folder, the package unpacked as its data
  folder, so this checkout's `data/` is out of reach. It runs the table
  commands below there and compares every page and summary record they
  write with what was there before (that commit's pages, the packaged
  records). It fails on an output missing, new, or changed in anything but
  a record's top-level `provenance` and `written_utc`, a page's UTC times,
  and the commits the report names beside its records' times.

Each record's provenance says whether any tracked file (code, config,
patch or environment list) differed from its commit, and keeps a SHA-256
of the difference when one did (`uncommitted_diff_sha256`, from 19
November 2026; earlier records looked at the Python files only).

## Making the tables again (level 2)

Unpack the package and point `SSY_DATA` at its `data/` folder; then, with
the core environment only:

| Published | Command | Writes |
|---|---|---|
| Step 4, the matched comparison | `python matched.py tables KIC8462852` | `data/measurements/matched.json`, `docs/results/KIC8462852-AGBT17A_999_68-matched.md` |
| Step 11, BLISS | `python matched_tables.py bliss KIC8462852` | `data/measurements/matched-bliss.json`, `docs/results/KIC8462852-AGBT17A_999_68-bliss.md` |
| Step 9, the curved pass | `python curved_pass.py tables KIC8462852` (and `orbit-tables`, `vet-tables`, `turboseti-tables`) | `data/measurements/curved-*.json` |
| The report | `python tools/report.py` | `docs/report/report.md` |

The pages are written into the checkout's `docs/`, so `git diff` shows at
once whether they came out the same; `tools/evidence.py reproduce` runs all
of these in a separate copy and does the comparison.

## Running it again (level 3)

These read the archive and take hours. Each resumes where it stopped, and
records a block only when it is whole.

| Step | Commands | Time here |
|---|---|---|
| The sweep of a cadence | `python seti.py sweep KIC8462852` then `python check.py` | about 5 hours, 308 blocks (2017 session) |
| Step 3, the other pipelines | `python pipelines.py run KIC8462852`, `compare` | about 2 hours |
| Steps 4 and 7 | `python matched.py run KIC8462852`, `tracks`, `tables` | 121 blocks |
| Step 9 | `python curved_pass.py run KIC8462852`, `recheck`, `orbits`, `vet`, `turboseti`, then the tables | 121 blocks; the checks alone 62 hours of worker time |
| Step 10 | `python independent.py check`, `sweep`, `choose`, `measure`, `curved`, `verdict` | 121 blocks, 3 workers a stage |
| Step 11 | `python matched.py bliss KIC8462852`, `bliss-judge`, `bliss-control`, then `matched_tables.py bliss` | about 20 minutes a block on a GTX 1080 |

Step 10 refuses to run if the code it rests on has changed since
`config/step10.json` was frozen (its fingerprint), unless a stage is given
`--deviation "why"`, which is logged in `data/step10/deviations.json` and
printed in the verdict. Its verdict, a failure of both false-rate
criteria, is the published result and is not re-run to a different end.

BLISS's GPU hits come in a different order on each run and its event
stage pairs greedily, so its events vary a little run to run; the adapter
feeds them in a fixed order, and the tables also give three seeded
shuffles (comparable.md, step 11).
