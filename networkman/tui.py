from __future__ import annotations

from typing import Any, Dict, Iterable, List

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _device_table(device_status: Dict[str, Dict[str, Any]]) -> Table:
    table = Table(title="Named Local Devices", expand=True)
    table.add_column("Device")
    table.add_column("IP")
    table.add_column("Role")
    table.add_column("Status")
    table.add_column("Last RTT")
    for item in sorted(device_status.values(), key=lambda x: x.get("device_name", "")):
        ok = item.get("ok", None)
        if ok is True:
            status = "UP"
        elif ok is False:
            status = "DOWN"
        else:
            status = "UNKNOWN"
        rtt = item.get("rtt_ms")
        rtt_s = f"{rtt:.1f} ms" if isinstance(rtt, (int, float)) else "-"
        table.add_row(item.get("device_name", "?"), item.get("target_ip", "?"), item.get("device_role", "?"), status, rtt_s)
    return table


def _dns_table(dns_stats: Dict[str, Dict[str, Any]]) -> Table:
    table = Table(title="DNS Resolver Health", expand=True)
    table.add_column("Resolver")
    table.add_column("Checks")
    table.add_column("Fail %")
    table.add_column("Avg Latency")
    for resolver, stats in sorted(dns_stats.items()):
        checks = stats.get("checks", 0)
        failures = stats.get("failures", 0)
        fail_pct = (failures / checks * 100.0) if checks else 0.0
        lat = stats.get("avg_latency_ms")
        lat_s = f"{lat:.1f} ms" if isinstance(lat, (int, float)) else "-"
        table.add_row(resolver, str(checks), f"{fail_pct:.1f}%", lat_s)
    return table


def _recent_incidents(recent: Iterable[Dict[str, Any]]) -> Table:
    table = Table(title="Recent Incidents", expand=True)
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("Start (UTC)")
    table.add_column("End (UTC)")
    for inc in list(recent)[:10]:
        table.add_row(
            inc.get("incident_id", "?"),
            inc.get("incident_type", "?"),
            inc.get("started_at", "?"),
            inc.get("ended_at", "?"),
        )
    return table


def build_dashboard(
    node_id: str,
    hostname: str,
    active_incident: Dict[str, Any] | None,
    device_status: Dict[str, Dict[str, Any]],
    dns_stats: Dict[str, Dict[str, Any]],
    recent_incidents: List[Dict[str, Any]],
    event_feed: List[str],
) -> Group:
    header = Text(f"Node: {node_id} ({hostname})")
    active_text = (
        f"ACTIVE: {active_incident['incident_type']} ({active_incident['incident_id']})"
        if active_incident
        else "ACTIVE: none"
    )

    feed_lines = "\n".join(event_feed[-8:]) if event_feed else "No transitions yet"
    panels = [
        Panel(header, title="Observer Node"),
        Panel(active_text, title="Incident State"),
        _device_table(device_status),
        _dns_table(dns_stats),
        _recent_incidents(recent_incidents),
        Panel(feed_lines, title="Event Feed"),
    ]
    return Group(*panels)
