# networkman v2

Dual-process network and DNS monitoring with incident capture for ISP escalation.

## Run

Install dependency:

```bash
pip3 install -r requirements.txt
```

Then run:

```bash
python3 main.py
```

Headless mode:

```bash
python3 main.py --headless
```

Shell wrapper:

```bash
./main.sh
```

Validate config:

```bash
python3 main.py --once --config config.toml.example
```

## Design

- Parent supervisor process: logging, incident detection, Rich TUI.
- Worker process 1: ICMP reachability for router/externals/named local devices.
- Worker process 2: DNS checks via system and public resolvers.

## Evidence output

- Daily event log: `netwatch_logs/events_YYYYMMDD.jsonl`
- Incident bundles: `netwatch_logs/incidents/<incident_id>/`
  - `incident_summary.json`
  - `timeline.jsonl`
  - diagnostics snapshots (`traceroute`, `dig +trace`, system DNS)

## Dual-node correlation

Run on each Pi independently, then compare:

```bash
python3 tools/compare_incidents.py --left /path/pi1/incidents --right /path/pi2/incidents
```
