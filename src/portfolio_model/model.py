from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import mean, pstdev


@dataclass(frozen=True)
class EquityInput:
    symbol: str
    industry: str
    price: float
    pe: float
    pb: float
    fcf_yield: float
    revenue_yoy: float
    eps_yoy: float
    gross_margin: float
    debt_to_equity: float
    sentiment: float
    sentiment_confidence: float
    current_weight: float = 0.0
    holding_days: int = 0
    market_cap: float = 0.0
    free_cash_flow: float = 0.0
    dcf_score: float = 0.5
    dcf_margin_safety: float = 0.0
    dcf_confidence: float = 0.0
    dcf_intrinsic_value: float = 0.0
    dcf_reason: str = ""
    forward_pe: float = 0.0
    forward_eps_yoy: float = 0.0
    forward_eps_revision_3m: float = 0.0


@dataclass(frozen=True)
class ModelConfig:
    value_weight: float = 0.34
    growth_weight: float = 0.25
    quality_weight: float = 0.18
    sentiment_weight: float = 0.05
    dcf_weight: float = 0.18
    buy_threshold: float = 0.62
    sell_threshold: float = 0.38
    trim_threshold: float = 0.46
    min_holding_days: int = 45
    max_position_weight: float = 0.12
    max_industry_weight: float = 0.35
    rebalance_buffer: float = 0.015


@dataclass(frozen=True)
class ScoreBreakdown:
    symbol: str
    value: float
    growth: float
    quality: float
    sentiment: float
    composite: float
    target_weight: float
    dcf: float = 0.5
    dcf_margin_safety: float = 0.0
    dcf_confidence: float = 0.0
    dcf_intrinsic_value: float = 0.0
    dcf_reason: str = ""


@dataclass(frozen=True)
class PortfolioDecision:
    symbol: str
    action: str
    score: ScoreBreakdown
    current_weight: float
    target_weight: float
    rationale: str


