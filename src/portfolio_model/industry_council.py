from __future__ import annotations

import argparse
import csv
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path

from portfolio_model.alpaca import AlpacaClient, AlpacaConfigError
from portfolio_model.cli import load_universe, print_decisions
from portfolio_model.decision_book import save_decision_book
from portfolio_model.env import load_dotenv
from portfolio_model.execution_coordinator import (
    ExecutionPlanRow,
    account_capital,
    allocation_note,
    build_execution_plan,
    conviction_trade_cap,
    execute_execution_plan,
    execution_account,
    execution_settings,
    record_execution_plan,
)
from portfolio_model.exit_manager import execute_exit_plan, run_exit_manager
from portfolio_model.industry_types import IndustryAgentResult, IndustryAgentSpec
from portfolio_model.model import PortfolioDecision
from portfolio_model.opportunity import opportunity_components, opportunity_score, predicted_return_pct
from portfolio_model.portfolio_state import sync_alpaca_portfolio
from portfolio_model.preopen import execute_at_open, market_clock
from portfolio_model.research_memory import record_research_cycle
from portfolio_model.scout import OpportunityScout, ScoutConfig

def main() -> None:
    load_dotenv(Path(".env"))

    parser = argparse.ArgumentParser(description="Run five industry agents until the opportunity target is reached.")
    parser.add_argument("--universe", default="data/sample_universe.csv")
    parser.add_argument("--agents-file", default="data/industry_agents.csv")
    parser.add_argument("--decision-book", default="state/decision_book.json")
    parser.add_argument("--research-ledger", default="state/research_ledger.csv")
    parser.add_argument("--research-memory", default="state/research_memory.csv")
    parser.add_argument("--score-ledger", default="state/opportunity_scores.csv")
    parser.add_argument("--agent-ledger", default="state/agent_scores.csv")
    parser.add_argument("--execution-plan", default="state/execution_plan.csv")
    parser.add_argument("--portfolio-snapshot", default="state/alpaca_portfolio.csv")
    parser.add_argument("--exit-plan", default="state/exit_plan.csv")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--industry-agent-count", type=int, default=int(os.getenv("PORTFOLIO_INDUSTRY_AGENT_COUNT", "5")))
    parser.add_argument("--workers-per-industry", type=int, default=int(os.getenv("PORTFOLIO_WORKERS_PER_INDUSTRY", "8")))
    parser.add_argument("--discover-per-industry", type=int, default=int(os.getenv("PORTFOLIO_DISCOVER_PER_INDUSTRY", "25")))
    parser.add_argument("--candidate-count", type=int, default=int(os.getenv("PORTFOLIO_TARGET_CANDIDATE_COUNT", "10")))
    parser.add_argument("--target-average-score", type=float, default=float(os.getenv("PORTFOLIO_TARGET_AVERAGE_SCORE", "7.0")))
    parser.add_argument("--memory-min-score", type=float, default=float(os.getenv("PORTFOLIO_MEMORY_MIN_SCORE", "0.46")))
    parser.add_argument("--research-interval-minutes", type=float, default=float(os.getenv("PORTFOLIO_PREOPEN_RESEARCH_INTERVAL_MINUTES", "15")))
    parser.add_argument("--clock-interval-seconds", type=float, default=float(os.getenv("PORTFOLIO_CLOCK_INTERVAL_SECONDS", "30")))
    parser.add_argument("--max-trade-notional", type=float, default=float(os.getenv("PORTFOLIO_MAX_TRADE_NOTIONAL", "250")))
    args = parser.parse_args()
    run_industry_council(args)


