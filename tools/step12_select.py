"""Step 12's session, chosen by the rule in comparable.md step 12 from the
archive's metadata alone: the listing (query-files), the session folder's
file list where the listing was asked by target, and for a session that
passes everything else the first ON file's HDF5 index (its shape, chunking
and header, no spectra). Every reply of the archive is saved with its
SHA-256 under data/step12/selection/, and the choice record names them, so
the same listing gives the same session.

    python tools/step12_select.py          choose, write data/step12/selection/choice.json
    python tools/step12_select.py gate     only the compatibility gate at Green Bank's geometry

The compatibility gate plants step 10's grid (110 signals a block, the same
S_in and drift bins) in synthetic noise shaped as the session's files (the
header's channel width and sign, spectrum time, spectra a look, channels a
block), ten blocks at seed 12, and searches and judges them with the frozen
code at SNR 30; it passes when the share recovered in all three ON looks is
at least 0.9 of the same measurement at Green Bank's geometry, and the
search's reach in drift fits the block. No spectra of any session are read.
"""
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matched  # noqa: E402
import measure  # noqa: E402
import searching  # noqa: E402
import seti  # noqa: E402
import yoke  # noqa: E402

OUT = yoke.DATA / "step12" / "selection"
TELESCOPE_FIRST = "Parkes"
GREEN_BANK = ("GBT", "GreenBank", "Green Bank", "GB")
BANDS = (("C", 3950.0, 8000.0), ("X", 8000.0, 11600.0))       # MHz, by the listed centre frequency
PRODUCTS = (".0000.h5", ".0000.fil")
READ_TARGETS = {"KIC8462852", "HIP17147", "HIP91699"}
READ_SESSIONS = {"AGBT17A_999_68", "AGBT16A_999_192"}
TARGETS = ("HIP39826", "HIP99427", "HIP66704", "HIP65352", "HIP4436")
MIN_BLOCKS = 61
GATE_BLOCKS = 10
GATE_SEED = 12
GATE_SHARE = 0.9
GATE_CUT = 30
GREEN_BANK_GEOMETRY = {"foff": -2.7939677238464355e-06, "tsamp": 18.253611008, "n_t": 16, "n_f": 1048576,
                       "look_s": 330.0}
CADENCE_DAYS = seti.CADENCE_DAYS


# --- the archive, every reply kept ------------------------------------------------

def _save(kind, params, text):
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    name = f"{kind}-{sha[:16]}.txt"
    (OUT / name).write_text(text, encoding="utf-8")
    return {"kind": kind, "params": params, "file": name, "sha256": sha, "bytes": len(text.encode("utf-8"))}


def _query(replies, **params):
    """The listing for params, or None if the archive will not answer it."""
    try:
        r = requests.get(seti.API, params=params, timeout=600, headers=seti.HEADERS)
    except requests.RequestException as e:
        replies.append({"kind": "query", "params": params, "error": str(e)})
        return None
    replies.append(dict(_save("query", params, r.text), status=r.status_code))
    if r.status_code != 200:
        return None
    try:
        rows = r.json().get("data")
    except ValueError:
        return None
    return rows if isinstance(rows, list) else None


def _folder(replies, url):
    base = url.rsplit("/", 1)[0] + "/"
    try:
        r = requests.get(base, timeout=seti.TIMEOUT, headers=seti.HEADERS)
    except requests.RequestException as e:
        replies.append({"kind": "folder", "params": {"url": base}, "error": str(e)})
        return []
    replies.append(dict(_save("folder", {"url": base}, r.text), status=r.status_code))
    if r.status_code != 200:
        return []
    out = []
    for name, mjd, seconds, target, _ in seti._LOOK.findall(r.text):
        out.append({"url": base + name, "target": target, "mjd": int(mjd) + int(seconds) / 86400,
                    "center_freq": None, "size": None, "telescope": None})
    return out


# --- the rule ---------------------------------------------------------------------

def _bare(t):
    return seti._bare(t)


def _is_gbt(tel):
    return str(tel or "").replace(" ", "").lower() in {g.replace(" ", "").lower() for g in GREEN_BANK}


def _band(mhz):
    for name, lo, hi in BANDS:
        if mhz is not None and lo <= float(mhz) < hi:
            return name
    return None


def runs(looks):
    """Every run of six looks ON, OFF, ON, OFF, ON, OFF in a session's looks
    (by MJD): the ON target the same, each OFF another, the OFFs within
    CADENCE_DAYS of the ON looks; the earliest first."""
    looks = sorted(looks, key=lambda r: r["mjd"])
    out = []
    for i in range(len(looks) - 5):
        six = looks[i:i + 6]
        on = _bare(six[0]["target"])
        if any(_bare(six[p]["target"]) != on for p in (2, 4)):
            continue
        if any(_bare(six[p]["target"]) == on for p in (1, 3, 5)):
            continue
        if six[5]["mjd"] - six[4]["mjd"] > CADENCE_DAYS or six[4]["mjd"] - six[0]["mjd"] > 4 * CADENCE_DAYS:
            continue
        out.append(six)
    return out


