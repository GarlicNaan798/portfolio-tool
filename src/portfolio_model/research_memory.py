from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from portfolio_model.model import PortfolioDecision


LEDGER_FIELDS = [
    "timestamp",
    "symbol",
    "action",
    "composite",
    "value",
    "growth",
    "quality",
    "sentiment",
    "dcf",
    "dcf_margin_safety",
    "dcf_confidence",
    "dcf_intrinsic_value",
    "dcf_reason",
    "current_weight",
    "target_weight",
    "memory_status",
    "rationale",
]

MEMORY_FIELDS = [
    "timestamp",
    "symbol",
    "action",
    "composite",
    "target_weight",
    "rationale",
]


def record_research_cycle(
    *,
    ledger_path: Path,
    memory_path: Path,
    decisions: list[PortfolioDecision],
    min_memory_score: float,
) -> tuple[int, int]:
    timestamp = datetime.now(UTC).isoformat()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    ledger_exists = ledger_path.exists()
    active_rows = []
    with ledger_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        if not ledger_exists:
            writer.writeheader()
        for decision in decisions:
            status = memory_status(decision, min_memory_score)
            row = {
                "timestamp": timestamp,
                "symbol": decision.symbol,
                "action": decision.action,
                "composite": f"{decision.score.composite:.4f}",
                "value": f"{decision.score.value:.4f}",
                "growth": f"{decision.score.growth:.4f}",
                "quality": f"{decision.score.quality:.4f}",
                "sentiment": f"{decision.score.sentiment:.4f}",
                "dcf": f"{decision.score.dcf:.4f}",
                "dcf_margin_safety": f"{decision.score.dcf_margin_safety:.4f}",
                "dcf_confidence": f"{decision.score.dcf_confidence:.4f}",
                "dcf_intrinsic_value": f"{decision.score.dcf_intrinsic_value:.4f}",
                "dcf_reason": decision.score.dcf_reason,
                "current_weight": f"{decision.current_weight:.4f}",
                "target_weight": f"{decision.target_weight:.4f}",
                "memory_status": status,
                "rationale": decision.rationale,
            }
            writer.writerow(row)
            if status == "ACTIVE":
                active_rows.append(
                    {
                        "timestamp": timestamp,
                        "symbol": decision.symbol,
                        "action": decision.action,
                        "composite": f"{decision.score.composite:.4f}",
                        "target_weight": f"{decision.target_weight:.4f}",
                        "rationale": decision.rationale,
                    }
                )

    with memory_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MEMORY_FIELDS)
        writer.writeheader()
        writer.writerows(active_rows)

    disposed = len(decisions) - len(active_rows)
    return len(active_rows), disposed


def memory_status(decision: PortfolioDecision, min_memory_score: float) -> str:
    if decision.score.composite < min_memory_score and decision.current_weight <= 0:
        return "DISPOSED"
    if decision.action == "SELL":
        return "DISPOSED"
    return "ACTIVE"