def run_industry_council(args: argparse.Namespace) -> None:
    specs = load_industry_agents(Path(args.agents_file))[: args.industry_agent_count]
    fallback_universe = sync_alpaca_portfolio(
        load_universe(Path(args.universe)),
        snapshot_path=Path(args.portfolio_snapshot),
    )
    latest_decisions: list[PortfolioDecision] = []
    target_reached = False
    today = date.today()

    print(
        f"Starting {len(specs)} industry agents. Target average opportunity score: "
        f"{args.target_average_score:.2f}/10 across top {args.candidate_count}.",
        flush=True,
    )
    print("Pre-open research can pause after target; market-hours research continues perpetually.", flush=True)

    try:
        while True:
            if date.today() != today:
                today = date.today()
                target_reached = False

            clock = market_clock()
            is_open = bool(clock.get("is_open")) if clock else False

            if is_open or not target_reached:
                fallback_universe = sync_alpaca_portfolio(
                    fallback_universe,
                    snapshot_path=Path(args.portfolio_snapshot),
                )
                run_exit_manager(Path(args.exit_plan))
                latest_decisions, average_score = research_council_once(args, specs, fallback_universe)
                target_reached = average_score >= args.target_average_score and not is_open
                if target_reached and not is_open:
                    print(
                        f"Target reached: average opportunity score {average_score:.2f}/10. "
                        "Pausing pre-open research until market state changes.",
                        flush=True,
                    )
                if is_open:
                    if args.execute:
                        execute_execution_plan(Path(args.execution_plan))
                        execute_exit_plan(Path(args.exit_plan))
                    else:
                        execute_at_open(args, latest_decisions)

            if clock:
                next_open = clock.get("next_open", "<unknown>")
                print(f"Market clock: is_open={is_open}, next_open={next_open}", flush=True)
            else:
                print("Market clock unavailable; continuing local workflow.", flush=True)

            sleep_seconds = args.clock_interval_seconds if target_reached else args.research_interval_minutes * 60
            time.sleep(max(5.0, sleep_seconds))
    except KeyboardInterrupt:
        print("\nStopped industry council.", flush=True)


def research_council_once(
    args: argparse.Namespace,
    specs: list[IndustryAgentSpec],
    fallback_universe,
) -> tuple[list[PortfolioDecision], float]:
    print(f"\n[{datetime.now(UTC).isoformat()}] Running industry research council.", flush=True)
    discovered = discover_symbols_by_agent(specs, args.discover_per_industry)
    results = []
    with ThreadPoolExecutor(max_workers=max(1, len(specs))) as pool:
        futures = {
            pool.submit(run_industry_agent, args, spec, discovered.get(spec.name, ()), fallback_universe): spec
            for spec in specs
        }
        for future in as_completed(futures):
            results.append(future.result())

    decisions = merge_decisions(results)
    print_council_summary(results)
    print_decisions(decisions)

    save_decision_book(
        Path(args.decision_book),
        decisions,
        {
            "workflow": "industry_council",
            "industry_agents": [spec.display_name for spec in specs],
            "target_average_score": args.target_average_score,
            "candidate_count": args.candidate_count,
        },
    )
    active, disposed = record_research_cycle(
        ledger_path=Path(args.research_ledger),
        memory_path=Path(args.research_memory),
        decisions=decisions,
        min_memory_score=args.memory_min_score,
    )
    average_score = record_opportunity_scores(
        Path(args.score_ledger),
        decisions,
        candidate_count=args.candidate_count,
    )
    record_agent_scores(
        Path(args.agent_ledger),
        results,
        candidate_count=args.candidate_count,
    )
    settings = execution_settings()
    account = execution_account()
    execution_plan = build_agent_quota_execution_plan(results, account, settings)
    record_execution_plan(Path(args.execution_plan), execution_plan)
    print(
        f"Recorded council CSVs: active_memory={active}, disposed_from_memory={disposed}, "
        f"average_top_score={average_score:.2f}/10.",
        flush=True,
    )
    return decisions, average_score


def monitor_exits(args: argparse.Namespace) -> None:
    print("Starting post-trade exit monitor. Press Ctrl+C to stop.", flush=True)
    try:
        while True:
            run_exit_manager(Path(args.exit_plan))
            execute_exit_plan(Path(args.exit_plan))
            time.sleep(max(5.0, args.clock_interval_seconds))
    except KeyboardInterrupt:
        print("\nStopped exit monitor.", flush=True)


