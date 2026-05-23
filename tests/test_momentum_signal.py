import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from portfolio_model.backtest import PriceBar
from portfolio_model.momentum_execution import execute_paper_plan, execution_error_rows
from portfolio_model.momentum_signal import (
    build_paper_plan,
    load_cached_bars,
    trade_action,
)


class FakeMomentumAlpaca:
    def __init__(self, *, base_url="https://paper-api.alpaca.markets", open_orders=None):
        self.config = SimpleNamespace(base_url=base_url)
        self.open_orders = open_orders or []
        self.submitted = []

    def account(self):
        return {"buying_power": "10000", "cash": "10000"}

    def positions(self):
        return []

    def orders(self, *, status="open", limit=100):
        return self.open_orders

    def submit_market_order(self, **kwargs):
        self.submitted.append(kwargs)
        return {"id": "paper-order-1", "status": "accepted"}


class MomentumSignalTest(unittest.TestCase):
    def test_build_paper_plan_scales_targets_to_strategy_sleeve(self):
        signal_rows = [
            {
                "run_date": "2026-05-20",
                "signal_date": "2026-05-19",
                "symbol": "MSFT",
                "strategy_sleeve_weight": "0.2500",
            }
        ]
        plan = build_paper_plan(
            signal_rows,
            account={"portfolio_value": "100000"},
            positions={"MSFT": {"market_value": "1000"}, "AAPL": {"market_value": "500"}},
            sleeve_fraction=0.10,
            min_trade_notional=25,
        )

        msft = next(row for row in plan if row["symbol"] == "MSFT")
        aapl = next(row for row in plan if row["symbol"] == "AAPL")
        self.assertEqual(msft["target_notional"], "2500.00")
        self.assertEqual(msft["current_notional"], "1000.00")
        self.assertEqual(msft["action"], "BUY")
        self.assertEqual(aapl["action"], "REVIEW")
        self.assertEqual(aapl["status"], "UNMANAGED_POSITION")

    def test_trade_action_uses_min_notional_band(self):
        self.assertEqual(trade_action(30, 25), "BUY")
        self.assertEqual(trade_action(-30, 25), "SELL")
        self.assertEqual(trade_action(10, 25), "HOLD")

    def test_load_cached_bars_filters_requested_symbols(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir) / "bars.json"
            today = date(2026, 5, 20)
            cache.write_text(
                '{"bars": {"MSFT": [{"day": "2026-05-19", "close": 420}], '
                '"AAPL": [{"day": "2026-05-19", "close": 190}]}}',
                encoding="utf-8",
            )

            bars = load_cached_bars(cache, {"MSFT"})

        self.assertEqual(list(bars), ["MSFT"])
        self.assertEqual(bars["MSFT"], [PriceBar(today - timedelta(days=1), 420.0)])

    def test_execute_paper_plan_submits_buy_deltas_only(self):
        client = FakeMomentumAlpaca()
        plan = [
            {"signal_date": "2026-05-20", "symbol": "MSFT", "action": "BUY", "delta_notional": "1500"},
            {"signal_date": "2026-05-20", "symbol": "AAPL", "action": "REVIEW", "delta_notional": "0"},
        ]

        with patch.dict("os.environ", {"PORTFOLIO_DRY_RUN": "false"}):
            results = execute_paper_plan(plan, run_date=date(2026, 5, 21), max_order_notional=1000, client=client)

        self.assertEqual(len(client.submitted), 1)
        self.assertEqual(client.submitted[0]["symbol"], "MSFT")
        self.assertEqual(client.submitted[0]["notional"], 1000)
        self.assertEqual(results[0]["status"], "ACCEPTED")
        self.assertEqual(results[1]["status"], "SKIPPED")

    def test_execute_paper_plan_requires_paper_endpoint(self):
        client = FakeMomentumAlpaca(base_url="https://api.alpaca.markets")
        with patch.dict("os.environ", {"PORTFOLIO_DRY_RUN": "false"}):
            with self.assertRaises(RuntimeError):
                execute_paper_plan([], run_date=date(2026, 5, 21), max_order_notional=1000, client=client)

    def test_execute_paper_plan_requires_dry_run_disabled(self):
        client = FakeMomentumAlpaca()
        with patch.dict("os.environ", {"PORTFOLIO_DRY_RUN": "true"}):
            with self.assertRaises(RuntimeError):
                execute_paper_plan([], run_date=date(2026, 5, 21), max_order_notional=1000, client=client)

    def test_execution_error_rows_preserve_audit_file_shape(self):
        rows = execution_error_rows(
            [{"signal_date": "2026-05-20", "symbol": "MSFT", "action": "BUY", "delta_notional": "250"}],
            date(2026, 5, 21),
            OSError("socket blocked"),
        )

        self.assertEqual(rows[0]["status"], "EXECUTION_ERROR")
        self.assertEqual(rows[0]["requested_notional"], "250.00")
        self.assertIn("socket blocked", rows[0]["reason"])


if __name__ == "__main__":
    unittest.main()
