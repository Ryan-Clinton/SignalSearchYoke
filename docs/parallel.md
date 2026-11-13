# Using the whole machine: a spec for parallel runs

Status: proposed, not built. Decided 13 November: Step 10 runs as
planned (3 workers a stage, the runner unchanged); reproducibility of the
frozen comparison comes before finishing sooner. Part A is dropped for
Step 10, and Part B (with Part A's record test) is for after its verdict. Written 12 November 2026, while the checks on the
curved second pass's candidates run (6 workers) and Step 10 waits behind them
(docs/comparable.md). Nothing here changes what any measurement computes: the
aim is the same records, sooner.

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

## Part A: now, for Step 10, without touching frozen code

Step 10's code is fingerprinted (config/step10.json): changing matched.py,
curved_pass.py, independent.py or what they import would mean a third freeze.
The runner (a PowerShell script outside the repository's code) is not
fingerprinted, and `--shard i/n` already exists. So:

1. **Worker count from the machine, at the start of each stage**:
   n = min(cores − 2, floor((free RAM − 4 GB reserve) / 2.5 GB)), and at most
   12. With the checks run ended this gives about 12 on this PC, against the 3
   planned.
2. **Shard 0 starts first** and the others start once its `blocks.json` exists,
   closing the race in point 2 above.
3. **BLAS pinned to one thread** per worker (`OPENBLAS_NUM_THREADS=1`,
   `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1` in the environment).
4. **The archive**: Step 10's measure and curved stages read the six files
   from the archive, block by block. With 12 workers the burst could reach
   72 requests. Proposal: start workers 30 s apart so their fetches fall out of
   step, and cap n at 8 for the stages that fetch (48 at most, about 5 on
   average). Open question below.
5. **Proof that the split cannot change a record**, before Step 10 uses it:
   re-measure 4 of step 4's blocks (2 clean, 2 crowded) with the new runner at
   n = 4 and with BLAS pinned, and compare each record with the stored one,
   field by field, everything except `times` and `finished_utc`. Any
   difference stops the change; the records are what the comparison rests on.
6. **Disclosed**: comparable.md says how many workers each stage used and that
   the split was shown not to change records.

Expected gain: Step 4's matched blocks took 12.4 h of worker time for 121
blocks and the curved pass 11.6 h; Step 10 has 61 crowded blocks against
step 4's 20, so more. At 3 workers each stage is roughly 5–7 h; at 8–12,
roughly 1.5–2.5 h, the long tail aside. About half a day saved in all.

## Part B: after Step 10's verdict, in the code

Once nothing is frozen, one shared mechanism for every run that goes block by
block (matched, curved_pass run/orbits/vet/turboSETI/recheck, the sweep's
per-block search where it applies):

1. **`--workers auto|N`** on each such command, replacing hand-started shards.
   `auto` is Part A's formula, with the per-worker memory taken from the
   previous records' peak (seti.py already measures `_peak_memory_mb`) rather
   than a fixed 2.5 GB. `--shard i/n` stays for running across machines.
2. **A shared queue instead of fixed shares**: a worker claims the next block
   by creating `claims/block_NNN` exclusively (`O_CREAT | O_EXCL`), writing its
   process id. A claim whose process is gone is taken over. Slow blocks then no
   longer leave one worker behind. Blocks are claimed in a fixed order, the
   crowded first (the longest first finishes soonest).
3. **Atomic records everywhere**: every block record and `blocks.json` written
   through `yoke.write`; on resume a record counts as done only if it reads as
   JSON of the run's format, so a partial one is redone.
4. **One machine-wide archive gate**: a Windows named semaphore
   (`CreateSemaphoreW`, through ctypes, no new dependency) or, if that proves
   awkward, a fixed set of lock files, so the cap of 6 (never 8) requests in
   flight holds across every process, as reading.py's comment intends.
5. **BLAS pinned** by the worker launcher before numpy is imported.
6. **What the run records**: the run's own metadata (not the block records)
   notes the worker count, the BLAS setting and the code commit.
7. **Inside a block, only if the tail still dominates**: the slow part of a
   vet block is its planted signals (1,572 s of 1,872), and of its false
   candidates the 20 choices of three ON looks are independent. Either could be
   spread across processes. This is the riskier step (the planted part draws
   from the block's random stream and shares a cache of verdicts), so it is
   done only if measurement after items 1–6 shows crowded blocks still set the
   end, with the random draws made up front in order, and the same record test.
8. **The same tests as Part A's item 5**, for each converted command, against
   records already stored, plus a test of the queue: kill a worker mid-block,
   check its claim is taken over and the block redone whole.

Not proposed: threads within a process for the Python-level work (the GIL
keeps them on one core); a GPU path (new code for the search itself, outside
this aim); running the sweep's download in parallel beyond the archive cap
(the server is shared).

## Open questions

1. Is a cap of 8 workers (48 requests at most, about 5 on average) a fair use
   of Breakthrough Listen's server for Step 10's fetching stages, or should
   Part A wait for Part B's machine-wide gate and keep the fetching stages
   lower?
2. Is re-measuring 4 of step 4's blocks enough to show the split cannot
   change a record, or should it be every block of one class?
3. Should Part A's runner change be disclosed as a change to Step 10's plan
   (comparable.md), even though no fingerprinted file changes? Proposed: yes.
