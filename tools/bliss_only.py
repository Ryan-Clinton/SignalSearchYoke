"""The planted signals BLISS recovers in all three ON looks at SNR 10 and
this search does not, from the committed records (comparable.md step 11):
each with this search's status at SNR 10 and its nearest candidate. Writes
data/analysis/bliss_only/list.json; the ones with no candidate at all
(lenient: none) are the ones to trace."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
base = ROOT / "data" / "matched" / "KIC8462852-AGBT17A_999_68"
out = []
for p in sorted(base.glob("block_*.json")):
    r = json.loads(p.read_text(encoding="utf-8"))
    bp = base / "bliss" / p.name
    if not bp.exists():
        continue
    b = json.loads(bp.read_text(encoding="utf-8"))
    for n, (t, bt) in enumerate(zip(r["tones"], b["tones"])):
        assert t["f_mhz"] == bt["f_mhz"]
        if bt["bliss"]["10"]["three_looks"] != "recovered" or t["ours"]["10"]["three_looks"] == "recovered":
            continue
        out.append({"block": r["block"], "class": r["class"], "tone": n, "f_mhz": t["f_mhz"],
                    "drift": t["drift"], "s_in": t["s_in"], "ours_10": t["ours"]["10"]})
none = [x for x in out if x["ours_10"]["lenient"] is None]
(ROOT / "data" / "analysis" / "bliss_only" / "list.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(f"{len(out)} recovered by BLISS at SNR 10 and not by this search; {len(none)} with no candidate at all")
for x in none:
    print(x["block"], x["class"], x["tone"], x["f_mhz"], round(x["drift"], 3), x["s_in"], x["ours_10"]["nearest"],
          x["ours_10"].get("members"))
sys.exit(0)
