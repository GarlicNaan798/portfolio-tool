import tempfile
import unittest
from pathlib import Path

from portfolio_model.decision_book import load_decision_book, save_decision_book
from portfolio_model.model import PortfolioDecision, ScoreBreakdown


class DecisionBookTest(unittest.TestCase):
    def test_round_trip_decision_book(self):
        decision = PortfolioDecision(
            symbol="TEST",
            action="BUY",
            score=ScoreBreakdown("TEST", 0.7, 0.6, 0.5, 0.4, 0.61, 0.1),
            current_weight=0.0,
            target_weight=0.1,
            rationale="test rationale",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "decision_book.json"
            save_decision_book(path, [decision], {"researched": 1})
            loaded = load_decision_book(path)

        self.assertEqual(loaded[0].symbol, "TEST")
        self.assertEqual(loaded[0].score.composite, 0.61)


if __name__ == "__main__":
    unittest.main()
