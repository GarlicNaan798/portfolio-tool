import unittest

from portfolio_model.exit_manager import build_exit_plan


class ExitManagerTest(unittest.TestCase):
    def test_take_profit_partial_exit(self):
        rows = build_exit_plan(
            [{"symbol": "AAA", "qty": "10", "market_value": "1000", "unrealized_plpc": "0.10"}],
            take_profit_pct=0.08,
            stop_loss_pct=0.04,
            partial_profit_fraction=0.5,
            full_exit_fraction=1.0,
        )

        self.assertEqual(rows[0].status, "TAKE_PROFIT")
        self.assertEqual(rows[0].exit_fraction, 0.5)

    def test_stop_loss_full_exit(self):
        rows = build_exit_plan(
            [{"symbol": "AAA", "qty": "10", "market_value": "1000", "unrealized_plpc": "-0.05"}],
            take_profit_pct=0.08,
            stop_loss_pct=0.04,
            partial_profit_fraction=0.5,
            full_exit_fraction=1.0,
        )

        self.assertEqual(rows[0].status, "STOP_LOSS")
        self.assertEqual(rows[0].exit_fraction, 1.0)


if __name__ == "__main__":
    unittest.main()
