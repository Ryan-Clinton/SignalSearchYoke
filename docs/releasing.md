# Releasing

What is checked before the repository is made public, and before each
evidence package is deposited beside a version of the report
(docs/publishing.md). The two are separate: the code can be public while
the package is still being prepared. Each check is a command; the state
below is the last time it was run.

## Before the repository is public

Made public on 19 November 2026, after the checks below.

| Check | How | State, 19 November 2026 |
|---|---|---|
| A licence for the project's own code | `LICENSE` at the root, named in `pyproject.toml` and `CITATION.cff` | MIT, 19 November 2026. The two BLISS-derived files stay under BLISS's BSD 3-Clause licence (THIRD_PARTY_NOTICES.md) |
| Nothing secret anywhere in the history | `python tools/history_scan.py`: every version of every file on every ref, values masked | 3 refs, 113 commits, 471 file versions at 135 paths. **No key, token, password or private key.** One address-shaped match, a version number (`pyerfa==2.0.1.5`). Home folders: the user name in an earlier `matched.py` (the BLISS paths, settings since), a placeholder in an earlier `docs/publishing.md` and in the scanner's own description. No key or credential file names, no file over 5 MB |
| The same, by a second scanner | `python tools/history_scan.py --export DIR`, then `detect-secrets scan --all-files DIR` (detect-secrets 1.5.0) | every finding a hex string that is a hash or a commit: step 10's fingerprints (config/step10.json), the Voyager file's and pickles' SHA-256, the BLISS and pickles commits. Gitleaks was not run: its download was not available here |
| What the history says about the author | the scan's commit identities; old versions of the docs | three identities: the author's name with a personal e-mail address (the commits up to 19 November 2026), and two GitHub noreply addresses; this repository commits under the noreply address from then on. Kept: the author judged the exposure small against breaking the commit IDs the docs and records cite. Old versions of HANDOVER.md, docs/multiuser.md and docs/publishing.md describe the author's work server and the site's posting in general terms (no address or credential); the current ones do not. Rewriting history would change every commit ID the docs and records cite (step 10's deviation log among them); **the author's decision** |
| The offline tests pass | GitHub Actions, `tests` (read-only token) | Linux on Python 3.11, 3.12 and 3.13, Windows and macOS on 3.12 |
| A newcomer's first steps work | `python tests/integration_quickstart.py`, or the `quick start` workflow by hand (Linux and Windows): `find`, then the README's 3 MHz search, against the hits it gave | 19 November: 10 hits, 271 shadow hits, the strongest at 2250.146695 MHz, 100 MB read. 18 November: the quick start on a copy with no `data/` and a new environment |
| Private vulnerability reporting, which SECURITY.md points to | Settings, Code security | switched on 19 November 2026, when the repository was made public |
| A version to point at | a tag, `v0.1.0`, and a CHANGELOG from it | after the switch |
| Pushes to `main` | a ruleset requiring the `tests` checks, with the owner able to bypass | the author's choice after the switch: the project is worked on by pushing to `main` directly, which a rule without a bypass would stop |

## Before an evidence package is deposited

| Check | How | State, 19 November 2026 |
|---|---|---|
| Built from committed code | `python tools/evidence.py build`; `reproduce` refuses a package built from a changed tree | package at c35afe3 (report 1.3, steps 10 and 12), from a clean tree; the one before, 3fd7837, predated step 12 |
| The zip is what the manifest says | `python tools/evidence.py check ZIP` (refuses a missing, changed or unlisted entry, or a store that is missing or differs; tested on broken packages in `tests/test_evidence.py`) | 3,181 records and the store, 238 MB zipped; all match |
| The tables come out the same from the zip alone | `python tools/evidence.py reproduce ZIP`: the code of the package's own commit in a new folder, the zip as its data; fails on any output missing, new, or changed in anything but its stamps | 8 table commands ran (the operating points added); 70 pages and records the same, none different, missing or new, from the package with the machine's names taken out. An earlier run (23643ae) caught `matched.json` written before the code added its `record` field; it was written again from the records |
| Nothing in it names the machine | `build` writes every home folder as `~` and every computer name as `COMPUTER` in the packaged copies, and refuses if anything still names the machine; the manifest's `machine_names_substituted` | 1,100 home folders and 1 computer name in 309 records, 13 runs in the store (a Windows drive as WSL mounts it, /mnt/c, now written `~` too: step 12's failed BLISS records quote paths there); every one of the 3,183 entries of the final zip read again for the user name, the computer name, the author's e-mail, /mnt/c and any home folder: none |
| Someone else makes the tables again | a second person, from the tagged release and the deposited package, by docs/reproducing-results.md level 2 | **not yet**: before the DOI is announced |

The package goes out as the records are but for that one substitution,
which is mechanical, counted in the manifest, and leaves each record's
original hash beside it; no value is otherwise edited to make a record
publishable. If anything else in a record should not be public, the code
that writes it changes and the record is written again.
