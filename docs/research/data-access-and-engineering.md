# Research: data access, speed and engineering

Research notes for the overhaul ([../overhaul.md](../overhaul.md)), 8 November
2026. Measured from this PC (Windows 11, Ryzen 9 3950X, 40 GB, GTX 1080, UK)
against the cadence's ON scan 31 file on `bldata.berkeley.edu` (scan 33 for
the index test); about 185 MB downloaded in all. UNVERIFIED marks what could
not be confirmed.

## Measurements

**The server and the file layout**

- nginx 1.21; supports byte ranges, keep-alive and multi-range requests
  (answers `multipart/byteranges`). HTTP/1.1 only (ALPN offers no h2). File
  ETag `"5df8840a-3a2e76858"`, Last-Modified 2019-12-17.
- Dataset (16, 1, 322,961,408) float32; each chunk is **(1, 1, 1048576)**: one
  spectrum of one coarse channel, filter 32008 (bitshuffle + LZ4).
- A chunk is about 3.1 MB compressed vs 4.19 MB raw (ratio 1.35).
- A block in one look is 16 chunks about 1 GB apart: 16 separate ranges,
  about 50 MB of real data. Across six looks **about 300 MB per block, not
  880 MB.**

**Latency and throughput**

- Round trip about 165 ms (UK to Berkeley).
- `requests.get` without a Session: **0.88–0.98 s per request** (a new TCP and
  TLS handshake each time). With a Session: **0.165 s** after the first.
- One stream reaches only **2–3.8 MB/s** (TCP window over that distance).
- The 16 chunks of one look in parallel: 4 streams **11.0 MB/s**, 16 streams
  **13.7 MB/s**; near a ceiling, link or server not established (UNVERIFIED).

**The current `read_slice` on one look's block**

- **91 s** for 35 requests of 4 MB: **147 MB transferred for 50 MB of data**.
- `io.BufferedReader(buffer_size=4 MB)` turns every small HDF5 metadata read
  (B-tree nodes) into a 4 MB fetch with no keep-alive: hence 880 MB per
  block, about 3× what is needed.

**Opening a file and finding chunks**

- `seti.Remote` (no Session, 64 KB buffer): four chunk lookups took 91
  requests and 118 s. With a Session and a 1 MB buffer: 86 requests, 32 s.
- **fsspec HTTPFileSystem (blockcache, 64 KB) with h5py
  `dataset.id.chunk_iter`**: the **full index of all 4,928 chunks in 17 s**,
  93 requests, 6 MB, a 154 KB JSON file.

**Decompression.** 16 chunks (50 MB → 67 MB) in **0.10 s**, by writing raw
chunks into an in-memory HDF5 with `write_direct_chunk` and reading them back
through hdf5plugin. Negligible.

**Search, on one real look (16 × 1,048,573)**

- `flatten`: 1.7 s.
- `search` as written: **52 s** (783 drift steps × 16 `np.roll` calls on 8 MB
  float64 arrays).
- The same algorithm in numpy float32 with slice-adds instead of `np.roll`:
  **3.8 s**, best-SNR array identical to a numba version (max diff 0.0). Not
  yet compared with the original float64 `np.roll` code.
- Numba `prange` (naive, modulo per element): 46 s on 1 thread, 5.1 s on 16,
  2.9 s on 32. **A GPU is not needed.**

**Machine notes**

- The Windows h5py 3.16 wheel has no `ros3` driver.
- GTX 1080 on driver 581.80.

## Where the 20–25 min per block goes

Six looks × (about 90 s of over-fetching, no-keep-alive I/O plus 50–100 s of
`np.roll` search), all in series: roughly **60% network waste, 40% slow
numpy**; decompression negligible. Smaller costs: `find()` queries the API on
every sweep run (7 s), and every block reopens each file and walks its
B-tree again.

## Recommendations, with expected speed-ups

**1. Quick fixes (about 5×, small diff)**

- One `requests.Session` in `Remote`.
- Drop the 4 MB BufferedReader, or use a 64 KB block cache.
- `search` as float32 slice-adds: 52 s → 4 s per look.
- Expected about 4–5 min per block.

**2. Chunk-index cache plus parallel fetch (about 40–50×)**

- Once per file, build `{(t, coarse): (offset, size)}` with fsspec or h5py
  `chunk_iter`, stored as JSON keyed by URL and ETag: 17 s per file, about
  2 min for the whole sweep.
- Per block, fetch the 96 chunk ranges with `ThreadPoolExecutor(8)` (a Session
  per thread) or fsspec `cat_ranges`; decode in memory; run the numpy search;
  overlap the fetch of block k+1 with the search of block k.
- Expected about 25–30 s per block (300 MB at 11–14 MB/s ≈ 25 s; search
  6 × 4 s in threads): **296 blocks in about 2–2.5 h instead of about 4–5
  days.**
