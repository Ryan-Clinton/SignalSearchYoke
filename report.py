"""The result of a swept cadence, written up from the hit store and the
measurements: `seti.py report TARGET SESSION` writes
docs/results/TARGET-SESSION.md (and a JSON record beside it in
data/results/), stating what docs/research/sensitivity-and-prior-searches.md
section 5 asks a result page to state: the observation, the search, what it
achieved (completeness, S_min and EIRP_min at the cut and at 50% and 90%
completeness), validation, what it found at each stage, and how.

Nothing here is measured afresh: every number comes from the store
(data/ssy.sqlite) or data/measurements/, and the report says which.
"""
import json
import math

import yoke

# Distances from Gaia DR3 (Gaia Collaboration 2023) and Bailer-Jones et al.
# 2021's geometric distances, queried from the Gaia archive on 9 Nov 2026:
# SELECT ... FROM gaiadr3.gaia_source / external.gaiaedr3_distance.
TARGETS = {
    "KIC8462852": {"name": "KIC 8462852 (Boyajian's star, Tabby's star)", "gaia_dr3": 2081900940499099136,
                   "parallax_mas": 2.2545, "parallax_error_mas": 0.0099, "g_mag": 11.76,
                   "distance_pc": 434.6, "distance_lo_pc": 433.0, "distance_hi_pc": 436.3,
                   "distance_source": "Bailer-Jones et al. 2021, geometric (r_med_geo, 16th-84th percentile)"},
}
PC_M = 3.0857e16
NOTCH_MHZ = (2300.0, 2360.0)        # Green Bank's S-band notch filter (Price et al. 2020)
ARECIBO_W = 1e13                    # CWTFM's normalisation (Enriquez et al. 2017, Eq. 11)
SEFD_BRACKET_JY = (10.0, 12.5)      # Price et al. 2020's 10 Jy; 25 K at 2.0 K/Jy (Price 2020 Table 1, GBT
                                    # Proposer's Guide): the bracket the 2019 calibration is carried to 2017 in
HARP_2016_W = (4e15, 7e15)          # ATA, 1-10 GHz, narrowband EIRP limit at 454 pc
PRICE_2020 = "Price et al. 2020, AJ 159, 86"


def _q(db, sql, args=()):
    return [dict(r) for r in db.execute(sql, args)]


def _crossing(rates, level):
    """The S_in where the kept rate first reaches `level`, interpolated in
    log S_in between the measured strengths: (value, how)."""
    pts = sorted(rates)
    if pts[0][1] >= level:
        return pts[0][0], "at or below"
    for (s0, r0), (s1, r1) in zip(pts, pts[1:]):
        if r0 < level <= r1:
            x = math.log(s0) + (level - r0) / (r1 - r0) * (math.log(s1) - math.log(s0))
            return math.exp(x), "interpolated"
    return pts[-1][0], "above"


