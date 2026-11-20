"""The derived evidence behind the published numbers, as one package to
deposit beside the report (docs/reproducing-results.md).

    python tools/evidence.py list              what goes in, by folder, with sizes
    python tools/evidence.py build [OUT_DIR]   write ssy-evidence-COMMIT.zip and its manifest
    python tools/evidence.py check ZIP         the zip against the manifest inside it
    python tools/evidence.py reproduce ZIP     the tables made again from the zip alone, compared

In: the summary records (data/measurements, steps 10 and 12's choices, deviations and step 12's saved
archive replies,
the result pages' records), the per-block records they are built from
(data/matched, data/curved_pass, data/analysis), and a consistent copy of
the hit store data/ssy.sqlite (every hit, event, check and run; the table
commands read which blocks were chosen from it). Out: the raw spectra (they
stay in Breakthrough Listen's archive), the chunk indexes and caches,
half-finished work (partial/), locks and logs. Unpacked as the data folder
(SSY_DATA), the tables are made again without reading a spectrum.

Files go in as they are but for one substitution (scrub): the names of
the machine that made them. Every home folder is written `~` (BLISS's
records name its module and response file under one), and every computer
name the store's runs give is written COMPUTER, in the records and in the
store's copy (wiped from its file, not just unlinked). The build is
refused if anything packaged still names the machine. The manifest gives
each file's SHA-256 and size as packaged, and its original SHA-256 where
the substitution changed it; the store's SHA-256 (packaged and original),
size and tables; the commit and whether the tree had changes; and what was
substituted, by count. check refuses a zip with a file missing or changed,
an entry the manifest does not list, or a store that is missing or
differs.

reproduce takes the zip alone: the code of the commit the package was
built at (git archive; a package built from a tree with changes is
refused) in a new folder, the zip unpacked as its data folder, so nothing
of this checkout's data/ is reachable; it runs the table commands there
(TABLES) and compares every page and summary record they write with what
was there before they ran (that commit's pages, the packaged records). It
fails on an output missing, new or changed in anything but its stamps
(STAMP_KEYS, STAMP_TIME, STAMP_WRITTEN).
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

FOLDERS = ("measurements", "step10", "step12", "results", "analysis", "matched", "curved_pass")
KEEP = {".json", ".md", ".png", ".svg", ".csv", ".txt"}     # .txt: step 12's saved archive replies
LEAVE_OUT = {"partial", "work"}
MACHINE_PATH = re.compile(rb'(/home/[^/"\s]+|/Users/[^/"\s]+|/mnt/[a-z]/|[A-Za-z]:\\\\Users\\\\[^\\"]+'
                          rb'|[A-Za-z]:/Users/[^/"]+|\\\\\\\\[A-Za-z0-9_.-]+\\\\|AppData)')
STORE_LIKE = ("%/home/%", "%/Users/%", "%:\\Users\\%", "%AppData%", "%/mnt/%")
STORE = "ssy.sqlite"
# The commands that make the published tables from the records, and the report.
TABLES = (("matched.py", "tables", "KIC8462852"), ("matched_tables.py", "bliss", "KIC8462852"),
          ("curved_pass.py", "tables", "KIC8462852"), ("curved_pass.py", "orbit-tables", "KIC8462852"),
          ("curved_pass.py", "vet-tables", "KIC8462852"), ("curved_pass.py", "turboseti-tables", "KIC8462852"),
          ("tools/operating_points.py", ), ("tools/report.py",))
# What may differ when a table is made again, and nothing else: when it was written, by which commit, and
# the machine's Python and libraries (a record's written_utc, and in its provenance GENERATED); in a page,
# the UTC time on its "written by" line and the time and commit after "written" or "finished" in the
# report's list of records. Every other time, value and provenance field is compared.
STAMP_KEYS = {"written_utc"}
GENERATED = {"git_commit", "uncommitted_changes", "uncommitted_diff_sha256", "created_utc", "python", "libraries"}
STAMP_TIME = re.compile(r"\b\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?Z")
STAMP_WRITTEN = re.compile(r"\b(written|finished) \d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?Z, commit (?:[0-9a-f]{7}|None)")


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


# Home folders, and a Windows drive as WSL mounts it (/mnt/c: tools run in WSL, BLISS, quote paths there)
HOME = re.compile(rb'/home/[a-z_][a-z0-9_-]*(?=/)|[A-Za-z]:\\{1,2}Users\\{1,2}[^\\"/]+(?=\\)|/Users/[^/"\s]+(?=/)|/mnt/[a-z](?=/)')
COMPUTER = "COMPUTER"


def scrub(raw, hosts):
    """A record with the machine's names taken out: every home folder made
    `~`, every computer name COMPUTER. Returns (bytes, home folders
    replaced, computer names replaced)."""
    out, homes = HOME.subn(b"~", raw)
    names = 0
    for h in hosts:
        names += out.count(h.encode())
        out = out.replace(h.encode(), COMPUTER.encode())
    return out, homes, names


def _scrub_store(path, hosts):
    """The store's copy without the computer names its runs were on, the
    old values wiped from the file, not just unlinked (secure_delete,
    VACUUM). Refuses if any text column still names the machine."""
    db = sqlite3.connect(path)
    db.execute("PRAGMA secure_delete = ON")
    n = db.execute("UPDATE runs SET host = ? WHERE host IS NOT NULL", (COMPUTER,)).rowcount if hosts else 0
    db.commit()
    db.execute("VACUUM")
    db.close()
    inv = store_inventory(path)
    left = [k for k in inv["local_paths"]]
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
        for c in db.execute(f'PRAGMA table_info("{name}")').fetchall():
            if c[2].upper() in ("TEXT", "") and any(
                    db.execute(f'SELECT 1 FROM "{name}" WHERE "{c[1]}" LIKE ? LIMIT 1', (f"%{h}%",)).fetchone()
                    for h in hosts):
                left.append(f"{name}.{c[1]}")
    db.close()
    raw = path.read_bytes()
    if any(h.encode() in raw for h in hosts) or HOME.search(raw):
        left.append("the file's bytes")
    if left:
        raise yoke.Refusal("INTERNAL_ERROR", f"the store's copy still names the machine in {sorted(set(left))}; "
                                             "nothing packaged")
    return n, inv


def manifest(rows, store, substituted):
    return {"package": "SignalSearchYoke derived evidence",
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "git_commit": _git("rev-parse", "HEAD"),
            "uncommitted_changes": bool(_git("status", "--porcelain", "--untracked-files=no")),
            "folders": list(FOLDERS), "files": rows, "total_bytes": sum(r["bytes"] for r in rows),
            "store": store,
            "machine_names_substituted": substituted,
            "included": "the records under data/ listed in files, and the hit store data/ssy.sqlite (store), "
                        "copied with SQLite's backup so it is one consistent state",
            "not_included": "raw spectra (Breakthrough Listen Open Data Archive), chunk indexes, caches, "
                            "partial work, locks and logs"}


def build(out_dir=None, say=print):
    """The package: every record and a copy of the store, with the machine's
    names substituted (scrub) and nothing else changed. Each record whose
    bytes changed keeps its original SHA-256 in the manifest beside the
    packaged one; the build is refused if anything packaged still names the
    machine."""
    out_dir = Path(out_dir or yoke.DATA / "evidence")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / STORE
        src = sqlite3.connect(f"file:{yoke.DATA / STORE}?mode=ro", uri=True)
        dst = sqlite3.connect(copy)
        src.backup(dst)
        dst.close()
        src.close()
        original_store = _sha(copy)
        hosts = store_inventory(copy)["computer_names"]
        store_rows, inv = _scrub_store(copy, hosts)
        inv["original_sha256"] = original_store
        rows, packed, homes, names, left = [], {}, 0, 0, []
        for rel in files():
            raw = (yoke.DATA / rel).read_bytes()
            out, h, n = scrub(raw, hosts)
            row = {"path": rel.as_posix(), "bytes": len(out), "sha256": hashlib.sha256(out).hexdigest()}
            if out != raw:
                row["original_sha256"] = hashlib.sha256(raw).hexdigest()
                homes, names = homes + h, names + n
            if MACHINE_PATH.search(out) or any(x.encode() in out for x in hosts):
                left.append(rel.as_posix())
            rows.append(row)
            packed[rel.as_posix()] = out
        if left:
            raise yoke.Refusal("INTERNAL_ERROR", f"{len(left)} record(s) still name the machine after the "
                                                 f"substitution, e.g. {left[:3]}; nothing packaged")
        substituted = {
            "rule": "every home folder (/home/NAME, C:\\Users\\NAME, /Users/NAME) written as ~, every computer "
                    "name the store's runs give written as " + COMPUTER + "; nothing else changed",
            "records_changed": sum("original_sha256" in r for r in rows),
            "home_folders_replaced": homes, "computer_names_replaced_in_records": names,
            "store_runs_changed": store_rows}
        man = manifest(rows, inv, substituted)
        if man["uncommitted_changes"]:
            say("note: the working tree has changes; the manifest says so")
        out = out_dir / f"ssy-evidence-{man['git_commit'][:7]}.zip"
        part = out.with_suffix(".zip.part")
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr("MANIFEST.json", json.dumps(man, indent=1))
            for r in rows:
                z.writestr("data/" + r["path"], packed[r["path"]])
            z.write(copy, "data/" + STORE)
    part.replace(out)
    (out_dir / (out.stem + ".manifest.json")).write_text(json.dumps(man, indent=1), encoding="utf-8")
    say(f"{out}: {len(rows)} files and the store, {man['total_bytes'] / 1e6:.0f} MB of records and "
        f"{inv['bytes'] / 1e6:.0f} MB of store before compression, {out.stat().st_size / 1e6:.0f} MB zipped")
    say(f"  machine names taken out: {homes} home folder(s) and {names} computer name(s) in "
        f"{substituted['records_changed']} record(s), {store_rows} run(s) in the store; none left")
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


def _strip(record):
    """A record without what says when, by which commit and on which machine it was written: its
    written_utc, and those fields (GENERATED) of its top-level provenance; the rest of its provenance
    is compared."""
    if isinstance(record, dict):
        out = {k: v for k, v in record.items() if k not in STAMP_KEYS}
        if isinstance(out.get("provenance"), dict):
            out["provenance"] = {k: v for k, v in out["provenance"].items() if k not in GENERATED}
        return out
    return record


def _unstamp(text):
    """A page's lines with only the times of its writing taken out: the time on a "written by" line and
    the time and commit after "written" or "finished" in a list of records; any other time stays."""
    out = []
    for ln in text.splitlines():
        ln = STAMP_WRITTEN.sub(r"\1 <utc>, commit <commit>", ln)
        if "written by" in ln.lower():
            ln = STAMP_TIME.sub("<utc>", ln)
        out.append(ln)
    return out


OLD = 946684800        # 2000-01-01: the time every output is given before the tables are made again


def made_by(cmd, page):
    """Whether a page says it is written by this command (in its first lines)."""
    head = "\n".join(page.decode(errors="replace").splitlines()[:6])
    name = " ".join(cmd)
    return f"`{name}`" in head or f"`python {name}`" in head


def not_made_again(touched, pages):
    """What the tables did not make again: a command that wrote nothing, and a page naming a command
    that was not rewritten. touched {command: [paths]}, pages {path: bytes before}."""
    bad = [f"wrote nothing: {' '.join(c)}" for c, ps in touched.items() if not ps]
    done = {p for ps in touched.values() for p in ps}
    for path, page in pages.items():
        for c in touched:
            if made_by(c, page) and path not in done:
                bad.append(f"not made again by {' '.join(c)}: {path}")
    return bad


def same(before, after, suffix):
    """Whether a page or record came out the same but for when and by which
    commit it was written: (same, a few lines of difference)."""
    if suffix == ".json":
        try:
            a, b = _strip(json.loads(before)), _strip(json.loads(after))
            if a == b:
                return True, []
            return False, list(difflib.unified_diff(json.dumps(a, indent=1, sort_keys=True).splitlines(),
                                                    json.dumps(b, indent=1, sort_keys=True).splitlines(),
                                                    lineterm="", n=0))[2:12]
        except ValueError:
            pass
    a, b = _unstamp(before.decode(errors="replace")), _unstamp(after.decode(errors="replace"))
    return a == b, list(difflib.unified_diff(a, b, lineterm="", n=0))[2:12]


def compare(before, after):
    """Every output that was there before must be there after, the same
    apart from its stamps, and nothing may appear that was not there:
    {"same": n, "changed": [(path, diff)], "missing": [...], "new": [...]}."""
    out = {"same": 0, "changed": [], "missing": sorted(p for p in before if p not in after),
           "new": sorted(p for p in after if p not in before)}
    for p in sorted(set(before) & set(after)):
        ok, diff = (True, []) if before[p] == after[p] else same(before[p], after[p], Path(p).suffix)
        if ok:
            out["same"] += 1
        else:
            out["changed"].append((p, diff))
    return out


def _snapshot(*folders):
    return {p: p.read_bytes() for f in folders if f.exists() for p in f.rglob("*") if p.is_file()}


def reproduce(path, keep=None, say=print):
    """The tables made again from the package, with the code of the commit
    it was built at; False on any missing, new or changed output."""
    if not check(path, say):
        return False
    with zipfile.ZipFile(path) as z:
        man = json.loads(z.read("MANIFEST.json"))
    commit = man["git_commit"]
    if man.get("uncommitted_changes"):
        say(f"refused: the package was built from a tree with changes beside {commit[:7]}, so no commit holds "
            "the code that made it; build it again from a clean tree")
        return False
    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}^{{commit}}"],
                      capture_output=True).returncode:
        say(f"refused: commit {commit[:7]}, which the package was built at, is not in this clone; fetch it")
        return False
    tmp = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="ssy-reproduce-"))
    tree = tmp / "tree"
    tree.mkdir(parents=True)
    tar = subprocess.run(["git", "-C", str(ROOT), "archive", commit], capture_output=True, check=True).stdout
    if not hasattr(tarfile, "data_filter"):
        say("refused: this Python's tarfile has no extraction filters (Python 3.11.4 or later, or 3.12+, is needed)")
        return False
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(tree, filter="data")
    with zipfile.ZipFile(path) as z:
        z.extractall(tree, [n for n in z.namelist() if n.startswith("data/")])
    data = tree / "data"
    watched = (tree / "docs" / "results", tree / "docs" / "report", data / "measurements", data / "analysis")
    before = _snapshot(*watched)
    for p in before:                       # every output old, so what the tables write shows
        os.utime(p, (OLD, OLD))
    env = dict(os.environ, SSY_DATA=str(data), PYTHONDONTWRITEBYTECODE="1")
    touched, seen = {}, set()
    for cmd in TABLES:
        r = subprocess.run([sys.executable, *cmd], cwd=tree, env=env, capture_output=True, text=True)
        say(f"  {' '.join(cmd)}: {'ran' if r.returncode == 0 else f'failed ({r.returncode})'}")
        if r.returncode:
            say("    " + "\n    ".join((r.stderr or r.stdout).strip().splitlines()[-8:]))
            return False
        now = {p for f in watched if f.exists() for p in f.rglob("*") if p.is_file() and p.stat().st_mtime > OLD + 1}
        touched[cmd] = sorted(now - seen)
        seen |= now
    pages = {p: b for p, b in before.items() if p.suffix == ".md"}
    missed = not_made_again(touched, pages)
    for m in missed:
        say(f"  {m}")
    res = compare(before, _snapshot(*watched))
    rel = lambda p: p.relative_to(tree).as_posix()  # noqa: E731
    say(f"{path}: made again at {commit[:7]} in {tree}; {res['same']} page(s) and record(s) the same (apart "
        f"from when and by which commit), {len(res['changed'])} different, {len(res['missing'])} missing, "
        f"{len(res['new'])} new")
    for p, diff in res["changed"]:
        say(f"  different: {rel(p)}")
        for line in diff:
            say(f"    {line}")
    for p in res["missing"]:
        say(f"  missing: {rel(p)}")
    for p in res["new"]:
        say(f"  new: {rel(p)}")
    return not (res["changed"] or res["missing"] or res["new"] or missed)


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
