from __future__ import annotations

import csv
import math
import statistics
from datetime import date
from pathlib import Path

from portfolio_model.backtest_types import ForwardEstimate, PriceBar, StrategyFeatures


def rank_symbols(
    symbols: list[str],
    bars: dict[str, list[PriceBar]],
    prices: dict[str, dict[date, float]],
    day: date,
    *,
    strategy_book: str = "metric_priority",
    sectors: dict[str, str] | None = None,
    forward_estimates: dict[str, list[ForwardEstimate]] | None = None,
) -> list[tuple[str, float]]:
    if strategy_book == "forward_pe_value":
        return rank_forward_pe_symbols(symbols, bars, day, sectors or {}, forward_estimates or {})
    ranked = []
    for symbol in symbols:
        features = strategy_features(bars[symbol], day)
        if features is None:
            continue
        score = strategy_score(strategy_book, features)
        ranked.append((symbol, clamp(score, 0.0, 10.0)))
    return sorted(ranked, key=lambda item: item[1], reverse=True)


def rank_forward_pe_symbols(
    symbols: list[str],
    bars: dict[str, list[PriceBar]],
    day: date,
    sectors: dict[str, str],
    forward_estimates: dict[str, list[ForwardEstimate]],
) -> list[tuple[str, float]]:
    rows = []
    for symbol in symbols:
        features = strategy_features(bars[symbol], day)
        estimate = latest_forward_estimate(forward_estimates, symbol, day)
        if features is None or estimate is None:
            continue
        sector = estimate.sector or sectors.get(symbol, "Unknown")
        rows.append((symbol, sector, features, estimate))

    by_sector: dict[str, list[ForwardEstimate]] = {}
    for _, sector, _, estimate in rows:
        by_sector.setdefault(sector, []).append(estimate)

    ranked = []
    for symbol, sector, features, estimate in rows:
        score = forward_pe_value_score(features, estimate, by_sector.get(sector, []))
        ranked.append((symbol, clamp(score, 0.0, 10.0)))
    return sorted(ranked, key=lambda item: item[1], reverse=True)


def strategy_features(series: list[PriceBar], day: date) -> StrategyFeatures | None:
    index = next((i for i, bar in enumerate(series) if bar.day == day), -1)
    if index < 252:
        return None
    close = series[index].close
    if close <= 0:
        return None
    momentum_12m = close / series[index - 252].close - 1.0
    momentum_6m = close / series[index - 126].close - 1.0
    momentum_3m = close / series[index - 63].close - 1.0
    drawdown = close / max(bar.close for bar in series[index - 252:index + 1]) - 1.0
    returns = [series[i].close / series[i - 1].close - 1.0 for i in range(index - 63, index + 1)]
    volatility = statistics.pstdev(returns) * math.sqrt(252) if len(returns) > 1 else 0.0
    reward_to_risk = (momentum_12m + max(momentum_3m, 0.0)) / max(volatility, 0.05)
    return StrategyFeatures(momentum_12m, momentum_6m, momentum_3m, drawdown, volatility, reward_to_risk)


def strategy_score(strategy_book: str, features: StrategyFeatures) -> float:
    if strategy_book == "quality_compounder":
        return quality_compounder_score(features)
    if strategy_book == "value_reversion":
        return value_reversion_score(features)
    if strategy_book == "momentum_breakout":
        return momentum_breakout_score(features)
    if strategy_book == "forward_pe_value":
        raise ValueError("forward_pe_value requires point-in-time forward estimate features")
    return metric_priority_score(features)


