from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from portfolio_model.alpaca import AlpacaApiError, AlpacaClient, AlpacaConfigError
from portfolio_model.backtest import (
    PriceBar,
    common_calendar,
    fetch_sp500_sectors,
    load_or_fetch_bars,
    price_table,
    rank_symbols,
    risk_weights,
    select_candidates,
    strategy_features,
)
from portfolio_model.env import load_dotenv
from portfolio_model.momentum_execution import execute_paper_plan, execution_error_rows, write_order_results
from portfolio_model.momentum_journal import (
    build_decision_journal,
    merge_orders_into_journal,
    merge_plan_into_journal,
    write_decision_journal,
)


DEFAULT_IGNORED_UNMANAGED_SYMBOLS = {"CBOE", "VRNS", "DRIO"}


def main() -> None:
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(description="Generate paper momentum-breakout signals for S&P 500 stocks.")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--max-symbols", type=int, default=503)
    parser.add_argument("--cache", default="state/backtest_bars_sp500.json")
    parser.add_argument("--output-dir", default="state")
    parser.add_argument("--min-score", type=float, default=6.5)
    parser.add_argument("--max-positions", type=int, default=5)
    parser.add_argument("--volatility-target", type=float, default=0.18)
    parser.add_argument("--sector-cap", type=float, default=0.40)
    parser.add_argument("--correlation-cap", type=float, default=0.75)
    parser.add_argument("--feed", default="iex")
    parser.add_argument("--refresh-data", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--sleeve-fraction", type=float, default=0.10)
    parser.add_argument("--min-trade-notional", type=float, default=25.0)
    parser.add_argument(
        "--execute-paper",
        action="store_true",
        help="Submit momentum plan deltas to Alpaca paper (BUY and managed SELL actions).",
    )
    parser.add_argument("--max-order-notional", type=float, default=3000.0)
    parser.add_argument(
        "--ignore-unmanaged-symbols",
        default="CBOE,VRNS,DRIO",
        help="Comma-separated held symbols to omit from unmanaged REVIEW analysis rows.",
    )
    args = parser.parse_args()

    result = generate_signal(args)
    output_path = write_signal(Path(args.output_dir), result["signals"])
    plan_path = write_paper_plan(Path(args.output_dir), result["paper_plan"], result["run_date"])
    order_path = None
    if args.execute_paper:
        try:
            order_rows = execute_paper_plan(
                result["paper_plan"],
                run_date=result["run_date"],
                max_order_notional=args.max_order_notional,
            )
        except (AlpacaApiError, AlpacaConfigError, OSError, RuntimeError) as exc:
            order_rows = execution_error_rows(result["paper_plan"], result["run_date"], exc)
        merge_orders_into_journal(result["decision_journal"], order_rows)
        order_path = write_order_results(Path(args.output_dir), order_rows, result["run_date"])
    journal_path = write_decision_journal(Path(args.output_dir), result["decision_journal"], result["run_date"])
    print(f"Wrote {len(result['signals'])} signal rows to {output_path}", flush=True)
    print(f"Wrote {len(result['paper_plan'])} paper plan rows to {plan_path}", flush=True)
    print(f"Wrote {len(result['decision_journal'])} decision journal rows to {journal_path}", flush=True)
    if order_path:
        print(f"Wrote paper order results to {order_path}", flush=True)
    for warning in result["warnings"]:
        print(f"WARNING: {warning}", flush=True)
    for row in result["signals"]:
        if row.get("symbol"):
            print(
                f"{row['symbol']} score={row['score']} weight={row['strategy_sleeve_weight']} "
                f"sector={row['sector']} action={plan_action(result['paper_plan'], row['symbol'])}",
                flush=True,
            )


def generate_signal(args: argparse.Namespace) -> dict[str, object]:
    end = datetime.now(UTC).date()
    start = end - timedelta(days=round(args.years * 365.25))
    warnings: list[str] = []
    cache_path = Path(args.cache)
    sectors = fetch_sectors_with_fallback(cache_path, warnings)
    symbols = list(dict.fromkeys([*sectors, "SPY"]))[: max(1, args.max_symbols)]
    if "SPY" not in symbols:
        symbols.append("SPY")

    bars = load_bars_with_fallback(
        symbols=symbols,
        start=start,
        end=end,
        feed=args.feed,
        cache_path=cache_path,
        refresh_data=args.refresh_data,
        warnings=warnings,
    )
    bars = {symbol: series for symbol, series in bars.items() if len(series) >= 260}
    if "SPY" not in bars:
        raise RuntimeError("SPY benchmark data is required for live signal generation.")
    prices = price_table(bars)
    calendar = common_calendar(bars)
    signal_date = calendar[-1]
    regime = regime_snapshot(prices["SPY"], signal_date)
    selected = []
    weights = {}
    ranked = []
    if regime["regime_on"] == "true":
        effective_sector_cap = args.sector_cap if has_sector_data(sectors) else 1.0
        ranked = rank_symbols(
            [symbol for symbol in bars if symbol != "SPY"],
            bars,
            prices,
            signal_date,
            strategy_book="momentum_breakout",
        )
        selected = select_candidates(
            ranked,
            min_score=args.min_score,
            max_positions=args.max_positions,
            sector_cap=effective_sector_cap,
            correlation_cap=args.correlation_cap,
            sectors=sectors,
            bars=bars,
            prices=prices,
            day=signal_date,
        )
        weights = risk_weights(selected, bars, prices, signal_date, args.volatility_target)

    selected_symbols = {symbol for symbol, _ in selected}
    plan_context = {
        "min_score": args.min_score,
        "max_positions": args.max_positions,
        "volatility_target": args.volatility_target,
        "sector_cap": args.sector_cap,
        "effective_sector_cap": effective_sector_cap if regime["regime_on"] == "true" else args.sector_cap,
        "correlation_cap": args.correlation_cap,
    }
    decision_journal = build_decision_journal(
        ranked,
        selected_symbols=selected_symbols,
        weights=weights,
        bars=bars,
        sectors=sectors,
        signal_date=signal_date,
        run_date=end,
        regime=regime,
        context=plan_context,
        max_rows=max(args.max_positions * 4, 25),
    )

    rows = []
    for symbol, score in selected:
        features = strategy_features(bars[symbol], signal_date)
        rows.append(
            {
                "run_date": end.isoformat(),
                "signal_date": signal_date.isoformat(),
                **regime,
                "symbol": symbol,
                "sector": sectors.get(symbol, "Unknown"),
                "score": f"{score:.4f}",
                "strategy_sleeve_weight": f"{weights.get(symbol, 0.0):.4f}",
                "close": f"{prices[symbol][signal_date]:.2f}",
                "momentum_6m": f"{features.momentum_6m:.4f}",
                "momentum_3m": f"{features.momentum_3m:.4f}",
                "drawdown": f"{features.drawdown:.4f}",
                "volatility": f"{features.volatility:.4f}",
                "data_warning": " | ".join(warnings),
            }
        )
    if not rows:
        rows.append(
            {
                "run_date": end.isoformat(),
                "signal_date": signal_date.isoformat(),
                **regime,
                "symbol": "",
                "sector": "",
                "score": "",
                "strategy_sleeve_weight": "",
                "close": "",
                "momentum_6m": "",
                "momentum_3m": "",
                "drawdown": "",
                "volatility": "",
                "data_warning": " | ".join(warnings),
            }
        )
    account, positions, account_warning = load_paper_account()
    if account_warning:
        warnings.append(account_warning)
    managed_symbols = load_momentum_managed_symbols(Path(args.output_dir))
    plan = build_paper_plan(
        rows,
        account=account,
        positions=positions,
        sleeve_fraction=args.sleeve_fraction,
        min_trade_notional=args.min_trade_notional,
        ignored_unmanaged_symbols=normalize_symbol_list(getattr(args, "ignore_unmanaged_symbols", "")),
        managed_symbols=managed_symbols,
    )
    merge_plan_into_journal(decision_journal, plan)
    return {"run_date": end, "signals": rows, "paper_plan": plan, "decision_journal": decision_journal, "warnings": warnings}


def normalize_symbol_list(raw: str) -> set[str]:
    values = {token.strip().upper() for token in str(raw or "").split(",") if token.strip()}
    return values or set(DEFAULT_IGNORED_UNMANAGED_SYMBOLS)


def load_momentum_managed_symbols(output_dir: Path) -> set[str]:
    symbols: set[str] = set()
    for path in output_dir.glob("momentum_signal_*.csv"):
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    symbol = str(row.get("symbol", "")).strip().upper()
                    if symbol:
                        symbols.add(symbol)
        except OSError:
            continue
    return symbols


def fetch_sectors_with_fallback(cache_path: Path, warnings: list[str]) -> dict[str, str]:
    try:
        return fetch_sp500_sectors()
    except (OSError, TimeoutError) as exc:
        warnings.append(f"S&P 500 membership refresh failed; using cached symbols with unknown sectors: {exc}")
    cached = load_cached_bars(cache_path, None)
    if cached:
        return {symbol: "Unknown" for symbol in cached if symbol != "SPY"}
    raise RuntimeError("Could not refresh S&P 500 membership and no cached symbols were available.")


def has_sector_data(sectors: dict[str, str]) -> bool:
    known = [sector for sector in sectors.values() if sector and sector != "Unknown"]
    return len(known) >= max(10, len(sectors) // 2)


def load_bars_with_fallback(
    *,
    symbols: list[str],
    start: date,
    end: date,
    feed: str,
    cache_path: Path,
    refresh_data: bool,
    warnings: list[str],
) -> dict[str, list[PriceBar]]:
    if refresh_data:
        try:
            return load_or_fetch_bars(symbols=symbols, start=start, end=end, feed=feed, cache_path=cache_path)
        except (AlpacaApiError, AlpacaConfigError, OSError) as exc:
            warnings.append(f"Bar refresh failed; using cached bars if available: {exc}")
    cached = load_cached_bars(cache_path, set(symbols))
    if not cached:
        raise RuntimeError(f"No usable cached bars found at {cache_path}.")
    return cached


def load_cached_bars(cache_path: Path, requested_symbols: set[str] | None) -> dict[str, list[PriceBar]]:
    if not cache_path.exists():
        return {}
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    bars = {}
    for symbol, rows in payload.get("bars", {}).items():
        if requested_symbols is not None and symbol not in requested_symbols:
            continue
        bars[symbol] = [
            PriceBar(date.fromisoformat(row["day"]), float(row["close"]))
            for row in rows
            if row.get("day") and row.get("close") is not None
        ]
    return bars


def load_paper_account() -> tuple[dict[str, str], dict[str, dict], str]:
    try:
        client = AlpacaClient()
        account = client.account()
        positions = {str(position.get("symbol", "")).upper(): position for position in client.positions()}
        return account, positions, ""
    except (AlpacaApiError, AlpacaConfigError, OSError) as exc:
        return {}, {}, f"Paper account sync failed; plan is target-only and no orders were placed: {exc}"


def build_paper_plan(
    signal_rows: list[dict[str, str]],
    *,
    account: dict,
    positions: dict[str, dict],
    sleeve_fraction: float,
    min_trade_notional: float,
    ignored_unmanaged_symbols: set[str] | None = None,
    managed_symbols: set[str] | None = None,
) -> list[dict[str, str]]:
    ignored_unmanaged_symbols = ignored_unmanaged_symbols or set()
    managed_symbols = managed_symbols or set()
    equity = parse_float(account.get("portfolio_value")) or parse_float(account.get("equity"))
    sleeve_notional = max(0.0, equity * max(0.0, min(sleeve_fraction, 1.0)))
    run_date = signal_rows[0]["run_date"] if signal_rows else datetime.now(UTC).date().isoformat()
    signal_date = signal_rows[0]["signal_date"] if signal_rows else ""
    rows: list[dict[str, str]] = []
    target_symbols = {row["symbol"] for row in signal_rows if row.get("symbol")}
    for row in signal_rows:
        symbol = row.get("symbol", "")
        if not symbol:
            continue
        target_weight = parse_float(row.get("strategy_sleeve_weight"))
        position = positions.get(symbol, {})
        current_notional = parse_float(position.get("market_value"))
        target_notional = sleeve_notional * target_weight
        delta = target_notional - current_notional
        action = trade_action(delta, min_trade_notional)
        rows.append(
            {
                "run_date": run_date,
                "signal_date": signal_date,
                "symbol": symbol,
                "target_sleeve_weight": f"{target_weight:.4f}",
                "account_equity": f"{equity:.2f}",
                "sleeve_fraction": f"{sleeve_fraction:.4f}",
                "target_notional": f"{target_notional:.2f}",
                "current_notional": f"{current_notional:.2f}",
                "delta_notional": f"{delta:.2f}",
                "action": action,
                "status": "PAPER_PLAN_ONLY",
                "reason": "Momentum target from latest completed daily close; no order submitted.",
            }
        )
    for symbol, position in sorted(positions.items()):
        if symbol in target_symbols:
            continue
        if symbol in ignored_unmanaged_symbols:
            continue
        current_notional = parse_float(position.get("market_value"))
        if current_notional <= 0:
            continue
        if symbol in managed_symbols:
            delta = -current_notional
            rows.append(
                {
                    "run_date": run_date,
                    "signal_date": signal_date,
                    "symbol": symbol,
                    "target_sleeve_weight": "0.0000",
                    "account_equity": f"{equity:.2f}",
                    "sleeve_fraction": f"{sleeve_fraction:.4f}",
                    "target_notional": "0.00",
                    "current_notional": f"{current_notional:.2f}",
                    "delta_notional": f"{delta:.2f}",
                    "action": trade_action(delta, min_trade_notional),
                    "status": "PAPER_PLAN_ONLY",
                    "reason": "Previously selected by momentum model but not a current target; exit to zero.",
                }
            )
            continue
        rows.append(
            {
                "run_date": run_date,
                "signal_date": signal_date,
                "symbol": symbol,
                "target_sleeve_weight": "0.0000",
                "account_equity": f"{equity:.2f}",
                "sleeve_fraction": f"{sleeve_fraction:.4f}",
                "target_notional": "0.00",
                "current_notional": f"{current_notional:.2f}",
                "delta_notional": "0.00",
                "action": "REVIEW",
                "status": "UNMANAGED_POSITION",
                "reason": "Held in paper account but not a current momentum target; review before any sell.",
            }
        )
    if not rows:
        rows.append(
            {
                "run_date": run_date,
                "signal_date": signal_date,
                "symbol": "",
                "target_sleeve_weight": "0.0000",
                "account_equity": f"{equity:.2f}",
                "sleeve_fraction": f"{sleeve_fraction:.4f}",
                "target_notional": "0.00",
                "current_notional": "0.00",
                "delta_notional": "0.00",
                "action": "HOLD_CASH",
                "status": "NO_TARGETS",
                "reason": "Regime gate is off or no stock met the threshold.",
            }
        )
    return rows


def trade_action(delta: float, min_trade_notional: float) -> str:
    if delta >= min_trade_notional:
        return "BUY"
    if delta <= -min_trade_notional:
        return "SELL"
    return "HOLD"


def plan_action(plan_rows: list[dict[str, str]], symbol: str) -> str:
    for row in plan_rows:
        if row.get("symbol") == symbol:
            return row.get("action", "")
    return ""


def parse_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def regime_snapshot(spy_prices: dict[date, float], signal_date: date) -> dict[str, str]:
    days = sorted(day for day in spy_prices if day <= signal_date)
    spy_close = spy_prices[days[-1]]
    ma50 = sum(spy_prices[day] for day in days[-50:]) / 50
    ma200 = sum(spy_prices[day] for day in days[-200:]) / 200
    spy_3m_momentum = spy_close / spy_prices[days[-63]] - 1.0
    return {
        "regime_on": str(spy_close > ma200 and ma50 > ma200 and spy_3m_momentum > 0).lower(),
        "spy_close": f"{spy_close:.2f}",
        "spy_ma50": f"{ma50:.2f}",
        "spy_ma200": f"{ma200:.2f}",
        "spy_3m_momentum": f"{spy_3m_momentum:.4f}",
    }


def write_signal(output_dir: Path, rows: list[dict[str, str]]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_date = rows[0]["run_date"].replace("-", "")
    path = output_dir / f"momentum_signal_{run_date}.csv"
    fields = [
        "run_date",
        "signal_date",
        "regime_on",
        "spy_close",
        "spy_ma50",
        "spy_ma200",
        "spy_3m_momentum",
        "symbol",
        "sector",
        "score",
        "strategy_sleeve_weight",
        "close",
        "momentum_6m",
        "momentum_3m",
        "drawdown",
        "volatility",
        "data_warning",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_paper_plan(output_dir: Path, rows: list[dict[str, str]], run_date: date) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"momentum_paper_plan_{run_date.isoformat().replace('-', '')}.csv"
    fields = [
        "run_date",
        "signal_date",
        "symbol",
        "target_sleeve_weight",
        "account_equity",
        "sleeve_fraction",
        "target_notional",
        "current_notional",
        "delta_notional",
        "action",
        "status",
        "reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


if __name__ == "__main__":
    main()
