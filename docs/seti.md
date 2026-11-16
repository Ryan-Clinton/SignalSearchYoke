# Radio SETI in Breakthrough Listen's open data

`seti.py` searches Breakthrough Listen's published radio recordings for
narrowband signals, in the spirit of SETI@home: a slice of the band at a
time, with the test that tells our own interference from a signal coming
from the target.

## What the data are

Breakthrough Listen (seti.berkeley.edu/opendata) observes nearby stars with
the Green Bank Telescope, Parkes and others in cadences: three five-minute
looks at the target, each followed by a look at another star (ON, OFF, ON,
OFF, ON, OFF). The finest product of each look, `.gpuspec.0000.h5`, splits
the band into channels about 2.8 Hz wide, one spectrum every 18 seconds,
and is about 15 GB. The files are HDF5, stored in chunks of one spectrum
by one coarse channel (1,048,576 channels, about 3.1 MB packed) with
bitshuffle, so `seti.py` reads only the chunks of the slice asked for, over
the web with HTTP range requests (it needs h5py and hdf5plugin:
`requirements.txt`, or Ubuntu's `python3-h5py` and `python3-hdf5plugin`).

How it reads (`reading.py`, 8 November 2026):

- Once per file, the place of every chunk is read from the file's own
  HDF5 index (h5py's `chunk_iter`, through a 64 KB block cache: 87
  requests, 17 s) and kept in `data/index/`, checked against the file's
  ETag each run.
- A slice's chunks are then fetched by their byte ranges, all the looks'
  at once, and decoded in memory by the same bitshuffle filter: the values
  are bit-identical to h5py's (checked on all 16 × 1,048,575 values of
  block 153 of scan 31).
- Every request goes through a kept-alive session (0.165 s a request
  against 0.9 s with a fresh TLS handshake each), retried with back-off on
  429 and 5xx, with at most `--threads` requests in flight (6 by default,
  never more than 8). One look's block: 8.5 s, 50 MB, 16 requests, where
  the old 4 MB read buffer moved 147 MB in 35 requests in 91 s.
- Every range request carries the index's ETag (`If-Match`), so a file
  changed on the server mid-run is refused (412) and its index dropped,
  never read as a mix of two versions. The archive honours it (checked 9
  November 2026: 206 for the right ETag, 412 for a wrong one).

## The commands

    ./seti.py find KIC8462852
    ./seti.py search URL --from 2250 --to 2253
    ./seti.py cadence ON1 OFF1 ON2 OFF2 ON3 OFF3 --from 2250 --to 2253

- `find` lists the target's finest looks by observing session, with the
  OFF looks of the same session between them where the archive lists them,
  and gives the `cadence` line for a whole cadence.
- `search` sums each look's spectra along every drift line up to 4 Hz a
  second either way (a transmitter on a turning, orbiting planet drifts),
  summing in each spectrum every channel a fast line crosses, and keeps
  lines 10 times above the noise of the summed lines themselves. The
  band's smooth shape is taken out first and the noise measured robustly
  (median and median absolute deviation), so the band's edges and a few
  bright signals do not make hits. 10 is turboSETI's default number, but
  not the same threshold: for the same signals turboSETI's SNR is 0.227 of
  this search's (measured below), so its cut of 10 is about 44 here.
- `cadence` groups every ON look's hits into events and measures every
  look along each event's track. Seen in every ON look (a hit, or S/N 5
  along the track) and nowhere in the OFF looks (no S/N 6 along the track,
  no hit of any strength), it is a candidate; seen in an OFF look,
  interference; otherwise unconfirmed. "The cadence test" below.
- `check.py` runs ten checks on each candidate (`vetting.py`; "The checks"
  below) and writes a report with a picture of the six looks.

## What a candidate is

Nearly every hit is ours: satellites, radar, phones, the telescope's own
electronics. Interference comes in wherever the telescope points; a signal
from the target only while pointing at it, which is what the cadence
tests. A candidate is the start of the checking, not the end: it is
compared with known interference and with the published searches of the
same data (Breakthrough Listen's own papers list their candidates for
these targets). Every candidate examined so far has turned out to be ours.

## The sweep

`./seti.py sweep KIC8462852 --blocks N` searches the target's whole
cadence N blocks further than the runs before got, one block at a time:
each block is one chunk of the files (one coarse channel of 1,048,576
channels, 2.93 MHz), so a block is read in the fewest pieces. Tabby's
25 May 2017 cadence is 308 blocks, 1818 to 2721 MHz.

- **Every hit is kept** (8 November 2026), in the hit store
  `data/ssy.sqlite` (`store.py`): every hit of all six looks, not only the
  candidates, with its frequency at the start and end of the look, drift
  and its error, SNR, power and noise in the file's units, width, smear
  (channels crossed in one spectrum) and whether it sits near a coarse
  channel's end or middle; every cadence result with the hit it matched in
  each look; the file, ETag and header of each look; and for each run the
  code's commit, the libraries and every search parameter. One transaction
  a block, so a block is in the store whole or not at all, and the
  `blocks` table says where the next run starts. Rejected hits are the
  evidence later checks (recurrence, look-alikes) work from.
- **A block searched again keeps its history.** Its earlier hits and
  events are not deleted but marked superseded by the new run, and the
  checks made on them stay; each new event names the earlier event at the
  same place and drift it replaces, so a candidate's checks follow it
  through a re-search. Each run records the search's version
  (`SEARCH_VERSION` in `seti.py`). The current results are the rows not
  superseded. (Tested 9 November 2026 on a copy of the store: block 0
  searched again, its 6 old hits and its event kept as superseded, the new
  event linked to the old.)
- **NULL means not measured**, never zero: `flagged_fraction` is NULL
  until Phase 3's spectral kurtosis, and says nothing about interference
  until then. `power` and `noise` are in the file's own data units
  (uncalibrated spectrometer output, not Jy): `noise` one spectrum's
  robust standard deviation at the hit's channel, `power` SNR × √16 ×
  noise. Physical units come with Phase 3's calibration.
- **A readable record** is written from the store after each run
  (`data/sweeps/TARGET-SESSION.json`): each block's counts and candidates,
  which `check.py` reads. The counts of the 12 blocks searched before the
  store kept hits are carried in it as `before_hit_store`.
- **The next block is fetched while this one is searched**, and the six
  looks are searched side by side. Each block's bytes, fetch and search
  seconds, CPU time and peak memory go to `data/logs/sweep.log`. A lock
  file (`data/sweep.lock`) stops two sweeps running at once.
- **The search sums in float32, a tile of the band at a time**: on the
  reference block (below) its hits and cadence labels are the same as the
  old np.roll search's, to the last figure kept, at about 4 s a look
  against 39 s.

## The reference block, and the speed (8 November 2026)

**The reference.** Block 153 of the 2017 cadence (2266.699 to 2269.629 MHz,
the slice benchmarked against turboSETI, widened to its whole coarse
channel), all six looks, saved in `data/reference/` (67 MB each; the
URLs in `reference.json`). The old search's answer on it is kept in
`baseline.json`, stamped with its commit (3cfeb68): hits per look 4, 2,
2, 1, 1, 2; four events, the 2267.509 MHz tone as interference and three
unconfirmed. Every change to the search is checked against it offline.

**The new search on it:** every hit the same (channel, frequency, drift,
SNR to 0.1, width) in all six looks, and the four events the same, at
4.2 s a look against 39 s. The band-shape step (`flatten`) is the old
one's values exactly, done block-wise in one go (1.1 s against 1.7 s).

**A sustained run** (`sweep --blocks 11 --threads 6`, blocks 1 to 11 of
the cadence, 8 November 2026):

| | per block |
|---|---|
| moved over the web | 296 to 312 MB (the data; 880 MB with the old reader) |
| fetch, six looks | 16.5 to 19.9 s, hidden behind the last block's search |
| search, six looks side by side | 18.9 to 24.0 s |
| each block, end to end | 21.6 s mean after the first (38.5 s, nothing to overlap) |
| CPU | about 100 s a block, about 5 of the 16 cores |
| peak memory | 4.2 GB (1.9 GB since 9 November: the noise is measured a spectrum at a time) |

The run is limited by the search, not the network. At 4 requests in
flight the fetch took 19.6 to 21.7 s, at 8 16.2 to 17.3 s (3 blocks
each): 6 stays the default, as 8 gains nothing a search-bound run can
use. The 308 blocks of the cadence would take about 1 h 50 min; that
estimate is from these 18 blocks, not yet a whole cadence.

**The same answers as before.** The 12 blocks the old sweep had searched
(1818.46 to 1853.61 MHz) were searched again into the hit store: every
block's counts the same as recorded (0 candidates, 11 interference, 1
unconfirmed), now with every hit kept: 73 hits in the six looks. One query
finds hits within 200 Hz of each other in different looks (140 pairs; the
first is a steady tone at 1820.000 MHz in all six: interference).

## A correct search (9 November 2026)

`searching.py` is the search since 9 November 2026 (search version 2);
`measure.py` measures it. Every figure here is from planted signals in real
looks or from the looks themselves: block 153 (the reference) and blocks 40,
100, 200 and 280 of the 2017 cadence (1.94, 2.11, 2.40 and 2.64 GHz; block
200 is in the 2.4 GHz Wi-Fi band), all six looks of each saved in
`data/reference/`. The answers are in `data/measurements/`.

**How it works now.**

- Each spectrum's band shape is taken out and its noise measured block by
  block, as before.
- Every drift line to ±4 Hz/s is summed. A line faster than one channel a
  spectrum (0.153 Hz/s) sums, in each spectrum, the N channels it crosses
  (N = ⌈|drift| × 18.25 s / 2.79 Hz⌉, up to 27 at 4 Hz/s): the boxcar
  desmearing of hyperseti and BLISS.
- A line's SNR is its sum less the median of the summed lines, over their
  robust spread, both measured on the summed lines themselves, per block
  of 1024 channels and per box width.
- Hits are picked strongest first. Each one's track is blanked, and the
  lines near it are summed again before the next is picked, so a weak
  signal beside a strong one is found on its own. A signal lit over far
  more channels than its box is one hit, marked wide, with its width.
- Hits from SNR 5 to the cut of 10 are kept as shadow hits: evidence for
  later checks, never seeds or matches in the cadence test.
- Each channel's spectral kurtosis is measured; a hit carries the share of
  its track that is flagged.

