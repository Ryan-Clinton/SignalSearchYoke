# SignalSearchYoke

A search for narrowband radio signals in Breakthrough Listen's open data,
with the ON-OFF cadence test that tells our own interference from a signal
coming from the target, and a measured comparison against two published
pipelines, turboSETI and BLISS.

It is experimental scientific software with measured, documented results
and stated limits. It uses no telescope of its own: it reads Breakthrough
Listen's published recordings over the web.

## What has been found

The report, [Comparing radio-signal searches on Breakthrough Listen
data](docs/report/report.md) (version 0.1, draft), has the method, tables
and limits. In short:

- **2017 session (KIC 8462852, AGBT17A_999_68), 121 blocks, 13,310 planted
  signals.** At the cut where each pipeline's measured false-candidate
  rate is at most 0.1 a block, this search found 4,520 in all three ON
  looks, turboSETI 442. BLISS as published reached that rate at no cut
  tested; BLISS's own hits put through this search's ON/OFF test found
  4,048. The rates are point estimates whose 95% intervals reach above 0.1,
  and these cuts were chosen on the same blocks they were judged on.
- **2016 session (HIP 17147, AGBT16A_999_192, L band), every choice fixed in
  advance** ([config/step10.json](config/step10.json), with a fingerprint
  of the code; one change after the freeze, a fix to how a stage read the
  store, is logged at each stage it touched). Recovery held (4,337 against turboSETI's 417), but **both
  pipelines failed the false-candidate limit set beforehand**: this search
  39.1 a block, turboSETI 1.27, against 0.1. Nearly all of this search's
  lie in blocks touching known satellite bands. No band has been masked
  afterwards, because that would be choosing the rule after seeing the
  result. [The verdict](docs/results/HIP17147-AGBT16A_999_192-step10.md).
- **No signal from another world.** The 2017 sweep's 11 candidates were
  all marked interference or likely interference by the checks
  ([docs/leads/](docs/leads/)); "unexplained" there would mean the end of
  the automatic checks, not a discovery.

Two sessions from one telescope do not show better sensitivity in general.

## What it does, and how far each part has got

| Part | Status |
|---|---|
| Reading the archive: only the blocks of a slice, by HTTP range requests (`reading.py`) | in use |
| The search: desmeared drift sums to ±4 Hz/s, hits at SNR 10, shadow hits from 5 (`searching.py`) | in use, search version 4; measured on planted and real signals ([docs/seti.md](docs/seti.md)) |
| The ON-OFF cadence test (`onoff.py`) | in use; its false rate failed the 2016 test above |
| The ten checks on a candidate, after blc1 (`check.py`, `vetting.py`) | in use, checks version 4 |
| Planted signals through everything (`injection.py`, `measure.py`) | in use |
| Comparison with turboSETI, pickles and BLISS at matched false rates (`pipelines.py`, `matched.py`) | done: turboSETI on both sessions, pickles and BLISS on the 2017 session |
| A second pass for curved tracks (`curved.py`, `curved_pass.py`) | **experimental**, apart from the search |
| A third session before any broad claim (step 12 of [docs/comparable.md](docs/comparable.md)) | proposed, not run |
| Parallel runs ([docs/parallel.md](docs/parallel.md)), many people's computers ([docs/multiuser.md](docs/multiuser.md)) | plans, not built |

It does not search for pulsed or broadband signals, drifts beyond ±4 Hz/s,
or data from other telescopes.

## Quick start

Python 3.11 or later. The core needs only numpy, requests, h5py and
hdf5plugin; turboSETI, BLISS and CUDA are needed only to repeat the
comparisons. The offline tests run on every push on Linux (Python 3.11,
3.12, 3.13), Windows (3.12) and macOS (3.12); the published results were
made on Windows with Python 3.12 (docs/reproducing-results.md).

Linux or macOS:

```
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python seti.py --help
.venv/bin/python seti.py find KIC8462852
```

Windows (PowerShell, Python from python.org):

```
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python seti.py --help
.venv\Scripts\python seti.py find KIC8462852
```

Below, `python` is the environment's: activate it first
(`source .venv/bin/activate`, or `.venv\Scripts\Activate.ps1` in
PowerShell), or write its path as above.

`find` lists the target's looks by session, from the archive's listing
(`--json` gives each look's URL). One small search, on 3 MHz of the 2017
session's first ON look (it reads only that slice, about 100 MB; under a
minute here, 10 hits, the strongest at 2250.146695 MHz;
`tests/integration_quickstart.py` checks exactly this):

```
python seti.py search https://bldata.berkeley.edu/pipeline/AGBT17A_999_68/holding/spliced_blc2021222324252627_guppi_57898_22410_DIAG_KIC8462852_0031.gpuspec.0000.h5 --from 2250 --to 2253
```

`sweep KIC8462852
--blocks 3` searches the first three blocks of the target's whole cadence
and runs the cadence test on them. What it keeps goes into `data/`
(created on first use; `SSY_DATA` moves it): every hit of a sweep in
`data/ssy.sqlite` (`store.py` has the tables), a readable record in
`data/sweeps/`, each file's chunk index in `data/index/`. Every command
takes `--json`.

The tests, offline and in about ten seconds:

```
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

## Where to read more

| Document | What it is |
|---|---|
| [docs/report/report.md](docs/report/report.md) | the report: question, method, results, limits |
| [docs/reproducing-results.md](docs/reproducing-results.md) | the environments, the evidence package and the commands behind each published number |
| [docs/seti.md](docs/seti.md) | how the search works, and everything measured on it |
| [docs/comparable.md](docs/comparable.md) | the plan for standing beside the published searches, steps 1 to 12, with what each found |
| [docs/results/](docs/results/) | the result pages, written by the code from the records |
| [docs/research/](docs/research/) | research notes behind the plan, some written with AI assistants; a claim is taken from the cited paper, not the note |
| [CONTRIBUTING.md](CONTRIBUTING.md) | tests, and what a change must not move |
| [docs/releasing.md](docs/releasing.md) | what is checked before a release and before the evidence is deposited |
| [HANDOVER.md](HANDOVER.md) | historical: the project's state on 9 November 2026 |

## Data and credit

The data are Breakthrough Listen's, read from their archive at
`bldata.berkeley.edu` a few requests at a time (6 by default, never more
than 8): Lebofsky et al. 2019, "The Breakthrough Listen search for
intelligent life: public data, formats, reduction and archiving", PASP
131, 124505 (arXiv:1906.07391). Breakthrough Listen is managed by the
Breakthrough Initiatives; nothing here is endorsed by them.

turboSETI, BLISS, pickles, blimpy and setigen are their authors' and are
installed separately, not included. Two files are derived from BLISS's
source under its BSD 3-Clause licence:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

To cite this software: [CITATION.cff](CITATION.cff).