def _same_setup(six):
    """One centre frequency (to 1 kHz) and size (to 1%), where listed."""
    fs = [r["center_freq"] for r in six if r.get("center_freq") is not None]
    ss = [r["size"] for r in six if r.get("size")]
    if fs and max(fs) - min(fs) > 1e-3:
        return False
    if ss and (max(ss) - min(ss)) > 0.01 * max(ss):
        return False
    return True


def structural(session, rows, replies, by_target):
    """The first run of a session that passes everything before the header,
    or (None, reason)."""
    if session in READ_SESSIONS:
        return None, "a session this project has read"
    fine = [r for r in rows if str(r.get("url", "")).endswith(PRODUCTS)]
    if not fine:
        return None, "no finest-frequency product"
    looks = fine
    if by_target:
        # Asked by target: the OFF looks are filed under other targets; read the folder.
        near = _folder(replies, fine[0]["url"])
        listed = {r["url"]: r for r in fine}
        looks = [listed.get(r["url"], r) for r in near] or fine
    for six in runs(looks):
        if _bare(six[0]["target"]) in READ_TARGETS:
            continue
        on_rows = [r for r in fine if r["url"] in {x["url"] for x in six}]
        full = [next((r for r in fine if r["url"] == x["url"]), x) for x in six]
        if not _same_setup(full):
            continue
        return {"session": session, "looks": [{"url": x["url"], "target": x["target"], "mjd": x["mjd"]} for x in six],
                "on_listed": len(on_rows)}, None
    return None, "no run of six looks ON, OFF, ON, OFF, ON, OFF eligible"


def header(url):
    """The first ON file's chunk index: shape, chunking and header. HDF5
    only; anything else the reader cannot open."""
    if not url.endswith(".h5"):
        return None, "not a file the reader opens (HDF5 only)"
    try:
        idx = seti.reading.chunk_index(url)
    except Exception as e:      # the rule: any refusal of the reader makes the session ineligible
        return None, f"the reader refused the header: {type(e).__name__}: {e}"
    a = idx["attrs"]
    shape, chunk = idx["shape"], idx["chunk_shape"]
    geo = {"foff": float(a["foff"]), "tsamp": float(a["tsamp"]), "n_t": int(shape[0]), "n_f": int(chunk[-1]),
           "nchans": int(shape[-1]), "blocks": int(math.ceil(shape[-1] / chunk[-1])), "fch1": float(a["fch1"])}
    if geo["blocks"] < MIN_BLOCKS:
        return geo, f"{geo['blocks']} blocks, fewer than {MIN_BLOCKS}"
    return geo, None


# --- the compatibility gate ---------------------------------------------------------

def _synthetic(geo, rng):
    looks = []
    t0 = 60000.0
    step = max(geo.get("look_s") or 0.0, geo["n_t"] * geo["tsamp"] + 30.0)
    for j in range(6):
        raw = rng.chisquare(64, size=(geo["n_t"], geo["n_f"])).astype(np.float64) * 1e3
        s = {"spectra": raw, "fch1": 2000.0, "foff": geo["foff"], "tsamp": geo["tsamp"],
             "tstart": t0 + j * step / 86400, "target": "SYNTH" if j % 2 == 0 else "SYNTH_OFF",
             "first_channel": 0, "coarse_channel": geo["n_f"]}
        looks.append({"s": s, "raw": raw, "spectra": raw, "sigma": measure.channel_noise(raw)})
    return looks


def drift_fits(geo):
    span = (geo["n_t"] - 1) * geo["tsamp"]
    most = int(searching.MAX_DRIFT * span / (abs(geo["foff"]) * 1e6))
    w = math.ceil(most / max(geo["n_t"] - 1, 1)) if most else 1
    edge = most + w + searching.WINDOW_CHANNELS
    return 2 * edge + 2400 < geo["n_f"], {"drift_channels": most, "edge_channels": edge}


def gate_share(geo, blocks=GATE_BLOCKS, seed=GATE_SEED, say=print):
    """The share of step 10's grid recovered in all three ON looks at SNR 30,
    on synthetic noise of this geometry, by the frozen code."""
    got = n = 0
    cut = str(GATE_CUT)
    for b in range(blocks):
        rng = np.random.default_rng([seed, b])
        cad = _synthetic(geo, rng)
        caches = [{} for _ in range(6)]
        searched = matched.our_search(cad)
        looks, events, order = matched.our_events(cad, searched, matched.TRUE, GATE_CUT, caches)
        plain = matched._our_kept(looks, events, order)
        del searched, looks
        ts = matched.tones(cad, rng)
        planted = matched.plant(cad, ts)
        cad_p = [dict(c, spectra=p["spectra"]) for c, p in zip(cad, planted)]
        del planted
        kept = matched._ours_true(cad_p, matched.our_search(cad_p))[cut]
        for t in ts:
            t_f = {j: matched.where(cad, t, j)[1] for j in matched.TRUE}
            got += matched._status(t_f, t["drift"], kept, plain)["three_looks"] == "recovered"
            n += 1
        say(f"  gate block {b}: {got} of {n} so far", flush=True)
        del cad, cad_p
    return got / n, got, n


