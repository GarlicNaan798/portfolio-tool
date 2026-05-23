import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from portfolio_model.model import EquityInput
from portfolio_model.portfolio_state import sync_alpaca_portfolio


class FakeAlpaca:
    def account(self):
        return {"portfolio_value": "10000"}

    def positions(self):
        return []


class PortfolioStateTest(unittest.TestCase):
    def test_empty_alpaca_portfolio_sets_current_weights_to_zero(self):
        universe = [
            EquityInput("MSFT", "Software", 100, 20, 3, 0.05, 0.1, 0.1, 0.5, 0.2, 0, 0.0, 0.10, 20)
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "portfolio.csv"
            with patch("portfolio_model.portfolio_state.alpaca.AlpacaClient", return_value=FakeAlpaca()):
                synced = sync_alpaca_portfolio(universe, snapshot_path=path)
            snapshot = path.read_text(encoding="utf-8")

        self.assertEqual(synced[0].current_weight, 0.0)
        self.assertIn("portfolio_value", snapshot)


if __name__ == "__main__":
    unittest.main()
