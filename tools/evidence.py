"""The derived evidence behind the published numbers, as one package to
deposit beside the report (docs/reproducing-results.md).

    python tools/evidence.py list              what goes in, by folder, with sizes
    python tools/evidence.py build [OUT_DIR]   write ssy-evidence-COMMIT.zip and its manifest
    python tools/evidence.py check ZIP         the zip against the manifest inside it
    python tools/evidence.py reproduce ZIP     the tables made again from the zip alone, compared

In: the summary records (data/measurements, step 10's choice and deviations,
the result pages' records), the per-block records they are built from
(data/matched, data/curved_pass, data/analysis), and a consistent copy of
the hit store data/ssy.sqlite (every hit, event, check and run; the table
commands read which blocks were chosen from it). Out: the raw spectra (they
stay in Breakthrough Listen's archive), the chunk indexes and caches,
half-finished work (partial/), locks and logs. Unpacked as the data folder
(SSY_DATA), the tables are made again without reading a spectrum.

Files go in byte for byte; nothing is rewritten. The manifest gives each
file's SHA-256 and size; the store's SHA-256, size and tables (columns and
rows); the commit and whether the tree had changes; and what in the package
names the machine that made it: every record that names a local path
(BLISS's records name its module and response file), the computer names in
the store's runs, and any local path in the store's text. check refuses a
zip with a file missing or changed, an entry the manifest does not list, or
a store that is missing or differs.

reproduce takes the zip alone: the committed code (git archive HEAD) in a
new folder, the zip unpacked as its data folder, so nothing of this
checkout's data/ is reachable; it runs the table commands there (TABLES)
and compares every page and summary record they write with what was there
before they ran (the committed pages, the packaged records), ignoring only
when a record was written and by which commit.
"""
import difflib
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import yoke  # noqa: E402

FOLDERS = ("measurements", "step10", "results", "analysis", "matched", "curved_pass")
KEEP = {".json", ".md", ".png", ".svg", ".csv"}
LEAVE_OUT = {"partial", "work"}
MACHINE_PATH = re.compile(rb'(/home/[^/"\s]+|/Users/[^/"\s]+|/mnt/[a-z]/|[A-Za-z]:\\\\Users\\\\[^\\"]+'
                          rb'|[A-Za-z]:/Users/[^/"]+|\\\\\\\\[A-Za-z0-9_.-]+\\\\|AppData)')
STORE_LIKE = ("%/home/%", "%/Users/%", "%:\\Users\\%", "%AppData%", "%/mnt/%")
STORE = "ssy.sqlite"
# The commands that make the published tables from the records, and the report.
TABLES = (("matched.py", "tables", "KIC8462852"), ("matched_tables.py", "bliss", "KIC8462852"),
          ("curved_pass.py", "tables", "KIC8462852"), ("curved_pass.py", "orbit-tables", "KIC8462852"),
          ("curved_pass.py", "vet-tables", "KIC8462852"), ("curved_pass.py", "turboseti-tables", "KIC8462852"),
          ("tools/report.py",))
