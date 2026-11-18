"""The derived evidence behind the published numbers, as one package to
deposit beside the report (docs/reproducing-results.md).

    python tools/evidence.py list              what goes in, by folder, with sizes
    python tools/evidence.py build [OUT_DIR]   write ssy-evidence-COMMIT.zip and its manifest
    python tools/evidence.py check ZIP         every file against the manifest inside it

In: the summary records (data/measurements, step 10's choice and deviations,
the result pages' records), the per-block records they are built from
(data/matched, data/curved_pass, data/analysis), and a consistent copy of
the hit store data/ssy.sqlite (every hit, event, check and run; the table
commands read which blocks were chosen from it). Out: the raw spectra (they
stay in Breakthrough Listen's archive), the chunk indexes and caches,
half-finished work (partial/), locks and logs. Unpacked as the data folder
(SSY_DATA), the tables are made again without reading a spectrum:
matched.py tables, matched_tables.py bliss, curved_pass.py tables,
vet-tables, orbit-tables, turboseti-tables, tools/report.py.

Files go in byte for byte; nothing is rewritten. The manifest gives each
file's SHA-256 and size, the commit and whether the tree had changes, and
lists any record that names a path on the machine that made it (BLISS's
records name its module and response file; the store's runs name the
computer, its injections the files planted in), so nothing in it is a
surprise.
"""
import hashlib
import json
import re
import sqlite3
import subprocess
import tempfile
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import yoke  # noqa: E402

FOLDERS = ("measurements", "step10", "results", "analysis", "matched", "curved_pass")
KEEP = {".json", ".md", ".png", ".svg", ".csv"}
LEAVE_OUT = {"partial", "work"}
MACHINE_PATH = re.compile(rb'(/home/[^/"\s]+|/mnt/[a-z]/|[A-Za-z]:\\\\Users\\\\[^\\"]+|[A-Za-z]:/Users/[^/"]+)')


def files(data=None):
    data = Path(data or yoke.DATA)
    out = []
    for folder in FOLDERS:
        for p in sorted((data / folder).rglob("*")):
            rel = p.relative_to(data)
            if p.is_file() and p.suffix in KEEP and not LEAVE_OUT & set(rel.parts):
                out.append(rel)
    return out


def _git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True).stdout.strip()


def manifest(data=None):
    data = Path(data or yoke.DATA)
    rows, paths = [], {}
    for rel in files(data):
        raw = (data / rel).read_bytes()
        rows.append({"path": rel.as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        found = sorted({m.decode(errors="replace") for m in MACHINE_PATH.findall(raw)})
        if found:
            paths[rel.as_posix()] = found[:5]
    return {"package": "SignalSearchYoke derived evidence", "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                                          time.gmtime()),
            "git_commit": _git("rev-parse", "HEAD"), "uncommitted_changes": bool(_git("status", "--porcelain")),
            "folders": list(FOLDERS), "files": rows, "total_bytes": sum(r["bytes"] for r in rows),
            "machine_paths": paths,
            "store": "data/ssy.sqlite, copied with SQLite's backup (one consistent state); its runs table names "
                     "the computer each run was on",
            "not_included": "raw spectra (Breakthrough Listen Open Data Archive), data/ssy.sqlite, chunk indexes, "
                            "caches, partial work, locks and logs"}


def build(out_dir=None, say=print):
    out_dir = Path(out_dir or yoke.DATA / "evidence")
    man = manifest()
    if man["uncommitted_changes"]:
        say("note: the working tree has changes; the manifest says so")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"ssy-evidence-{man['git_commit'][:7]}.zip"
    part = out.with_suffix(".zip.part")
    with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("MANIFEST.json", json.dumps(man, indent=1))
        for r in man["files"]:
            z.write(yoke.DATA / r["path"], "data/" + r["path"])
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "ssy.sqlite"
            src = sqlite3.connect(f"file:{yoke.DATA / 'ssy.sqlite'}?mode=ro", uri=True)
            dst = sqlite3.connect(copy)
            src.backup(dst)
            dst.close()
            src.close()
            raw_sha = hashlib.sha256(copy.read_bytes()).hexdigest()
            z.write(copy, "data/ssy.sqlite")
            z.writestr("STORE.sha256", raw_sha + "  data/ssy.sqlite\n")
    part.replace(out)
    (out_dir / (out.stem + ".manifest.json")).write_text(json.dumps(man, indent=1), encoding="utf-8")
    say(f"{out}: {len(man['files'])} files, {man['total_bytes'] / 1e6:.0f} MB before compression, "
        f"{out.stat().st_size / 1e6:.0f} MB zipped; {len(man['machine_paths'])} record(s) name machine paths")
    return out


def check(path, say=print):
    with zipfile.ZipFile(path) as z:
        man = json.loads(z.read("MANIFEST.json"))
        bad = [r["path"] for r in man["files"]
               if hashlib.sha256(z.read("data/" + r["path"])).hexdigest() != r["sha256"]]
        if "STORE.sha256" in z.namelist():
            want = z.read("STORE.sha256").decode().split()[0]
            h = hashlib.sha256()
            with z.open("data/ssy.sqlite") as f:
                for chunk in iter(lambda: f.read(1 << 22), b""):
                    h.update(chunk)
            if h.hexdigest() != want:
                bad.append("ssy.sqlite")
    say(f"{path}: {len(man['files']) - len(bad)} of {len(man['files'])} files match the manifest "
        f"(commit {man['git_commit'][:7]})")
    for p in bad:
        say(f"  differs: {p}")
    return not bad


def main(argv):
    what = argv[0] if argv else "list"
    if what == "list":
        by = {}
        for rel in files():
            key = "/".join(rel.parts[:2]) if rel.parts[0] in ("matched", "curved_pass") else rel.parts[0]
            n, b = by.get(key, (0, 0))
            by[key] = (n + 1, b + (yoke.DATA / rel).stat().st_size)
        for k, (n, b) in sorted(by.items()):
            print(f"{k:60s} {n:5d} files {b / 1e6:9.1f} MB")
        print(f"{'all':60s} {sum(n for n, _ in by.values()):5d} files "
              f"{sum(b for _, b in by.values()) / 1e6:9.1f} MB")
    elif what == "build":
        build(argv[1] if len(argv) > 1 else None)
    elif what == "check" and len(argv) > 1:
        sys.exit(0 if check(argv[1]) else 1)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
