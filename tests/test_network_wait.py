"""An outage of a server this project does not control must not end a long job, and a wrong answer from it must."""
import synth  # noqa: F401  (first: the tests' own data folder)

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

import reading
import yoke

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import negative_controls  # noqa: E402

URL = "https://example.test/data/file.h5"


def _reply(status, body=b"abcd", start=0):
    r = requests.Response()
    r.status_code = status
    r._content = body
    r.headers["Content-Range"] = f"bytes {start}-{start + len(body) - 1}/100"
    return r


class Waiting(unittest.TestCase):
    def ask(self, replies, waiting=True):
        s = mock.Mock()
        s.get.side_effect = replies
        env = {reading.WAIT_SETTING: "1"} if waiting else {}
        with mock.patch.dict(os.environ, env), mock.patch.object(reading, "session", return_value=s), \
                mock.patch.object(reading.time, "sleep") as sleep, mock.patch("builtins.print") as said:
            try:
                return reading.get_range(URL, 0, 3), sleep, said, s
            finally:
                reading._outage["since"] = None

    def test_a_long_outage_is_waited_out(self):
        outage = [requests.exceptions.ConnectionError("no name")] * 12 + [_reply(503), requests.exceptions.ReadTimeout()]
        got, sleep, said, s = self.ask(outage + [_reply(206)])
        self.assertEqual(got, b"abcd")
        self.assertEqual(s.get.call_count, 15)
        waits = [c.args[0] for c in sleep.call_args_list]
        self.assertEqual(waits[:3], [15, 30, 60])
        self.assertEqual(max(waits), reading.WAIT_MOST)
        lines = [c.args[0] for c in said.call_args_list]
        self.assertEqual(len(lines), 2)                       # when it began and when it ended, not one a try
        self.assertIn("back after", lines[1])

    def test_without_the_setting_it_is_reported(self):
        with self.assertRaises(requests.exceptions.ConnectionError):
            self.ask([requests.exceptions.ConnectionError("no name")], waiting=False)

    def test_a_missing_file_is_not_waited_for(self):
        with self.assertRaises(requests.exceptions.HTTPError):
            self.ask([_reply(404)])

    def test_the_wrong_bytes_are_not_waited_for(self):
        with self.assertRaises(yoke.Refusal):
            self.ask([_reply(200)])

    def test_the_limit_on_requests_is_not_held_while_waiting(self):
        seen = []
        before = reading._gate._value

        def sleeping(_):
            seen.append(reading._gate._value)
        s = mock.Mock()
        s.get.side_effect = [requests.exceptions.ConnectionError("x"), _reply(206)]
        with mock.patch.dict(os.environ, {reading.WAIT_SETTING: "1"}), mock.patch.object(reading, "session", return_value=s), \
                mock.patch.object(reading.time, "sleep", side_effect=sleeping), mock.patch("builtins.print"):
            reading.get_range(URL, 0, 3)
        reading._outage["since"] = None
        self.assertEqual(seen, [before])


class ExitCode(unittest.TestCase):
    """The queue tells an outage from a fault by the job's exit code, whatever the log holds."""

    def run_job(self, body, waiting=True):
        root = str(Path(__file__).resolve().parents[1])
        env = {k: v for k, v in os.environ.items() if k != reading.WAIT_SETTING}
        if waiting:
            env[reading.WAIT_SETTING] = "1"
        code = f"import sys; sys.path.insert(0, {root!r}); import reading, requests\n{body}"
        return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True).returncode

    def test_a_network_error_exits_75(self):
        self.assertEqual(self.run_job("raise requests.exceptions.ConnectionError('no name')"), yoke.NETWORK_EXIT)

    def test_a_fault_after_a_network_error_is_a_fault(self):
        body = ("try:\n    raise requests.exceptions.ConnectionError('requests.exceptions.ConnectionError')\n"
                "except Exception as e:\n    print(repr(e))\nraise ValueError('a real fault')")
        self.assertEqual(self.run_job(body), 1)

    def test_at_a_prompt_it_exits_as_python_does(self):
        self.assertEqual(self.run_job("raise requests.exceptions.ConnectionError('x')", waiting=False), 1)


