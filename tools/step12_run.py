"""Step 12 from the freeze to the verdict, as one resumable job for the
queue (tools/jobs.ps1): every stage is independent.py --step 12's own, and
each picks up where it stopped, so a restart runs this again from the top.

1. The regression against step 10 (tools/regress_step10.py) must have
   passed at this very commit; it is run if not.
2. independent.py --step 12 check, sweep, choose.
3. measure and curved, three shards each at once (as step 10 ran them).
4. verdict.
5. Supplementary, not a criterion: BLISS on the measured blocks and its
   hits through this search's cadence test (matched.py bliss, bliss-judge),
   GPU in WSL, waiting while the game (S4_Main) runs. If BLISS cannot read
   the session's files, that is recorded and left out
   (data/step12/bliss_status.json), never adapted.

    python tools/step12_run.py
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yoke  # noqa: E402

PY = sys.executable
TARGET = json.loads((ROOT / "config" / "step12.json").read_text(encoding="utf-8"))["target"]
SHARDS = 3
# Logged by independent.py with each stage (data/step12/deviations.json) and printed with the verdict.
DEVIATION = ("tools/turbo_curves.py sets a 4 GB floor on blimpy's load limit, which follows free memory: "
             "with another program holding the RAM, blimpy kept files on disk and turboSETI refused them "
             "(data shape (1,)); the data read and every hit are unchanged")


def say(text):
    print(time.strftime("%Y-%m-%dT%H:%M:%S ") + text, flush=True)


def run(*args, ok=(0,)):
    say("run: " + " ".join(args))
    done = subprocess.run([PY, "-u", *args], cwd=ROOT)
    if done.returncode not in ok:
        raise SystemExit(f"step12_run: {' '.join(args)} exited {done.returncode}")
    return done.returncode


def head():
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def regression():
    path = yoke.DATA / "analysis" / "regress_step10.json"

    def good():
        if not path.exists():
            return False
        r = json.loads(path.read_text(encoding="utf-8"))
        pv = r.get("provenance", {})
        return r.get("passed") and pv.get("git_commit") == head() and not pv.get("uncommitted_changes")
    if not good():
        run("tools/regress_step10.py")
    if not good():
        raise SystemExit("step12_run: the regression against step 10 has not passed at this commit")
    say("regression against step 10: passed at " + head()[:12])


def parallel(*stages):
    say("run: " + ", ".join(stages) + f", {SHARDS} shards each, at once")
    procs = []
    for stage in stages:
        if stage == "curved":
            # curved_pass.run reads the blocks matched.run writes when it starts (blocks.json)
            cfg = json.loads((ROOT / "config" / "step12.json").read_text(encoding="utf-8"))
            meta = yoke.DATA / "matched" / f"{cfg['target']}-{cfg['session']}" / "blocks.json"
            while not meta.exists():
                if procs and all(p.poll() is not None for p in procs):
                    break
                time.sleep(10)
        procs += [subprocess.Popen([PY, "-u", "independent.py", "--step", "12", stage, "--shard", f"{i}/{SHARDS}",
                                    "--deviation", DEVIATION], cwd=ROOT) for i in range(SHARDS)]
    codes = [p.wait() for p in procs]
    if any(codes):
        raise SystemExit(f"step12_run: {stages} shards exited {codes}")


def game_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq S4_Main.exe"], capture_output=True, text=True).stdout
    return "S4_Main" in out


def bliss():
    """BLISS's stages on step 12's session. The 2017 adapter's status and the general adapter's
    (SSY_BLISS_GENERAL=1) are kept apart. Recorded as not possible only when every block's record says
    its input is a layout the adapter does not take (matched.failure_kind); any other failure is left
    not done, to be tried again."""
    general = os.environ.get("SSY_BLISS_GENERAL") == "1"
    status = yoke.DATA / "step12" / ("bliss_general_status.json" if general else "bliss_status.json")
    if status.exists() and json.loads(status.read_text(encoding="utf-8")).get("done"):
        return
    while game_running():
        say("the game is running: BLISS (GPU) waits")
        time.sleep(600)
    rec = {"target": TARGET, "adapter": "general" if general else "2017"}
    sub = "bliss_general" if general else "bliss"
    for stage in ("bliss", "bliss-judge"):
        code = subprocess.run([PY, "-u", "matched.py", stage, TARGET], cwd=ROOT).returncode
        rec[stage] = code
        if code:
            recs = [json.loads(f.read_text(encoding="utf-8"))
                    for f in (yoke.DATA / "matched").glob(f"{TARGET}-*/{sub}/block_*.json")]
            kinds = [r.get("failed_kind") for r in recs]
            rec["failures"] = {k: kinds.count(k) for k in set(kinds) if k}
            if recs and all(k == "incompatible_input" for k in kinds):
                rec["done"] = True
                rec["not_possible"] = (f"matched.py {stage} exited {code}: every block's slice is a layout the "
                                       "adapter does not take (incompatible input, not a failure to run)")
                yoke.write(status, rec, indent=1, stamp=True)
                say(rec["not_possible"])
                return
            rec["done"] = False
            rec["failed_to_run"] = f"matched.py {stage} exited {code}; not marked done, to be tried again"
            yoke.write(status, rec, indent=1, stamp=True)
            raise SystemExit(rec["failed_to_run"])
    rec["done"] = True
    yoke.write(status, rec, indent=1, stamp=True)


def main():
    regression()
    # (check takes no deviation; the stages below log theirs)
    run("independent.py", "--step", "12", "sweep", "--deviation", DEVIATION)
    run("independent.py", "--step", "12", "choose", "--deviation", DEVIATION)
    # One stage at a time: six workers at once left too little free memory for blimpy, which then loads
    # one spectrum of a file and turboSETI refuses it (block 31, 19 Nov).
    parallel("measure")
    parallel("curved")
    run("independent.py", "--step", "12", "verdict", "--deviation", DEVIATION)
    bliss()
    say("step 12: done")


if __name__ == "__main__":
    main()
