# Using the whole machine: a spec for parallel runs

Status: Part B is approved in direction and revised below; nothing is
built. Decided 13 November: Step 10 runs as planned (3 workers a stage, the
runner unchanged); reproducibility of the frozen comparison comes before
finishing sooner. Part A is dropped and kept only as a record; Part B is
built after Step 10's verdict, in three stages with a test gate between
each. Written 12 November 2026, revised 14 November after review. Nothing
here changes what any measurement computes: the aim is the same records,
sooner.

## What the machine does now (measured, not assumed)

The PC: Ryzen 9 3950X, 16 cores / 32 threads, 40 GB RAM, Windows 11.

During the checks run, 12:00 on 12 November:

| | |
|---|---|
| CPU, all threads | 22–24% busy (6 of 32 threads) |
| clock | about 118% of the 3.5 GHz base on the busy cores (boost already on) |
| memory | about 6 GB free; each worker 2.0–2.5 GB |
| disk | idle |

Each worker is one Python process doing one block at a time, single-threaded
in practice (the work is Python loops and numpy calls on modest arrays, not
large BLAS products). So the run goes at the speed of its worker count, and the
worker count is limited by memory, not cores. Overclocking would not help: with
few cores loaded the chip already boosts above what an all-core overclock
holds, and an unstable one risks a multi-hour measurement.

Where a block's time goes (medians from the records, seconds):

| run | blocks | block | parts |
|---|---|---|---|
| matched.py (step 4) | 121 | ~200 | search 37–40, judging 3–21, planted 65–79, turboSETI 40, Pickles-style 12, fetch 18–19 |
| curved_pass.py run | 121 | 165 | search 53, planted 109 |
| curved_pass.py orbits | 121 | 212 | |
| curved_pass.py vet | 40 so far | 1,872 | false candidates 117, planted 1,572 |

The tail is long: crowded blocks take much more (vet block 36: 6,931 s against
a median of 1,872). With the current split (worker i takes every n-th block
from the i-th, fixed at start) one worker that draws slow blocks sets the end:
at 12:00, worker 3 had done 3 blocks and workers 0, 1, 4 and 5 had done 7 each.

## What already makes parallel runs safe

Checked in the code:

1. **Each block has its own random stream**, `np.random.default_rng([SEED, k])`
   for block k (matched.run, curved_pass.run, orbits, vet, turboSETI runs), so
   a block's planted signals do not depend on which worker runs it or what ran
   before.
2. **Each block's record is its own file** (`block_NNN.json`), and a run skips
   blocks whose file exists, so runs resume and shards do not share state.
3. **Work folders are per shard** (`work_{i}`, `work_turbo_{i}`).
4. **The verdict of Step 10 fails closed**: every chosen block must be whole.

## What is not safe yet (found while writing this)

1. **Block records are not written atomically.** matched.py and curved_pass.py
   write `block_NNN.json` with `Path.write_text`. A worker killed mid-write
   leaves a partial file, and the resume test (`exists()`) then skips that
   block as done. Step 10's verdict would refuse it (unreadable), but the other
   runs and their tables would not notice. `yoke.write` (write to `.part`,
   fsync, rename) already exists and is not used here.
2. **`blocks.json` is written by every shard at start**, also with
   `write_text`. Shards started together can read each other's half-written
   file. Harmless so far (same content, short file) but a race.
3. **The archive limit is per process.** `reading.py` caps requests in flight
   at 6 (never more than 8) because Breakthrough Listen's server is shared.
   That gate is a `threading.BoundedSemaphore`: with n worker processes the
   machine can have 6n requests in flight. Fetching is about 10% of a matched
   block, so the average is far lower, but 12 workers starting together could
   burst to 72.
4. **BLAS threads are not pinned.** numpy here uses OpenBLAS (up to 24
   threads). Little of the work uses it, but many processes each spawning
   BLAS threads would oversubscribe, and a BLAS reduction's result can depend
   on its thread count.

## Part A: dropped (kept as a record, not to be built)

Part A proposed changing only Step 10's runner (8-12 workers from free
memory, staggered starts, BLAS pinned) to finish about half a day sooner. It
was dropped on 13 November: a new runner, worker environment and archive
load during a frozen measurement is a risk the time saved does not buy.
**It must not be implemented for Step 10.** Its proof that a split cannot
change a record moved to Part B's tests.

## Part B: after Step 10's verdict

One mechanism for every run that goes block by block (matched, curved_pass
run/orbits/vet/turboSETI/recheck). Two guarantees govern it:

- a completed block is scientifically identical whichever worker ran it;
- a crash cannot turn a missing, partial or conflicting result into a
  valid measurement.

**The scheduler knows no science.** It runs a fixed list of blocks through
an existing function (`matched.block`, `curved_pass.block`, ...), publishes
validated records and reports status. It never reads curvature, strength,
ON/OFF matching, thresholds or verdicts. A change that alters a scientific
value is a new measurement needing its own validation, not an optimisation.

