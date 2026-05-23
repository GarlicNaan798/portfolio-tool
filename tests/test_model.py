import unittest

from portfolio_model.model import EquityInput, ModelConfig, PortfolioModel


def sample_universe():
    return [
        EquityInput("AAA", "Software", 100, 18, 4, 0.08, 0.20, 0.25, 0.75, 0.10, 0.6, 0.9),
        EquityInput("BBB", "Software", 80, 40, 12, 0.02, 0.05, 0.02, 0.55, 0.80, -0.3, 0.8),
        EquityInput("CCC", "Energy", 50, 9, 1.4, 0.12, 0.08, 0.10, 0.42, 0.20, 0.2, 0.7),
        EquityInput("DDD", "Energy", 70, 25, 3.0, 0.03, -0.02, -0.05, 0.30, 1.10, -0.5, 0.9),
    ]


class PortfolioModelTest(unittest.TestCase):
    def test_scores_rank_stronger_fundamentals_higher(self):
        scores = {score.symbol: score for score in PortfolioModel().score_universe(sample_universe())}

        self.assertGreater(scores["AAA"].composite, scores["BBB"].composite)
        self.assertGreater(scores["CCC"].composite, scores["DDD"].composite)

    def test_dcf_score_affects_composite(self):
        universe = [
            EquityInput("CHEAP", "Software", 100, 20, 4, 0.05, 0.1, 0.1, 0.5, 0.2, 0.0, 0.0, dcf_score=0.9, dcf_margin_safety=0.4, dcf_confidence=1.0),
            EquityInput("RICH", "Software", 100, 20, 4, 0.05, 0.1, 0.1, 0.5, 0.2, 0.0, 0.0, dcf_score=0.2, dcf_margin_safety=-0.3, dcf_confidence=1.0),
        ]

        scores = {score.symbol: score for score in PortfolioModel().score_universe(universe)}

        self.assertGreater(scores["CHEAP"].composite, scores["RICH"].composite)
        self.assertGreater(scores["CHEAP"].dcf_margin_safety, 0)

    def test_forward_pe_rewards_cheap_names_with_revision_support(self):
        universe = [
            EquityInput("CHEAP", "Software", 100, 25, 5, 0.04, 0.1, 0.1, 0.5, 0.2, 0.0, 0.0, forward_pe=14, forward_eps_yoy=0.18, forward_eps_revision_3m=0.04),
            EquityInput("TRAP", "Software", 100, 25, 5, 0.04, 0.1, 0.1, 0.5, 0.2, 0.0, 0.0, forward_pe=12, forward_eps_yoy=-0.15, forward_eps_revision_3m=-0.06),
            EquityInput("RICH", "Software", 100, 25, 5, 0.04, 0.1, 0.1, 0.5, 0.2, 0.0, 0.0, forward_pe=35, forward_eps_yoy=0.12, forward_eps_revision_3m=0.01),
        ]

        scores = {score.symbol: score for score in PortfolioModel().score_universe(universe)}

        self.assertGreater(scores["CHEAP"].value, scores["TRAP"].value)
        self.assertGreater(scores["CHEAP"].value, scores["RICH"].value)

    def test_new_high_score_position_is_buy(self):
        decisions = {decision.symbol: decision for decision in PortfolioModel().decide(sample_universe())}

        self.assertEqual(decisions["AAA"].action, "BUY")

    def test_unowned_neutral_position_is_watch_not_hold(self):
        decisions = {decision.symbol: decision for decision in PortfolioModel().decide(sample_universe())}

        self.assertIn(decisions["BBB"].action, {"WATCH", "PASS"})
        self.assertNotEqual(decisions["BBB"].action, "HOLD")

    def test_minimum_holding_period_reduces_churn(self):
        universe = [
            EquityInput("AAA", "Software", 100, 18, 4, 0.08, 0.20, 0.25, 0.75, 0.10, 0.6, 0.9, 0.08, 10),
            EquityInput("BBB", "Software", 80, 24, 6, 0.04, 0.08, 0.09, 0.65, 0.25, 0.1, 0.7),
        ]
        config = ModelConfig(sell_threshold=0.20, min_holding_days=45)

        decisions = {decision.symbol: decision for decision in PortfolioModel(config).decide(universe)}

        self.assertEqual(decisions["AAA"].action, "HOLD")


if __name__ == "__main__":
    unittest.main()
