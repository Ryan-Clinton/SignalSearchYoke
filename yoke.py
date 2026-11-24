"""What the scripts need around them: where their data is, the --json
envelope, and keeping a record whole."""
import contextlib
import hashlib
import json
import os
import time
import platform
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("SSY_DATA") or ROOT / "data")
SCHEMAS = ROOT / "schemas"
SCHEMA_VERSION = "1.0"


# --- the --json envelope -------------------------------------------------------

ERRORS = {
    "INVALID_REQUEST": (False, "Check the command's arguments."),
    "INTERNAL_ERROR": (False, "Unexpected failure; see the message."),
    "NOT_FOUND": (False, "Run the step it names first."),
    "NOT_CHECKED": (False, "Run check.py on the store's candidates first."),
    "NOT_MEASURED": (False, "Run the measurement it names first."),
    "SOURCE_CHANGED": (False, "The archive file changed since its results were made: keep them apart (a new session in the store) or recover the version recorded."),
}


class Refusal(SystemExit):
    """A command declining to act, with a stable code; on the command line it
    prints its message and exits non-zero."""

    def __init__(self, code, message):
        assert code in ERRORS, code
        super().__init__(message)
        self.code_name, self.message = code, message


def error(code, message):
    retryable, advice = ERRORS[code]
    return {"code": code, "message": message, "retryable": retryable, "advice": advice}


def envelope(command, data=None, errors=()):
    return {"schema_version": SCHEMA_VERSION, "ok": not errors, "command": command,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": data if data is not None else {}, "warnings": [], "errors": list(errors)}


def jsonable(value):
    """Datetimes and numpy numbers as plain JSON values."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


NETWORK_EXIT = 75              # a job's exit code when a network error ended it (EX_TEMPFAIL): tools/jobs.ps1 runs it again


def main(command, work, as_json=False):
    """Run work(). With as_json, what it prints goes to stderr and one JSON
    envelope to stdout."""
    if not as_json:
        return work()
    with contextlib.redirect_stdout(sys.stderr):
        try:
            result = envelope(command, work())
        except Refusal as refusal:
            result = envelope(command, errors=[error(refusal.code_name, refusal.message)])
        except SystemExit as stop:
            result = envelope(command, errors=[error("INTERNAL_ERROR", str(stop))])
        except Exception as problem:
            traceback.print_exc(file=sys.stderr)
            result = envelope(command, errors=[error("INTERNAL_ERROR", f"{type(problem).__name__}: {problem}")])
    json.dump(result, sys.stdout, indent=1, default=jsonable)
    print()
    raise SystemExit(0 if result["ok"] else 1)


# --- records -------------------------------------------------------------------

def _code_state(root):
    """The checkout's commit, whether any tracked file differs from it, and the diff (bytes, or None)."""
    try:
        sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=10).stdout.strip() or None
        changed = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                                      capture_output=True, text=True, timeout=10).stdout.strip())
        diff = (subprocess.run(["git", "-C", str(root), "diff", "HEAD", "--binary"], capture_output=True,
                               timeout=30).stdout if changed else None)
    except (OSError, subprocess.SubprocessError):
        return None, None, None
    return sha, changed, diff


def _keep_diff(diff):
    """The diff kept under data/provenance/diffs/ by its SHA-256, which is returned."""
    if diff is None:
        return None
    diff_sha = hashlib.sha256(diff).hexdigest()
    kept = DATA / "provenance" / "diffs" / f"{diff_sha}.patch"
    try:
        if not kept.exists():
            kept.parent.mkdir(parents=True, exist_ok=True)
            kept.write_bytes(diff)
    except OSError:
        pass
    return diff_sha


# The code as this process loaded it: a long run's modules are the ones there when it started, so its records
# name that commit and those changes, not whatever the checkout holds when each record is written.
_STARTED = {ROOT: _code_state(ROOT)}


