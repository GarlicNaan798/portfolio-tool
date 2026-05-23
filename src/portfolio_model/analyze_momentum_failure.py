from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from portfolio_model.backtest import (
    AgentParams,
    common_calendar,
    fetch_sp500_sectors,
    load_or_fetch_bars,
    market_regime,
    prepare_rankings,
    price_table,
    simulate,
)
from portfolio_model.env import load_dotenv


def main() -> None:
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(description="Analyze yearly failure modes for momentum breakout.")
    parser.add_argument("--year", type=int, default=2022)
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--cache", default="state/backtest_bars_sp500.json")
    parser.add_argument("--output-prefix", default="state/momentum_failure_2022")
    parser.add_argument("--cost-bps", type=float, default=10.0)
    args = parser.parse_args()

    end = datetime.now(UTC).date()
    start = end - timedelta(days=round(args.years * 365.25))
    sectors = local_sector_map(Path("data/industry_agents.csv"))
    if not sectors:
        sectors = fetch_sp500_sectors()
    symbols = list(dict.fromkeys([*sectors, "SPY"]))
    bars = load_or_fetch_bars(symbols=symbols, start=start, end=end, feed="iex", cache_path=Path(args.cache))
    bars = {symbol: series for symbol, series in bars.items() if len(series) >= 260}
    calendar = common_calendar(bars)
    prices = price_table(bars)
    rankings = prepare_rankings(
        bars,
        prices,
        calendar,
        rebalance_every=5,
        strategy_book="momentum_breakout",
        sectors=sectors,
    )
    days = [day for day in calendar if day.year == args.year]
    params = AgentParams(6.5, 5, 0.08, 0.35, False, 0.18, 0.40, 0.75, False)
    metrics, rows = simulate(
        bars,
        days,
        params,
        rankings={day: value for day, value in rankings.items() if day in set(days)},
        prices=prices,
        sectors=sectors,
        rebalance_every=5,
        cost_bps=args.cost_bps,
    )

    prefix = Path(args.output_prefix)
    write_trades(prefix.with_name(f"{prefix.name}_trades.csv"), rows, sectors)
    write_months(prefix.with_name(f"{prefix.name}_months.csv"), rows)
    write_sectors(prefix.with_name(f"{prefix.name}_sectors.csv"), rows, sectors)
    write_regime(prefix.with_name(f"{prefix.name}_regime.csv"), days, prices)
    write_summary(prefix.with_name(f"{prefix.name}_summary.md"), args.year, metrics, rows, prices)
    print(
        f"{args.year}: return={metrics['total_return']:.2%}, dd={metrics['max_drawdown']:.2%}, "
        f"trades={metrics['trade_count']}, pf={metrics['profit_factor']:.2f}, avg_r={metrics['average_r']:.2f}",
        flush=True,
    )


def write_trades(path: Path, rows: list[dict[str, str]], sectors: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        fields = ["date", "symbol", "sector", "score", "action"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            if row["symbol"] == "__EQUITY__":
                continue
            writer.writerow({**row, "sector": sectors.get(row["symbol"], "Unknown")})


def write_months(path: Path, rows: list[dict[str, str]]) -> None:
    monthly = {}
    previous = None
    for row in rows:
        if row["symbol"] != "__EQUITY__":
            continue
        month = str(row["date"])[:7]
        value = float(row["action"])
        first, _ = monthly.get(month, (value, value))
        monthly[month] = (first, value)
        previous = value
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["month", "return"])
        writer.writeheader()
        for month, (first, last) in monthly.items():
            writer.writerow({"month": month, "return": f"{(last / first - 1.0 if first else 0.0):.6f}"})


def write_sectors(path: Path, rows: list[dict[str, str]], sectors: dict[str, str]) -> None:
    stats = defaultdict(lambda: {"selects": 0, "exits": 0, "exit_return": 0.0})
    for row in rows:
        if row["symbol"] == "__EQUITY__":
            continue
        sector = sectors.get(row["symbol"], "Unknown")
        if row["action"] == "SELECT":
            stats[sector]["selects"] += 1
        elif row["action"] == "EXIT":
            stats[sector]["exits"] += 1
            stats[sector]["exit_return"] += float(row["score"])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sector", "selects", "exits", "average_exit_return"])
        writer.writeheader()
        for sector, values in sorted(stats.items(), key=lambda item: item[1]["selects"], reverse=True):
            exits = values["exits"]
            writer.writerow(
                {
                    "sector": sector,
                    "selects": values["selects"],
                    "exits": exits,
                    "average_exit_return": f"{(values['exit_return'] / exits if exits else 0.0):.6f}",
                }
            )


def write_regime(path: Path, days, prices) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "regime"])
        writer.writeheader()
        for day in days:
            writer.writerow({"date": day.isoformat(), "regime": market_regime(prices.get("SPY", {}), day)})


def write_summary(path: Path, year: int, metrics: dict[str, float], rows: list[dict[str, str]], prices) -> None:
    exits = [row for row in rows if row.get("action") == "EXIT"]
    worst = sorted(exits, key=lambda row: float(row["score"]))[:10]
    regimes = defaultdict(int)
    for row in rows:
        if row["symbol"] == "__EQUITY__":
            continue
        day = datetime.fromisoformat(row["date"]).date()
        regimes[market_regime(prices.get("SPY", {}), day)] += 1
    lines = [
        f"# Momentum Failure Analysis: {year}",
        "",
        f"- Return: {metrics['total_return']:.2%}",
        f"- Max drawdown: {metrics['max_drawdown']:.2%}",
        f"- Trades: {metrics['trade_count']}",
        f"- Profit factor: {metrics['profit_factor']:.2f}",
        f"- Average R: {metrics['average_r']:.2f}",
        f"- Selection/exits by regime: {dict(regimes)}",
        "",
        "## Worst Realized Exits",
        "",
    ]
    for row in worst:
        lines.append(f"- {row['date']} {row['symbol']}: {float(row['score']):.2%}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()


def local_sector_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return {
            row["symbol"].strip().upper(): row.get("industry", "Unknown").strip() or "Unknown"
            for row in rows
            if row.get("symbol")
        }