def build_agent_quota_execution_plan(
    results: list[IndustryAgentResult],
    account: dict,
    settings: dict,
) -> list[ExecutionPlanRow]:
    capital = account_capital(account)
    total_budget = capital.liquid_capital * settings["buying_power_fraction"]
    exploration_budget = capital.liquid_capital * settings["exploration_budget_fraction"]
    trade_cap = conviction_trade_cap(account, settings)
    agent_budget = total_budget / max(1, len(results))
    agent_exploration_budget = exploration_budget / max(1, len(results))
    capital_note = allocation_note(capital, trade_cap)
    rows: list[ExecutionPlanRow] = []
    for result in results:
        sorted_decisions = sorted(result.decisions, key=opportunity_score, reverse=True)
        high_conviction = [
            decision for decision in sorted_decisions
            if decision.action in {"BUY", "ADD"} and opportunity_score(decision) >= settings["min_opportunity_score"]
        ][: settings["max_approved_trades"]]
        selected_symbols = {decision.symbol for decision in high_conviction}
        exploration = [
            decision for decision in sorted_decisions
            if decision.symbol not in selected_symbols
            and decision.action == "WATCH"
            and opportunity_score(decision) >= settings["exploration_min_score"]
        ][: max(0, settings["min_trades_per_agent"] - len(high_conviction))]
        selected_symbols.update(decision.symbol for decision in exploration)
        quota_fill = [
            decision for decision in sorted_decisions
            if decision.symbol not in selected_symbols
        ][: max(0, settings["min_trades_per_agent"] - len(high_conviction) - len(exploration))]

        for decision in high_conviction:
            notional = min(trade_cap, agent_budget / max(1, len(high_conviction)))
            rows.append(
                execution_row(
                    result,
                    decision,
                    notional,
                    "APPROVED",
                    f"high-conviction agent signal; {capital_note}",
                    "BUY",
                    capital=capital,
                    allocation_note=capital_note,
                )
            )
        for decision in exploration:
            notional = min(
                settings["exploration_max_notional"],
                agent_exploration_budget / max(1, settings["min_trades_per_agent"]),
            )
            rows.append(
                execution_row(
                    result,
                    decision,
                    notional,
                    "EXPLORATION_APPROVED",
                    "daily learning quota from WATCH signal; exploration cap preserved",
                    "BUY",
                    capital=capital,
                    allocation_note=f"exploration capped at ${settings['exploration_max_notional']:,.2f}; {capital_note}",
                )
            )
        for decision in quota_fill:
            notional = min(
                settings["forced_exploration_max_notional"],
                agent_exploration_budget / max(1, settings["min_trades_per_agent"]),
            )
            rows.append(
                execution_row(
                    result,
                    decision,
                    notional,
                    "FORCED_EXPLORATION_APPROVED",
                    "daily learning quota fill from best remaining researched signal; forced cap preserved",
                    "BUY",
                    capital=capital,
                    allocation_note=f"forced exploration capped at ${settings['forced_exploration_max_notional']:,.2f}; {capital_note}",
                )
            )
        for decision in sorted_decisions:
            if decision.symbol in {row.symbol for row in rows if row.agent == result.spec.name}:
                continue
            rows.append(
                execution_row(
                    result,
                    decision,
                    0.0,
                    "REJECTED",
                    f"{decision.action} not selected for agent quota",
                    decision.action,
                    capital=capital,
                    allocation_note=capital_note,
                )
            )
    return sorted(rows, key=lambda row: (row.status != "APPROVED", row.status != "EXPLORATION_APPROVED", -row.opportunity_score))