class TheWholeControl(unittest.TestCase):
    """Planted faults in the choice, the sweep records, the store and the verdicts must each be refused."""
    VERSION = "v"

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="ssy-controls-"))
        (self.folder / "sweeps").mkdir()
        self.chosen = [{"target": t, "session": f"S{t}", "looks": [{"url": f"u{t}{i}"} for i in range(6)]} for t in "ABCD"]
        self.db_path = self.folder / "ssy.sqlite"
        db = sqlite3.connect(self.db_path)
        db.executescript("""CREATE TABLE cadences (cadence TEXT, session TEXT, target TEXT, urls TEXT);
            CREATE TABLE blocks (session TEXT, block_idx INTEGER, f_lo_mhz REAL, f_hi_mhz REAL, status TEXT);
            CREATE TABLE events (event_id INTEGER, session TEXT, block_idx INTEGER, snr REAL, f_start_mhz REAL,
                                 drift_hz_s REAL, label TEXT, superseded_run INTEGER);
            CREATE TABLE checks (event_id INTEGER, lead TEXT, name TEXT, result TEXT, version TEXT, checked_utc TEXT);""")
        for n, c in enumerate(self.chosen):
            db.execute("INSERT INTO cadences VALUES (?,?,?,?)", (c["session"], c["session"], c["target"],
                                                                json.dumps([x["url"] for x in c["looks"]])))
            db.executemany("INSERT INTO blocks VALUES (?,?,?,?, 'done')", [(c["session"], k, k, k + 1) for k in range(2)])
            db.execute("INSERT INTO events VALUES (?,?,0,40,0.5,0,'candidate',NULL)", (n + 1, c["session"]))
            self.evaluate(db, n + 1, "likely interference (indicated: x)", self.VERSION, "t1")
            self.write(c, 2)
        db.commit()
        db.close()

    @staticmethod
    def evaluate(db, event, verdict, version, when):
        db.executemany("INSERT INTO checks VALUES (?,?,?,?,?,?)",
                       [(event, f"L{event}", "1. data", "x", version, when), (event, f"L{event}", "10. report", verdict, version, when)])

    def write(self, c, done, **change):
        make = lambda k: {"complete": True, "from_mhz": k, "to_mhz": k + 1, "search_version": self.VERSION,  # noqa: E731
                          "events": [{"snr": 40}] if k == 0 else []}
        rec = {"blocks": [[0, 1], [1, 2]], "done": {str(k): make(k) for k in range(done)}}
        rec["done"].update(change)
        (self.folder / "sweeps" / f"{c['target']}-{c['session']}.json").write_text(json.dumps(rec), encoding="utf-8")

    def tables(self):
        with mock.patch.object(negative_controls, "CONTROLS", self.folder), \
                mock.patch.object(negative_controls, "_choice", return_value={"chosen": self.chosen}), \
                mock.patch("seti.SEARCH_VERSION", self.VERSION), mock.patch.object(yoke, "write") as wrote:
            try:
                return negative_controls.tables(say=lambda *a: None), wrote
            except yoke.Refusal as e:
                self.assertFalse(wrote.called)
                return None, str(e)

    def edit(self, sql, *args):
        db = sqlite3.connect(self.db_path)
        with db:
            db.execute(sql, args)
        db.close()

    def verdicts(self):
        db = sqlite3.connect(self.db_path)
        try:
            return negative_controls.candidate_verdicts(db, self.VERSION, 2)
        finally:
            db.close()

    def test_the_whole_control_is_tabled(self):
        got, _ = self.tables()
        self.assertEqual((got["over_all"]["blocks"], got["over_all"]["rate_30"]), (8, 0.5))

    def test_a_cadence_not_swept_is_refused(self):
        (self.folder / "sweeps" / "D-SD.json").unlink()
        self.assertIn("SD: not swept yet", self.tables()[1])

    def test_a_cadence_part_swept_is_refused(self):
        self.write(self.chosen[3], 1)
        self.assertIn("SD: 1 of 2 blocks", self.tables()[1])

    def test_a_wrong_block_number_is_refused(self):
        c = self.chosen[1]
        path = self.folder / "sweeps" / "B-SB.json"
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["done"]["99"] = rec["done"].pop("1")
        path.write_text(json.dumps(rec), encoding="utf-8")
        self.assertIn(f"{c['session']}: its block numbers", self.tables()[1])

    def test_a_moved_boundary_is_refused(self):
        self.write(self.chosen[0], 2, **{"1": {"complete": True, "from_mhz": 1.5, "to_mhz": 2, "search_version": "v", "events": []}})
        self.assertIn("not at its boundaries", self.tables()[1])

    def test_another_search_version_is_refused(self):
        self.write(self.chosen[0], 2, **{"1": {"complete": True, "from_mhz": 1, "to_mhz": 2, "search_version": "old", "events": []}})
        self.assertIn("search version", self.tables()[1])

    def test_another_cadence_in_the_store_is_refused(self):
        self.edit("UPDATE cadences SET urls=? WHERE cadence='SC'", json.dumps(["other"] * 6))
        self.assertIn("not the one chosen", self.tables()[1])

    def test_a_block_missing_from_the_store_is_refused(self):
        self.edit("DELETE FROM blocks WHERE session='SA' AND block_idx=1")
        self.assertIn("store's blocks", self.tables()[1])

    def test_a_candidate_missing_from_the_store_is_refused(self):
        self.edit("DELETE FROM events WHERE event_id=1")
        self.assertIn("candidates differ", self.tables()[1])

    def test_fewer_than_four_are_refused(self):
        for chosen in (self.chosen[:3], self.chosen[:3] + [dict(self.chosen[3], session="SA")],
                       self.chosen[:3] + [dict(self.chosen[3], target="A")]):
            with mock.patch.object(negative_controls, "OUT", self.folder):
                (self.folder / "choice.json").write_text(json.dumps({"chosen": chosen}), encoding="utf-8")
                with self.assertRaises(yoke.Refusal):
                    negative_controls._choice()

    def test_one_verdict_each(self):
        self.assertEqual({e["verdict"] for e in self.verdicts()}, {"likely interference (indicated: x)"})

    def test_an_old_version_is_not_read(self):
        self.edit("UPDATE checks SET version='old' WHERE event_id=2")
        with self.assertRaises(yoke.Refusal):
            self.verdicts()

    def test_an_old_verdict_beside_the_current_is_ignored(self):
        db = sqlite3.connect(self.db_path)
        with db:
            self.evaluate(db, 2, "unexplained, strong", "old", "t0")
        db.close()
        got = {e["event_id"]: e["verdict"] for e in self.verdicts()}
        self.assertTrue(got[2].startswith("likely"))

    def test_two_current_evaluations_are_refused(self):
        db = sqlite3.connect(self.db_path)
        with db:
            self.evaluate(db, 2, "unexplained, weak", self.VERSION, "t2")
        db.close()
        with self.assertRaises(yoke.Refusal):
            self.verdicts()

    def test_a_cut_off_evaluation_is_not_a_verdict(self):
        self.edit("DELETE FROM checks WHERE event_id=3 AND name='1. data'")
        with self.assertRaises(yoke.Refusal):
            self.verdicts()


