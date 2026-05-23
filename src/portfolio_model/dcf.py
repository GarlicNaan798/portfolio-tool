from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class DcfAssumptions:
    forecast_years: int = 5
    discount_rate: float = 0.10
    terminal_growth: float = 0.025
    base_growth: float = 0.04


@dataclass(frozen=True)
class DcfResult:
    intrinsic_value_per_share: float
    margin_of_safety: float
    score: float
    confidence: float
    reason: str


def build_dcf(
    *,
    price: float,
    revenue_yoy: float,
    eps_yoy: float,
    debt_to_equity: float,
    market_cap: float = 0.0,
    free_cash_flow: float = 0.0,
    fcf_yield: float = 0.0,
    assumptions: DcfAssumptions | None = None,
) -> DcfResult:
    assumptions = assumptions or DcfAssumptions()
    if price <= 0:
        return _empty("DCF unavailable: missing market price")

    normalized_fcf = free_cash_flow
    if normalized_fcf == 0 and market_cap > 0 and fcf_yield:
        normalized_fcf = market_cap * fcf_yield
    if market_cap <= 0 or normalized_fcf == 0:
        return _empty("DCF unavailable: missing market cap or free cash flow")

    shares = market_cap / price
    if shares <= 0:
        return _empty("DCF unavailable: invalid share count estimate")

    growth_signal = _clamp(0.55 * revenue_yoy + 0.45 * eps_yoy, -0.05, 0.18)
    forecast_growth = _clamp(0.50 * assumptions.base_growth + 0.50 * growth_signal, -0.02, 0.14)
    discount_rate = _clamp(assumptions.discount_rate + max(0.0, debt_to_equity - 0.5) * 0.015, 0.08, 0.16)
    terminal_growth = min(assumptions.terminal_growth, discount_rate - 0.025)

    present_value = 0.0
    cash_flow = normalized_fcf
    for year in range(1, assumptions.forecast_years + 1):
        fade = 1.0 - (year - 1) / max(1, assumptions.forecast_years)
        year_growth = terminal_growth + (forecast_growth - terminal_growth) * fade
        cash_flow *= 1.0 + year_growth
        present_value += cash_flow / ((1.0 + discount_rate) ** year)

    terminal_cash_flow = cash_flow * (1.0 + terminal_growth)
    terminal_value = terminal_cash_flow / max(0.001, discount_rate - terminal_growth)
    present_value += terminal_value / ((1.0 + discount_rate) ** assumptions.forecast_years)

    intrinsic = present_value / shares
    margin = intrinsic / price - 1.0
    score = _clamp(0.50 + margin / 1.50)
    confidence = _confidence(normalized_fcf, market_cap, revenue_yoy, eps_yoy)
    reason = (
        f"DCF margin {margin:.1%}, intrinsic ${intrinsic:.2f}, "
        f"growth {forecast_growth:.1%}, discount {discount_rate:.1%}"
    )
    return DcfResult(
        intrinsic_value_per_share=round(intrinsic, 4),
        margin_of_safety=round(margin, 4),
        score=round(score, 4),
        confidence=round(confidence, 4),
        reason=reason,
    )


def _confidence(free_cash_flow: float, market_cap: float, revenue_yoy: float, eps_yoy: float) -> float:
    confidence = 0.55
    if free_cash_flow > 0:
        confidence += 0.20
    if market_cap > 0:
        confidence += 0.10
    if isfinite(revenue_yoy) and isfinite(eps_yoy):
        confidence += 0.15
    return _clamp(confidence)


def _empty(reason: str) -> DcfResult:
    return DcfResult(
        intrinsic_value_per_share=0.0,
        margin_of_safety=0.0,
        score=0.5,
        confidence=0.0,
        reason=reason,
    )


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
