from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from .config import AppConfig
from .diagnostics import capture_diagnostics
from .logging_io import write_json, write_jsonl
from .models import utc_now_iso


@dataclass
class Incident:
    incident_id: str
    incident_type: str
    started_at: str


class IncidentEngine:
    def __init__(self, cfg: AppConfig, log_dir: Path):
        self.cfg = cfg
        self.log_dir = log_dir
        self.fail_streak = 0
        self.ok_streak = 0
        self.active: Optional[Incident] = None
        self.waiting_post = False
        self.post_remaining = 0
        self.captured: List[Dict[str, Any]] = []
        self.recent: Deque[Dict[str, Any]] = deque(maxlen=cfg.storage.max_recent_incidents)

    def _classify(self, snapshot: Dict[str, Any]) -> tuple[bool, str, Dict[str, Any]]:
        if not snapshot.get("network_ready", False):
            # Avoid false startup incidents before initial samples arrive.
            return False, "", {"reason": "network_not_ready"}

        router_ok = bool(snapshot.get("router_ok", False))
        external_up = int(snapshot.get("external_up", 0))
        local_down = snapshot.get("local_down", [])
        dns_fail_ratio = float(snapshot.get("dns_fail_ratio", 0.0))
        dns_ready = bool(snapshot.get("dns_ready", False))

        lan_down = not router_ok
        wan_down = router_ok and external_up == 0
        dns_bad = dns_ready and dns_fail_ratio >= self.cfg.thresholds.dns_fail_ratio
        local_flap = router_ok and external_up > 0 and len(local_down) > 0

        if lan_down:
            return True, "LAN_ROUTER_DOWN", {"router_ok": router_ok}
        if wan_down and dns_bad:
            return True, "COMBINED_WAN_DNS_OUTAGE", {"router_ok": router_ok, "dns_fail_ratio": dns_fail_ratio}
        if wan_down:
            return True, "WAN_UPSTREAM_DOWN", {"router_ok": router_ok, "external_up": external_up}
        if dns_bad:
            return True, "DNS_PATH_DEGRADED", {"dns_fail_ratio": dns_fail_ratio}
        if local_flap:
            return True, "LOCAL_DEVICE_FLAP", {"local_down": local_down}
        return False, "", {}

    def _start_incident(self, incident_type: str, pre_events: List[Dict[str, Any]]) -> Incident:
        incident_id = utc_now_iso().replace(":", "").replace("-", "")
        incident = Incident(incident_id=incident_id, incident_type=incident_type, started_at=utc_now_iso())
        self.active = incident
        self.captured = list(pre_events)
        self.waiting_post = False
        self.post_remaining = 0
        return incident

    def _close_incident(self, cfg: AppConfig) -> Optional[Dict[str, Any]]:
        if not self.active:
            return None
        closed = utc_now_iso()
        duration_s = (
            datetime.fromisoformat(closed).timestamp()
            - datetime.fromisoformat(self.active.started_at).timestamp()
        )
        summary = {
            "incident_id": self.active.incident_id,
            "incident_type": self.active.incident_type,
            "started_at": self.active.started_at,
            "ended_at": closed,
            "duration_seconds": duration_s,
            "node_id": cfg.node_id,
            "event_count": len(self.captured),
        }

        incident_dir = self.log_dir / "incidents" / self.active.incident_id
        incident_dir.mkdir(parents=True, exist_ok=True)
        write_json(incident_dir / "incident_summary.json", summary)
        write_jsonl(incident_dir / "timeline.jsonl", self.captured)

        if cfg.diagnostics.enable:
            capture_diagnostics(incident_dir / "diagnostics", cfg.diagnostics.traceroute_targets, cfg.dns.domains)

        self.recent.appendleft(summary)
        self.active = None
        self.captured = []
        self.waiting_post = False
        self.post_remaining = 0
        self.fail_streak = 0
        self.ok_streak = 0
        return summary

    def update(
        self,
        snapshot: Dict[str, Any],
        recent_events: List[Dict[str, Any]],
        tick_events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        out_events: List[Dict[str, Any]] = []
        is_outage, incident_type, reason = self._classify(snapshot)

        if not self.active and not self.waiting_post:
            if is_outage:
                self.fail_streak += 1
                if self.fail_streak >= self.cfg.thresholds.fail_streak:
                    incident = self._start_incident(incident_type, recent_events)
                    evt = {
                        "ts_utc": utc_now_iso(),
                        "worker": "supervisor",
                        "event_type": "incident.state",
                        "node_id": self.cfg.node_id,
                        "state": "started",
                        "incident_id": incident.incident_id,
                        "incident_type": incident.incident_type,
                        "reason": reason,
                    }
                    out_events.append(evt)
            else:
                self.fail_streak = 0
            return out_events

        if self.active and not self.waiting_post:
            self.captured.extend(tick_events)
            if is_outage:
                self.ok_streak = 0
            else:
                self.ok_streak += 1
                if self.ok_streak >= self.cfg.thresholds.recover_streak:
                    self.waiting_post = True
                    self.post_remaining = self.cfg.thresholds.post_seconds
                    out_events.append(
                        {
                            "ts_utc": utc_now_iso(),
                            "worker": "supervisor",
                            "event_type": "incident.state",
                            "node_id": self.cfg.node_id,
                            "state": "recovering",
                            "incident_id": self.active.incident_id,
                            "incident_type": self.active.incident_type,
                            "reason": reason,
                        }
                    )
            return out_events

        if self.waiting_post:
            self.captured.extend(tick_events)
            self.post_remaining -= 1
            if self.post_remaining <= 0:
                closed = self._close_incident(self.cfg)
                if closed:
                    out_events.append(
                        {
                            "ts_utc": utc_now_iso(),
                            "worker": "supervisor",
                            "event_type": "incident.state",
                            "node_id": self.cfg.node_id,
                            "state": "closed",
                            "incident_id": closed["incident_id"],
                            "incident_type": closed["incident_type"],
                            "reason": {},
                        }
                    )

        return out_events
