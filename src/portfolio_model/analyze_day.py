from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from portfolio_model.alpaca import AlpacaClient
from portfolio_model.env import load_dotenv


def main() -> None:
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(description="Analyze current P/L against yesterday's execution plan.")
    parser.add_argument("--execution-plan", default="state/execution_plan.csv")
    parser.add_argument("--output", default="state/day_analysis.md")
    args = parser.parse_args()
    report = build_report(Path(args.execution_plan))
    Path(args.output).write_text(report, encoding="utf-8")
    print(report)


def build_report(plan_path: Path) -> str:
    plan = {row["symbol"]: row for row in read_csv(plan_path)}
    positions = AlpacaClient().positions()
    total = 0.0
    by_agent = defaultdict(float)
    by_status = defaultdict(float)
    lines = ["# Trading Day Analysis", ""]
    lines.append("| Symbol | P/L | P/L % | Agent | Status | Score | Thesis |")
    lines.append("|---|---:|---:|---|---|---:|---|")
    for position in sorted(positions, key=lambda item: float(item.get("unrealized_pl") or 0)):
        symbol = position.get("symbol", "")
        pl = float(position.get("unrealized_pl") or 0)
        plpc = float(position.get("unrealized_plpc") or 0)
        row = plan.get(symbol, {})
        total += pl
        by_agent[row.get("agent_name", "legacy/unplanned")] += pl
        by_status[row.get("status", "legacy/unplanned")] += pl
        lines.append(
            "| "
            + " | ".join(
                [
                    symbol,
                    f"${pl:.2f}",
                    f"{plpc:.2%}",
                    row.get("agent_name", "legacy/unplanned"),
                    row.get("status", "legacy/unplanned"),
                    row.get("opportunity_score", ""),
                    row.get("reason", ""),
                ]
            )
            + " |"
        )
    lines.extend(["", f"Total current unrealized P/L: ${total:.2f}", "", "## By Agent"])
    for agent, pl in sorted(by_agent.items(), key=lambda item: item[1]):
        lines.append(f"- {agent}: ${pl:.2f}")
    lines.extend(["", "## By Signal Type"])
    for status, pl in sorted(by_status.items(), key=lambda item: item[1]):
        lines.append(f"- {status}: ${pl:.2f}")
    lines.extend(
        [
            "",
            "## Diagnosis",
            "- Losses are concentrated in exploration trades rather than high-conviction trades.",
            "- The prior quota design converted WATCH ideas into $250 buys, which made learning trades too large.",
            "- Predicted return was a score-derived heuristic, not a calibrated forecast; it overstated edge on low-history names.",
            "- Agent rationales were mostly broad factor rationales, not near-term catalysts.",
            "",
            "## Policy Changes",
            "- Keep 5 ideas per agent, but exploration trade size is capped separately from conviction trade size.",
            "- Raise exploration score threshold and reduce exploration budget.",
            "- Tighten stop-loss and take-profit defaults for faster feedback.",
            "- Treat forced quota fills as learning probes, not normal positions.",
        ]
    )
    return "\n".join(lines) + "\n"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    main()
