# Many people searching: the plan

Written 11 November 2026, revised the same day. **Nothing here is built.**
It says how the search would run on many people's computers, what stays in
one place, how an answer from a stranger's computer is checked, and in what
order it is built and tested. Where it gives a figure, it says whether the
figure was measured (and where) or is a target still to be set.

## What it is for, and what it is not

One computer swept one cadence of one star (308 blocks, about 900 MHz) in
about a day. Breakthrough Listen's open archive holds many more cadences.
Many computers, each doing a block at a time, can search more of them, as
SETI@home searched Arecibo's data.

**That is throughput, not credibility.** More data searched does not make
the search more sensitive, its false candidates fewer, or a candidate more
convincing. The search's measured advantage over turboSETI is from one
session (comparable.md step 4); whether it holds on others is step 10's
question, and a survey's candidates are only as good as the checks and the
ranking, the ranking not yet finished (step 5). The two aims are kept
apart here: the machinery below makes sure a block was searched as this
repository searches it; it says nothing about whether what was found is
a signal.

## The principle

- **The data comes from Breakthrough Listen's archive**, read directly by
  each computer (`reading.py`: range requests for the 2.9 MHz needed,
  each request tied to the file's ETag with If-Match, so a changed file
  is refused rather than mixed in). The project never stores or passes on
  the recordings.
- **Every answer from a volunteer's computer is untrusted until checked,**
  and so is everything it reports about itself: its version, its library
  versions, its timings, its stamps. A version check stops honest mistakes,
  not a modified program. What makes an answer trusted is that it agrees
  with other answers and with the project's own runs (below).
- **The checks and the ranking run centrally** on evidence the project has
  read itself (below), never on a volunteer's word.

## Who does what

| | a volunteer's computer | the work server | the project's own computer |
|---|---|---|---|
| reads the recordings | one block at a time | no | a sample of blocks, and every candidate's block |
| searches, runs the cadence test | yes | no | the same, on what it reads |
| keeps hits and events | sends them, keeps nothing | holds submissions; keeps what is accepted | its own runs |
| checks (`check.py`), ranking | no | yes, on accepted results and the project's own evidence | can |
| hands out work, compares answers | no | yes | no |

The checks stay central because three of them need hits from elsewhere:
recurrence (check 6) looks at other targets and sessions, harmonics and
crowding (checks 8 and 9) use the whole session's hits. The "project's own
computer" is a machine the project runs itself: this one, not the server
(below, "Where it runs").

## The work unit

One block of one cadence: 2.9 MHz in all six looks, as `seti.py sweep`
does it now. **Measured** on this computer (the 121 blocks of comparable.md
step 4, `data/matched/`):

| | median | worst |
|---|---|---|
| read from the archive | 18 s | 58 s |
| search and cadence test | 35 s | 24 minutes (a crowded block) |
| memory | not recorded per block | 3.4 GB (block 35, 12,000 hits a look) |

The size of an answer is **estimated**, not measured: the store holds the
whole sweep's hits (72,555 at the cut, 572,844 shadow hits), events and
stamps in 194 MB, about 0.6 MB a block on average; crowded blocks are
larger. The transfer format, its compression and a size limit are set in
stage 3 from real answers.

**A work unit's identity** is a digest of everything that decides its
answer, and the answer carries it back:

- the six file URLs and each file's ETag and size when the unit was made;
- the block's index and frequencies;
- the search version and its parameters (`seti.search_params()`, as the
  store's `runs` table keeps them);
- the release of the program it is meant for (below).

If a file's ETag has changed since, the unit is withdrawn and remade, and
answers to the old one are kept but not compared with answers to the new:
a changed file is not a volunteer's error.

**What an answer holds:** the unit's digest; every hit of the six looks,
shadow hits included, with its look, frequency, drift, SNR and origin;
every event with its label, member hits and what each look showed along
its track; each look's completeness (a look stopped at the 2,000-hit
limit is marked so, as `store.save_block` marks it now); the OFF test's
random-track counts; and, as reported (not trusted), the program's
release, Python and library versions, operating system and times.
Candidate stamps are sent too, for a first look, but are never what the
checks run on (below).

