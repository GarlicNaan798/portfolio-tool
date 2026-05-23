from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from portfolio_model.alpaca import AlpacaApiError, AlpacaClient, AlpacaConfigError
from portfolio_model.backtest_scoring import (
    clamp,
    cross_sectional_inverse_score,
    cross_sectional_score,
    forward_pe_value_score,
    growth_proxy_score,
    latest_forward_estimate,
    load_forward_estimates,
    metric_priority_score,
    momentum_breakout_score,
    quality_proxy_score,
    rank_forward_pe_symbols,
    rank_symbols,
    sentiment_proxy_score,
    strategy_features,
    strategy_min_scores,
    strategy_score,
    strategy_stop_losses,
    strategy_take_profits,
    value_proxy_score,
    value_reversion_score,
    trailing_volatility,
    validate_forward_estimates,
)
from portfolio_model.backtest_types import (
    AgentParams,
    BacktestResult,
    ForwardEstimate,
    PriceBar,
    STRATEGY_BOOKS,
    StrategyFeatures,
)
from portfolio_model.env import load_dotenv


SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def main() -> None:
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(description="Walk-forward backtest for the local industry-agent decision logic.")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--train-fraction", type=float, default=0.75)
    parser.add_argument("--symbols-file", default="")
    parser.add_argument("--max-symbols", type=int, default=120)
    parser.add_argument("--feed", default="iex")
    parser.add_argument("--cache", default="state/backtest_bars.json")
    parser.add_argument("--summary", default="state/backtest_summary.csv")
    parser.add_argument("--equity-curve", default="state/backtest_equity_curve.csv")
    parser.add_argument("--trades", default="state/backtest_trades.csv")
    parser.add_argument("--fast-grid", action="store_true", help="Use a small parameter grid for strategy-book comparison.")
    parser.add_argument("--fixed-params", action="store_true", help="Evaluate the explicit parameter flags instead of training a grid.")
    parser.add_argument("--rebalance-every", type=int, default=21, help="Trading days between rebalance decisions.")
    parser.add_argument("--min-score", type=float, default=6.0)
    parser.add_argument("--max-positions", type=int, default=5)
    parser.add_argument("--stop-loss", type=float, default=0.08)
    parser.add_argument("--take-profit", type=float, default=0.35)
    parser.add_argument("--volatility-target", type=float, default=0.12)
    parser.add_argument("--sector-cap", type=float, default=0.40)
    parser.add_argument("--correlation-cap", type=float, default=0.75)
    parser.add_argument("--cost-bps", type=float, default=0.0, help="One-way transaction cost/slippage in basis points.")
    parser.add_argument("--regime-filter", action="store_true")
    parser.add_argument("--regime-reducer", action="store_true", help="Reduce exposure in weak/high-volatility SPY regimes without disabling entries.")
    parser.add_argument("--drawdown-throttle", action="store_true")
    parser.add_argument(
        "--forward-estimates",
        default="",
        help="Point-in-time CSV with date,symbol,forward_pe,forward_eps_yoy,forward_eps_revision_3m,fcf_yield,debt_to_equity.",
    )
    parser.add_argument(
        "--strategy-book",
        default="metric_priority",
        choices=STRATEGY_BOOKS,
        help="Strategy book to test: explicit entry logic instead of one blended stock score.",
    )
    args = parser.parse_args()

    end = datetime.now(UTC).date()
    start = end - timedelta(days=round(args.years * 365.25))
    sectors = {} if args.symbols_file else fetch_sp500_sectors()
    symbols = load_symbols(args.symbols_file) if args.symbols_file else list(sectors)
    symbols = list(dict.fromkeys([*symbols, "SPY"]))[: max(1, args.max_symbols)]
    if "SPY" not in symbols:
        symbols.append("SPY")

    bars = load_or_fetch_bars(
        symbols=symbols,
        start=start,
        end=end,
        feed=args.feed,
        cache_path=Path(args.cache),
    )
    bars = {symbol: series for symbol, series in bars.items() if len(series) >= 260}
    if "SPY" not in bars:
        raise RuntimeError("SPY benchmark data is required for the backtest.")

    calendar = common_calendar(bars)
    split_index = max(260, min(len(calendar) - 2, int(len(calendar) * args.train_fraction)))
    train_days = calendar[:split_index]
    test_days = calendar[split_index:]

    prices = price_table(bars)
    forward_estimates = load_forward_estimates(Path(args.forward_estimates)) if args.forward_estimates else {}
    if args.strategy_book == "forward_pe_value":
        validate_forward_estimates(forward_estimates)
    print(f"Loaded {len(bars)} symbols. Preparing rankings...", flush=True)
    rankings = prepare_rankings(
        bars,
        prices,
        calendar,
        rebalance_every=args.rebalance_every,
        strategy_book=args.strategy_book,
        sectors=sectors,
        forward_estimates=forward_estimates,
    )
    print(f"Prepared rankings for {len(rankings)} rebalance dates. Training agents...", flush=True)
    if args.fixed_params:
        best = AgentParams(
            args.min_score,
            args.max_positions,
            args.stop_loss,
            args.take_profit,
            args.regime_filter,
            args.volatility_target,
            args.sector_cap,
            args.correlation_cap,
            args.drawdown_throttle,
        )
    else:
        best = train_agents(
            bars,
            train_days,
            rankings=rankings,
            prices=prices,
            sectors=sectors,
            fast=args.fast_grid,
            strategy_book=args.strategy_book,
            rebalance_every=args.rebalance_every,
        )
    print("Evaluating train/test split...", flush=True)
    train_result, _ = simulate(
        bars,
        train_days,
        best,
        rankings=rankings,
        prices=prices,
        sectors=sectors,
        rebalance_every=args.rebalance_every,
        cost_bps=args.cost_bps,
        regime_reducer=args.regime_reducer,
    )
    test_result, test_rows = simulate(
        bars,
        test_days,
        best,
        rankings=rankings,
        prices=prices,
        sectors=sectors,
        rebalance_every=args.rebalance_every,
        cost_bps=args.cost_bps,
        regime_reducer=args.regime_reducer,
    )
    benchmark_return = buy_and_hold_return(bars["SPY"], test_days)
    result = BacktestResult(
        strategy_book=args.strategy_book,
        rebalance_every=args.rebalance_every,
        params=best,
        train_return=train_result["total_return"],
        test_return=test_result["total_return"],
        benchmark_return=benchmark_return,
        excess_return=test_result["total_return"] - benchmark_return,
        max_drawdown=test_result["max_drawdown"],
        sharpe=test_result["sharpe"],
        win_rate=test_result["win_rate"],
        rebalance_count=test_result["rebalance_count"],
        trade_count=test_result["trade_count"],
        profit_factor=test_result["profit_factor"],
        average_r=test_result["average_r"],
        sample_warning=sample_size_warning(test_result["trade_count"]),
    )
    write_summary(Path(args.summary), result, start, end, len(bars), len(train_days), len(test_days))
    write_equity_curve(Path(args.equity_curve), test_rows)
    write_trades(Path(args.trades), test_rows)
    print_summary(result, start, end, len(bars), len(train_days), len(test_days))


