"""The tests never touch a real data folder (docs/audits.md 23)."""
import tempfile
import unittest

import synth  # noqa: F401  (paths and a throwaway data folder)

import yoke


class Isolation(unittest.TestCase):
    def test_the_data_folder_is_a_throwaway(self):
        self.assertTrue(str(yoke.DATA).startswith(tempfile.gettempdir()), yoke.DATA)
        import os
        self.assertEqual(yoke.DATA.resolve(), __import__("pathlib").Path(os.environ["SSY_DATA"]).resolve())
        self.assertNotEqual(yoke.DATA.resolve(), (yoke.ROOT / "data").resolve())


if __name__ == "__main__":
    unittest.main()
