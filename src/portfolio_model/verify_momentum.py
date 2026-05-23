from __future__ import annotations

import argparse
import csv
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from portfolio_model.backtest import (
    AgentParams,
    buy_and_hold_return,
    common_calendar,
    fetch_sp500_sectors,
    load_or_fetch_bars,
    prepare_rankings,
    price_table,
    simulate,
)
from portfolio_model.env import load_dotenv


def main() -> None:
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(description="Replicability checks for the momentum breakout book.")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--max-symbols", type=int, default=503)
    parser.add_argument("--cache", default="state/backtest_bars_sp500.json")
    parser.add_argument("--output", default="state/momentum_replicability_checks.csv")
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--regime-reducer", action="store_true")
    args = parser.parse_args()

    end = datetime.now(UTC).date()
    start = end - timedelta(days=round(args.years * 365.25))
    sectors = fetch_sp500_sectors()
    symbols = list(dict.fromkeys([*sectors, "SPY"]))[: max(1, args.max_symbols)]
    if "SPY" not in symbols:
        symbols.append("SPY")

    bars = load_or_fetch_bars(
        symbols=symbols,
        start=start,
        end=end,
        feed="iex",
        cache_path=Path(args.cache),
    )
    bars = {symbol: series for symbol, series in bars.items() if len(series) >= 260}
    calendar = common_calendar(bars)
    prices = price_table(bars)
    full_rankings = prepare_rankings(
        bars,
        prices,
        calendar,
        rebalance_every=5,
        strategy_book="momentum_breakout",
        sectors=sectors,
    )
    params = AgentParams(
        min_score=6.5,
        max_positions=5,
        stop_loss=0.08,
        take_profit=0.35,
        regime_filter=False,
        volatility_target=0.18,
        sector_cap=0.40,
        correlation_cap=0.75,
        drawdown_throttle=False,
    )

    rows = []
    for label, window_days in yearly_windows(calendar):
        rows.append(run_window(label, bars, prices, sectors, params, window_days, full_rankings, args.cost_bps, delay_rebalances=0, regime_reducer=args.regime_reducer))
        rows.append(run_window(f"{label}_delayed_1w", bars, prices, sectors, params, window_days, full_rankings, args.cost_bps, delay_rebalances=5, regime_reducer=args.regime_reducer))

    write_rows(Path(args.output), rows)
    for row in rows:
        print(
            f"{row['window']}: return={float(row['total_return']):.2%}, "
            f"spy={float(row['benchmark_return']):.2%}, excess={float(row['excess_return']):.2%}, "
            f"dd={float(row['max_drawdown']):.2%}, trades={row['trade_count']}, "
            f"pf={float(row['profit_factor']):.2f}, delay={row['delay_rebalances']}",
            flush=True,
        )


def run_window(
    label: str,
    bars,
    prices,
    sectors: dict[str, str],
    params: AgentParams,
    window_days: list[date],
    full_rankings: dict[date, list[tuple[str, float]]],
    cost_bps: float,
    *,
    delay_rebalances: int,
    regime_reducer: bool,
) -> dict[str, str]:
    window_set = set(window_days)
    rankings = {day: rows for day, rows in full_rankings.items() if day in window_set}
    if delay_rebalances:
        rankings = delayed_rankings(rankings, window_days, delay_rebalances)
    metrics, _ = simulate(
        bars,
        window_days,
        params,
        rankings=rankings,
        prices=prices,
        sectors=sectors,
        rebalance_every=5,
        cost_bps=cost_bps,
        regime_reducer=regime_reducer,
    )
    benchmark = buy_and_hold_return(bars["SPY"], window_days)
    return {
        "window": label,
        "start": window_days[0].isoformat(),
        "end": window_days[-1].isoformat(),
        "delay_rebalances": str(delay_rebalances),
        "total_return": f"{metrics['total_return']:.6f}",
        "benchmark_return": f"{benchmark:.6f}",
        "excess_return": f"{(metrics['total_return'] - benchmark):.6f}",
        "max_drawdown": f"{metrics['max_drawdown']:.6f}",
        "sharpe": f"{metrics['sharpe']:.6f}",
        "trade_count": str(metrics["trade_count"]),
        "profit_factor": f"{metrics['profit_factor']:.6f}",
        "average_r": f"{metrics['average_r']:.6f}",
        "largest_symbol_pnl_share": f"{metrics['largest_symbol_pnl_share']:.6f}",
    }


def yearly_windows(calendar: list[date]) -> list[tuple[str, list[date]]]:
    years = sorted({day.year for day in calendar})
    windows = []
    for year in years:
        days = [day for day in calendar if day.year == year]
        if len(days) >= 120:
            windows.append((str(year), days))
    return windows


def delayed_rankings(
    rankings: dict[date, list[tuple[str, float]]],
    calendar: list[date],
    delay_days: int,
) -> dict[date, list[tuple[str, float]]]:
    delayed = {}
    for day in sorted(rankings):
        index = calendar.index(day)
        delayed_day = calendar[min(len(calendar) - 1, index + delay_days)]
        delayed[delayed_day] = rankings[day]
    return delayed


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "window",
        "start",
        "end",
        "delay_rebalances",
        "total_return",
        "benchmark_return",
        "excess_return",
        "max_drawdown",
        "sharpe",
        "trade_count",
        "profit_factor",
        "average_r",
        "largest_symbol_pnl_share",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
