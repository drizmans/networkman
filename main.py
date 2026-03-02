#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import sys

from networkman.config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="networkman v2: dual-process network + DNS monitor")
    parser.add_argument("--config", default=None, help="Path to TOML config")
    parser.add_argument("--log-dir", default=None, help="Override log directory")
    parser.add_argument("--node-id", default=None, help="Override node identifier")
    parser.add_argument("--headless", action="store_true", help="Run without Rich TUI")
    parser.add_argument("--no-diagnostics", action="store_true", help="Disable incident diagnostics capture")
    parser.add_argument("--once", action="store_true", help="Validate config and print effective settings")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)

    if args.log_dir:
        cfg.storage.log_dir = args.log_dir
    if args.node_id:
        cfg.node_id = args.node_id
    if args.no_diagnostics:
        cfg.diagnostics.enable = False

    if args.once:
        print("networkman v2 config validated")
        print(f"node_id={cfg.node_id}")
        print(f"log_dir={cfg.storage.log_dir}")
        print(f"router={cfg.router.name} ({cfg.router.ip})")
        print(f"local_devices={', '.join(f'{d.name} ({d.ip})' for d in cfg.locals)}")
        print(f"dns_resolvers={', '.join(cfg.dns.resolvers)}")
        return 0

    from networkman.supervisor import Supervisor

    supervisor = Supervisor(cfg, headless=args.headless)

    def _stop(*_args):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        supervisor.run()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
