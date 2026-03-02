from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from networkman.config import load_config
from networkman.incident_engine import IncidentEngine


class IncidentEngineTests(unittest.TestCase):
    def test_not_ready_does_not_classify_outage(self) -> None:
        cfg = load_config(None)
        with tempfile.TemporaryDirectory() as tmp:
            cfg.storage.log_dir = tmp
            engine = IncidentEngine(cfg, Path(tmp))
            is_outage, incident_type, _ = engine._classify(
                {
                    "network_ready": False,
                    "dns_ready": False,
                    "router_ok": False,
                    "external_up": 0,
                    "local_down": [],
                    "dns_fail_ratio": 1.0,
                }
            )
            self.assertFalse(is_outage)
            self.assertEqual(incident_type, "")

    def test_dns_degraded_classification(self) -> None:
        cfg = load_config(None)
        with tempfile.TemporaryDirectory() as tmp:
            cfg.storage.log_dir = tmp
            engine = IncidentEngine(cfg, Path(tmp))
            is_outage, incident_type, _ = engine._classify(
                {
                    "network_ready": True,
                    "dns_ready": True,
                    "router_ok": True,
                    "external_up": 2,
                    "local_down": [],
                    "dns_fail_ratio": 0.8,
                }
            )
            self.assertTrue(is_outage)
            self.assertEqual(incident_type, "DNS_PATH_DEGRADED")


if __name__ == "__main__":
    unittest.main()