class PortfolioModel:
    """Cross-sectional equity model for deliberate, medium-horizon decisions."""

    def __init__(self, config: ModelConfig | None = None) -> None:
        self.config = config or ModelConfig()

    def score_universe(self, universe: list[EquityInput]) -> list[ScoreBreakdown]:
        if not universe:
            return []

        industry_groups = self._group_by_industry(universe)
        raw_scores = []
        for equity in universe:
            peers = industry_groups[equity.industry]
            value = self._value_score(equity, peers)
            growth = self._growth_score(equity, peers)
            quality = self._quality_score(equity, peers)
            sentiment = self._sentiment_score(equity)
            dcf = self._dcf_score(equity)
            composite = (
                self.config.value_weight * value
                + self.config.growth_weight * growth
                + self.config.quality_weight * quality
                + self.config.sentiment_weight * sentiment
                + self.config.dcf_weight * dcf
            )
            raw_scores.append((equity, value, growth, quality, sentiment, dcf, composite))

        target_weights = self._target_weights(raw_scores)
        return [
            ScoreBreakdown(
                symbol=equity.symbol,
                value=round(value, 4),
                growth=round(growth, 4),
                quality=round(quality, 4),
                sentiment=round(sentiment, 4),
                composite=round(composite, 4),
                target_weight=round(target_weights[equity.symbol], 4),
                dcf=round(dcf, 4),
                dcf_margin_safety=round(equity.dcf_margin_safety, 4),
                dcf_confidence=round(equity.dcf_confidence, 4),
                dcf_intrinsic_value=round(equity.dcf_intrinsic_value, 4),
                dcf_reason=equity.dcf_reason,
            )
            for equity, value, growth, quality, sentiment, dcf, composite in raw_scores
        ]

    def decide(self, universe: list[EquityInput]) -> list[PortfolioDecision]:
        scores = {score.symbol: score for score in self.score_universe(universe)}
        decisions = []
        for equity in universe:
            score = scores[equity.symbol]
            action = self._action(equity, score)
            decisions.append(
                PortfolioDecision(
                    symbol=equity.symbol,
                    action=action,
                    score=score,
                    current_weight=round(equity.current_weight, 4),
                    target_weight=score.target_weight,
                    rationale=self._rationale(equity, score, action),
                )
            )
        return sorted(decisions, key=lambda item: item.score.composite, reverse=True)

    def _value_score(self, equity: EquityInput, peers: list[EquityInput]) -> float:
        pe = self._relative_inverse_score(equity.pe, [p.pe for p in peers])
        forward_pe = self._forward_pe_score(equity, peers)
        pb = self._relative_inverse_score(equity.pb, [p.pb for p in peers])
        fcf = self._relative_score(equity.fcf_yield, [p.fcf_yield for p in peers])
        if equity.forward_pe > 0:
            return self._clamp(0.20 * pe + 0.30 * forward_pe + 0.15 * pb + 0.35 * fcf)
        return self._clamp(0.40 * pe + 0.20 * pb + 0.40 * fcf)

    def _forward_pe_score(self, equity: EquityInput, peers: list[EquityInput]) -> float:
        valid_forward_peers = [p.forward_pe for p in peers if p.forward_pe > 0]
        if equity.forward_pe <= 0 or len(valid_forward_peers) < 2:
            return 0.5
        cheapness = self._relative_inverse_score(equity.forward_pe, valid_forward_peers)
        revision_support = self._clamp(0.5 + equity.forward_eps_revision_3m * 5.0)
        growth_support = self._clamp(0.5 + equity.forward_eps_yoy)
        return self._clamp(0.65 * cheapness + 0.20 * revision_support + 0.15 * growth_support)

    def _growth_score(self, equity: EquityInput, peers: list[EquityInput]) -> float:
        revenue = self._relative_score(equity.revenue_yoy, [p.revenue_yoy for p in peers])
        eps = self._relative_score(equity.eps_yoy, [p.eps_yoy for p in peers])
        return self._clamp(0.45 * revenue + 0.55 * eps)

    def _quality_score(self, equity: EquityInput, peers: list[EquityInput]) -> float:
        margin = self._relative_score(equity.gross_margin, [p.gross_margin for p in peers])
        leverage = self._relative_inverse_score(equity.debt_to_equity, [p.debt_to_equity for p in peers])
        return self._clamp(0.60 * margin + 0.40 * leverage)

    def _sentiment_score(self, equity: EquityInput) -> float:
        confidence = self._clamp(equity.sentiment_confidence)
        normalized = (self._clamp(equity.sentiment, -1.0, 1.0) + 1.0) / 2.0
        return self._clamp(0.50 + (normalized - 0.50) * confidence)

    def _dcf_score(self, equity: EquityInput) -> float:
        confidence = self._clamp(equity.dcf_confidence)
        return self._clamp(0.50 + (self._clamp(equity.dcf_score) - 0.50) * confidence)

    def _action(self, equity: EquityInput, score: ScoreBreakdown) -> str:
        delta = score.target_weight - equity.current_weight
        locked = equity.current_weight > 0 and equity.holding_days < self.config.min_holding_days

        if locked and score.composite > self.config.sell_threshold:
            return "HOLD"
        if equity.current_weight <= 0 and score.composite >= self.config.buy_threshold:
            return "BUY"
        if equity.current_weight <= 0 and score.composite >= self.config.trim_threshold:
            return "WATCH"
        if equity.current_weight <= 0:
            return "PASS"
        if equity.current_weight > 0 and score.composite <= self.config.sell_threshold:
            return "SELL"
        if equity.current_weight > 0 and score.composite <= self.config.trim_threshold:
            return "TRIM"
        if delta > self.config.rebalance_buffer and score.composite >= self.config.buy_threshold:
            return "ADD"
        if delta < -self.config.rebalance_buffer:
            return "TRIM"
        return "HOLD"

    def _rationale(self, equity: EquityInput, score: ScoreBreakdown, action: str) -> str:
        leaders = sorted(
            [
                ("value", score.value),
                ("growth", score.growth),
                ("quality", score.quality),
                ("sentiment", score.sentiment),
                ("DCF", score.dcf),
            ],
            key=lambda item: item[1],
            reverse=True,
        )
        best = ", ".join(name for name, _ in leaders[:2])
        holding_note = ""
        if equity.current_weight > 0 and equity.holding_days < self.config.min_holding_days:
            holding_note = f" Minimum holding period still active at {equity.holding_days} days."
        return (
            f"{action} from composite {score.composite:.2f}; strongest inputs are {best}. "
            f"Target weight {score.target_weight:.1%} versus current {equity.current_weight:.1%}. "
            f"DCF margin of safety {score.dcf_margin_safety:.1%}. {score.dcf_reason}"
            f"{holding_note}"
        )

    def _target_weights(self, raw_scores: list[tuple[EquityInput, float, float, float, float, float, float]]) -> dict[str, float]:
        eligible = [(equity, max(composite - self.config.sell_threshold, 0.0)) for equity, *_, composite in raw_scores]
        total_edge = sum(edge for _, edge in eligible)
        if total_edge == 0:
            return {equity.symbol: 0.0 for equity, *_ in raw_scores}

        unconstrained = {
            equity.symbol: min(edge / total_edge, self.config.max_position_weight)
            for equity, edge in eligible
        }
        by_symbol = {equity.symbol: equity for equity, *_ in raw_scores}
        return self._apply_industry_caps(unconstrained, by_symbol)

    def _apply_industry_caps(self, weights: dict[str, float], by_symbol: dict[str, EquityInput]) -> dict[str, float]:
        capped = dict(weights)
        for industry in {equity.industry for equity in by_symbol.values()}:
            members = [symbol for symbol, equity in by_symbol.items() if equity.industry == industry]
            industry_weight = sum(capped[symbol] for symbol in members)
            if industry_weight > self.config.max_industry_weight:
                scale = self.config.max_industry_weight / industry_weight
                for symbol in members:
                    capped[symbol] *= scale
        return capped

    @staticmethod
    def _group_by_industry(universe: list[EquityInput]) -> dict[str, list[EquityInput]]:
        groups: dict[str, list[EquityInput]] = {}
        for equity in universe:
            groups.setdefault(equity.industry, []).append(equity)
        return groups

    def _relative_score(self, value: float, values: list[float]) -> float:
        return self._percentile_from_z(self._z_score(value, values))

    def _relative_inverse_score(self, value: float, values: list[float]) -> float:
        return 1.0 - self._relative_score(value, values)

    @staticmethod
    def _z_score(value: float, values: list[float]) -> float:
        clean = [item for item in values if isfinite(item)]
        if len(clean) < 2:
            return 0.0
        sigma = pstdev(clean)
        if sigma == 0:
            return 0.0
        return (value - mean(clean)) / sigma

    def _percentile_from_z(self, z_score: float) -> float:
        return self._clamp(0.5 + z_score / 6.0)

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))
