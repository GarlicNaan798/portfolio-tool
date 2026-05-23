import os
import unittest
from unittest.mock import patch

from portfolio_model.model import PortfolioDecision, ScoreBreakdown
from portfolio_model.runner import execute_orders


class FakeAlpaca:
    def __init__(self, positions):
        self._positions = positions
        self.orders = []

    def account(self):
        return {"account_number": "PAPER123"}

    def positions(self):
        return self._positions

    def submit_market_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"id": "order-1"}


def decision(symbol, action, current_weight, target_weight):
    return PortfolioDecision(
        symbol=symbol,
        action=action,
        score=ScoreBreakdown(
            symbol=symbol,
            value=0.5,
            growth=0.5,
            quality=0.5,
            sentiment=0.5,
            composite=0.5,
            target_weight=target_weight,
        ),
        current_weight=current_weight,
        target_weight=target_weight,
        rationale="test",
    )


class RunnerExecutionTest(unittest.TestCase):
    def test_sell_is_skipped_when_no_paper_position_exists(self):
        client = FakeAlpaca([])
        with patch.dict(os.environ, {"PORTFOLIO_DRY_RUN": "false"}), patch(
            "portfolio_model.runner.AlpacaClient", return_value=client
        ):
            execute_orders([decision("MSFT", "TRIM", 0.10, 0.05)], 250)

        self.assertEqual(client.orders, [])

    def test_sell_uses_qty_capped_to_held_position(self):
        client = FakeAlpaca(
            [{"symbol": "MSFT", "market_value": "100", "current_price": "50", "qty": "2"}]
        )
        with patch.dict(os.environ, {"PORTFOLIO_DRY_RUN": "false"}), patch(
            "portfolio_model.runner.AlpacaClient", return_value=client
        ):
            execute_orders([decision("MSFT", "TRIM", 0.10, 0.00)], 250)

        self.assertEqual(len(client.orders), 1)
        self.assertEqual(client.orders[0]["side"], "sell")
        self.assertEqual(client.orders[0]["qty"], 2.0)

    def test_buy_order_still_submits_notional(self):
        client = FakeAlpaca([])
        with patch.dict(os.environ, {"PORTFOLIO_DRY_RUN": "false"}), patch(
            "portfolio_model.runner.AlpacaClient", return_value=client
        ):
            execute_orders([decision("CRM", "BUY", 0.00, 0.10)], 250)

        self.assertEqual(len(client.orders), 1)
        self.assertEqual(client.orders[0]["side"], "buy")
        self.assertEqual(client.orders[0]["notional"], 250)


if __name__ == "__main__":
    unittest.main()
