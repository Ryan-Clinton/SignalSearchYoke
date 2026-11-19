# Releasing

What is checked before the repository is made public, and before each
evidence package is deposited beside a version of the report
(docs/publishing.md). Each check is a command; the state below is the last
time it was run.

## Before the repository is public

| Check | How | State, 19 November 2026 |
|---|---|---|
| A licence for the project's own code | `LICENSE` at the root, named in `pyproject.toml` and `CITATION.cff` | **not chosen yet**. BLISS's licence for the two files derived from it is in THIRD_PARTY_NOTICES.md and stands whatever is chosen |
| Nothing secret anywhere in the history | `python tools/history_scan.py`: every version of every file on every ref, values masked | 3 refs, 103 commits, 439 file versions at 128 paths. **No key, token, password or private key.** One address-shaped match, a version number (`pyerfa==2.0.1.5`). One home folder, `/home/` and the user name in an earlier `matched.py` (the BLISS paths, settings since). No key or credential file names, no file over 5 MB |
| What the history says about the author | the same scan's commit identities; old versions of the docs | two identities: the author's name with a personal e-mail address (most commits), and a GitHub noreply address. Old versions of HANDOVER.md and docs/multiuser.md describe the author's work server in general terms (no address or credential); the current ones do not. Rewriting history would change every commit ID the docs and records cite (step 10's deviation log among them); **the author's decision** |
| The offline tests pass | GitHub Actions, `tests` workflow | Linux on Python 3.11 and 3.12, Windows on 3.12 |
| A newcomer's first steps work | README's quick start on a copy of the code with no `data/` and a new environment | 18 November: install, `--help`, `find`, a 3 MHz search (37 s), the tests |
| Private vulnerability reporting, which SECURITY.md points to | Settings, Code security | GitHub offers it only on public repositories: switched on right after the switch |
| A version to point at | a tag, `v0.1.0`, and a CHANGELOG from it | after the switch |

## Before an evidence package is deposited

| Check | How | State, 19 November 2026 |
|---|---|---|
| Built from committed code | `python tools/evidence.py build`; the manifest's `uncommitted_changes` is false | the deposited package is built at the release commit |
| The zip is what the manifest says | `python tools/evidence.py check ZIP` (refuses a missing, changed or unlisted entry, or a store that is missing or differs) | package at fe775a3: 1,482 records and the store, 242 MB zipped; all match |
| The tables come out the same from the zip alone | `python tools/evidence.py reproduce ZIP`: committed code in a new folder, the zip as its data | package at fe775a3: 7 table commands ran, 65 pages and records the same apart from when and by which commit; one record (`curved-pass-vetting.json`) had fields the code added after it was written, every value the same (written again since) |
| What in it names the machine | the manifest's `records_naming_local_paths` and `store` | 244 BLISS records name its module and response file under the home folder in WSL (the same user name as the commits); the store's runs name the computer (one name); no local path in the store's text. Everything else is the archive's file URLs and the measurements |

The package goes out byte for byte, so a record is never edited to make it
publishable; if something in it should not be public, the code that writes
it changes and the record is written again.
