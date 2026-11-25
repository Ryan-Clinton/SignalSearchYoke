"""The sweep's lock: one sweep of a target at a time, sweeps of different
targets at once, and a sweep that waits for another of its target rather
than failing (control C's lanes)."""
import threading
import time
import unittest

import synth  # noqa: F401  (sets SSY_DATA to a fresh folder)

import seti
import yoke


class SweepLock(unittest.TestCase):
    def test_a_second_sweep_of_the_same_target_is_refused(self):
        with seti._Lock("HIP400"):
            with self.assertRaises(yoke.Refusal):
                with seti._Lock("HIP400"):
                    pass
        with seti._Lock("HIP400"):         # let go: taken again
            pass

    def test_sweeps_of_different_targets_run_at_once(self):
        with seti._Lock("HIP400"), seti._Lock("HIP194"):
            pass

    def test_a_waiting_sweep_waits_for_the_other_then_runs(self):
        said, got = [], []
        first = seti._Lock("HIP17147")
        first.__enter__()

        def second():
            with seti._Lock("HIP17147", wait=True, say=said.append, every=0.05):
                got.append(time.monotonic())
        t = threading.Thread(target=second)
        t.start()
        time.sleep(0.3)
        self.assertEqual(got, [])           # still waiting while the first holds it
        self.assertEqual(len(said), 1)      # and said so once
        released = time.monotonic()
        first.__exit__(None, None, None)
        t.join(5)
        self.assertEqual(len(got), 1)
        self.assertGreaterEqual(got[0], released)

    def test_names_that_are_not_file_names_are_made_safe(self):
        self.assertEqual(seti._lock_name("KIC 8462852/x"), "KIC_8462852_x")
        self.assertEqual(seti._Lock("a/b").path.name, "sweep-a_b.lock")

    def test_each_target_logs_to_its_own_file(self):
        a, b = seti._log("HIP400"), seti._log("HIP194")
        self.assertIsNot(a, b)
        self.assertNotEqual(a.handlers[0].baseFilename, b.handlers[0].baseFilename)
        self.assertTrue(a.handlers[0].baseFilename.endswith("sweep-HIP400.log"))
        for h in (*a.handlers, *b.handlers):
            h.close()


if __name__ == "__main__":
    unittest.main()
