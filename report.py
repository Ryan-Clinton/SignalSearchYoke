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
    notch = sum(max(0.0, min(b["f_hi_mhz"], NOTCH_MHZ[1]) - max(b["f_lo_mhz"], NOTCH_MHZ[0])) for b in current)
    t = TARGETS.get(target)
    comp = json.load(open(yoke.DATA / "measurements" / "completeness.json"))
    cells = comp["tables"]["by_cell"]
    flux = lambda s: injection.flux_jy_hz(s, n_t, width_hz, tsamp)  # noqa: E731
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
    nu_rel = covered / mid if mid else None
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
        "sefd_jy": injection.SEFD_JY, "cut_flux_jy_hz": cut_flux, "cut_eirp_w": cut_eirp,
        "sensitivity": sens, "nu_rel": nu_rel,
        "cwtfm": zeta * cut_eirp / (1 * nu_rel) if cut_eirp and nu_rel else None,
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
    done = r["blocks_current"] == r["blocks_total"]
    lines += ["## In brief", ""]
    lines += [f"- **Searched:** {r['blocks_current']} of {r['blocks_total']} blocks "
              f"({r['covered_mhz']:.1f} MHz, {r['from_mhz']:.3f} to {r['to_mhz']:.3f} MHz)"
              + ("" if done else " — **the sweep is not complete; this report is partial**") + ".",
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
    lines.append(f"- **Sensitivity:** S_min {r['cut_flux_jy_hz']:.1f} Jy Hz at the cut (SNR {r['snr_min']:g}), "
                 f"EIRP_min {_w(r['cut_eirp_w'])} at {t.get('distance_pc', '?')} pc for a transmitter narrower "
                 f"than 1 Hz, with an assumed SEFD of {r['sefd_jy']:g} Jy; higher at fast drifts (below).")
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
    lines += ["", f"- **Band:** {r['from_mhz']:.3f} to {r['to_mhz']:.3f} MHz searched; of it {r['notch_mhz']:.1f} MHz "
              f"lies in the receiver's notch filter ({NOTCH_MHZ[0]:g} to {NOTCH_MHZ[1]:g} MHz), searched but "
              f"with its sensitivity not measured and left out of the limits below.",
              f"- **Blanked:** one channel in each coarse channel (the spectrometer's spike at its middle): "
              f"{r['blocks_current']} of {r['blocks_current'] * 1048576:,} channels. Nothing else is masked; "
              f"spectral kurtosis is recorded, never used to drop.",
              f"- **Looks cut short:** {r['looks_incomplete']} of {r['looks']} block-looks reached the "
              f"2,000-hit limit (their hits are not all there).",
              f"- **SEFD:** {r['sefd_jy']:g} Jy, Price et al. 2020's figure for Green Bank at S-band: assumed, "
              f"not measured here; every flux and EIRP below scales with it.", ""]
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
    lines += ["", f"At the cut (SNR {r['snr_min']:g}): S_min {r['cut_flux_jy_hz']:.1f} Jy Hz "
              f"({r['cut_flux_jy_hz']:.1f}×10⁻²⁶ W m⁻²), EIRP_min {_w(r['cut_eirp_w'])}. The strengths between "
              "the four planted are interpolated (in log S_in); \"≤\" means already reached at the faintest "
              "planted, \">\" not reached at the brightest.", "",
              f"For comparison with published searches only: CWTFM {r['cwtfm']:.3g} (Enriquez et al. 2017, "
              f"Eq. 11; N_star 1, ν_rel {r['nu_rel']:.3f}), transmitter rate {r['transmitter_rate']:.2f}. No limit "
              "on the share of stars with transmitters is drawn from one star: at best 0.95/(η·D) at 95% "
              "confidence (Margot et al. 2023), which says nothing.", "",
              f"In context: Harp et al. 2016 (ATA, 1 to 10 GHz, Oct to Nov 2015) set narrowband limits of "
              f"{HARP_2016_W[0]:.0e} to {HARP_2016_W[1]:.0e} W at 454 pc; at the cut here, about "
              f"{HARP_2016_W[0] / (r['cut_eirp_w'] or 1):.0f} to {HARP_2016_W[1] / (r['cut_eirp_w'] or 1):.0f} "
              f"times deeper, over {r['from_mhz']:.0f} to {r['to_mhz']:.0f} MHz only and for slow drifts "
              "(at 2 to 4 Hz/s and 90% kept, see the table).", ""]
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
              "- **Not done:** a calibrated SEFD; the polyphase filterbank's channel shape; non-steady signals "
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
