# SignalSearchYoke

Searches Breakthrough Listen's open radio recordings for narrowband
signals, one slice of the band at a time, with the ON-OFF cadence test
that tells our own interference from a signal from the target.

```
pip install -r requirements.txt
./seti.py find KIC8462852
./seti.py sweep KIC8462852 --blocks 3
```

How it works and where it stands: [HANDOVER.md](HANDOVER.md). The search
and what has been measured: [docs/seti.md](docs/seti.md).
