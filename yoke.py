"""What the scripts need around them: where their data is, the --json
envelope, and keeping a record whole."""
import contextlib
import hashlib
import json
import os
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

def provenance(record_version=1):
    """What made a record: the code's commit, whether any tracked file
    (code, config, patch, environment list) differed from it and a hash of
    how, the libraries, the time."""
    diff_sha = None
    try:
        sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=10).stdout.strip() or None
        changed = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                                      capture_output=True, text=True, timeout=10).stdout.strip())
        if changed:
            diff = subprocess.run(["git", "-C", str(ROOT), "diff", "HEAD", "--binary"], capture_output=True,
                                  timeout=30).stdout
            diff_sha = hashlib.sha256(diff).hexdigest()
    except (OSError, subprocess.SubprocessError):
        sha, changed = None, None
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
            "schema_version": SCHEMA_VERSION,
            "record_version": record_version, "python": platform.python_version(), "libraries": libraries,
            "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def write(path, record, stamp=False, record_version=1, indent=1):
    """Keep `record` at `path` as JSON, whole or not at all."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if stamp and isinstance(record, dict):
        record = dict(record, provenance=provenance(record_version))
    text = json.dumps(record, indent=indent, default=jsonable)
    partial = path.with_name(path.name + ".part")
    with open(partial, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    partial.replace(path)
    return record
