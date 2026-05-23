import csv
import tempfile
import unittest
from pathlib import Path

from portfolio_model.model import PortfolioDecision, ScoreBreakdown
from portfolio_model.research_memory import memory_status, record_research_cycle


def decision(symbol: str, action: str, composite: float, current_weight: float = 0.0) -> PortfolioDecision:
    return PortfolioDecision(
        symbol=symbol,
        action=action,
        score=ScoreBreakdown(symbol, 0.5, 0.5, 0.5, 0.5, composite, 0.1),
        current_weight=current_weight,
        target_weight=0.1,
        rationale="test",
    )


class ResearchMemoryTest(unittest.TestCase):
    def test_unowned_low_score_is_disposed(self):
        self.assertEqual(memory_status(decision("LOW", "HOLD", 0.3), 0.46), "DISPOSED")

    def test_owned_low_score_stays_active_unless_sell(self):
        self.assertEqual(memory_status(decision("OWN", "TRIM", 0.3, 0.05), 0.46), "ACTIVE")
        self.assertEqual(memory_status(decision("SELL", "SELL", 0.3, 0.05), 0.46), "DISPOSED")

    def test_record_research_cycle_writes_ledger_and_active_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = Path(temp_dir) / "ledger.csv"
            memory = Path(temp_dir) / "memory.csv"
            active, disposed = record_research_cycle(
                ledger_path=ledger,
                memory_path=memory,
                decisions=[decision("GOOD", "BUY", 0.7), decision("BAD", "HOLD", 0.2)],
                min_memory_score=0.46,
            )

            with ledger.open(newline="", encoding="utf-8") as handle:
                ledger_rows = list(csv.DictReader(handle))
            with memory.open(newline="", encoding="utf-8") as handle:
                memory_rows = list(csv.DictReader(handle))

        self.assertEqual(active, 1)
        self.assertEqual(disposed, 1)
        self.assertEqual(len(ledger_rows), 2)
        self.assertEqual(memory_rows[0]["symbol"], "GOOD")


if __name__ == "__main__":
    unittest.main()
