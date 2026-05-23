from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from portfolio_model.alpaca import AlpacaApiError, AlpacaClient, AlpacaConfigError
from portfolio_model.model import PortfolioDecision
from portfolio_model.opportunity import opportunity_score, predicted_profit, predicted_return_pct


EXECUTION_ACTIONS = {"BUY", "ADD"}


@dataclass(frozen=True)
class ExecutionPlanRow:
    agent: str
    agent_name: str
    industry: str
    symbol: str
    action: str
    source_action: str
    opportunity_score: float
    target_weight: float
    current_weight: float
    notional: float
    status: str
    reason: str
    predicted_return_pct: float
    predicted_profit: float
    cash: float = 0.0
    buying_power: float = 0.0
    equity: float = 0.0
    allocation_note: str = ""


@dataclass(frozen=True)
class AccountCapital:
    cash: float
    buying_power: float
    equity: float
    long_market_value: float
    short_market_value: float

    @property
    def liquid_capital(self) -> float:
        return self.buying_power or self.cash


def build_execution_plan(
    decisions: list[PortfolioDecision],
    *,
    account: dict,
    max_trade_notional: float,
    min_opportunity_score: float,
    buying_power_fraction: float,
    quality_bias: float = 1.5,
    max_approved_trades: int = 5,
) -> list[ExecutionPlanRow]:
    capital = account_capital(account)
    budget = max(0.0, capital.liquid_capital * buying_power_fraction)
    trade_cap = conviction_trade_cap(account, {"max_trade_notional": max_trade_notional})
    candidates = []
    rejected = []
    for decision in decisions:
        score = opportunity_score(decision)
        if decision.action not in EXECUTION_ACTIONS:
            rejected.append(_row(decision, score, 0.0, "REJECTED", f"action {decision.action} is not executable buy/add"))
            continue
        if score < min_opportunity_score:
            rejected.append(_row(decision, score, 0.0, "REJECTED", "opportunity score below execution threshold"))
            continue
        edge = max(score - min_opportunity_score, 0.01) ** quality_bias
        candidates.append((decision, score, edge))

    total_edge = sum(edge for _, _, edge in candidates)
    approved = []
    for index, (decision, score, edge) in enumerate(sorted(candidates, key=lambda item: item[2], reverse=True), start=1):
        if index > max_approved_trades:
            rejected.append(_row(decision, score, 0.0, "REJECTED", "lower expected-profit rank than approved trade cap"))
            continue
        allocation = budget * edge / total_edge if total_edge else 0.0
        notional = min(allocation, trade_cap)
        status = "APPROVED" if notional >= 1 else "REJECTED"
        note = allocation_note(capital, trade_cap)
        reason = f"validated by execution coordinator; {note}" if status == "APPROVED" else "allocation below $1"
        approved.append(_row(decision, score, notional, status, reason, capital=capital, allocation_note=note))
    return sorted(approved + rejected, key=lambda row: row.opportunity_score, reverse=True)


def record_execution_plan(path: Path, rows: list[ExecutionPlanRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()
    with path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "timestamp",
            "agent",
            "agent_name",
            "industry",
            "symbol",
            "action",
            "source_action",
            "opportunity_score",
            "target_weight",
            "current_weight",
            "notional",
            "predicted_return_pct",
            "predicted_profit",
            "cash",
            "buying_power",
            "equity",
            "allocation_note",
            "status",
            "reason",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "timestamp": timestamp,
                    "agent": row.agent,
                    "agent_name": row.agent_name,
                    "industry": row.industry,
                    "symbol": row.symbol,
                    "action": row.action,
                    "source_action": row.source_action,
                    "opportunity_score": f"{row.opportunity_score:.4f}",
                    "target_weight": f"{row.target_weight:.4f}",
                    "current_weight": f"{row.current_weight:.4f}",
                    "notional": f"{row.notional:.2f}",
                    "predicted_return_pct": f"{row.predicted_return_pct:.4f}",
                    "predicted_profit": f"{row.predicted_profit:.2f}",
                    "cash": f"{row.cash:.2f}",
                    "buying_power": f"{row.buying_power:.2f}",
                    "equity": f"{row.equity:.2f}",
                    "allocation_note": row.allocation_note,
                    "status": row.status,
                    "reason": row.reason,
                }
            )


def execution_account() -> dict:
    try:
        return AlpacaClient().account()
    except (AlpacaApiError, AlpacaConfigError, OSError):
        return {"buying_power": "0", "cash": "0"}


