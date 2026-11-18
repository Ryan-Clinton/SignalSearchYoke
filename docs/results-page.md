# The results page: spec

18 November 2026. This is a public page reporting where the comparison stands after step 11 of
[comparable.md](comparable.md). It is an interim research update, labelled as one. It is not an
announcement that this search is better. Nothing is put on the server until the owner says so.

## Where it lives

- **Address:** a subdomain of ryanclinton.uk, proposed as `seti.ryanclinton.uk`. The name is the
  owner's choice. The other ryanclinton.uk subdomains are served by nginx on brokerblitzer.
- **What is served:** static files only (one HTML page, its stylesheet and the figures), with no
  service, database or upload. On the server that means one directory and one nginx server block
  with a certificate, beside the live sites and without touching them. The owner sets up the server
  or gives the go for it. Until then brokerblitzer stays read-only for this project.
- **Updates:**
  - Each version goes into its own directory, named by its commit.
  - It is checked there, then made live by switching one symlink that nginx serves.
  - A half-copied version is never visible, and going back is switching the link back.
  - Each version's footer gives the commit it was built from.

## How it is built

- `site.py build` writes the page into `site/` from the committed records:
  - data/measurements/matched.json (step 4);
  - matched-bliss.json (step 11);
  - the step 10 verdict and its deviations file;
  - the curved-pass records.

  No number on the page is typed by hand. Each one is read from a record, and each sentence that
  carries a number is a template filled from it.
- **It refuses to build** in any of these cases:
  - the working tree has changes to the records or to `site.py`;
  - a record is older than the code that made it, by its config identity;
  - a record is incomplete in the way the tables already refuse (the BLISS records by
    `matched.judge_whole` and `bliss_done`; step 10 by its own fail-closed verdict).
