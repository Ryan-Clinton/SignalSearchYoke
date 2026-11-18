"""Every script parses; every module that needs nothing beyond
requirements.txt imports; seti.py answers --help."""
import subprocess
import sys
import unittest

import synth  # noqa: F401  (paths and a temporary SSY_DATA)

ROOT = synth.ROOT

# Run only in another environment, or scripts that run on import: parsed, not imported.
ELSEWHERE = {
    "tools/bliss_curves.py": "BLISS's environment (pybliss, WSL)",
    "tools/bliss/backend_components.py": "BLISS's environment (pybliss)",
    "tools/bliss/port_vs_bliss.py": "BLISS's environment (pybliss)",
    "tools/turbo_curves.py": "turboSETI's environment",
    "tools/turbo_events.py": "turboSETI's environment",
    "tools/turbo_local.py": "turboSETI's environment",
    "tools/setigen_frame.py": "turboSETI's environment (setigen)",
    "tools/pickles_block.py": "turboSETI's environment, a script that runs on import",
    "tools/pickles_check.py": "turboSETI's environment, a script that runs on import",
    "tools/pickles_choices.py": "turboSETI's environment, a script that runs on import",
    "tools/bliss_only.py": "a script that runs on import (reads data/)",
}


def scripts():
    return sorted(p for pat in ("*.py", "tools/*.py", "tools/bliss/*.py") for p in ROOT.glob(pat))


class Imports(unittest.TestCase):
    def test_every_script_parses(self):
        for p in scripts():
            with self.subTest(p.relative_to(ROOT).as_posix()):
                compile(p.read_text(encoding="utf-8"), str(p), "exec")

    def test_modules_import(self):
        import importlib
        for p in scripts():
            rel = p.relative_to(ROOT).as_posix()
            if rel in ELSEWHERE:
                continue
            with self.subTest(rel):
                importlib.import_module(p.stem)

    def test_seti_help(self):
        done = subprocess.run([sys.executable, str(ROOT / "seti.py"), "--help"], capture_output=True, text=True,
                              timeout=60, cwd=ROOT)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("find", done.stdout)


if __name__ == "__main__":
    unittest.main()
