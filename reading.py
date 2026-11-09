"""Reading Breakthrough Listen's files over the web, quickly and politely.

A look's finest product (.gpuspec.0000.h5) is HDF5, packed with bitshuffle
in chunks of one spectrum by one coarse channel (1 x 1 x 1,048,576 float32,
about 3.1 MB). Reading a block of the band is 16 such chunks a look. So:

- once per file, the byte offset and size of every chunk are read from its
  HDF5 index (h5py's chunk_iter over a remote file with a 64 KB block
  cache, about 100 small requests) and kept in data/index/, keyed by the
  file's URL and checked against its ETag;
- after that, a block's chunks are fetched by their byte ranges, in
  parallel, and decoded in memory by the same bitshuffle filter h5py uses,
  so the values are the file's own, bit for bit.

Every request goes through one requests.Session per thread (keep-alive: a
fresh TLS handshake to Berkeley costs about 0.9 s against 0.165 s), retries
with back-off on 429 and 5xx, and a limit on requests in flight across the
whole process (THREADS, at most MAX_THREADS), for the server's sake:
Breakthrough Listen publishes no rate limit, so this keeps to a modest one.
"""
import hashlib
import io
import json
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import yoke

TIMEOUT = 120
HEADERS = {"User-Agent": "signalsearchyoke/0.2 (personal SETI search of Breakthrough Listen open data)"}
CACHE_BLOCK = 1 << 16          # bytes: the unit the remote file is read and cached in
CACHE_BLOCKS = 512             # blocks kept (32 MB): enough for an HDF5 file's index
THREADS = 6                    # requests in flight at once, by default
MAX_THREADS = 8                # never more, whatever is asked
INDEX_VERSION = 1
BITSHUFFLE = 32008             # the HDF5 filter id of bitshuffle

_local = threading.local()
_gate = threading.BoundedSemaphore(THREADS)
_gate_size = THREADS
_stats_lock = threading.Lock()
STATS = {"requests": 0, "bytes": 0}


def set_threads(n):
    """How many requests may be in flight at once, 1 to MAX_THREADS."""
    global _gate, _gate_size
    if not 1 <= int(n) <= MAX_THREADS:
        raise yoke.Refusal("INVALID_REQUEST", f"--threads is 1 to {MAX_THREADS}: Breakthrough Listen's server is "
                                              "shared, and 4 streams already reach about 11 MB/s.")
    _gate, _gate_size = threading.BoundedSemaphore(int(n)), int(n)
    return _gate_size


def threads():
    return _gate_size


def session():
    """This thread's Session: kept alive, retried with back-off."""
    s = getattr(_local, "session", None)
    if s is None:
        retry = Retry(total=6, connect=6, read=6, status=6, backoff_factor=1.0,
                      status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET", "HEAD"),
                      respect_retry_after_header=True, raise_on_status=False)
        s = requests.Session()
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=MAX_THREADS)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers.update(HEADERS)
        _local.session = s
    return s


def head(url):
    """The file's size and ETag."""
    with _gate:
        reply = session().head(url, timeout=TIMEOUT, allow_redirects=True)
    reply.raise_for_status()
    return int(reply.headers["Content-Length"]), reply.headers.get("ETag", "")


class Changed(yoke.Refusal):
    """The file on the server is no longer the one its index was built from."""


def get_range(url, start, end, etag=None):
    """Bytes start to end (inclusive) of the file at url, exactly those;
    with `etag`, only from that version of the file. The archive honours
    If-Match on range requests (412 for another ETag, checked 9 November
    2026), so chunks of two versions of a file can never be mixed. (Never
    If-Range: on a mismatch it answers with the whole 15 GB file.)"""
    headers = {"Range": f"bytes={start}-{end}"}
    if etag:
        headers["If-Match"] = etag
    with _gate:
        reply = session().get(url, headers=headers, timeout=TIMEOUT)
    if reply.status_code == 412:
        index_path(url).unlink(missing_ok=True)
        with _index_lock:
            _indexes.pop(url, None)
        raise Changed("INTERNAL_ERROR", f"{url} has changed on the server since its chunk index was built "
                                        f"(ETag {etag}); the index is dropped and will be rebuilt on the next run.")
    reply.raise_for_status()
    # Only the bytes asked for will do: a server that ignores the range answers
    # 200 with the file from its start, which read as the slice would be wrong
    # data with no error.
    expected = f"bytes {start}-{end}/"
    if reply.status_code != 206 or not str(reply.headers.get("Content-Range", "")).startswith(expected):
        raise yoke.Refusal("INTERNAL_ERROR", f"{url} did not answer the range asked for "
                                             f"({reply.status_code}, Content-Range {reply.headers.get('Content-Range')!r}).")
    data = reply.content
    if len(data) != end - start + 1:
        raise yoke.Refusal("INTERNAL_ERROR", f"{url} sent {len(data)} bytes for a range of {end - start + 1}.")
    with _stats_lock:
        STATS["requests"] += 1
        STATS["bytes"] += len(data)
    return data


