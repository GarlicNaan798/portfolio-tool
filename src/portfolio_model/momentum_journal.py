from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from portfolio_model.backtest import (
    PriceBar,
    clamp,
    quality_proxy_score,
    strategy_features,
    trailing_volatility,
)


DECISION_JOURNAL_FIELDS = [
    "run_date",
    "signal_date",
    "agent",
    "symbol",
    "rank",
    "sector",
    "decision",
    "reason",
    "regime_on",
    "spy_close",
    "spy_ma50",
    "spy_ma200",
    "spy_3m_momentum",
    "score",
    "score_formula",
    "momentum_12m",
    "momentum_6m",
    "momentum_3m",
    "drawdown",
    "volatility",
    "reward_to_risk",
    "mom6_component",
    "mom3_component",
    "near_high_component",
    "quality_component",
    "weighted_mom6",
    "weighted_mom3",
    "weighted_near_high",
    "weighted_quality",
    "min_score",
    "max_positions",
    "sector_cap",
    "effective_sector_cap",
    "correlation_cap",
    "volatility_target",
    "risk_weight_formula",
    "trailing_volatility_for_weight",
    "raw_weight_numerator",
    "strategy_sleeve_weight",
    "plan_action",
    "target_notional",
    "current_notional",
    "delta_notional",
    "order_status",
    "order_id",
    "order_reason",
]


def build_decision_journal(
    ranked: list[tuple[str, float]],
    *,
    selected_symbols: set[str],
    weights: dict[str, float],
    bars: dict[str, list[PriceBar]],
    sectors: dict[str, str],
    signal_date: date,
    run_date: date,
    regime: dict[str, str],
    context: dict[str, float],
    max_rows: int,
) -> list[dict[str, str]]:
    rows = []
    selected_count_by_sector = selected_sector_counts(selected_symbols, sectors)
    for rank, (symbol, score) in enumerate(ranked[:max_rows], start=1):
        features = strategy_features(bars[symbol], signal_date)
        if features is None:
            continue
        rows.append(
            decision_journal_row(
                symbol=symbol,
                rank=rank,
                score=score,
                selected=symbol in selected_symbols,
                weight=weights.get(symbol, 0.0),
                bars=bars,
                sectors=sectors,
                signal_date=signal_date,
                run_date=run_date,
                regime=regime,
                context=context,
                selected_count_by_sector=selected_count_by_sector,
            )
        )
    if not rows:
        rows.append(empty_decision_journal_row(run_date, signal_date, regime, "No ranked symbols; regime may be off."))
    return rows


def decision_journal_row(
    *,
    symbol: str,
    rank: int,
    score: float,
    selected: bool,
    weight: float,
    bars: dict[str, list[PriceBar]],
    sectors: dict[str, str],
    signal_date: date,
    run_date: date,
    regime: dict[str, str],
    context: dict[str, float],
    selected_count_by_sector: dict[str, int],
) -> dict[str, str]:
    features = strategy_features(bars[symbol], signal_date)
    if features is None:
        raise ValueError(f"No strategy features for {symbol} on {signal_date}")
    components = momentum_score_components(features)
    sector = sectors.get(symbol, "Unknown")
    vol = trailing_volatility(bars[symbol], signal_date)
    raw_weight_numerator = max(score - 5.0, 0.01) / max(vol, 0.08)
    return {
        "run_date": run_date.isoformat(),
        "signal_date": signal_date.isoformat(),
        "agent": "momentum_breakout",
        "symbol": symbol,
        "rank": str(rank),
        "sector": sector,
        "decision": "SELECTED" if selected else "REJECTED",
        "reason": selection_reason(
            rank=rank,
            score=score,
            selected=selected,
            sector=sector,
            selected_count_by_sector=selected_count_by_sector,
            context=context,
        ),
        "regime_on": regime.get("regime_on", ""),
        "spy_close": regime.get("spy_close", ""),
        "spy_ma50": regime.get("spy_ma50", ""),
        "spy_ma200": regime.get("spy_ma200", ""),
        "spy_3m_momentum": regime.get("spy_3m_momentum", ""),
        "score": f"{score:.4f}",
        "score_formula": (
            "10*(0.40*mom6_component + 0.30*mom3_component + "
            "0.20*near_high_component + 0.10*quality_component)"
        ),
        "momentum_12m": f"{features.momentum_12m:.4f}",
        "momentum_6m": f"{features.momentum_6m:.4f}",
        "momentum_3m": f"{features.momentum_3m:.4f}",
        "drawdown": f"{features.drawdown:.4f}",
        "volatility": f"{features.volatility:.4f}",
        "reward_to_risk": f"{features.reward_to_risk:.4f}",
        "mom6_component": f"{components['mom6_component']:.4f}",
        "mom3_component": f"{components['mom3_component']:.4f}",
        "near_high_component": f"{components['near_high_component']:.4f}",
        "quality_component": f"{components['quality_component']:.4f}",
        "weighted_mom6": f"{components['weighted_mom6']:.4f}",
        "weighted_mom3": f"{components['weighted_mom3']:.4f}",
        "weighted_near_high": f"{components['weighted_near_high']:.4f}",
        "weighted_quality": f"{components['weighted_quality']:.4f}",
        "min_score": f"{context['min_score']:.4f}",
        "max_positions": f"{context['max_positions']:.0f}",
        "sector_cap": f"{context['sector_cap']:.4f}",
        "effective_sector_cap": f"{context['effective_sector_cap']:.4f}",
        "correlation_cap": f"{context['correlation_cap']:.4f}",
        "volatility_target": f"{context['volatility_target']:.4f}",
        "risk_weight_formula": "max(score-5,0.01)/max(trailing_volatility,0.08), normalized to volatility target",
        "trailing_volatility_for_weight": f"{vol:.4f}",
        "raw_weight_numerator": f"{raw_weight_numerator:.6f}",
        "strategy_sleeve_weight": f"{weight:.4f}",
        "plan_action": "",
        "target_notional": "",
        "current_notional": "",
        "delta_notional": "",
        "order_status": "",
        "order_id": "",
        "order_reason": "",
    }


