from __future__ import annotations

import unittest

from tools.compare_incidents import overlaps


class CompareTests(unittest.TestCase):
    def test_overlap_true(self) -> None:
        left = {"started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:01:00+00:00"}
        right = {"started_at": "2026-01-01T00:00:30+00:00", "ended_at": "2026-01-01T00:02:00+00:00"}
        self.assertTrue(overlaps(left, right))


if __name__ == "__main__":
    unittest.main()
