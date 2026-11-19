"""The README's quick start against the real archive: `find` lists the 2017
session's whole cadence, and the 3 MHz search of its first ON look gives
the hits it gave when this was written (19 November 2026, search version
4). Reads about 100 MB from Breakthrough Listen's archive, so it is not
part of the offline tests: run it by hand, or from GitHub's Actions tab
(the `quick start` workflow), not on every push.

    python tests/integration_quickstart.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = ("https://bldata.berkeley.edu/pipeline/AGBT17A_999_68/holding/"
       "spliced_blc2021222324252627_guppi_57898_22410_DIAG_KIC8462852_0031.gpuspec.0000.h5")
EXPECT = {"hit_count": 10, "shadow_count": 271, "channels": 1073744, "spectra": 16,
          "strongest": {"frequency_mhz": 2250.146695, "drift_hz_s": 0.0, "snr": 306.4}}


def run(*args):
    r = subprocess.run([sys.executable, "seti.py", *args, "--json"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"seti.py {' '.join(args)} failed:\n{r.stderr or r.stdout}")
    return json.loads(r.stdout)["data"]


def main():
    bad = []
    found = json.dumps(run("find", "KIC8462852"))
    if "AGBT17A_999_68" not in found or URL not in found:
        bad.append("find: the 2017 session's first ON look is not listed")
    d = run("search", URL, "--from", "2250", "--to", "2253")
    for k in ("hit_count", "shadow_count", "channels", "spectra"):
        if d[k] != EXPECT[k]:
            bad.append(f"search: {k} {d[k]}, expected {EXPECT[k]}")
    top = max(d["hits"], key=lambda h: h["snr"]) if d["hits"] else None
    want = EXPECT["strongest"]
    if not top or abs(top["frequency_mhz"] - want["frequency_mhz"]) > 1e-5 \
            or abs(top["drift_hz_s"] - want["drift_hz_s"]) > 0.01 or abs(top["snr"] - want["snr"]) > 1:
        bad.append(f"search: strongest hit {top and {k: top[k] for k in want}}, expected {want}")
    print(f"quick start: {d['hit_count']} hits, {d['shadow_count']} shadow hits, {d['fetched_mb']} MB read")
    for b in bad:
        print("  " + b)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