def selected_sector_counts(selected_symbols: set[str], sectors: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for symbol in selected_symbols:
        sector = sectors.get(symbol, "Unknown")
        counts[sector] = counts.get(sector, 0) + 1
    return counts


def momentum_score_components(features) -> dict[str, float]:
    mom6 = (clamp(features.momentum_6m, -0.10, 0.60) + 0.10) / 0.70
    mom3 = (clamp(features.momentum_3m, -0.05, 0.35) + 0.05) / 0.40
    near_high = 1.0 - clamp(abs(features.drawdown), 0.0, 0.20) / 0.20
    quality = quality_proxy_score(features)
    return {
        "mom6_component": mom6,
        "mom3_component": mom3,
        "near_high_component": near_high,
        "quality_component": quality,
        "weighted_mom6": 0.40 * mom6,
        "weighted_mom3": 0.30 * mom3,
        "weighted_near_high": 0.20 * near_high,
        "weighted_quality": 0.10 * quality,
    }


def selection_reason(
    *,
    rank: int,
    score: float,
    selected: bool,
    sector: str,
    selected_count_by_sector: dict[str, int],
    context: dict[str, float],
) -> str:
    if selected:
        return "Selected: passed regime gate, min score, max positions, sector/correlation filters, and risk sizing."
    if score < context["min_score"]:
        return f"Rejected: score {score:.2f} below min_score {context['min_score']:.2f}."
    if rank > context["max_positions"]:
        sector_note = ""
        if context["effective_sector_cap"] < 1.0 and selected_count_by_sector.get(sector, 0) > 0:
            sector_note = f" Sector {sector} already represented among selected names."
        return f"Rejected: rank {rank} outside max_positions {context['max_positions']:.0f}.{sector_note}"
    return "Rejected by diversification filters or duplicate exposure grouping."


def merge_plan_into_journal(journal_rows: list[dict[str, str]], plan_rows: list[dict[str, str]]) -> None:
    plan_by_symbol = {row.get("symbol", ""): row for row in plan_rows}
    for row in journal_rows:
        plan = plan_by_symbol.get(row.get("symbol", ""))
        if not plan:
            continue
        row["plan_action"] = plan.get("action", "")
        row["target_notional"] = plan.get("target_notional", "")
        row["current_notional"] = plan.get("current_notional", "")
        row["delta_notional"] = plan.get("delta_notional", "")


def merge_orders_into_journal(journal_rows: list[dict[str, str]], order_rows: list[dict[str, str]]) -> None:
    orders_by_symbol = {row.get("symbol", ""): row for row in order_rows}
    for row in journal_rows:
        order = orders_by_symbol.get(row.get("symbol", ""))
        if not order:
            continue
        row["order_status"] = order.get("status", "")
        row["order_id"] = order.get("order_id", "")
        row["order_reason"] = order.get("reason", "")


def empty_decision_journal_row(run_date: date, signal_date: date, regime: dict[str, str], reason: str) -> dict[str, str]:
    return {field: "" for field in DECISION_JOURNAL_FIELDS} | {
        "run_date": run_date.isoformat(),
        "signal_date": signal_date.isoformat(),
        "agent": "momentum_breakout",
        "decision": "NO_ACTION",
        "reason": reason,
        "regime_on": regime.get("regime_on", ""),
        "spy_close": regime.get("spy_close", ""),
        "spy_ma50": regime.get("spy_ma50", ""),
        "spy_ma200": regime.get("spy_ma200", ""),
        "spy_3m_momentum": regime.get("spy_3m_momentum", ""),
    }


def write_decision_journal(output_dir: Path, rows: list[dict[str, str]], run_date: date) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"momentum_decision_journal_{run_date.isoformat().replace('-', '')}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DECISION_JOURNAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path
