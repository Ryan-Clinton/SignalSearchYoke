# SignalSearchYoke

Searches Breakthrough Listen's open radio recordings for narrowband
signals, one slice of the band at a time, with the ON-OFF cadence test
that tells our own interference from a signal from the target.

Linux:

```
pip install -r requirements.txt
./seti.py find KIC8462852
./seti.py sweep KIC8462852 --blocks 3
```

Windows (PowerShell, Python 3.11 or later from python.org):

```
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python seti.py find KIC8462852
.venv\Scripts\python seti.py sweep KIC8462852 --blocks 3
.venv\Scripts\python check.py
```

How it works and where it stands: [HANDOVER.md](HANDOVER.md). The search
and what has been measured: [docs/seti.md](docs/seti.md).