## Checking an answer

### Two answers, compared whole

Every block goes to two different volunteer identities. An identity is not
a computer: one person can hold several, and two people can share a fault
or agree to cheat, so two agreeing answers show a block was searched the
same way twice, not that it was searched right. The other checks below
are there for that.

Two answers are compared whole, not by their candidates:

- **the hit sets**, shadow hits included: each hit of one matched to one
  of the other by look, frequency, drift and SNR within tolerances;
- **the events**: the same events with the same member hits and labels;
- **completeness**: the same looks marked complete.

The tolerances are not chosen here: stage 1 measures how far honest
computers differ (different processors, operating systems and numpy
builds may round differently, and a hit near the cut or two near-equal
peaks may come out differently), and the tolerances are set from those
differences, with the share of blocks that still disagree.

**When they disagree:** the block goes to a third identity, and also to
the project's own computer. The project's own answer decides: the answers
it agrees with (within the tolerances) are accepted, the others marked
wrong. If the project's own answer agrees with none, the block is held for
a person to look at; nothing from it is accepted.

### The project's own runs

- **A random share of blocks** (a target of 2 to 5%, to be set by what the
  project's computer can keep up with) is searched by the project's own
  computer as well, without the volunteers knowing which. A volunteer
  whose accepted answers disagree with these is caught even when its
  twin agreed with it.
- **Known blocks:** now and then a block whose answer the project already
  holds (the KIC 8462852 cadence's 308 blocks to start with) goes out as
  ordinary work. The volunteer cannot tell it from any other.

### Every candidate's evidence is read by the project

A candidate's stamps (the spectra around its track that check 1 looks at)
and every measurement the checks use come from the volunteer's computer
in its answer. The checks do not run on them. **Before a block's
candidates are checked, the project's own computer reads that block from
the archive itself and searches it** (the same release, the same unit).
Its own events, stamps and measurements are what go into the store and to
the checks; the volunteers' answers must agree with it, as above. A
cadence makes few candidates (11 in the KIC 8462852 sweep, in 7 of 308
blocks), so this is a few per cent of the reading. A candidate's page
shows whether its evidence is the project's own.

### Planted signals measure completeness, not honesty

The first version of this plan had volunteers' computers plant signals
the server would then look for, "at places only the server knows". That
does not work: a computer that plants a signal has been told where it is,
and a modified program can report it without searching. So:

- **Planted signals measure completeness**: some units ask the volunteer's
  computer to plant signals (`injection.py`, as Phase 6 and step 5 plant
  them) and report what it found; the share recovered across the survey
  is its running completeness. A computer could fake these, so they are
  kept apart from the trust checks and do not count toward trusting it.
- **Honesty is checked only by what the volunteer cannot know**: the
  twin answer, the project's own runs, the known blocks.
- A block with planted signals is not a searched block: its hits are not
  stored as the sky's, and the block goes out again without them.

### Every submission kept

Every answer, accepted, rejected, disputed or late, is kept with its
digest, its identity and what it reported, so any decision can be looked
at again.

## Work units through the server

Each unit moves through these states, and only these:

`ready → leased → answered → (second answer) → comparing → accepted`

with the branches:

- **lease runs out** (no answer in its time, or no renewal): back to
  `ready` for another identity; the first may still answer (below);
- **disagreement**: `comparing → disputed`, then a third answer and the
  project's own (above), then `accepted` or `held`;
- **withdrawn**: a source file changed (above);
- **rejected**: an answer fails its shape, its digest, or the comparison.

Rules:

- **Leases** are set by the block's expected time (a crowded block's are
  longer: the hit counts in the store say which), and the program renews
  its lease while it works. A unit is leased to at most a set number of
  identities at once, and retried at most a set number of times before it
  is held for a person.
- **A late answer** is still taken and compared if the unit is not yet
  accepted; after that it is kept but changes nothing.
- **Answers are idempotent:** the same answer sent twice (a retried
  upload) is the same submission.
- **An answer is taken only for a lease that identity holds,** with the
  unit's digest; a block number alone is not enough.
- **After a restart** the server rebuilds its state from its own records:
  every state change is written before it is acted on.

## The store

The science store (the shape of `data/ssy.sqlite`) and the work queue are
apart: the queue (units, leases, submissions, identities) in PostgreSQL
(already on the server, "Where it runs"), accepted results in the science
store. An accepted result is never overwritten:
a later one (a new search version, a block searched again) supersedes it,
as the store's `superseded_run` already does for runs.

**One writer:** `store.save_block` writes a block's hits, events, links
and stamps in one transaction, written for one search process. The server
has one process that writes the science store, fed from a queue of
accepted results; the web side only writes the work queue. SQLite in
write-ahead mode serves a pilot; whether a larger survey moves the science
store to PostgreSQL too is decided when the store's growth (194 MB a cadence now, mostly shadow
hits) and the write rate are measured in stage 4. Backups are daily, and a
restore is tested in stage 3.

