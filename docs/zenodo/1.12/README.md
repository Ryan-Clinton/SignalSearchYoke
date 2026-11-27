# The Zenodo deposit of report 1.12

doi:10.5281/zenodo.24577702 (reserved; registered when the record is published).

Every file of the deposit is here except the evidence package,
`ssy-evidence-5a3de68.zip` (259,589,987 bytes), which is over GitHub's size
limit. Its SHA-256 is in `SHA256SUMS.txt`, and `ssy-evidence-5a3de68.manifest.json`
gives the SHA-256 and size of every record in it. The package can be made again
from this commit's data with `python tools/evidence.py build`, and checked and
reproduced as `REPRODUCING-RESULTS.md` says.

| File | What it is |
|---|---|
| `SignalSearchYoke-report-1.12.pdf` | The report |
| `ssy-evidence-5a3de68.zip` (in the deposit only) | The evidence package: every result record behind the report, built and reproduced at `5a3de68` |
| `ssy-evidence-5a3de68.manifest.json` | The package's manifest |
| `SignalSearchYoke-source-5a3de68.zip` | The source at `5a3de68` (`git archive`) |
| `REPRODUCING-RESULTS.md` | How to reproduce the results |
| `SHA256SUMS.txt` | The SHA-256 of each file above |
| `metadata.json` | The record's metadata as sent to Zenodo |