def execution_row(
    result: IndustryAgentResult,
    decision: PortfolioDecision,
    notional: float,
    status: str,
    reason: str,
    action: str,
    *,
    capital=None,
    allocation_note: str = "",
) -> ExecutionPlanRow:
    from portfolio_model.opportunity import predicted_profit, predicted_return_pct

    return ExecutionPlanRow(
        agent=result.spec.name,
        agent_name=result.spec.display_name,
        industry=result.spec.industry,
        symbol=decision.symbol,
        action=action,
        source_action=decision.action,
        opportunity_score=opportunity_score(decision),
        target_weight=decision.target_weight,
        current_weight=decision.current_weight,
        notional=notional,
        status=status,
        reason=reason,
        predicted_return_pct=predicted_return_pct(decision),
        predicted_profit=predicted_profit(notional, decision),
        cash=getattr(capital, "cash", 0.0),
        buying_power=getattr(capital, "buying_power", 0.0),
        equity=getattr(capital, "equity", 0.0),
        allocation_note=allocation_note,
    )


def run_industry_agent(
    args: argparse.Namespace,
    spec: IndustryAgentSpec,
    discovered_symbols: tuple[str, ...],
    fallback_universe,
) -> IndustryAgentResult:
    symbols = tuple(dict.fromkeys((*spec.symbols, *discovered_symbols)))
    with tempfile.TemporaryDirectory() as temp_dir:
        watchlist = Path(temp_dir) / f"{spec.name}.csv"
        write_watchlist(watchlist, spec.industry, symbols[: args.discover_per_industry])
        scout = OpportunityScout(
            ScoutConfig(
                agents=args.workers_per_industry,
                discover_limit=args.discover_per_industry,
                watchlist_path=watchlist,
            ),
            fallback_universe=fallback_universe,
        )
        result = scout.run()
    return IndustryAgentResult(
        spec=spec,
        decisions=result.decisions,
        researched=result.researched,
        skipped=result.skipped,
        errors=result.errors,
        warnings=result.warnings or [],
    )


def discover_symbols_by_agent(
    specs: list[IndustryAgentSpec],
    discover_per_industry: int,
) -> dict[str, tuple[str, ...]]:
    try:
        assets = AlpacaClient().assets(status="active", asset_class="us_equity")
    except (AlpacaConfigError, OSError):
        return {spec.name: () for spec in specs}

    discovered: dict[str, list[str]] = {spec.name: [] for spec in specs}
    keywords = industry_keywords(specs)
    for asset in assets:
        symbol = str(asset.get("symbol", "")).upper()
        name = str(asset.get("name", "")).lower()
        if not asset.get("tradable") or not symbol or "." in symbol or "/" in symbol:
            continue
        for spec in specs:
            if len(discovered[spec.name]) >= discover_per_industry:
                continue
            agent_keywords = keywords.get(spec.name, ())
            if (
                symbol in spec.symbols
                or spec.industry.lower() in name
                or spec.name.replace("_", " ") in name
                or any(keyword in name for keyword in agent_keywords)
            ):
                discovered[spec.name].append(symbol)
    return {name: tuple(symbols) for name, symbols in discovered.items()}


def industry_keywords(specs: list[IndustryAgentSpec]) -> dict[str, tuple[str, ...]]:
    defaults = {
        "software": (
            "software",
            "cloud",
            "data",
            "analytics",
            "cyber",
            "digital",
            "internet",
            "technology",
            "semiconductor",
            "systems",
            "platform",
        ),
        "energy": (
            "energy",
            "oil",
            "gas",
            "petroleum",
            "drilling",
            "pipeline",
            "midstream",
            "solar",
            "power",
            "uranium",
            "renewable",
            "coal",
        ),
        "consumer_staples": (
            "food",
            "beverage",
            "grocery",
            "consumer",
            "retail",
            "restaurant",
            "household",
            "staples",
            "products",
            "stores",
            "markets",
        ),
        "healthcare": (
            "health",
            "medical",
            "pharma",
            "biotech",
            "therapeutics",
            "hospital",
            "care",
            "diagnostic",
            "surgical",
            "medicine",
            "life sciences",
        ),
        "industrials": (
            "industrial",
            "manufacturing",
            "machinery",
            "aerospace",
            "defense",
            "transport",
            "rail",
            "airline",
            "logistics",
            "shipping",
            "equipment",
            "engineering",
        ),
    }
    return {
        spec.name: defaults.get(spec.name, (spec.industry.lower(),))
        for spec in specs
    }


