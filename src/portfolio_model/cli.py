from __future__ import annotations

import argparse
import csv
from pathlib import Path

from portfolio_model.model import EquityInput, PortfolioModel


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the medium-horizon portfolio model.")
    parser.add_argument("--universe", required=True, help="CSV file containing equity fundamentals and sentiment inputs.")
    args = parser.parse_args()

    universe = load_universe(Path(args.universe))
    decisions = PortfolioModel().decide(universe)
    print_decisions(decisions)


def load_universe(path: Path) -> list[EquityInput]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return [parse_equity(row) for row in rows]


def parse_equity(row: dict[str, str]) -> EquityInput:
    return EquityInput(
        symbol=row["symbol"].strip().upper(),
        industry=row["industry"].strip(),
        price=float(row["price"]),
        pe=float(row["pe"]),
        pb=float(row["pb"]),
        fcf_yield=float(row["fcf_yield"]),
        revenue_yoy=float(row["revenue_yoy"]),
        eps_yoy=float(row["eps_yoy"]),
        gross_margin=float(row["gross_margin"]),
        debt_to_equity=float(row["debt_to_equity"]),
        sentiment=float(row["sentiment"]),
        sentiment_confidence=float(row["sentiment_confidence"]),
        current_weight=float(row.get("current_weight") or 0.0),
        holding_days=int(float(row.get("holding_days") or 0)),
        market_cap=float(row.get("market_cap") or 0.0),
        free_cash_flow=float(row.get("free_cash_flow") or 0.0),
        dcf_score=float(row.get("dcf_score") or 0.5),
        dcf_margin_safety=float(row.get("dcf_margin_safety") or 0.0),
        dcf_confidence=float(row.get("dcf_confidence") or 0.0),
        dcf_intrinsic_value=float(row.get("dcf_intrinsic_value") or 0.0),
        dcf_reason=row.get("dcf_reason") or "",
        forward_pe=float(row.get("forward_pe") or 0.0),
        forward_eps_yoy=float(row.get("forward_eps_yoy") or 0.0),
        forward_eps_revision_3m=float(row.get("forward_eps_revision_3m") or 0.0),
    )


def print_decisions(decisions) -> None:
    header = f"{'Symbol':<8} {'Action':<6} {'Score':>7} {'Current':>9} {'Target':>8}  Rationale"
    print(header)
    print("-" * len(header))
    for decision in decisions:
        print(
            f"{decision.symbol:<8} {decision.action:<6} "
            f"{decision.score.composite:>7.2f} "
            f"{decision.current_weight:>8.1%} "
            f"{decision.target_weight:>7.1%}  "
            f"{decision.rationale}"
        )


if __name__ == "__main__":
    main()
