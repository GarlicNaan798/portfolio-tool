from __future__ import annotations

import argparse
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from portfolio_model.alpaca import AlpacaClient, AlpacaConfigError
from portfolio_model.cli import load_universe, print_decisions
from portfolio_model.decision_book import save_decision_book
from portfolio_model.env import load_dotenv
from portfolio_model.research_memory import record_research_cycle
from portfolio_model.runner import execute_orders
from portfolio_model.scout import OpportunityScout, ScoutConfig


def main() -> None:
    load_dotenv(Path(".env"))

    parser = argparse.ArgumentParser(
        description="Research continuously before market open, then execute the latest decision book at open."
    )
    parser.add_argument("--universe", default="data/sample_universe.csv", help="Fallback CSV for prices/current holdings.")
    parser.add_argument("--watchlist", default="", help="Optional CSV of symbols and industries. Empty means discover assets.")
    parser.add_argument("--decision-book", default="state/decision_book.json", help="Where to save the latest decisions.")
    parser.add_argument("--research-ledger", default="state/research_ledger.csv", help="Append-only CSV of all researched decisions.")
    parser.add_argument("--research-memory", default="state/research_memory.csv", help="CSV of currently desirable researched equities.")
    parser.add_argument("--execute", action="store_true", help="Allow execution when the market opens.")
    parser.add_argument(
        "--research-agents",
        type=int,
        default=int(os.getenv("PORTFOLIO_RESEARCH_AGENTS", "4")),
        help="Parallel research workers.",
    )
    parser.add_argument(
        "--discover-limit",
        type=int,
        default=int(os.getenv("PORTFOLIO_DISCOVER_LIMIT", "250")),
        help="Maximum symbols to research each cycle.",
    )
    parser.add_argument(
        "--research-interval-minutes",
        type=float,
        default=float(os.getenv("PORTFOLIO_PREOPEN_RESEARCH_INTERVAL_MINUTES", "15")),
        help="Minutes between pre-open research cycles.",
    )
    parser.add_argument(
        "--clock-interval-seconds",
        type=float,
        default=float(os.getenv("PORTFOLIO_CLOCK_INTERVAL_SECONDS", "30")),
        help="Seconds between market-clock checks.",
    )
    parser.add_argument(
        "--max-trade-notional",
        type=float,
        default=float(os.getenv("PORTFOLIO_MAX_TRADE_NOTIONAL", "250")),
        help="Maximum dollar notional per generated order.",
    )
    parser.add_argument(
        "--memory-min-score",
        type=float,
        default=float(os.getenv("PORTFOLIO_MEMORY_MIN_SCORE", "0.46")),
        help="Unowned equities below this composite score are disposed from active memory.",
    )
    args = parser.parse_args()
    run_preopen(args)


def run_preopen(args: argparse.Namespace) -> None:
    decision_book_path = Path(args.decision_book)
    fallback_universe = load_universe(Path(args.universe))
    latest_decisions = []
    last_research_at = 0.0
    executed = False

    print("Starting pre-market research coordinator. Press Ctrl+C to stop.", flush=True)
    print("Dry-run remains active unless --execute and PORTFOLIO_DRY_RUN=false are both set.", flush=True)

    try:
        while True:
            now = time.time()
            should_research = not latest_decisions or now - last_research_at >= args.research_interval_minutes * 60
            if should_research:
                latest_decisions = research_once(args, fallback_universe, decision_book_path)
                last_research_at = now

            clock = market_clock()
            if clock:
                is_open = bool(clock.get("is_open"))
                next_open = clock.get("next_open", "<unknown>")
                print(f"Market clock: is_open={is_open}, next_open={next_open}", flush=True)
                if is_open and not executed:
                    execute_at_open(args, latest_decisions)
                    executed = True
                    return
            else:
                print("Market clock unavailable; continuing research loop.", flush=True)

            time.sleep(max(5.0, args.clock_interval_seconds))
    except KeyboardInterrupt:
        print("\nStopped pre-market coordinator.", flush=True)


def research_once(
    args: argparse.Namespace,
    fallback_universe,
    decision_book_path: Path,
):
    watchlist_path = Path(args.watchlist) if args.watchlist else None
    scout = OpportunityScout(
        ScoutConfig(
            agents=args.research_agents,
            discover_limit=args.discover_limit,
            watchlist_path=watchlist_path,
        ),
        fallback_universe=fallback_universe,
    )
    result = scout.run()
    print(
        f"\n[{datetime.now(UTC).isoformat()}] Research complete: "
        f"researched={result.researched}, skipped={result.skipped}, errors={len(result.errors)}",
        flush=True,
    )
    for error in result.errors[:5]:
        print(f"  research warning: {error}", flush=True)
    for warning in result.warnings or []:
        print(f"  research warning: {warning}", flush=True)

    print_decisions(result.decisions)
    save_decision_book(
        decision_book_path,
        result.decisions,
        {
            "researched": result.researched,
            "skipped": result.skipped,
            "errors": result.errors,
            "research_agents": args.research_agents,
            "discover_limit": args.discover_limit,
        },
    )
    print(f"Saved latest decision book to {decision_book_path}.", flush=True)
    active, disposed = record_research_cycle(
        ledger_path=Path(args.research_ledger),
        memory_path=Path(args.research_memory),
        decisions=result.decisions,
        min_memory_score=args.memory_min_score,
    )
    print(
        f"Recorded research CSVs: active_memory={active}, disposed_from_memory={disposed}, "
        f"ledger={args.research_ledger}, memory={args.research_memory}.",
        flush=True,
    )
    return result.decisions


def market_clock() -> dict | None:
    try:
        return AlpacaClient().clock()
    except AlpacaConfigError as exc:
        print(f"Market clock unavailable: {exc}", flush=True)
    except Exception as exc:
        print(f"Market clock unavailable: {exc}", flush=True)
    return None


def execute_at_open(args: argparse.Namespace, decisions) -> None:
    dry_run = os.getenv("PORTFOLIO_DRY_RUN", "true").lower() != "false"
    if not args.execute or dry_run:
        print("\nMarket is open. Execution skipped: dry-run is active or --execute was not supplied.", flush=True)
        return
    print("\nMarket is open. Executing latest decision book.", flush=True)
    execute_orders(decisions, args.max_trade_notional)


if __name__ == "__main__":
    main()