def forward_pe_value_score(
    features: StrategyFeatures,
    estimate: ForwardEstimate,
    sector_estimates: list[ForwardEstimate],
) -> float:
    valid_forward_pe = [item.forward_pe for item in sector_estimates if item.forward_pe > 0]
    valid_fcf = [item.fcf_yield for item in sector_estimates]
    valid_debt = [item.debt_to_equity for item in sector_estimates if item.debt_to_equity >= 0]
    if estimate.forward_pe <= 0 or len(valid_forward_pe) < 2:
        return 0.0

    cheapness = cross_sectional_inverse_score(estimate.forward_pe, valid_forward_pe)
    revision_support = clamp(0.50 + estimate.forward_eps_revision_3m * 5.0, 0.0, 1.0)
    growth_support = clamp(0.50 + estimate.forward_eps_yoy, 0.0, 1.0)
    fcf_support = cross_sectional_score(estimate.fcf_yield, valid_fcf) if valid_fcf else 0.5
    leverage_support = cross_sectional_inverse_score(estimate.debt_to_equity, valid_debt) if valid_debt else 0.5
    stabilization = (
        0.45 * sentiment_proxy_score(features)
        + 0.35 * (1.0 - clamp(abs(features.drawdown), 0.0, 0.35) / 0.35)
        + 0.20 * (1.0 - clamp(features.volatility, 0.0, 0.8) / 0.8)
    )
    trap_penalty = 0.0
    if estimate.forward_eps_revision_3m < -0.05:
        trap_penalty += 1.5
    if estimate.forward_eps_yoy < -0.20:
        trap_penalty += 1.0
    if estimate.fcf_yield < 0:
        trap_penalty += 1.0

    return 10.0 * (
        0.35 * cheapness
        + 0.20 * revision_support
        + 0.15 * growth_support
        + 0.15 * fcf_support
        + 0.10 * leverage_support
        + 0.05 * stabilization
    ) - trap_penalty


def metric_priority_score(features: StrategyFeatures) -> float:
    value_proxy = value_proxy_score(features)
    growth_proxy = growth_proxy_score(features)
    quality_proxy = quality_proxy_score(features)
    sentiment_proxy = sentiment_proxy_score(features)
    dcf_proxy = value_proxy
    return 10.0 * (
        0.34 * value_proxy
        + 0.25 * growth_proxy
        + 0.18 * quality_proxy
        + 0.05 * sentiment_proxy
        + 0.18 * dcf_proxy
    )


def quality_compounder_score(features: StrategyFeatures) -> float:
    steady_growth = 1.0 - abs(clamp(features.momentum_6m, -0.2, 0.35) - 0.16) / 0.55
    return 10.0 * (
        0.45 * quality_proxy_score(features)
        + 0.30 * growth_proxy_score(features)
        + 0.15 * steady_growth
        + 0.10 * (1.0 - clamp(abs(features.drawdown), 0.0, 0.35) / 0.35)
    )


def value_reversion_score(features: StrategyFeatures) -> float:
    constructive_turn = (clamp(features.momentum_3m, -0.10, 0.25) + 0.10) / 0.35
    not_broken = 1.0 - clamp(max(0.0, -features.momentum_12m - 0.20), 0.0, 0.50) / 0.50
    return 10.0 * (
        0.45 * value_proxy_score(features)
        + 0.25 * constructive_turn
        + 0.20 * not_broken
        + 0.10 * (1.0 - clamp(features.volatility, 0.0, 0.8) / 0.8)
    )


def momentum_breakout_score(features: StrategyFeatures) -> float:
    near_high = 1.0 - clamp(abs(features.drawdown), 0.0, 0.20) / 0.20
    return 10.0 * (
        0.40 * (clamp(features.momentum_6m, -0.10, 0.60) + 0.10) / 0.70
        + 0.30 * (clamp(features.momentum_3m, -0.05, 0.35) + 0.05) / 0.40
        + 0.20 * near_high
        + 0.10 * quality_proxy_score(features)
    )


def value_proxy_score(features: StrategyFeatures) -> float:
    return 0.55 * clamp(-features.drawdown, 0.0, 0.35) / 0.35 + 0.45 * (
        1.0 - clamp(features.volatility, 0.0, 0.8) / 0.8
    )


def growth_proxy_score(features: StrategyFeatures) -> float:
    return (
        0.45 * (clamp(features.momentum_12m, -0.4, 0.8) + 0.4) / 1.2
        + 0.35 * (clamp(features.momentum_6m, -0.3, 0.6) + 0.3) / 0.9
        + 0.20 * (clamp(features.momentum_3m, -0.25, 0.4) + 0.25) / 0.65
    )