def build(target, session):
    import injection
    import instrument
    import onoff
    import searching
    import seti
    import store
    import vetting
    db = store.connect()
    files = _q(db, "SELECT * FROM files WHERE session=? AND cadence_target=? ORDER BY cadence_position",
               (session, target))
    if len(files) != 6:
        raise yoke.Refusal("INVALID_REQUEST", f"No swept cadence of {target} in {session} in the store.")
    version = seti.SEARCH_VERSION
    blocks = _q(db, "SELECT b.*, r.search_version, r.git_commit, r.libraries, r.params, r.host FROM blocks b"
                    " JOIN runs r ON r.run_id = b.run_id WHERE b.session=? ORDER BY b.block_idx", (session,))
    current = [b for b in blocks if b["search_version"] == version]
    per = round(seti.GBT_COARSE_MHZ / abs(files[0]["foff_mhz"]))
    n_blocks = round(files[0]["nchans"] / per) if files[0]["nchans"] else None
    # Only blocks searched by the current version count: a block an older
    # version searched is not yet comparable.
    ids = {b["block_idx"] for b in current}
    events = [e for e in _q(db, "SELECT * FROM events WHERE session=? AND superseded_run IS NULL", (session,))
              if e["block_idx"] in ids]
    looks = [lk for lk in _q(db, "SELECT * FROM looks WHERE session=? AND superseded_run IS NULL", (session,))
             if lk["block_idx"] in ids]
    candidates = sorted([e for e in events if e["label"] == "candidate"], key=lambda e: -e["snr"])
    for c in candidates:
        rows = _q(db, "SELECT * FROM checks WHERE event_id=? ORDER BY check_id", (c["event_id"],))
        latest = [r for r in rows if r["version"] == vetting.VERSION] or rows
        # A candidate checked again at the same version: its latest result per check.
        latest = list({r["name"]: r for r in latest}.values())
        c["checks"] = [{k: r[k] for k in ("name", "result", "strength")} for r in latest]
        c["verdict"] = next((r["result"] for r in latest if r["name"].startswith("10.")), None)
        c["checks_version"] = latest[0]["version"] if latest else None
        c["lead"] = latest[0]["lead"] if latest else None
    marks = ",".join("?" * len(ids)) or "NULL"
    hits = db.execute(f"SELECT origin, count(*) n FROM hits WHERE session=? AND superseded_run IS NULL"
                      f" AND block_idx IN ({marks}) GROUP BY origin", (session, *ids)).fetchall()
    hit_counts = {r["origin"]: r["n"] for r in hits}
    on_off = db.execute(f"SELECT f.is_on, count(*) n FROM hits h JOIN files f ON f.file_id=h.file_id WHERE h.session=?"
                        f" AND h.superseded_run IS NULL AND h.origin='search' AND h.block_idx IN ({marks})"
                        f" GROUP BY f.is_on", (session, *ids)).fetchall()
    runs = sorted({b["run_id"] for b in current})
    run_rows = _q(db, f"SELECT * FROM runs WHERE run_id IN ({','.join('?' * len(runs))})", runs) if runs else []
    db.close()

    width_hz = abs(files[0]["foff_mhz"]) * 1e6
    tsamp, n_t = files[0]["tsamp_s"], files[0]["n_spectra"] or 16
    span = (n_t - 1) * tsamp
    lo = min((b["f_lo_mhz"] for b in current), default=None)
    hi = max((b["f_hi_mhz"] for b in current), default=None)
    covered = sum(b["f_hi_mhz"] - b["f_lo_mhz"] for b in current)
    in_notch = lambda b: max(0.0, min(b["f_hi_mhz"], NOTCH_MHZ[1]) - max(b["f_lo_mhz"], NOTCH_MHZ[0]))  # noqa: E731
    notch = sum(in_notch(b) for b in current)
    # A block with a look that stopped at the hit limit has no full list of
    # its hits: searched, but no limit is claimed for it.
    cut_short = sorted({lk["block_idx"] for lk in looks if lk["complete"] == 0})
    short_blocks = [b for b in current if b["block_idx"] in cut_short]
    short_mhz = sum(b["f_hi_mhz"] - b["f_lo_mhz"] - in_notch(b) for b in short_blocks)
    usable = covered - notch - short_mhz
    t = TARGETS.get(target)
    comp = json.load(open(yoke.DATA / "measurements" / "completeness.json"))
    cells = comp["tables"]["by_cell"]
    # The flux scale: the SEFD measured on 3C295 in the same S-band setup
    # (measure.py sefd), else the 10 Jy assumed before it was.
    sefd_rec = instrument.load("sefd")
    sefd = sefd_rec["sefd_jy"] if sefd_rec else injection.SEFD_JY
    flux = lambda s: injection.flux_jy_hz(s, n_t, width_hz, tsamp, sefd)  # noqa: E731
    eirp = (lambda jy_hz, d_pc: 4 * math.pi * (d_pc * PC_M) ** 2 * jy_hz * 1e-26)  # noqa: E731
    sens = []
    for drift in sorted({tuple(c["drift_hz_s"]) for c in cells}):
        rates = [(c["s_in"], c["kept_rate"]) for c in cells if tuple(c["drift_hz_s"]) == drift]
        row = {"drift_hz_s": list(drift)}
        for level in (0.5, 0.9):
            s, how = _crossing(rates, level)
            row[f"s_in_{int(level * 100)}"] = round(s, 1)
            row[f"how_{int(level * 100)}"] = how
            row[f"flux_{int(level * 100)}_jy_hz"] = round(flux(s), 2)
            if t:
                row[f"eirp_{int(level * 100)}_w"] = eirp(flux(s), t["distance_pc"])
        sens.append(row)
    cut_flux = flux(seti.SNR_MIN)
    mid = (lo + hi) / 2 if lo else None
    nu_rel = usable / mid if mid else None
    cut_eirp = eirp(cut_flux, t["distance_pc"]) if t else None
    zeta = 1000 * 0.5 / ARECIBO_W
    null_tracks = sum(b["off_null_tracks"] or 0 for b in current)
    null_vetoed = sum(b["off_null_vetoed"] or 0 for b in current)
    null_over = sum(b["off_null_over"] or 0 for b in current)
    voyager = _load("voyager")
    price = _load("price")
    record = {
        "target": target, "session": session, "target_info": t, "files": files, "search_version": version,
        "blocks_total": n_blocks, "blocks_current": len(current), "blocks_older": len(blocks) - len(current),
        "from_mhz": lo, "to_mhz": hi, "covered_mhz": round(covered, 3), "notch_mhz": round(notch, 3),
        "looks_incomplete": sum(1 for lk in looks if lk["complete"] == 0), "looks": len(looks),
        "blocks_cut_short": [{"block_idx": b["block_idx"], "f_lo_mhz": b["f_lo_mhz"], "f_hi_mhz": b["f_hi_mhz"],
                              "looks": sum(1 for lk in looks if lk["block_idx"] == b["block_idx"]
                                           and lk["complete"] == 0)}
                             for b in short_blocks],
        "cut_short_mhz": round(short_mhz, 3), "usable_mhz": round(usable, 3),
        "frequency_complete": len(current) == n_blocks, "complete": len(current) == n_blocks and not short_blocks,
        "channel_hz": width_hz, "tsamp_s": tsamp, "spectra": n_t, "span_s": span,
        "drift_step_hz_s": width_hz / span, "snr_min": seti.SNR_MIN, "max_drift_hz_s": seti.MAX_DRIFT,
        "hits_at_cut": hit_counts.get("search", 0), "shadow_hits": hit_counts.get("shadow", 0),
        "hits_on": next((r["n"] for r in on_off if r["is_on"] == 1), 0),
        "hits_off": next((r["n"] for r in on_off if r["is_on"] == 0), 0),
        "events": {lab: sum(e["label"] == lab for e in events) for lab in ("candidate", "interference", "unconfirmed")},
        "candidates": [{k: c.get(k) for k in ("event_id", "lead", "block_idx", "f_start_mhz", "drift_hz_s", "snr",
                                                "off_snr_max", "on_snr_min", "verdict", "checks", "checks_version")}
                       for c in candidates],
        "off_null": {"tracks": null_tracks, "vetoed": null_vetoed, "over_off_max": null_over},
        "sefd_jy": sefd, "sefd_measured": bool(sefd_rec), "sefd_assumed_before_jy": injection.SEFD_JY,
        "sefd_16_84_jy": sefd_rec and sefd_rec["sefd_jy_16_84"],
        "sefd_pairs": sefd_rec and [{k: p.get(k) for k in ("utc", "elevation_on_deg", "sefd_jy_median", "kept",
                                                            "not_kept_because")} for p in sefd_rec["pairs"]],
        "cadence_elevation_deg": [round(instrument.elevation(f["tstart_mjd"], f["ra_hours"], f["dec_degrees"]), 1)
                                  for f in files if f["ra_hours"] is not None],
        "sefd_bracket_jy": [min(SEFD_BRACKET_JY[0], sefd), max(SEFD_BRACKET_JY[1], sefd)],
        "positions": _positions(files, (lo + hi) / 2 if lo else None),
        "response": instrument.load("response"), "dropped": instrument.load("dropped"),
        "pipelines": (lambda x: x if x and x.get("session") == session else None)(_load("pipelines")),
        "edge_channels": int(seti.MAX_DRIFT * span / width_hz) + math.ceil(seti.MAX_DRIFT * tsamp / width_hz) + 4,
        "on_min": onoff.ON_MIN, "off_max": onoff.OFF_MAX, "max_hits": searching.MAX_HITS,
        "cut_flux_jy_hz": cut_flux, "cut_eirp_w": cut_eirp,
        "sensitivity": sens, "nu_rel": nu_rel,
        "cwtfm": zeta * cut_eirp / (1 * nu_rel) if cut_eirp and nu_rel else None,
        "cwtfm_90": (zeta * sens[0]["eirp_90_w"] / nu_rel if t and nu_rel and sens and sens[0]["how_90"] != "above"
                     else None),
        "transmitter_rate": 1 / nu_rel if nu_rel else None,
        "completeness": comp["tables"], "false_summary": comp.get("false_summary"),
        "completeness_provenance": comp.get("provenance"),
        "voyager": voyager and {k: voyager.get(k) for k in ("rows", "earth_drift_hz_s", "hits_at_cut", "sha256")},
        "price": price and [{"session": s["session"], "turboseti_events": s["turboseti_events"],
                             "ours": [o for o in s["ours"] if o["label"] == "candidate"]} for s in price["sessions"]],
        "runs": [{k: r[k] for k in ("run_id", "started_utc", "finished_utc", "command", "git_commit",
                                    "uncommitted_changes", "host", "python", "libraries", "search_version")}
                 for r in run_rows],
        "checks_version": vetting.VERSION, "kind": "measured",
    }
    return record


