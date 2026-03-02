from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from multiprocessing.synchronize import Event
from queue import Full
from typing import Any, Dict, List

from ..config import AppConfig
from ..models import Device, base_event

PING_TIME_RE = re.compile(r"time[=<]([\d.]+)\s*ms", re.IGNORECASE)


def _is_darwin() -> bool:
    return sys.platform.startswith("darwin")


def _build_ping_cmd(host: str, timeout_ms: int) -> List[str]:
    if _is_darwin():
        return ["ping", "-n", "-c", "1", "-W", str(int(timeout_ms)), host]
    timeout_sec = max(1, int(round(timeout_ms / 1000.0)))
    return ["ping", "-n", "-c", "1", "-W", str(timeout_sec), host]


def _ping_once(device: Device, timeout_ms: int) -> Dict[str, Any]:
    cmd = _build_ping_cmd(device.ip, timeout_ms)
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=max(2.0, timeout_ms / 1000.0 + 1.0),
        )
        out = proc.stdout or ""
        match = PING_TIME_RE.search(out)
        rtt = float(match.group(1)) if match else None
        ok = proc.returncode == 0 and rtt is not None
        return {"ok": ok, "rtt_ms": rtt, "exit_code": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "rtt_ms": None, "exit_code": 124}
    except Exception:
        return {"ok": False, "rtt_ms": None, "exit_code": 255}


def run_network_worker(cfg: AppConfig, queue: Any, stop_event: Event, hostname: str) -> None:
    devices = [cfg.router] + cfg.externals + cfg.locals
    timeout_ms = max(300, int(cfg.dns.timeout_ms))
    local_ips = set()
    try:
        local_ips.update(socket.gethostbyname_ex(hostname)[2])
    except Exception:
        pass

    while not stop_event.is_set():
        started = time.time()
        for device in devices:
            result = _ping_once(device, timeout_ms)
            self_target = device.ip in local_ips
            event = base_event("network", "network.sample", cfg.node_id, hostname)
            event.update(device.to_dict())
            event.update(result)
            event["self_target"] = self_target
            event["classification_eligible"] = not self_target
            try:
                queue.put_nowait(event)
            except Full:
                pass

        hb = base_event("network", "worker.heartbeat", cfg.node_id, hostname)
        hb.update({"samples_emitted": len(devices)})
        try:
            queue.put_nowait(hb)
        except Full:
            pass

        elapsed = time.time() - started
        time.sleep(max(0.0, cfg.timing.network_interval_sec - elapsed))