def train_agents(
    bars: dict[str, list[PriceBar]],
    days: list[date],
    *,
    rankings: dict[date, list[tuple[str, float]]] | None = None,
    prices: dict[str, dict[date, float]] | None = None,
    sectors: dict[str, str] | None = None,
    fast: bool = False,
    strategy_book: str = "metric_priority",
    rebalance_every: int = 21,
) -> AgentParams:
    grid = []
    min_scores = (6.0, 6.5) if fast else strategy_min_scores(strategy_book)
    max_position_options = (5,) if fast else (5, 8)
    stop_losses = (0.08,) if fast else strategy_stop_losses(strategy_book)
    take_profits = (0.35,) if fast else strategy_take_profits(strategy_book)
    regime_filters = (True, False)
    volatility_targets = (0.12,) if fast else (0.08, 0.12, 0.18)
    sector_caps = (0.40,) if fast else (0.20, 0.40)
    correlation_caps = (0.75,) if fast else (0.60, 0.75)
    drawdown_throttles = (True, False)
    for min_score in min_scores:
        for max_positions in max_position_options:
            for stop_loss in stop_losses:
                for take_profit in take_profits:
                    for regime_filter in regime_filters:
                        for volatility_target in volatility_targets:
                            for sector_cap in sector_caps:
                                for correlation_cap in correlation_caps:
                                    for drawdown_throttle in drawdown_throttles:
                                        grid.append(
                                            AgentParams(
                                                min_score,
                                                max_positions,
                                                stop_loss,
                                                take_profit,
                                                regime_filter,
                                                volatility_target,
                                                sector_cap,
                                                correlation_cap,
                                                drawdown_throttle,
                                            )
                                        )
    scored = []
    validation_start = max(260, int(len(days) * 0.70))
    fit_days = days[:validation_start]
    validation_days = days[validation_start:]
    for params in grid:
        fit_metrics, _ = simulate(
            bars,
            fit_days,
            params,
            rankings=rankings,
            prices=prices,
            sectors=sectors,
            rebalance_every=rebalance_every,
        )
        validation_metrics, _ = simulate(
            bars,
            validation_days,
            params,
            rankings=rankings,
            prices=prices,
            sectors=sectors,
            rebalance_every=rebalance_every,
        )
        scored.append((training_objective(params, fit_metrics, validation_metrics), params))
    return max(scored, key=lambda item: item[0])[1]


