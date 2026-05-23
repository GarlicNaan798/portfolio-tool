from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from portfolio_model.alpaca import AlpacaApiError, AlpacaClient, AlpacaConfigError
from portfolio_model.dcf import build_dcf
from portfolio_model.model import EquityInput, PortfolioDecision, PortfolioModel
from portfolio_model.sec import SecClient
from portfolio_model.sentiment import score_texts


RESEARCH_SUB_AGENTS = (
    "price",
    "sec_fundamentals",
    "valuation_metrics",
    "growth_metrics",
    "quality_metrics",
    "news_sentiment",
    "dcf_model",
    "portfolio_context",
)


@dataclass(frozen=True)
class ScoutConfig:
    agents: int = 4
    discover_limit: int = 50
    news_limit: int = 8
    market_feed: str = "iex"
    watchlist_path: Path | None = None


@dataclass(frozen=True)
class ScoutResult:
    decisions: list[PortfolioDecision]
    researched: int
    skipped: int
    errors: list[str]
    warnings: list[str] | None = None
    research_checks: dict[str, dict[str, bool]] | None = None


class OpportunityScout:
    def __init__(
        self,
        config: ScoutConfig | None = None,
        *,
        alpaca: AlpacaClient | None = None,
        sec: SecClient | None = None,
        model: PortfolioModel | None = None,
        fallback_universe: list[EquityInput] | None = None,
    ) -> None:
        self.config = config or ScoutConfig()
        self.alpaca = alpaca
        self.sec = sec or SecClient()
        self.model = model or PortfolioModel()
        self.fallback_universe = {equity.symbol: equity for equity in fallback_universe or []}

    def run(self) -> ScoutResult:
        symbols = self._discover_symbols()
        bars = self._latest_bars(symbols)
        warnings = []
        if symbols and not bars:
            warnings.append("latest bars unavailable; using fallback prices where available")
        industry_map = self._industry_map()

        researched = []
        research_checks = {}
        errors = []
        with ThreadPoolExecutor(max_workers=max(1, self.config.agents)) as pool:
            futures = {
                pool.submit(self._research_symbol, symbol, bars.get(symbol), industry_map.get(symbol, "Unknown")): symbol
                for symbol in symbols
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    researched_item = future.result()
                except Exception as exc:
                    errors.append(f"{symbol}: {exc}")
                    continue
                if researched_item is not None:
                    equity, checks = researched_item
                    researched.append(equity)
                    research_checks[symbol] = checks
                    missing = [name for name, passed in checks.items() if not passed]
                    if missing:
                        warnings.append(f"{symbol} incomplete research checks: {', '.join(missing)}")

        return ScoutResult(
            decisions=self.model.decide(researched),
            researched=len(researched),
            skipped=max(0, len(symbols) - len(researched)),
            errors=errors[:20],
            warnings=warnings[:50],
            research_checks=research_checks,
        )

    def _discover_symbols(self) -> list[str]:
        watchlist = list(self._industry_map().keys())
        if watchlist:
            return watchlist[: self.config.discover_limit]

        try:
            alpaca = self._alpaca()
            assets = alpaca.assets(status="active", asset_class="us_equity")
        except AlpacaConfigError:
            return []

        symbols = []
        for asset in assets:
            if not asset.get("tradable"):
                continue
            symbol = str(asset.get("symbol", "")).upper()
            if symbol and "." not in symbol and "/" not in symbol:
                symbols.append(symbol)
            if len(symbols) >= self.config.discover_limit:
                break
        return symbols

    def _research_symbol(self, symbol: str, bar: dict | None, industry: str) -> tuple[EquityInput, dict[str, bool]] | None:
        fallback = self.fallback_universe.get(symbol)
        price = _bar_price(bar) or (fallback.price if fallback else None)
        fundamentals = self.sec.fundamentals_for_symbol(symbol, price)
        if fundamentals is None or price is None:
            return None

        news_items = self._news(symbol)
        texts = [
            f"{item.get('headline', '')} {item.get('summary', '')}"
            for item in news_items
        ]
        sentiment, confidence = score_texts(texts)
        dcf = build_dcf(
            price=price,
            revenue_yoy=fundamentals.revenue_yoy,
            eps_yoy=fundamentals.eps_yoy,
            debt_to_equity=fundamentals.debt_to_equity,
            market_cap=fundamentals.market_cap,
            free_cash_flow=fundamentals.free_cash_flow,
            fcf_yield=fundamentals.fcf_yield,
        )

        equity = EquityInput(
            symbol=symbol,
            industry=industry,
            price=price,
            pe=fundamentals.pe,
            pb=fundamentals.pb,
            fcf_yield=fundamentals.fcf_yield,
            revenue_yoy=fundamentals.revenue_yoy,
            eps_yoy=fundamentals.eps_yoy,
            gross_margin=fundamentals.gross_margin,
            debt_to_equity=fundamentals.debt_to_equity,
            sentiment=sentiment,
            sentiment_confidence=confidence,
            current_weight=fallback.current_weight if fallback else 0.0,
            holding_days=fallback.holding_days if fallback else 0,
            market_cap=fundamentals.market_cap,
            free_cash_flow=fundamentals.free_cash_flow,
            dcf_score=dcf.score,
            dcf_margin_safety=dcf.margin_of_safety,
            dcf_confidence=dcf.confidence,
            dcf_intrinsic_value=dcf.intrinsic_value_per_share,
            dcf_reason=dcf.reason,
        )
        return equity, research_sub_agent_checks(equity, news_items)

    def _latest_bars(self, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        try:
            return self._alpaca().latest_bars(symbols, feed=self.config.market_feed)
        except (AlpacaApiError, AlpacaConfigError, OSError) as exc:
            print(f"Market data warning: {exc}", flush=True)
            return {}

    def _news(self, symbol: str) -> list[dict]:
        try:
            return self._alpaca().news([symbol], limit=self.config.news_limit)
        except (AlpacaApiError, AlpacaConfigError, OSError):
            return []

    def _industry_map(self) -> dict[str, str]:
        if not self.config.watchlist_path or not self.config.watchlist_path.exists():
            return {}
        with self.config.watchlist_path.open(newline="", encoding="utf-8") as handle:
            rows = csv.DictReader(handle)
            return {
                row["symbol"].strip().upper(): row.get("industry", "Unknown").strip() or "Unknown"
                for row in rows
                if row.get("symbol")
            }

    def _alpaca(self) -> AlpacaClient:
        if self.alpaca is None:
            self.alpaca = AlpacaClient()
        return self.alpaca


def _bar_price(bar: dict | None) -> float | None:
    if not bar:
        return None
    for key in ("c", "close"):
        if key in bar and bar[key] is not None:
            return float(bar[key])
    return None


def research_sub_agent_checks(equity: EquityInput, news_items: list[dict]) -> dict[str, bool]:
    checks = {
        "price": equity.price > 0,
        "sec_fundamentals": equity.pe > 0 and equity.pb > 0,
        "valuation_metrics": equity.pe > 0 and equity.pb > 0 and equity.fcf_yield >= 0,
        "growth_metrics": equity.revenue_yoy != 0 or equity.eps_yoy != 0,
        "quality_metrics": equity.gross_margin > 0 and equity.debt_to_equity >= 0,
        "news_sentiment": bool(news_items) and equity.sentiment_confidence > 0,
        "dcf_model": equity.dcf_confidence > 0 and equity.dcf_intrinsic_value > 0,
        "portfolio_context": equity.current_weight >= 0 and equity.holding_days >= 0,
    }
    return {name: checks[name] for name in RESEARCH_SUB_AGENTS}
