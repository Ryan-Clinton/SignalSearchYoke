# Releasing

What is checked before the repository is made public, and before each
evidence package is deposited beside a version of the report
(docs/publishing.md). The two are separate: the code can be public while
the package is still being prepared. Each check is a command; the state
below is the last time it was run.

## Before the repository is public

| Check | How | State, 19 November 2026 |
|---|---|---|
| A licence for the project's own code | `LICENSE` at the root, named in `pyproject.toml` and `CITATION.cff` | **not chosen yet**. BLISS's licence for the two files derived from it is in THIRD_PARTY_NOTICES.md and stands whatever is chosen |
| Nothing secret anywhere in the history | `python tools/history_scan.py`: every version of every file on every ref, values masked | 3 refs, 113 commits, 471 file versions at 135 paths. **No key, token, password or private key.** One address-shaped match, a version number (`pyerfa==2.0.1.5`). Home folders: the user name in an earlier `matched.py` (the BLISS paths, settings since), a placeholder in an earlier `docs/publishing.md` and in the scanner's own description. No key or credential file names, no file over 5 MB |
| The same, by a second scanner | `python tools/history_scan.py --export DIR`, then `detect-secrets scan --all-files DIR` (detect-secrets 1.5.0) | every finding a hex string that is a hash or a commit: step 10's fingerprints (config/step10.json), the Voyager file's and pickles' SHA-256, the BLISS and pickles commits. Gitleaks was not run: its download was not available here |
| What the history says about the author | the scan's commit identities; old versions of the docs | three identities: the author's name with a personal e-mail address (most commits), and two GitHub noreply addresses. Old versions of HANDOVER.md, docs/multiuser.md and docs/publishing.md describe the author's work server and the site's posting in general terms (no address or credential); the current ones do not. Rewriting history would change every commit ID the docs and records cite (step 10's deviation log among them); **the author's decision** |
| The offline tests pass | GitHub Actions, `tests` (read-only token) | Linux on Python 3.11, 3.12 and 3.13, Windows and macOS on 3.12 |
| A newcomer's first steps work | `python tests/integration_quickstart.py`, or the `quick start` workflow by hand (Linux and Windows): `find`, then the README's 3 MHz search, against the hits it gave | 19 November: 10 hits, 271 shadow hits, the strongest at 2250.146695 MHz, 100 MB read. 18 November: the quick start on a copy with no `data/` and a new environment |
| Private vulnerability reporting, which SECURITY.md points to | Settings, Code security | GitHub offers it only on public repositories: switched on right after the switch |
| A version to point at | a tag, `v0.1.0`, and a CHANGELOG from it | after the switch |
| Pushes to `main` | a ruleset requiring the `tests` checks, with the owner able to bypass | the author's choice after the switch: the project is worked on by pushing to `main` directly, which a rule without a bypass would stop |

## Before an evidence package is deposited

| Check | How | State, 19 November 2026 |
|---|---|---|
| Built from committed code | `python tools/evidence.py build`; `reproduce` refuses a package built from a changed tree | package at 23643ae, from a clean tree |
| The zip is what the manifest says | `python tools/evidence.py check ZIP` (refuses a missing, changed or unlisted entry, or a store that is missing or differs; tested on broken packages in `tests/test_evidence.py`) | 1,483 records and the store, 242 MB zipped; all match |
| The tables come out the same from the zip alone | `python tools/evidence.py reproduce ZIP`: the code of the package's own commit in a new folder, the zip as its data; fails on any output missing, new, or changed in anything but its stamps | 7 table commands ran; 65 pages and records the same, none different, missing or new. The first run caught `matched.json` written before the code added its `record` field; it was written again from the records and the package rebuilt |
| What in it names the machine | the manifest's `records_naming_local_paths` and `store` | 244 BLISS records name its module and response file under the home folder in WSL (the same user name as the commits); the store's runs name the computer (one name); no local path in the store's text. **The author's decision** whether these go out as they are: changing them means changing what the code records and running BLISS's 121 blocks again |
| Someone else makes the tables again | a second person, from the tagged release and the deposited package, by docs/reproducing-results.md level 2 | **not yet**: before the DOI is announced |

The package goes out byte for byte, so a record is never edited to make it
publishable; if something in it should not be public, the code that writes
it changes and the record is written again.
