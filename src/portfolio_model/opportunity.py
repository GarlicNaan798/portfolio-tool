from __future__ import annotations

from portfolio_model.model import PortfolioDecision

VALUE_GROWTH_WEIGHT = 0.32
GROWTH_QUALITY_WEIGHT = 0.27
QUALITY_WEIGHT = 0.21
DCF_WEIGHT = 0.15
SENTIMENT_WEIGHT = 0.05


def opportunity_components(decision: PortfolioDecision) -> dict[str, float]:
    upside = 0.55 * decision.score.value + 0.45 * decision.score.growth
    promise = 0.55 * decision.score.growth + 0.45 * decision.score.quality
    sentiment = decision.score.sentiment
    dcf = getattr(decision.score, "dcf", 0.5)
    quality_adjustment = 0.90 + 0.20 * decision.score.quality
    financial_score = (
        VALUE_GROWTH_WEIGHT * upside
        + GROWTH_QUALITY_WEIGHT * promise
        + QUALITY_WEIGHT * decision.score.quality
        + DCF_WEIGHT * dcf
    )
    raw_score = 10.0 * (
        financial_score
        + SENTIMENT_WEIGHT * sentiment
    )
    quality_adjusted_score = raw_score * quality_adjustment
    return {
        "upside": upside,
        "promise": promise,
        "financial": financial_score,
        "sentiment": sentiment,
        "dcf": dcf,
        "quality_adjustment": quality_adjustment,
        "raw_score": raw_score,
        "quality_adjusted_score": quality_adjusted_score,
    }


def opportunity_score(decision: PortfolioDecision) -> float:
    return round(min(10.0, opportunity_components(decision)["quality_adjusted_score"]), 4)


def predicted_return_pct(decision: PortfolioDecision, hurdle_score: float = 5.0) -> float:
    score = opportunity_score(decision)
    edge = max(0.0, score - hurdle_score)
    return round(min(0.35, edge * 0.035), 4)


def predicted_profit(notional: float, decision: PortfolioDecision) -> float:
    return round(notional * predicted_return_pct(decision), 2)