def training_objective(params: AgentParams, fit_metrics: dict[str, float], validation_metrics: dict[str, float]) -> float:
    validation_return = validation_metrics["total_return"]
    validation_drawdown = abs(validation_metrics["max_drawdown"])
    fit_return = fit_metrics["total_return"]
    fit_drawdown = abs(fit_metrics["max_drawdown"])
    robustness = min(max(fit_return, -0.25), 0.75) * 0.10 - max(0.0, fit_drawdown - validation_drawdown) * 0.50
    drawdown_penalty = validation_drawdown * 2.00 + max(0.0, validation_drawdown - 0.16) * 3.00
    sharpe_reward = max(validation_metrics["sharpe"], -1.0) * 0.25
    return_floor_penalty = max(0.0, 0.15 - validation_return) * 1.25
    constraint_reward = 0.0
    if params.sector_cap <= 0.40:
        constraint_reward += 0.02
    if params.correlation_cap <= 0.75:
        constraint_reward += 0.02
    if params.drawdown_throttle:
        constraint_reward += 0.03
    if params.regime_filter:
        constraint_reward += 0.02
    turnover_penalty = max(0.0, validation_metrics["rebalance_count"] - 80) * 0.001
    return (
        validation_return
        + sharpe_reward
        + robustness
        + constraint_reward
        - drawdown_penalty
        - return_floor_penalty
        - turnover_penalty
    )