# What may differ when a table is made again: when, and by which commit and machine.
STAMP_KEYS = {"provenance", "written_utc", "created_utc", "record"}
STAMP_LINE = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?Z|written \d{4}-|commit [0-9a-f]{7})")


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


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def store_inventory(path):
    """The store's tables, and what in it names the machine: the computer
    names its runs were on, and any text that looks like a local path."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    tables, found = {}, {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
        cols = db.execute(f'PRAGMA table_info("{name}")').fetchall()
        tables[name] = {"rows": db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0],
                        "columns": [f"{c[1]} {c[2]}".strip() for c in cols]}
        for c in cols:
            if c[2].upper() not in ("TEXT", ""):
                continue
            where = " OR ".join(f'"{c[1]}" LIKE ?' for _ in STORE_LIKE)
            rows = db.execute(f'SELECT COUNT(*), MIN("{c[1]}") FROM "{name}" WHERE {where}', STORE_LIKE).fetchone()
            if rows[0]:
                found[f"{name}.{c[1]}"] = {"rows": rows[0], "example": str(rows[1])[:200]}
    hosts = sorted({h for (h,) in db.execute("SELECT DISTINCT host FROM runs") if h}) if "runs" in tables else []
    db.close()
    return {"path": "data/" + STORE, "bytes": path.stat().st_size, "sha256": _sha(path), "tables": tables,
            "computer_names": hosts, "local_paths": found}


def manifest(data=None, store=None):
    data = Path(data or yoke.DATA)
    rows, paths = [], {}
    for rel in files(data):
        raw = (data / rel).read_bytes()
        rows.append({"path": rel.as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        found = sorted({m.decode(errors="replace") for m in MACHINE_PATH.findall(raw)})
        if found:
            paths[rel.as_posix()] = found[:5]
    return {"package": "SignalSearchYoke derived evidence",
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "git_commit": _git("rev-parse", "HEAD"), "uncommitted_changes": bool(_git("status", "--porcelain")),
            "folders": list(FOLDERS), "files": rows, "total_bytes": sum(r["bytes"] for r in rows),
            "records_naming_local_paths": paths,
            "store": store,
            "included": "the records under data/ listed in files, and the hit store data/ssy.sqlite (store), "
                        "copied with SQLite's backup so it is one consistent state",
            "not_included": "raw spectra (Breakthrough Listen Open Data Archive), chunk indexes, caches, "
                            "partial work, locks and logs"}


def build(out_dir=None, say=print):
    out_dir = Path(out_dir or yoke.DATA / "evidence")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / STORE
        src = sqlite3.connect(f"file:{yoke.DATA / STORE}?mode=ro", uri=True)
        dst = sqlite3.connect(copy)
        src.backup(dst)
        dst.close()
        src.close()
        man = manifest(store=store_inventory(copy))
        if man["uncommitted_changes"]:
            say("note: the working tree has changes; the manifest says so")
        out = out_dir / f"ssy-evidence-{man['git_commit'][:7]}.zip"
        part = out.with_suffix(".zip.part")
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr("MANIFEST.json", json.dumps(man, indent=1))
            for r in man["files"]:
                z.write(yoke.DATA / r["path"], "data/" + r["path"])
            z.write(copy, "data/" + STORE)
    part.replace(out)
    (out_dir / (out.stem + ".manifest.json")).write_text(json.dumps(man, indent=1), encoding="utf-8")
    st = man["store"]
    say(f"{out}: {len(man['files'])} files and the store, {man['total_bytes'] / 1e6:.0f} MB of records and "
        f"{st['bytes'] / 1e6:.0f} MB of store before compression, {out.stat().st_size / 1e6:.0f} MB zipped")
    say(f"  naming the machine: {len(man['records_naming_local_paths'])} record(s) with local paths; "
        f"store computer names {st['computer_names']}, local paths in {sorted(st['local_paths']) or 'no column'}")
    return out


def check(path, say=print):
    with zipfile.ZipFile(path) as z:
        man = json.loads(z.read("MANIFEST.json"))
        names = set(z.namelist())
        want = {"MANIFEST.json"} | {"data/" + r["path"] for r in man["files"]}
        bad = []
        for r in man["files"]:
            name = "data/" + r["path"]
            if name not in names:
                bad.append(f"missing: {r['path']}")
            elif hashlib.sha256(z.read(name)).hexdigest() != r["sha256"]:
                bad.append(f"differs: {r['path']}")
        st = man.get("store")
        if not st or not st.get("sha256"):
            bad.append("the manifest gives no store checksum")
        else:
            want.add(st["path"])
            if st["path"] not in names:
                bad.append(f"missing: {st['path']}")
            else:
                h = hashlib.sha256()
                with z.open(st["path"]) as f:
                    for chunk in iter(lambda: f.read(1 << 22), b""):
                        h.update(chunk)
                if h.hexdigest() != st["sha256"]:
                    bad.append(f"differs: {st['path']}")
        bad += [f"not in the manifest: {n}" for n in sorted(names - want) if not n.endswith("/")]
    say(f"{path}: {len(man['files'])} files and the store, commit {man['git_commit'][:7]}: "
        f"{'all match the manifest' if not bad else f'{len(bad)} problem(s)'}")
    for b in bad:
        say(f"  {b}")
    return not bad


def _strip(x):
    if isinstance(x, dict):
        return {k: _strip(v) for k, v in x.items() if k not in STAMP_KEYS}
    if isinstance(x, list):
        return [_strip(v) for v in x]
    return x


def _same(before, after, suffix):
    """Equal but for when and by which commit a record was written."""
    if suffix == ".json":
        try:
            return _strip(json.loads(before)) == _strip(json.loads(after)), []
        except ValueError:
            pass
    a = [ln for ln in before.decode(errors="replace").splitlines() if not STAMP_LINE.search(ln)]
    b = [ln for ln in after.decode(errors="replace").splitlines() if not STAMP_LINE.search(ln)]
    return a == b, list(difflib.unified_diff(a, b, lineterm="", n=0))[2:12]


def _snapshot(*folders):
    return {p: p.read_bytes() for f in folders if f.exists() for p in f.rglob("*") if p.is_file()}


def reproduce(path, keep=None, say=print):
    if not check(path, say):
        return False
    tmp = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="ssy-reproduce-"))
    tree = tmp / "tree"
    tree.mkdir(parents=True)
    head = _git("rev-parse", "--short", "HEAD")
    tar = subprocess.run(["git", "-C", str(ROOT), "archive", "HEAD"], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(tree, filter="data")
    with zipfile.ZipFile(path) as z:
        man = json.loads(z.read("MANIFEST.json"))
        z.extractall(tree, [n for n in z.namelist() if n.startswith("data/")])
    if man["git_commit"][:7] != head:
        say(f"note: the package was built at {man['git_commit'][:7]}, the code is HEAD {head}")
    data = tree / "data"
    watched = (tree / "docs" / "results", tree / "docs" / "report", data / "measurements")
    before = _snapshot(*watched)
    env = dict(os.environ, SSY_DATA=str(data), PYTHONDONTWRITEBYTECODE="1")
    for cmd in TABLES:
        r = subprocess.run([sys.executable, *cmd], cwd=tree, env=env, capture_output=True, text=True)
        say(f"  {' '.join(cmd)}: {'ran' if r.returncode == 0 else f'failed ({r.returncode})'}")
        if r.returncode:
            say("    " + "\n    ".join((r.stderr or r.stdout).strip().splitlines()[-8:]))
            return False
    after = _snapshot(*watched)
    new = sorted(p for p in after if p not in before)
    changed, same = [], 0
    for p in sorted(before):
        if p not in after:
            continue
        if before[p] == after[p]:
            same += 1
            continue
        ok, diff = _same(before[p], after[p], p.suffix)
        if ok:
            same += 1
        else:
            changed.append((p, diff))
    rel = lambda p: p.relative_to(tree).as_posix()  # noqa: E731
    say(f"{path}: made again in {tree}; {same} page(s) and record(s) the same (apart from when and by "
        f"which commit), {len(changed)} different, {len(new)} new")
    for p, diff in changed:
        say(f"  different: {rel(p)}")
        for line in diff:
            say(f"    {line}")
    for p in new:
        say(f"  new: {rel(p)}")
    return not changed


def main(argv):
    what = argv[0] if argv else "list"
    if what in ("-h", "--help", "help"):
        print(__doc__)
    elif what == "list":
        by = {}
        for rel in files():
            key = "/".join(rel.parts[:2]) if rel.parts[0] in ("matched", "curved_pass") else rel.parts[0]
            n, b = by.get(key, (0, 0))
            by[key] = (n + 1, b + (yoke.DATA / rel).stat().st_size)
        for k, (n, b) in sorted(by.items()):
            print(f"{k:60s} {n:5d} files {b / 1e6:9.1f} MB")
        print(f"{'all':60s} {sum(n for n, _ in by.values()):5d} files "
              f"{sum(b for _, b in by.values()) / 1e6:9.1f} MB")
        print(f"{'and the store, ' + STORE:60s} {(yoke.DATA / STORE).stat().st_size / 1e6:21.1f} MB")
    elif what == "build":
        build(argv[1] if len(argv) > 1 else None)
    elif what == "check" and len(argv) > 1:
        sys.exit(0 if check(argv[1]) else 1)
    elif what == "reproduce" and len(argv) > 1:
        sys.exit(0 if reproduce(argv[1], argv[2] if len(argv) > 2 else None) else 1)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
