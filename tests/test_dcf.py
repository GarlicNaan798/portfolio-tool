import unittest

from portfolio_model.dcf import build_dcf


class DcfTest(unittest.TestCase):
    def test_dcf_rewards_margin_of_safety(self):
        result = build_dcf(
            price=100,
            market_cap=10_000_000_000,
            free_cash_flow=900_000_000,
            revenue_yoy=0.08,
            eps_yoy=0.10,
            debt_to_equity=0.3,
        )

        self.assertGreater(result.intrinsic_value_per_share, 100)
        self.assertGreater(result.margin_of_safety, 0)
        self.assertGreater(result.score, 0.5)
        self.assertGreater(result.confidence, 0.8)

    def test_dcf_returns_neutral_when_inputs_are_missing(self):
        result = build_dcf(
            price=100,
            market_cap=0,
            free_cash_flow=0,
            revenue_yoy=0.08,
            eps_yoy=0.10,
            debt_to_equity=0.3,
        )

        self.assertEqual(result.score, 0.5)
        self.assertEqual(result.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
