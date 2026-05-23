from __future__ import annotations

import csv
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from portfolio_model import alpaca
from portfolio_model.model import EquityInput


def sync_alpaca_portfolio(universe: list[EquityInput], snapshot_path: Path | None = None) -> list[EquityInput]:
    try:
        client = alpaca.AlpacaClient()
        account = client.account()
        positions = client.positions()
    except (alpaca.AlpacaApiError, alpaca.AlpacaConfigError, OSError) as exc:
        if snapshot_path is not None:
            write_portfolio_snapshot(snapshot_path, {}, {}, warning=str(exc))
        return universe

    portfolio_value = _float(account.get("portfolio_value")) or _float(account.get("equity")) or 0.0
    by_symbol = {str(position.get("symbol", "")).upper(): position for position in positions}
    synced = []
    synced_symbols = set()
    for equity in universe:
        position = by_symbol.get(equity.symbol)
        synced_symbols.add(equity.symbol)
        if position and portfolio_value > 0:
            market_value = _float(position.get("market_value"))
            weight = market_value / portfolio_value if market_value else 0.0
            synced.append(replace(equity, current_weight=weight))
        else:
            synced.append(replace(equity, current_weight=0.0))

    for symbol, position in by_symbol.items():
        if symbol in synced_symbols:
            continue
        market_value = _float(position.get("market_value"))
        price = _float(position.get("current_price")) or _float(position.get("avg_entry_price"))
        weight = market_value / portfolio_value if portfolio_value and market_value else 0.0
        synced.append(
            EquityInput(
                symbol=symbol,
                industry="Held Position",
                price=price,
                pe=99.0,
                pb=99.0,
                fcf_yield=0.0,
                revenue_yoy=0.0,
                eps_yoy=0.0,
                gross_margin=0.0,
                debt_to_equity=0.0,
                sentiment=0.5,
                sentiment_confidence=0.0,
                current_weight=weight,
            )
        )

    if snapshot_path is not None:
        write_portfolio_snapshot(snapshot_path, account, by_symbol)
    return synced


def write_portfolio_snapshot(
    path: Path,
    account: dict,
    positions: dict[str, dict] | None,
    *,
    warning: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "timestamp",
            "symbol",
            "qty",
            "market_value",
            "portfolio_value",
            "weight",
            "avg_entry_price",
            "unrealized_plpc",
            "warning",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        portfolio_value = _float(account.get("portfolio_value")) or _float(account.get("equity")) or 0.0
        if positions is None:
            positions = {}
        if not positions:
            writer.writerow(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "symbol": "",
                    "qty": "0",
                    "market_value": "0.00",
                    "portfolio_value": f"{portfolio_value:.2f}",
                    "weight": "0.0000",
                    "avg_entry_price": "0.00",
                    "unrealized_plpc": "0.0000",
                    "warning": warning,
                }
            )
            return
        for symbol, position in sorted(positions.items()):
            market_value = _float(position.get("market_value"))
            writer.writerow(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "symbol": symbol,
                    "qty": position.get("qty", "0"),
                    "market_value": f"{market_value:.2f}",
                    "portfolio_value": f"{portfolio_value:.2f}",
                    "weight": f"{(market_value / portfolio_value if portfolio_value else 0.0):.4f}",
                    "avg_entry_price": position.get("avg_entry_price", "0.00"),
                    "unrealized_plpc": position.get("unrealized_plpc", "0.0000"),
                    "warning": warning,
                }
            )


def _float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