**The noise of the summed lines** is √(16 × N) times a spectrum's noise, as
the old search assumed: the measured spread over √(16N) is 1.00 at the
median for one channel and 0.97 to 1.00 for 27, in every look measured,
with the 90th percentile of blocks at 1.05 to 1.18. The "off by up to 3×"
reported for setigen (issue #32) does not show in these data. What was
off is the level: the summed lines sit about 0.5 (in a spectrum's noise)
above zero, per channel of box, because each spectrum's median, not its
mean, is taken out and the power's distribution is skewed. The old search
read every SNR about 0.13 high; this one takes the median off.

**The planted strengths are measured independently of the search.**
`measure.py` sets each signal's strength from a channel's noise measured
by its own method (differences between neighbouring channels, which
cancel the band's shape), not the search's `flatten`. On all 30 looks the
two estimates agree: the planting's over the search's is 0.9999 at the
median (0.993 to 1.001 across looks; 0.98 to 1.02 across blocks within a
look; `measure.py noise`). Physical units (Jy, from the receiver's SEFD)
come in Phase 6.

**Each look's search is kept** in the store's `looks` table: its hits and
shadow hits, the noise of its summed lines by box width, its flagged
channels, and whether it is complete. The search picks at most 2,000 hits
a look; if it stops there, the look is marked not complete with the
number of line starts still over SNR 5, the block is marked not complete,
and nothing later may treat its hits as the whole list. No look of the 18
blocks swept first reached the limit (most had about 250 hits); in the
whole sweep the crowded blocks do (34 of the first 654 block-looks, in 10
blocks near 1918 to 1960 MHz). The result page lists those blocks and
leaves them out of the usable band and the limits: their candidates and
interference stand, but a signal there may have gone unpicked.

**Against turboSETI** (`measure.py scale`; turboSETI 2.3.2): 30 slow
signals (|drift| < 0.15 Hz/s, S_in 60 to 300) planted in one look of each
of the five blocks, both searches run on the same files, 123 signals found
by both. turboSETI's SNR is **0.227 of this search's** at the median of
the five blocks (0.224 to 0.242 across them; quartiles within a block
about ±5%). turboSETI's cut of 10 is about 44 on this search's scale, so
the two searches' "SNR 10" are far apart: turboSETI's noise estimate runs
high, as Choza et al. 2024 found (their factor 3.25 on their data; about
4.4 here, the inverse of 0.227). It is a measured ratio for these blocks,
for slow signals: not a constant.

**Desmearing chosen by planted signals** (`measure.py desmear`; four looks
in four bands, 40 signals in each drift bin and strength, the same planted
data through each method; found = a hit at the cut within 3 channels and
its box of the planted start, drift within 3 steps or 10%):

| drift (Hz/s) | S_in | boxcar | scrunch | none |
|---|---|---|---|---|
| 0 to 0.15 | 15 | 50% | 50% | 50% |
| 0 to 0.15 | 30 | 100% | 100% | 100% |
| 0.15 to 0.5 | 30 | 100% | 100% | 90% |
| 0.5 to 1 | 30 | 92% | 50% | 2% |
| 0.5 to 1 | 60 | 100% | 100% | 95% |
| 1 to 2 | 30 | 22% | 0% | 0% |
| 1 to 2 | 60 | 100% | 100% | 5% |
| 2 to 4 | 60 | 95% | 45% | 0% |
| 2 to 4 | 120 | 100% | 100% | 5% |

The SNR found over S_in, by drift bin, with the boxcar: 0.68, 0.53, 0.39,
0.28, 0.22 (theory for a box of N channels: 1/√N, 0.19 to 0.28 at 2 to 4
Hz/s). Without desmearing it falls to 0.09 at 2 to 4 Hz/s, and the strong
fast signals there made 131 hits at the wrong place or drift (boxcar: 0;
scrunch: 1). **The boxcar is kept.** The full table, with Wilson
intervals, is in `data/measurements/desmear.json`. S_in is set from the
raw spectra alone (see measure.py): the SNR a search would give collecting
all the power in ideal noise. Even at slow drift a search finds 0.68 of
it, because a tone at a random place in a channel puts only part of its
power in the nearest channel (the sinc-squared response of an FFT channel;
Breakthrough Listen's polyphase filterbank has a flatter response, so this
loss is, if anything, overstated here: unverified).

**Close pairs** (`measure.py pairs`; 12 pairs each): with the boxcar, two
equal signals at 0.05 Hz/s, or at +1 and −1 Hz/s, come out as two hits at
3 channels apart and more, every time; two at the same 1 Hz/s (box of 7
channels) at 30 channels and more every time, at 10 in 8 of 12, and at 3
never (their boxes overlap: one hit). A weak signal (S_in 30, 0.3 Hz/s)
beside one 20 times stronger was found every time at 10, 30, 100 and 300
channels: the blanking works.

**Spectral kurtosis** (`measure.py kurtosis`; all 30 looks). The flag at 3
marks 0.018% to 0.026% of the channels of quiet looks (noise alone would
give 0.0076%: the real tail is about three times heavier), 0.04% to 0.06%
of busier ones, and 0.46% of the ON look with the burst. Leaving flagged
channels out of the noise made no difference to what was found (boxcar
with and without: the same within one signal per cell). But **it flags
real signals**: planted signals drifting under 0.5 Hz/s at S_in 60 and
above had 56% to 100% of their tracks flagged, because a slow tone sits in
each channel for a few spectra only. Fast ones (over 1 Hz/s) were almost
never flagged. A hit's `flagged_fraction` is therefore recorded and never
read as interference on its own.

**False hits, a stress test** (`measure.py false`; each of the 30 looks scrambled twice:
every spectrum turned round the band by its own random amount, so it keeps
its noise and its interference but no signal can line up from one spectrum
to the next):

| looks | hits at the cut | per block of six looks (95% interval) |
|---|---|---|
| 48 looks of blocks 40, 100, 200, 280 | 0 | 0 (0 to 0.46) |
| 12 looks of block 153 | 53 | 26.5 (19.9 to 34.7) |
| all 60 | 53 | 5.3 (4.0 to 6.9) |

Where the band is quiet the cut makes no false hits. Block 153's come from
its strong tone at 2267.509 MHz (SNR about 80) and the burst in scan 31:
scrambled, their bright pixels are scattered through the band, and lines
through several of them reach the cut (SNR 10 to 17.6). That is harsher
than the real looks, where those pixels form one tone; but it says that
impulsive interference, bright for one spectrum at a time, does make false
hits at this cut, and that a block's count of hits has to be read with its
interference. Shadow hits (SNR 5 to 10): about 275 a look, scrambled or
not. This is a stress test of one look's detections, not the pipeline's
false-alarm rate: scrambling changes the data's structure, and it says
nothing of how often noise or interference makes a *candidate* that
survives the six looks and the checks. That is measured on whole cadences
in Phase 6.

**The reference block** through the new search: the 2267.509 MHz tone in
all six looks (SNR 50 to 95; interference), the weak 2269.557 MHz tone in
scans 32, 33 and 36, and the burst at 2266.8 MHz as three fast-drifting
hits in scan 31, one marked wide; the cadence gives the same labels as
before (one interference, three unconfirmed, no candidate). New: a hit at
−3.99 Hz/s with a 27-channel box in scan 32, which summing one channel a
spectrum could not collect. 220 to 350 shadow hits a look. 5.5 s a look.

**The 18 blocks swept, searched again** (9 November 2026, `sweep
--blocks 18`): 287 hits at the cut where version 1 found 123, 46
interference where it found 19, 4 unconfirmed, no candidate; 28,321 shadow
hits (about 1,500 a block); 190 of the hits in one block (6, 1836 to 1839
MHz). Version 1's hits and events stay in the store marked superseded, and
each of its 24 events is linked to the new event that replaces it. About
34 s a block (fetch 18 to 27 s, hidden; search 29 to 58 s; 120 CPU
seconds; 2.3 GB peak): the whole cadence would take about 2.9 hours.

## The cadence test (Phase 4, 9 November 2026)

`onoff.py` is the cadence test since search version 3:

- **Every ON look's hits at the cut are seeds**, not only the first look's:
  a signal that starts in the second ON look is followed.
- **Hits are matched by one distance**, one to one, closest first. A hit
  is projected to the other look's start along its drift; the frequency
  difference in channels over its tolerance (3 channels, plus half each
  hit's box, plus the drift's error over the time between: half a drift
  step or 2% of the drift, whichever is more), and the drift difference
  in drift steps over its tolerance (2 steps plus 5% of the drift), are
  added in quadrature; a match is 1 or less. The ±50% drift tolerance of
  the old test is gone. Groups join only when every hit of one matches
  every hit of the other (search version 4), so a chain of near matches
  (A with B, B with C, but not A with C) is two events, not one; on the
  six real cadences here this changed no event.
- **The OFF test's veto rate is measured in every block** (search version
  4): 32 random tracks, at random places and drifts, measured in the OFF
  looks as an event is; the share that would be vetoed (S/N 6 or more, or
  a hit near) is kept with each block in the store (`blocks.off_null_*`).
  On the five saved cadences and HIP 91699's, 1 of 192 (a hit already
  there), none at S/N 6; the noise's median best S/N 3.4 to 3.8. A whole
  cadence's sweep gives about 9,800 such tracks across the band.
- **Every look is measured along the event's track**, found or not: the
  S/N of the summed line (box included) against the same line 60 to 1,900
  channels to either side, the best within the matching tolerance. In an
  ON look that is its drift fit; in an OFF look, its power with no
  threshold.
- **Interference** is any OFF look at S/N 6 or more along the track (where
  the drift would put it, or where it started), or any hit there of any
  strength, shadow hits from SNR 5 included. **A candidate** has no OFF
  evidence, a hit at the cut in at least one ON look, and in every ON look
  a hit or an S/N along the track of 5 or more. The rest are unconfirmed.
- Recorded with each event: the OFF looks' brightest S/N, the ON looks'
  faintest, the spread of the ON looks' drifts (flagged beyond 2 steps),
  the largest ON/OFF stamp dot product (ATA's DOT score), and each look's
  measurements. A candidate's six stamps are kept in the store.

**The reference cadence** through it: the 2267.509 MHz tone is
interference (OFF S/N 79, DOT 0.56); the weak 2269.557 MHz tone, which
starts in the second ON look and so was never followed before, is
interference too (OFF S/N 15); the three fast hits in the burst remain
unconfirmed. 30 s for the six looks.

**Planted in whole cadences** (`measure.py cadence`; the five saved
cadences, three runs each, 32 signals in the ON looks only and 8 in all
six looks a run; 9 November 2026). Of the ON-only signals the search
found in a look, the share labelled candidate:

| drift (Hz/s) | S_in 15 | S_in 30 | S_in 60 | S_in 120 |
|---|---|---|---|---|
| 0 to 0.15 | 96% | 100% | 100% | 100% |
| 0.15 to 0.5 | 75% | 100% | 100% | 97% |
| 0.5 to 1 | - | 90% | 97% | 97% |
| 1 to 2 | - | 100% | 100% | 93% |
| 2 to 4 | - | 100% | 93% | 93% |

(30 signals a cell under 1 Hz/s, 15 above; "-": none found.) Of 370 ON-only signals found, 359 came
out candidates; of the 11 that did not, 10 were vetoed by noise in an OFF
look at S/N 5.2 to 6.5 (the best of noise over the matching window: median
3.3, 99th percentile 5.4) and one fast signal (2.4 Hz/s) stayed
unconfirmed. Every one of the 71 signals planted in all six looks and
found came out interference, with OFF S/N 11.6 and more. The OFF level was
then set at 6, where 2 of the 370 (0.5%) would be vetoed; Phase 6 measures
it through the whole pipeline. Interference fainter than 6 in an OFF look
is still caught by any hit there, down to SNR 5.

Measured again with the OFF level at 6 and complete matching (search
version 4; the same planted signals, `data/measurements/cadence.json`):
the same 370 found, 367 candidates, 2 vetoed (as expected at 6), 1
unconfirmed; the 71 in all six looks all interference. The table above
is the earlier run at 5.

## The checks (Phase 5, 9 November 2026)

`vetting.py` runs ten checks on each candidate, after Sheikh et al.'s
framework for blc1; `check.py` runs them on the store's current candidates
and keeps every result in the `checks` table, a record in `data/checks/`
and a report in `docs/leads/` with a picture of the six looks around the
track. No check deletes a candidate. Each result has a strength: **shown**
(the signal is demonstrably elsewhere), **indicated** (a strong sign short
of proof), **coincidence possible** (a relation whose chance, at this many
hits, is not small; the chance is recorded), or none.

| # | check | strength it can give |
|---|---|---|
| 1 | data sanity: every look complete, stamps finite, no blank spectra | none (a weak verdict if not sound) |
| 2 | the OFF looks below the threshold (the cadence test's S/N) | shown |
| 3 | known Green Bank bands (16 bands: GNSS, Iridium, Inmarsat, ADS-B, cellular, space links, the S-band notch filter, Wi-Fi) | indicated |
| 4 | zero or very low drift (under one drift step, 0.0102 Hz/s) | indicated |
| 5 | drift against the Earth's (rotation and orbit, toward the target, at Green Bank) | recorded only |
| 6 | recurrence at other targets and times in the store | shown: a hit at the cut within 3 days, drift agreeing, that chance would give under 5% of the time, by the files' measured hit density near the candidate; indicated: the same from shadow hits, or many matches against few expected; else coincidence possible |
| 7 | look-alikes: the same drift over frequency (or its mirror) in the cadence, and whether they show in OFF looks | indicated, or coincidence possible |
| 8 | harmonics (×2 to ×20, ÷2 to ÷20), clock spacings (2.000004 to 133.33 MHz) and intermodulation (a·f1 ± b·f2 of strong zero-drift hits), within 1 kHz | indicated, or coincidence possible |
| 9 | crowding: hits in the MHz around it against the band's median | indicated at 10 times |
| 10 | the report, with blc1's ten steps each marked automated, in part, or not possible here (re-observation: the project has no telescope); a Rio 2.0 score only for "unexplained, strong", by hand | |

The verdict: **interference (shown)** if any check shows it; **likely
interference (indicated)** if any indicates it; **unexplained, strong**
if every ON look has a hit at the cut and the data are sound; otherwise
**unexplained, weak**. "Unexplained" is the end of these checks, not a
discovery: blc1 was unexplained until its look-alikes were found.

Chance rates. For look-alikes (check 7) the chance is the Poisson chance
of finding at least as many in the OFF looks as were found, when the
expected number is the OFF hits at the cut times the share of the ±4 Hz/s
drift range the tolerance covers (2 drift steps, over frequency, and its
mirror). Near zero drift, where interference crowds, a look-alike is only
ever a possible coincidence. For harmonics and intermodulation (check 8)
the chance is the share of 200 random frequencies in the session's band
that would find a relation too. A relation is "indicated" when its chance
is under 5%.

The Earth's drift (check 5) for Tabby's star (RA 20h06m15.45s, Dec
+44°27′24.6″) from Green Bank on 25 May 2017 at 2267.5 MHz is about
−0.106 Hz/s (rotation −0.102, orbit −0.004).

**Tested on planted signals** (`measure.py vetting`; reports in
`data/measurements/vetting/`). In each of two cadences, a lone signal in
the ON looks only, and a family of five signals sharing one drift over
frequency (as harmonics of one oscillator would): four in all six looks,
as interference, and one more in the ON looks only, as blc1 was.

| block | signal | cadence test | the checks |
|---|---|---|---|
| 100 (2111-2114 MHz) | lone, −0.83 Hz/s | candidate | unexplained, strong |
| 100 | family member in the ON looks only, +0.45 Hz/s | candidate | likely interference (indicated: look-alikes in the cadence: 12 in OFF looks where 0.12 were expected by chance) |
| 100 | the four family members in all looks | interference | (not checked: not candidates) |
| 153 (2266.7-2269.6 MHz) | lone | candidate | likely interference (indicated: in the 2200-2290 MHz space downlink band) |
| 153 | family member in the ON looks only | candidate | likely interference (indicated: the band; look-alikes) |

The family's lone ON member is caught by its look-alikes, as blc1 was; a
lone signal in a clean band comes out unexplained, and in a band of known
transmitters is marked, not dropped.

What the checks cannot do from archive data: re-observe (blc1 step 10);
compare with an observatory interference database (Green Bank publishes
none in machine-readable form: the store becomes this project's); judge
by eye whether look-alikes are one phenomenon (step 8 is automated only
by the chance rates). Recurrence (check 6) sees only what the store holds:
this cadence's OFF looks now, more as other sessions and targets are
searched. The store is asked, file by file, for the same window check 6
tests (100 Hz plus the drift's travel over the time between, within a
day; `check.recurrence_hits`, since 9 November 2026; before, a fixed ±12
kHz, which a fast signal hours away could fall outside). Those hits were
picked for lying near the candidate, so their own spread cannot give the
chance of a match: check 6 (checks version 3) takes it from every file it
looks in, matched or not, as that file's hits within 1.5 MHz of the
candidate over the band its session searched there
(`check.recurrence_background`), with the share whose drift agrees counted,
not assumed uniform over ±4 Hz/s. Without that background check 6 never
says "shown". The density is still flat within the 3 MHz, and checks 7 and
8 still assume a uniform one; interference clusters, so a small chance is a
sign, not proof of one transmitter ([comparable.md](comparable.md), step 6,
measures the occupancy by frequency and drift).

## Checked against turboSETI

`./seti.py search` and `cadence` take `--keep DIR` to save each slice
they read (a small HDF5 file in Breakthrough Listen's own layout), and
`./seti.py benchmark FILE...` runs each saved slice through this search
and through turboSETI, Breakthrough Listen's own, at the same limits
(10 times the noise, drifts to 4 Hz/s), and lists what both find and
what only one does. turboSETI is not an Ubuntu package: it is installed
in its own environment that sees the system's h5py
(`python3 -m venv --system-site-packages ~/.local/share/signalsearchyoke/seti-venv`,
then its `pip install turbo_seti`; `SSY_TURBOSETI_PYTHON` names another).

On a made-up flat band with two tones (3 November 2026) both found both.
On a sloping band turboSETI found neither: it measures the noise over the
whole slice, band shape and all, where this search takes the band's
shape out first. That is a difference in method to be measured on real
data, not a fault in either.

On real data (3 November 2026): Tabby's star, Green Bank, 25 May 2017,
2266.75 to 2269.60 MHz, one ON look (scan 31) and one OFF (scan 32),
the same saved slices through both searches at SNR 10 and 4 Hz/s.

| Look | this search | turboSETI | both |
|---|---|---|---|
| OFF (scan 32) | 2 | 2 | 2 |
| ON (scan 31) | 61 | 10 | 5 |

Outside one burst of interference at 2266.79 to 2266.91 MHz, turboSETI
found nothing this search missed; this search found 5 more, weak (SNR
11 to 19), four within 0.02 MHz of the slice's lower edge and one by
the burst: the edge of a slice is still where it is least sure. In the
burst it keeps 51 separate hits where turboSETI keeps 5: turboSETI
folds a burst 110 kHz wide into fewer hits, and on the brightest the
two drifts differ by about 0.07 Hz/s (more than the two steps the
comparison allows). The whole cadence of that slice (all six looks,
880 MB read in 23 minutes on the laptop: the old reader moved about three
times the 300 MB of data) gave no candidate: 13 hits of the first ON look
were in an OFF look too, and 98 were not in every ON look.

## Is the search right?

### Completeness through the whole pipeline (Phase 6, 9 November 2026)

`./seti.py inject` plants signals as the sky makes them (smeared through
each 18 s spectrum, an FFT channel's sinc² response, a random place in a
channel, strength S_in set from each look's own noise measured apart from
the search) in the three ON looks of a saved cadence, each at the
frequency its drift carries it to by that look's start, and none in the
OFF looks; then searches all six looks, runs the cadence test and the
checks, and follows every signal to the end. A signal is **kept** when it
comes out a candidate the checks do not call interference ("likely
interference" is a weight on it, counted apart, not a loss). Five
cadences: block 153 (the reference) and blocks 40, 100, 200 and 280,
1.94 to 2.64 GHz; 3,257 signals in all (`data/measurements/completeness.json`,
and the store's `injections` table). Flux is from the radiometer equation
with Green Bank's SEFD taken as 10 Jy (Price et al. 2020), 2
polarisations, 2.79 Hz channels and 18.25 s spectra: S_in 1 is about 0.69
Jy Hz (0.69 × 10⁻²⁶ W m⁻²). The SEFD has since been measured at 10.65 Jy
("The instrument, measured", below): the result page scales these fluxes
by it (6.5% higher); the table keeps the 10 Jy it was made with.

Kept, of those planted in the ON looks only (95% Wilson interval):

| drift (Hz/s) | S_in 15 (10 Jy Hz) | S_in 30 (21) | S_in 60 (41) | S_in 120 (83) |
|---|---|---|---|---|
| 0 to 0.15 | 85% (78-90) | 100% (97-100) | 100% (97-100) | 100% (97-100) |
| 0.15 to 0.5 | 19% (13-27) | 100% (97-100) | 99% (96-100) | 100% (97-100) |
| 0.5 to 1 | 0% (0-3) | 98% (95-100) | 99% (96-100) | 100% (97-100) |
| 1 to 2 | 0% (0-3) | 52% (44-60) | 99% (96-100) | 99% (96-100) |
| 2 to 4 | 0% (0-3) | 4% (2-9) | 97% (92-99) | 99% (95-100) |

130 signals a cell under 1 Hz/s, 144 or 145 above. Where they were lost:
almost all at the search (too faint for the cut once smeared); 10 at the
cadence test (noise in an OFF look over the OFF level, or a fast signal's
looks not joined); none at the checks.

- **By place in the coarse channel** (S_in 60 and 120): the middle 99%
  (1,201 of 1,209), within 5% of an end 98% (146 of 149), within the
  drift's reach of the blanked spike at the middle 100% (20 of 20; 84-100%:
  fewer than the 100 the plan asks, said here rather than left out). The
  outermost 3,000 channels of a slice (0.3%) are not planted: the search
  cannot follow a track off the slice.
- **Interference planted in all six looks:** none of the 301 found was
  kept as a candidate.
- **The checks mark, they do not drop.** 1,225 of the 1,972 planted
  candidates were marked "likely interference", almost all for their band:
  blocks 40, 153 and 200 sit in the cellular, space-downlink and Wi-Fi
  bands, and every candidate there is marked. In the two clean blocks (100
  and 280) 41 of 788 (5.2%) were marked: 26 for a drift under one step
  (as a ground transmitter's), 24 for a chance harmonic or
  intermodulation relation with the other planted signals (about the 5%
  the chance threshold allows), 4 for chance look-alikes (some for two
  reasons). SETI@home's aim, that vetting loses under 10% of planted
  signals: no check dropped any; the band marks are a weight a reader has
  to see.
- **False candidates through the whole pipeline:** each cadence's six
  looks searched once, then judged with each of the 19 other choices of
  three looks as the ON looks, where no signal from the target can pass:
  152 events, **1 candidate in 95 judged cadences**: a signal at 1937.81
  MHz in the first three looks only (interference that came and went),
  which the checks marked for its band. **None came out unexplained.** The
  19 choices of a cadence share its six looks, so they are not 95
  independent trials: counted as distinct signals in 5 real cadences, it
  is 1 in 5, **0.2 a block's cadence (95% interval 0.005 to 1.1)**
  (`injection.false_summary`). That bound is wide: over the 308 blocks of
  a whole cadence it allows anywhere from about 1.5 to 340 false
  candidates before the checks, and says little about how many reach
  "unexplained". The sweep itself will be the larger sample: every block's
  events are kept.
- **Against setigen** (`measure.py setigen`; setigen 2.7.0, Brzycki et al.
  2022): the same tones on an empty frame at 0.05 to −3.5 Hz/s; the
  profiles correlate 0.994 or better in every spectrum, the centroids
  agree within 0.2 channel; setigen's sinc² profile carries 8.5% less
  power for the same level, a convention of its own (ours carries 0.96 to
  1.00 of the power asked for; only sinc² tails beyond 4 channels are
  dropped).
- **Not modelled:** Breakthrough Listen's polyphase filterbank response
  (flatter across a channel than sinc², so the loss at a channel's edge is
  if anything overstated here); signals that are not steady tones (pulsed,
  wide, or drifting unevenly).

The earlier single-look tables (below) were made with the old planting,
one channel a spectrum, and overstate what is found above 0.15 Hz/s; they
are kept as the history of how the search was first checked.

### Before 9 November 2026

Measured on real data before the sweep was let loose.

**Signals planted in real noise** (`./seti.py inject`, now marked LEGACY in
every answer and record: it plants one channel a spectrum, and is
superseded by `measure.py desmear` until Phase 6 rebuilds it; 3 November 2026,
the OFF look of Tabby's 2017 cadence, scan 32, 2266.75 to 2269.60 MHz,
40 drifting signals at each strength, drifts up to 3.6 Hz/s):

| SNR planted | found | drift off by (median) | false hits |
|---|---|---|---|
| 10 | 30% | 0.001 Hz/s | 0 |
| 12 | 82% | 0.002 Hz/s | 0 |
| 15 | 98% | 0.003 Hz/s | 0 |
| 20, 30, 50 | 100% | 0.003 Hz/s | 0 |

The search's cut is SNR 10, so a signal at the cut is found about a
third of the time, as noise pushes it either side; from SNR 15 almost
all are found, and none of the 240 runs made a false hit.

**This table overstates what is found above about 0.15 Hz/s** (found
8 November 2026). `plant` puts each signal's whole power in one channel a
spectrum, whatever its drift; a real signal drifting faster than one
channel per spectrum (2.79 Hz / 18.25 s ≈ 0.153 Hz/s) spreads its power
over every channel it crosses within the spectrum, about 24 at 3.6 Hz/s,
and the search, summing one channel a spectrum, collects a fraction of
it. The table holds for slow drifts only; Phases 3 and 6 of
docs/overhaul.md measure it properly.

**Against turboSETI** after the changes of dd1a763 (noise measured
block by block, one hit per run of bright channels, the ends masked):

| Look | this search | turboSETI | both | only this | only turboSETI |
|---|---|---|---|---|---|
| ON, scan 31 | 3 | 10 | 2 | 1 | 8 |
| OFF, scan 32 | 3 | 2 | 2 | 1 | 0 |

All eight hits only turboSETI found, and the one only this search found
in scan 31, lie in one burst of interference 110 kHz wide (2266.79 to
2266.90 MHz), which this search now counts once and turboSETI eight
times. Outside it the two agree on every hit turboSETI finds. The one
extra hit in scan 32 is at SNR 10.4, at the cut, 0.07 MHz from the end
of the coarse channel. Measuring the noise block by block has one cost
to know: a burst filling a block raises that block's noise, so the
burst's own SNR comes out low (17.8 here, where turboSETI gives 157).
That matters for wide interference, not for the narrow signals this
looks for.

**All seven looks, two sessions** (b23ab79: the receiver's spike at
each coarse channel's middle, the "DC bin", blanked; turboSETI reads the
saved slices spike and all, so its hit there is counted apart). The
2017 cadence's six looks at 2266.75 to 2269.60 MHz, and the 2018 look
(session AGBT18A_999_30, scan 9) at 1472.20 to 1475.05 MHz:

| Look | this search | turboSETI (spike apart) | both | only this | only turboSETI |
|---|---|---|---|---|---|
| 2017 ON, scan 31 | 2 | 9 | 1 | 1 | 8 (all in the burst) |
| 2017 OFF, scan 32 | 2 | 1 | 1 | 1 | 0 |
| 2017 ON, scan 33 | 2 | 1 | 1 | 1 | 0 |
| 2017 OFF, scan 34 | 1 | 1 | 1 | 0 | 0 |
| 2017 ON, scan 35 | 1 | 1 | 1 | 0 | 0 |
| 2017 OFF, scan 36 | 2 | 1 | 1 | 1 | 0 |
| 2018 ON, scan 9 | 2 | 0 | 0 | 2 | 0 |

Outside the one burst, turboSETI found nothing this search missed. The
hit both find in every 2017 look is a steady tone at 2267.509 MHz (SNR
about 80) in ON and OFF alike: interference. The extra hits are weak:
a steady tone at 2269.5573 MHz (SNR 10 to 13) in scans 32, 33 and 36,
ON and OFF, so interference too, which turboSETI's whole-band noise
leaves under its cut; and two in 2018 at SNR 14.4 and 10.4. Planted in
the 2018 look's noise, signals are found as in 2017: 28% at SNR 10,
78% at 12, 98% at 15, all at 20 and above, no false hits in 240 runs.

On that evidence the sweep is let loose (3 November 2026): it agrees
with turboSETI on seven real looks from two sessions and finds 98% of
signals at SNR 15. What it finds is still judged by the cadence, and a
candidate is still ours until checked.

## Real signals (Phase 7, 9 November 2026)

Planted signals test the pipeline against the model of a signal; these
test it against real transmitters.

### Voyager 1

`./measure.py voyager` (`data/measurements/voyager.json`). The file
turboSETI's own documentation uses (Enriquez et al. 2017's check):
`blpd0.ssl.berkeley.edu/Voyager_data/Voyager1.single_coarse.fine_res.h5`,
one coarse channel at 8418.5 to 8421.4 MHz, 16 spectra, Green Bank, 19
September 2016 (50 MB, ETag "5d166dbd-30351eb").

| | turboSETI's README | turboSETI 2.3.2 here | this search |
|---|---|---|---|
| carrier | 8419.297028 MHz, −0.3731 Hz/s, SNR 245.7 | 8419.297028, −0.3776, 245.7 | 8419.297031, −0.3776, 1360.5 |
| sideband | 8419.319368, −0.3922, 30.6 | 8419.319368, −0.3980, 30.6 | 8419.319368, −0.3878, 112.1 |
| sideband | 8419.274374, −0.3922, 31.2 | 8419.274374, −0.3980, 31.2 | 8419.274374, −0.3776, 112.9 |

- **Found where published:** all three within one channel (3 Hz) and two
  drift steps (0.02 Hz/s); turboSETI 2.3.2 gives the README's frequencies
  and SNRs with a slightly different drift (its drift grid has changed
  since).
- **The drift is the Earth's:** check 5's arithmetic toward Voyager (RA
  17.168 h, Dec +12.18°) at mid-scan gives −0.3772 Hz/s (rotation −0.4060,
  orbit +0.0288); measured −0.3776. Voyager's own acceleration is far
  below a drift step.
- **SNR:** turboSETI's is 0.18 of ours on the carrier and 0.27 on the
  sidebands (0.227 on planted signals, "Checked against turboSETI"): its
  noise is taken from the summed spectrum around a very bright line.
- **What the model leaves out: wide signals.** Each sideband is a band of
  power about 322 Hz wide (115 channels) between two lines at the
  carrier's drift (the second-order sidebands, at ±67 kHz, are the same).
  This search records 51 hits at the cut: 17 at the carrier's drift (the
  lines, and weaker ones a few channels from the carrier), and 34 at
  −0.93 and −1.55 Hz/s, tiling the bands of power between the lines with
  wider boxes. turboSETI keeps only the strongest hit within ±600 Hz and
  records 3. Neither describes a wide signal as one: in a cadence, a wide
  interferer gives this search many events (each judged on its own, so
  still interference when it is in the OFF looks), and the crowding check
  sees it. A wide-signal search is not part of this one.

### Price et al. 2020: HIP 91699

`./measure.py price` (`data/measurements/price.json`). Price et al.
(2020, 1,327 stars) published totals only (at Green Bank S-band, 10.12
million hits, 5,102 events, 1,572 event groups, no candidates), not their
hit or event lists, so no star's hits can be set against theirs. Their
Fig. 8 shows S-band events at four stars, all judged interference by eye;
for HIP 91699 the text says the events are short, drifting, and like
others at 2200.04 to 2200.5 MHz, some in OFF looks. Their pipeline is
public, so it was run here on the same data: turboSETI at ±4 Hz/s and SNR
10, its event pipeline at filter threshold 3 (`tools/turbo_events.py`),
on the 2200.0 to 2200.6 MHz slice of both of HIP 91699's S-band cadences.

| session | Price's pipeline, run here | this search and cadence test | the checks |
|---|---|---|---|
| AGBT17A_999_25 (14 March 2017) | no event | no event | |
| AGBT17A_999_67 (22 May 2017; OFF looks HIP 90977, HIP 91058, HIP 91119) | 1 event: 2200.050356 MHz, −3.83 Hz/s, SNR 153 | 2 candidates: 2200.050412 MHz, −3.98 Hz/s, SNR 291 (from the first ON look) and 2200.047476 MHz, −3.83 Hz/s, SNR 580 (from the second) | both **likely interference (indicated)**: the space downlink band, and recurrence in the third OFF look |

- **Found by both pipelines**, in the band and at the drift Price et al.
  describe, and passing both cadence tests: nothing at its drift in the
  OFF looks (OFF S/N 3.5 at most here). That matches their interference
  case at this star; it does not show which transmitter it was.
- **Two candidates, kept as two.** They start 2.94 kHz apart, 694 s
  apart in time. Carried along −3.98 Hz/s, the first lands 174 Hz (62
  channels) from the second: a matching distance of 1.47, beyond the 1 at
  which looks join. They are consistent with one transmitter whose drift
  changes (−3.98, −3.83 and −3.54 Hz/s at the starts of the three ON
  looks, by this search), but that is not shown, and nothing here joins
  them: each is judged, checked and reported on its own. turboSETI's
  pipeline reports one event, its own table giving it in 2 of the 3 ON
  looks.
- **The checks mark them, as Price et al. did by eye, and say how
  strongly:** the third OFF look (HIP 91119) has a spray of tracks at
  2200.043 MHz drifting −1.4 to −3.9 Hz/s (turboSETI's hit there: SNR 10.7
  at −2.10). This search has them all as shadow hits (SNR 5 to 10), so
  check 6, given the cadence's OFF looks as the store gives them, calls the
  recurrence **indicated**, not shown: a shadow hit within two drift steps
  is a sign, not proof of one transmitter. (Before 9 November 2026 a single
  such shadow hit made it "shown"; "shown" now needs a hit at the cut whose
  chance match is under 5%.) Without the store only check 3 marks them,
  for the 2200 to 2290 MHz space downlink band.
- **Not reproduced:** the other three stars, and anything beyond this 0.6
  MHz: with no published hit lists, a fuller comparison is turboSETI against
  this search on the same data, which "Checked against turboSETI" already
  does.

## The instrument, measured (9 November 2026)

Three assumptions the limits rested on, measured from public data
(`instrument.py`; [comparable.md](comparable.md), step 2). None needed more
than 400 MB read; the sweep's own reads were left alone.

**The fine channel's response** (`measure.py response`,
`data/measurements/response.json`). Voyager 1's carrier drifts −0.377 Hz/s,
2.5 channels a spectrum, 40 in the look, so it crosses every place within
a channel. Each window's response, averaged over the carrier's place in
each of a spectrum's 51 FFTs, was fitted to the 16 spectra (±30 channels,
each spectrum's amplitude free, noise growing with power):

| response | χ² / dof |
|---|---|
| rectangular (no window, sinc²) | 3.72 |
| Hann | 5.79 |
| Hamming | 5.90 |

The unwindowed FFT fits best by Δχ² 1,950: the sinc² response the planted
signals were made with holds for these files (gpuspec, until now
unverified). The fit is not perfect (χ²/dof 3.7; residuals under 1% of the
peak in every channel), and the far wings run above sinc² beyond 5 channels
(0.0017 of the peak at 10 to 20 channels against sinc²'s 0.0005), which the
carrier's own phase noise could give: they are not separable here. One
observation (19 September 2016); that the 2017 files were processed the
same way is taken, not shown. Phase 6's completeness needs no new run.

**The SEFD** (`measure.py sefd`, `data/measurements/sefd.json`). The
archive has no flux calibrator from the 2017 session. It has 3C295, a
steady calibrator 5″ across (Perley & Butler 2017: no sign of
variability), in Green Bank's ON-OFF form (the OFF a degree north), in the
same S-band setup (1818.5 to 2720.8 MHz, the same channels) from two
sessions of a TESS survey, read in the `.0002` product (96 MB a scan). In
each coarse channel SEFD = S(3C295) / (P_on / P_off − 1), the power the
median over time of the mean over the channel's central 80%:

| pair | elevation | SEFD (median, 16-84% over the band) | used |
|---|---|---|---|
| 2 Dec 2019 20:00 UTC | 36° | 10.65 Jy (10.03 to 11.28) | yes: power steady to 0.2% and 0.5%, SEFD flat with frequency (f^0.02) |
| 27 Nov 2019 12:11 UTC | 57° | 15.49 Jy (14.05 to 17.92) | no: power moving +10% in the ON scan and −9% in the OFF, SEFD rising as f^0.84 (the source off the beam's centre) |

The pair used: `spliced_blc0001020304050607_guppi_58819_72038_3C295_0091`
(ON, SHA-256 7338cd8edccc03e6…) and `…_58819_72177_3C295_0092` (OFF,
393011fe1a630b85…), `.gpuspec.0002.h5` at
https://bldata.berkeley.edu/bl_tess/s_band/; the one not used,
`spliced_blc7071727374757677_guppi_58814_43898_3C295_0129` and
`…_44040_3C295_0130`. Full checksums and ETags in `sefd.json`.

So **SEFD 10.65 Jy**, against the 10 Jy assumed: every flux and EIRP on
the result page is now 6.5% higher than before. The 16-84% figures are a
spread over frequency, not an uncertainty. Carried to the 2017 cadence
(another epoch and elevation, one pair, so neither the transfer nor the
repeatability is measured), it is the best estimate within a bracket of
10 to 12.5 Jy, the published values for this receiver (Price et al. 2020's
10 Jy; 25 K at 2.0 K/Jy): the result page gives every EIRP limit with that
range too (0.94 to 1.17 times the value). A bracket of published values,
not a statistical interval. Over 50 MHz bins it runs
from 9.8 to 11.5 Jy (13.5 at the band's top edge). In the notch the ON/OFF
ratio is 1.07, as a filter that removes the source should leave it. Not
measured: the 2017 cadence's own (another epoch; the cadence was at about
56° elevation), the repeatability (one pair passes), the noise diode (not
in these files), the 8-bit requantisation's linearity, atmospheric opacity
(about 1%). Not used: 3C123 in AGBT17B_999_50 (the L-band setup) and
3C286 and 3C353 in AGBT19B_999_128 (the 3C286 "ON" header 2′ off the
source; 3C353 partly resolved by the beam).

**Dropped data** (`measure.py dropped KIC8462852 AGBT17A_999_68`,
`data/measurements/dropped.json`). Each chunk of the files is one spectrum
of one coarse channel, compressed: a chunk of zeros (rawspec's fill for
lost data) would be a few kB. All 29,568 chunks of the six looks are 3.07
to 3.35 MB (the smallest 97% of its file's median): no spectrum of any
coarse channel is zeros, and no node is missing (`zz`) or dropped (`oo`).
Read from the chunk indexes alone, no data. This finds no whole spectrum
of zeros; it does not show every sample intact: packets lost within a
spectrum lower its power without zeroing it and are not seen this way.

**A stored-data fault found on the way:** the files table held each
file's position divided by about 3,600 (`store._sexagesimal` unpacked the
HDF5 header's decimal hours as sigproc's packed hhmmss). Only check 5 (the
drift against the Earth's, which never sets a strength) read it, so no
verdict changed; its evidence did. Fixed in `store.py` (9 November 2026),
the stored rows put right from each row's own header (KIC 8462852 at 20.1043
h, +44.4568°; its OFF looks a degree north), and `check.py --all` run again. The result page now
lists each look's stored position against its own header, its distance
from the first look, its elevation (57 to 61°) and the Earth's drift there,
and says so in bold if any position and header disagree.

## Tabby's star

KIC 8462852 was observed by Green Bank in May 2017, among other times;
`./seti.py find KIC8462852` lists them. The whole cadence is on 25 May
2017 (session AGBT17A_999_68, scans 31 to 36: three looks at the star,
each followed by one at KIC8462852_OFF); the archive files the OFF looks
under their own name, so `find` reads them from the session's folder.

### The whole cadence, searched (9 November 2026)

All 308 blocks (1818.457 to 2720.801 MHz) searched with search version 4,
07:52 to 12:55 UTC on the Windows PC; the result page is
[results/KIC8462852-AGBT17A_999_68.md](results/KIC8462852-AGBT17A_999_68.md)
and each candidate's report is in [leads/](leads/).

- **Usable for limits:** 801.3 of 902.3 MHz: the notch (2300 to 2360 MHz)
  and 14 blocks where a look stopped at the 2,000-hit limit (41.0 MHz,
  near 1920 to 1985, 2190 to 2199 and 2496 MHz) are left out.
- **Found:** 72,555 hits at SNR 10 or more; 27,823 events: 27,423
  interference, 389 unconfirmed, 11 candidates.
- **After the checks (version 3):** 2 interference (shown: the signal
  recurs at other targets and times; 2188.43 and 2197.16 MHz, the latter
  the strongest at SNR 68) and 9 likely interference (indicated: zero or
  very low drift with crowding near 1918 to 1925 MHz; the band and
  crowding near 2105 MHz; the notch at 2316.7 MHz). No candidate came out
  unexplained, and no technosignature is claimed.
- **Sensitivity, measured** (90% of planted signals kept, SEFD 10.65 Jy,
  a transmitter under 1 Hz wide at 434.6 pc): EIRP 3.1×10¹⁴ W at drifts
  under 0.15 Hz/s, 9.5×10¹⁴ W at 2 to 4 Hz/s; 0.94 to 1.17 times these
  over the SEFD's bracket. About 13 to 23 times deeper than Harp et al.
  2016 at slow drifts, over the usable band only.
- **The OFF test's veto rate** on random tracks across the sweep: 85 of
  9,856 (0.86%), against 0.5% on planted signals.

The crowded blocks near 2190 MHz took 6 to 15 minutes each, against about
33 s for a quiet block, so the sweep took five hours, not the 2.7 first
expected.

### The other pipelines on the same cadence (9 November 2026)

turboSETI's event pipeline (Price et al. 2020's settings) and Painter et
al. 2025's pickles (commit e4539e3, run as published from its hotspots on,
its bands masked and unmasked) were run over all 308 blocks on the
sweep's own slices (`pipelines.py run`, about two hours), and set against
this search's events (`pipelines.py compare`). turboSETI kept 0 events
from 2,744 hits; pickles kept nothing with its masks, and 1 window at
level 2 (3 at level 1) without them. Every window pickles kept holds
interference events here (OFF S/N 6.0 to 7.4 along the track); with this
search's tracks blanked, none passes its level 1 (`pipelines.py
followup`: track-removal evidence, not a subtraction), and in two of them
a fast, wide, short band in another ON look (its movement only apparent,
from two or three spectra; what it is not established), outside both
drift searches, supplied pickles' second ON look. On
turboSETI's own statistics 10 of this search's 11 candidates are under its
cut in every ON look; the eleventh clears it in two ON looks but is
dropped by its top-hit rule for a larger line 2.1 kHz away. All 11 are
inside pickles' masks. The result page has each one.

### The pipelines at matched sensitivity (10 November 2026)

`matched.py run` (comparable.md steps 4 and 7; the page is
[results/KIC8462852-AGBT17A_999_68-matched.md](results/KIC8462852-AGBT17A_999_68-matched.md))
read 121 blocks of the cadence once each, the 61 crowded ones (more than
20 hits at the cut in the six looks) and 60 of the 247 clean at random,
and ran all three pipelines on them twice: with each of the 19 wrong
choices of three ON looks among the six, for the false candidates, and
with 110 signals planted in the true ON looks of each block (13,310 in
all; S_in 10 to 400, drifts 0 to 4 Hz/s), for the recovery.

**False candidates a block against the cut** (wrong-cadence control: real
looks of the target in the wrong roles, not empty sky; the two classes
weighted by their share of the 308 blocks; candidates sharing a member hit
counted once; 95% intervals by bootstrap over blocks):

| cut | this search | turboSETI |
|---|---|---|
| 5 | - | 0.26 (0.07-0.51) |
| 10 | 3.3 (1.3-6.2) | 0.29 (0.01-0.81) |
| 15 | 0.79 (0.39-1.36) | 0.28 (0.01-0.80) |
| 20 | 0.22 (0.11-0.36) | 0.15 (0-0.44) |
| 30 | 0.068 (0.023-0.133) | 0.049 (0-0.13) |
| 50 | 0.049 (0.013-0.097) | 0.013 (0-0.036) |
| 100 | 0.026 (0.003-0.058) | 0.010 (0-0.029) |

Almost all of them come from the crowded blocks: in the clean ones this
search keeps 0.13 a block at its cut of 10 and none from 20, turboSETI
none at any cut. Some blocks are far from typical: one gave this search
340 at the cut of 10 (a comb of interference switching between looks),
and one gave turboSETI 73. Other ways of counting one signal (frequency
and drift, frequency within 6 Hz, 100 Hz, 3 kHz, none) change these by up
to about a factor of two at the cut of 10 (3.3 a block, 1.5 merged
within 3 kHz) and hardly at all at 30. turboSETI's rate does not fall
at every step of the cut (0.26 at 5, 0.29 at 10): a higher cut removes OFF
hits as well as ON ones, and in block 129 looks 0, 3 and 4 hold about 300
hits at both cuts while looks 1, 2 and 5 fall from 521 to 66, so with (0,
3, 4) as ON the vetoes go and 72 events survive at 10 against 12 at 5. The
cut taken is therefore the lowest from which the rate stays under the
target at every higher cut tested. pickles kept 1.1 windows a block at
level 1 unmasked, 0.08 at level 2, 0.03 and 0.003 with its masks.

**At an estimated 0.1 false candidates a block, both pipelines need SNR 30** (this
search 0.068, turboSETI 0.049; each interval reaches about 0.13, and the
cut's own interval runs from 30 to 50 here, 5 to 50 for turboSETI).
There, of the 13,310 planted signals, in all three ON looks:

| drift (Hz/s) | this search, cut 30 | turboSETI, cut 30 | this search, cut 10 | turboSETI, cut 10 |
|---|---|---|---|---|
| 0-0.15 | 1514/2662 | 283/2662 | 2359/2662 | 811/2662 |
| 0.15-0.5 | 1225/2662 | 159/2662 | 2174/2662 | 599/2662 |
| 0.5-1 | 868/2662 | 0/2662 | 1909/2662 | 273/2662 |
| 1-2 | 594/2662 | 0/2662 | 1478/2662 | 26/2662 |
| 2-4 | 319/2662 | 0/2662 | 786/2662 | 0/2662 |
| **all** | **4520** | **442** | **8706** | **1709** |

At the matched cut, 7 signals turboSETI found were missed here, and 4,085
the other way. 80% are recovered from S_in 50 (near zero drift), 60, 120
and 200 (to 2 Hz/s) here, and from S_in 400 near zero drift for turboSETI
(above 0.15 Hz/s it never reaches 80%). No recovery was a false
association. The ratio of the counts (4,520 to 442, about ten) belongs to
this planted population (strengths spread evenly from S_in 10 to 400,
drifts to 4 Hz/s), not to the instruments: in strength, near zero drift
this search reaches 80% at a signal 8 times weaker (S_in 50 against 400),
and for strong signals there the two come close (238 and 210 of 242 at
S_in 400); at higher drifts turboSETI does not reach 80% at all, so no
ratio can be given there.

**The result does not hang on the rate chosen.** At every estimated rate
both reach in the cuts tested (0.026 to 0.26 a block), this search recovers
more on these blocks (the rates' own intervals are wide, so this is a
comparison at about matched rates, not at rates shown equal): at
its cut of 30 (0.068 a block) 4,520, more than turboSETI at its loosest
cut of 5 (3,128, at 0.26 a block); at 20 (0.22) 6,189 against 2,762 for
turboSETI at 6 (0.24); at 50 (0.049) 2,785 against 442 at 30 (0.049).
Below 0.026 a block only turboSETI was measured (203 at its cut of 50,
0.013 a block; none at 100), as this search's highest cut tested is 100. Most of the difference is at drifts above
0.5 Hz/s, where turboSETI's search smears the signal across channels and
its SNR falls (it finds none there at the matched cut), but this search
also recovers five times as many near zero drift.

**On another session (step 10, 14 November 2026): recovery held, the
false rate did not.** HIP17147, AGBT16A_999_192 (L band, 2016, the same
telescope), every choice fixed beforehand in config/step10.json, one logged
deviation (a query fix, comparable.md step 10); the page as generated is
docs/results/HIP17147-AGBT16A_999_192-step10.md. At SNR 30:

| | false a block (95%) | recovered in all three ON looks |
|---|---|---|
| this search | 39.1 (13.6-69.2) | 4,337 of 13,310 |
| turboSETI | 1.27 (0.27-2.8) | 417 of 13,310 |
| step 4, for comparison | 0.068 and 0.049 | 4,520 and 442 |

- **Recovery reproduced:** this search ahead of turboSETI with the
  intervals apart (paired, 3,925 by this search alone, 5 by turboSETI
  alone; difference +0.294, 0.284-0.304), close to step 4's figures. The
  curved pass held both its recovery criteria (2,769 against production's
  389 of 7,260 curved signals; none of production's lost).
- **The false rate failed, for both pipelines,** this search's by far the
  more: 39 a block against the limit of 0.1. The pass adds almost nothing
  to it (39.2 against 39.1) but fails with production. As fixed
  beforehand, this is the result; it is not mended by a new cut, rule or
  blocks. SNR 30 does not hold this search at 0.1 a block on this session,
  so the matched comparison of step 4 (both at 0.1) is not reproduced here.
- **Where the false candidates are** (described after the verdict, not a
  criterion; distinct candidates at SNR 30 by shared hits, as the rate
  counts them, before the full checks; `tools/false_frequencies.py`, by
  each candidate's own frequency): 3,888 of 3,938 lie inside one of check
  3's listed bands: Galileo E5b / BeiDou B2 1,249, GPS L5 / Galileo E5a
  952, GPS L1 and the other navigation systems' L1 830, Inmarsat and other
  mobile satellites 789, weather satellites 45, Iridium and Globalstar 20,
  GPS L2 2, aircraft at 1,090 MHz 1. Seven blocks hold 3,654. Of the other
  50, 2 are in blocks overlapping a band but outside it and 48 in blocks
  overlapping none: 46 in crowded blocks (27 crowded blocks: 1.7 a block,
  above 0.1 on their own), 2 in clean ones.
  - **Inside a listed band is not an identification.** It says a
    candidate is where navigation and mobile satellites transmit, not that
    it is one of them; none is identified here by its own behaviour yet.
  - **The block at 1,376-1,379 MHz** (block 119, 27 of the 48): 26 of its
    candidates lie between 1,378.42 and 1,378.63 MHz, each seeded from a
    single look's hit (look 0 or look 4, the other looks measured along the
    track), drifting -0.07 to -0.36 Hz/s; many hits a few kHz apart in one
    look at a time, a source that comes and goes between looks. It is near
    GPS L3 (1,381.05 MHz), outside the band list; unidentified.
  - So the cadence test alone does not reject what lies in these bands at
    L band, as it did the interference of step 4's S-band session; and the
    crowded blocks outside them are above 0.1 too.
- **Measured next, after the verdict and apart from it:** the full checks
  on step 10's own 121 blocks (`curved_pass.py vet --choice
  data/step10/choice.json`), with the store opened read-only and its
  content compared before and after: how many distinct false candidates
  they leave unexplained, how many planted signals survive them, and how
  much of the rejection rests on the band list rather than on evidence
  from the looks. Then the same checks on step 4's blocks again, with the
  same code and the store as it now is (two sessions), so the two
  sessions compare like for like. Whatever they show, step 10 failed its
  criterion: the frozen rate is the cadence test's output, and a later
  checks result is a separate, post-hoc measurement, never a substitute
  for it.
- **Measured (2026-11-15), post hoc, the verdict unchanged:** the checks
  on step 10's 121 blocks and on step 4's 121 again, the same code, the
  store opened read-only and unchanged by both runs. Production's row,
  distinct wrong-choice candidates kept by the cadence test and those the
  checks leave unexplained, and planted signals recovered and still kept
  after the checks. The planted signals here are the vetting run's own
  (`curved_pass.py vet`: straight and accelerating, planted afresh), not
  the 13,310 of steps 4 and 10's comparison, so these counts are not that
  comparison's (step 10's 4,337, for one):

  | Session | Cut | False kept | Unexplained: uniform / measured / store | Planted recovered | Kept after the full checks |
  |---|---|---|---|---|---|
  | HIP17147 (step 10, L band) | 10 | 10,836 | 86 / 65 / 8 | 6,174 | 4,076 (66%) |
  | HIP17147 | 30 | 3,938 | 13 / 14 / 0 | 3,729 | 2,456 (66%) |
  | KIC8462852 (step 4, S band) | 10 | 991 | 24 / 6 / 3 | 6,749 | 2,838 (42%) |
  | KIC8462852 | 30 | 21 | 3 / 0 / 0 | 4,078 | 1,735 (43%) |

  - The full checks reduce step 10's thousands of false candidates to 8
    at SNR 10 and none at SNR 30, as they do step 4's. This was not a
    criterion fixed beforehand, and it does not change step 10's result.
  - What they cost differs: on step 10's blocks a third of the recovered
    planted signals are rejected with them, on step 4's more than half.
  - **What each rejection rests on** (`vet-tables` now breaks it down from
    the records: a verdict "shown" by evidence from the looks or the
    store; else "indicated" by the band list alone, by it and other
    checks, or by other checks only; check 3, the band list, only ever
    indicates). Production, the full checks, SNR 30:

    | Session | | Unexplained | Shown | Band list alone | Band list and other checks | Other checks only |
    |---|---|---|---|---|---|---|
    | HIP17147 (L band) | false (3,938) | 0 | 39 | 21 | 3,835 | 43 |
    | | planted recovered (3,729) | 2,456 | 0 | 913 | 185 | 175 |
    | KIC8462852 (S band) | false (21) | 0 | 7 | 1 | 10 | 3 |
    | | planted recovered (4,078) | 1,735 | 0 | 1,685 | 490 | 168 |

    The false candidates do not rest on the band list: 21 of L band's
    3,938 are rejected by it alone, and every other one is also indicated
    or shown by another check, so without the list they would still be
    rejected. The planted signals do: of those the full checks reject,
    913 of 1,273 at L band and 1,685 of 2,343 at S band are rejected by
    the band list alone (they were planted there). So the zero
    unexplained is not built in by the list, but most of what the checks
    cost in planted signals is the list. At SNR 10 the same holds (L
    band: 320 of 10,836 false candidates rest on the list alone, 1,405 of
    2,098 planted losses). The other checks' share of planted losses (175
    and 168 at SNR 30, "other checks only") is the part to look into
    before the list's weight is changed; nothing is changed yet.
  - Step 4's blocks again: every figure the same as the first run, except
    that the full checks now reject 2 to 5 more planted signals a row
    (2,841 to 2,838 at SNR 10, 1,737 to 1,735 at SNR 30), the recurrence
    from the second session now in the store. The run took 12.7 hours of
    blocks against the first's 61.8 (check 8 looks hits up by index).
  - The pass adds 1 to 3 false candidates on step 4's blocks, none left
    unexplained by the full checks; on both sessions the pass's rows
    follow production's (data/logs/vet-step10-tables.log,
    vet-same-store-tables.log).
- **Not done: masking the bands.** Leaving the listed bands out would
  lower the rate by making a blind spot where the interference is worst,
  and a transmitter of interest could sit there too. Any change that
  rejects more must say what it rejects and which planted signals it
  loses, and the cadence test is not changed until it is known which
  evidence (shared drift families, recurrence, time structure, the track
  across looks) separates these signals from planted ones.
- **What it means for the claims:** "recovers about ten times as many
  planted signals as turboSETI at SNR 30" held on a second session. "At a
  matched false rate of 0.1 a block" did not: at L band, at SNR 30,
  neither pipeline reached it, and this search's cadence test passes far
  more satellite interference than turboSETI's. Both sessions are Green
  Bank's (comparable.md step 12).

What this does not show: it is one session at one telescope, and blocks
near each other share interference, so the intervals describe this sample
of blocks, not observations in general; the recovery intervals are for
signals, which within a block are not independent either. The cuts were
chosen on the same blocks they are judged on, so they may be optimistic
for another session; comparable.md step 10 tested them, fixed beforehand,
on one, and the false rate did not hold there (above). turboSETI's
three-look recovery uses its own hit tables at the cut (its event table
does not list every look), so which hits its events used is not
recorded. Two false candidates of this search that the checks left
unexplained (block 6, 1837.5101 MHz) and the 22 others it called unexplained are kept as
test cases for the checks, held out from fitting step 5's score (which
fits nothing); checked again with the store's evidence, none is
unexplained (below).

### Candidates ranked, and candidate sensitivity (11 November 2026)

`ranking.py` (comparable.md step 5; `check.py` ranks after every run, or
`check.py --rank`). **The score** is the sum, over what the checks measure,
of −log10 of the chance that a signal from the sky at a random place in
this session's band would show it by accident, each term capped at 4 (a
chance of 1e-4): the OFF looks' S/N along the track against 10,000 random
tracks in the five saved cadences' OFF looks (`ranking.py offnull`: median
3.6, 66 over the OFF level of 6); a listed band (their share of the band
searched, 0.44, so 0.35); drift under one step (2.6); check 6's recurrence
chance; check 7's look-alike chance where the drift is 0.1 Hz/s or more
(nearer zero the check's chance takes OFF hits' drifts as even, which they
are not, and the check itself calls those coincidence; with it, every real
candidate took the cap); check 8's share of random frequencies with a
relation; and the share of places in the band with as many hits within
0.5 MHz (check 9). The drift against the Earth's is not a term: a
transmitter at the target needs no particular drift. **Nothing is fitted:**
the terms are the checks' own chances and this session's measured shares,
the cap is fixed, and no candidate, planted or real, set any of it. Lower
is more worth a look; one shown to be interference ranks after every
other. **It is a heuristic ranking, not a probability:** the terms are of
different kinds (chances of coincidence, shares of the band, a place in a
random-track distribution) and not independent (a crowded place also
tends to have recurrences and relations), so the sum is neither a combined
chance nor a likelihood ratio, and says nothing of how likely a candidate
is to be a signal. Every ranked list keeps its calibration (the session
whose hits gave the shares, the OFF null's file and its digest, the cap,
the versions); scores from different calibrations are not compared.

The 11 candidates rank: first the three drifting ones at 2104.6 to 2106.5
MHz (0.07 to 0.09 Hz/s, in the space-uplink band; scores 3.4 to 4.3), then
the zero-drift and crowded ones (5.4 to 7.7), the two shown by recurrence
last.

**Birdies** (`ranking.py birdies`): 1,400 signals planted in the ON looks of
the five saved cadences (S_in 15 to 120, drifts to 4 Hz/s; 35 a run, 8 runs
a cadence), searched and judged, every candidate they made put through the
checks with the store's evidence exactly as the sweep's candidates are
(`check.vet_from_store`), scored and ranked against the 11. 1,057 were
kept. **Uncovered at N = 10** (within the first ten of the real candidates
and itself) every kept one was; **at N = 1** (ahead of every real candidate,
the bar for a survey of many cadences):

| drift (Hz/s) | outside the listed bands | inside the listed bands |
|---|---|---|
| 0 to 0.15 | 110/110 (97-100%) | 154/167 (87-95%) |
| 0.15 to 0.5 | 97/97 (96-100%) | 148/149 (96-100%) |
| 0.5 to 1 | 84/85 (94-100%) | 124/125 (96-100%) |
| 1 to 2 | 71/71 (95-100%) | 99/101 (93-100%) |
| 2 to 4 | 61/61 (94-100%) | 89/91 (92-99%) |

So against this sweep's candidates, candidate sensitivity is detection
sensitivity: 80% are uncovered from the same S_in as are kept (15 near
zero drift, 20, 30, 45 and 45 to 4 Hz/s), outside the bands and in. The
loss is in the bands near zero drift, where 13 of 167 fall behind the
first real candidate (a drift under one step, or look-alikes at 0.1 to
0.15 Hz/s), whatever their strength: the per-strength table puts that
cell's 80% at S_in 90 only because one cell, 19 of 24 at S_in 60, falls
just under it.

**That is a low bar, and the held-out candidates show it.** Every one of
the sweep's 11 carries marked interference, so beating them is easy. The
24 candidates that step 4's wrong choices of ON looks made and its checks
left unexplained (held out from everything above) were read again
(`ranking.py heldout`; all 24 found again) and checked with the store's
evidence. **None is unexplained now:** 6 are shown to be interference
(recurrence), 18 likely interference (recurrence and crowding). In step
4's run the checks had only the cadence's own hits (no recurrence, no
session-wide crowding); with the store's evidence they mark all 24. That
is the checks' doing, with more evidence, not the ranking's: the ranking
only orders what the checks found. **But
the score does not put all of them behind the planted signals.** Four, in
block 14 (1861.56 to 1861.58 MHz, crowding their only mark), score 1.07 to
4.05, the best three ahead of every real candidate; 1.07 is ahead of 44% of
the kept birdies (21% of those outside the bands, 60% of those inside). A
survey with interference like it would show a person such things before
many real signals. Their one mark, crowding, adds little to the score,
because crowded places are common in this session (the term is the share
of places as crowded): the score uses the measured occupancy only through
that share, and step 6 replaces it with the occupancy by frequency and
drift.

**How much the ranking leans on each term** (`ranking.py tables`, each
term set to 0 for every candidate in turn, nothing refitted):

| taken out | kept birdies ahead of every real candidate | best held-out candidate ahead of (of kept birdies) | held-out ahead of every real |
|---|---|---|---|
| nothing | 1037/1057 | 44% | 3 |
| OFF S/N | 997 | 32% | 2 |
| band | 1035 | 29% | 3 |
| zero drift | 1040 | 43% | 3 |
| recurrence | 1037 | 34% | 12 |
| look-alikes | 1045 | 44% | 3 |
| relations | 1036 | 44% | 3 |
| crowding | 981 | 94% | 3 |

No one term carries the planted signals (981 to 1,045 stay first whatever
is taken out). Two carry the interference down: without crowding the best
held-out candidate would be ahead of 94% of the planted signals, and
without recurrence 12 of the 24 would be ahead of every real candidate.
Taking out the OFF term or the band lowers the best held-out candidate's
place (to 32% and 29%): those terms count against planted signals more
than against it, so the ranking is not monotone in evidence, as a
heuristic sum need not be.

What this does not show: the birdies are in five blocks of one session,
the real candidates are one cadence's eleven, and the held-out ones are
24 from one session's wrong cadences; across a survey a person looks at
the first few of thousands, and that is measured at the survey's scale
(docs/multiuser.md, "Ranking across a survey").

### The measured occupancy, and the ranking again (checks version 4, 11 November 2026)

comparable.md step 6. `occupancy.py` measures the session's interference
from its own 645,399 hits (at the cut and shadow hits) and two checks take
their chances from it instead of a uniform background:

- **Crowding (check 9) by frequency and drift:** the hits within 0.5 MHz
  whose drift is like the candidate's (within 2 drift steps or 10%), its
  own 5 kHz left out, against the same count at every one of 90,244 places
  of the band searched, for that drift. The chance is the share of places
  as crowded; under 5% is "indicated" (before: 10 times the band's median
  per MHz, whatever the drift). Shadow hits count: weak members of a
  family are evidence too. A place in a block cut short at the hit limit
  is marked, its count a lower bound.
- **Look-alikes (check 7) by drift:** the share of the session's other 307
  blocks whose OFF looks hold as many hits at the cut with the same drift
  over frequency. Measured, it holds near zero drift too, where the old
  chance (OFF hits' drifts taken as even over ±4 Hz/s) gave every real
  candidate the cap and was not used.

Recurrence (check 6) already took its chance from each file's hits near
the candidate with the drift share measured, and harmonics (check 8) from
random frequencies against the session's hits; neither changed. Every
chance is at least one over the places or blocks compared, and the ranking
caps each term at 4. The places are not independent (neighbouring places
share hits), so a share near its floor is no finer than the band's
structure allows.

**The candidates, checked again** (`check.py --all`): all 11 keep their
verdicts (2 shown, 9 likely interference); look-alikes are now indicated
for every one but the two shown, as their blocks hold more OFF look-alikes
at their drifts than nearly every other block, and crowding at their drift
is unusual (0.2 to 2% of places). Their scores rise from 3.4 to 7.7 to 7.0
to 9.7, the order changing a little.

**Does it tell interference from signals better?** The same 1,400 birdies
(the same seed, so the same plantings, searched again) and the held-out
24, checked and scored under version 4 (ranking version 2), against
version 1:

| | version 1 (uniform) | version 2 (measured) |
|---|---|---|
| kept birdies ranked ahead of every real candidate | 1037 of 1057 | 1057 of 1057 |
| kept birdies' scores (10%, median, 90%) | 0.17, 0.99, 1.94 | 0.41, 1.14, 2.30 |
| kept birdies marked likely interference by the checks | 663 | 664 |
| the best-scoring held-out candidate is ahead of | 44% of kept birdies | 15% |
| held-out candidates ahead of every real candidate | 3 | 11 |
| held-out candidates the checks leave unexplained | 0 | 3 |

**It separates the held-out interference from the planted signals better**
(the worst held-out case ahead of 15% of them instead of 44%), and the
planted signals' scores and verdicts hardly change, so the gain is from
marking the interference more, not from favouring the plantings. Nothing
was set from the held-out set: the occupancy's definitions were written
before it was scored, and nothing was changed after.

**But two things go the other way, and both are kept as found.** Three
held-out candidates in block 14 (1861.56 to 1861.58 MHz, drift −0.02 Hz/s)
are unexplained again: by drift, their place is as crowded as 8% of the
band's places, so crowding no longer marks them (it did under the old
rule, 10 times the median); their scores still put them behind 85% or
more of the kept birdies. What they are: one family, all three at drift
−0.0204 Hz/s within 14 kHz of each other, each in a choice that takes look
1 (an OFF look of the true cadence) as an ON look, so interference by the
true cadence. A check for several candidates of the same drift within a
few kHz would mark them; it is not added, since it would be written from
the held-out cases themselves. And the real candidates now score higher than
almost every held-out one (11 held-out ahead of every real candidate),
because their own crowding and look-alikes are measured to be unusual: the
11 real candidates are a weaker bar than ever.

**How much it leans on each term** (each taken out in turn):

| taken out | kept birdies ahead of every real | best held-out ahead of | held-out ahead of every real |
|---|---|---|---|
| nothing | 1057 | 15% | 11 |
| OFF S/N | 1057 | 9% | 8 |
| band | 1057 | 11% | 10 |
| zero drift | 1057 | 13% | 4 |
| recurrence | 1057 | 29% | 17 |
| look-alikes | 1054 | 47% | 5 |
| relations | 1057 | 15% | 11 |
| crowding | 1055 | 37% | 5 |

Look-alikes, measured, now carry most of the separation (without them the
worst held-out case is ahead of 47%), then crowding and recurrence. Still
a heuristic: no term is a calibrated probability, and the sum is not one.

### Curved tracks: does a changing drift defeat the search? (11 November 2026)

comparable.md step 9's first test. A signal's drift changes when its
transmitter or the telescope accelerates unevenly: frequency f(t) = f0 +
d t + a t²/2, a in Hz/s². Every narrowband search here (this one,
turboSETI, BLISS, hyperseti) fits straight lines.

**Has it been done?** Linear drift is the standard model, with the maximum
drift chosen from physics (Sheikh et al. 2019, ApJ 884, 14,
arXiv:1910.01148: up to 200 nHz; Li et al. 2023, AJ 166, 182,
arXiv:2311.01427: 99% of known exoplanets within ±53 nHz, ±0.44 nHz for a
bias-reduced population). A 2026 FAST pipeline (arXiv:2605.23739) argues
curvature is negligible within a single integration of tens of seconds. No
search fitting curved tracks across a cadence was found in what was looked
at (not an exhaustive review); `blc1` drifted along curves over hours and
was interference, so a curve is no sign of where a signal comes from.

**How much curvature is physical** (at 2.2 GHz, f/c = 7.3 s/m): the
Earth's spin at Green Bank gives up to 1.4×10⁻⁵ Hz/s² (f ω³ R cos φ / c),
in every sky signal. A transmitter on a planet in a circular orbit with
line-of-sight speed K has drift amplitude D = f K ω / c and curvature up
to D ω; where its drift passes through this search's ±4 Hz/s, the
curvature is about D ω. So: an Earth-like spin, 1.4×10⁻⁵; any orbit whose
whole drift stays within ±4 Hz/s, at most 4ω (2.9×10⁻⁵ for a 10-day
orbit, 9.7×10⁻⁵ for 3 days, 2.9×10⁻⁴ for 1 day); a hot Jupiter (3 days,
130 km/s), about 5.6×10⁻⁴; a 1-day orbit at 200 km/s, about 7.7×10⁻³; a
transmitter on the equator of a Jupiter-sized planet spinning in 10 hours,
about 2.8×10⁻³. Within one 292 s look a curve leaves its best straight line
by a T²/12: 0.7 Hz at 10⁻⁴, 7 Hz at 10⁻³, 21 Hz at 3×10⁻³ (the channel is
2.79 Hz). Across the cadence, 22 minutes from the first ON look to the
last, it moves its drift by a × 1,320 s: 0.13 Hz/s at 10⁻⁴.

**A correction (11 November 2026, evening).** The first version of the
measurements below counted a planted signal as lost when the first event
holding one of its hits was not a candidate. A curved track at slow drift
often comes out as several events, one a look (the drifts no longer agree,
so the cadence test does not join them), and one of those is usually a
candidate on its own (its straight track measured in the other ON looks
clears S/N 5): what a person would see. Checked on one saved cadence at
10⁻⁴: 34 of 35 such signals had a candidate among their events, the first
event of most was "unconfirmed". `injection.trial` now also says whether
any event holding a signal's hits is a candidate (`any_candidate`; its
`label` is unchanged, and nothing else that uses it changes), the three
measurements were run again with the same seeds (the same plantings), and
the first versions are kept (data/measurements/*-v1.json). **The first
version overstated the loss**: it put the start of the loss at 2 to 3×10⁻⁵
Hz/s² for slow drifts (twice the Earth's own curvature) and had turboSETI
keeping, at 10⁻⁴, signals this search lost. Neither holds.

**Measured** (`measure.py curvature`; signals planted at S_in 60, where
straight tracks are kept at every drift, in the five saved cadences, 100
at each |a|, both signs, drifts to 4 Hz/s; the acceleration held over the
whole cadence). "Kept" is any event holding its hits a candidate; the first
version's count in brackets:

| a (Hz/s²) | kept as candidates | drifts under 0.5 Hz/s | not found by a hit in every ON look | found in every ON look, not kept |
|---|---|---|---|---|
| 0 | 100/100 (100) | 30/30 | 2 | 0 |
| 1×10⁻⁵ | 100/100 (99) | 51/51 | 3 | 0 |
| 1×10⁻⁴ | 97/100 (41) | 45/48 | 4 | 3 |
| 3×10⁻⁴ | 49/100 (5) | 1/36 | 10 | 47 |
| 1×10⁻³ | 1/100 (0) | 0/33 | 42 | 58 |
| 3×10⁻³ | 0/100 | 0/36 | 96 | 4 |
| 1×10⁻² | 0/100 | 0/46 | 100 | 0 |

And between 10⁻⁵ and 10⁻⁴ (`measure.py curvature-fine`, 100 at each |a|):
100/100 kept at 1, 2 and 3×10⁻⁵ (the first version: 100, 98, 86), 93 at 5
and at 7×10⁻⁵ (70, 54), the few lost all at drifts under 0.5 Hz/s.

**So at S_in 60 the cadence test starts to lose signals from about 5×10⁻⁵
Hz/s² and loses half at 3×10⁻⁴; the search itself loses the hits from
about 10⁻³.** The cadence test joins hits across looks only if their
drifts agree within 2 drift steps and 5% (onoff.py `_tolerance`); a curved
signal's looks then make separate events, each judged on its own, and one
is still a candidate while its straight track in the other ON looks stays
within the track's tolerance and S/N 5. At 3×10⁻⁴ the track has moved 65
Hz (23 channels) off the line in the next ON look, and only fast drifts
(where 5% of the drift is wide enough) keep it. The Earth's own curvature
(up to 1.4×10⁻⁵, in every sky signal) is well below the loss. "Kept" here
is a candidate raised at the signal; by step 4's three-look standard (every
ON look on the signal's own track) far fewer are kept at 10⁻⁴: see the
second pass below (12 November).

**turboSETI on the same curved tracks** (`curved.py turboseti`; S_in 400
and drifts under 0.5 Hz/s, where turboSETI keeps straight signals; its hit
search and event stage as step 4 runs them; 40 at each |a|; its three-look
rule checked from its own hit tables):

| a (Hz/s²) | this search | turboSETI |
|---|---|---|
| 0 | 39/40 | 40/40 |
| 1×10⁻⁵ | 40/40 | 39/40 |
| 1×10⁻⁴ | 40/40 (first version 0) | 26/40 |
| 3×10⁻⁴ | 4/40 (0) | 9/40 |
| 1×10⁻³ and more | 0 | 0 |

turboSETI's event stage follows a hit into the next ON look within ± the
drift times twice the look's length and never asks the drifts to agree
(`find_event.follow_event`). At 10⁻⁴ this search raises more candidates
(but turboSETI's count asks a hit in each ON look and ours does not; on
the three-look standard, on the same signals, the two are level at S_in
400 and production keeps more below it: see the orbital section below); at 3×10⁻⁴
turboSETI keeps a few more (9 to 4 of 40); above 10⁻³ both lose
everything, in the search.

**A cadence test for curved tracks, first version** (`curved.py study`,
experimental and kept apart: nothing in the search or the store uses it).
It joins a hit in the first ON look to one in the last under a constant
acceleration up to a_max, needs the middle ON look on the curve (a hit or
S/N 5), and measures the OFF looks along the curve. Run with a_max = 0 too,
the same code as a straight-line test. Same plantings as above (S_in 60, 50
at each |a|), and its false candidates with the 19 wrong choices of ON
looks on ten blocks of the sweep read again (eight crowded ones with many
wrong-choice candidates in step 4, two clean). Its production column is
the first version's count (first event only) and is not run again: the
second pass below replaces this study.

| a (Hz/s²) | production (first event) | curved test, a_max 0 | a_max 10⁻⁴ | a_max 10⁻³ | a_max 10⁻² |
|---|---|---|---|---|---|
| 0 | 50/50 | 49 | 50 | 50 | 50 |
| 1×10⁻⁵ | 49/50 | 43 | 47 | 47 | 47 |
| 1×10⁻⁴ | 15/50 | 6 | 46 | 46 | 46 |
| 3×10⁻⁴ | 0/50 | 0 | 0 | 45 | 45 |
| 1×10⁻³ | 0/50 | 0 | 0 | 26 | 25 |
| 3×10⁻³ and more | 0 | 0 | 0 | 0 | 0-1 |
| **false candidates, 190 wrong cadences** | | **8** | **14** | **21** | **21** |

On its own, in place of the straight test, it costs false candidates (8 to
21 in these 190 wrong cadences, from a_max 10⁻³); the ten blocks were
chosen for their many wrong-choice candidates, so these are not survey
rates.

### Curved tracks: a second pass over step 4's blocks, at matched rates (11 November 2026)

`curved_pass.py`, experimental and kept apart (nothing in the search, the
cadence test or the store uses it). **The production test runs first,
unchanged; the second pass looks only at what it left unsettled**: hits at
the cut that are no member of a production candidate or of a production
interference event (an OFF veto along the straight track stands). From any
two ON looks with such hits (not only the first and last), it joins a pair
whose drifts differ by what a constant acceleration |a| ≤ a_max allows and
whose frequencies agree with that curve, needs the third ON look on the
curve (a hit, or the track at S/N 5), and measures the OFF looks along the
curve and where the first hit was (any hit there, of any strength, or S/N
6 is interference). What it keeps is added to the production candidates.

On all 121 of step 4's blocks (61 crowded, 60 clean; the same blocks, read
again from the archive), each searched once:

- **false candidates:** every hit of every one of the 19 wrong choices of
  ON looks goes through production and the pass (not only planted
  signals), at each of step 4's cuts; distinct signals per block by shared
  member hits, blocks the unit, weighted by class, bootstrap intervals
  (step 4's rules, `matched_tables`);
- **recovery:** 120 signals a block planted in the true ON looks (S_in 30,
  60, 120 and 400; the five drift bins; |a| 0, 10⁻⁵, 3×10⁻⁵, 10⁻⁴, 3×10⁻⁴,
  10⁻³, signs at random), 605 in each strength and |a|. Recovered: a kept
  candidate whose every ON member hit is on the signal's track in its look
  (frequency within 6 Hz + |a| T²/12 of the best line's start, drift within
  0.05 Hz/s of its slope at mid-look); none matched what the unplanted
  block already held. That is the strict test; step 4's three-look
  standard, which also checks the ON looks without a member hit, follows
  the first table and is the one to quote.

**False candidates a block** (95% interval):

| cut | production | + pass, a_max 10⁻⁴ | 3×10⁻⁴ | 10⁻³ |
|---|---|---|---|---|
| 10 | 3.30 (1.32-6.17) | 3.30 | 3.30 | 3.31 |
| 20 | 0.221 (0.110-0.357) | 0.221 | 0.221 | 0.224 |
| 30 | 0.068 (0.023-0.133) | 0.068 | 0.068 | 0.071 (0.026-0.130) |
| 50 | 0.049 | 0.049 | 0.049 | 0.049 |

Every configuration is matched at 0.1 a block at the same cut, 30, and the
pass's cost there is one false candidate in 121 blocks (in a crowded one)
at a_max 10⁻³ and none below. Most of what the pass joins in the wrong
choices already carries an OFF veto or is part of a production event; it
adds distinct wrong-choice candidates mainly at the lowest cut: 8, 15 and
20 at cut 8 (by a_max) to production's 1,836 over the 121 blocks, 1 to 3
at cut 10 to its 991.

**Recovered at the matched cut (30)**, of 605 each (95% interval):

| \|a\| (Hz/s²) | S_in | production | + pass, a_max 3×10⁻⁴ | + pass, a_max 10⁻³ |
|---|---|---|---|---|
| 0 to 3×10⁻⁵ | 120 / 400 | 79-82% / 90-91% | the same | the same |
| 10⁻⁴ | 60 | 31% | 33% | 33% |
| 10⁻⁴ | 120 | 79% | 80% | 80% |
| 10⁻⁴ | 400 | 96% | 96% | 96% |
| 3×10⁻⁴ | 60 | 0% | 25% | 26% |
| 3×10⁻⁴ | 120 | 32% (28-36) | 78% (75-81) | 78% |
| 3×10⁻⁴ | 400 | 54% (50-58) | 97% (95-98) | 97% |
| 10⁻³ | 120 | 0% | 0% | 59% (55-63) |
| 10⁻³ | 400 | 8% (6-10) | 8% | 86% (83-88) |

In all, 5,567 of the 14,520 planted signals with production, 7,119 with
the pass at a_max 10⁻³ (+28%); straight and nearly straight signals are
the same either way. S_in 30 is not recovered at cut 30 by any (its S/N is
under the cut); at the published cut, 10, the pass gives the same kind of
gain (at 10⁻³: 0-8% to 23-86% by strength).

**The same signals by step 4's three-look standard (12 November 2026).**
The test above (strict) asks only that an event's *formal* member hits lie
on the signal's track. An event with one member hit passes it, though its
other ON looks (where the cadence test measured a track, not a hit) are
never compared with the signal; and the pass's candidates did not record
the track it measured in the third ON look. Step 4's main standard
(`matched.RECOVERY`, three looks) needs every one of the three ON looks on
the signal: its member hit, or, where it has none at the cut, the track
measured there. The pass now records that track, and `curved_pass.py
recheck` judged the true choice of all 121 blocks again with the same seeds
(the same plantings; every strict status came out as recorded, so nothing
else moved; the false-candidate counts do not depend on how recovery is
tested and stand). The first table is kept as above and
data/measurements/curved-pass-v1.json.

**Recovered at the matched cut (30), three looks**, of 605 each (95%
interval):

| \|a\| (Hz/s²) | S_in | production | + pass, a_max 3×10⁻⁴ | + pass, a_max 10⁻³ |
|---|---|---|---|---|
| 0 to 3×10⁻⁵ | 120 / 400 | 71-76% / 88-91% | 72-76% / 89-91% | the same |
| 10⁻⁴ | 60 | 3% (2-5) | 29% (25-33) | 29% |
| 10⁻⁴ | 120 | 29% (26-33) | 65% (61-69) | 65% |
| 10⁻⁴ | 400 | 44% (40-48) | 78% (75-81) | 78% |
| 3×10⁻⁴ | 60 | 0% | 25% (22-29) | 26% (23-30) |
| 3×10⁻⁴ | 120 | 0% | 69% (65-73) | 70% (66-73) |
| 3×10⁻⁴ | 400 | 2% (1-3) | 82% (79-85) | 82% (79-85) |
| 10⁻³ | 120 | 0% | 0% | 55% (51-59) |
| 10⁻³ | 400 | 0% | 0% | 81% (78-84) |

In all, 4,078 of the 14,520 with production (strict: 5,567), 5,723 with the
pass at a_max 3×10⁻⁴, 6,557 at 10⁻³ (strict: 7,119): **+61% by three
looks, against +28% strict** (28.1% to 45.2% of this planted set, half
of it curved by 10⁻⁴ or more: a gain in recovering these signals, not in
the telescope's sensitivity). No planted signal was a false association
(matched by what the unplanted block already held) in any configuration,
at either cut, by either test: every denominator is the 14,520. At the published cut, 10: 6,749 to 11,002.
How many of the three ON looks the recovering event holds by a formal hit
(1 / 2 / 3), at the matched cut: production 447 / 966 / 2,665; with the
pass at 10⁻³ 304 / 2,532 / 3,721. At 3×10⁻⁴ and 10⁻³ every signal the pass
recovers is held by two or three formal hits (two at the least is how the
pass joins), the third ON look a hit or its track measured on the curve.

**So the second pass's gain survives step 4's standard, and production's
own recovery of curved signals was overstated by the strict test**: at
10⁻⁴, production's candidate at a curved signal is often one look's hit
with straight tracks measured in the other ON looks, at S/N 5 but off the
signal's own track (at 10⁻⁴ its drift has moved about 0.07 Hz/s between
ON looks, past the 0.05 Hz/s tolerance), so the cadence is not verified
along the signal. By three looks production keeps 29-44% at 10⁻⁴ (S_in 120
and 400; 39-44% at cut 10 for S_in 60 to 400), the pass 65-78%; straight and nearly straight
(to 3×10⁻⁵) signals are within a point of each other. This bears on the
curvature measurements above, which count any candidate event holding a
signal's hits (a candidate is raised at the signal; whether its three ON
looks lie on the signal is not asked there): their 97/100 at 10⁻⁴ is
candidates raised, not cadences verified along the track, and the
comparison with turboSETI at 10⁻⁴ (whose count asked its hits in each ON
look) is not like for like on this standard (settled below, "orbital
paths": on the same signals turboSETI does not keep what production loses
at 10⁻⁴). The loss
does not start at 2-3×10⁻⁵ either way (three looks: 81-84% at 0 to 3×10⁻⁵,
S_in 60, cut 10).

**What this shows and does not.** At step 4's matched false-candidate rate,
on its 121 blocks and by its three-look standard, the second pass recovers
signals accelerating at 10⁻⁴ to 10⁻³ Hz/s² that the production test loses
(up to the search's own limit for weak ones). Its cost in false candidates
on these blocks is one in 121 (0.068 to 0.071 a block, the intervals
overlapping almost wholly): too few to measure here, not shown to be
negligible in other sessions. Below 10⁻⁴ it changes nothing. Not shown: the
acceleration is held constant over 22 minutes (for a circular orbit it
changes at the orbital rate, by at most 10% over the cadence for a 1-day
orbit and 1% for 10 days, but 23% for a 10-hour spin); one session and one
target's blocks; the checks (vetting.py) are not run on what the pass
adds; and the planted signals are placed where the block's own hits are
not, as in step 4. **The production cadence test is not changed on this.**
What would justify a change: the same result on another session (step
10's blocks), the checks run on the pass's candidates, and orbital
(sinusoidal) tracks planted as well as constant accelerations.

### Curved tracks: orbital paths, and the checks on what the pass adds (12 November 2026)

Two measurements, both on step 4's 121 blocks with the second pass
unchanged, their parameters fixed before they ran (`curved_pass.py orbits`,
`vet`; `selftest` checks the pieces they rest on).

**Orbital paths.** A constant acceleration over 22 minutes is the simplest
curve. Here each planted signal has a line-of-sight acceleration a_pk
cos(ωt − φ), so its acceleration and its jerk change over the cadence, with
the Earth's own turning and orbit toward the target at Green Bank added
(`vetting.expected_drift`, beyond the drift it has at the cadence's start).
Peaks 10⁻⁴, 3×10⁻⁴ and 10⁻³ Hz/s²; periods 10 hours, 1 day and 10 days;
the phase at random; S_in 60, 120 and 400 (S_in 30 is under the matched
cut); five drift bins; and a control with no orbit, the Earth's motion
alone. 150 signals a block, seed 62.

What the cases are physically: the line-of-sight acceleration is a_pk c/f.
At 2 GHz, 10⁻⁴ Hz/s² is 0.015 m/s² and 10⁻³ is 0.15 m/s², against the
Earth's turning at Green Bank, up to 0.025 m/s². For a circular orbit
seen edge-on, a = vω: at 10⁻³ a 1-day orbit is a line-of-sight speed of
2.1 km/s and a 10-day orbit 21 km/s. A 10-hour period at 10⁻³ is 0.86 km/s,
more a fast-turning body (a transmitter on a planet turning in 10 hours at
twice Jupiter's equatorial speed) than an orbit. These cases are a grid
over the range where the pass's bound matters. They are not a sample of
real planetary systems: inclination folds into a_pk, and nothing here
weights them by how common they are.

Recovery is by three looks, against the best straight line fitted to the
path in each look, the frequency tolerance 6 Hz plus the path's largest
departure from that line (up to 7.4 Hz more at 10⁻³). Two controls on that
matching: "tight", the same with 6 Hz only, and "mirror", each signal
scored against the path it would have with its phase turned half a cycle
(the opposite curvature and jerk). A recovery against the mirror path means
the matching is too loose, not that the signal was found. False
associations are counted in each cell.

**The checks on what the pass adds.** In three ways, on production's
candidates and the pass's alike:

- "uniform", as step 4 ran the checks on its wrong-choice candidates
  (`measure.vet_hook`: the cadence's own hits, no recurrence, the uniform
  chances), kept to compare with step 4's held-out figures. These are
  partial checks.
- "measured": the same with the session's measured occupancy (checks 7 and
  9). Also partial.
- "store": the full checks a sweep's candidate gets
  (`check.vet_from_store`). These are recurrence from the store's hits in
  every file outside the choice's ON looks, check 6's background from
  them, the session's 72,555 hits at the cut for checks 8 and 9, its
  measured occupancy, and its own target. The store holds this one
  session's six files and no other session, so "recurrence elsewhere" is,
  for now, the cadence's other looks over the whole band (at the sweep's
  cut and its shadow hits). Another session's sweep adds to it.

At cuts 10 and 30 these run on every wrong-choice candidate, and on the
candidates that recover a planted signal (the same plantings as above, seed
61). That measures what the checks remove from the false candidates and
what they cost real curved signals.

A pass candidate is kept whole: its reference look and epoch, frequency,
drift, acceleration, and each look's measured values (hit, track on the
curve, or OFF S/N, each OFF look marked measured or not, and its OFF
evidence taken from those values). The checks themselves are written for a
straight track and read one frequency and one drift; check by check:

| check | what it reads | for a curved candidate |
|---|---|---|
| 1 data sanity | stamps, completeness | no stamps cut for a pass candidate; rests on the looks being complete (marked) |
| 2 OFF looks | each OFF look's S/N | measured along the curve and where the first hit was |
| 3 bands, 8 harmonics | frequency | unaffected |
| 5 the Earth's drift | drift | reports only |
| 4 zero drift, 7 look-alikes, 9 crowding | the reference drift | could depend on the reference look |
| 6 recurrence | frequency, drift extrapolated in a line | a curved signal's recurrence in the other looks can be missed (10⁻³ Hz/s² is 700 Hz off the line 20 minutes on); that leaves more of the pass's candidates unexplained, not fewer, and those looks are the ones the pass measured along the curve |

So each pass candidate is also checked with each of its member looks as
the reference, and the tables say how often the verdict changes.

`selftest`:
- the orbital paths agree with a separate double integration of the
  acceleration (the orbit's plus the Earth's, from expected_drift on its
  own grid) to under 10⁻⁴ Hz over the cadence;
- a planted orbital track's centre is within 0.1 channel of its path in
  every spectrum;
- the adapter tells apart an OFF look measured under the threshold, one
  that could not be measured, and one at it;
- the tolerance is 6 Hz for a straight signal, and 6 Hz plus about
  aT²/12 for a curved one.

**Orbital paths, measured** (all 121 blocks, 18,150 signals, 14.5 hours;
`data/measurements/curved-orbits.json`). Recovered by three looks, each
cell 1,815 signals (the three periods together; 605 for no orbit); no false
association in any cell, at either cut, for any configuration:

| a_pk (Hz/s²) | S_in | cut 30: production | + pass 10⁻⁴ | 3×10⁻⁴ | 10⁻³ | cut 10: production | + pass 10⁻³ |
|---|---|---|---|---|---|---|---|
| none (the Earth's alone) | 60 / 120 / 400 | 36% / 75% / 90% | the same | the same | the same | 85% / 89% / 90% | the same |
| 10⁻⁴ | 60 | 19% | 30% | 31% | 31% | 62% | 79% |
| 10⁻⁴ | 120 | 54% | 70% | 70% | 70% | 69% | 84% |
| 10⁻⁴ | 400 | 70% | 84% | 84% | 84% | 70% | 84% |
| 3×10⁻⁴ | 60 | 6% | 8% | 27% | 27% | 21% | 80% |
| 3×10⁻⁴ | 120 | 15% | 20% | 68% | 68% | 22% | 82% |
| 3×10⁻⁴ | 400 | 23% | 27% | 81% | 81% | 23% | 81% |
| 10⁻³ | 60 | 2% | 2% | 5% | 6% | 6% | 72% |
| 10⁻³ | 120 | 4% | 5% | 13% | 60% | 5% | 77% |
| 10⁻³ | 400 | 5% | 6% | 14% | 77% | 5% | 77% |

Of the 16,335 orbital signals, at cut 30: production 3,607, the pass 4,571,
7,108 and 9,118 (a_max 10⁻⁴, 3×10⁻⁴, 10⁻³); at cut 10, 5,145 and 12,978
at 10⁻³. What this says:

- **The constant-acceleration result carries over to orbits.** An orbit's
  acceleration over the cadence is a_pk cos φ, up to the peak, so
  production keeps more of these than of signals held at the peak (15%
  against 0% at 3×10⁻⁴, S_in 120), and the pass recovers about what it
  did at a constant acceleration (68% against 69-70%).
- **The period matters only at 10⁻³ and 10 hours**, where the acceleration
  changes most within the cadence: the pass recovers 51% at S_in 120
  against 63-65% for 1 and 10 days. Elsewhere the three periods are within
  a few points of each other.
- **The tolerance is not what recovers them.** With 6 Hz only ("tight"),
  the pass at 10⁻³ keeps 53% at S_in 120 and 69% at 400 (against 60% and
  77%), and at 10⁻⁴ and 3×10⁻⁴ it loses one or two points. The widened
  tolerance adds the signals whose path bends by more than 6 Hz from its
  best straight line in some look, which is what it is for.
- **The matching is not loose.** Against the mirror path, 114 of the
  16,335 recover at cut 30 (0.7%), the same 114 under every configuration,
  most at 10⁻⁴ and none above 2 in a cell at 10⁻³. These are signals whose
  phase leaves them nearly straight over the cadence, so that their mirror
  path is nearly the same path.
- **No orbit:** the Earth's motion alone curves a track here by about
  5×10⁻⁶ Hz/s², and production and the pass recover the same signals.

The pass's orbital recoveries, by formal hits at cut 30: 466 by one,
4,978 by two and 3,674 by three; production's 1,120 / 1,340 / 1,147.

**The checks on what the pass adds, measured** (all 121 blocks, 61.8 hours
of worker time, 6 workers; `data/measurements/curved-pass-vetting.json`).
Wrong-choice candidates are distinct signals by shared member hits;
"left" is what the checks leave unexplained. Planted signals are those
recovered by three looks, and "left" is how many of them survive the checks
(a real signal should):

| cut, checks | wrong choices kept / left: production | pass 10⁻³ | planted recovered / left: production | pass 10⁻⁴ | 3×10⁻⁴ | 10⁻³ |
|---|---|---|---|---|---|---|
| 30, uniform | 21 / 3 | 22 / 3 | 4,078 / 1,779 | 4,662 / 2,005 | 5,723 / 2,435 | 6,555 / 2,792 |
| 30, measured | 21 / 0 | 22 / 0 | 4,078 / 1,758 | 4,662 / 1,978 | 5,723 / 2,395 | 6,555 / 2,754 |
| 30, store | 21 / 0 | 22 / 0 | 4,078 / 1,737 | 4,662 / 1,967 | 5,723 / 2,381 | 6,555 / 2,745 |
| 10, uniform | 991 / 24 | 994 / 24 | 6,749 / 2,997 | 7,646 / 3,367 | 9,469 / 4,135 | 10,998 / 4,825 |
| 10, measured | 991 / 6 | 994 / 6 | 6,749 / 2,930 | 7,646 / 3,282 | 9,469 / 4,024 | 10,998 / 4,702 |
| 10, store | 991 / 3 | 994 / 3 | 6,749 / 2,841 | 7,646 / 3,190 | 9,469 / 3,914 | 10,998 / 4,573 |

(The pass at 10⁻⁴ and 3×10⁻⁴ keeps 992 wrong choices at cut 10 and 21 at
cut 30, with the same number left.) What this says:

- **The pass adds no unexplained false candidate.** Across the 121 blocks
  it keeps 3 more wrong-choice signals than production at cut 10 and 1
  more at cut 30, and every one is explained by the checks, partial or
  full: the number left is production's in every row.
- **The checks cost the pass's curved signals what they cost straight
  ones.** With the full checks at cut 30, 42.6% of production's recovered
  signals survive and 41.9% of the pass's at 10⁻³. Cell by cell: no
  curvature, S_in 400, 236 of 542 (44%); 10⁻³, S_in 400, 211 of 489 (43%)
  and S_in 120, 143 of 331 (43%); 3×10⁻⁴, S_in 120, 173 of 422 (41%).
  Check 6 extrapolating a curved signal in a line (above) does not show
  as a loss.
- **That share is the checks' own cost, not the pass's.** More than half
  of the planted signals that a search recovers are explained away by the
  checks, straight or curved, the same share for every configuration. It
  belongs in the sensitivity of the whole search (search and checks
  together). Broken down (full checks, cut 30; straight signals recovered
  by production, 3,603, and curved ones, 10⁻⁴ and up, by the pass at
  10⁻³, 2,935): unexplained 42.7% and 40.9%; check 3's known interference
  bands alone 40.7% and 41.8%, and with other indications 12.3% and 11.4%
  more; the other checks alone (zero drift, recurrence, crowding,
  look-alikes) 3.8% and 4.8%. Every one is "likely interference
  (indicated)", none "shown". So the cost is nearly all check 3: it marks
  any signal at a frequency on the interference list, real or not, and
  about half of the planted signals fall on it (the chosen blocks weight
  the crowded ones, which are mostly listed bands). Zero drift costs the
  curved signals slightly more (2.2% against 1.3% alone), as expected for a
  path that passes through zero drift.
- **Detection and vetting, inside and outside the known bands**
  (`tools/vet_breakdown.py`, from the same records;
  `data/measurements/curved-pass-vetting-breakdown.json`). A band is a
  label on a frequency, not evidence that a signal is terrestrial, so the
  two are reported apart. At cut 30, of the signals planted inside a
  listed band and outside one, recovered by three looks, then left
  unexplained by the full checks:

  | | inside: planted | recovered | left | outside: planted | recovered | left |
  |---|---|---|---|---|---|---|
  | straight, production | 3,880 | 1,914 (49%) | 0 | 3,380 | 1,689 (50%) | 1,538 (91%) |
  | curved, production | 3,877 | 261 (7%) | 0 | 3,383 | 214 (6%) | 199 (93%) |
  | curved, the pass at 10⁻³ | 3,877 | 1,592 (41%) | 0 | 3,383 | 1,343 (40%) | 1,200 (89%) |

  The search recovers signals as well inside the listed bands as outside
  them. Inside them the checks leave none unexplained, by design (check 3
  marks every one "indicated", which ranks below unexplained). Outside them
  they keep about 90%, straight or curved. So the vetting sensitivity of
  this search is the band list's coverage first and the other checks'
  cost (about 10%) second; a signal in a listed band is left for a person,
  marked, not discarded. At cut 10 the same: outside the bands 91%
  (straight) and 89% (curved, the pass) are left. Step 10's L band put
  3,890 of its 3,938 false candidates at SNR 30 in blocks overlapping the
  listed bands (above); the full checks have not been run on them.
- **The reference look matters for 7.7%.** Of 14,732 pass candidates
  checked with each member look as the reference, 1,131 change between
  explained and unexplained. The tables use the strongest member, as for
  production's. That choice is not neutral, so the range it hides is
  measured (`tools/vet_breakdown.py`):
  - of the 2,477 planted signals only the pass recovers (cut 30), 1,007
    are left unexplained with the strongest member as the reference,
    1,113 with some member, and 943 with every member: 38% to 45%, the
    table's figure (41%) inside. At cut 10, 1,603 to 1,910 of 4,249.
  - of the pass's own wrong-choice candidates (1 distinct signal at cut
    30, 4 at cut 10), none is left unexplained under any reference look.
    The false-candidate result does not depend on the choice.

  The checks read one frequency and one drift, which describes a straight
  track at any look but a curved one only at its reference epoch. The fix
  is to check a curved candidate along its path (check 4 against its
  drift at each look, check 6 and 7 along the curve), which changes
  `vetting.py`, the production checks: left until after Step 10, with
  both results kept until then.

The first orbital run (17 blocks, before the controls were added) is kept
apart, as is a one-block test of the partial checks and the first checks
run's format-1 records.

**turboSETI on the same curved signals, by the same standard.** The first
comparison (`curved.py turboseti`, 40 signals at each acceleration) counted
this search's signal kept when any event holding its hits was a candidate,
and turboSETI's when it had an event and a hit in each ON look. Those are
two different standards, so its 10⁻⁴ result was left open (above).
`curved_pass.py turboseti` runs turboSETI on step 4's 121 blocks with the
second pass's plantings (seed 61, the same 14,520 signals). Its hit search
and event stage run as step 4 runs them (`tools/turbo_curves.py`, the true
choice, unplanted and planted, cuts 10 and 30), and it is scored as step 4
scores it, against the curved track:
- an event whose every listed ON row lies on the track;
- its own hit tables holding a hit on the track in each of the three ON
  looks, its frequency taken half a spectrum in.

An event the unplanted block already had is a false association. This
search's side is the three-look status already recorded for the same
signals.

**Measured** (all 121 blocks, 14,520 signals, 3.1 hours of turboSETI;
`data/measurements/curved-turboseti-blocks.json`). No false association for
turboSETI either, at either cut. Recovered by three looks, of 605 in each
cell:

| \|a\| (Hz/s²) | S_in | cut 10: turboSETI | production | + pass 10⁻³ | cut 30: turboSETI | production | + pass 10⁻³ |
|---|---|---|---|---|---|---|---|
| 0 | 120 | 161 | 534 | 534 | 0 | 454 | 454 |
| 0 | 400 | 352 | 544 | 544 | 187 | 542 | 542 |
| 10⁻⁴ | 120 | 73 | 260 | 478 | 0 | 177 | 393 |
| 10⁻⁴ | 400 | 268 | 269 | 474 | 82 | 267 | 472 |
| 3×10⁻⁴ | 120 | 12 | 17 | 526 | 0 | 0 | 422 |
| 3×10⁻⁴ | 400 | 181 | 11 | 498 | 13 | 11 | 498 |
| 10⁻³ | 120 | 0 | 0 | 465 | 0 | 0 | 331 |
| 10⁻³ | 400 | 10 | 0 | 490 | 0 | 0 | 489 |

In all: at cut 30, where step 4 matched the two false rates, turboSETI
613 of 14,520, production 4,078, the pass 6,557; at cut 10 (turboSETI's
published cut, about 44 on this search's scale, so not a matched
comparison) 2,054, 6,749 and 11,002. Under S_in 120 turboSETI recovers
almost nothing at either cut; its S/N is about 0.23 of this search's, as
step 4 measured.

That settles the comparison left open above. At 10⁻⁴, by the same
standard on the same signals, turboSETI does not keep what this search
loses: at S_in 400 and cut 10 the two are level (268 and 269), and below
that, or at the matched cut, production keeps more. At 3×10⁻⁴ and S_in 400,
turboSETI keeps more than production (181 against 11 at cut 10), as the
first comparison found (9 against 4). It searches each look on its own,
and its event stage follows a hit into the next ON look without asking the
drifts to agree, so a strong curved signal can still pass where
production's single track across the looks cannot. The second pass recovers 498 of the same 605, at both cuts.