**Order may change, membership never.** Crowded blocks are claimed first
(the longest first finishes soonest), but which blocks a run covers is
fixed before it starts (for a frozen experiment, by its config) and never
depends on any result. The run's report checks that every block of the list
is present, whenever it ran; an incomplete run never gives a pass or fail
(as `independent.py verdict` already refuses).

### Stage 1: reliable records (fixed shards kept)

1. **Unique temporary files.** `yoke.write` uses one fixed `.part` name per
   destination, safe for one writer only. Each publication writes to its own
   temporary file, created exclusively in the destination folder, validates
   it, then renames it into place.
2. **`blocks.json` written once**, by the launching process before any
   worker starts; workers only read it.
3. **What a block record must prove before a resume skips it** (else it is
   redone; a record that fails is moved aside, never deleted):

   | property | requirement |
   |---|---|
   | target, session, the six files | exact match |
   | block index | exact match |
   | run configuration | matching hash |
   | scientific code | matching fingerprint (the function closure Step 10 uses) |
   | seed and number of planted signals | matching |
   | schema | valid and complete |
   | state | published by its owner |

   Records written before this (every existing one) lack some of these
   fields. They are kept as they are and never silently taken as a new
   run's; a separate, explicit migration adds the identity a record can be
   shown to have (from its run's metadata and commit), and anything it
   cannot show stays legacy.
4. **The run's own metadata** (not the block records) holds the worker
   count, the BLAS setting, the code commit and the config hash.
5. **Gate:** interrupting a run at random points (during a block, during a
   publication) never leaves a partial record counted, nor a block skipped.

### Stage 2: a shared queue

1. **Claims.** A worker claims a block by creating `claims/block_NNN`
   exclusively. The claim holds the run's id, the block, the worker's
   identity (process id, the process's creation time, a random id, so a
   reused process id is not mistaken for the owner), a generation number,
   and its state (claimed, running, publishing, done, failed).
2. **Taking over.** A claim is abandoned only when its process (id and
   creation time) no longer exists; a long block whose worker is alive keeps
   its claim, however long it runs (no lease expires under a slow crowded
   block). A worker taking over writes generation n+1 by exclusive creation;
   only one can win.
3. **Publishing.** Just before the rename, a worker checks its claim still
   names it at its generation; a stale worker discards its result. The
   records are deterministic (each block's own random stream,
   `default_rng([SEED, k])`), so even a publication racing that check could
   only write the same scientific content; the check keeps the record's
   provenance single.
4. **Admission by memory, per workload.** Each command has its own profile:
   peak memory a block from earlier records (`seti._peak_memory_mb`), plus
   headroom. A worker starts a new block only if its estimate fits the free
   memory; idle workers take more only while memory allows. A heavy vet run
   runs fewer workers than a search. No worker is killed to free memory.
5. **BLAS pinned** to one thread per worker before numpy is imported.
6. **Gate:** two workers never publish one block; a killed worker's claim is
   taken over and its block redone whole.

### Stage 3: the archive and the process lifecycle

1. **One machine-wide archive limit**, around each HTTP request (where
   reading.py's per-process gate sits now), so the cap of 6 (never 8) holds
   across every process. Not a Windows semaphore: a semaphore has no owner,
   and a killed process's permits are never returned. A pool of 6 named
   mutexes instead: a waiter is told when a holder died (an abandoned
   mutex), so no permit is lost. A central download process is the
   alternative if the mutexes prove awkward.
2. **Start/resume, status, stop**, independent of any terminal session:
   status lists workers, the block each holds and for how long, blocks done
   and failed, memory and throughput, and tells a dead worker from one on a
   slow block; stop assigns no more work, lets running blocks finish, and
   only then ends workers.
3. **Gate:** a worker killed mid-download leaves the others running and the
   limit never exceeded.

### Tests (before the scheduler becomes the default)

Against records already stored, every scientific field compared (planted
paths, hits, candidate identities, checks verdicts, recovery classes);
`times`, `finished_utc` and other timestamps excepted:

- 2 clean and 2 crowded blocks of step 4, and its slowest crowded block;
- the same blocks at 1, 3 and N workers;
- a download interrupted; a worker killed during publication; a stale claim
  taken over.

Any difference in a scientific field stops the change.

### Inside a block, only if the tail still dominates

The slow part of a vet block is its planted signals (1,572 s of 1,872), and
of its false candidates the 20 choices of three ON looks are independent.
Spreading either across processes is the riskier step (the planted part
draws from the block's random stream and shares a cache of verdicts), so it
is done only if measurement after stages 1-3 shows crowded blocks still set
the end, with the random draws made up front in order, and the same tests.

Not proposed: threads within a process for the Python-level work (the GIL
keeps them on one core); a GPU path (new code for the search itself, outside
this aim); downloading beyond the archive cap (the server is shared).

## Open questions

1. The archive cap of 6 across the machine is reading.py's own; is it still
   the right figure once more workers fetch at once?
2. Across machines (`--shard i/n`) shares stay fixed; is a shared queue
   across machines worth its cost?
