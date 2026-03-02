from __future__ import annotations

import socket
import subprocess
import time
from multiprocessing.synchronize import Event
from queue import Full
from typing import Any

from ..config import AppConfig
from ..models import base_event


def _dig_query(domain: str, qtype: str, resolver: str, timeout_ms: int) -> dict:
    cmd = ["dig", "+time=1", "+tries=1", "+short", domain, qtype]
    if resolver != "system":
        cmd = ["dig", "+time=1", "+tries=1", "+short", f"@{resolver}", domain, qtype]

    start = time.perf_counter()
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=max(2, timeout_ms / 1000.0 + 1))
        latency_ms = (time.perf_counter() - start) * 1000.0
        out = (proc.stdout or "").strip()
        ok = proc.returncode == 0 and bool(out)
        return {
            "ok": ok,
            "rcode": "NOERROR" if ok else "NOANSWER",
            "latency_ms": round(latency_ms, 2),
            "answer_count": len([line for line in out.splitlines() if line.strip()]),
            "error_class": "" if ok else "empty_answer",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "rcode": "TIMEOUT", "latency_ms": None, "answer_count": 0, "error_class": "timeout"}
    except Exception:
        return {"ok": False, "rcode": "ERROR", "latency_ms": None, "answer_count": 0, "error_class": "exception"}


def run_dns_worker(cfg: AppConfig, queue: Any, stop_event: Event, hostname: str) -> None:
    while not stop_event.is_set():
        started = time.time()
        emitted = 0
        for resolver in cfg.dns.resolvers:
            for domain in cfg.dns.domains:
                result = _dig_query(domain, cfg.dns.qtype, resolver, cfg.dns.timeout_ms)
                event = base_event("dns", "dns.sample", cfg.node_id, hostname)
                event.update({"resolver": resolver, "domain": domain, "qtype": cfg.dns.qtype})
                event.update(result)
                try:
                    queue.put_nowait(event)
                except Full:
                    pass
                emitted += 1

        hb = base_event("dns", "worker.heartbeat", cfg.node_id, hostname)
        hb.update({"samples_emitted": emitted})
        try:
            queue.put_nowait(hb)
        except Full:
            pass

        elapsed = time.time() - started
        time.sleep(max(0.0, cfg.timing.dns_interval_sec - elapsed))