def execute_execution_plan(path: Path) -> None:
    dry_run = os.getenv("PORTFOLIO_DRY_RUN", "true").lower() != "false"
    if dry_run:
        print("Execution plan skipped: PORTFOLIO_DRY_RUN is active.", flush=True)
        return
    try:
        client = AlpacaClient()
    except AlpacaConfigError as exc:
        print(f"Execution plan skipped: {exc}", flush=True)
        return

    if not path.exists():
        print(f"Execution plan skipped: {path} does not exist.", flush=True)
        return

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    try:
        positions = {
            str(position.get("symbol", "")).upper(): position
            for position in client.positions()
        }
        open_buy_symbols = {
            str(order.get("symbol", "")).upper()
            for order in client.orders(status="open", limit=100)
            if str(order.get("side", "")).lower() == "buy"
        }
    except (AlpacaApiError, OSError) as exc:
        print(f"Execution plan skipped: portfolio/order check failed: {exc}", flush=True)
        return

    for row in rows:
        if "APPROVED" not in row.get("status", ""):
            continue
        notional = _float(row.get("notional"))
        if notional <= 0:
            continue
        symbol = row["symbol"]
        current_weight = _float(row.get("current_weight"))
        if symbol.upper() in positions or current_weight > 0:
            print(f"Skipped APPROVED buy {symbol}: position already held.", flush=True)
            continue
        if symbol.upper() in open_buy_symbols:
            print(f"Skipped APPROVED buy {symbol}: buy order already open.", flush=True)
            continue
        client_order_id = f"council-{symbol.lower()}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        response = client.submit_market_order(
            symbol=symbol,
            side="buy",
            notional=notional,
            client_order_id=client_order_id,
        )
        print(
            f"Submitted {row['status']} buy {symbol} for ${notional:.2f}: {response.get('id', '<no id>')}",
            flush=True,
        )


def execution_settings() -> dict:
    return {
        "max_trade_notional": float(os.getenv("PORTFOLIO_MAX_TRADE_NOTIONAL", "250")),
        "max_trade_fraction_of_buying_power": float(os.getenv("PORTFOLIO_MAX_TRADE_FRACTION_OF_BUYING_POWER", "0.01")),
        "max_position_fraction_of_equity": float(os.getenv("PORTFOLIO_MAX_POSITION_FRACTION_OF_EQUITY", "0.03")),
        "min_conviction_notional": float(os.getenv("PORTFOLIO_MIN_CONVICTION_NOTIONAL", "1000")),
        "min_opportunity_score": float(os.getenv("PORTFOLIO_EXECUTION_MIN_SCORE", "6.5")),
        "buying_power_fraction": float(os.getenv("PORTFOLIO_BUYING_POWER_FRACTION", "0.25")),
        "quality_bias": float(os.getenv("PORTFOLIO_QUALITY_BIAS", "1.5")),
        "max_approved_trades": int(os.getenv("PORTFOLIO_MAX_APPROVED_TRADES", "5")),
        "min_trades_per_agent": int(os.getenv("PORTFOLIO_MIN_TRADES_PER_AGENT", "5")),
        "exploration_min_score": float(os.getenv("PORTFOLIO_EXPLORATION_MIN_SCORE", "4.75")),
        "exploration_budget_fraction": float(os.getenv("PORTFOLIO_EXPLORATION_BUDGET_FRACTION", "0.10")),
        "exploration_max_notional": float(os.getenv("PORTFOLIO_EXPLORATION_MAX_NOTIONAL", "25")),
        "forced_exploration_max_notional": float(os.getenv("PORTFOLIO_FORCED_EXPLORATION_MAX_NOTIONAL", "10")),
    }


def account_capital(account: dict) -> AccountCapital:
    return AccountCapital(
        cash=_float(account.get("cash")),
        buying_power=_float(account.get("buying_power")) or _float(account.get("cash")),
        equity=_float(account.get("equity")) or _float(account.get("portfolio_value")),
        long_market_value=_float(account.get("long_market_value")),
        short_market_value=_float(account.get("short_market_value")),
    )


def conviction_trade_cap(account: dict, settings: dict) -> float:
    capital = account_capital(account)
    fallback_cap = _float(settings.get("max_trade_notional"))
    buying_power_fraction = _float(settings.get("max_trade_fraction_of_buying_power", 0.01))
    equity_fraction = _float(settings.get("max_position_fraction_of_equity", 0.03))
    buying_power_cap = capital.liquid_capital * buying_power_fraction
    equity_cap = capital.equity * equity_fraction
    dynamic_caps = [cap for cap in (buying_power_cap, equity_cap) if cap > 0]
    if not dynamic_caps:
        return fallback_cap

    cap = min(dynamic_caps)
    min_conviction = _float(settings.get("min_conviction_notional", 1000.0))
    if min_conviction > 0 and capital.liquid_capital >= min_conviction:
        cap = max(cap, min_conviction)
    return max(fallback_cap, cap)


def allocation_note(capital: AccountCapital, trade_cap: float) -> str:
    return (
        f"sized from cash ${capital.cash:,.2f}, buying power ${capital.buying_power:,.2f}, "
        f"equity ${capital.equity:,.2f}; conviction cap ${trade_cap:,.2f}"
    )


def _row(
    decision: PortfolioDecision,
    score: float,
    notional: float,
    status: str,
    reason: str,
    *,
    agent: str = "",
    agent_name: str = "",
    industry: str = "",
    action: str | None = None,
    capital: AccountCapital | None = None,
    allocation_note: str = "",
) -> ExecutionPlanRow:
    capital = capital or AccountCapital(0.0, 0.0, 0.0, 0.0, 0.0)
    return ExecutionPlanRow(
        agent=agent,
        agent_name=agent_name,
        industry=industry,
        symbol=decision.symbol,
        action=action or decision.action,
        source_action=decision.action,
        opportunity_score=score,
        target_weight=decision.target_weight,
        current_weight=decision.current_weight,
        notional=notional,
        status=status,
        reason=reason,
        predicted_return_pct=predicted_return_pct(decision),
        predicted_profit=predicted_profit(notional, decision),
        cash=capital.cash,
        buying_power=capital.buying_power,
        equity=capital.equity,
        allocation_note=allocation_note,
    )


def _float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
