from __future__ import annotations

import socket
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from .models import Device


@dataclass
class TimingConfig:
    network_interval_sec: float = 1.0
    dns_interval_sec: float = 2.0


@dataclass
class ThresholdConfig:
    fail_streak: int = 2
    recover_streak: int = 2
    pre_seconds: int = 10
    post_seconds: int = 15
    dns_fail_ratio: float = 0.5


@dataclass
class DNSConfig:
    domains: List[str] = field(default_factory=lambda: [
        "example.com",
        "cloudflare.com",
        "google.com",
        "amazon.com",
    ])
    qtype: str = "A"
    resolvers: List[str] = field(default_factory=lambda: ["system", "1.1.1.1", "8.8.8.8"])
    timeout_ms: int = 1200


@dataclass
class StorageConfig:
    log_dir: str = "./netwatch_logs"
    max_recent_incidents: int = 10


@dataclass
class DiagnosticsConfig:
    enable: bool = True
    traceroute_targets: List[str] = field(default_factory=lambda: ["1.1.1.1", "8.8.8.8"])


@dataclass
class AppConfig:
    node_id: str = ""
    timing: TimingConfig = field(default_factory=TimingConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    dns: DNSConfig = field(default_factory=DNSConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    diagnostics: DiagnosticsConfig = field(default_factory=DiagnosticsConfig)
    router: Device = field(
        default_factory=lambda: Device(
            device_id="tp_link_router",
            name="TP-Link 300Mbps Wireless N Modem Router",
            ip="192.168.1.1",
            role="router",
        )
    )
    externals: List[Device] = field(
        default_factory=lambda: [
            Device("external_cloudflare", "Cloudflare DNS", "1.1.1.1", "external"),
            Device("external_google", "Google DNS", "8.8.8.8", "external"),
        ]
    )
    locals: List[Device] = field(
        default_factory=lambda: [
            Device(
                "netgear_switch",
                "Netgear 24-Port Gigabit Smart Switch PoE + 4 SFP",
                "192.168.1.151",
                "switch",
            ),
            Device("clear_flow", "Clear Flow by Antiference", "192.168.1.200", "local_device"),
            Device("lnk_pi_02", "lnk-pi-02", "192.168.1.108", "observer_node"),
            Device("lnk_pi_01", "lnk-pi-01", "192.168.1.110", "observer_node"),
        ]
    )


def _device_from_dict(d: Dict[str, Any]) -> Device:
    return Device(
        device_id=str(d["device_id"]),
        name=str(d["name"]),
        ip=str(d["ip"]),
        role=str(d.get("role", "local_device")),
    )


def _update_dataclass(obj: Any, values: Dict[str, Any]) -> None:
    for k, v in values.items():
        if hasattr(obj, k):
            setattr(obj, k, v)


def load_config(path: str | None) -> AppConfig:
    cfg = AppConfig()
    cfg.node_id = socket.gethostname()

    if not path:
        return cfg

    loaded = tomllib.loads(Path(path).read_text(encoding="utf-8"))

    if "node_id" in loaded:
        cfg.node_id = str(loaded["node_id"])

    if timing := loaded.get("timing"):
        _update_dataclass(cfg.timing, timing)

    if thresholds := loaded.get("thresholds"):
        _update_dataclass(cfg.thresholds, thresholds)

    if dns := loaded.get("dns"):
        _update_dataclass(cfg.dns, dns)

    if storage := loaded.get("storage"):
        _update_dataclass(cfg.storage, storage)

    if diagnostics := loaded.get("diagnostics"):
        _update_dataclass(cfg.diagnostics, diagnostics)

    if targets := loaded.get("targets"):
        if router := targets.get("router"):
            cfg.router = _device_from_dict(router)
        if externals := targets.get("externals"):
            cfg.externals = [_device_from_dict(item) for item in externals]
        if locals_ := targets.get("locals"):
            cfg.locals = [_device_from_dict(item) for item in locals_]

    return cfg
