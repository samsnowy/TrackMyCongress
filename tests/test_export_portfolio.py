import json
import unittest
from unittest.mock import mock_open, patch

from main import _read_live_positions


class ExportPortfolioTests(unittest.TestCase):
    def test_pending_entry_metadata_is_available_to_broker_snapshot(self):
        state = {
            "open_positions": [],
            "pending_entries": [
                {
                    "ticker": "NVDA",
                    "politicians": ["Cleo Fields"],
                    "entry_date": "2026-07-22",
                    "order_id": "filled-after-check",
                    "qty": 231,
                    "entry_price": 213.51,
                    "source": "stock",
                }
            ],
        }

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=json.dumps(state))
        ):
            positions = _read_live_positions()

        self.assertEqual(positions[0]["ticker"], "NVDA")
        self.assertEqual(positions[0]["entry_date"], "2026-07-22")
        self.assertEqual(positions[0]["politicians"], ["Cleo Fields"])
        self.assertEqual(positions[0]["lifecycle"], "pending")

    def test_open_position_metadata_wins_over_pending_duplicate(self):
        state = {
            "open_positions": [{"ticker": "NVDA", "politicians": ["Confirmed"]}],
            "pending_entries": [{"ticker": "NVDA", "politicians": ["Pending"]}],
        }

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=json.dumps(state))
        ):
            positions = _read_live_positions()

        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["politicians"], ["Confirmed"])
        self.assertEqual(positions[0]["lifecycle"], "open")


if __name__ == "__main__":
    unittest.main()
