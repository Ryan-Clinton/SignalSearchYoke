"""An outage of a server this project does not control must not end a long job, and a wrong answer from it must."""
import synth  # noqa: F401  (first: the tests' own data folder)

import json
import os
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


class TablesNeedTheWholeControl(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="ssy-controls-"))
        (self.folder / "sweeps").mkdir()
        self.chosen = [{"target": "A", "session": "S1"}, {"target": "B", "session": "S2"}]

    def write(self, target, session, done):
        block = {"complete": True, "events": []}
        rec = {"blocks": [[0, 1], [1, 2]], "done": {str(k): block for k in range(done)}}
        (self.folder / "sweeps" / f"{target}-{session}.json").write_text(json.dumps(rec), encoding="utf-8")

    def tables(self):
        with mock.patch.object(negative_controls, "CONTROLS", self.folder), \
                mock.patch.object(negative_controls, "_choice", return_value={"chosen": self.chosen}), \
                mock.patch.object(yoke, "write") as wrote:
            try:
                return negative_controls.tables(say=lambda *a: None), wrote
            except yoke.Refusal as e:
                self.assertFalse(wrote.called)
                return None, e

    def test_a_cadence_not_swept_is_refused(self):
        self.write("A", "S1", 2)
        got, why = self.tables()
        self.assertIsNone(got)
        self.assertIn("S2: not swept yet", str(why))

    def test_a_cadence_part_swept_is_refused(self):
        self.write("A", "S1", 2)
        self.write("B", "S2", 1)
        got, why = self.tables()
        self.assertIsNone(got)
        self.assertIn("S2: 1 of 2 blocks", str(why))

    def test_the_whole_control_is_tabled(self):
        self.write("A", "S1", 2)
        self.write("B", "S2", 2)
        got, _ = self.tables()
        self.assertEqual(got["over_all"]["blocks"], 4)


if __name__ == "__main__":
    unittest.main()