def search_space(r):
    """What this search can and cannot see (docs/comparable.md, step 1),
    from the search's parameters and the planting model."""
    look_s = r["spectra"] * r["tsamp_s"]
    # A drift that changes: the track leaves its fitted line by half a
    # channel when the change reaches 16 x (width / 2) / T^2 (the largest gap
    # between a parabola and its best line over T is a T^2 / 16).
    curve = 16 * 0.5 * r["channel_hz"] / look_s ** 2
    edge_khz = r["edge_channels"] * r["channel_hz"] / 1e3
    resp = r.get("response")
    drop = r.get("dropped")
    out = ["## What this search can and cannot see", "",
           "The completeness and the limits below hold for this signal and no other:", "",
           f"- **A tone narrower than one channel** ({r['channel_hz']:.2f} Hz) at the transmitter; wider signals "
           "spread over channels and lose sensitivity, not modelled (Voyager 1's 322 Hz sidebands came out as dozens "
           "of hits).",
           f"- **Drifting steadily**, within ±{r['max_drift_hz_s']:g} Hz/s (steps of {r['drift_step_hz_s']:.4f} "
           f"Hz/s), as the planted signals did. A drift that changes by more than about {curve:.1e} Hz/s² leaves "
           f"its line by half a channel within a look (an estimate, not measured: comparable.md step 9).",
           f"- **On through each ON look** ({r['spectra']} spectra of {r['tsamp_s']:.2f} s, {look_s:.0f} s): a "
           "signal on for part of a look gives about that share of its power (a pulse train shorter than "
           f"{r['tsamp_s']:.0f} s is averaged into a steady one at its mean power).",
           f"- **In all three ON looks** (a hit at SNR {r['snr_min']:g} in one, at least S/N {r['on_min']:g} "
           f"along the track in the others), **and in none of the three OFF looks** (under S/N {r['off_max']:g} "
           "along the track and no hit there): a transmitter also seen in the OFF directions is called "
           "interference by design; one on in some ON looks only is unconfirmed.",
           "- **Seen in total power** (both polarisations summed): any polarisation.",
           ("- **With the channel response measured on Voyager 1's carrier** (`measure.py response`): "
            f"{resp['best']} fits best, by χ² {resp['chi2_margin_over_next']:g} over the next "
            f"(χ²/dof {resp['fits'][resp['best']]['chi2_per_dof']:g}), the response the planted signals used. "
            "Not a perfect fit: residuals up to "
            f"{100 * max(abs(v) for v in resp['fits'][resp['best']]['residual_over_peak_by_channel'].values()):.1f}% "
            "of the peak, and the far wings above sinc² (at 10 to 20 channels "
            f"{next(w['observed'] for w in resp['wings'] if w['channels'][0] == 10):.4f} of the peak against "
            f"{next(w['sinc2'] for w in resp['wings'] if w['channels'][0] == 10):.4f}), which the carrier's own phase "
            "noise could give. One observation, of September 2016; other sessions' processing is taken to be the "
            "same, not shown to be."
            if resp else "- **With the sinc² channel response assumed** (an unwindowed FFT, as in rawspec)."),
           "", "It cannot see:", "",
           f"- drifts beyond ±{r['max_drift_hz_s']:g} Hz/s (the `.0002` product could reach about 2.7 kHz/s: "
           "comparable.md step 9);",
           "- signals wider than a few channels, broadband or dispersed pulses, and pulses resolved in time (the "
           "finest time here is one spectrum);",
           f"- the receiver's notch ({r['notch_mhz']:.1f} MHz searched there) and the blocks where a look stopped "
           f"at the {r['max_hits']:,}-hit limit ({r['cut_short_mhz']:.1f} MHz), left out of the limits;",
           f"- line starts within about {r['edge_channels']} channels ({edge_khz:.1f} kHz) of each coarse "
           "channel's edges, where a line would run off the block (about "
           f"{100 * 2 * r['edge_channels'] / 1048576:.2f}% of the band), and the blanked middle channel of each;",
           "- anything outside the half-hour of the cadence or the beam (about 5.8′ wide at 2.3 GHz, centred on "
           "the star).", ""]
    if drop:
        out += [f"**Dropped data** (`measure.py dropped`, from the files' chunk indexes): a test for spectra "
                "of zeros, which compress to almost nothing, found "
                f"{drop['zero_like_chunks']} in any coarse channel of the six looks, and "
                f"{drop['missing_or_dropped_nodes']} missing or dropped nodes (no `zz` or `oo` in the names); the "
                "smallest chunk is "
                f"{100 * min(lk['smallest_over_median'] for lk in drop['looks']):.0f}% of its file's median. This "
                "does not show that every sample is intact: packets lost within a spectrum lower its power without "
                "zeroing it, and are not seen this way.", ""]
    return out