class Replay(TheWholeControl):
    """negative_controls.replay: right package passes as written by tables and summary; a changed one is refused."""

    def package(self):
        folder = self.folder / "package"
        (folder / "sweeps").mkdir(parents=True)
        records = []
        for c in self.chosen:
            text = (self.folder / "sweeps" / f"{c['target']}-{c['session']}.json").read_text(encoding="utf-8")
            (folder / "sweeps" / f"{c['target']}-{c['session']}.json").write_text(text, encoding="utf-8")
            records.append((c, json.loads(text)))
        events = self.verdicts()
        put = lambda n, r: (folder / n).write_text(json.dumps(r), encoding="utf-8")  # noqa: E731
        put("choice.json", {"chosen": self.chosen})
        put("verdicts.json", {"events": events})
        put("tables.json", dict(negative_controls.table_rows(records), provenance={}))
        put("summary.json", dict(negative_controls.summary_rows(records, events), kind="measured", provenance={},
                                 one_wrong_choice_on_the_project_sessions={}))
        self.seal(folder)
        return folder

    @staticmethod
    def seal(folder):
        files = {p.relative_to(folder).as_posix(): negative_controls._sha(p) for p in folder.rglob("*.json")
                 if p.name != "manifest.json"}
        (folder / "manifest.json").write_text(json.dumps({"files": files}), encoding="utf-8")

    def test_a_right_package_replays(self):
        got = negative_controls.replay(self.package(), say=lambda *a: None)
        self.assertTrue(got["tables_same"] and got["summary_same"])

    def test_a_changed_file_is_refused(self):
        folder = self.package()
        path = folder / "verdicts.json"
        path.write_text(path.read_text(encoding="utf-8").replace("likely", "unexplained"), encoding="utf-8")
        with self.assertRaises(yoke.Refusal):
            negative_controls.replay(folder, say=lambda *a: None)

    def test_a_changed_verdict_is_refused_even_when_rehashed(self):
        folder = self.package()
        path = folder / "verdicts.json"
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["events"][0]["verdict"] = "unexplained, strong"
        path.write_text(json.dumps(rec), encoding="utf-8")
        self.seal(folder)
        with self.assertRaises(yoke.Refusal):
            negative_controls.replay(folder, say=lambda *a: None)


