"""The evidence for the material findings (docs/audits.md, "Evidence for the
material findings"), checked against the result files themselves: each row
names a finding, its audit, the result file under data/, the commit it was
made at (with "clean" or "local changes") and the command. A row passes when
the file is there and parses, its own provenance names that commit, the
commit is in this checkout's history, and its state is the one the row says.
A row made with local changes passes only if the diff it was made with is
kept (data/provenance/diffs/, from 20 November 2026) or the row says
"diff not kept"; such a result can be tied to its code only through that
diff.

    python tools/ledger.py           every row; exit 1 if any fails
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yoke  # noqa: E402

PLAN = ROOT / "docs" / "audits.md"
HEADING = "## Evidence for the material findings"


def rows(text):
    """The ledger's rows: {finding, audit, result, commit, state, command, note} each."""
    if HEADING not in text:
        return []
    part = text.split(HEADING, 1)[1]
    part = part.split("\n## ", 1)[0]
    out = []
    for line in part.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or cells[0] in ("Finding", "") or set(cells[0]) <= set("-: "):
            continue
        made = re.match(r"`?([0-9a-f]{7,40})`?,?\s*(clean|local changes)(.*)", cells[3])
        out.append({"finding": cells[0], "audit": cells[1], "result": cells[2].strip("`"),
                    "commit": made.group(1) if made else None, "state": made.group(2) if made else None,
                    "note": made.group(3).strip(" ;,()") if made else cells[3], "command": cells[4].strip("`")})
    return out


def _is_ancestor(commit):
    r = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"], capture_output=True)
    return r.returncode == 0


def problems(row, data=None, ancestor=_is_ancestor):
    """What is wrong with one row; [] when it holds."""
    data = Path(data or yoke.DATA)
    if not row["commit"]:
        return ["no commit and state given (`abc1234`, clean | local changes)"]
    path = data / row["result"].removeprefix("data/")
    if not path.is_file():
        return [f"{row['result']} is not there"]
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"{row['result']} does not parse: {e}"]
    prov = rec.get("provenance") if isinstance(rec, dict) else None
    if not isinstance(prov, dict):
        return [f"{row['result']} has no provenance"]
    bad = []
    made = prov.get("git_commit") or ""
    if not made.startswith(row["commit"]):
        bad.append(f"made at {made[:7] or 'no commit'}, not {row['commit']}")
    elif not ancestor(made):
        bad.append(f"{made[:7]} is not in this checkout's history")
    state = "local changes" if prov.get("uncommitted_changes") else "clean"
    if state != row["state"]:
        bad.append(f"made {state}, not {row['state']}")
    if state == "local changes":
        diff = prov.get("uncommitted_diff_sha256")
        kept = diff and (data / "provenance" / "diffs" / f"{diff}.patch").is_file()
        if not kept and "diff not kept" not in row["note"]:
            bad.append("made with local changes whose diff is not kept: the row must say \"diff not kept\"")
    if prov.get("code_changed_while_running") and "changed while running" not in row["note"]:
        bad.append("the checkout changed while it ran: the row must say \"changed while running\" and how")
    if prov.get("command") and row["command"] and prov["command"][0] not in row["command"]:
        bad.append(f"made by {prov['command'][0]}, not {row['command']}")
    return bad


def main():
    found = rows(PLAN.read_text(encoding="utf-8"))
    if not found:
        sys.exit(f"no ledger in {PLAN.name} (a section headed {HEADING!r})")
    failed = 0
    for r in found:
        bad = problems(r)
        failed += bool(bad)
        print(f"{'FAIL' if bad else 'ok  '} {r['result']}: {'; '.join(bad) if bad else r['finding'][:80]}")
    print(f"{len(found) - failed} of {len(found)} rows hold")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
