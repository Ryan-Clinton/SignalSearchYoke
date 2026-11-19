# Contributing

Issues and pull requests are welcome. This is one person's research
project, so replies may be slow.

## Before a pull request

```
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m unittest discover -s tests -v
```

The tests are offline and take about ten seconds; GitHub runs the same on
every push and pull request (Linux on Python 3.11 and 3.12, Windows on
3.12). They need no archive access, no turboSETI or BLISS, and nothing in
`data/`.

## Two tiers of checks

| Tier | What | When |
|---|---|---|
| Fast | the offline tests: the search on synthetic looks, the cadence test, records and the store, step 10's freeze, the BLISS port, imports; and `tests/reference_hits.json`, every hit the search gives on one seeded synthetic look with three planted signals | every push and pull request |
| Scientific | the measurements on real blocks: planted signals through every pipeline, false candidates under the 19 wrong choices, the matched comparison (docs/reproducing-results.md, level 3); and the tables made again from the evidence package (`tools/evidence.py reproduce`, level 2) | before a change to the search, the cadence test, the checks or the planting is released, and before each version of the report |

The reference hits only say that the search's output moved; the measured
records are the standard. A change meant to move them raises the search's
version and writes the reference again (`python tests/test_reference.py
--write`) in the same commit.

## What a change must not move without saying so

The published results rest on the search, the cadence test, the checks,
the planting and the thresholds. A change to any of them changes what was
measured, so it comes with:

- a new search or checks version (`SEARCH_VERSION` in `seti.py`, `VERSION` in
  `vetting.py`), so older
  results are marked superseded and searched again rather than mixed in;
- the measurement it affects run again, and the result pages regenerated
  from the records, not edited by hand;
- a note in docs/seti.md or docs/comparable.md of what changed and what it
  moved.

Step 10's verdict (config/step10.json) is final; it is not re-run to a
different end.

Tidying, error messages, documentation and new tests need none of this.

## The long checks

The experiments in docs/reproducing-results.md (sweeps, matched runs,
BLISS) take hours and read gigabytes from Breakthrough Listen's archive.
They are not part of a pull request's checks. Keep requests to the archive
modest: `reading.py` holds at most 8 at a time.
