import unittest
from datetime import date, timedelta
from pathlib import Path
import tempfile

from portfolio_model.backtest import (
    AgentParams,
    ForwardEstimate,
    PriceBar,
    StrategyFeatures,
    buy_and_hold_return,
    latest_forward_estimate,
    load_forward_estimates,
    rank_symbols,
    regime_exposure_multiplier,
    sample_size_warning,
    simulate,
    strategy_score,
    train_agents,
    training_objective,
)


def series(start: date, length: int, first: float, daily_return: float):
    price = first
    rows = []
    for index in range(length):
        rows.append(PriceBar(start + timedelta(days=index), price))
        price *= 1.0 + daily_return
    return rows


class BacktestTest(unittest.TestCase):
    def test_buy_and_hold_return(self):
        bars = series(date(2020, 1, 1), 3, 100, 0.10)

        self.assertAlmostEqual(buy_and_hold_return(bars, [bar.day for bar in bars]), 0.21)

    def test_simulate_selects_positive_momentum_symbols(self):
        days = [date(2020, 1, 1) + timedelta(days=index) for index in range(320)]
        bars = {
            "AAA": series(days[0], 320, 100, 0.002),
            "BBB": series(days[0], 320, 100, -0.001),
            "SPY": series(days[0], 320, 100, 0.0005),
        }

        metrics, rows = simulate(bars, days, AgentParams(4.0, 1, 0.20, 0.50))

        self.assertGreater(metrics["total_return"], 0)
        self.assertTrue(any(row["symbol"] == "AAA" for row in rows))
        self.assertIn("trade_count", metrics)
        self.assertIn("average_r", metrics)

    def test_train_agents_returns_parameter_set(self):
        days = [date(2020, 1, 1) + timedelta(days=index) for index in range(320)]
        bars = {
            "AAA": series(days[0], 320, 100, 0.002),
            "BBB": series(days[0], 320, 100, -0.001),
            "SPY": series(days[0], 320, 100, 0.0005),
        }

        params = train_agents(bars, days, fast=True)

        self.assertIsInstance(params, AgentParams)

    def test_rebalance_cadence_changes_trade_opportunities(self):
        days = [date(2020, 1, 1) + timedelta(days=index) for index in range(360)]
        bars = {
            "AAA": series(days[0], 360, 100, 0.002),
            "BBB": series(days[0], 360, 100, 0.0015),
            "SPY": series(days[0], 360, 100, 0.0005),
        }

        weekly, _ = simulate(bars, days, AgentParams(4.0, 2, 0.20, 0.50), rebalance_every=5)
        monthly, _ = simulate(bars, days, AgentParams(4.0, 2, 0.20, 0.50), rebalance_every=21)

        self.assertGreater(weekly["rebalance_count"], monthly["rebalance_count"])

    def test_transaction_costs_reduce_returns(self):
        days = [date(2020, 1, 1) + timedelta(days=index) for index in range(360)]
        bars = {
            "AAA": series(days[0], 360, 100, 0.002),
            "BBB": series(days[0], 360, 100, 0.0015),
            "SPY": series(days[0], 360, 100, 0.0005),
        }

        params = AgentParams(4.0, 2, 0.20, 0.10)
        no_cost, no_cost_rows = simulate(bars, days, params, rebalance_every=5)
        with_cost, _ = simulate(bars, days, params, rebalance_every=5, cost_bps=10)

        self.assertLess(with_cost["total_return"], no_cost["total_return"])
        self.assertTrue(any(row["action"] == "EXIT" for row in no_cost_rows))

    def test_regime_exposure_multiplier_reduces_weak_market_exposure(self):
        days = [date(2020, 1, 1) + timedelta(days=index) for index in range(260)]
        spy = series(days[0], 260, 100, -0.001)
        spy_prices = {bar.day: bar.close for bar in spy}

        self.assertLess(regime_exposure_multiplier(spy_prices, spy, days[-1]), 1.0)

    def test_training_objective_prefers_risk_disciplined_params(self):
        loose = AgentParams(6.0, 5, 0.12, 0.50, False, 0.25, 1.0, 1.0, False)
        disciplined = AgentParams(6.5, 8, 0.08, 0.35, True, 0.12, 0.40, 0.75, True)
        fit = {"total_return": 0.40, "max_drawdown": -0.10, "sharpe": 1.0, "rebalance_count": 20}

        loose_score = training_objective(
            loose,
            fit,
            {"total_return": 0.30, "max_drawdown": -0.28, "sharpe": 0.7, "rebalance_count": 55},
        )
        disciplined_score = training_objective(
            disciplined,
            fit,
            {"total_return": 0.24, "max_drawdown": -0.10, "sharpe": 0.9, "rebalance_count": 55},
        )

        self.assertGreater(disciplined_score, loose_score)

    def test_sample_size_warning_labels_small_backtests(self):
        self.assertEqual(sample_size_warning(25), "LOW_SAMPLE")
        self.assertEqual(sample_size_warning(150), "MODERATE_SAMPLE")
        self.assertEqual(sample_size_warning(400), "OK")

    def test_strategy_books_produce_distinct_rankings(self):
        features_days = [date(2020, 1, 1) + timedelta(days=index) for index in range(320)]
        bars = {
            "STEADY": series(features_days[0], 320, 100, 0.0007),
            "FAST": series(features_days[0], 320, 100, 0.0020),
            "WEAK": series(features_days[0], 320, 100, -0.0010),
        }
        prices = {symbol: {bar.day: bar.close for bar in rows} for symbol, rows in bars.items()}

        quality = rank_symbols(list(bars), bars, prices, features_days[-1], strategy_book="quality_compounder")
        momentum = rank_symbols(list(bars), bars, prices, features_days[-1], strategy_book="momentum_breakout")

        self.assertGreaterEqual(quality[0][1], quality[-1][1])
        self.assertEqual(momentum[0][0], "FAST")

    def test_strategy_features_can_score_all_books(self):
        features = StrategyFeatures(0.20, 0.12, 0.05, -0.08, 0.18, 1.5)

        scores = [
            strategy_score(ranker, features)
            for ranker in (
                "metric_priority",
                "quality_compounder",
                "value_reversion",
                "momentum_breakout",
            )
        ]

        self.assertEqual(len(scores), 4)
        self.assertTrue(all(0.0 <= score <= 10.0 for score in scores))

    def test_forward_pe_book_requires_forward_estimate_features(self):
        features = StrategyFeatures(0.20, 0.12, 0.05, -0.08, 0.18, 1.5)

        with self.assertRaises(ValueError):
            strategy_score("forward_pe_value", features)

    def test_load_forward_estimates_uses_latest_point_in_time_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "forward_estimates.csv"
            path.write_text(
                "date,symbol,sector,forward_pe,forward_eps_yoy,forward_eps_revision_3m,fcf_yield,debt_to_equity\n"
                "2020-01-01,AAA,Software,18,0.10,0.01,0.04,0.2\n"
                "2020-02-01,AAA,Software,14,0.20,0.04,0.05,0.2\n",
                encoding="utf-8",
            )
            estimates = load_forward_estimates(path)

        early = latest_forward_estimate(estimates, "AAA", date(2020, 1, 15))
        later = latest_forward_estimate(estimates, "AAA", date(2020, 2, 15))

        self.assertEqual(early.forward_pe, 18)
        self.assertEqual(later.forward_pe, 14)

    def test_forward_pe_book_ranks_supported_cheapness_over_value_trap(self):
        days = [date(2020, 1, 1) + timedelta(days=index) for index in range(320)]
        bars = {
            "CHEAP": series(days[0], 320, 100, 0.0010),
            "TRAP": series(days[0], 320, 100, -0.0010),
            "RICH": series(days[0], 320, 100, 0.0010),
        }
        prices = {symbol: {bar.day: bar.close for bar in rows} for symbol, rows in bars.items()}
        estimates = {
            "CHEAP": [ForwardEstimate(days[260], "CHEAP", "Software", 14, 0.18, 0.04, 0.05, 0.20)],
            "TRAP": [ForwardEstimate(days[260], "TRAP", "Software", 12, -0.25, -0.08, -0.02, 0.85)],
            "RICH": [ForwardEstimate(days[260], "RICH", "Software", 35, 0.12, 0.01, 0.04, 0.20)],
        }

        ranked = rank_symbols(
            list(bars),
            bars,
            prices,
            days[-1],
            strategy_book="forward_pe_value",
            forward_estimates=estimates,
        )

        self.assertEqual(ranked[0][0], "CHEAP")


if __name__ == "__main__":
    unittest.main()
