"""Every version of every file ever committed, on every branch and tag,
searched for what should not be public, before the repository is.

    python tools/history_scan.py            the findings by kind, values masked
    python tools/history_scan.py --json     the same, as JSON
    python tools/history_scan.py --export DIR
                                            every version of every file written to DIR
                                            (BLOB_PATH), for another scanner to read

It reads each object reachable from any ref once (git rev-list --all
--objects, then git cat-file --batch) and the commits' author and committer
lines. Kinds:

- secret: private keys, cloud and GitHub tokens, Slack and Google keys,
  a password, secret, token or API key given a value in the text;
- address: IPv4 addresses that are not local or documentation ranges;
  e-mail addresses other than GitHub's noreply ones;
- local path: a home folder (/home/NAME, C:\\Users\\NAME, /Users/NAME);
- file: a committed file whose name says key, credential or environment
  file, and any file over 5 MB.

Values are masked (the first four characters), so the output can be kept.
A match is a lead, not a verdict: each is read and judged (docs/releasing.md
has the last judgement).
"""
import json
import re
import subprocess
import sys
import threading
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECRET = {
    "private key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "AWS key": re.compile(rb"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(rb"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "Slack token": re.compile(rb"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "Google key": re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Anthropic or OpenAI key": re.compile(rb"\bsk-(ant-)?[A-Za-z0-9_-]{20,}"),
    "bearer token": re.compile(rb"[Bb]earer\s+[A-Za-z0-9._~+/-]{20,}"),
    "assigned secret": re.compile(rb"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)"
                                  rb"\b\s*[:=]\s*['\"]([^'\"\s]{6,})['\"]"),
}
IPV4 = re.compile(rb"(?<![\d.])((?:\d{1,3}\.){3}\d{1,3})(?![\d.])")
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LOCAL = re.compile(rb"(/home/[a-z_][a-z0-9_-]*|[A-Za-z]:\\{1,2}Users\\{1,2}[A-Za-z0-9_. -]+|/Users/[A-Za-z0-9_.-]+)")
RISKY_NAME = re.compile(r"(^|/)(\.env(\..*)?|id_[rd]sa.*|.*\.(pem|key|p12|pfx|kdbx)|credentials.*|secrets?\..*)$", re.I)
BIG = 5_000_000


def _git(*args, **kw):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True, **kw).stdout


def _ip_public(ip):
    parts = [int(p) for p in ip.split(".")]
    if any(p > 255 for p in parts):
        return False
    a, b = parts[0], parts[1]
    return not (a in (0, 10, 127) or a >= 224 or (a == 169 and b == 254) or (a == 172 and 16 <= b <= 31)
                or (a == 192 and b == 168) or (a, b, parts[2]) in ((192, 0, 2), (198, 51, 100), (203, 0, 113))
                or parts[3] == 0 and parts[2] == 0)


def mask(v):
    v = v if isinstance(v, str) else v.decode(errors="replace")
    return v[:4] + "*" * min(8, max(0, len(v) - 4))


def scan():
    objects = {}
    for line in _git("rev-list", "--all", "--objects").decode(errors="replace").splitlines():
        sha, _, path = line.partition(" ")
        if path:
            objects.setdefault(sha, set()).add(path)
    commits = len(_git("rev-list", "--all").split())
    found = defaultdict(lambda: defaultdict(set))       # kind -> (what, masked) -> paths
    shas = list(objects)
    proc = subprocess.Popen(["git", "-C", str(ROOT), "cat-file", "--batch"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)
    # Fed from a thread: git answers while it reads, and full pipes both ways would stall.
    def feed():
        proc.stdin.write(("\n".join(shas) + "\n").encode())
        proc.stdin.close()
    threading.Thread(target=feed, daemon=True).start()
    blobs = 0
    for sha in shas:
        header = proc.stdout.readline().split()
        size = int(header[2]) if len(header) == 3 else 0
        body = proc.stdout.read(size)
        proc.stdout.read(1)
        if len(header) != 3 or header[1] != b"blob":
            continue
        blobs += 1
        paths = objects[sha]
        for p in paths:
            if RISKY_NAME.search(p):
                found["file"][("name says key or credential", p)].add(p)
        if size > BIG:
            for p in paths:
                found["file"][(f"over {BIG // 1_000_000} MB ({size / 1e6:.0f} MB)", p)].add(p)
        for what, rx in SECRET.items():
            for m in rx.finditer(body):
                found["secret"][(what, mask(m.group(m.lastindex or 0)))].update(paths)
        for m in IPV4.finditer(body):
            ip = m.group(1).decode()
            if _ip_public(ip):
                found["address"][("IPv4", mask(ip))].update(paths)
        for m in EMAIL.finditer(body):
            e = m.group(0).decode(errors="replace")
            if not e.endswith("users.noreply.github.com") and not e.endswith("noreply@anthropic.com"):
                found["address"][("e-mail", mask(e))].update(paths)
        for m in LOCAL.finditer(body):
            found["local path"][("home folder", m.group(1).decode(errors="replace"))].update(paths)
    proc.wait()
    authors = set(_git("log", "--all", "--format=%an <%ae>%n%cn <%ce>").decode(errors="replace").splitlines())
    return {"refs": _git("for-each-ref", "--format=%(refname)").decode().split(), "commits": commits,
            "objects": len(shas), "blobs": blobs, "paths": len({p for ps in objects.values() for p in ps}),
            "commit_identities": sorted(a.split(" <")[0] + " <" + mask(a.split(" <")[1].rstrip(">")) + ">"
                                        for a in authors if " <" in a),
            "findings": {k: [{"what": w, "value": v, "files": sorted(ps)[:6], "in_files": len(ps)}
                             for (w, v), ps in sorted(d.items())] for k, d in found.items()}}


def export(out):
    """Every version of every committed file, as a plain file in `out`
    named by its object and path, so a scanner that reads files (not git
    history) sees all of the history: detect-secrets scan --all-files DIR."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for line in _git("rev-list", "--all", "--objects").decode(errors="replace").splitlines():
        sha, _, path = line.partition(" ")
        if not path or _git("cat-file", "-t", sha).strip() != b"blob":
            continue
        (out / f"{sha[:10]}_{path.replace('/', '_')}").write_bytes(_git("cat-file", "blob", sha))
        n += 1
    print(f"{n} file versions written to {out}")


def main(argv):
    if "--export" in argv:
        export(argv[argv.index("--export") + 1])
        return
    r = scan()
    if "--json" in argv:
        print(json.dumps(r, indent=1))
        return
    print(f"{len(r['refs'])} refs, {r['commits']} commits, {r['blobs']} file versions at {r['paths']} paths")
    print("commit identities: " + "; ".join(r["commit_identities"]))
    for kind in ("secret", "address", "local path", "file"):
        rows = r["findings"].get(kind, [])
        print(f"\n{kind}: {len(rows) or 'none'}")
        for f in rows:
            print(f"  {f['what']}: {f['value']}  in {f['in_files']} file(s): {', '.join(f['files'][:3])}")


if __name__ == "__main__":
    main(sys.argv[1:])
