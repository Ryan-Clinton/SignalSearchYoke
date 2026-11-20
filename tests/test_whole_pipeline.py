"""The whole pipeline on six synthetic files, from the first byte read to the
ranking (docs/audits.md 23): the files are served over HTTP by a local server
that answers byte ranges and If-Match as the archive does, so the reader runs
as it does on the archive (chunk index from the file's own HDF5 index, ranges,
direct chunk decoding, DC blanking). Then the sweep keeps every hit and event
in the store, the checks run on its candidates, the OFF null is measured and
the candidates are ranked. Planted in the noise:

- in the file's first chunk: a drifting tone in the three ON looks only (a
  candidate), and a zero-drift tone in all six looks (interference);
- in its second: a tone in the ON looks drifting the other way (a
  candidate), and one in the ON looks and one OFF look (not a candidate).

Then a second cadence of the same session (six other scans, one tone in its
ON looks) is swept too: it is kept under a key of its own (SESSION-c2), and
the first cadence's blocks are untouched by it.

(The band runs downward, so the sweep numbers the second chunk block 0:
blocks go lowest frequency first. The test matches by frequency.)

No archive is read. A few minutes at most."""
import synth  # noqa: F401  (first: the tests' own data folder)

import argparse
import hashlib
import http.server
import json
import math
import re
import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np

N_T = 16
PER = 16384                 # channels a chunk, so a block
N_F = 2 * PER               # two blocks
FOFF = synth.FOFF
TSAMP = synth.TSAMP
FCH1 = synth.FCH1
LOOK_S = synth.LOOK_S
SESSION = "AGBT99Z_999_01"
TARGET = "SYNTHSTAR"
OFF_NAMES = ("OFFA", "OFFB", "OFFC")

# (chunk of the file, channel in it at the first look's start, drift Hz/s, looks it is in, kind)
TONES = [
    (0, 5000.3, 0.25, (0, 2, 4), "candidate"),
    (0, 11000.6, 0.0, (0, 1, 2, 3, 4, 5), "everywhere"),
    (1, 6000.2, -0.4, (0, 2, 4), "candidate"),
    (1, 12000.5, 0.15, (0, 1, 2, 4), "in an OFF look"),
]


class _Files(http.server.BaseHTTPRequestHandler):
    """Byte ranges with Content-Range and 206, If-Match against a fixed ETag (412 otherwise), HEAD with the
    size: what reading.py relies on from the archive."""
    root = None

    def log_message(self, *args):
        pass

    def _target(self):
        p = self.root / self.path.lstrip("/")
        return p if p.is_file() else None

    def _etag(self, p):
        return '"' + hashlib.sha1(p.read_bytes()).hexdigest()[:16] + '"'

    def do_HEAD(self):
        p = self._target()
        if not p:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(p.stat().st_size))
        self.send_header("ETag", self._etag(p))
        self.end_headers()

    def do_GET(self):
        p = self._target()
        if not p:
            self.send_error(404)
            return
        if self.headers.get("If-Match") and self.headers["If-Match"] != self._etag(p):
            self.send_error(412)
            return
        data = p.read_bytes()
        m = re.fullmatch(r"bytes=(\d+)-(\d+)", self.headers.get("Range", ""))
        if not m:
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        a, z = int(m.group(1)), min(int(m.group(2)), len(data) - 1)
        self.send_response(206)
        self.send_header("Content-Range", f"bytes {a}-{z}/{len(data)}")
        self.send_header("Content-Length", str(z - a + 1))
        self.send_header("ETag", self._etag(p))
        self.end_headers()
        self.wfile.write(data[a:z + 1])


