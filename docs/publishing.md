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

  Every number is read from the project's result records and checked
  against them. The records are not in git (data/ is ignored):
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

## The request to ryanclinton.uk

One page at /astrophotography/signalsearch/, through the site's existing
setup, holding:

- the report, with its version number and date;
- a "how to cite" line with the DOI;
- the PDF to download, the same file as on Zenodo;
- the list of revisions;
- citation meta tags in the page head (citation_title, citation_author,
  citation_publication_date, citation_doi, citation_pdf_url), which Google
  Scholar reads.

How that fits the site is the site's decision. SignalSearchYoke supplies
the Markdown, the PDF, the figures and the citation details in whatever
format the site's inbox takes, and needs to know that format.
