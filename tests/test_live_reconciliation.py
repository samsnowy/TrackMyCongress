import unittest

from congress.live import _reconcile_entries, _sync_positions_from_broker


class ReconcileEntriesTests(unittest.TestCase):
    def test_rejected_legacy_position_is_removed_and_signal_is_retryable(self):
        position = {
            "ticker": "NVDA",
            "order_id": "rejected-order",
            "signal_date": "2026-07-16",
            "politicians": ["Cleo Fields"],
        }
        seen = {"NVDA_2026-07-16_Cleo Fields"}

        open_positions, pending = _reconcile_entries(
            [position],
            [],
            seen,
            set(),
            lambda _: {"status": "rejected", "filled_qty": 0},
        )

        self.assertEqual(open_positions, [])
        self.assertEqual(pending, [])
        self.assertEqual(seen, set())

    def test_pending_order_stays_pending(self):
        position = {
            "ticker": "NVDA",
            "order_id": "new-order",
            "signal_keys": ["nvda-key"],
        }
        seen = {"nvda-key"}

        open_positions, pending = _reconcile_entries(
            [],
            [position],
            seen,
            set(),
            lambda _: {"status": "accepted", "filled_qty": 0},
        )

        self.assertEqual(open_positions, [])
        self.assertEqual(pending, [position])
        self.assertEqual(seen, {"nvda-key"})

    def test_filled_pending_order_is_promoted_with_actual_fill(self):
        position = {
            "ticker": "NVDA",
            "order_id": "filled-order",
            "qty": 239,
            "entry_price": 207.29,
        }

        open_positions, pending = _reconcile_entries(
            [],
            [position],
            set(),
            set(),
            lambda _: {
                "status": "filled",
                "filled_qty": 237,
                "filled_avg_price": 208.12,
            },
        )

        self.assertEqual(pending, [])
        self.assertEqual(open_positions[0]["qty"], 237)
        self.assertEqual(open_positions[0]["entry_price"], 208.12)

    def test_legacy_open_broker_position_wins_without_an_order_lookup(self):
        position = {"ticker": "NVDA", "order_id": "filled-order"}

        def unexpected_lookup(_):
            self.fail("filled broker positions should not need an order lookup")

        open_positions, pending = _reconcile_entries(
            [position], [], set(), {"NVDA"}, unexpected_lookup
        )

        self.assertEqual(open_positions, [position])
        self.assertEqual(pending, [])

    def test_pending_fill_records_fill_date(self):
        position = {"ticker": "NVDA", "order_id": "filled-order"}

        open_positions, _ = _reconcile_entries(
            [],
            [position],
            set(),
            {"NVDA"},
            lambda _: {
                "status": "filled",
                "filled_qty": 239,
                "filled_avg_price": 208.12,
                "filled_at": "2026-07-23 13:31:00+00:00",
            },
        )

        self.assertEqual(open_positions[0]["entry_date"], "2026-07-23")


class BrokerPositionSyncTests(unittest.TestCase):
    def test_split_adjusted_quantity_and_cost_basis_replace_stale_state(self):
        state_position = {
            "ticker": "MNST",
            "qty": 489,
            "entry_price": 96.529918,
            "entry_date": "2026-05-20",
            "planned_exit": "2026-08-18",
            "politicians": ["Example Politician"],
        }
        broker_positions = [
            {
                "ticker": "MNST",
                "qty": 978,
                "avg_entry": 48.264959,
                "current_price": 45.96,
                "unrealized_pl": -2254.45,
            }
        ]

        synced = _sync_positions_from_broker([state_position], broker_positions)

        self.assertEqual(synced[0]["qty"], 978)
        self.assertEqual(synced[0]["entry_price"], 48.264959)
        self.assertEqual(synced[0]["planned_exit"], "2026-08-18")
        self.assertEqual(synced[0]["politicians"], ["Example Politician"])

    def test_missing_broker_position_does_not_destroy_local_state(self):
        state_position = {"ticker": "MNST", "qty": 489, "entry_price": 96.529918}

        synced = _sync_positions_from_broker([state_position], [])

        self.assertEqual(synced[0], state_position)


if __name__ == "__main__":
    unittest.main()
