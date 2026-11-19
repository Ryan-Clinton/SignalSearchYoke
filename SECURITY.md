# Security

To report a vulnerability, or something in this repository or its history
that should not be public (a credential, a private address), use GitHub's
private vulnerability reporting: the repository's Security tab, "Report a
vulnerability" (switched on when the repository is made public;
docs/releasing.md). Please don't open a public issue for it.

The software reads Breakthrough Listen's public archive over HTTPS. What it
measures it writes under its data folder (`data/`, or `SSY_DATA`); the
commands that make the result pages and the report also write those pages
into the checkout's `docs/` (`docs/results/`, `docs/report/`, `docs/leads/`).
It runs no server and holds no credentials. `tools/history_scan.py` searches
every committed version of every file for keys, tokens, addresses and
local paths.