def simulate(
    bars: dict[str, list[PriceBar]],
    days: list[date],
    params: AgentParams,
    *,
    rebalance_every: int = 21,
    rankings: dict[date, list[tuple[str, float]]] | None = None,
    prices: dict[str, dict[date, float]] | None = None,
    sectors: dict[str, str] | None = None,
    cost_bps: float = 0.0,
    regime_reducer: bool = False,
) -> tuple[dict[str, float], list[dict[str, float | str]]]:
    prices = prices or price_table(bars)
    sectors = sectors or {}
    investable = [symbol for symbol in bars if symbol != "SPY"]
    cash = 1.0
    positions: dict[str, tuple[float, float]] = {}
    equity_curve = []
    rows = []
    trade_returns = []
    trade_pnls: dict[str, float] = {}
    last_value = 1.0
    cost_rate = max(0.0, cost_bps) / 10_000.0

    for index, day in enumerate(days):
        value = cash + sum(qty * prices.get(symbol, {}).get(day, 0.0) for symbol, (qty, _) in positions.items())
        if value <= 0:
            continue
        portfolio_peak = max([1.0, *(row[1] for row in equity_curve)], default=1.0)
        portfolio_drawdown = value / portfolio_peak - 1.0 if portfolio_peak else 0.0

        for symbol, (qty, entry) in list(positions.items()):
            price = prices.get(symbol, {}).get(day)
            if not price:
                continue
            pnl = price / entry - 1.0
            if pnl <= -params.stop_loss or pnl >= params.take_profit:
                exit_value = qty * price
                cost = exit_value * cost_rate
                cash += exit_value - cost
                trade_returns.append(pnl)
                trade_pnls[symbol] = trade_pnls.get(symbol, 0.0) + qty * (price - entry) - cost
                rows.append({"date": day.isoformat(), "symbol": symbol, "score": f"{pnl:.4f}", "action": "EXIT"})
                del positions[symbol]

        should_rebalance = day in rankings if rankings is not None else index % rebalance_every == 0 and index >= 252
        if should_rebalance:
            value = cash + sum(qty * prices.get(symbol, {}).get(day, 0.0) for symbol, (qty, _) in positions.items())
            ranked = rankings.get(day, []) if rankings is not None else rank_symbols(investable, bars, prices, day)
            if params.regime_filter and market_regime(prices.get("SPY", {}), day) == "RISK_OFF":
                ranked = []
            exposure_multiplier = 1.0
            if params.drawdown_throttle:
                exposure_multiplier *= drawdown_exposure_multiplier(portfolio_drawdown)
            if regime_reducer:
                exposure_multiplier *= regime_exposure_multiplier(prices.get("SPY", {}), bars.get("SPY", []), day)
            min_score = params.min_score + (0.5 if params.drawdown_throttle and portfolio_drawdown <= -0.05 else 0.0)
            max_positions = max(1, params.max_positions // 2) if params.drawdown_throttle and portfolio_drawdown <= -0.08 else params.max_positions
            selected = select_candidates(
                ranked,
                min_score=min_score,
                max_positions=max_positions,
                sector_cap=params.sector_cap,
                correlation_cap=params.correlation_cap,
                sectors=sectors,
                bars=bars,
                prices=prices,
                day=day,
            )
            selected_symbols = {symbol for symbol, _ in selected}
            for symbol, (qty, _) in list(positions.items()):
                price = prices.get(symbol, {}).get(day)
                if symbol not in selected_symbols and price:
                    entry = positions[symbol][1]
                    exit_value = qty * price
                    cost = exit_value * cost_rate
                    cash += exit_value - cost
                    pnl = price / entry - 1.0
                    trade_returns.append(pnl)
                    trade_pnls[symbol] = trade_pnls.get(symbol, 0.0) + qty * (price - entry) - cost
                    rows.append({"date": day.isoformat(), "symbol": symbol, "score": f"{pnl:.4f}", "action": "EXIT"})
                    del positions[symbol]

            if selected:
                weights = risk_weights(selected, bars, prices, day, params.volatility_target, exposure_multiplier=exposure_multiplier)
                for symbol, score in selected:
                    price = prices.get(symbol, {}).get(day)
                    if not price:
                        continue
                    target_value = value * weights.get(symbol, 0.0)
                    current_qty, _ = positions.get(symbol, (0.0, price))
                    current_value = current_qty * price
                    delta = target_value - current_value
                    if delta < 0 and current_qty > 0:
                        sell_value = min(current_value, abs(delta))
                        sell_qty = sell_value / price
                        cost = sell_value * cost_rate
                        cash += sell_value - cost
                        remaining_qty = current_qty - sell_qty
                        if remaining_qty > 1e-12:
                            positions[symbol] = (remaining_qty, positions[symbol][1])
                        else:
                            del positions[symbol]
                    if delta > 0 and cash > 0:
                        gross_buy_value = min(cash / (1.0 + cost_rate), delta)
                        cost = gross_buy_value * cost_rate
                        positions[symbol] = (current_qty + gross_buy_value / price, price)
                        cash -= gross_buy_value + cost
                    rows.append({"date": day.isoformat(), "symbol": symbol, "score": f"{score:.4f}", "action": "SELECT"})

        value = cash + sum(qty * prices.get(symbol, {}).get(day, 0.0) for symbol, (qty, _) in positions.items())
        daily_return = value / last_value - 1.0 if last_value else 0.0
        equity_curve.append((day, value, daily_return))
        rows.append({"date": day.isoformat(), "symbol": "__EQUITY__", "score": "", "action": f"{value:.6f}"})
        last_value = value

    returns = [row[2] for row in equity_curve[1:]]
    total_return = equity_curve[-1][1] - 1.0 if equity_curve else 0.0
    return {
        "total_return": total_return,
        "max_drawdown": max_drawdown([row[1] for row in equity_curve]),
        "sharpe": sharpe_ratio(returns),
        "win_rate": sum(1 for item in returns if item > 0) / len(returns) if returns else 0.0,
        "rebalance_count": sum(1 for row in rows if row["action"] == "SELECT"),
        "trade_count": len(trade_returns),
        "profit_factor": profit_factor(trade_returns),
        "average_r": average_r(trade_returns, params.stop_loss),
        "largest_symbol_pnl_share": largest_symbol_pnl_share(trade_pnls),
    }, rows


def profit_factor(trade_returns: list[float]) -> float:
    gross_profit = sum(item for item in trade_returns if item > 0)
    gross_loss = abs(sum(item for item in trade_returns if item < 0))
    if gross_loss == 0:
        return 0.0 if gross_profit == 0 else 99.0
    return gross_profit / gross_loss


def average_r(trade_returns: list[float], stop_loss: float) -> float:
    if not trade_returns or stop_loss <= 0:
        return 0.0
    return statistics.mean(item / stop_loss for item in trade_returns)


def sample_size_warning(trade_count: int) -> str:
    if trade_count < 100:
        return "LOW_SAMPLE"
    if trade_count < 380:
        return "MODERATE_SAMPLE"
    return "OK"


def largest_symbol_pnl_share(trade_pnls: dict[str, float]) -> float:
    positive_total = sum(value for value in trade_pnls.values() if value > 0)
    if positive_total <= 0:
        return 0.0
    return max((value for value in trade_pnls.values() if value > 0), default=0.0) / positive_total


def prepare_rankings(
    bars: dict[str, list[PriceBar]],
    prices: dict[str, dict[date, float]],
    days: list[date],
    *,
    rebalance_every: int = 21,
    strategy_book: str = "metric_priority",
    sectors: dict[str, str] | None = None,
    forward_estimates: dict[str, list[ForwardEstimate]] | None = None,
) -> dict[date, list[tuple[str, float]]]:
    investable = [symbol for symbol in bars if symbol != "SPY"]
    rebalance_days = [day for index, day in enumerate(days) if index % rebalance_every == 0 and index >= 252]
    return {
        day: rank_symbols(
            investable,
            bars,
            prices,
            day,
            strategy_book=strategy_book,
            sectors=sectors,
            forward_estimates=forward_estimates,
        )
        for day in rebalance_days
    }


def risk_weights(
    selected: list[tuple[str, float]],
    bars: dict[str, list[PriceBar]],
    prices: dict[str, dict[date, float]],
    day: date,
    volatility_target: float,
    *,
    exposure_multiplier: float = 1.0,
) -> dict[str, float]:
    raw = {}
    for symbol, score in selected:
        vol = trailing_volatility(bars[symbol], day)
        raw[symbol] = max(score - 5.0, 0.01) / max(vol, 0.08)
    total = sum(raw.values())
    if total <= 0:
        return {symbol: 1.0 / len(selected) for symbol, _ in selected}
    gross_exposure = clamp(volatility_target / 0.18, 0.50, 1.25) * exposure_multiplier
    return {symbol: gross_exposure * value / total for symbol, value in raw.items()}


def select_candidates(
    ranked: list[tuple[str, float]],
    *,
    min_score: float,
    max_positions: int,
    sector_cap: float,
    correlation_cap: float,
    sectors: dict[str, str],
    bars: dict[str, list[PriceBar]],
    prices: dict[str, dict[date, float]],
    day: date,
) -> list[tuple[str, float]]:
    selected: list[tuple[str, float]] = []
    sector_counts: dict[str, int] = {}
    groups = set()
    max_sector_count = max(1, math.ceil(max_positions * sector_cap))

    for symbol, score in ranked:
        if score < min_score or len(selected) >= max_positions:
            continue
        group = exposure_group(symbol)
        if group in groups:
            continue
        sector = sectors.get(symbol, "Unknown")
        if sector_cap < 1.0 and sector_counts.get(sector, 0) >= max_sector_count:
            continue
        if correlation_cap < 1.0 and any(
            trailing_correlation(symbol, chosen, bars, prices, day) >= correlation_cap
            for chosen, _ in selected
        ):
            continue
        selected.append((symbol, score))
        groups.add(group)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    return selected


def exposure_group(symbol: str) -> str:
    duplicate_groups = {
        "GOOG": "GOOG",
        "GOOGL": "GOOG",
        "FOX": "FOX",
        "FOXA": "FOX",
        "NWS": "NWS",
        "NWSA": "NWS",
    }
    if symbol in duplicate_groups:
        return duplicate_groups[symbol]
    return symbol.split(".")[0]


def trailing_correlation(
    left: str,
    right: str,
    bars: dict[str, list[PriceBar]],
    prices: dict[str, dict[date, float]],
    day: date,
    window: int = 63,
) -> float:
    left_returns = trailing_returns(bars[left], prices[left], day, window)
    right_returns = trailing_returns(bars[right], prices[right], day, window)
    common_days = sorted(set(left_returns) & set(right_returns))
    if len(common_days) < 20:
        return 0.0
    x = [left_returns[item] for item in common_days]
    y = [right_returns[item] for item in common_days]
    x_mean = statistics.mean(x)
    y_mean = statistics.mean(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    x_var = sum((a - x_mean) ** 2 for a in x)
    y_var = sum((b - y_mean) ** 2 for b in y)
    if x_var <= 0 or y_var <= 0:
        return 0.0
    return numerator / math.sqrt(x_var * y_var)


def trailing_returns(series: list[PriceBar], prices: dict[date, float], day: date, window: int) -> dict[date, float]:
    index = next((i for i, bar in enumerate(series) if bar.day == day), -1)
    if index <= 0:
        return {}
    start = max(1, index - window + 1)
    returns = {}
    for item in series[start:index + 1]:
        previous_day_index = next((i for i, bar in enumerate(series) if bar.day == item.day), -1) - 1
        if previous_day_index < 0:
            continue
        previous = series[previous_day_index]
        if previous.close:
            returns[item.day] = item.close / previous.close - 1.0
    return returns


def drawdown_exposure_multiplier(drawdown: float) -> float:
    if drawdown <= -0.10:
        return 0.25
    if drawdown <= -0.08:
        return 0.40
    if drawdown <= -0.05:
        return 0.65
    if drawdown <= -0.03:
        return 0.80
    return 1.0


def market_regime(spy_prices: dict[date, float], day: date) -> str:
    days = sorted(item for item in spy_prices if item <= day)
    if len(days) < 200:
        return "RISK_ON"
    current = spy_prices[days[-1]]
    ma_200 = sum(spy_prices[item] for item in days[-200:]) / 200
    ma_50 = sum(spy_prices[item] for item in days[-50:]) / 50
    return "RISK_ON" if current >= ma_200 and ma_50 >= ma_200 else "RISK_OFF"


def regime_exposure_multiplier(spy_prices: dict[date, float], spy_bars: list[PriceBar], day: date) -> float:
    days = sorted(item for item in spy_prices if item <= day)
    if len(days) < 200:
        return 1.0
    current = spy_prices[days[-1]]
    ma_200 = sum(spy_prices[item] for item in days[-200:]) / 200
    ma_50 = sum(spy_prices[item] for item in days[-50:]) / 50
    multiplier = 1.0
    if current < ma_200:
        multiplier *= 0.50
    if ma_50 < ma_200:
        multiplier *= 0.75
    if trailing_volatility(spy_bars, day) >= 0.25:
        multiplier *= 0.70
    return clamp(multiplier, 0.25, 1.0)


def load_or_fetch_bars(
    *,
    symbols: list[str],
    start: date,
    end: date,
    feed: str,
    cache_path: Path,
) -> dict[str, list[PriceBar]]:
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        cached_symbols = set(payload.get("symbols", []))
        requested_symbols = set(symbols)
        if (
            payload.get("start") == start.isoformat()
            and payload.get("end") == end.isoformat()
            and requested_symbols.issubset(cached_symbols)
        ):
            return {
                symbol: [PriceBar(date.fromisoformat(row["day"]), float(row["close"])) for row in rows]
                for symbol, rows in payload.get("bars", {}).items()
                if symbol in requested_symbols
            }

    client = AlpacaClient()
    fetched: dict[str, list[PriceBar]] = {}
    for offset in range(0, len(symbols), 100):
        batch = symbols[offset:offset + 100]
        raw = client.historical_bars(
            batch,
            start=start.isoformat(),
            end=end.isoformat(),
            feed=feed,
        )
        for symbol, rows in raw.items():
            fetched[symbol] = [
                PriceBar(datetime.fromisoformat(row["t"].replace("Z", "+00:00")).date(), float(row["c"]))
                for row in rows
                if row.get("c") is not None and row.get("t")
            ]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "symbols": symbols,
                "bars": {
                    symbol: [{"day": bar.day.isoformat(), "close": bar.close} for bar in rows]
                    for symbol, rows in fetched.items()
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return fetched


def fetch_sp500_symbols() -> list[str]:
    return list(fetch_sp500_sectors())


def fetch_sp500_sectors() -> dict[str, str]:
    parser = Sp500Parser()
    request = Request(SP500_WIKI_URL, headers={"User-Agent": "portfolio-tool-backtest/0.1"})
    with urlopen(request, timeout=30) as response:
        parser.feed(response.read().decode("utf-8", errors="ignore"))
    return parser.sectors


class Sp500Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.in_cell = False
        self.cell_index = -1
        self.current_cell = ""
        self.current_row: list[str] = []
        self.symbols: list[str] = []
        self.sectors: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs = dict(attrs)
        if tag == "table" and "wikitable" in attrs.get("class", "") and not self.symbols:
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.cell_index = -1
            self.current_row = []
        elif self.in_table and tag in {"td", "th"}:
            self.in_cell = True
            self.current_cell = ""
            self.cell_index += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self.in_table:
            self.in_table = False
        elif tag == "tr" and self.in_table:
            if len(self.current_row) >= 3:
                symbol = self.current_row[0].strip().upper()
                sector = self.current_row[2].strip()
                if symbol and symbol != "SYMBOL" and 1 <= len(symbol) <= 8:
                    self.symbols.append(symbol)
                    self.sectors[symbol] = sector or "Unknown"
        elif tag in {"td", "th"}:
            if self.in_table and self.in_cell:
                self.current_row.append(" ".join(self.current_cell.split()))
            self.in_cell = False

    def handle_data(self, data: str) -> None:
        if self.in_table and self.in_cell:
            self.current_cell += data


def load_symbols(path: str) -> list[str]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return [row["symbol"].strip().upper() for row in rows if row.get("symbol")]


def common_calendar(bars: dict[str, list[PriceBar]]) -> list[date]:
    counts: dict[date, int] = {}
    for series in bars.values():
        for bar in series:
            counts[bar.day] = counts.get(bar.day, 0) + 1
    threshold = max(2, round(len(bars) * 0.20))
    return sorted(day for day, count in counts.items() if count >= threshold)


def price_table(bars: dict[str, list[PriceBar]]) -> dict[str, dict[date, float]]:
    return {symbol: {bar.day: bar.close for bar in series} for symbol, series in bars.items()}


def buy_and_hold_return(series: list[PriceBar], days: list[date]) -> float:
    prices = {bar.day: bar.close for bar in series}
    valid = [prices[day] for day in days if day in prices]
    if len(valid) < 2 or valid[0] == 0:
        return 0.0
    return valid[-1] / valid[0] - 1.0


def max_drawdown(values: list[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            worst = min(worst, value / peak - 1.0)
    return worst


def sharpe_ratio(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    sigma = statistics.pstdev(returns)
    if sigma == 0:
        return 0.0
    return statistics.mean(returns) / sigma * math.sqrt(252)


def write_summary(
    path: Path,
    result: BacktestResult,
    start: date,
    end: date,
    symbol_count: int,
    train_days: int,
    test_days: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "start",
            "end",
            "symbols",
            "train_days",
            "test_days",
            "strategy_book",
            "rebalance_every",
            "min_score",
            "max_positions",
            "stop_loss",
            "take_profit",
            "regime_filter",
            "volatility_target",
            "sector_cap",
            "correlation_cap",
            "drawdown_throttle",
            "train_return",
            "test_return",
            "benchmark_return",
            "excess_return",
            "max_drawdown",
            "sharpe",
            "win_rate",
            "rebalance_count",
            "trade_count",
            "profit_factor",
            "average_r",
            "sample_warning",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "symbols": symbol_count,
                "train_days": train_days,
                "test_days": test_days,
                "strategy_book": result.strategy_book,
                "rebalance_every": result.rebalance_every,
                "min_score": result.params.min_score,
                "max_positions": result.params.max_positions,
                "stop_loss": result.params.stop_loss,
                "take_profit": result.params.take_profit,
                "regime_filter": result.params.regime_filter,
                "volatility_target": result.params.volatility_target,
                "sector_cap": result.params.sector_cap,
                "correlation_cap": result.params.correlation_cap,
                "drawdown_throttle": result.params.drawdown_throttle,
                "train_return": f"{result.train_return:.6f}",
                "test_return": f"{result.test_return:.6f}",
                "benchmark_return": f"{result.benchmark_return:.6f}",
                "excess_return": f"{result.excess_return:.6f}",
                "max_drawdown": f"{result.max_drawdown:.6f}",
                "sharpe": f"{result.sharpe:.6f}",
                "win_rate": f"{result.win_rate:.6f}",
                "rebalance_count": result.rebalance_count,
                "trade_count": result.trade_count,
                "profit_factor": f"{result.profit_factor:.6f}",
                "average_r": f"{result.average_r:.6f}",
                "sample_warning": result.sample_warning,
            }
        )


def write_equity_curve(path: Path, rows: list[dict[str, float | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "equity"])
        writer.writeheader()
        for row in rows:
            if row["symbol"] == "__EQUITY__":
                writer.writerow({"date": row["date"], "equity": row["action"]})


def write_trades(path: Path, rows: list[dict[str, float | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "symbol", "score", "action"])
        writer.writeheader()
        writer.writerows([row for row in rows if row["symbol"] != "__EQUITY__"])


def print_summary(
    result: BacktestResult,
    start: date,
    end: date,
    symbol_count: int,
    train_days: int,
    test_days: int,
) -> None:
    print(f"Backtest window: {start} to {end}")
    print(f"Symbols with data: {symbol_count}; train days={train_days}; test days={test_days}")
    print(f"Strategy book: {result.strategy_book}; rebalance_every={result.rebalance_every}")
    print(
        "Best train params: "
        f"min_score={result.params.min_score}, max_positions={result.params.max_positions}, "
        f"stop_loss={result.params.stop_loss:.0%}, take_profit={result.params.take_profit:.0%}, "
        f"regime_filter={result.params.regime_filter}, vol_target={result.params.volatility_target:.0%}, "
        f"sector_cap={result.params.sector_cap:.0%}, corr_cap={result.params.correlation_cap:.0%}, "
        f"drawdown_throttle={result.params.drawdown_throttle}"
    )
    print(f"Train return: {result.train_return:.2%}")
    print(f"Test return: {result.test_return:.2%}")
    print(f"SPY benchmark return: {result.benchmark_return:.2%}")
    print(f"Excess return: {result.excess_return:.2%}")
    print(f"Max drawdown: {result.max_drawdown:.2%}")
    print(
        f"Sharpe: {result.sharpe:.2f}; win rate: {result.win_rate:.2%}; "
        f"trades={result.trade_count}; profit_factor={result.profit_factor:.2f}; "
        f"avg_R={result.average_r:.2f}; sample={result.sample_warning}"
    )


if __name__ == "__main__":
    try:
        main()
    except (AlpacaApiError, AlpacaConfigError) as exc:
        raise SystemExit(str(exc)) from exc