def _write_look(path, spectra, j):
    """One look as Green Bank's finest product is laid out: (time, 1, channel) float32, chunks of one
    spectrum by one coarse channel, no filter."""
    import h5py
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        f.attrs["CLASS"], f.attrs["VERSION"] = "FILTERBANK", "1.0"
        d = f.create_dataset("data", data=spectra.astype(np.float32).reshape(N_T, 1, N_F), chunks=(1, 1, PER))
        name = TARGET if j % 2 == 0 else OFF_NAMES[j // 2]
        for k, v in {"fch1": FCH1, "foff": FOFF, "nchans": N_F, "tsamp": TSAMP,
                     "tstart": 60000.0 + j * LOOK_S / 86400, "nbits": 32, "nifs": 1, "data_type": 1,
                     "telescope_id": 6, "machine_id": 10, "source_name": name, "src_raj": 0.0, "src_dej": 0.0,
                     "coarse_channel": PER}.items():
            d.attrs[k] = v
    return name


TONES_2 = [(0, 7000.4, 0.35, (0, 2, 4), "candidate")]


def _files(folder, tones=None, scan0=10000, seed=23):
    import measure
    tones_in = TONES if tones is None else tones
    rng = np.random.default_rng(seed)
    names = []
    for j in range(6):
        raw = rng.chisquare(64, size=(N_T, N_F)).astype(np.float64) * 1e3
        sigma = float(np.median(measure.channel_noise(raw)))
        dt = j * LOOK_S
        tones = []
        for block, x0, drift, looks, _ in tones_in:
            if j in looks:
                x = block * PER + x0 + drift * dt / (FOFF * 1e6)
                tones.append((x, drift, 80 * sigma / math.sqrt(N_T)))
        raw = measure.plant(raw, tones, TSAMP, FOFF)
        names.append(f"spliced_blc00_guppi_60000_{scan0 + j}_{'' if j % 2 else 'DIAG_'}"
                     f"{TARGET if j % 2 == 0 else OFF_NAMES[j // 2]}_{j:04d}.gpuspec.0000.h5")
        _write_look(folder / "pipeline" / SESSION / names[-1], raw, j)
    return names


def _mhz(block, x0):
    return FCH1 + (block * PER + x0) * FOFF


class WholePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="ssy-whole-"))
        names = _files(cls.tmp / "www")
        names_2 = _files(cls.tmp / "www", TONES_2, scan0=20000, seed=24)
        _Files.root = cls.tmp / "www"
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Files)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{cls.server.server_address[1]}/pipeline/{SESSION}/"
        cls.urls = [base + n for n in names]
        cls.urls_2 = [base + n for n in names_2]

        import check
        import ranking
        import seti
        import store
        import yoke
        cls.store = store
        # A data folder of its own: other tests leave stores of their own making in the shared one.
        cls.saved = (yoke.DATA, ranking.MEAS)
        yoke.DATA = cls.tmp / "data"
        ranking.MEAS = yoke.DATA / "measurements"
        check.REPORTS = cls.tmp / "leads"
        said = []
        cls.first = seti.sweep(TARGET, count=5, say=said.append, files=(SESSION, cls.urls))
        cls.again = seti.sweep(TARGET, count=5, say=said.append, files=(SESSION, cls.urls))
        db = store.connect()
        cls.first_blocks = store.done_blocks(db, SESSION)
        db.close()
        cls.second = seti.sweep(TARGET, count=5, say=said.append, files=(SESSION, cls.urls_2))
        args = argparse.Namespace(all=False, event=None, rank=False, json=False)
        cls.checked = check.run(args, say=said.append)
        for key in (SESSION, f"{SESSION}-c2"):
            ranking.off_null(say=said.append, session=key, n_blocks=2, tracks=200)
        cls.ranked = ranking.rank(say=said.append)
        cls.checked_again = check.run(args, say=said.append)
        cls.said = said

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        import ranking
        import yoke
        yoke.DATA, ranking.MEAS = cls.saved

    def test_every_block_read_and_searched_completely(self):
        self.assertEqual(self.first["blocks"], 2)
        self.assertEqual(self.first["searched"], 2)
        self.assertEqual(len(self.first["this_run"]), 2)
        self.assertAlmostEqual(self.first["searched_completely_mhz"], self.first["searched_mhz"], places=6)

    def test_a_second_sweep_resumes_without_searching_again(self):
        self.assertEqual(self.again["this_run"], [])
        self.assertEqual(self.again["searched"], 2)

    def test_candidates_are_the_on_only_tones(self):
        found = [(c["frequency_mhz"], c["drift_hz_s"]) for c in self.first["candidates_so_far"]]
        width = abs(FOFF)
        for chunk, x0, drift, looks, kind in TONES:
            # an event's frequency is its seed look's start: the tone's at any of its looks' starts
            at = [_mhz(chunk, x0) + drift * j * LOOK_S / 1e6 for j in looks]
            near = [c for c in found if min(abs(c[0] - f) for f in at) < 20 * width]
            if kind == "candidate":
                self.assertTrue(near, f"the tone at {_mhz(chunk, x0):.6f} MHz is not a candidate: {found}")
                self.assertTrue(any(abs(c[1] - drift) <= 0.05 for c in near), (near, drift))
            else:
                self.assertFalse(near, f"the {kind} tone at {_mhz(chunk, x0):.6f} MHz was made a candidate")
        self.assertEqual(len(found), 2, found)

    def test_the_interference_is_kept_as_interference(self):
        db = self.store.connect()
        f = _mhz(0, 11000.6)
        rows = db.execute("SELECT label FROM events WHERE session=? AND abs(f_start_mhz - ?) < 1e-4"
                          " AND superseded_run IS NULL", (SESSION, f)).fetchall()
        db.close()
        self.assertTrue(rows)
        self.assertNotIn("candidate", [r["label"] for r in rows])

    def test_a_second_cadence_of_the_session_is_kept_apart(self):
        self.assertEqual((self.second["session"], self.second["cadence"]), (SESSION, f"{SESSION}-c2"))
        self.assertEqual(self.second["searched"], 2)
        found = [(c["frequency_mhz"], c["drift_hz_s"]) for c in self.second["candidates_so_far"]]
        self.assertEqual(len(found), 1, found)
        db = self.store.connect()
        self.assertEqual(self.store.done_blocks(db, SESSION), self.first_blocks)      # the first untouched
        db.close()

    def test_every_candidate_checked_once_with_every_check(self):
        import vetting
        self.assertEqual(len(self.checked["checked"]), 3)
        for rec in self.checked["checked"]:
            self.assertEqual(rec["version"], vetting.VERSION)
            self.assertEqual(len(rec["checks"]), vetting.N_CHECKS)
            self.assertIn(rec["verdict"], ("interference", "likely interference", "unexplained, strong",
                                           "unexplained, weak"))
            self.assertTrue((Path(self.tmp / "leads") / f"{rec['lead']}.md").exists())
        self.assertEqual(self.checked_again["checked"], [])          # done once, not again

    def test_the_ranking_ranks_both_with_its_off_null(self):
        self.assertIsNotNone(self.checked["ranking_waits_for"])      # before the OFF null: said, not hidden
        self.assertFalse(self.ranked["partial"])
        s = self.ranked["sessions"][SESSION]
        self.assertEqual(s["calibration"]["off_null"]["file"], f"data/measurements/off_null-{SESSION}.json")
        self.assertEqual(len(s["ranked"]), 2, s["ranked"])
        self.assertEqual(sorted(r["rank"] for r in s["ranked"]), [1, 2])
        s2 = self.ranked["sessions"][f"{SESSION}-c2"]
        self.assertEqual(s2["calibration"]["off_null"]["file"], f"data/measurements/off_null-{SESSION}-c2.json")
        self.assertEqual(len(s2["ranked"]), 1)

    def test_the_store_is_whole(self):
        db = self.store.connect()
        problems = self.store.integrity(db)
        n_files = db.execute("SELECT count(*) FROM files WHERE session=?", (SESSION,)).fetchone()[0]
        db.close()
        self.assertEqual(problems, [])
        self.assertEqual(n_files, 12)

    def test_the_sweep_record_matches_the_store(self):
        import seti
        rec = json.loads(seti.sweep_store(TARGET, SESSION).read_text(encoding="utf-8"))
        self.assertEqual(sorted(rec["done"]), ["0", "1"])
        events = [e for d in rec["done"].values() for e in d["events"]]
        self.assertEqual(len(events), 2)


if __name__ == "__main__":
    unittest.main()
