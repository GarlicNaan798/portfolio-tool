import tempfile
import unittest
from pathlib import Path

from portfolio_model.model import EquityInput
from portfolio_model.scout import OpportunityScout, ScoutConfig
from portfolio_model.sec import AnnualFundamentals


class FakeAlpaca:
    def latest_bars(self, symbols, *, feed="iex"):
        return {symbol: {"c": 100.0 + index} for index, symbol in enumerate(symbols)}

    def news(self, symbols, *, limit=10):
        return [{"headline": f"{symbols[0]} beats expectations", "summary": "Strong growth"}]


class FakeSec:
    def fundamentals_for_symbol(self, symbol, price):
        if symbol == "MISS":
            return None
        return AnnualFundamentals(
            revenue=1_000_000,
            revenue_yoy=0.15,
            eps_yoy=0.20,
            gross_margin=0.55,
            debt_to_equity=0.25,
            pb=3.0,
            pe=18.0,
            fcf_yield=0.06,
        )


class ScoutTest(unittest.TestCase):
    def test_scout_researches_watchlist_in_parallel(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "watchlist.csv"
            path.write_text("symbol,industry\nGOOD,Software\nMISS,Software\n", encoding="utf-8")
            scout = OpportunityScout(
                ScoutConfig(agents=2, discover_limit=10, watchlist_path=path),
                alpaca=FakeAlpaca(),
                sec=FakeSec(),
            )

            result = scout.run()

        self.assertEqual(result.researched, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.decisions[0].symbol, "GOOD")
        self.assertEqual(len(result.research_checks["GOOD"]), 8)
        self.assertTrue(result.research_checks["GOOD"]["news_sentiment"])

    def test_scout_uses_fallback_price_when_market_data_unavailable(self):
        class NoBarsAlpaca(FakeAlpaca):
            def latest_bars(self, symbols, *, feed="iex"):
                return {}

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "watchlist.csv"
            path.write_text("symbol,industry\nGOOD,Software\n", encoding="utf-8")
            scout = OpportunityScout(
                ScoutConfig(agents=1, discover_limit=10, watchlist_path=path),
                alpaca=NoBarsAlpaca(),
                sec=FakeSec(),
                fallback_universe=[
                    EquityInput("GOOD", "Software", 123.0, 20.0, 3.0, 0.05, 0.1, 0.1, 0.5, 0.2, 0, 0)
                ],
            )

            result = scout.run()

        self.assertEqual(result.researched, 1)


if __name__ == "__main__":
    unittest.main()
