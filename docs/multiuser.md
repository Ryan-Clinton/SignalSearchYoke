# Many people searching: the plan

Written 11 November 2026, revised twice the same day. **Nothing here is
built.** It says how the search would run on many people's computers, what
stays in one place, how an answer from a stranger's computer is checked and
what that checking cannot do, and in what order it is built and tested.
Every figure says whether it was measured (and where), is a projection, or
is a target still to be set.

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
ranking, the ranking not yet finished (step 5). Two things are kept apart
throughout:

- **was the block searched as this repository searches it** (the machinery
  below: computing reliability);
- **is what was found a signal** (the checks, the ranking, and a person:
  science). The first is needed for the second and says nothing about it.

## The principle

- **The data comes from Breakthrough Listen's archive**, read directly by
  each computer (`reading.py`: range requests for the 2.9 MHz needed, each
  tied to the file's ETag with If-Match, so a changed file is refused
  rather than mixed in). The project never stores or passes on the
  recordings.
- **Every answer from a volunteer's computer is untrusted until checked,**
  and so is everything it reports about itself: its version, library
  versions, timings, stamps, bytes read. A version check stops honest
  mistakes, not a modified program.
- **Evidence has a trust level, and keeps it** (below): what the checks
  use is accepted evidence, and a candidate's page says which level each
  part of its evidence has.

## Who does what

| | a volunteer's computer | the work server | the project's own computer |
|---|---|---|---|
| reads the recordings | one block at a time | no | blocks it is asked to search again (below) |
| searches, runs the cadence test | yes | no | the same, on what it reads |
| keeps hits and events | sends them, keeps nothing | keeps every submission; accepted results in the science store | sends its answers to the server |
| checks (`check.py`), ranking | no | yes, on accepted evidence | can |
| hands out work, compares answers | no | yes | no |