- A hand-rolled kerchunk. Real kerchunk needs zarr plus a numcodecs bitshuffle
  codec (imagecodecs; header handling UNVERIFIED): more dependencies for no
  gain. ros3 is unavailable on Windows; HTTP/2 is not offered, so aiohttp and
  threads are equivalent here.

**3. Contiguous ranges (optional).** The chunks of one time row are adjacent
in frequency, so N consecutive blocks can be fetched as 16 × 6 ranges of
N × 3.1 MB, cutting requests by N.

**4. Politeness toward the server**

- No published rate limit or terms of use found; the opendata page only says
  a query returns at most 500 files.
- Keep about 4–8 concurrent streams (4 already reach 11 MB/s), keep the
  User-Agent, back off on 429/5xx with urllib3 `Retry`, and cite Lebofsky et
  al. 2019 (arXiv:1906.07391). That BL tolerates sustained parallel pulls is
  UNVERIFIED.

**5. GPU, numba and multiprocessing**

- None needed once the search is about 4 s per look.
- If a GPU is ever wanted, Pascal (sm_61) needs CUDA 12.x builds such as
  `cupy-cuda12x`; CUDA 13 dropped Maxwell, Pascal and Volta, and drivers after
  the 580 branch reportedly end Pascal support.
- Processes on Windows (spawn): top-level functions, an
  `if __name__ == "__main__"` guard, no h5py handles or Sessions passed,
  arrays or shared memory instead. Threads are fine here: numpy adds and
  network I/O release the GIL.

**6. Results storage: SQLite, not JSON** (stdlib, transactional, queryable)

- The current record keeps only candidate events; hits labelled interference
  or unconfirmed are thrown away, so recurrence or RFI-history queries are
  impossible.
- No provenance: `sweep` calls `yoke.write` without `stamp`; no file URLs,
  ETags or search parameters.
- `provenance()` silently misses hdf5plugin (no `__version__`; use
  `hdf5plugin.version`).
- Suggested tables:
  - `runs(run_id, started_utc, git_commit, dirty, host, python, libs_json, params_json)`
  - `files(file_id, url, etag, size, session, scan, target, is_on, tstart_mjd, fch1, foff, tsamp)`
  - `blocks(session, block_idx, f_lo, f_hi, status, run_id, bytes, fetch_s, search_s, searched_utc)`,
    primary key (session, block_idx): the resume ledger.
  - `hits(hit_id, run_id, file_id, block_idx, channel, freq_mhz, drift_hz_s, snr, width_ch)`,
    indexed on freq_mhz; all hits kept (about 100 per block).
  - `events(hit_id, label, in_on_json, in_off_json)`
- Cross-session recurrence is then one query. WAL mode, one transaction per
  block, a JSON export for people. Parquet is overkill at this scale.

**7. Engineering practice**

- **Packaging:** `[build-system]` (setuptools),
  `[tool.setuptools] py-modules = ["seti", "yoke", "check"]`,
  `[project.scripts] seti = "seti:main"`, `ssy-check = "check:main"`; then
  `pip install -e .` gives `.venv\Scripts\seti.exe`.
- **Logging:** stdlib `logging` with a `RotatingFileHandler` at
  `data/logs/sweep.log`; one line per block with bytes, fetch seconds, search
  seconds and counts.
- **Resumable runs:** a lock file against two sweeps at once; retries with
  backoff; the ETag checked against the cached index; commit per block, as
  now.
- **Background running:** `schtasks /create /tn SSY-sweep /sc daily /st 01:00
  /tr "C:\Projects\SignalSearchYoke\.venv\Scripts\seti.exe sweep KIC8462852
  --blocks 300"`, "run whether logged on or not", a longer "stop if runs
  longer than", and "wake to run" or `powercfg` so the PC does not sleep.
- **Checks:** a few seconds on tiny synthetic arrays — a planted tone found
  at the right drift; `judge` labels; `channels` and `blank_dc`; the
  chunk-index plus direct-decode path matching h5py on a tiny bitshuffle file;
  **the new search giving identical hits to the old `np.roll` version**.
  Before switching the sweep over, run old and new search on one saved real
  slice and confirm the hit lists match.
- **Small catch:** a test script segfaulted at interpreter exit when an h5py
  File on a Python file object was not closed first. `seti` uses `with`; keep
  that pattern.

## Sources

- https://seti.berkeley.edu/opendata (query limit only; read with curl, as the
  page loops between http and https for the fetcher)
- https://arxiv.org/abs/1906.07391 (Lebofsky et al. 2019)
- https://breakthroughinitiatives.org/opendatasearch
- https://www.tomshardware.com/pc-components/gpus/nvidia-to-drop-cuda-support-for-maxwell-pascal-and-volta-gpus-with-the-next-major-toolkit-release
- https://docs.nvidia.com/cuda/cuda-features-archive/index.html
- https://www.guru3d.com/publish/comments/nvidia-gpu-driver-changes-maxwell-pascal-and-volta-unsupported-after-release-580-series/
