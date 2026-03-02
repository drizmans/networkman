#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_incidents(path: Path) -> List[Dict]:
    out = []
    for p in sorted(path.glob("*/incident_summary.json")):
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def overlaps(a: Dict, b: Dict) -> bool:
    a_start, a_end = parse_ts(a["started_at"]), parse_ts(a["ended_at"])
    b_start, b_end = parse_ts(b["started_at"]), parse_ts(b["ended_at"])
    return a_start <= b_end and b_start <= a_end


def main() -> int:
    parser = argparse.ArgumentParser(description="Correlate incidents across two nodes")
    parser.add_argument("--left", required=True, help="Incident dir from node A")
    parser.add_argument("--right", required=True, help="Incident dir from node B")
    args = parser.parse_args()

    left = load_incidents(Path(args.left))
    right = load_incidents(Path(args.right))

    seen_right = set()
    both = []
    left_only = []

    for l in left:
        match = None
        for idx, r in enumerate(right):
            if overlaps(l, r):
                match = r
                seen_right.add(idx)
                break
        if match:
            both.append({"left": l["incident_id"], "right": match["incident_id"], "type": l.get("incident_type")})
        else:
            left_only.append(l["incident_id"])

    right_only = [r["incident_id"] for i, r in enumerate(right) if i not in seen_right]

    print(json.dumps({"seen_by_both": both, "left_only": left_only, "right_only": right_only}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
