from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from portfolio_model.env import load_dotenv


def main() -> None:
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(description="Show portfolio model progress from local state files.")
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    show_status(Path(args.state_dir), args.top)


def show_status(state_dir: Path, top: int) -> None:
    scores_path = state_dir / "opportunity_scores.csv"
    ledger_path = state_dir / "research_ledger.csv"
    memory_path = state_dir / "research_memory.csv"

    scores = read_rows(scores_path)
    ledger = read_rows(ledger_path)
    memory = read_rows(memory_path)

    print(f"State directory: {state_dir.resolve()}")
    print(f"Opportunity score rows: {len(scores)}")
    print(f"Research ledger rows: {len(ledger)}")
    print(f"Active memory rows: {len(memory)}")

    if scores:
        latest_timestamp = scores[-1]["timestamp"]
        latest_cycle = [row for row in scores if row["timestamp"] == latest_timestamp]
        average = latest_cycle[-1].get("average_top_score", "0")
        print(f"\nLatest score cycle: {latest_timestamp}")
        print(f"Average top score: {float(average):.2f}/10")
        print("Top opportunities:")
        for row in latest_cycle[:top]:
            print(
                f"  {row['symbol']:<6} score={float(row['opportunity_score']):>5.2f} "
                f"action={row['action']:<5} target={float(row['target_weight']):>5.1%}"
            )

    if ledger:
        latest_ledger_timestamp = ledger[-1]["timestamp"]
        latest_ledger = [row for row in ledger if row["timestamp"] == latest_ledger_timestamp]
        counts = Counter(row["memory_status"] for row in latest_ledger)
        print(f"\nLatest research cycle: {latest_ledger_timestamp}")
        print(f"Memory statuses: ACTIVE={counts.get('ACTIVE', 0)}, DISPOSED={counts.get('DISPOSED', 0)}")
        disposed = [row["symbol"] for row in latest_ledger if row["memory_status"] == "DISPOSED"]
        if disposed:
            print(f"Disposed this cycle: {', '.join(disposed[:top])}")


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    main()
