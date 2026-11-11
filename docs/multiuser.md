# Many people searching: the plan

Written 11 November 2026. Nothing here is built yet. It says how the search
would run on many people's computers, what stays in one place, how a result
from a stranger's computer is trusted, and in what order it is built.

## What it is for

One computer swept one cadence of one star (308 blocks, about 900 MHz) in
about a day. Breakthrough Listen's open archive holds thousands of
cadences. Many computers, each doing a block at a time, can search them as
SETI@home searched Arecibo's data: the work split into small pieces,
every piece done twice, and planted signals hidden in the work to show
each computer is finding what it should.

## What stays as it is

- **The data comes from Breakthrough Listen's archive**, read directly by
  each computer (`reading.py`: range requests for the 2.9 MHz needed, not
  whole 15 GB files). The project never stores or passes on the recordings.
- **The search, the cadence test and the checks** are the ones this
  repository runs now, at a fixed version. Nobody's computer runs a
  version of its own.

## Who does what

| | a volunteer's computer | the work server (central) |
|---|---|---|
| reads the recordings | yes, one block at a time | no |
| searches the six looks, runs the cadence test | yes | no |
| keeps every hit and event | sends them, keeps nothing | yes, in one store |
| the checks (`check.py`) and the ranking (`ranking.py`) | no | yes |
| hands out work, compares the two answers to each block | no | yes |

The checks stay central because three of them need hits from elsewhere:
recurrence (check 6) looks at other targets and sessions, and harmonics
and crowding (checks 8 and 9) use the whole session's hits. A volunteer
holds one block. Checks run on one computer also mean a candidate is never
judged two ways. The ranking is central for the same reason: it ranks every
candidate of the survey against every other.

## The work unit

One block of one cadence: 2.9 MHz in all six looks (ON, OFF, ON, OFF, ON,
OFF), as `seti.py sweep` does it now. On this computer (the 121 blocks of
comparable.md step 4):

| | typical | worst |
|---|---|---|
| read from the archive | about 300 MB, 18 s | 58 s |
| search and cadence test | 35 s | 24 minutes (a crowded block) |
| memory | about 1 GB | 3.4 GB (block 35, 12,000 hits a look) |
| sent back | about 0.6 MB (hits, events, the block's record) | a few MB |

A work unit names the six file URLs, the block's frequencies, the search
version, and (for some) the signals to plant (below). The volunteer's
computer sends back the block's hits, its events with their member hits and
stamps, the looks' completeness, the OFF test's random-track counts, and
what the store's `runs` table keeps now: search version, commit, Python and
library versions, host type, times.

## Trusting an answer

- **Every block done twice,** by two different people's computers, and the
  two answers compared before either goes into the store. Agreeing answers
  are kept; disagreeing ones go to a third computer. At a fixed version
  the search should give the same hits, but different processors and
  numpy builds may round differently, so "the same" needs tolerances:
  frequency, drift and SNR within limits measured first (stage 1 below),
  and the same events with the same labels.
- **Planted signals:** some work units carry signals the volunteer's
  computer plants itself before searching (`injection.py`, as Phase 6 and
  step 5 plant them), at places and strengths only the server knows. A
  computer that misses signals it should find is caught, and the planted
  ones double as a running measure of completeness over the whole survey.
  The planted hits are taken out before the block's answer is stored.
- **A known block now and then:** a block of the KIC 8462852 cadence
  already in the store, whose answer is known.
- **A computer whose answers keep failing** stops being sent work.

None of this needs the volunteers to be trusted; it needs the server to
check.

## The load on Breakthrough Listen's archive

`reading.py` keeps a modest limit on requests in flight from one computer,
as Breakthrough Listen publishes no rate limit. A hundred computers is a
hundred times that. Before the call goes wider than a few people, the
project asks Breakthrough Listen (by email, from the project's owner) what
load they are content with, and the server enforces it: how many work
units are out at once, and how many a computer takes in an hour.

## The work server

On the project owner's existing server ("brokerblitzer") for now: nothing
to buy. A small web service (for example FastAPI) with its own SQLite store
of the same shape as `data/ssy.sqlite`:

- **hand out:** the next block nobody has, or the second copy of one
  somebody has; a work unit expires if no answer comes back in a set time;
- **take back:** an answer, checked for shape and version, held until its
  twin arrives;
- **compare and keep:** two answers that agree go into the store; then the
  checks and ranking run there on what is new;
- **show:** a page of how far each cadence has got, the candidates by rank,
  and each volunteer's count of blocks (by a name they choose; no email
  needed to take part).

Its OS, access and what else runs there are to be settled when it is built,
so it disturbs nothing else on that machine.

## The volunteer's program

A command (`seti.py work --server URL`) that asks for a work unit, does it,
sends it back, and asks again, until stopped; it keeps nothing but a
log. For those without Python, one Windows program built from the same code
(PyInstaller or similar), and pip for the rest. turboSETI and pickles are
not part of it: they belong to the comparisons, not the search.

## In what order

1. **Reproduction by a few technical people, no server.** Each runs
   `seti.py sweep KIC8462852 --blocks N` on a few blocks of their choosing
   and sends back the store; their hits and events are compared with this
   computer's. *Done when:* at least three other computers (Windows and one
   other OS) have done at least five blocks each, and the differences are
   measured and give the tolerances for comparing two answers.
2. **comparable.md step 10:** the matched comparison on another session,
   its cuts fixed beforehand. Until it passes, no claim about the search
   goes beyond one session, so no open call is made.
3. **The work server and the `work` command,** with double answers,
   planted signals and known blocks. *Done when:* the few people of stage 1
   sweep a whole cadence through it and the store matches a sweep done
   here.
4. **Asking Breakthrough Listen about load,** then an open call, with the
   Windows program.

## What is open

- Who the first few people are (stage 1): people the owner knows, or a
  small call to people who can run Python.
- Breakthrough Listen's answer on load (stage 4).
- How cadences are chosen once KIC 8462852's is done: by target list
  (nearby stars, the published searches' targets), or every whole cadence
  in the archive in turn.
- What the ranking does across many cadences: step 5 measures how often a
  planted signal ranks first among one cadence's candidates; across a
  survey a person looks only at the first few of thousands, so that bar
  is higher, and is measured again as the survey grows.
