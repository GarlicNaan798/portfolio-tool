from __future__ import annotations

import argparse
import csv
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from portfolio_model.alpaca import AlpacaClient, AlpacaConfigError
from portfolio_model.env import load_dotenv


def main() -> None:
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(description="Log live agent utility and outcome diagnostics.")
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--interval-seconds", type=float, default=60)
    parser.add_argument("--workers-per-industry", type=int, default=8)
    parser.add_argument("--discover-per-industry", type=int, default=120)
    parser.add_argument("--until-market-close", action="store_true")
    args = parser.parse_args()
    run_diagnostics(args)


def run_diagnostics(args: argparse.Namespace) -> None:
    state_dir = Path(args.state_dir)
    today = datetime.now(UTC).strftime("%Y%m%d")
    cycle_path = state_dir / f"diagnostics_cycles_{today}.csv"
    agent_path = state_dir / f"diagnostics_agents_{today}.csv"
    portfolio_path = state_dir / f"diagnostics_portfolio_{today}.csv"
    seen_cycles = load_seen_cycles(cycle_path)
    print(
        f"Logging diagnostics to {cycle_path}, {agent_path}, and {portfolio_path}.",
        flush=True,
    )

    while True:
        now = datetime.now(UTC)
        clock = alpaca_clock()
        is_open = bool(clock.get("is_open")) if clock else True
        next_close = str(clock.get("next_close") or "") if clock else ""

        agent_rows = read_csv(state_dir / "agent_scores.csv")
        execution_rows = read_csv(state_dir / "execution_plan.csv")
        research_rows = read_csv(state_dir / "research_ledger.csv")

        cycles = cycles_by_timestamp(agent_rows)
        for timestamp in sorted(cycles):
            if timestamp in seen_cycles:
                continue
            previous_timestamp = previous_cycle_timestamp(cycles, timestamp)
            record_cycle(
                cycle_path,
                agent_path,
                timestamp,
                previous_timestamp,
                cycles[timestamp],
                execution_rows,
                research_rows,
                workers_per_industry=args.workers_per_industry,
                discover_per_industry=args.discover_per_industry,
            )
            seen_cycles.add(timestamp)

        record_portfolio_snapshot(portfolio_path, now, clock, state_dir)

        if args.until_market_close and clock and not is_open:
            print("Market is closed; diagnostic logger stopping.", flush=True)
            return
        if args.until_market_close and next_close:
            try:
                close_dt = datetime.fromisoformat(next_close)
                if now.timestamp() > close_dt.timestamp() + 120:
                    print("Past market close; diagnostic logger stopping.", flush=True)
                    return
            except ValueError:
                pass

        time.sleep(max(5.0, args.interval_seconds))


