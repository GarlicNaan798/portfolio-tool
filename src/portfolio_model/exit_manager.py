from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from portfolio_model.alpaca import AlpacaApiError, AlpacaClient, AlpacaConfigError


@dataclass(frozen=True)
class ExitPlanRow:
    symbol: str
    qty: float
    market_value: float
    unrealized_plpc: float
    side: str
    exit_fraction: float
    status: str
    reason: str


def build_exit_plan(
    positions: list[dict],
    *,
    take_profit_pct: float,
    stop_loss_pct: float,
    partial_profit_fraction: float,
    full_exit_fraction: float,
) -> list[ExitPlanRow]:
    rows = []
    for position in positions:
        symbol = str(position.get("symbol", "")).upper()
        qty = abs(_float(position.get("qty")))
        market_value = abs(_float(position.get("market_value")))
        unrealized = _float(position.get("unrealized_plpc"))
        side = "sell" if _float(position.get("qty")) > 0 else "buy"

        if qty <= 0:
            continue
        if unrealized >= take_profit_pct:
            rows.append(
                ExitPlanRow(
                    symbol=symbol,
                    qty=qty,
                    market_value=market_value,
                    unrealized_plpc=unrealized,
                    side=side,
                    exit_fraction=partial_profit_fraction,
                    status="TAKE_PROFIT",
                    reason=f"unrealized return {unrealized:.2%} >= take profit {take_profit_pct:.2%}",
                )
            )
        elif unrealized <= -abs(stop_loss_pct):
            rows.append(
                ExitPlanRow(
                    symbol=symbol,
                    qty=qty,
                    market_value=market_value,
                    unrealized_plpc=unrealized,
                    side=side,
                    exit_fraction=full_exit_fraction,
                    status="STOP_LOSS",
                    reason=f"unrealized return {unrealized:.2%} <= stop loss {-abs(stop_loss_pct):.2%}",
                )
            )
        else:
            rows.append(
                ExitPlanRow(
                    symbol=symbol,
                    qty=qty,
                    market_value=market_value,
                    unrealized_plpc=unrealized,
                    side=side,
                    exit_fraction=0.0,
                    status="HOLD_POSITION",
                    reason="no exit trigger",
                )
            )
    return rows


def record_exit_plan(path: Path, rows: list[ExitPlanRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()
    with path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "timestamp",
            "symbol",
            "qty",
            "market_value",
            "unrealized_plpc",
            "side",
            "exit_fraction",
            "status",
            "reason",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "timestamp": timestamp,
                    "symbol": row.symbol,
                    "qty": f"{row.qty:.6f}",
                    "market_value": f"{row.market_value:.2f}",
                    "unrealized_plpc": f"{row.unrealized_plpc:.4f}",
                    "side": row.side,
                    "exit_fraction": f"{row.exit_fraction:.4f}",
                    "status": row.status,
                    "reason": row.reason,
                }
            )


def run_exit_manager(path: Path) -> list[ExitPlanRow]:
    try:
        client = AlpacaClient()
        positions = client.positions()
    except (AlpacaApiError, AlpacaConfigError, OSError) as exc:
        rows = [
            ExitPlanRow("", 0.0, 0.0, 0.0, "", 0.0, "UNAVAILABLE", str(exc))
        ]
        record_exit_plan(path, rows)
        return rows

    rows = build_exit_plan(
        positions,
        take_profit_pct=float(os.getenv("PORTFOLIO_TAKE_PROFIT_PCT", "0.08")),
        stop_loss_pct=float(os.getenv("PORTFOLIO_STOP_LOSS_PCT", "0.04")),
        partial_profit_fraction=float(os.getenv("PORTFOLIO_PARTIAL_PROFIT_FRACTION", "0.50")),
        full_exit_fraction=float(os.getenv("PORTFOLIO_FULL_EXIT_FRACTION", "1.00")),
    )
    record_exit_plan(path, rows)
    return rows


def execute_exit_plan(path: Path) -> None:
    dry_run = os.getenv("PORTFOLIO_DRY_RUN", "true").lower() != "false"
    if dry_run or not path.exists():
        return
    client = AlpacaClient()
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row.get("status") not in {"TAKE_PROFIT", "STOP_LOSS"}:
            continue
        qty = _float(row.get("qty")) * _float(row.get("exit_fraction"))
        if qty <= 0:
            continue
        client.submit_market_order(
            symbol=row["symbol"],
            side=row["side"],
            notional=0.0,
            qty=qty,
            client_order_id=f"exit-{row['symbol'].lower()}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        )


def _float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
