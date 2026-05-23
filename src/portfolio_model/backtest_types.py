from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PriceBar:
    day: date
    close: float


@dataclass(frozen=True)
class StrategyFeatures:
    momentum_12m: float
    momentum_6m: float
    momentum_3m: float
    drawdown: float
    volatility: float
    reward_to_risk: float


@dataclass(frozen=True)
class ForwardEstimate:
    day: date
    symbol: str
    sector: str
    forward_pe: float
    forward_eps_yoy: float
    forward_eps_revision_3m: float
    fcf_yield: float = 0.0
    debt_to_equity: float = 0.0


@dataclass(frozen=True)
class AgentParams:
    min_score: float
    max_positions: int
    stop_loss: float
    take_profit: float
    regime_filter: bool = True
    volatility_target: float = 0.18
    sector_cap: float = 1.0
    correlation_cap: float = 1.0
    drawdown_throttle: bool = False


@dataclass(frozen=True)
class BacktestResult:
    strategy_book: str
    rebalance_every: int
    params: AgentParams
    train_return: float
    test_return: float
    benchmark_return: float
    excess_return: float
    max_drawdown: float
    sharpe: float
    win_rate: float
    rebalance_count: int
    trade_count: int = 0
    profit_factor: float = 0.0
    average_r: float = 0.0
    sample_warning: str = ""


STRATEGY_BOOKS = (
    "metric_priority",
    "quality_compounder",
    "value_reversion",
    "momentum_breakout",
    "forward_pe_value",
)
