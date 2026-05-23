import unittest

from portfolio_model.execution_coordinator import build_execution_plan, conviction_trade_cap
from portfolio_model.model import PortfolioDecision, ScoreBreakdown


def decision(symbol: str, action: str, value: float, growth: float, quality: float, sentiment: float):
    return PortfolioDecision(
        symbol=symbol,
        action=action,
        score=ScoreBreakdown(symbol, value, growth, quality, sentiment, 0.7, 0.1),
        current_weight=0.0,
        target_weight=0.1,
        rationale="test",
    )


class ExecutionCoordinatorTest(unittest.TestCase):
    def test_allocates_only_validated_buy_signals(self):
        rows = build_execution_plan(
            [
                decision("GOOD", "BUY", 0.9, 0.9, 0.9, 0.9),
                decision("HOLD", "HOLD", 0.9, 0.9, 0.9, 0.9),
                decision("LOW", "BUY", 0.2, 0.2, 0.2, 0.2),
            ],
            account={"buying_power": "10000"},
            max_trade_notional=250,
            min_opportunity_score=6.5,
            buying_power_fraction=0.25,
        )

        by_symbol = {row.symbol: row for row in rows}
        self.assertEqual(by_symbol["GOOD"].status, "APPROVED")
        self.assertEqual(by_symbol["GOOD"].notional, 1000)
        self.assertEqual(by_symbol["GOOD"].buying_power, 10000)
        self.assertIn("buying power", by_symbol["GOOD"].allocation_note)
        self.assertEqual(by_symbol["HOLD"].status, "REJECTED")
        self.assertEqual(by_symbol["LOW"].status, "REJECTED")

    def test_conviction_cap_scales_with_account_capital(self):
        cap = conviction_trade_cap(
            {"cash": "92912.82", "buying_power": "387987.4", "equity": "99065.67"},
            {
                "max_trade_notional": 250,
                "max_trade_fraction_of_buying_power": 0.01,
                "max_position_fraction_of_equity": 0.03,
                "min_conviction_notional": 1000,
            },
        )

        self.assertAlmostEqual(cap, 2971.97, places=2)


if __name__ == "__main__":
    unittest.main()