def provenance(record_version=1):
    """What made a record: the code's commit as the process started, whether any
    tracked file (code, config, patch, environment list) differed from it and a
    hash of how (the diff itself kept under data/provenance/diffs/, so a record
    made with local changes can be made again exactly), the command and a hash
    of the script it ran (which may not be committed yet), the libraries, the
    time. If the checkout changed while the process ran, what it holds now is
    recorded beside it (`code_changed_while_running`), since a module imported
    late would come from there."""
    now = _code_state(ROOT)
    sha, changed, diff = _STARTED.get(ROOT) or now
    diff_sha = _keep_diff(diff)
    moved = None
    if ROOT in _STARTED and (now[0], now[2]) != (sha, diff):
        moved = {"git_commit": now[0], "uncommitted_changes": now[1], "uncommitted_diff_sha256": _keep_diff(now[2])}
    script = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    try:
        where = str(script.resolve().relative_to(ROOT)).replace("\\", "/") if script else None
    except ValueError:
        where = script.name
    script_sha = (hashlib.sha256(script.read_bytes()).hexdigest()
                  if script is not None and script.is_file() else None)
    libraries = {}
    for name in ("numpy", "h5py", "hdf5plugin", "requests"):
        try:
            module = __import__(name)
            # hdf5plugin has no __version__: its version is hdf5plugin.version
            libraries[name] = str(getattr(module, "__version__", None) or getattr(module, "version"))
        except (ImportError, AttributeError):
            libraries[name] = None
    try:
        import h5py
        libraries["hdf5"] = h5py.version.hdf5_version
    except ImportError:
        pass
    return {"git_commit": sha, "uncommitted_changes": changed, "uncommitted_diff_sha256": diff_sha,
            "command": ([where] + [str(a) for a in sys.argv[1:]]) if where else None, "script_sha256": script_sha,
            "schema_version": SCHEMA_VERSION,
            "record_version": record_version, "python": platform.python_version(), "libraries": libraries,
            "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            **({"code_changed_while_running": moved} if moved else {})}


def remove_tree(path):
    """A folder removed whole, read-only files too (git's objects are read-only on Windows)."""
    import shutil
    import stat

    def again(func, where, *_):
        os.chmod(where, stat.S_IWRITE)
        func(where)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=again)
    else:
        shutil.rmtree(path, onerror=again)


def whole(path, valid=None):
    """Whether a record is there, parses whole and (with `valid`, a test of the record) is complete. One
    that does not parse, or fails `valid`, is moved aside to <name>.bad-<utc>-<random>, so its block is made
    again and the bytes are kept to look at. One that cannot be read at all (locked, unreadable) is not
    moved: the error is raised."""
    path = Path(path)
    if not path.exists():
        return False
    raw = path.read_bytes()                     # an OSError here is raised, not taken for a broken record
    try:
        rec = json.loads(raw.decode("utf-8"))
        ok = valid is None or bool(valid(rec))
    except (ValueError, UnicodeDecodeError, AttributeError, KeyError, TypeError):
        ok = False
    if not ok:
        path.replace(path.with_name(f"{path.name}.bad-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-"
                                    f"{os.urandom(3).hex()}"))
    return ok


def write(path, record, stamp=False, record_version=1, indent=1):
    """Keep `record` at `path` as JSON, whole or not at all."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if stamp and isinstance(record, dict):
        record = dict(record, provenance=provenance(record_version))
    text = json.dumps(record, indent=indent, default=jsonable)
    # each writer its own temporary file, so two writing the same record cannot write into one
    partial = path.with_name(f"{path.name}.{os.getpid()}.{os.urandom(4).hex()}.part")
    with open(partial, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    # On Windows a replace can be refused while another writer is replacing the same file: try again for a
    # while, and never leave the temporary file behind
    try:
        for attempt in range(50):
            try:
                partial.replace(path)
                break
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        if partial.exists():
            partial.unlink()
    return record