def record_cycle(
    cycle_path: Path,
    agent_path: Path,
    timestamp: str,
    previous_timestamp: str | None,
    rows: list[dict[str, str]],
    execution_rows: list[dict[str, str]],
    research_rows: list[dict[str, str]],
    *,
    workers_per_industry: int,
    discover_per_industry: int,
) -> None:
    by_agent: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_agent[row.get("agent_name", row.get("agent", "unknown"))].append(row)

    cycle_seconds = seconds_between(previous_timestamp, timestamp)
    agent_summaries = [agent_summary(agent, agent_rows, cycle_seconds, workers_per_industry) for agent, agent_rows in by_agent.items()]
    total_researched = sum(item["researched"] for item in agent_summaries)
    total_errors = sum(item["errors"] for item in agent_summaries)
    total_skipped = sum(item["skipped"] for item in agent_summaries)
    total_capacity = max(1, len(agent_summaries) * discover_per_industry)
    actions = Counter(row.get("action", "") for row in rows)
    latest_execution = latest_rows_for_timestamp(execution_rows)
    exec_status = Counter(row.get("status", "") for row in latest_execution)
    approved = [
        row for row in latest_execution
        if "APPROVED" in row.get("status", "") and float_or_zero(row.get("notional")) > 0
    ]
    latest_research = [row for row in research_rows if row.get("timestamp") == timestamp]
    memory_status = Counter(row.get("memory_status", "") for row in latest_research)

    append_row(
        cycle_path,
        [
            "logged_at",
            "cycle_timestamp",
            "cycle_seconds",
            "agents",
            "workers_per_industry",
            "discover_per_industry",
            "total_researched",
            "total_skipped",
            "total_errors",
            "research_per_minute",
            "capacity_fill_rate",
            "buy_count",
            "watch_count",
            "pass_count",
            "approved_count",
            "rejected_count",
            "active_memory_count",
            "disposed_memory_count",
            "top_symbol",
            "top_score",
            "top_action",
        ],
        {
            "logged_at": datetime.now(UTC).isoformat(),
            "cycle_timestamp": timestamp,
            "cycle_seconds": f"{cycle_seconds:.2f}" if cycle_seconds else "",
            "agents": len(agent_summaries),
            "workers_per_industry": workers_per_industry,
            "discover_per_industry": discover_per_industry,
            "total_researched": total_researched,
            "total_skipped": total_skipped,
            "total_errors": total_errors,
            "research_per_minute": f"{per_minute(total_researched, cycle_seconds):.2f}",
            "capacity_fill_rate": f"{total_researched / total_capacity:.4f}",
            "buy_count": actions.get("BUY", 0),
            "watch_count": actions.get("WATCH", 0),
            "pass_count": actions.get("PASS", 0),
            "approved_count": len(approved),
            "rejected_count": exec_status.get("REJECTED", 0),
            "active_memory_count": memory_status.get("ACTIVE", 0),
            "disposed_memory_count": memory_status.get("DISPOSED", 0),
            "top_symbol": rows[0].get("symbol", "") if rows else "",
            "top_score": rows[0].get("opportunity_score", "") if rows else "",
            "top_action": rows[0].get("action", "") if rows else "",
        },
    )

    for summary in agent_summaries:
        append_row(
            agent_path,
            [
                "logged_at",
                "cycle_timestamp",
                "agent_name",
                "industry",
                "workers",
                "researched",
                "skipped",
                "errors",
                "research_per_minute",
                "worker_research_per_minute",
                "candidate_fill_rate",
                "agent_average_score",
                "top_symbol",
                "top_score",
                "top_action",
            ],
            {
                "logged_at": datetime.now(UTC).isoformat(),
                "cycle_timestamp": timestamp,
                "agent_name": summary["agent_name"],
                "industry": summary["industry"],
                "workers": workers_per_industry,
                "researched": summary["researched"],
                "skipped": summary["skipped"],
                "errors": summary["errors"],
                "research_per_minute": f"{summary['research_per_minute']:.2f}",
                "worker_research_per_minute": f"{summary['worker_research_per_minute']:.2f}",
                "candidate_fill_rate": f"{summary['researched'] / max(1, discover_per_industry):.4f}",
                "agent_average_score": summary["agent_average_score"],
                "top_symbol": summary["top_symbol"],
                "top_score": summary["top_score"],
                "top_action": summary["top_action"],
            },
        )

    print(
        f"Logged cycle {timestamp}: researched={total_researched}, errors={total_errors}, "
        f"approved={len(approved)}, top={rows[0].get('symbol', '') if rows else ''}.",
        flush=True,
    )


def agent_summary(agent_name: str, rows: list[dict[str, str]], cycle_seconds: float, workers: int) -> dict[str, Any]:
    first = rows[0] if rows else {}
    researched = int(float_or_zero(first.get("researched")))
    skipped = int(float_or_zero(first.get("skipped")))
    errors = int(float_or_zero(first.get("errors")))
    return {
        "agent_name": agent_name,
        "industry": first.get("industry", ""),
        "researched": researched,
        "skipped": skipped,
        "errors": errors,
        "research_per_minute": per_minute(researched, cycle_seconds),
        "worker_research_per_minute": per_minute(researched, cycle_seconds) / max(1, workers),
        "agent_average_score": first.get("agent_average_score", ""),
        "top_symbol": first.get("symbol", ""),
        "top_score": first.get("opportunity_score", ""),
        "top_action": first.get("action", ""),
    }


