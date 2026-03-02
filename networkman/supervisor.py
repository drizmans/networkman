from __future__ import annotations

import multiprocessing as mp
import socket
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty
from typing import Any, Deque, Dict, List

from rich.console import Console
from rich.live import Live

from .config import AppConfig
from .incident_engine import IncidentEngine
from .logging_io import append_jsonl, ensure_dirs
from .models import base_event, utc_now_iso
from .tui import build_dashboard
from .workers.dns_worker import run_dns_worker
from .workers.network_worker import run_network_worker


class Supervisor:
    def __init__(self, cfg: AppConfig, headless: bool = False):
        self.cfg = cfg
        self.headless = headless
        self.hostname = socket.gethostname()
        self.log_dir = Path(cfg.storage.log_dir)
        ensure_dirs(self.log_dir)
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.events_path = self.log_dir / f"events_{day}.jsonl"

        self.queue: mp.Queue = mp.Queue(maxsize=5000)
        self.stop_event = mp.Event()

        self.network_status: Dict[str, Dict[str, Any]] = {}
        self.dns_rollup: Dict[str, Dict[str, Any]] = {}
        self.feed: Deque[str] = deque(maxlen=60)
        self.event_window: Deque[Dict[str, Any]] = deque(maxlen=max(120, cfg.thresholds.pre_seconds * 25))
        self.tick_events: List[Dict[str, Any]] = []
        self.external_ids = {d.device_id for d in cfg.externals}
        self.router_id = cfg.router.device_id
        self.local_ids = {d.device_id for d in cfg.locals}
        self.local_device_defaults: Dict[str, Dict[str, Any]] = {
            d.device_id: {
                "device_id": d.device_id,
                "device_name": d.name,
                "target_ip": d.ip,
                "device_role": d.role,
                "ok": None,
                "rtt_ms": None,
            }
            for d in cfg.locals
        }

        self.engine = IncidentEngine(cfg, self.log_dir)
        self.workers: Dict[str, mp.Process] = {}

    def _start_worker(self, worker_name: str) -> mp.Process:
        if worker_name == "network_worker":
            proc = mp.Process(
                target=run_network_worker,
                args=(self.cfg, self.queue, self.stop_event, self.hostname),
                name="network_worker",
            )
        else:
            proc = mp.Process(
                target=run_dns_worker,
                args=(self.cfg, self.queue, self.stop_event, self.hostname),
                name="dns_worker",
            )
        proc.start()
        self.workers[worker_name] = proc
        return proc

    def _spawn_workers(self) -> None:
        self._start_worker("network_worker")
        self._start_worker("dns_worker")

    def _ensure_workers(self) -> None:
        for worker_name in ("network_worker", "dns_worker"):
            proc = self.workers.get(worker_name)
            if proc is None or not proc.is_alive():
                self.feed.append(f"{utc_now_iso()} restarting {worker_name}")
                self._start_worker(worker_name)

    def _process_event(self, event: Dict[str, Any]) -> None:
        append_jsonl(self.events_path, event)
        self.event_window.append(event)
        self.tick_events.append(event)

        et = event.get("event_type")
        if et == "network.sample":
            self.network_status[event["device_id"]] = event
        elif et == "dns.sample":
            resolver = event.get("resolver", "unknown")
            stats = self.dns_rollup.setdefault(resolver, {"checks": 0, "failures": 0, "lat_sum": 0.0, "lat_count": 0})
            stats["checks"] += 1
            if not event.get("ok", False):
                stats["failures"] += 1
            latency = event.get("latency_ms")
            if isinstance(latency, (int, float)):
                stats["lat_sum"] += latency
                stats["lat_count"] += 1
                stats["avg_latency_ms"] = stats["lat_sum"] / max(1, stats["lat_count"])
        elif et == "incident.state":
            state = event.get("state")
            self.feed.append(f"{event['ts_utc']} {state} {event.get('incident_type', '')} {event.get('incident_id', '')}")

    def _snapshot(self) -> Dict[str, Any]:
        router_ok = False
        external_up = 0
        local_down: List[str] = []
        dns_checks = 0
        dns_fails = 0
        router_seen = False
        external_seen = set()

        for item in self.network_status.values():
            device_id = item.get("device_id")
            role = item.get("device_role")
            ok = bool(item.get("ok", False))
            if device_id == self.router_id:
                router_seen = True
            if role == "router":
                router_ok = ok
            elif role == "external":
                if device_id:
                    external_seen.add(device_id)
                if ok:
                    external_up += 1
            elif role in {"switch", "local_device", "observer_node"} and not ok and item.get("classification_eligible", True):
                local_down.append(item.get("device_name", item.get("target_ip", "unknown")))

        for stats in self.dns_rollup.values():
            dns_checks += stats.get("checks", 0)
            dns_fails += stats.get("failures", 0)

        dns_fail_ratio = (dns_fails / dns_checks) if dns_checks else 0.0
        network_ready = router_seen and self.external_ids.issubset(external_seen)
        dns_ready = dns_checks > 0
        return {
            "router_ok": router_ok,
            "external_up": external_up,
            "local_down": local_down,
            "dns_fail_ratio": dns_fail_ratio,
            "network_ready": network_ready,
            "dns_ready": dns_ready,
        }

    def _emit_supervisor_events(self, items: List[Dict[str, Any]]) -> None:
        for event in items:
            append_jsonl(self.events_path, event)
            if event.get("event_type") == "incident.state":
                state = event.get("state")
                self.feed.append(f"{event['ts_utc']} {state} {event.get('incident_type')} {event.get('incident_id')}")

    def run(self) -> None:
        console = Console()
        self._spawn_workers()

        try:
            if self.headless:
                self._run_headless(console)
            else:
                self._run_live(console)
        finally:
            self.stop_event.set()
            for proc in self.workers.values():
                proc.join(timeout=2)
                if proc.is_alive():
                    proc.terminate()

    def _run_headless(self, console: Console) -> None:
        last_eval = time.monotonic()
        while True:
            self._drain_events(0.5)
            now = time.monotonic()
            if now - last_eval >= 1.0:
                self._ensure_workers()
                snapshot = self._snapshot()
                outputs = self.engine.update(snapshot, list(self.event_window), self.tick_events)
                self._emit_supervisor_events(outputs)
                active = self.engine.active.incident_type if self.engine.active else "none"
                console.print(f"{utc_now_iso()} active={active} router_ok={snapshot['router_ok']} dns_fail_ratio={snapshot['dns_fail_ratio']:.2f}")
                self.tick_events = []
                last_eval = now

    def _run_live(self, console: Console) -> None:
        last_eval = time.monotonic()
        with Live(console=console, refresh_per_second=4, screen=True) as live:
            while True:
                self._drain_events(0.25)
                now = time.monotonic()
                if now - last_eval >= 1.0:
                    self._ensure_workers()
                    snapshot = self._snapshot()
                    outputs = self.engine.update(snapshot, list(self.event_window), self.tick_events)
                    self._emit_supervisor_events(outputs)
                    self.tick_events = []
                    last_eval = now

                active = None
                if self.engine.active:
                    active = {
                        "incident_id": self.engine.active.incident_id,
                        "incident_type": self.engine.active.incident_type,
                    }
                dashboard = build_dashboard(
                    self.cfg.node_id,
                    self.hostname,
                    active,
                    self.network_status.get(self.router_id),
                    self._build_external_view(),
                    self._build_local_device_view(),
                    self.dns_rollup,
                    list(self.engine.recent),
                    list(self.feed),
                )
                live.update(dashboard)

    def _drain_events(self, timeout: float) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                event = self.queue.get(timeout=0.05)
            except Empty:
                continue
            self._process_event(event)

    def _build_local_device_view(self) -> Dict[str, Dict[str, Any]]:
        view = dict(self.local_device_defaults)
        for device_id, status in self.network_status.items():
            if device_id in self.local_ids:
                view[device_id] = status
        return view

    def _build_external_view(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for device_id, status in self.network_status.items():
            if device_id in self.external_ids:
                out[device_id] = status
        return out
