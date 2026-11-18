# Third-party notices

## BLISS

Two files in this repository are derived from BLISS
(github.com/UCBerkeleySETI/bliss, at commit
2b98afe960f13ee7e467aca499576d87ee7502f5), used under its BSD 3-Clause
licence, reproduced below:

- `tools/bliss/bliss_events.py`: a Python port, line for line, of BLISS's
  event stage (`bliss/drift_search/event_search.cpp`). Changed: it runs on
  hits already found instead of asking each scan for its hits again, it
  leaves out the distance cache, and it takes the hits in a fixed order (by
  channel, then drift). Its arithmetic and its constants are BLISS's.
- `tools/bliss/event_search_off_hits_once.patch`: a change to BLISS's own
  `event_search.cpp`, applied to a local build for the comparison: each OFF
  scan's hits are read once and kept, instead of being asked for again for
  each candidate, for speed only (patched and unpatched builds gave the same
  events where both were compared: docs/comparable.md, step 11).

These two files are hashed into every BLISS record's configuration
(`matched.bliss_config`), so the notice is kept here rather than in them.

```
BSD 3-Clause License

Copyright (c) 2026, Nathan West, Berkeley SETI Research Center

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Used, not included

These are installed or fetched separately and are not part of this
repository; only code that calls them is here:

- **turboSETI** and **blimpy** (Breakthrough Listen): installed with pip
  in their own environment (`docs/reproducing-results.md`).
- **pickles** (Painter et al. 2025, github.com/UCBerkeleySETI/pickles):
  `pipelines.py` fetches `pickles.py` at a pinned commit into `data/` and
  runs it there; it is not redistributed.
- **setigen** (Brzycki et al. 2022): installed with pip in turboSETI's
  environment.
- **numpy, requests, h5py, hdf5plugin**: installed with pip.