## Checks that change

- **Incomplete blocks:** a block with a look stopped at the hit limit
  (48 of 1,848 block-looks in the KIC 8462852 sweep) is accepted as
  searched with a cut-short look, as now, and left out of the usable band
  and the limits, as the result page does now. It is never counted as
  fully searched.
- **Recurrence grows:** check 6 looks at every other session's hits, so a
  candidate's verdict can change as the survey adds sessions near its
  frequency. Every candidate's checks are rerun when the store gains hits
  within its recurrence window, and each check record keeps the checks
  version and the date of the store it saw.
- **New versions:** a new search or checks version is a new release; its
  blocks are searched again (as `seti.py sweep` does now for blocks of an
  older search version), and the old results stay until superseded.

## Ranking across a survey

`ranking.py` is being built now (comparable.md step 5: a score from the
checks' chances, signals planted to see how often one ranks where a
person would look). It is not committed or validated at this writing.
Before a survey's candidates are ranked against each other:

- step 5 is done and its result read: how often a planted signal ranks
  first among one cadence's real candidates, by strength and drift;
- the ranking has a version of its own, kept with every ranked list;
- across a survey a person looks at the first few of thousands of
  candidates, not of one cadence's eleven: completeness into the top N of
  the survey is measured with planted signals at the survey's own scale,
  not assumed from one cadence;
- candidates are ranked again when their checks change (above).

## Security

- **Identities:** taking part needs no email; each install gets a token
  from the server, which can be revoked, with limits on units held and
  answers sent per hour.
- **Archive addresses only:** the program reads only from Breakthrough
  Listen's archive host (`reading.py`'s source), refuses any other address
  in a unit and any redirect away from it; the server cannot make it fetch
  anything else.
- **Uploads:** over HTTPS, checked for shape, size and digest before they
  are stored; anything else is refused.
- **The program:** released from tagged commits, with its dependencies
  pinned and the release's hashes published; a signed Windows build when
  there is one. These show a download is the release, not that a
  computer ran it unchanged: that is what the checks above are for.
- **The server:** runs as its own unprivileged user with limits on memory
  and disk, apart from whatever else runs on that machine, with
  monitoring and the backups above.

## Load on Breakthrough Listen's archive

`reading.py` limits the requests one computer has in flight, as Breakthrough
Listen publishes no rate limit. Many computers multiply that, so the limit
is the server's: it caps the units leased at once and watches the bytes
read per hour across all of them, and stops handing out work when either
passes its limit. **The limits come from Breakthrough Listen:** the
project's owner asks them before any computer other than the project's own
reads for it at scale, and before the server is built, so their answer
can shape it.