class ConsecutiveBlocks(unittest.TestCase):
    def test_bunched_counts_widen_the_interval(self):
        bunched = [0] * 90 + [10] * 10
        spread = ([0] * 9 + [10]) * 10
        a, b = negative_controls._windows95([bunched], 16), negative_controls._windows95([spread], 16)
        self.assertGreater(a[1] - a[0], 2 * (b[1] - b[0]))

    def test_none_stays_none(self):
        self.assertEqual(negative_controls._windows95([[0] * 50], 4), [0.0, 0.0])

    def test_the_mean_is_near_the_rate(self):
        low, high = negative_controls._windows95([[1, 2] * 100], 3)
        self.assertLess(low, 1.5)
        self.assertGreater(high, 1.5)


class ControlSummary(unittest.TestCase):
    """negative_controls.describe: the counts behind the control's write-up, on a small known case."""
    BLOCKS = {("S", 0): True, ("S", 1): False, ("S", 2): False, ("S", 3): True}

    def events(self):
        e = lambda b, snr, v: {"session": "S", "block": b, "snr": snr, "verdict": v}  # noqa: E731
        return [e(1, 40, "interference (shown: OFF looks below the threshold)"), e(1, 35, "likely interference (indicated: x)"),
                e(1, 31, "unexplained, weak"), e(2, 50, "unexplained, strong"), e(0, 12, "unexplained, weak"),
                e(3, 30, "likely interference (indicated: y)")]

    def test_the_counts_at_each_cut(self):
        d = negative_controls.describe(self.events(), self.BLOCKS, 30)
        self.assertEqual((d["candidates"], d["rate"], d["unexplained"], d["blocks_with_any"]), (5, 1.25, 2, 3))
        self.assertEqual(d["by_verdict"], {"interference": 1, "likely interference": 2, "unexplained, strong": 1,
                                           "unexplained, weak": 1})
        self.assertEqual((d["in_the_busiest_block"], d["in_the_three_busiest_blocks"]), (3, 5))
        self.assertEqual((d["candidates_in_complete_blocks"], d["candidates_in_capped_blocks"]), (1, 4))
        self.assertEqual(negative_controls.describe(self.events(), self.BLOCKS, 10)["candidates"], 6)

    def test_a_flipped_block_moves_the_split(self):
        blocks = dict(self.BLOCKS)
        blocks[("S", 1)] = True
        d = negative_controls.describe(self.events(), blocks, 30)
        self.assertEqual((d["candidates_in_complete_blocks"], d["candidates_in_capped_blocks"]), (4, 1))

    def test_a_verdict_not_known_is_refused(self):
        with self.assertRaises(yoke.Refusal):
            negative_controls.verdict_class("probably fine")


if __name__ == "__main__":
    unittest.main()