class Remote(io.RawIOBase):
    """A file on the web read as if it were here, in 64 KB blocks kept in a
    small cache: HDF5's many small index reads cost one request each for a
    new block, not a 4 MB fetch each."""

    def __init__(self, url, size=None, etag=None):
        self.url, self.etag, self.pos, self.fetched, self.requests = url, etag, 0, 0, 0
        self.size = size if size is not None else head(url)[0]
        self.cache = OrderedDict()

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        self.pos = offset if whence == io.SEEK_SET else self.pos + offset if whence == io.SEEK_CUR else self.size + offset
        return self.pos

    def _blocks(self, first, last):
        """Blocks first to last, from the cache or fetched in runs of
        neighbours, one request a run."""
        got, missing = {}, []
        for b in range(first, last + 1):
            if b in self.cache:
                self.cache.move_to_end(b)
                got[b] = self.cache[b]
            else:
                missing.append(b)
        runs = []
        for b in missing:
            if runs and b == runs[-1][1] + 1:
                runs[-1][1] = b
            else:
                runs.append([b, b])
        for a, z in runs:
            start, end = a * CACHE_BLOCK, min((z + 1) * CACHE_BLOCK, self.size) - 1
            data = get_range(self.url, start, end, self.etag)
            self.fetched += len(data)
            self.requests += 1
            for b in range(a, z + 1):
                got[b] = data[(b - a) * CACHE_BLOCK:(b - a + 1) * CACHE_BLOCK]
                self.cache[b] = got[b]
        while len(self.cache) > CACHE_BLOCKS:
            self.cache.popitem(last=False)
        return got

    def readinto(self, buffer):
        if self.pos >= self.size:
            return 0
        n = min(len(buffer), self.size - self.pos)
        first, last = self.pos // CACHE_BLOCK, (self.pos + n - 1) // CACHE_BLOCK
        got = self._blocks(first, last)
        joined = b"".join(got[b] for b in range(first, last + 1))
        offset = self.pos - first * CACHE_BLOCK
        buffer[:n] = joined[offset:offset + n]
        self.pos += n
        return n


def h5():
    try:
        import h5py
        import hdf5plugin  # noqa: F401  (the bitshuffle filter Breakthrough Listen's files are packed with)
    except ImportError:
        raise yoke.Refusal("INVALID_REQUEST", "Reading Breakthrough Listen's files needs h5py and hdf5plugin: "
                                              "pip install -r requirements.txt.")
    return h5py


# --- the chunk index ------------------------------------------------------------

def index_path(url):
    return yoke.DATA / "index" / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".json")


def _attr(v):
    if isinstance(v, bytes):
        return v.decode(errors="replace")
    if hasattr(v, "tolist"):
        return v.tolist()
    return v


def build_index(url, size, etag):
    """Every chunk's place in the file, from its own HDF5 index."""
    h5py = h5()
    remote = Remote(url, size, etag)
    started = time.monotonic()
    with h5py.File(remote, "r") as f:
        data = f["data"]
        dcpl = data.id.get_create_plist()
        filters = []
        for i in range(dcpl.get_nfilters()):
            code, flags, values, _name = dcpl.get_filter(i)
            filters.append([int(code), int(flags), [int(v) for v in values]])
        chunks = []
        data.id.chunk_iter(lambda info: chunks.append(
            [int(x) for x in info.chunk_offset] + [int(info.byte_offset), int(info.size), int(info.filter_mask)]))
        record = {"index_version": INDEX_VERSION, "url": url, "etag": etag, "size": size,
                  "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "build_seconds": None, "requests": None,
                  "shape": [int(x) for x in data.shape], "chunk_shape": [int(x) for x in data.chunks],
                  "dtype": str(data.dtype), "filters": filters,
                  "attrs": {k: _attr(v) for k, v in data.attrs.items()}, "chunks": sorted(chunks)}
    record["build_seconds"] = round(time.monotonic() - started, 1)
    record["requests"] = remote.requests
    return record


