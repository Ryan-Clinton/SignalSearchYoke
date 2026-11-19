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

The reports appear at `https://ryanclinton.uk/astrophotography/signalsearch/`,
one page each at `/astrophotography/signalsearch/SLUG/`, with a list of
them at the section's front page (set up 19 November 2026; not a subdomain).

Each page carries the report's text and figures, the PDF of each version
(the same files as on Zenodo), its revisions, the commit it was built from,
a "how to cite" line (the DOI when there is one, else the page's address)
and Google Scholar's `citation_*` tags. The site checks every report before
it goes up: figures that run or load nothing, PDFs with no active content,
and no local paths in the text or metadata. How a report is posted to the
site is kept with the site, not here.
