# Publishing the findings

Ryan's first publication: one report, citable, with a readable home on his
site. When a second comes along, this gets revisited then.

## The pieces

- **The report.** "Comparing radio-signal searches on Breakthrough Listen
  data". It has a plain summary at the top, then:
  - the question and the method;
  - the results, with their tables, intervals and figures;
  - what they suggest;
  - the limitations, including the 2016 session's failed false-candidate
    limit, stated plainly;
  - data and code availability;
  - references and revisions.

  Every number is read from the project's result records, and so is the
  experiment's definition (signals a block, the strength grid, the drift
  bins, the tolerances, the wrong choices, the pipelines' versions):
  `tools/report.py` refuses to write the report if the per-block records,
  the summary records and the environment as run disagree. The records are not in git (data/ is ignored):
  `tools/evidence.py build` packs the summary records (data/measurements,
  step 10's choice and deviations), the per-block records (data/matched,
  data/curved_pass) and a copy of the hit store, with a manifest of
  hashes, about 240 MB zipped; it is deposited on Zenodo with each version,
  so anyone can check a number against its source or make the tables again
  (docs/reproducing-results.md).
  The report is written as Markdown and a PDF. Each version has a number and
  a date, and a revision note says what changed.
- **Zenodo holds each version.** The PDF of each version is deposited on
  Zenodo, which gives it a permanent DOI (and a concept DOI for all
  versions). This is what people cite.
- **The code.** Once the repository is public: a tagged release archived on
  Zenodo with its own DOI, and a CITATION.cff in the repository. The report
  cites both.
- **The data.** Credited as papers using it do:
  - a data availability statement pointing to the Breakthrough Listen Open
    Data Archive;
  - a citation of its data release paper (Lebofsky et al. 2019, PASP 131,
    124505);
  - a code availability statement for the tools used (turboSETI, BLISS,
    blimpy).

  No use of their logo or name as an endorsement.
- **Ryan's accounts.** Zenodo and ORCID are in Ryan's name. Each version goes
  to Zenodo only on his go, because a DOI is permanent.

## On ryanclinton.uk

Set up 19 November 2026, at the address Ryan chose: the reports go at
`https://ryanclinton.uk/astrophotography/signalsearch/`, one page each at
`/astrophotography/signalsearch/SLUG/`, with a list of them at the
section's front page. Not a subdomain: none was approved.

SignalSearchYoke posts a report the way telescopeyoke posts a diary entry:
a folder, `findings/SLUG/`, sent into the web server's inbox, where the
server checks it, builds the site, runs its privacy scan and publishes,
or sets the post aside and leaves the live site as it was. The inbox and
its key are SignalSearchYoke's own (`ryanclinton-signalsearch`, in WSL on
the Windows PC); they take reports and nothing else.

- `findings/SLUG/report.md`: a `+++` TOML header (title, summary,
  version, date, commit, and optionally the DOI and the PDF's name, then
  every version in `[[revisions]]`), then the report's Markdown, starting
  at `##` (the site sets the title) and with no raw HTML.
- Its figures beside it (`.svg`, `.png`, `.jpg`, `.webp`), written as
  `![what it shows](NAME.svg)`. An SVG may carry nothing that runs or
  loads: no script, links, `<use>`, `<image>` or outside `url()`.
- Its PDFs beside it, one name per version (`report-v1.0.pdf`), the same
  files as on Zenodo, with no JavaScript, actions, forms, attachments or
  encryption. Their text and metadata go through the privacy scan, so no
  home paths (`C:\Users\...`).

The site adds the "how to cite" line (the DOI when there is one, else the
page's address), the PDF to download, the revisions, "built from commit
...", and Google Scholar's `citation_*` tags. The full format, the checks
and the command to post are in ryanclinton.uk's
[docs/posting-signalsearch.md](https://github.com/Ryan-Clinton/ryanclinton.uk/blob/main/docs/posting-signalsearch.md)
(private; on this PC at
`\\wsl.localhost\Ubuntu\home\facepipe\ryanclinton.uk\docs\posting-signalsearch.md`).
