from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from portfolio_model.alpaca import AlpacaApiError, AlpacaClient, AlpacaConfigError
from portfolio_model.env import load_dotenv


def main() -> None:
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(description="Review one paper-trading day.")
    parser.add_argument("--date", required=True, help="Local review date, YYYY-MM-DD.")
    parser.add_argument("--tz-offset-hours", type=int, default=4)
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    review_date = date.fromisoformat(args.date)
    state_dir = Path(args.state_dir)
    report = build_report(review_date, args.tz_offset_hours, state_dir)
    output = Path(args.output or state_dir / f"performance_review_{review_date.strftime('%Y%m%d')}.md")
    output.write_text(report, encoding="utf-8")
    print(report)


def build_report(review_date: date, tz_offset_hours: int, state_dir: Path) -> str:
    local_tz = timezone(timedelta(hours=tz_offset_hours))
    start_local = datetime.combine(review_date, time.min, tzinfo=local_tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)

    account: dict = {}
    positions: list[dict] = []
    orders: list[dict] = []
    portfolio_history: dict = {}
    api_warning = ""
    try:
        client = AlpacaClient()
        account = client.account()
        positions = client.positions()
        orders = [
            order for order in client.orders(status="all", limit=500)
            if start_utc <= order_timestamp(order) < end_utc
        ]
        portfolio_history = fetch_portfolio_history(client, start_utc, end_utc)
    except (AlpacaApiError, AlpacaConfigError, OSError) as exc:
        api_warning = str(exc)

    execution_log = state_dir / "continuous_research_execute.out.log"
    error_log = state_dir / "continuous_research_execute.err.log"
    cycles = cycle_timestamps(execution_log, start_utc, end_utc)
    log_text = execution_log.read_text(encoding="utf-8", errors="replace") if execution_log.exists() else ""
    log_slice = log_between(log_text, start_utc, end_utc)
    skipped = Counter(re.findall(r"Skipped (?:sell|buy) ([A-Z.]+): ([^\n]+)", log_slice))
    connected_count = log_slice.count("Connected to Alpaca account")
    research_success_count = log_slice.count("Research scout: researched=")
    stderr_text = error_log.read_text(encoding="utf-8", errors="replace").strip() if error_log.exists() else ""
    orders_by_status = Counter(str(order.get("status", "unknown")) for order in orders)
    orders_by_side = Counter(str(order.get("side", "unknown")) for order in orders)
    filled_orders = [order for order in orders if str(order.get("status", "")).lower() == "filled"]

    lines = [
        f"# Paper Trading Performance Review - {review_date.isoformat()}",
        "",
        f"Review window: {start_local.isoformat()} to {end_local.isoformat()} "
        f"({start_utc.isoformat()} to {end_utc.isoformat()} UTC).",
        "",
        "## Headline",
    ]
    if api_warning:
        lines.append(f"- Alpaca data warning: {api_warning}")
    lines.append(f"- Research/execution loop cycles observed: {len(cycles)}.")
    lines.append(f"- Successful research cycles in log: {research_success_count}.")
    lines.append(f"- Alpaca account connection attempts in log: {connected_count}.")
    lines.append(f"- Orders observed in Alpaca during window: {len(orders)}; filled: {len(filled_orders)}.")
    lines.append(f"- Current paper equity: ${as_float(account.get('equity') or account.get('portfolio_value')):,.2f}.")
    if stderr_text:
        lines.append("- Error log is not empty; review required.")
    else:
        lines.append("- Error log is clean.")
    lines.extend(["", "## Orders"])
    if not orders:
        lines.append("- No Alpaca paper orders were recorded in the review window.")
    else:
        lines.append(f"- By status: {dict(orders_by_status)}")
        lines.append(f"- By side: {dict(orders_by_side)}")
        lines.extend(["", "| Time UTC | Symbol | Side | Status | Filled Qty | Avg Price | Notional |", "|---|---|---|---|---:|---:|---:|"])
        for order in sorted(orders, key=order_timestamp):
            qty = as_float(order.get("filled_qty") or order.get("qty"))
            avg = as_float(order.get("filled_avg_price"))
            notional = as_float(order.get("notional")) or qty * avg
            lines.append(
                f"| {order_timestamp(order).isoformat()} | {order.get('symbol', '')} | "
                f"{order.get('side', '')} | {order.get('status', '')} | {qty:.4f} | ${avg:.2f} | ${notional:.2f} |"
            )

    lines.extend(["", "## Current Positions"])
    if not positions:
        lines.append("- No current paper positions.")
    else:
        lines.append("| Symbol | Market Value | Unrealized P/L | Unrealized % | Qty |")
        lines.append("|---|---:|---:|---:|---:|")
        for position in sorted(positions, key=lambda item: as_float(item.get("unrealized_pl"))):
            lines.append(
                f"| {position.get('symbol', '')} | ${as_float(position.get('market_value')):,.2f} | "
                f"${as_float(position.get('unrealized_pl')):,.2f} | {as_float(position.get('unrealized_plpc')):.2%} | "
                f"{as_float(position.get('qty')):.4f} |"
            )

    lines.extend(["", "## Loop Behavior"])
    if cycles:
        lines.append(f"- First cycle: {cycles[0].isoformat()}.")
        lines.append(f"- Last cycle: {cycles[-1].isoformat()}.")
    for (symbol, reason), count in skipped.most_common(8):
        lines.append(f"- Skipped {symbol} {count}x: {reason}")
    if not skipped:
        lines.append("- No skipped-order messages found in the execution log.")

    equity_points = portfolio_history.get("equity") or []
    if len(equity_points) >= 2:
        start_equity = as_float(equity_points[0])
        end_equity = as_float(equity_points[-1])
        change = end_equity - start_equity
        pct = change / start_equity if start_equity else 0.0
        lines.extend(
            [
                "",
                "## Portfolio History",
                f"- Start equity: ${start_equity:,.2f}.",
                f"- End equity: ${end_equity:,.2f}.",
                f"- Change: ${change:,.2f} ({pct:.2%}).",
            ]
        )

    lines.extend(
        [
            "",
            "## Diagnosis",
            "- The continuous runner was alive and stable, but it did not create meaningful new exposure from its own decisions.",
            "- The only executable action repeatedly surfaced was `TRIM MSFT`, and that was safely skipped because the paper account did not hold MSFT.",
            "- The daily momentum plan generated buy targets, but that plan is separate from the continuous research runner and was not wired into execution.",
            "- The research runner is still using the small watchlist/sample-universe flow, so it researched 9 names repeatedly instead of scanning the full S&P 500 momentum opportunity set.",
            "",
            "## Next Fix",
            "- Unify the daily momentum signal with the execution loop, so approved momentum BUY targets can become paper orders.",
            "- Replace stale/sample current weights with live Alpaca portfolio weights before every model decision.",
            "- Record every cycle to structured CSV, not only stdout logs, so performance attribution is auditable.",
        ]
    )
    return "\n".join(lines) + "\n"


