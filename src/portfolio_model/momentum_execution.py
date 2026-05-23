from __future__ import annotations

import csv
import os
from datetime import UTC, date, datetime
from pathlib import Path

from portfolio_model.alpaca import AlpacaApiError, AlpacaClient


ORDER_RESULT_FIELDS = [
    "run_date",
    "signal_date",
    "symbol",
    "plan_action",
    "requested_notional",
    "submitted_notional",
    "status",
    "order_id",
    "reason",
]


def execute_paper_plan(
    plan_rows: list[dict[str, str]],
    *,
    run_date: date,
    max_order_notional: float,
    client: AlpacaClient | None = None,
) -> list[dict[str, str]]:
    client = client or AlpacaClient()
    if "paper-api.alpaca.markets" not in client.config.base_url:
        raise RuntimeError(f"Refusing to execute momentum plan against non-paper Alpaca URL: {client.config.base_url}")
    if not paper_execution_enabled():
        raise RuntimeError("Refusing to execute: set PORTFOLIO_DRY_RUN=false and pass --execute-paper.")

    account = client.account()
    positions = {str(position.get("symbol", "")).upper(): position for position in client.positions()}
    open_orders = client.orders(status="open", limit=100)
    open_buy_symbols = open_order_symbols(open_orders, "buy")
    open_sell_symbols = open_order_symbols(open_orders, "sell")
    buying_power = parse_float(account.get("buying_power")) or parse_float(account.get("cash"))

    results = []
    for row in plan_rows:
        result, buying_power = execute_plan_row(
            row,
            run_date=run_date,
            max_order_notional=max_order_notional,
            client=client,
            positions=positions,
            open_buy_symbols=open_buy_symbols,
            open_sell_symbols=open_sell_symbols,
            buying_power=buying_power,
        )
        results.append(result)
    return results


def execute_plan_row(
    row: dict[str, str],
    *,
    run_date: date,
    max_order_notional: float,
    client: AlpacaClient,
    positions: dict[str, dict],
    open_buy_symbols: set[str],
    open_sell_symbols: set[str],
    buying_power: float,
) -> tuple[dict[str, str], float]:
    symbol = row.get("symbol", "").upper()
    action = row.get("action", "")
    delta_notional = parse_float(row.get("delta_notional"))
    requested = abs(delta_notional) if action == "SELL" else max(0.0, delta_notional)
    submitted = min(requested, max_order_notional)
    result = base_order_result(run_date, row, symbol, action, requested)

    skip_reason = order_skip_reason(
        action=action,
        symbol=symbol,
        submitted=submitted,
        buying_power=buying_power,
        positions=positions,
        open_buy_symbols=open_buy_symbols,
        open_sell_symbols=open_sell_symbols,
    )
    if skip_reason:
        result["reason"] = skip_reason
        return result, buying_power

    side = "buy" if action == "BUY" else "sell"
    try:
        response = client.submit_market_order(
            symbol=symbol,
            side=side,
            notional=submitted,
            client_order_id=f"momentum-{symbol.lower()}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        )
    except (AlpacaApiError, OSError) as exc:
        result["status"] = "REJECTED"
        result["reason"] = str(exc)
        return result, buying_power

    result["submitted_notional"] = f"{submitted:.2f}"
    result["status"] = str(response.get("status") or "SUBMITTED").upper()
    result["order_id"] = str(response.get("id", ""))
    result["reason"] = "submitted to Alpaca paper"
    if action == "BUY":
        buying_power = max(0.0, buying_power - submitted)
        open_buy_symbols.add(symbol)
    else:
        open_sell_symbols.add(symbol)
    return result, buying_power


def base_order_result(run_date: date, row: dict[str, str], symbol: str, action: str, requested: float) -> dict[str, str]:
    return {
        "run_date": run_date.isoformat(),
        "signal_date": row.get("signal_date", ""),
        "symbol": symbol,
        "plan_action": action,
        "requested_notional": f"{requested:.2f}",
        "submitted_notional": "0.00",
        "status": "SKIPPED",
        "order_id": "",
        "reason": "",
    }


def order_skip_reason(
    *,
    action: str,
    symbol: str,
    submitted: float,
    buying_power: float,
    positions: dict[str, dict],
    open_buy_symbols: set[str],
    open_sell_symbols: set[str],
) -> str:
    if action not in {"BUY", "SELL"}:
        return f"plan action {action or '<blank>'} is not executable"
    if not symbol:
        return "missing symbol"
    if action == "BUY" and symbol in open_buy_symbols:
        return "open buy order already exists"
    if action == "SELL" and symbol in open_sell_symbols:
        return "open sell order already exists"
    if action == "SELL" and symbol not in positions:
        return "no held position to sell"
    if action == "SELL" and parse_float(positions.get(symbol, {}).get("market_value")) <= 0:
        return "position market value is non-positive; skipping sell"
    if action == "BUY" and submitted > buying_power:
        return "buying power below requested notional"
    if submitted < 1.0:
        return "requested notional below $1"
    return ""


def execution_error_rows(
    plan_rows: list[dict[str, str]],
    run_date: date,
    exc: Exception,
) -> list[dict[str, str]]:
    reason = f"execution unavailable before order submission: {exc}"
    rows = [
        {
            "run_date": run_date.isoformat(),
            "signal_date": row.get("signal_date", ""),
            "symbol": row.get("symbol", ""),
            "plan_action": row.get("action", ""),
            "requested_notional": f"{abs(parse_float(row.get('delta_notional'))):.2f}",
            "submitted_notional": "0.00",
            "status": "EXECUTION_ERROR",
            "order_id": "",
            "reason": reason,
        }
        for row in plan_rows
    ]
    if rows:
        return rows
    return [
        {
            "run_date": run_date.isoformat(),
            "signal_date": "",
            "symbol": "",
            "plan_action": "",
            "requested_notional": "0.00",
            "submitted_notional": "0.00",
            "status": "EXECUTION_ERROR",
            "order_id": "",
            "reason": reason,
        }
    ]


def paper_execution_enabled() -> bool:
    return os.getenv("PORTFOLIO_DRY_RUN", "true").lower() == "false"


def open_order_symbols(open_orders: list[dict], side: str) -> set[str]:
    return {
        str(order.get("symbol", "")).upper()
        for order in open_orders
        if str(order.get("side", "")).lower() == side
    }


def write_order_results(output_dir: Path, rows: list[dict[str, str]], run_date: date) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"momentum_order_results_{run_date.isoformat().replace('-', '')}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ORDER_RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def parse_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