def record_portfolio_snapshot(path: Path, now: datetime, clock: dict[str, Any] | None, state_dir: Path) -> None:
    account: dict[str, Any] = {}
    positions: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    try:
        client = AlpacaClient()
        account = client.account()
        positions = client.positions()
        orders = client.orders(status="open", limit=100)
    except (AlpacaConfigError, OSError, Exception) as exc:
        account = {"error": str(exc)}

    append_row(
        path,
        [
            "logged_at",
            "is_open",
            "next_close",
            "cash",
            "buying_power",
            "equity",
            "portfolio_value",
            "positions_count",
            "open_orders_count",
            "positions",
            "latest_cycle_timestamp",
            "latest_cycle_age_seconds",
            "account_error",
        ],
        {
            "logged_at": now.isoformat(),
            "is_open": clock.get("is_open", "") if clock else "",
            "next_close": clock.get("next_close", "") if clock else "",
            "cash": account.get("cash", ""),
            "buying_power": account.get("buying_power", ""),
            "equity": account.get("equity", ""),
            "portfolio_value": account.get("portfolio_value", ""),
            "positions_count": len(positions),
            "open_orders_count": len(orders),
            "positions": ";".join(
                f"{p.get('symbol')}:{p.get('qty')}:{p.get('market_value')}:{p.get('unrealized_pl')}"
                for p in positions
            ),
            "latest_cycle_timestamp": latest_timestamp(state_dir / "agent_scores.csv"),
            "latest_cycle_age_seconds": latest_cycle_age_seconds(state_dir / "agent_scores.csv", now),
            "account_error": account.get("error", ""),
        },
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def append_row(path: Path, fields: list[str], row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def cycles_by_timestamp(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    cycles: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        timestamp = row.get("timestamp", "")
        if timestamp:
            cycles[timestamp].append(row)
    return cycles


def latest_rows_for_timestamp(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if not rows:
        return []
    timestamp = max(row.get("timestamp", "") for row in rows)
    return [row for row in rows if row.get("timestamp") == timestamp]


def previous_cycle_timestamp(cycles: dict[str, list[dict[str, str]]], timestamp: str) -> str | None:
    ordered = sorted(cycles)
    index = ordered.index(timestamp)
    return ordered[index - 1] if index > 0 else None


def seconds_between(previous: str | None, current: str) -> float:
    if not previous:
        return 0.0
    try:
        return (datetime.fromisoformat(current) - datetime.fromisoformat(previous)).total_seconds()
    except ValueError:
        return 0.0


def per_minute(count: int, seconds: float) -> float:
    if seconds <= 0:
        return 0.0
    return count / (seconds / 60.0)


def latest_timestamp(path: Path) -> str:
    rows = read_csv(path)
    return max((row.get("timestamp", "") for row in rows), default="")


def latest_cycle_age_seconds(path: Path, now: datetime) -> str:
    timestamp = latest_timestamp(path)
    if not timestamp:
        return ""
    try:
        return f"{(now - datetime.fromisoformat(timestamp)).total_seconds():.2f}"
    except ValueError:
        return ""


def load_seen_cycles(path: Path) -> set[str]:
    rows = read_csv(path)
    return {row.get("cycle_timestamp", "") for row in rows if row.get("cycle_timestamp")}


def alpaca_clock() -> dict[str, Any] | None:
    try:
        return AlpacaClient().clock()
    except (AlpacaConfigError, OSError, Exception):
        return None


def float_or_zero(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    main()