def quality_proxy_score(features: StrategyFeatures) -> float:
    return 0.60 * (clamp(features.reward_to_risk, -1.0, 3.0) + 1.0) / 4.0 + 0.40 * (
        1.0 - clamp(features.volatility, 0.0, 0.8) / 0.8
    )


def sentiment_proxy_score(features: StrategyFeatures) -> float:
    return (clamp(features.momentum_3m, -0.25, 0.4) + 0.25) / 0.65


def strategy_min_scores(strategy_book: str) -> tuple[float, ...]:
    if strategy_book == "momentum_breakout":
        return (7.0, 7.5, 8.0)
    return (6.5, 7.0, 7.5)


def strategy_stop_losses(strategy_book: str) -> tuple[float, ...]:
    if strategy_book == "momentum_breakout":
        return (0.06, 0.08)
    if strategy_book == "value_reversion":
        return (0.08, 0.10, 0.12)
    return (0.06, 0.08, 0.10)


def strategy_take_profits(strategy_book: str) -> tuple[float, ...]:
    if strategy_book == "momentum_breakout":
        return (0.25, 0.35, 0.50)
    if strategy_book == "quality_compounder":
        return (0.35, 0.50)
    return (0.25, 0.35)


def load_forward_estimates(path: Path) -> dict[str, list[ForwardEstimate]]:
    if not path.exists():
        raise RuntimeError(f"Forward estimates file does not exist: {path}")
    estimates: dict[str, list[ForwardEstimate]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "symbol", "forward_pe", "forward_eps_yoy", "forward_eps_revision_3m"}
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise RuntimeError(f"Forward estimates file missing required columns: {', '.join(missing)}")
        for row in reader:
            symbol = str(row.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            estimate = ForwardEstimate(
                day=date.fromisoformat(str(row["date"])),
                symbol=symbol,
                sector=str(row.get("sector", "")).strip() or "Unknown",
                forward_pe=_float(row.get("forward_pe")),
                forward_eps_yoy=_float(row.get("forward_eps_yoy")),
                forward_eps_revision_3m=_float(row.get("forward_eps_revision_3m")),
                fcf_yield=_float(row.get("fcf_yield")),
                debt_to_equity=_float(row.get("debt_to_equity")),
            )
            estimates.setdefault(symbol, []).append(estimate)
    for rows in estimates.values():
        rows.sort(key=lambda item: item.day)
    return estimates


def validate_forward_estimates(forward_estimates: dict[str, list[ForwardEstimate]]) -> None:
    if not forward_estimates:
        raise RuntimeError("--strategy-book forward_pe_value requires --forward-estimates point-in-time CSV data.")
    usable = sum(1 for rows in forward_estimates.values() if any(item.forward_pe > 0 for item in rows))
    if usable < 20:
        raise RuntimeError("Forward estimate data is too sparse for a cross-sectional forward P/E backtest.")


def latest_forward_estimate(
    forward_estimates: dict[str, list[ForwardEstimate]],
    symbol: str,
    day: date,
) -> ForwardEstimate | None:
    rows = forward_estimates.get(symbol, [])
    latest = None
    for row in rows:
        if row.day <= day:
            latest = row
        else:
            break
    return latest


def cross_sectional_score(value: float, values: list[float]) -> float:
    clean = [item for item in values if math.isfinite(item)]
    if len(clean) < 2:
        return 0.5
    sigma = statistics.pstdev(clean)
    if sigma == 0:
        return 0.5
    return clamp(0.5 + (value - statistics.mean(clean)) / (6.0 * sigma), 0.0, 1.0)


def cross_sectional_inverse_score(value: float, values: list[float]) -> float:
    return 1.0 - cross_sectional_score(value, values)


def trailing_volatility(series: list[PriceBar], day: date, window: int = 63) -> float:
    index = next((i for i, bar in enumerate(series) if bar.day == day), -1)
    if index < window:
        return 0.30
    returns = [series[i].close / series[i - 1].close - 1.0 for i in range(index - window + 1, index + 1)]
    return statistics.pstdev(returns) * math.sqrt(252) if len(returns) > 1 else 0.30


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
