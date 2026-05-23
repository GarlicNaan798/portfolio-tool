from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from portfolio_model.model import PortfolioDecision, ScoreBreakdown


def save_decision_book(path: Path, decisions: list[PortfolioDecision], metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "metadata": metadata,
        "decisions": [asdict(decision) for decision in decisions],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_decision_book(path: Path) -> list[PortfolioDecision]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    decisions = []
    for row in payload.get("decisions", []):
        score = ScoreBreakdown(**row["score"])
        decisions.append(
            PortfolioDecision(
                symbol=row["symbol"],
                action=row["action"],
                score=score,
                current_weight=row["current_weight"],
                target_weight=row["target_weight"],
                rationale=row["rationale"],
            )
        )
    return decisions