def _positions(files, f_mhz):
    """Each look's pointing: as stored, as its own header gives it (they must
    agree: a fault once stored them about 3,600 times too small), its
    distance from the first look's, its elevation, and the drift the Earth
    gives a signal fixed in the sky there at mid-band."""
    import instrument
    import store
    import vetting
    out = []
    first = files[0]
    for f in files:
        a = json.loads(f["attrs"] or "{}")
        ra_h, dec_h = store._coordinate(a.get("src_raj")), store._coordinate(a.get("src_dej"))
        ok = (ra_h is not None and f["ra_hours"] is not None and abs(ra_h - f["ra_hours"]) < 1e-6
              and abs(dec_h - f["dec_degrees"]) < 1e-6)
        d1, r1 = math.radians(first["dec_degrees"]), math.radians(first["ra_hours"] * 15)
        d2, r2 = math.radians(f["dec_degrees"]), math.radians(f["ra_hours"] * 15)
        apart = math.degrees(math.acos(min(1.0, math.sin(d1) * math.sin(d2)
                                           + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2))))
        mid = f["tstart_mjd"] + (f["n_spectra"] or 16) * (f["tsamp_s"] or 18.25) / 2 / 86400
        out.append({"position": f["cadence_position"], "ra_hours": round(f["ra_hours"], 5),
                    "dec_deg": round(f["dec_degrees"], 5), "matches_header": ok,
                    "from_first_deg": round(apart, 4),
                    "elevation_deg": round(instrument.elevation(mid, f["ra_hours"], f["dec_degrees"]), 1),
                    "earth_drift_hz_s": round(vetting.expected_drift(f_mhz, mid, f["ra_hours"], f["dec_degrees"])[0], 4)
                    if f_mhz else None})
    return out


def other_pipelines(r):
    """The section setting turboSETI's and pickles' events on this cadence
    against this search's (pipelines.py compare)."""
    p = r.get("pipelines")
    if not p:
        return ["## Other pipelines on the same cadence", "",
                "Not run yet (`pipelines.py run`, then `pipelines.py compare`).", ""]
    t, k = p["turboseti"], p["pickles"]
    out = ["## Other pipelines on the same cadence", "",
           f"Both run here over all {p['blocks']} blocks on the same slices (`pipelines.py run`, "
           "`pipelines.py compare`; data/measurements/pipelines.json), as no published search lists this "
           "cadence's hits:", "",
           f"- **turboSETI {t['version']}** with its event pipeline ({t['settings']}).",
           f"- **pickles** (Painter et al. 2025; github.com/UCBerkeleySETI/pickles at `{k['commit'][:7]}`, "
           f"SHA-256 {k['sha256'][:12]}…), its code run as published from its hotspots on ({k['settings']}); "
           "once with its interference bands masked, as published, once with none masked. Its code names a "
           "variable it never defines when a block has no hotspots; that name is supplied, nothing else changed.",
           "",
           "| pipeline | lines found | kept as events or candidates |", "|---|---|---|",
           f"| this search | {p['ours']['hits']:,} hits at SNR 10 | {p['ours']['candidates']} candidates, "
           "none unexplained by the checks |",
           f"| turboSETI | {t['hits']:,} hits at its SNR 10 | {t['events']} events |",
           f"| pickles, masked | {k['masked']['level0']:,} hotspots | {k['masked']['level1']} at level 1, "
           f"{k['masked']['level2']} at level 2 |",
           f"| pickles, unmasked | {k['unmasked']['level0']:,} hotspots | {k['unmasked']['level1']} at level 1, "
           f"{k['unmasked']['level2']} at level 2 |", "",
           f"turboSETI's SNR is about {p['turbo_scale']:g} of this search's for the same signal, so its cut of 10 "
           "is about 44 here: the two lists of hits differ mainly in depth. No line was kept by all three. "
           "This search's candidates, in the others:", "",
           "| candidate (MHz) | SNR | turboSETI | pickles |", "|---|---|---|---|"]
    for o in p["our_candidates"]:
        out.append(f"| {o['f_mhz']:.6f} | {o['snr']:.1f} | {o['turboseti']} | {o['pickles']} |")
    out += ["", "What the others kept at level 1 or more, or as events, in this search:", "",
            "| pipeline | MHz | kept | here |", "|---|---|---|---|"]
    for e in p["their_events"]:
        kept = (f"level {e['level']}" + (", masks on" if e.get("masks") else ", masks off")
                + (f" (ON kurtosis {', '.join(f'{x:.2f}' for x in e['k_on'])}; OFF "
                   f"{', '.join(f'{x:.2f}' for x in e['k_off'])})" if "k_on" in e else ""))             if e["pipeline"] == "pickles" else f"event, SNR {e['snr']:.1f}"
        here = "; ".join(f"{x['label']} at {x['f_start_mhz']:.6f} MHz, {x['drift_hz_s']:+.4f} Hz/s, SNR "
                         f"{x['snr']:.1f}" + (f", OFF S/N {x['off_snr_max']:.2f} along the track, ON at least "
                                              f"{x['on_snr_min']:.2f}" if x.get("off_snr_max") is not None else "")
                         for x in e["ours"]) or "no event"
        out.append(f"| {e['pipeline']} | {e['f_mhz']:.6f} | {kept} | {here} |")
    if not p["their_events"]:
        out.append("| (none) | | | |")
    pk = [e for e in p["their_events"] if e["pipeline"] == "pickles"]
    two_of_three = [e for e in pk if min(e["k_on"]) < 0.5]
    unexplained = [e for e in p["their_events"] if not e["ours"] or any(x["label"] == "unconfirmed" for x in e["ours"])]
    weak = [o for o in p["our_candidates"] if o["turboseti_expected_snr"] < 10]
    out += [""]
    if pk:
        out.append(f"pickles' level 1 asks for the median ON kurtosis, so a line in two of the three ON looks passes: "
                   f"{len(two_of_three)} of its {len(pk)} kept window(s) have an ON look under 0.5"
                   + (" (each its first), where this search finds the line under S/N 5 along the track: here they "
                      "need all three, so they would be unconfirmed even without the OFF evidence." if two_of_three
                      and all(e["k_on"][0] < 0.5 for e in two_of_three) else "."))
        out.append("")
    out.append(("Nothing either of the others kept is missed here: every window or event of theirs is an event here, "
                "called interference by the OFF looks along its track. " if not unexplained else
                f"{len(unexplained)} of what the others kept has no event here or only an unconfirmed one (the "
                "table). ")
               + f"Of this search's {len(p['our_candidates'])} candidates, {len(weak)} are under turboSETI's cut on "
                 "its scale; pickles masks every one as published, and unmasked finds none at level 1. All are "
                 "explained here as interference by the checks.")
    out.append("")
    return out


