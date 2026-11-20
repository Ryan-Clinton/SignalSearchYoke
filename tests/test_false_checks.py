"""The mended combined interval of the false-candidate rate
(tools/false_checks.py): a class with no candidate keeps its own
uncertainty whether or not the other class has some."""
import unittest

import numpy as np

import synth  # noqa: F401  (paths and a throwaway data folder)
import false_checks as fc

W = {"clean": 61 / 64, "crowded": 3 / 64}


class Interval(unittest.TestCase):
    def test_published_drops_the_empty_class_when_the_other_has_one(self):
        rng = np.random.default_rng(0)
        counts = {"clean": [0] * 61, "crowded": [1, 0, 0]}
        _, (_, hi) = fc.published_interval(counts, W, rng, boot=2000)
        # the crowded class alone, bootstrapped: at most 1/3 of its weight
        self.assertLessEqual(hi, W["crowded"] * 1.0 + 1e-9)

    def test_mended_keeps_the_empty_class(self):
        rng = np.random.default_rng(0)
        counts = {"clean": [0] * 61, "crowded": [1, 0, 0]}
        _, (_, hi_mixed) = fc.mended_interval(counts, W, rng, boot=4000)
        _, (_, hi_pub) = fc.published_interval(counts, W, np.random.default_rng(0), boot=4000)
        self.assertGreater(hi_mixed, hi_pub)

    def test_an_empty_class_reaches_the_exact_poisson_limit(self):
        # Gamma(1, 1/n): its 97.5% point is -ln(0.025)/n = 3.689/n, the exact (Garwood) upper limit for 0 events.
        rng = np.random.default_rng(0)
        _, (_, hi) = fc.mended_interval({"clean": [0] * 100}, {"clean": 1.0}, rng, boot=20000)
        self.assertAlmostEqual(hi, 3.689 / 100, delta=0.003)

    def test_the_estimate_is_unchanged(self):
        counts = {"clean": [0, 2, 1], "crowded": [5, 0]}
        e1, _ = fc.mended_interval(counts, {"clean": 0.5, "crowded": 0.5}, np.random.default_rng(0), boot=200)
        e2, _ = fc.published_interval(counts, {"clean": 0.5, "crowded": 0.5}, np.random.default_rng(0), boot=200)
        self.assertAlmostEqual(e1, 0.5 * 1.0 + 0.5 * 2.5)
        self.assertAlmostEqual(e1, e2)



class Look:
    def __init__(self, on, hits):
        self.on, self.hits, self.fch1, self.foff = on, hits, 2000.0, -2.79e-6


def event(matches, label="candidate"):
    return {"label": label, "matches": matches, "frequency_mhz": 2000.0, "drift_hz_s": 0.1, "snr": 20.0,
            "seed_position": next(p for p, i in enumerate(matches) if i is not None),
            "looks": [{"track_channel": None} for _ in matches]}


def hits():
    return [{"frequency_mhz": 2000.0, "drift_hz_s": 0.1}]


class OurKept(unittest.TestCase):
    """matched._our_kept takes a candidate's members from the ON looks by each look's own flag."""

    def test_alternating_looks_as_published(self):
        import matched
        looks = [Look(p % 2 == 0, hits()) for p in range(6)]
        kept = matched._our_kept(looks, [event([0, None, 0, None, 0, None])], [0, 1, 2, 3, 4, 5])
        self.assertEqual([m[0] for m in kept[0]["members"]], [0, 2, 4])

    def test_on_looks_at_odd_places(self):
        import matched
        ons = (1, 3, 5)
        looks = [Look(p in ons, hits()) for p in range(6)]
        kept = matched._our_kept(looks, [event([None, 0, None, 0, None, 0])], [0, 1, 2, 3, 4, 5])
        self.assertEqual([m[0] for m in kept[0]["members"]], [1, 3, 5])


def kept(*keys):
    """A kept candidate whose members are hits (look, index)."""
    return {"members": [[lk, i, 0.0, 0.0] for lk, i in keys]}


class Records(unittest.TestCase):
    def test_assignment_stats(self):
        by = {"(0, 1, 2)": [kept((0, 1)), kept((2, 5))], "(0, 1, 3)": [kept((0, 1))], "(1, 2, 3)": []}
        per, union, recur = fc.assignment_stats(by)
        self.assertEqual(sorted(per), [0, 1, 2])
        self.assertEqual(union, 2)                    # the hit (0, 1) is one signal in two choices
        self.assertEqual(sorted(recur), [1, 2])

    def test_window_groups_by_block_number(self):
        per = {0: ("clean", 1), 1: ("clean", 2), 5: ("clean", 3), 6: ("crowded", 9), 7: ("crowded", 4)}
        got = fc.window_groups(per, 4)
        self.assertEqual(got["clean"], [[1, 2], [3]])
        self.assertEqual(got["crowded"], [[9, 4]])

    def test_partition_single_link_within_reach(self):
        pts = [(1.000, 0.0), (1.002, 0.0), (1.004, 0.0), (1.010, 0.0)]
        g = fc._partition(pts, 3e-3, lambda a, b: abs(a[0] - b[0]) <= 3e-3)
        self.assertEqual(len(set(g)), 2)
        self.assertEqual(g[0], g[2])                  # chained through the middle point

    def test_conservative_holds_zero_when_nothing_is_counted(self):
        lo, hi = fc.class_interval([0] * 50, np.random.default_rng(0))
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 3.689 / 50, delta=0.002)



class TimeOrderEndToEnd(unittest.TestCase):
    """A synthetic cadence with a tone in looks 1, 3 and 5 only: called ON as
    (1, 3, 5), the published ON, OFF pairs and time order must keep the same
    candidate with the same member hits; called ON as (0, 2, 4), neither keeps it."""

    def test_both_orders_keep_the_same_candidates(self):
        import math
        import matched
        import measure
        cad = synth.cadence(5)
        sigma = float(np.median(cad[1]["sigma"]))
        planted = []
        for j, c in enumerate(cad):
            raw = c["raw"]
            if j in (1, 3, 5):
                dt = (c["s"]["tstart"] - cad[0]["s"]["tstart"]) * 86400
                x = 8000.3 + 0.2 * dt / (c["s"]["foff"] * 1e6)
                raw = measure.plant(raw, [(x, 0.2, 60 * sigma / math.sqrt(raw.shape[0]))], c["s"]["tsamp"],
                                    c["s"]["foff"])
            planted.append(dict(c, raw=raw, spectra=raw, s=dict(c["s"], spectra=raw)))
        searched = matched.our_search(planted)

        def kept(f, ons):
            looks, events, order = f(planted, searched, ons, 10, [{} for _ in range(6)])
            return sorted(sorted(matched._hit_key(m) for m in ev["members"])
                          for ev in matched._our_kept(looks, events, order))
        pairs = kept(matched.our_events, (1, 3, 5))
        time_order = kept(fc._judge_in_time_order, (1, 3, 5))
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs, time_order)
        self.assertEqual(sorted(k[0] for k in pairs[0]), [1, 3, 5])
        self.assertEqual(kept(matched.our_events, (0, 2, 4)), [])
        self.assertEqual(kept(fc._judge_in_time_order, (0, 2, 4)), [])

if __name__ == "__main__":
    unittest.main()
