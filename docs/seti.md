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
- `cadence` follows each hit of the first ON look to where its drift puts
  it in the later looks. Found in every ON look and no OFF look, it is a
  candidate; seen in any OFF look, interference; missing from an ON look,
  unconfirmed.

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

**False hits** (`measure.py false`; each of the 30 looks scrambled twice:
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
not.

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
hits (about 1,500 a block); 190 of the hits in one block (7, 1836 to 1839
MHz). Version 1's hits and events stay in the store marked superseded, and
each of its 24 events is linked to the new event that replaces it. About
34 s a block (fetch 18 to 27 s, hidden; search 29 to 58 s; 120 CPU
seconds; 2.3 GB peak): the whole cadence would take about 2.9 hours.

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

Measured on real data before the sweep was let loose.

**Signals planted in real noise** (`./seti.py inject`; 3 November 2026,
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
