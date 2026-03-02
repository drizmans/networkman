from __future__ import annotations

import unittest

from networkman.config import load_config


class ConfigTests(unittest.TestCase):
    def test_default_named_locals_present(self) -> None:
        cfg = load_config(None)
        ids = {d.device_id for d in cfg.locals}
        self.assertIn("netgear_switch", ids)
        self.assertIn("lnk_pi_01", ids)
        self.assertIn("lnk_pi_02", ids)


if __name__ == "__main__":
    unittest.main()