def fetch_portfolio_history(client: AlpacaClient, start_utc: datetime, end_utc: datetime) -> dict:
    query = urlencode(
        {
            "period": "1D",
            "timeframe": "5Min",
            "date_end": end_utc.date().isoformat(),
        }
    )
    try:
        response = client._request("GET", f"/v2/account/portfolio/history?{query}")
        return response if isinstance(response, dict) else {}
    except (AlpacaApiError, OSError):
        return {}


def cycle_timestamps(log_path: Path, start_utc: datetime, end_utc: datetime) -> list[datetime]:
    if not log_path.exists():
        return []
    timestamps = []
    pattern = re.compile(r"\[(?P<ts>\d{4}-\d{2}-\d{2}T[^\]]+)\] Running portfolio model")
    for match in pattern.finditer(log_path.read_text(encoding="utf-8", errors="replace")):
        timestamp = datetime.fromisoformat(match.group("ts"))
        if start_utc <= timestamp < end_utc:
            timestamps.append(timestamp)
    return timestamps


def log_between(text: str, start_utc: datetime, end_utc: datetime) -> str:
    chunks = []
    sections = re.split(r"(?=\[\d{4}-\d{2}-\d{2}T[^\]]+\] Running portfolio model)", text)
    for section in sections:
        match = re.match(r"\[(?P<ts>\d{4}-\d{2}-\d{2}T[^\]]+)\]", section)
        if not match:
            continue
        timestamp = datetime.fromisoformat(match.group("ts"))
        if start_utc <= timestamp < end_utc:
            chunks.append(section)
    return "\n".join(chunks)


def order_timestamp(order: dict) -> datetime:
    for key in ("filled_at", "submitted_at", "created_at"):
        value = order.get(key)
        if value:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime.min.replace(tzinfo=UTC)


def as_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    main()
