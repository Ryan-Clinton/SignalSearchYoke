# Control C and a candidate version of the checks: the protocol

Fixed on 24 November 2026, and committed before control C's sessions were
chosen or any of their data read. Any change after that is logged at the
end of this file with its reason.

## Why

On control B's cadences, signals planted in the ON looks showed that the
checks keep about three in four real-looking candidates in complete
blocks, but one in five in blocks at the hit cap (docs/audits.md, audit 4).
Left out in turn, the known-band check (check 3) stood alone against 298
of the 493 planted candidates the checks did not keep at S/N 30, and alone
against none of control B's 158 false candidates.

That was found on control B, so control B can't also be the test of a
change made because of it. Control C is that test.

## The candidate version: checks 6

Version 5, the checks in force, with one change. Check 3 still names any
listed band a candidate lies in, but being in one is **context, not a sign
of interference**: it no longer makes a candidate "likely interference" on
its own. Every other check, threshold and rule is unchanged
(`vetting.vet(..., bands_as_context=True)`, version label
`VERSION_BANDS_AS_CONTEXT`). It is not in force: the checks of steps 4, 10
and 12, and of report 1.7, stay version 5 unless the rule below adopts
version 6.

## Control C

- **The cadences:** the next four sessions by control B's own rule
  (`tools/negative_controls.py`'s docstring), never a session or ON target
  that control B or this project has read: `negative_controls.py select
  --control c`.
- **The sweep:** each searched whole by the search as frozen, in a store of
  its own (`data/controls_c/`).
- **The checks:** both version 5 and version 6 on every candidate, kept
  apart by version.
- **Planted signals:** `docs/control-injection.md`'s protocol unchanged on
  these cadences, with seed 20261125. That is 32 blocks, four capped and
  four complete in each cadence, and 3,520 signals. Every planted candidate
  is judged by both versions.

## The rule for adopting version 6, fixed now

Version 6 becomes the checks' next version only if, on control C, both of
these hold:

1. **It keeps more real-looking signals.** Among planted candidates at S/N
   30, the share left unexplained is higher under version 6 than under
   version 5:
   - in capped blocks; and
   - weighted to control C's own mix of capped and complete blocks.

   In both cases the lower end of a 95% interval for the paired
   difference, with blocks resampled, must be above 0.
2. **It does not let interference through.** Control C's real candidates
   at S/N 30 left unexplained by version 6 must be at most 0.02 a block
   over all four cadences. The upper end of the interval from resampled
   runs of 16 consecutive blocks must be at most 0.05.

`tools/control_c_verdict.py` applies this rule. It was written and tested
before any of control C's results existed.

If either fails, version 5 stays, and the result is reported as measured.
Either way the outcome is written up, failure included. Nothing about
either version, or any threshold, is changed after control C's data is
read. Version 6 was also evaluated on control B, where it was designed;
that result is reported as descriptive only.

## Limits known now

- Four more cadences, still from one telescope.
- Clean planted tones, and the project's own planting method.
- Under version 6, a real transmitter in a listed band can only be caught
  by the other checks. The second part of the rule measures what that
  costs, on four cadences.

## Changes after this was fixed

- 24 November 2026, before any spectra were read: the first draw chose the
  same session, AGBT16B_999_09, under three catalogue stars (HIP 400, 428
  and 443), because the rule skipped targets already chosen but not
  sessions. A control holds a session once, so the rule now passes over a
  session already chosen, and the draw was made again. Only the archive
  listing and the first file's header had been read. Control B's draw is
  unaffected: its four sessions were all different.
