from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Device:
    device_id: str
    name: str
    ip: str
    role: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_name": self.name,
            "target_ip": self.ip,
            "device_role": self.role,
        }


def base_event(worker: str, event_type: str, node_id: str, hostname: str) -> Dict[str, Any]:
    return {
        "ts_utc": utc_now_iso(),
        "worker": worker,
        "event_type": event_type,
        "node_id": node_id,
        "hostname": hostname,
    }
