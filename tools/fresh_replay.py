"""Step 10's measurement replayed from nothing of this checkout (docs/audits.md 16):
the public repository cloned afresh from GitHub, new environments built from
the pinned versions (core: requirements.txt with docs/environments/
core-windows.txt as constraints; turboSETI: docs/environments/
turboseti-windows.txt), the evidence package unpacked as an empty data
folder, and tools/regress_step10.py run there: two of step 10's blocks read
again from Breakthrough Listen's archive, measured by the clone's code and
compared field by field with step 10's records in the package.

What it does not show: another machine, operating system or person. It is
the same PC, Windows and Python; another machine is the step after.

    python tools/fresh_replay.py [EVIDENCE_ZIP]     the newest package in data/evidence/ by default

Writes data/analysis/fresh_replay.json in this checkout: the clone's
commit, each environment's pip freeze hash, the package and its SHA-256, the
regression's record from the clone, and whether it passed. About 1 GB read
from the archive and 2 GB on disk, in the system's temporary folder.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yoke  # noqa: E402

REPO = "https://github.com/Ryan-Clinton/SignalSearchYoke.git"
OUT = yoke.DATA / "analysis" / "fresh_replay.json"


def _run(cmd, cwd=None, env=None, say=print):
    say("$ " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode:
        raise yoke.Refusal("INTERNAL_ERROR", f"{cmd[0]} failed ({r.returncode}):\n{(r.stderr or r.stdout)[-3000:]}")
    return r.stdout


def _venv(where, base_python, say):
    _run([base_python, "-m", "venv", where], say=say)
    py = where / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    _run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"], say=say)
    return py


def _freeze_sha(py):
    text = _run([py, "-m", "pip", "freeze"], say=lambda *_: None)
    return hashlib.sha256(text.encode()).hexdigest(), len(text.splitlines())


def main(zip_path=None, say=print):
    zips = sorted((yoke.DATA / "evidence").glob("ssy-evidence-*.zip"), key=lambda p: p.stat().st_mtime)
    zip_path = Path(zip_path) if zip_path else (zips[-1] if zips else None)
    if not zip_path or not zip_path.exists():
        raise yoke.Refusal("NOT_FOUND", "no evidence package: build one with tools/evidence.py build")
    base_python = getattr(sys, "_base_executable", sys.executable)
    work = Path(tempfile.gettempdir()) / "ssy-fresh-replay"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    clone, data = work / "clone", work / "data"

    _run(["git", "clone", "-q", REPO, clone], say=say)
    commit = _run(["git", "-C", clone, "rev-parse", "HEAD"], say=say).strip()

    core = _venv(work / "core-venv", base_python, say)
    _run([core, "-m", "pip", "install", "-q", "-r", clone / "requirements.txt",
          "-c", clone / "docs" / "environments" / "core-windows.txt"], say=say)
    turbo = _venv(work / "turbo-venv", base_python, say)
    # The freeze is installed as it is, without resolving: the environment it records has sigpyproc 2.0.0 (which
    # asks for numpy 2) beside numpy 1.26.4, and setigen and sigpyproc without some of what they list; pip cannot
    # resolve it, but it is what ran, and turboSETI and setigen import without the rest.
    _run([turbo, "-m", "pip", "install", "-q", "--no-deps", "-r",
          clone / "docs" / "environments" / "turboseti-windows.txt"], say=say)
    turbo_check = subprocess.run([str(turbo), "-m", "pip", "check"], capture_output=True, text=True).stdout
    _run([turbo, "-c", "import turbo_seti, setigen, blimpy"], say=say)

    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if name.startswith("data/"):
                target = data / name.removeprefix("data/")
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()

    env = {k: v for k, v in os.environ.items() if not k.startswith("SSY_")}
    env.update(SSY_DATA=str(data), SSY_TURBOSETI_PYTHON=str(turbo), PYTHONNOUSERSITE="1")
    log = _run([core, "-u", clone / "tools" / "regress_step10.py"], cwd=clone, env=env, say=say)
    say(log)
    regression = json.loads((data / "analysis" / "regress_step10.json").read_text(encoding="utf-8"))

    core_freeze, turbo_freeze = _freeze_sha(core), _freeze_sha(turbo)
    out = {"repository": REPO, "clone_commit": commit,
           "environments": {"core": {"pip_freeze_sha256": core_freeze[0], "packages": core_freeze[1],
                                     "constraints": "docs/environments/core-windows.txt"},
                            "turboseti": {"pip_freeze_sha256": turbo_freeze[0], "packages": turbo_freeze[1],
                                          "pins": "docs/environments/turboseti-windows.txt",
                                          "installed": "pip install --no-deps -r (the freeze as it is)",
                                          "pip_check": turbo_check.splitlines()},
                            "base_python": base_python},
           "evidence": {"file": zip_path.name, "sha256": zip_sha},
           "regression": regression, "passed": bool(regression.get("passed")),
           "not_shown": "another machine, operating system or person (same PC, Windows and Python)",
           "kind": "measured"}
    yoke.write(OUT, out, indent=1, stamp=True)
    say(f"fresh replay at {commit[:7]}: {'passed' if out['passed'] else 'FAILED'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