def load_industry_agents(path: Path) -> list[IndustryAgentSpec]:
    grouped: dict[tuple[str, str, str], list[str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            agent = row["agent"].strip()
            display_name = row.get("agent_name", agent.replace("_", " ").title()).strip()
            key = (agent, display_name, row["industry"].strip())
            grouped.setdefault(key, []).append(row["symbol"].strip().upper())
    return [
        IndustryAgentSpec(name=agent, display_name=display_name, industry=industry, symbols=tuple(symbols))
        for (agent, display_name, industry), symbols in grouped.items()
    ]


def merge_decisions(results: list[IndustryAgentResult]) -> list[PortfolioDecision]:
    best: dict[str, PortfolioDecision] = {}
    for result in results:
        for decision in result.decisions:
            previous = best.get(decision.symbol)
            if previous is None or opportunity_score(decision) > opportunity_score(previous):
                best[decision.symbol] = decision
    return sorted(best.values(), key=opportunity_score, reverse=True)


def record_opportunity_scores(
    path: Path,
    decisions: list[PortfolioDecision],
    *,
    candidate_count: int,
) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()
    top = sorted(decisions, key=opportunity_score, reverse=True)[:candidate_count]
    average_score = sum(opportunity_score(decision) for decision in top) / len(top) if top else 0.0
    fields = [
            "timestamp",
            "symbol",
            "action",
            "opportunity_score",
            "average_top_score",
            "upside_component",
            "promise_component",
            "sentiment_component",
            "dcf_component",
            "dcf_margin_safety",
            "dcf_intrinsic_value",
            "dcf_reason",
            "composite",
            "target_weight",
            "predicted_return_pct",
            "quality_adjustment",
            "rationale",
        ]
    exists = prepare_csv_for_schema(path, fields)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        for decision in top:
            upside = 0.55 * decision.score.value + 0.45 * decision.score.growth
            promise = 0.55 * decision.score.growth + 0.45 * decision.score.quality
            components = opportunity_components(decision)
            writer.writerow(
                {
                    "timestamp": timestamp,
                    "symbol": decision.symbol,
                    "action": decision.action,
                    "opportunity_score": f"{opportunity_score(decision):.4f}",
                    "average_top_score": f"{average_score:.4f}",
                    "upside_component": f"{10 * upside:.4f}",
                    "promise_component": f"{10 * promise:.4f}",
                    "sentiment_component": f"{10 * decision.score.sentiment:.4f}",
                    "dcf_component": f"{10 * decision.score.dcf:.4f}",
                    "dcf_margin_safety": f"{decision.score.dcf_margin_safety:.4f}",
                    "dcf_intrinsic_value": f"{decision.score.dcf_intrinsic_value:.4f}",
                    "dcf_reason": decision.score.dcf_reason,
                    "composite": f"{decision.score.composite:.4f}",
                    "target_weight": f"{decision.target_weight:.4f}",
                    "predicted_return_pct": f"{predicted_return_pct(decision):.4f}",
                    "quality_adjustment": f"{components['quality_adjustment']:.4f}",
                    "rationale": decision.rationale,
                }
            )
    return average_score


def record_agent_scores(
    path: Path,
    results: list[IndustryAgentResult],
    *,
    candidate_count: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()
    fields = [
        "timestamp",
        "agent",
        "agent_name",
        "industry",
        "symbol",
        "rank",
        "opportunity_score",
        "agent_average_score",
        "action",
        "composite",
        "value",
        "growth",
        "quality",
        "sentiment",
        "dcf",
        "dcf_margin_safety",
        "dcf_confidence",
        "dcf_intrinsic_value",
        "dcf_reason",
        "target_weight",
        "predicted_return_pct",
        "quality_adjustment",
        "researched",
        "skipped",
        "errors",
        "rationale",
    ]
    exists = prepare_csv_for_schema(path, fields)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        for result in sorted(results, key=lambda item: item.spec.name):
            top = sorted(result.decisions, key=opportunity_score, reverse=True)[:candidate_count]
            average = sum(opportunity_score(decision) for decision in top) / len(top) if top else 0.0
            if not top:
                writer.writerow(
                    {
                        "timestamp": timestamp,
                        "agent": result.spec.name,
                        "agent_name": result.spec.display_name,
                        "industry": result.spec.industry,
                        "symbol": "",
                        "rank": "",
                        "opportunity_score": "0.0000",
                        "agent_average_score": "0.0000",
                        "action": "",
                        "composite": "0.0000",
                        "value": "0.0000",
                        "growth": "0.0000",
                        "quality": "0.0000",
                        "sentiment": "0.0000",
                        "dcf": "0.0000",
                        "dcf_margin_safety": "0.0000",
                        "dcf_confidence": "0.0000",
                        "dcf_intrinsic_value": "0.0000",
                        "dcf_reason": "",
                        "target_weight": "0.0000",
                        "predicted_return_pct": "0.0000",
                        "quality_adjustment": "0.0000",
                        "researched": result.researched,
                        "skipped": result.skipped,
                        "errors": len(result.errors),
                        "rationale": "",
                    }
                )
            for rank, decision in enumerate(top, start=1):
                components = opportunity_components(decision)
                writer.writerow(
                    {
                        "timestamp": timestamp,
                        "agent": result.spec.name,
                        "agent_name": result.spec.display_name,
                        "industry": result.spec.industry,
                        "symbol": decision.symbol,
                        "rank": rank,
                        "opportunity_score": f"{opportunity_score(decision):.4f}",
                        "agent_average_score": f"{average:.4f}",
                        "action": decision.action,
                        "composite": f"{decision.score.composite:.4f}",
                        "value": f"{decision.score.value:.4f}",
                        "growth": f"{decision.score.growth:.4f}",
                        "quality": f"{decision.score.quality:.4f}",
                        "sentiment": f"{decision.score.sentiment:.4f}",
                        "dcf": f"{decision.score.dcf:.4f}",
                        "dcf_margin_safety": f"{decision.score.dcf_margin_safety:.4f}",
                        "dcf_confidence": f"{decision.score.dcf_confidence:.4f}",
                        "dcf_intrinsic_value": f"{decision.score.dcf_intrinsic_value:.4f}",
                        "dcf_reason": decision.score.dcf_reason,
                        "target_weight": f"{decision.target_weight:.4f}",
                        "predicted_return_pct": f"{predicted_return_pct(decision):.4f}",
                        "quality_adjustment": f"{components['quality_adjustment']:.4f}",
                        "researched": result.researched,
                        "skipped": result.skipped,
                        "errors": len(result.errors),
                        "rationale": decision.rationale,
                    }
                )


def prepare_csv_for_schema(path: Path, fields: list[str]) -> bool:
    if not path.exists():
        return False
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        current = next(reader, [])
    if current == fields:
        return True
    archived = path.with_name(f"{path.stem}.legacy-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}{path.suffix}")
    path.rename(archived)
    return False


def print_council_summary(results: list[IndustryAgentResult]) -> None:
    for result in sorted(results, key=lambda item: item.spec.name):
        print(
            f"Agent {result.spec.display_name}: industry={result.spec.industry}, "
            f"researched={result.researched}, skipped={result.skipped}, errors={len(result.errors)}",
            flush=True,
        )
        for warning in result.warnings[:2]:
            print(f"  warning: {warning}", flush=True)
        for error in result.errors[:2]:
            print(f"  error: {error}", flush=True)


def write_watchlist(path: Path, industry: str, symbols: tuple[str, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "industry"])
        writer.writeheader()
        for symbol in symbols:
            writer.writerow({"symbol": symbol, "industry": industry})


def _float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    main()