The checks stay central because three of them need hits from elsewhere:
recurrence (check 6) looks at other targets and sessions, harmonics and
crowding (checks 8 and 9) use the whole session's hits. The project's own
computer is a machine the project runs itself (this one), not the server
("Where it runs"); it is not always on, and the server must not need it to
be (below).

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
answer, and the answer carries it back: the six file URLs and each file's
ETag and size when the unit was made; the block's index and frequencies;
the search version and its parameters (`seti.search_params()`, as the
store's `runs` table keeps them); the release of the program. If a file's
ETag changes, the unit is withdrawn and remade; answers to the old one are
kept but not compared with answers to the new (a changed file is not a
volunteer's error).

**What an answer holds:** the unit's digest; every hit of the six looks,
shadow hits included, with its look, frequency, drift, SNR and origin;
every event with its label, member hits and what each look showed along
its track; each look's completeness (a look stopped at the 2,000-hit limit
is marked so, as `store.save_block` marks it now); the OFF test's
random-track counts; and, as reported, not trusted: the release, Python and
library versions, operating system, times and bytes read. Candidate stamps
are sent too, for a first look; the checks do not use them (below).

## Checking an answer

### What can go wrong, and what catches it

| | false inclusion: an answer holds what is not there | false omission: an answer leaves out what is there |
|---|---|---|
| an honest fault (a bug, a bad build, a flaky machine) | the twin answer disagrees | the twin answer disagrees |
| one dishonest identity | the twin answer disagrees | the twin answer disagrees |
| two identities agreeing, by fault or collusion | a candidate's block is searched by the project before it is accepted as evidence (below); a wrong hit that is not a candidate is caught only by the random audit | **caught only by the random audit, and then only by chance** |

**Omission is the weak side, and it matters most:** the survey exists to
find rare signals, and a candidate two answers both leave out triggers no
search by the project. What stands against it:

- **Pairing:** the two identities given a block are drawn at random from
  those active, and a new identity's answers are paired with an
  established one's. An attacker must hold both of a block's identities;
  holding a share f of the active identities, that happens for about f²
  of blocks. Identities need no email, so f is not bounded: this raises
  the cost, it does not prevent it.
- **The random audit** (below): a share p of accepted blocks, chosen after
  both answers are in, is searched again by the project. A pair that leaves
  out a candidate from one block escapes with probability 1 − p (97% at
  p = 3%); one that does it on k blocks escapes all of them with (1 − p)^k
  (at p = 3%: 74% for k = 10, 22% for k = 50, 5% for k = 100). **A single
  omission is not reliably caught, and the plan does not claim it is.** A
  pair caught once has all its answers searched again or set aside.

### Two answers, compared whole

Every block goes to two identities. Two answers are compared whole, not by
their candidates: the hit sets, shadow hits included (each hit of one
matched to one of the other by look, frequency, drift and SNR within
tolerances); the events (the same member hits and labels); the looks'
completeness. The tolerances are not chosen here: stage 1 measures how far
honest computers differ (processors, operating systems and numpy builds
may round differently; a hit near the cut, or two near-equal peaks, may
come out differently) and sets them, with the share of blocks that still
disagree.

**When they disagree:** a third identity's answer is asked for, and the
block goes on the project's verification queue as a dispute. Until the
project's own answer comes back, the block is **disputed**: nothing from
it is accepted. The project's answer decides; answers it agrees with are
accepted, the others marked wrong. If it agrees with none, the block is
held for a person.

### The random audit

A share p of accepted blocks (a target of 2 to 5%, set by what the
project's computer can keep up with; stage 4 measures that) is searched
again by the project. **They are chosen after both answers are in,** by
the server, at random, so no computer can know while it works whether its
block will be audited. An audited block whose accepted answer disagrees
with the project's is set aside with every other answer of both its
identities until each is searched again or replaced.

### Known blocks are regression tests, not secret checks

Blocks whose answer the project holds (the KIC 8462852 cadence's 308 to
start with) go out now and then. **A volunteer can recognise them**: a
unit names its files and frequencies, and the KIC 8462852 answers are
public. So they test that a release and a platform give the known answer
(compatibility, regression), not that a computer is honest: a modified
program can answer known blocks honestly and others not. The random audit
is the honesty check, because it is chosen after the answer.

### Planted signals measure completeness, under a design

A computer that plants a signal has been told where it is, so planted
signals never count toward trusting a computer. They measure the survey's
completeness, and only if planted by design:

- **A sampling plan, fixed before the survey:** a share of units in every
  stratum that matters (band, the block's hit density, drift, strength;
  as Phase 6 and steps 4 and 5 measured them) carries planted signals,
  chosen by the server at random within its stratum, with the probabilities
  recorded.
- **Every stage kept apart**, as `injection.py` keeps them now: found in
  each look; an event; a candidate (all three ON looks); kept by the
  checks; ranked within the first N (step 5). Each with intervals, by
  stratum; never one survey-wide percentage.
- **Published completeness comes only from planted units the project
  searched itself** (a share of them, by the same plan), or whose two
  answers agreed and were audited. Volunteers' reports on the rest are a
  running check, not a measurement.
- **Detector or worker:** a planted signal lost the same way by the
  project's own search is the detector's loss; lost by one worker and not
  the other or the project, the worker's.
- A planted unit is not a searched block: its hits never enter the science
  store, and the block goes out again unplanted.

### Every candidate's block is searched by the project

The checks do not run on a candidate's evidence as a volunteer sent it.
Before a candidate's checks, the project's own computer reads its block
from the archive and searches it (the same release, the same unit). Its
events, stamps and measurements are what the store keeps for that block,
and the volunteers' answers must agree with it.

That protects the candidate's own spectra. **The rest of its evidence
mostly does not come from the project:** recurrence (check 6) and its
background, harmonics (check 8) and crowding (check 9) use hits from other
blocks, sessions and targets, nearly all of them accepted volunteer
answers that the project never searched. So:

### Three levels of evidence

1. **Submitted:** a volunteer's answer, not yet compared. Never used.
2. **Accepted:** two answers agreed (or a dispute was settled by the
   project). Used by the checks, as the evidence of other blocks.
3. **The project's own:** searched by the project (candidate blocks,
   audited blocks, settled disputes).

Every hit in the store carries the level of the block it came from. A
check's record says how much of what it used was at each level (for
recurrence: how many of its matches and of its background's blocks). A
candidate that comes out unexplained, or ranks near the top, is
**escalated**: the blocks its recurrence matches and nearest background
came from are searched by the project too, and the checks run again on
the project's own evidence. Nothing is said publicly about a candidate
before that.

### Every submission kept

Every answer, accepted, rejected, disputed or late, is kept (subject to the
storage plan below), so any decision can be looked at again.

## When the project's computer is off

The project's computer is not always on. The server keeps working without
it and never decides in its place:

- **Two queues:** volunteer work, and verification (candidate blocks,
  disputes, audits, escalations, planted units for completeness). The
  verification queue is in the server's database and survives restarts.
- **Priorities:** disputes and candidate blocks first, then escalations,
  then audits, then planted units.
- **What waits:** a disputed block stays disputed; a block with a candidate
  is accepted as searched (its hits are accepted evidence) but its
  candidate is not checked or ranked until the project's search is back;
  an escalated candidate stays provisional. Nothing is promoted because
  the project's computer is away.
- **What goes on:** volunteer work, comparison, acceptance of blocks
  without candidates.
- **Backpressure:** the server stops handing out new work when the
  verification queue passes a set size (or its oldest item a set age),
  and an operator can pause handing out work at any time. Both limits are
  set in stage 4.
- **On return:** the project's computer takes work from the verification
  queue in priority order, at a rate it chooses.

**This can bottleneck the survey.** The KIC 8462852 sweep had candidates in
7 of 308 blocks; that is one session's figure, not a forecast: comparable.md
step 4 found false candidates per block differ many times over between
clean and crowded bands, other sessions may make more, and disputes and
audits add to it. Stage 4 measures the project's searching needed per
volunteer block (candidates, disputes, audits, separately), and the server
admits volunteer work only at a rate the project can verify.

## Work units, leases, submissions, decisions

Four kinds of record, each with its own states:

- **Unit:** `open` (needs answers) → `deciding` → `accepted` | `held` |
  `withdrawn`. A unit needs two agreeing accepted answers (or the
  project's).
- **Lease:** one identity's hold on one unit: `active` → `answered` |
  `expired` | `revoked`, with its time issued, expiry, last renewal.
- **Submission:** one answer: `received` → `valid` | `rejected` (shape,
  size, digest); valid ones are `compared`; each ends `agreed`,
  `disagreed`, `late` or `superseded`. Immutable once received.
- **Decision:** what was concluded about a unit, from which submissions
  and comparisons (and the project's answer if any); immutable; a later
  decision supersedes, never edits, it.

Rules:

- **Leasing is one transaction:** pick a unit that is `open`, has fewer
  than two active or agreed leases, and none held by this identity, and
  insert the lease, with the unit's row locked (`SELECT … FOR UPDATE SKIP
  LOCKED` in PostgreSQL) and a uniqueness constraint on (unit, identity).
  PostgreSQL takes many writers; it does not make this race-free by itself.
- **A unit can have several leases** at once: when one expires, another is
  issued, and the expired one may still answer.
- **Late answers:** a valid submission on an expired lease is still
  compared while the unit is open or deciding, and kept but unused once
  it is accepted.
- **Which answers are compared:** submissions in the order received;
  the first two valid ones from different identities form the first
  comparison; if they disagree, any further valid answers (late ones
  included) and the project's are compared with both, and the project's
  answer decides. The unit is accepted when two agree, or by the project's
  answer, and held after a set number of disagreements.
- **Idempotent:** a submission is keyed by (lease, digest of its content);
  the same answer sent twice is one submission.
- **An answer is taken only on a lease that identity holds or held,**
  with the unit's digest; a block number alone is not enough.
- **Restart:** every state change is a row written before it is acted on.

## From a decision to the science store

The queue (units, leases, submissions, decisions) is in PostgreSQL; the
science store (`data/ssy.sqlite`'s shape) is SQLite. They cannot share a
transaction, so:

- An accepted decision writes an **ingestion row** in PostgreSQL in the
  same transaction: (decision id, the canonical submission, the target
  block).
- One ingester process takes ingestion rows in order and writes each with
  `store.save_block` in one SQLite transaction, recording the decision id
  in the block's record; it then marks the ingestion row done.
- If it stops between the two, the row is still pending: on restart it
  looks for the decision id in the store, and writes the block only if it
  is not there. Writing is retried until done; it is never done twice.

**History:** `store.save_block` now marks a block's earlier hits, events
and looks superseded and replaces the block's own record (`INSERT OR
REPLACE`). That keeps the hits' history, not the decisions'. The full
history is in PostgreSQL's submissions and decisions, each science-store
block record naming the decision it came from; the block record's own
replacement needs to keep its predecessors (a history table), a change
made with the server, not before.

## Checks that change

- **Searched and complete are separate.** Every block has two statuses:
  *verification* (submitted, accepted, the project's own, disputed, held)
  and *coverage* (complete; cut short, with which looks hit the 2,000-hit
  limit). A block can be accepted and cut short: its hits are kept, used
  for interference and recurrence, and it is left out of the usable band,
  the limits and completeness, as the result page does now (48 of 1,848
  block-looks in the KIC 8462852 sweep). A later search version that lifts
  the limit searches it again.
- **A candidate's context changes** when the store gains, near it:
  - hits (within check 6's recurrence window, checks 8 and 9's ranges);
  - **searched coverage, even with no hits**: check 6's background counts
    the band searched (`check.recurrence_background` takes it from the
    searched blocks), so new empty coverage changes its expected count;
  - a new checks version.
  Each accepted block marks as stale the candidates whose windows it
  overlaps (by frequency, and session for checks 8 and 9); stale ones are
  checked again. At survey scale this needs coverage kept by frequency
  (a summary table) rather than every check querying every hit; built
  when the store's size calls for it, but the behaviour is set now.
- **Reproducible verdicts:** a check record keeps the checks version and
  the **store revision** it saw (the highest decision id ingested), not
  only a date; the store keeps enough history to rebuild that revision.

## Ranking across a survey

`ranking.py` is being built (comparable.md step 5) and is not committed or
validated at this writing. Before a survey's candidates are ranked against
each other: step 5 is done and its result read; the ranking has a version
of its own, kept with every ranked list; completeness into the first N of
the whole survey (not one cadence's eleven) is measured with planted
signals at the survey's scale; candidates are ranked again when their
checks change.

## Storage

**Projection, not measurement:** at 194 MB a cadence (the KIC 8462852 store,
mostly shadow hits), accepted science data alone would be about 19 GB for
100 cadences, 194 GB for 1,000 and 1.9 TB for 10,000; real sizes depend on
each session's interference, the schema, indexes and compression. Kept
submissions (at least two a block, more in disputes) roughly double to
triple that, and backups add more. Brokerblitzer has 217 GB free, shared
with its other services. So:

- **Separate budgets** for the science store, kept submissions, the
  queue's records, backups and temporary files, each measured in stage 4
  from compressed answers.
- **Retention:** accepted science data and every decision are kept;
  a submission that agreed is kept as its digest and comparison result
  once its block is accepted, its content dropped after a set time (the
  canonical one is in the science store); rejected, disputed and wrong
  submissions are kept whole (they are the evidence about a worker).
- **Admission by disk:** the server stops handing out work before free
  disk falls below a floor that protects the other services.
- **Before the survey outgrows the box:** the science store moves to
  storage of its own; brokerblitzer's disk is for the pilot.

## Security and isolation

- **Identities:** taking part needs no email; each install gets a token
  from the server, which can be revoked, with limits on leases held and
  submissions per hour.
- **Archive addresses only:** the program reads only from Breakthrough
  Listen's archive host, refuses any other address in a unit and any
  redirect away from it.
- **Uploads:** HTTPS; a request-body limit at nginx; parsed as a stream
  with limits on size and counts, checked for shape and digest before
  anything is stored; anything else refused.
- **Bounded everything:** a fixed pool of web workers, a cap on PostgreSQL
  connections, temporary-file and memory limits for the service (a systemd
  slice), a bounded ingestion queue, the comparison of answers done by the
  ingester side with its own limits, not by web requests.
- **Monitoring:** free disk, queue and verification-backlog sizes and
  ages, database errors, rejected submissions by identity; the server
  pauses handing out work on any limit.
- **The program:** released from tagged commits, dependencies pinned, the
  release's hashes published; a signed Windows build when there is one.
  These show a download is the release, not that a computer ran it
  unchanged: the checks above are for that.

## Load on Breakthrough Listen's archive

**The server cannot see or enforce the archive traffic:** volunteers read
from Breakthrough Listen directly, and a modified program can ignore any
limit it is given. `reading.py` now runs up to 6 requests at once by
default (at most 8) per computer, and Breakthrough Listen publishes no
rate limit. What the project can do:

- **Indirect limits:** a cap on leases out at once across all identities,
  and on units started per hour, set conservatively (the figures from
  Breakthrough Listen, below); the program told how many requests to have
  in flight (fewer than now for volunteers).
- **Estimates, said to be estimates:** units started times their
  measured size gives the expected traffic; volunteers' reported bytes are
  reports.
- **Throttling:** the program reports 429 and 503 answers; when they rise
  across many identities, the server slows or stops handing out work and
  tells programs to back off, beyond `reading.py`'s own retries.
- **An emergency stop** an operator can pull, and one Breakthrough Listen
  can ask for.
- **Asked first:** the project's owner asks Breakthrough Listen, before the
  server is built, what aggregate rate they accept and whether they want
  a different arrangement (an agreed rate, a mirror, a token).

## Where it runs

The work server goes on the project owner's existing server
("brokerblitzer") for the pilot: nothing to buy. Looked at (read only) on
11 November 2026: Ubuntu 24.04, 6 cores, 7.7 GB of memory (about 5 GB
free), 217 GB of disk free. It already runs nginx with HTTPS on 443 for the
ryanclinton.uk sites (each a service on a local port behind nginx),
PostgreSQL 16, Redis, earlyoom, and other services and customers'
workloads. So:

- **The service** is one more local-port service behind nginx, on a
  subdomain of ryanclinton.uk, under its own unprivileged user, in a
  systemd slice with memory, CPU and task limits (earlyoom kills the
  largest process when memory runs short: it must be this service, not a
  site), with the bounds above.
- **The queue in PostgreSQL** (its own database and user, a connection
  cap); the science store SQLite, one ingester.
- **The project's own searches stay off it** (up to 3.4 GB a block).
- **The checks** (about 5 s and little memory a candidate) and the ranking
  run there, in the same slice.
- **Load tests on it are gentle:** stage 3's load and failure tests run on
  the project's own machines; on brokerblitzer only a light check that
  the limits hold, never saturating what other services share.

## The volunteer's program

A command (`seti.py work --server URL`), and for those without Python one
Windows program built from the same release; pip for the rest. turboSETI
and pickles are not part of it.

- **Plain about the cost:** it says, before it starts, that it uses CPU,
  memory, network and electricity, how much per block (from stage 1), and
  how to stop it.
- **Controls:** how many blocks at once (one by default), a CPU share or
  low priority, a memory check before taking work (a unit says the memory
  its block needs, from its hit counts; a computer without it is not
  given it), hours to run in, pause and stop (a key, and a file the
  program watches).
- **A minimum computer** (memory, disk for one block's data) from stage 1's
  measurements, refused politely below it.
- **Keeps little:** a log and the current unit's retry state; no
  recordings once a unit is done, no personal data.

## In what order, and when each is done

1. **Reproduction by a few technical people, no server.** Each searches
   the same set of the KIC 8462852 cadence's blocks, chosen to cover what
   goes wrong: crowded blocks (35, 36, 129), blocks cut short at the hit
   limit, the 7 blocks with candidates, clean blocks, the coarse channels'
   edges; at least 20 blocks. (`seti.py sweep --blocks N` searches the next
   N blocks in order; choosing blocks needs a small option, which does not
   change the search.) Every hit, shadow hit, event and label is compared
   with this computer's, and each computer's time and memory per block
   recorded. *Done when:* at least three other computers, Windows and at
   least one other operating system, have done the set, and the
   differences are written up (how many hits and events differ, by how
   much, why, the tolerances they give), with the minimum computer.
2. **comparable.md steps 5 and 10:** the ranking measured, and the matched
   comparison on another session with its cuts fixed beforehand. Until
   step 10 is done, no claim about the search goes beyond one session, and
   no open call is made.
3. **The server, tested on the project's own machines.** Several copies of
   the program, with these made to happen on purpose: leases running out
   and late answers (the A, B-expired, C, B-late order), the same answer
   sent twice, an upload cut off halfway, the server and the ingester
   stopped between acceptance and the science store, malformed and
   oversized answers, a hit or event changed, a whole answer invented, two
   identities agreeing on an invented candidate, **two identities agreeing
   to leave out a real candidate** (planted, so its place is known), a
   candidate whose recurrence evidence comes from blocks accepted on two
   volunteers' agreement only, the project's computer off for days, a
   source file's ETag changing, the disk floor reached.
   *Done when:* each is caught, survived or reported as this plan says,
   and what was not caught is written down with why: in particular, that
   the left-out candidate is not caught by the candidate searches, and
   how often the audit caught it over many trials at the chosen p (which
   shows the audit works as designed, not that omission is prevented).
   A restore from backup has been done.
4. **A pilot with a few known people** (stage 1's), through the server on
   brokerblitzer. *Done when:* they have searched the whole KIC 8462852
   cadence through it, and the accepted store matches this computer's
   sweep (every hit, event, candidate and check); and measured: request
   rates and bytes (estimated, as above), time per block, the project's
   searching needed per volunteer block (candidates, disputes, audits
   apart), storage per cadence, compressed answer sizes. This shows the
   machinery and its accounting work with honest people; it does not
   show resistance to a determined dishonest one.
5. **An open call,** with Breakthrough Listen's answer applied, the
   Windows program, limits set from stage 4, and a public page saying what
   the results can and cannot show, including what the checking above
   cannot catch.

## What is open

- The subdomain, and the service's limits on brokerblitzer (stage 3).
- Breakthrough Listen's answer on load (before stage 3).
- Who the first few people are.
- How cadences are chosen once KIC 8462852's is done.
- Set from measurement: the tolerances (stage 1), the minimum computer
  (stage 1), the audit share p and the backlog limits (stage 4), lease
  times (stage 3), storage budgets and retention times (stage 4).
