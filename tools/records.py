"""Checks shared by the experiment tools (control_injection.py, independent_injection.py, midlook.py), so each holds
its records to one standard:

- code_problems: a record's version labels are not enough. Every commit that touched the science code after the
  record was made must be listed in NEUTRAL with the reason it moves no result, and a record made with local
  changes must be listed in DIRTY_OK with what they were. A commit added to NEUTRAL is a claim reviewed like code.
- claim: one worker at a time on a block, for tools run in several lanes at once.
"""
import ctypes
import functools
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The modules whose change could move a planted signal's or a candidate's result.
SCIENCE = ("seti.py", "searching.py", "onoff.py", "vetting.py", "check.py", "matched.py", "measure.py", "injection.py",
           "pipelines.py", "reading.py", "tools/turbo_curves.py")

# Commits that touched SCIENCE (or a tool's own file, passed beside it) without moving a result, and why.
NEUTRAL = {
    "77094ad": "reading.py: queued jobs report network errors by exit code; the bytes read are unchanged",
    "ac59d3c": "reading.py: waiting out a network outage, then reading as before; the bytes read are unchanged. "
               "control_injection.py: checks by identity, weighting and leave-one-out, in the analysis only",
    "2e2c8c2": "reading.py: the end of an outage logged only after a good read; the bytes read are unchanged. "
               "control_injection.py: a block's record also carries its versions; the rest is analysis",
    "8f62e94": "vetting.py, check.py: version 6 behind a flag that is off by default; version 5's verdicts unchanged. "
               "control_injection.py: a block's record also carries version 6's verdicts beside version 5's",
    "18bda4f": "control_injection.py: the tables' intervals; not how a block is planted, searched or judged",
    "4dcc81c": "setigen_plant.py, independent_injection.py: Doppler smearing as an option, off by default; each "
               "record carries the setting it was planted with and is checked against it",
    "0259e41": "setigen_plant.py: each smeared signal bounded to the channels it crosses, only with smearing on; the "
               "same placement and power (tests/test_setigen_plant.py)",
    "42f9b04": "midlook.py: a session worked from its last block too; each block's work unchanged",
    "7b9317e": "record checks, block claims and turboSETI's mid-look scoring added beside the tools' block work, which "
               "is unchanged; setigen_plant.py checks the frame's axis more strictly, refusing only, not planting "
               "differently",
    "177861f": "independent_injection.py: a third draw, of another session, and block claims, beside the first two "
               "draws' block work; the project's planting's results written by own_status, the rule they were written "
               "by before; records carry each signal's place from now on",
    "dda5abb": "midlook.py: turbo-tables adds paired intervals from the same block records; each block's work "
               "unchanged",
}

# Records made with local changes, and what those changes were.
DIRTY_OK = {
    "8678e6e": "tools/setigen_plant.py and docs/independent-injection.md, committed next as 0259e41; midlook.py, which "
               "made these records, does not use setigen",
}


# Where the code's history is read. A tree unpacked from git archive has none: tools/evidence.py's reproduce names
# the clone it came from (SSY_HISTORY) and the commit it holds (SSY_HISTORY_HEAD), which stands for HEAD.
HISTORY = os.environ.get("SSY_HISTORY") or str(ROOT)
HISTORY_HEAD = os.environ.get("SSY_HISTORY_HEAD") or "HEAD"


@functools.lru_cache(maxsize=None)
def _changed_since(commit, files):
    got = subprocess.run(["git", "-C", HISTORY, "log", "--format=%h", "--abbrev=7", f"{commit}..{HISTORY_HEAD}", "--",
                          *files], capture_output=True, text=True)
    if got.returncode:
        return None
    return tuple(c[:7] for c in got.stdout.split())


def code_problems(provenance, own=(), files=SCIENCE, neutral=None, dirty_ok=None):
    """Why a record's code cannot be taken as today's: [] when every change since is listed as neutral. `own`: the
    tool's own files, checked beside the science modules."""
    neutral = NEUTRAL if neutral is None else neutral
    dirty_ok = DIRTY_OK if dirty_ok is None else dirty_ok
    commit = str((provenance or {}).get("git_commit") or "")
    if not commit:
        return ["no commit recorded"]
    if (provenance or {}).get("uncommitted_changes") and commit[:7] not in dirty_ok:
        return [f"made at {commit[:7]} with local changes not accounted for"]
    changed = _changed_since(commit, tuple(files) + tuple(own))
    if changed is None:
        return [f"commit {commit[:7]} is not in this repository"]
    unlisted = [c for c in changed if c not in neutral]
    return [f"the science code changed after {commit[:7]}, in {', '.join(unlisted)}"] if unlisted else []


def _alive(pid):
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # os.kill(pid, 0) would end the process on Windows: ask for its exit code instead
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        try:
            return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextmanager
def claim(path):
    """Yields True while this process holds the block whose record is `path` (a `.claim` file beside it, made only
    if absent), False when a live process holds it. A claim left by a process that has ended is taken over."""
    mark = Path(path).with_name(Path(path).name + ".claim")
    mark.parent.mkdir(parents=True, exist_ok=True)
    held = False
    for _ in range(2):
        try:
            fd = os.open(mark, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                pid = int(mark.read_text(encoding="ascii").strip() or 0)
                age = time.time() - mark.stat().st_mtime
            except (OSError, ValueError):
                pid, age = 0, 0.0
            # an empty claim may be one being written: taken over only once it is a minute old
            if _alive(pid) or (pid == 0 and age < 60):
                break
            mark.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(str(os.getpid()))
        held = True
        break
    try:
        yield held
    finally:
        if held:
            mark.unlink(missing_ok=True)
