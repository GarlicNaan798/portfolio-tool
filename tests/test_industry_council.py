import csv
import tempfile
import unittest
from pathlib import Path

from portfolio_model.industry_council import (
    IndustryAgentResult,
    IndustryAgentSpec,
    build_agent_quota_execution_plan,
    load_industry_agents,
    record_opportunity_scores,
)
from portfolio_model.model import PortfolioDecision, ScoreBreakdown
from portfolio_model.opportunity import opportunity_components, opportunity_score


def decision(symbol: str, value: float, growth: float, quality: float, sentiment: float, action: str = "BUY") -> PortfolioDecision:
    return PortfolioDecision(
        symbol=symbol,
        action=action,
        score=ScoreBreakdown(symbol, value, growth, quality, sentiment, 0.7, 0.1),
        current_weight=0.0,
        target_weight=0.1,
        rationale="test",
    )


class IndustryCouncilTest(unittest.TestCase):
    def test_opportunity_score_uses_zero_to_ten_scale(self):
        high = decision("HIGH", 0.9, 0.8, 0.8, 0.9)
        low = decision("LOW", 0.2, 0.2, 0.2, 0.2)

        self.assertGreater(opportunity_score(high), opportunity_score(low))
        self.assertLessEqual(opportunity_score(high), 10.0)

    def test_opportunity_score_prioritizes_financials_over_sentiment(self):
        strong_financials = decision("FIN", 0.85, 0.85, 0.85, 0.10)
        hot_sentiment = decision("BUZZ", 0.40, 0.40, 0.40, 1.00)

        components = opportunity_components(strong_financials)

        self.assertAlmostEqual(components["financial"], 0.7550, places=4)
        self.assertGreater(opportunity_score(strong_financials), opportunity_score(hot_sentiment))

    def test_load_industry_agents_groups_symbols(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agents.csv"
            path.write_text(
                "agent,industry,symbol\nsoftware,Software,MSFT\nsoftware,Software,CRM\nenergy,Energy,XOM\n",
                encoding="utf-8",
            )

            specs = load_industry_agents(path)

        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0].symbols, ("MSFT", "CRM"))

    def test_record_opportunity_scores_writes_top_average(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scores.csv"
            avg = record_opportunity_scores(
                path,
                [decision("A", 0.9, 0.8, 0.7, 0.8), decision("B", 0.5, 0.5, 0.5, 0.5)],
                candidate_count=1,
            )
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertGreater(avg, 7.0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "A")

    def test_agent_execution_plan_scales_conviction_but_caps_exploration(self):
        result = IndustryAgentResult(
            spec=IndustryAgentSpec("software", "Ada Software", "Software", ("HIGH", "WATCH")),
            decisions=[
                decision("HIGH", 0.9, 0.9, 0.9, 0.9, "BUY"),
                decision("WATCH", 0.7, 0.7, 0.7, 0.7, "WATCH"),
            ],
            researched=2,
            skipped=0,
            errors=[],
            warnings=[],
        )

        rows = build_agent_quota_execution_plan(
            [result],
            {"cash": "90000", "buying_power": "360000", "equity": "100000"},
            {
                "buying_power_fraction": 0.25,
                "exploration_budget_fraction": 0.03,
                "max_trade_notional": 250,
                "max_trade_fraction_of_buying_power": 0.01,
                "max_position_fraction_of_equity": 0.03,
                "min_conviction_notional": 1000,
                "min_opportunity_score": 6.5,
                "max_approved_trades": 5,
                "min_trades_per_agent": 2,
                "exploration_min_score": 5.75,
                "exploration_max_notional": 25,
                "forced_exploration_max_notional": 10,
            },
        )

        by_symbol = {row.symbol: row for row in rows}
        self.assertEqual(by_symbol["HIGH"].status, "APPROVED")
        self.assertEqual(by_symbol["HIGH"].notional, 3000)
        self.assertEqual(by_symbol["WATCH"].status, "EXPLORATION_APPROVED")
        self.assertEqual(by_symbol["WATCH"].notional, 25)
        self.assertIn("cash $90,000.00", by_symbol["HIGH"].allocation_note)


if __name__ == "__main__":
    unittest.main()
