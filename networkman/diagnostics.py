from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List


def _run_text(cmd: List[str]) -> str:
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
        return proc.stdout or ""
    except Exception as exc:
        return f"command_failed: {exc}\n"


def _find_traceroute_cmd() -> List[str] | None:
    if shutil.which("traceroute"):
        return ["traceroute", "-n"]
    if shutil.which("tracepath"):
        return ["tracepath", "-n"]
    return None


def capture_diagnostics(out_dir: Path, traceroute_targets: List[str], dns_domains: List[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    trace_cmd = _find_traceroute_cmd()
    if trace_cmd:
        for target in traceroute_targets:
            text = _run_text(trace_cmd + [target])
            (out_dir / f"traceroute_{target.replace('.', '_')}.txt").write_text(text, encoding="utf-8")

    for domain in dns_domains[:3]:
        text = _run_text(["dig", "+trace", domain])
        (out_dir / f"dns_trace_{domain.replace('.', '_')}.txt").write_text(text, encoding="utf-8")

    if shutil.which("scutil"):
        dns_text = _run_text(["scutil", "--dns"])
        (out_dir / "system_dns_snapshot.txt").write_text(dns_text, encoding="utf-8")
    elif shutil.which("resolvectl"):
        dns_text = _run_text(["resolvectl", "status"])
        (out_dir / "system_dns_snapshot.txt").write_text(dns_text, encoding="utf-8")
