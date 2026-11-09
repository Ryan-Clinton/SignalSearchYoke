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
swept blocks reached the limit (most had about 250 hits).

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
  the old test is gone.
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
| 6 | recurrence at other targets and times in the store | shown within 3 days with drift agreeing; else indicated or coincidence possible |
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
searched.

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
with Green Bank's SEFD taken as 10 Jy (Price et al. 2020: assumed, not
measured here), 2 polarisations, 2.79 Hz channels and 18.25 s spectra:
S_in 1 is about 0.69 Jy Hz (0.69 × 10⁻²⁶ W m⁻²).

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
  152 events, **1 candidate in 95 judged cadences** (0.011 a block's
  cadence, 95% interval 0.0003 to 0.059): a signal at 1937.81 MHz in the
  first three looks only (interference that came and went), which the
  checks marked for its band. **None came out unexplained** (at most 0.039
  a block's cadence, 95%). Over the 308 blocks of a whole cadence, about
  3 false candidates (0.1 to 18) are to be expected before the checks.
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

## Tabby's star

KIC 8462852 was observed by Green Bank in May 2017, among other times;
`./seti.py find KIC8462852` lists them. The whole cadence is on 25 May
2017 (session AGBT17A_999_68, scans 31 to 36: three looks at the star,
each followed by one at KIC8462852_OFF); the archive files the OFF looks
under their own name, so `find` reads them from the session's folder.
