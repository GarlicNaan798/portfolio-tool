from __future__ import annotations

import argparse
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from portfolio_model.alpaca import AlpacaApiError, AlpacaClient, AlpacaConfigError
from portfolio_model.cli import load_universe, print_decisions
from portfolio_model.env import load_dotenv
from portfolio_model.model import PortfolioDecision, PortfolioModel
from portfolio_model.scout import OpportunityScout, ScoutConfig


TRADE_ACTIONS = {"BUY", "ADD", "SELL", "TRIM"}


def main() -> None:
    load_dotenv(Path(".env"))

    parser = argparse.ArgumentParser(description="Run the model and optionally submit Alpaca paper orders.")
    parser.add_argument("--universe", required=True, help="CSV file containing equity research inputs.")
    parser.add_argument("--auto-research", action="store_true", help="Discover and research symbols online before scoring.")
    parser.add_argument("--watchlist", default="data/watchlist.csv", help="CSV of symbols and industries for online research.")
    parser.add_argument(
        "--research-agents",
        type=int,
        default=int(os.getenv("PORTFOLIO_RESEARCH_AGENTS", "4")),
        help="Parallel research workers for fundamentals/news collection.",
    )
    parser.add_argument(
        "--discover-limit",
        type=int,
        default=int(os.getenv("PORTFOLIO_DISCOVER_LIMIT", "50")),
        help="Maximum symbols to research in one cycle.",
    )
    parser.add_argument("--execute", action="store_true", help="Submit orders to Alpaca. Without this, only prints decisions.")
    parser.add_argument("--loop", action="store_true", help="Keep running locally until stopped with Ctrl+C.")
    parser.add_argument(
        "--interval-minutes",
        type=float,
        default=float(os.getenv("PORTFOLIO_INTERVAL_MINUTES", "60")),
        help="Minutes to wait between runs when --loop is enabled.",
    )
    parser.add_argument(
        "--max-trade-notional",
        type=float,
        default=float(os.getenv("PORTFOLIO_MAX_TRADE_NOTIONAL", "250")),
        help="Maximum dollar notional per generated order.",
    )
    args = parser.parse_args()

    if args.loop:
        run_loop(args)
        return

    run_once(args)


def run_loop(args: argparse.Namespace) -> None:
    interval_seconds = max(args.interval_minutes * 60, 60)
    print(
        f"Starting local continuous runner. Interval: {interval_seconds / 60:.1f} minutes. "
        "Press Ctrl+C to stop.",
        flush=True,
    )
    try:
        while True:
            started_at = datetime.now(UTC)
            print(f"\n[{started_at.isoformat()}] Running portfolio model.", flush=True)
            run_once(args)
            print(f"Sleeping until next run. Press Ctrl+C to stop.", flush=True)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nStopped local continuous runner.", flush=True)


def run_once(args: argparse.Namespace) -> None:
    if args.auto_research:
        fallback_universe = load_universe(Path(args.universe))
        scout = OpportunityScout(
            ScoutConfig(
                agents=args.research_agents,
                discover_limit=args.discover_limit,
                watchlist_path=Path(args.watchlist),
            ),
            fallback_universe=fallback_universe,
        )
        result = scout.run()
        decisions = result.decisions
        print(
            f"Research scout: researched={result.researched}, skipped={result.skipped}, "
            f"errors={len(result.errors)}"
        )
        for error in result.errors[:5]:
            print(f"  research warning: {error}")
    else:
        universe = load_universe(Path(args.universe))
        decisions = PortfolioModel().decide(universe)

    print_decisions(decisions)

    dry_run = os.getenv("PORTFOLIO_DRY_RUN", "true").lower() != "false"
    if not args.execute or dry_run:
        print("\nExecution skipped: dry-run is active. Use --execute and PORTFOLIO_DRY_RUN=false to place orders.")
        return

    execute_orders(decisions, args.max_trade_notional)


def execute_orders(decisions: list[PortfolioDecision], max_trade_notional: float) -> None:
    try:
        client = AlpacaClient()
    except AlpacaConfigError as exc:
        print(f"\nExecution skipped: {exc}")
        return

    account = client.account()
    print(f"\nConnected to Alpaca account {account.get('account_number', '<unknown>')}.")
    try:
        positions = {
            str(position.get("symbol", "")).upper(): position
            for position in client.positions()
        }
    except (AlpacaApiError, OSError) as exc:
        print(f"Execution skipped: could not sync paper positions: {exc}")
        return

    for decision in decisions:
        if decision.action not in TRADE_ACTIONS:
            continue
        side = "buy" if decision.action in {"BUY", "ADD"} else "sell"
        notional = min(abs(decision.target_weight - decision.current_weight) * 10_000, max_trade_notional)
        if notional <= 1:
            continue
        qty = None
        if side == "sell":
            position = positions.get(decision.symbol.upper())
            if not position:
                print(f"Skipped sell {decision.symbol}: no paper position is currently held.")
                continue
            held_notional = _float(position.get("market_value"))
            current_price = _float(position.get("current_price")) or _float(position.get("avg_entry_price"))
            held_qty = abs(_float(position.get("qty")))
            notional = min(notional, held_notional)
            if current_price > 0 and held_qty > 0:
                qty = min(held_qty, notional / current_price)
            if notional <= 1 and (qty is None or qty <= 0):
                print(f"Skipped sell {decision.symbol}: computed sell size is below $1.")
                continue
        order_id = f"portfolio-model-{decision.symbol.lower()}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        try:
            response = client.submit_market_order(
                symbol=decision.symbol,
                side=side,
                notional=notional,
                qty=qty,
                client_order_id=order_id,
            )
        except (AlpacaApiError, OSError) as exc:
            print(f"Skipped {side} {decision.symbol}: Alpaca rejected order: {exc}")
            continue
        print(f"Submitted {side} {decision.symbol} for ${notional:.2f}: {response.get('id', '<no id>')}")


def _float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    main()