## Where it runs

The work server goes on the project owner's existing server
("brokerblitzer") for now: nothing to buy. Looked at (read only) on 11
November 2026: Ubuntu 24.04, 6 cores, 7.7 GB of memory (about 5 GB free),
217 GB of disk free, up 109 days. It already runs nginx with HTTPS on port
443 for the ryanclinton.uk sites (each a service on a local port behind
nginx), PostgreSQL 16, Redis and earlyoom, and other services and
customers' workloads. So:

- **The service** is one more local-port service behind the existing
  nginx, on a subdomain of ryanclinton.uk, as the other sites are, under
  its own unprivileged user with a memory limit (earlyoom there kills the
  largest process when memory runs short: it must not be another site).
- **The work queue in PostgreSQL**, which is already running there (its
  own database and user): it handles many writers, so the queue's leases
  and submissions need no single-writer design of their own. The science
  store stays SQLite, written by one process, as above.
- **The project's own runs stay off it.** Searching a block takes up to
  3.4 GB (block 35), which that box cannot spare beside its other
  services: the project's own searches (the random share, every
  candidate's block, disputes) run on the project's own computer (this
  one), which fetches the work from the server like a volunteer's but
  under the project's identity, and whose answers the server trusts.
- **The checks** (about 5 s and little memory a candidate) and the ranking
  can run on the server.

## The volunteer's program

A command (`seti.py work --server URL`) that asks for a unit, does it, sends
it back and asks again until stopped, keeping only a log. For those without
Python, one Windows program built from the same release; pip for the rest.
turboSETI and pickles are not part of it: they belong to the comparisons,
not the search.

## In what order, and when each is done

1. **Reproduction by a few technical people, no server.** Each searches
   the same set of the KIC 8462852 cadence's blocks, chosen to cover what
   goes wrong: crowded blocks (35, 36, 129), blocks cut short at the hit
   limit, blocks with candidates (the 11), clean blocks, and the coarse
   channels' edges; at least 20 blocks. (`seti.py sweep --blocks N` now
   searches the next N blocks in order; choosing blocks needs a small
   option added, which does not change the search.) Every hit, shadow
   hit, event and label is compared with this computer's.
   *Done when:* at least three other computers, Windows and at least one
   other operating system, have done the set, and the differences are
   written up: how many hits and events differ, by how much, why, and the
   tolerances they give.
2. **comparable.md steps 5 and 10:** the ranking measured, and the matched
   comparison on another session, its cuts fixed beforehand. Until step
   10 is done, no claim about the search goes beyond one session, and no
   open call is made.
3. **The server, tested on the project's own machines.** Several copies of
   the program on trusted computers, with these made to happen on
   purpose: leases running out, the same answer sent twice, an upload cut
   off halfway, the server stopped mid-write and restarted, malformed and
   oversized answers, a hit or event changed in an answer, a whole answer
   invented, two identities agreeing on a wrong answer, a source file's
   ETag changing.
   *Done when:* each is caught or survived as this plan says, and a
   restore from backup has been done.
4. **A pilot with a few known people** (stage 1's), through the server.
   *Done when:* they have searched the whole KIC 8462852 cadence through
   it, and the accepted store matches this computer's sweep: every hit,
   event, candidate and check; and the request rates, bytes read and time
   per block are measured.
5. **An open call,** with Breakthrough Listen's limits enforced, the
   Windows program, and a public page saying what the results can and
   cannot show.

## What is open

- The subdomain, and the server's memory limit for the service (stage 3).
- Breakthrough Listen's answer on load (before stage 3).
- Who the first few people are: people the owner knows, or a small call
  to people who can run Python.
- How cadences are chosen once KIC 8462852's is done: a target list, or
  every whole cadence in the archive in turn.
- The tolerances (stage 1), the share of blocks searched by the project
  as well (stage 3), the lease times and limits (stage 3).