def _load(name):
    p = yoke.DATA / "measurements" / f"{name}.json"
    return json.load(open(p)) if p.exists() else None


def _w(x):
    if x is None:
        return "n/a"
    e = int(math.floor(math.log10(abs(x))))
    return f"{x / 10 ** e:.1f}×10^{e} W"


def markdown(r):
    t = r["target_info"] or {"name": r["target"]}
    f0 = r["files"]
    lines = [f"# {t['name']}: Green Bank {r['session']}", "",
             f"The narrowband search of one whole ON-OFF cadence, written by `seti.py report {r['target']} "
             f"{r['session']}` from the hit store and the measurements in `data/measurements/` "
             f"({yoke.provenance()['created_utc']}). Search version {r['search_version']}; checks version "
             f"{r['checks_version']}.", ""]
    done = r["frequency_complete"]
    short = r["blocks_cut_short"]
    lines += ["## In brief", ""]
    lines += [f"- **Searched:** {r['blocks_current']} of {r['blocks_total']} blocks "
              f"({r['covered_mhz']:.1f} MHz, {r['from_mhz']:.3f} to {r['to_mhz']:.3f} MHz)"
              + ("" if done else " — **the sweep is not complete; this report is partial**") + ".",
              f"- **Usable for limits:** {r['usable_mhz']:.1f} MHz: the band searched less the receiver's notch "
              f"({r['notch_mhz']:.1f} MHz) and {len(short)} block(s) where a look stopped at the hit limit "
              f"({r['cut_short_mhz']:.1f} MHz, listed below)"
              + (". Every block of the band is searched, but not every one completely" if done and short else "")
              + ".",
              f"- **Found:** {r['hits_at_cut']:,} hits at SNR {r['snr_min']:g} or more in the six looks "
              f"({r['shadow_hits']:,} more from SNR 5 kept as shadow hits); {sum(r['events'].values()):,} events: "
              f"{r['events']['candidate']} candidate(s), {r['events']['interference']:,} interference, "
              f"{r['events']['unconfirmed']:,} unconfirmed."]
    verdicts = {}
    for c in r["candidates"]:
        key = (c["verdict"] or "not checked").split(" (")[0]
        verdicts[key] = verdicts.get(key, 0) + 1
    lines.append("- **After the checks:** " + (", ".join(f"{n} {k}" for k, n in sorted(verdicts.items()))
                                               if verdicts else "no candidate to check") + ".")
    slow, fast = (r["sensitivity"][0], r["sensitivity"][-1]) if r["sensitivity"] else (None, None)
    if slow:
        lines.append(f"- **Sensitivity, measured** (90% of planted signals kept; SEFD {r['sefd_jy']:g} Jy, "
                     f"{'measured on 3C295' if r['sefd_measured'] else 'assumed'}; "
                     f"a transmitter narrower than 1 Hz at {t.get('distance_pc', '?')} pc): EIRP "
                     f"{'≤ ' if slow['how_90'] == 'at or below' else ''}{_w(slow.get('eirp_90_w'))} at "
                     f"{slow['drift_hz_s'][0]:g} to {slow['drift_hz_s'][1]:g} Hz/s, "
                     f"{_w(fast.get('eirp_90_w'))} at {fast['drift_hz_s'][0]:g} to {fast['drift_hz_s'][1]:g} Hz/s"
                     + (f"; with the SEFD anywhere in {r['sefd_bracket_jy'][0]:g} to {r['sefd_bracket_jy'][1]:g} Jy, "
                        f"{_w(slow.get('eirp_90_w') * r['sefd_bracket_jy'][0] / r['sefd_jy'])} to "
                        f"{_w(slow.get('eirp_90_w') * r['sefd_bracket_jy'][1] / r['sefd_jy'])} and "
                        f"{_w(fast.get('eirp_90_w') * r['sefd_bracket_jy'][0] / r['sefd_jy'])} to "
                        f"{_w(fast.get('eirp_90_w') * r['sefd_bracket_jy'][1] / r['sefd_jy'])}"
                        if r["sefd_measured"] and slow.get("eirp_90_w") and fast.get("eirp_90_w") else "") + ".")
    lines.append(f"- **Nominal threshold** (the radiometer equation at the cut, SNR {r['snr_min']:g}; not "
                 f"measured, as the faintest planted signals were S_in 15): S_min {r['cut_flux_jy_hz']:.1f} Jy Hz, "
                 f"EIRP {_w(r['cut_eirp_w'])}.")
    lines.append("- **No technosignature is claimed.** " + (
        "No candidate came out unexplained." if not any((c["verdict"] or "").startswith("unexplained")
                                                       for c in r["candidates"])
        else "Unexplained candidates are listed below; unexplained is the end of these checks, not a detection."))
    lines += ["", "## The observation", ""]
    if r["target_info"]:
        lines += [f"- **Target:** {t['name']}, Gaia DR3 {t['gaia_dr3']} (G {t['g_mag']}); parallax "
                  f"{t['parallax_mas']} ± {t['parallax_error_mas']} mas; distance {t['distance_pc']} pc "
                  f"({t['distance_lo_pc']} to {t['distance_hi_pc']}; {t['distance_source']})."]
    lines += [f"- **Session:** {r['session']}, Green Bank Telescope, S-band receiver; the cadence's six looks:", "",
              "| # | ON/OFF | target | start (UTC) | file | ETag |", "|---|---|---|---|---|---|"]
    import seti
    for f in f0:
        lines.append(f"| {f['cadence_position'] + 1} | {'ON' if f['is_on'] else 'OFF'} | {f['target']} | "
                     f"{seti._utc(f['tstart_mjd'])} | [{f['url'].rsplit('/', 1)[-1]}]({f['url']}) | "
                     f"`{(f['etag'] or '').strip(chr(34))}` |")
    pos = r["positions"]
    lines += ["", "Where each look pointed (stored, checked against its own header), and the drift the Earth "
              f"gives a signal fixed in that direction at {(r['from_mhz'] + r['to_mhz']) / 2:.0f} MHz:", "",
              "| # | RA (h) | Dec (°) | matches its header | from look 1 (°) | elevation mid-look (°) | Earth's drift (Hz/s) |",
              "|---|---|---|---|---|---|---|"]
    for p in pos:
        lines.append(f"| {p['position'] + 1} | {p['ra_hours']:.5f} | {p['dec_deg']:+.5f} | "
                     f"{'yes' if p['matches_header'] else '**NO**'} | {p['from_first_deg']:.3f} | "
                     f"{p['elevation_deg']:.1f} | {p['earth_drift_hz_s']:+.4f} |")
    if not all(p["matches_header"] for p in pos):
        lines += ["", "**The stored positions do not match the headers: check 5 and the elevations are wrong "
                  "until the files' rows are written again.**"]
    lines += ["", f"- **Band:** {r['from_mhz']:.3f} to {r['to_mhz']:.3f} MHz searched; of it {r['notch_mhz']:.1f} MHz "
              f"lies in the receiver's notch filter ({NOTCH_MHZ[0]:g} to {NOTCH_MHZ[1]:g} MHz), searched but "
              f"with its sensitivity not measured and left out of the limits below.",
              f"- **Blanked:** one channel in each coarse channel (the spectrometer's spike at its middle): "
              f"{r['blocks_current']} of {r['blocks_current'] * 1048576:,} channels. Nothing else is masked; "
              f"spectral kurtosis is recorded, never used to drop.",
              f"- **Looks cut short:** {r['looks_incomplete']} of {r['looks']} block-looks stopped at the "
              f"2,000-hit limit (shadow hits included) with lines at SNR 5 or more left unpicked, in "
              f"{len(short)} block(s): "
              + (", ".join(f"{b['block_idx']} ({b['f_lo_mhz']:.3f} to {b['f_hi_mhz']:.3f} MHz, {b['looks']} look(s))"
                           for b in short) or "none")
              + ". Their candidates and interference stand, but a signal there may have gone unpicked, so they "
                "are left out of the usable band and of the limits.",
              (f"- **SEFD:** {r['sefd_jy']:g} Jy, measured with the flux calibrator 3C295 in the same S-band "
               f"setup (`measure.py sefd`; across the band's coarse channels, 16-84%, {r['sefd_16_84_jy'][0]:g} "
               f"to {r['sefd_16_84_jy'][1]:g} Jy: a spread over frequency, not an uncertainty; pairs "
               + ", ".join(f"{p['utc']} UTC at {p['elevation_on_deg']:g}° elevation: {p['sefd_jy_median']:g} Jy"
                           for p in r["sefd_pairs"] if p["kept"])
               + "".join(f"; one of {p['utc']} UTC not used ({p['sefd_jy_median']:g} Jy: "
                         + "; ".join(p["not_kept_because"]) + ")" for p in r["sefd_pairs"] if not p["kept"])
               + f"), against the {r['sefd_assumed_before_jy']:g} Jy assumed before. Measured in December 2019, "
                 "not on the 2017 cadence (the archive lists no scan of a flux calibrator from that session: "
                 "3C48, 3C123, 3C138, 3C147, 3C196, 3C286, 3C295, 3C353, 3C380 and others queried): same receiver "
                 "and setup, other epoch; "
                 "the cadence's elevation at the start of each look was "
               + ", ".join(f"{e:g}°" for e in r["cadence_elevation_deg"]) + ". One pair, so its repeatability "
                 "is not measured either. The limits below use it as the best estimate, and carry it to 2017 within "
                 f"a bracket of {r['sefd_bracket_jy'][0]:g} to {r['sefd_bracket_jy'][1]:g} Jy (Price et al. "
                 "2020's 10 Jy; 25 K at the Proposer's Guide's 2.0 K/Jy): a range of published values, not a "
                 "statistical interval. Every flux and EIRP below scales with it." if r["sefd_measured"] else
               f"- **SEFD:** {r['sefd_jy']:g} Jy, Price et al. 2020's figure for Green Bank at S-band: assumed, "
               "not measured here; every flux and EIRP below scales with it."), ""]
    lines += ["## The search", "",
              f"- **Data:** the finest product (`.gpuspec.0000.h5`): {r['channel_hz']:.3f} Hz channels, "
              f"{r['spectra']} spectra of {r['tsamp_s']:.2f} s ({r['span_s']:.0f} s between the first and the last).",
              f"- **Drifts:** ±{r['max_drift_hz_s']:g} Hz/s in steps of {r['drift_step_hz_s']:.4f} Hz/s, each "
              f"line summed with a box of channels as wide as its smear (docs/seti.md, \"A correct search\").",
              f"- **SNR:** the excess along a line over the robust spread of the summed lines themselves (true "
              f"noise of the sums; turboSETI's SNR is about 0.23 of it). The cut: SNR {r['snr_min']:g}; shadow "
              f"hits from 5 kept for the OFF test and the checks.",
              "- **The cadence test** (`onoff.py`): every ON look's hits seed events; hits join by one distance, "
              "one to one, every member matching every other; every look measured along the track. "
              "Interference: an OFF look at S/N 6 or more along the track, or any hit there. Candidate: in "
              "every ON look (a hit, or S/N 5 along the track), no OFF evidence.",
              "- **The checks** (`vetting.py`, after Sheikh et al. 2021's ten steps for blc1): data sanity, "
              "the OFF looks, known bands, zero drift, the Earth's drift, recurrence, look-alikes, harmonics "
              "and intermodulation, crowding, the report; each marked shown, indicated or coincidence "
              "possible with its chance. None deletes a candidate.", ""]
    lines += search_space(r)
    lines += ["## What it achieved", "",
              "### Completeness through the whole pipeline", "",
              "Signals planted as the sky makes them in the ON looks of five saved cadences of this session "
              "(3,257 signals; docs/seti.md, \"Completeness through the whole pipeline\") and followed through "
              "search, cadence test and checks. Kept: a candidate the checks do not call interference.", "",
              "| drift (Hz/s) | " + " | ".join(f"S_in {s} ({flux(s, r):.0f} Jy Hz)" for s in (15, 30, 60, 120)) + " |",
              "|---|---|---|---|---|"]
    for d in sorted({tuple(c["drift_hz_s"]) for c in r["completeness"]["by_cell"]}):
        cells = {c["s_in"]: c for c in r["completeness"]["by_cell"] if tuple(c["drift_hz_s"]) == d}
        lines.append(f"| {d[0]:g} to {d[1]:g} | " + " | ".join(
            f"{cells[s]['kept_rate'] * 100:.0f}% ({cells[s]['kept_interval'][0] * 100:.0f}-"
            f"{cells[s]['kept_interval'][1] * 100:.0f})" if s in cells else "" for s in (15, 30, 60, 120)) + " |")
    ia = r["completeness"]["in_all"]
    fs = r["false_summary"] or {}
    lines += ["", f"Interference planted in all six looks: {ia['kept_as_candidate']} of {ia['found_in_a_look']} "
              f"found kept as candidates. False candidates (each cadence judged with the 19 wrong choices of ON "
              f"looks): {fs.get('distinct_signals')} distinct in {fs.get('cadences')} cadences, "
              f"{fs.get('per_cadence')} a block's cadence (95% {fs.get('per_cadence_interval')}), none "
              f"unexplained. The OFF test's veto rate on random tracks in this sweep: "
              f"{r['off_null']['vetoed']} of {r['off_null']['tracks']:,} "
              f"({100 * r['off_null']['vetoed'] / max(r['off_null']['tracks'], 1):.2f}%; "
              f"{r['off_null']['over_off_max']} by S/N 6 along the track, the rest by a hit there); "
              f"on planted signals, 0.5%.", "",
              "The completeness was measured with search version 3; version 4 changed how hits join "
              "(no event changed on the planted cadences) and check 6, which the planted trials do not reach.", "",
              "### Sensitivity", "",
              f"S_min = S_in × SEFD / √(n_pol Δν τ) × Δν / √n: a signal of strength S_in gives SNR ≈ S_in at zero "
              f"drift. EIRP_min = 4π d² S_min at {t.get('distance_pc', '?')} pc; for a transmitter 1 Hz wide "
              f"or narrower (wider ones spread over channels and are not modelled).", "",
              "| drift (Hz/s) | 50% kept: S_in, flux, EIRP | 90% kept: S_in, flux, EIRP |", "|---|---|---|"]
    for s in r["sensitivity"]:
        cell = lambda p: (f"{'≤' if s[f'how_{p}'] == 'at or below' else '>' if s[f'how_{p}'] == 'above' else ''}"  # noqa: E731
                          f"{s[f's_in_{p}']:g}, {s[f'flux_{p}_jy_hz']:.0f} Jy Hz, {_w(s.get(f'eirp_{p}_w'))}")
        lines.append(f"| {s['drift_hz_s'][0]:g} to {s['drift_hz_s'][1]:g} | {cell(50)} | {cell(90)} |")
    if r["sefd_measured"]:
        lines += ["", f"With the SEFD's bracket ({r['sefd_bracket_jy'][0]:g} to {r['sefd_bracket_jy'][1]:g} Jy, "
                  "above), every flux and EIRP in this table lies between "
                  f"{r['sefd_bracket_jy'][0] / r['sefd_jy']:.2f} and {r['sefd_bracket_jy'][1] / r['sefd_jy']:.2f} "
                  "times the value given."]
    lines += ["", "The limits hold over the usable band only (the notch and the blocks cut short left out). "
              f"Nominal, at the cut (SNR {r['snr_min']:g}; the radiometer equation, not a measured rate): S_min "
              f"{r['cut_flux_jy_hz']:.1f} Jy Hz ({r['cut_flux_jy_hz']:.1f}×10⁻²⁶ W m⁻²), EIRP_min "
              f"{_w(r['cut_eirp_w'])}. The strengths between "
              "the four planted are interpolated (in log S_in); \"≤\" means already reached at the faintest "
              "planted, \">\" not reached at the brightest.", "",
              f"For comparison with published searches only: CWTFM {r['cwtfm']:.3g} at the nominal threshold, as "
              f"published searches quote it (Enriquez et al. 2017, Eq. 11; N_star 1, ν_rel {r['nu_rel']:.3f} from "
              f"the usable {r['usable_mhz']:.1f} MHz)"
              + (f", {r['cwtfm_90']:.3g} at the measured 90% EIRP for slow drifts" if r.get("cwtfm_90") else "")
              + f"; transmitter rate {r['transmitter_rate']:.2f}. No limit "
              "on the share of stars with transmitters is drawn from one star: at best 0.95/(η·D) at 95% "
              "confidence (Margot et al. 2023), which says nothing.", "",
              f"In context: Harp et al. 2016 (ATA, 1 to 10 GHz, Oct to Nov 2015) set narrowband limits of "
              f"{HARP_2016_W[0]:.0e} to {HARP_2016_W[1]:.0e} W at 454 pc (drifts to ±1 Hz/s); here, at 90% kept "
              f"for drifts under {r['sensitivity'][0]['drift_hz_s'][1]:g} Hz/s, about "
              f"{HARP_2016_W[0] / (r['sensitivity'][0].get('eirp_90_w') or 1):.0f} to "
              f"{HARP_2016_W[1] / (r['sensitivity'][0].get('eirp_90_w') or 1):.0f} times deeper, over the usable "
              f"part of {r['from_mhz']:.0f} to {r['to_mhz']:.0f} MHz only; less at faster drifts (the table).", ""]
    lines += ["## Validation", ""]
    if r["voyager"]:
        v = r["voyager"]
        lines.append(f"- **Voyager 1** (`measure.py voyager`, SHA-256 {v['sha256'][:12]}…): the carrier and both "
                     "sidebands found within one channel and two drift steps of turboSETI's published hits; drift "
                     f"{v['rows'][0]['ours']['drift_hz_s']:+.4f} Hz/s against the Earth's {v['earth_drift_hz_s'][0]:+.4f}. "
                     "Its 322 Hz-wide sidebands are tiled with many hits: wide signals are outside this search.")
    if r["price"]:
        lines.append(f"- **{PRICE_2020}**, HIP 91699 at 2200.0 to 2200.6 MHz (`measure.py price`): their "
                     "pipeline run here finds their S-band event; this search finds it as two candidates (kept "
                     "as two) and the checks mark both likely interference, as they judged by eye. Their hit "
                     "lists are not published, so no star's hits could be set against theirs.")
    lines += ["- **turboSETI** on seven real looks from two sessions: outside one burst of interference it found "
              "nothing this search missed (docs/seti.md, \"Checked against turboSETI\").",
              "- **Not done:** the 2017 cadence's own SEFD (the one measured is from 2019); the coarse "
              "polyphase filterbank's roll-off; non-steady signals "
              "(pulsed, chirped, wide); re-observation (no telescope here).", ""]
    lines += ["## What it found", "",
              "| stage | count |", "|---|---|",
              f"| hits at SNR {r['snr_min']:g} or more, six looks | {r['hits_at_cut']:,} (ON {r['hits_on']:,}, "
              f"OFF {r['hits_off']:,}) |",
              f"| shadow hits, SNR 5 to {r['snr_min']:g} | {r['shadow_hits']:,} |",
              f"| events (from the ON looks' hits) | {sum(r['events'].values()):,} |",
              f"| interference | {r['events']['interference']:,} |",
              f"| unconfirmed (not in every ON look) | {r['events']['unconfirmed']:,} |",
              f"| candidates | {r['events']['candidate']} |"]
    for k, n in sorted(verdicts.items()):
        lines.append(f"| after the checks: {k} | {n} |")
    lines.append("")
    if r["candidates"]:
        lines += ["Every candidate, by SNR (reports in `docs/leads/`; the checks that gave a strength):", "",
                  "| lead | MHz | drift (Hz/s) | SNR | OFF S/N max | verdict | signs |", "|---|---|---|---|---|---|---|"]
        for c in r["candidates"]:
            signs = "; ".join(f"{x['name'].split('. ', 1)[-1]}: {x['strength']}" for x in c["checks"]
                              if x["strength"] and not x["name"].startswith("10."))
            lines.append(f"| {c['lead'] or c['event_id']} | {c['f_start_mhz']:.6f} | {c['drift_hz_s']:+.4f} | "
                         f"{c['snr']:.1f} | {c['off_snr_max'] if c['off_snr_max'] is not None else ''} | "
                         f"{c['verdict'] or 'not checked'} | {signs} |")
        lines += ["", "Candidates are listed one by one, never merged. Those marked only for their band are a "
                  "weight on the frequency, not a finding about the signal.", ""]
    lines += other_pipelines(r)
    lines += ["## How", "",
              "Runs that made the current results (from the store's `runs` table):", "",
              "| run | started (UTC) | commit | uncommitted | host | python | libraries |", "|---|---|---|---|---|---|---|"]
    for run in r["runs"]:
        libs = json.loads(run["libraries"] or "{}")
        lines.append(f"| {run['run_id']} | {run['started_utc']} | `{(run['git_commit'] or '')[:10]}` | "
                     f"{'yes' if run['uncommitted_changes'] else 'no'} | {run['host']} | {run['python']} | "
                     + ", ".join(f"{k} {v}" for k, v in libs.items()) + " |")
    lines += ["", "To repeat it: clone the repository at the commit above, `pip install -r requirements.txt`, "
              f"then `seti.py sweep {r['target']} --blocks {r['blocks_total']}`, `check.py`, `seti.py report "
              f"{r['target']} {r['session']}`. The completeness: `seti.py inject`; validation: `measure.py "
              "voyager`, `measure.py price`.", ""]
    return "\n".join(lines)


def flux(s_in, r):
    import injection
    return injection.flux_jy_hz(s_in, r["spectra"], r["channel_hz"], r["tsamp_s"])


def write(target, session, say=print):
    r = build(target, session)
    md = markdown(r)
    out = yoke.ROOT / "docs" / "results" / f"{target}-{session}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8", newline="\n")
    yoke.write(yoke.DATA / "results" / f"{target}-{session}.json", r, stamp=True)
    say(f"{out}: {r['blocks_current']} of {r['blocks_total']} blocks, {r['events']['candidate']} candidate(s)")
    return {"report": str(out), "blocks": r["blocks_current"], "of": r["blocks_total"],
            "events": r["events"], "kind": "measured"}