_indexes = {}
_index_lock = threading.Lock()


def chunk_index(url):
    """The file's chunk index: kept on disk, rebuilt if the file changed."""
    with _index_lock:
        if url in _indexes:
            return _indexes[url]
    size, etag = head(url)
    path = index_path(url)
    record = None
    if path.exists():
        kept = json.loads(path.read_text(encoding="utf-8"))
        if kept.get("index_version") == INDEX_VERSION and kept.get("etag") == etag and kept.get("size") == size:
            record = kept
    if record is None:
        record = build_index(url, size, etag)
        yoke.write(path, record, indent=None)
    record["_where"] = {(c[0], c[2]): (c[3], c[4], c[5]) for c in record["chunks"]}
    with _index_lock:
        _indexes[url] = record
    return record


def direct_ready(index):
    """Whether the direct path fits this file: float32 data of (time, 1,
    channel) in chunks of one spectrum by a run of channels."""
    shape, chunk = index["shape"], index["chunk_shape"]
    return (len(shape) == 3 and shape[1] == 1 and chunk[0] == 1 and chunk[1] == 1 and index["dtype"] == "float32"
            and len(index["chunks"]) == shape[0] * -(-shape[2] // chunk[2]))


# --- reading chunks directly ----------------------------------------------------

def plan(index, first, last):
    """The chunk requests for channels [first, last) of every spectrum:
    (time, chunk's first channel, offset, size, filter mask)."""
    per = index["chunk_shape"][2]
    out = []
    for t in range(index["shape"][0]):
        for c0 in range((first // per) * per, last, per):
            offset, size, mask = index["_where"][(t, c0)]
            out.append((t, c0, offset, size, mask))
    return out


def decode(index, pieces, first, last):
    """Raw chunks (time, chunk's first channel, bytes, filter mask) turned
    into the (time, channel) float32 array for [first, last), by the file's
    own filter in an in-memory HDF5 file."""
    h5py = h5()
    per = index["chunk_shape"][2]
    n_t = index["shape"][0]
    c_lo = (first // per) * per
    c_hi = -(-last // per) * per
    width = c_hi - c_lo
    code, _flags, values = index["filters"][0] if index["filters"] else (None, 0, [])
    if code == BITSHUFFLE:
        # The filter puts its version and the element size in front of what
        # it is given (0, 3, 4 in Green Bank's files): give it only the rest
        # (block size, compressor), or it reads the doubled list wrongly.
        values = values[3:]
    with h5py.File(io.BytesIO(), "w") as f:
        kwargs = {"compression": code, "compression_opts": tuple(values)} if code is not None else {}
        ds = f.create_dataset("d", shape=(n_t, 1, width), chunks=(1, 1, per), dtype="float32", **kwargs)
        for t, c0, raw, mask in pieces:
            ds.id.write_direct_chunk((t, 0, c0 - c_lo), raw, mask)
        out = ds[:, 0, first - c_lo:last - c_lo]
    return out


def read_many(requests_by_url, threads_hint=None):
    """Channels [first, last) of several files at once: {url: (first,
    last)} -> {url: float32 (time, channel) array}, with the bytes moved
    for each.
    All the chunks of all the files are fetched through one pool, under the
    process-wide limit on requests in flight."""
    indexes = {url: chunk_index(url) for url in requests_by_url}
    tasks = []
    for url, (first, last) in requests_by_url.items():
        for t, c0, offset, size, mask in plan(indexes[url], first, last):
            tasks.append((url, t, c0, offset, size, mask))

    def fetch(task):
        url, t, c0, offset, size, mask = task
        return url, t, c0, get_range(url, offset, offset + size - 1, indexes[url].get("etag")), mask

    with ThreadPoolExecutor(max_workers=threads_hint or _gate_size) as pool:
        fetched = list(pool.map(fetch, tasks))
    by_url = {url: [] for url in requests_by_url}
    moved = {url: 0 for url in requests_by_url}
    for url, t, c0, raw, mask in fetched:
        by_url[url].append((t, c0, raw, mask))
        moved[url] += len(raw)
    out = {url: decode(indexes[url], by_url[url], *requests_by_url[url]) for url in requests_by_url}
    return out, moved


def prepare(urls):
    """The chunk indexes of several files, built in parallel where missing."""
    with ThreadPoolExecutor(max_workers=max(1, min(len(urls), _gate_size))) as pool:
        return list(pool.map(chunk_index, urls))