def gate(geo, say=print):
    fits, reach = drift_fits(geo)
    ref_path = OUT / "gate_green_bank.json"
    if ref_path.exists():
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
    else:
        say("the gate at Green Bank's geometry:", flush=True)
        share, got, n = gate_share(GREEN_BANK_GEOMETRY, say=say)
        ref = {"geometry": GREEN_BANK_GEOMETRY, "share": share, "recovered": got, "of": n,
               "blocks": GATE_BLOCKS, "seed": GATE_SEED, "cut": GATE_CUT}
        yoke.write(ref_path, ref, indent=1, stamp=True)
    if not fits:
        return {"passed": False, "reason": "the search's reach in drift does not fit the block", **reach,
                "green_bank": ref["share"]}
    if all(math.isclose(geo[k], GREEN_BANK_GEOMETRY[k], rel_tol=1e-6) for k in ("foff", "tsamp", "n_t", "n_f")):
        share, got, n = ref["share"], ref["recovered"], ref["of"]
    else:
        say("the gate at the session's geometry:", flush=True)
        share, got, n = gate_share(geo, say=say)
    passed = share >= GATE_SHARE * ref["share"]
    return {"passed": passed, "share": share, "recovered": got, "of": n, "green_bank": ref["share"],
            "needed": GATE_SHARE * ref["share"], **reach}


# --- choosing ---------------------------------------------------------------------

def _sessions(rows):
    out = {}
    for r in rows:
        if "url" in r:
            out.setdefault(seti._session(r["url"]), []).append(r)
    return dict(sorted(out.items()))


def candidates(replies, say=print):
    """(telescope, band, session, rows, by_target) in the rule's order."""
    order = []
    parkes = _query(replies, telescope=TELESCOPE_FIRST)
    by_target = parkes is None
    if by_target:
        parkes = [r for t in TARGETS for r in (_query(replies, target=t, telescope=TELESCOPE_FIRST) or [])]
    seen = {str(r.get("telescope")) for r in parkes if r.get("telescope")}
    say(f"{TELESCOPE_FIRST}: {len(parkes)} files listed{' (by target)' if by_target else ''}", flush=True)
    for s, rows in _sessions(parkes).items():
        order.append((TELESCOPE_FIRST, None, s, rows, by_target))
    gbt = _query(replies, telescope="GBT")
    gbt_by_target = gbt is None
    if gbt_by_target:
        gbt = [r for t in TARGETS for r in (_query(replies, target=t) or []) if _is_gbt(r.get("telescope"))]
    seen |= {str(r.get("telescope")) for r in gbt if r.get("telescope")}
    say(f"Green Bank: {len(gbt)} files listed{' (by target)' if gbt_by_target else ''}", flush=True)
    others = sorted(t for t in seen if t.lower() != TELESCOPE_FIRST.lower() and not _is_gbt(t))
    for tel in others:
        rows = _query(replies, telescope=tel) or []
        for s, rs in _sessions(rows).items():
            order.append((tel, None, s, rs, False))
    for band, _, _ in BANDS:
        rows = [r for r in gbt if _band(r.get("center_freq")) == band]
        for s, rs in _sessions(rows).items():
            order.append(("GBT", band, s, rs, gbt_by_target))
    return order


def choose(say=print):
    replies, tried = [], []
    chosen = None
    for tel, band, session, rows, by_target in candidates(replies, say):
        run, why = structural(session, rows, replies, by_target)
        if run is None:
            tried.append({"telescope": tel, "band": band, "session": session, "passed_over": why})
            continue
        geo, why = header(run["looks"][0]["url"])
        if why:
            tried.append({"telescope": tel, "band": band, "session": session, "passed_over": why, "header": geo})
            continue
        say(f"{tel} {band or ''} {session}: structure and header pass; the gate", flush=True)
        g = gate(geo, say=say)
        if not g["passed"]:
            tried.append({"telescope": tel, "band": band, "session": session, "passed_over": "the gate",
                          "gate": g, "header": geo})
            continue
        chosen = {"telescope": tel, "band": band, **run, "header": geo, "gate": g}
        break
    rec = {"rule": "comparable.md step 12, 'Choosing the session, from metadata alone'",
           "chosen": chosen, "passed_over": tried, "replies": replies,
           "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    yoke.write(OUT / "choice.json", rec, indent=1, stamp=True)
    if chosen:
        say(f"chosen: {chosen['telescope']} {chosen['band'] or ''} {chosen['session']}, "
            f"target {chosen['looks'][0]['target']}", flush=True)
    else:
        say("no session eligible: step 12 is not run (comparable.md step 12, rule 6)", flush=True)
    return rec


def main():
    if sys.argv[1:] == ["gate"]:
        return gate(GREEN_BANK_GEOMETRY)
    if (OUT / "choice.json").exists():
        raise yoke.Refusal("INVALID_REQUEST", f"{OUT / 'choice.json'} exists: the choice is made once")
    choose()


if __name__ == "__main__":
    main()