- **Each figure links** to the results page it comes from on GitHub, at the commit the page was
  built from (docs/results/*.md), and from there to the code.
- `site.py check` re-reads the built page and confirms that every number on it matches the records
  it names. The build runs the check, so a page cannot leave the build with a number its records do
  not give.
- **Each comparison has its own template, and the build checks what the comparison needs:**
  - **A paired comparison** (both, either alone, neither, the bootstrap) is built only when both
    pipelines' records cover the same blocks, the same planted signals (frequency, drift and S_in
    per block) and the same scoring standard. Otherwise the build refuses.
  - **A comparison at the matched rule** says what it is: "both met the 0.1-a-block target at
    the tested cut, with different measured false rates", followed by both rates and their
    intervals. Equal cuts are never written up as equal rates.
  - **Inference:** each bootstrap interval is said to hold for this session, these cuts and this
    signal grid, not for sensitivity in general.
- **What the checks cannot do:** they keep the numbers, provenance and pairing honest, but not
  whether a comparison means what the sentence says. That is the owner's read before it goes up
  (Done when).

## What it says, in order

Every finding carries one of three labels. The page keeps them apart and never merges them in a
summary. A label is given only with its evidence, a commit, and `site.py` reads the label from a
table in the script, not from the prose:

- **fixed beforehand:** frozen before the data was read, with a fingerprint checked when it ran.
  Only step 10 has this: config/step10.json, its fingerprint and its logged deviation.
- **method set beforehand:** the method and the comparison were committed before the run whose
  records the page reads, and the evidence is the method's commit dated before those records.
  Step 11's BLISS run at step 4's matched rule qualifies: the rule and the signal grid were
  committed before BLISS was run. Step 4's own cuts do not: they were chosen on the blocks they
  were judged on (comparable.md step 10).
- **exploratory:** designed or chosen after seeing a result. This covers step 4's matched cuts,
  BLISS's hits through this search's test, the same-hit control, the curved second pass, the
  satellite-band breakdown of step 10's false candidates and the full checks on its blocks. A
  measurement whose order cannot be shown from the commits is exploratory.

1. **What this is.** An experimental search for narrowband radio signals, tested against
   turboSETI and BLISS on recorded Breakthrough Listen observations from Green Bank, with
   synthetic signals planted in them. It is one person's project, run on one PC.
2. **How it is measured, in a paragraph.**
   - The archive's spectra are used as they are.
   - Each block gets 110 signals planted in it, across a grid of strength and drift (13,310 in all
     over 121 blocks).
   - A signal counts as found only when it is detected in all three ON looks, within ±6 Hz and
     ±0.05 Hz/s.
   - False candidates are counted on the 19 wrong ON/OFF choices.
   - Pipelines are compared at the cut where each gives at most 0.1 false candidates a block.
3. **The first session** (KIC8462852, AGBT17A_999_68, 2017; exploratory for this search's and
   turboSETI's cuts, method set beforehand for BLISS as published). One table: each pipeline's
   cut, its false rate with its interval, and the signals it recovers.
   - This search: cut 30, 0.068 a block, 4,520 recovered.
   - turboSETI: cut 30, 0.049 a block, 442 recovered.
   - BLISS as published: never reaches 0.1 a block in the cuts tested.
   - BLISS's hits through this search's cadence test: cut 30, 0.052 a block, 4,048 recovered.

   The paired difference against that last row goes under the table: +0.036 of the 13,310 by a
   block bootstrap (0.026 to 0.046); 691 recovered by this search alone, 219 by BLISS's hits alone.
   The text says that both met the 0.1-a-block target at the tested cut, with different measured
   false rates (0.068 and 0.052). The interval holds for this session, cut and signal grid.
4. **The second session** (HIP17147, AGBT16A_999_192, 2016, L band; fixed beforehand). This section
   gets the same weight on the page as section 3, and comes straight after it.
   - **Recovery held:** 4,337 against turboSETI's 417.
   - **Both false rates failed** the frozen limit of 0.1 a block at SNR 30: this search 39.1,
     turboSETI 1.27.
   - The step's verdict is quoted as generated, with its logged deviation.
   - The satellite-band breakdown follows, labelled after the fact.
5. **BLISS** (exploratory, apart from BLISS as published in section 3). Why BLISS as published has no matched cut:
   - It groups hits differently as the cut changes.
   - Its event stage keeps making false candidates from interference hits that this search's test
     rejects.
   - Through this search's test, its hits do reach the target.

   This section states only what the same-hit-list control (step 11) supports. If the control
   leaves the cause open between the hit grouping and the event stage, the page says so.

   It also says that the BLISS row with this search's test is a combination of the two pipelines,
   not BLISS as published.
6. **Curved tracks** (exploratory on step 4's blocks; its run on step 10's session was fixed beforehand: its recovery held, 2,769 against production's 389 of 7,260 with none of production's lost, and its false rate failed with production's). The curved second pass is kept apart from the
   search. Give its recovery at |a| ≥ 10⁻⁴ Hz/s² against production's at the same cut, and state
   that no change to `onoff.py` is made on it.
7. **What this does not show.**
   - Two sessions, both from one telescope and one recording pipeline.
   - No Parkes, MeerKAT or other receiver.
   - Steady drifts within ±4 Hz/s (plus the curved-track experiment).
   - No claim of better sensitivity in general, or for any other telescope, band or signal type.
   - Step 12, a third session, comes before any broad claim.
8. **Open questions.** These are named, not answered:
   - the 219 signals BLISS's hits recover and this search does not, and among the 135 BLISS finds
     on its own, the 28 with no candidate from this search at all;
   - the false candidates in step 10's satellite bands.
9. **Sources.**
   - The repository and the commit the page was built from.
   - The results pages and comparable.md.
   - The Breakthrough Listen open data archive, credited as the source of the data. The archive's
     terms of use are to be read before the page goes up, and the credit worded to them.

## What it never does

- Says or implies that this search beats BLISS or turboSETI in general. Every comparison names its
  session, its cut and its signal grid.
- Puts step 10's failure below the fold, in a footnote or in softer words than "failed".
- Uses Breakthrough Listen's, Berkeley SETI's or a telescope's logo or name as an endorsement.
- Shows a number that was chosen after seeing it without the "after the fact" label.

## Done when

- `site.py build` and `site.py check` pass on a clean tree.
- The page reads correctly at phone width and on a desktop.
- The owner has read it, and has put it up on the subdomain or given the go to do so.
