from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


SEC_BASE_URL = "https://data.sec.gov"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


@dataclass(frozen=True)
class AnnualFundamentals:
    revenue: float | None
    revenue_yoy: float
    eps_yoy: float
    gross_margin: float
    debt_to_equity: float
    pb: float
    pe: float
    fcf_yield: float
    market_cap: float = 0.0
    free_cash_flow: float = 0.0


class SecClient:
    def __init__(self, user_agent: str | None = None, timeout_seconds: int = 30) -> None:
        self.user_agent = user_agent or os.getenv(
            "SEC_USER_AGENT",
            "portfolio-tool/0.1 contact@example.com",
        )
        self.timeout_seconds = timeout_seconds
        self.cache_dir = Path(os.getenv("PORTFOLIO_SEC_CACHE_DIR", "state/sec_cache"))

    def cik_for_symbol(self, symbol: str) -> str | None:
        symbol = symbol.upper()
        for company in self._company_tickers().values():
            if company.get("ticker", "").upper() == symbol:
                return f"{int(company['cik_str']):010d}"
        return None

    def company_facts(self, cik: str) -> dict[str, Any]:
        return self._get_json(f"{SEC_BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json")

    def fundamentals_for_symbol(self, symbol: str, price: float | None) -> AnnualFundamentals | None:
        cik = self.cik_for_symbol(symbol)
        if not cik:
            return None
        facts = self.company_facts(cik)
        gaap = facts.get("facts", {}).get("us-gaap", {})

        revenue = _annual_values(gaap, ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"])
        eps = _annual_values(gaap, ["EarningsPerShareDiluted", "EarningsPerShareBasic"])
        gross_profit = _annual_values(gaap, ["GrossProfit"])
        liabilities = _instant_values(gaap, ["Liabilities"])
        equity = _instant_values(gaap, ["StockholdersEquity"])
        shares = _instant_values(gaap, ["EntityCommonStockSharesOutstanding"])
        operating_cash = _annual_values(gaap, ["NetCashProvidedByUsedInOperatingActivities"])
        capex = _annual_values(gaap, ["PaymentsToAcquirePropertyPlantAndEquipment"])

        latest_revenue = revenue[-1] if revenue else None
        prior_revenue = revenue[-2] if len(revenue) > 1 else None
        latest_eps = eps[-1] if eps else None
        prior_eps = eps[-2] if len(eps) > 1 else None
        latest_gross_profit = gross_profit[-1] if gross_profit else None
        latest_liabilities = liabilities[-1] if liabilities else None
        latest_equity = equity[-1] if equity else None
        latest_shares = shares[-1] if shares else None
        latest_operating_cash = operating_cash[-1] if operating_cash else None
        latest_capex = capex[-1] if capex else None

        if latest_revenue is None or latest_equity is None or latest_equity <= 0:
            return None

        market_cap = (price or 0.0) * latest_shares if price and latest_shares else None
        free_cash_flow = None
        if latest_operating_cash is not None and latest_capex is not None:
            free_cash_flow = latest_operating_cash - abs(latest_capex)

        return AnnualFundamentals(
            revenue=latest_revenue,
            revenue_yoy=_growth(latest_revenue, prior_revenue),
            eps_yoy=_growth(latest_eps, prior_eps),
            gross_margin=_ratio(latest_gross_profit, latest_revenue),
            debt_to_equity=_ratio(latest_liabilities, latest_equity),
            pb=_ratio(market_cap, latest_equity) or 99.0,
            pe=_ratio(price, latest_eps) if price and latest_eps and latest_eps > 0 else 99.0,
            fcf_yield=_ratio(free_cash_flow, market_cap) if free_cash_flow and market_cap else 0.0,
            market_cap=market_cap or 0.0,
            free_cash_flow=free_cash_flow or 0.0,
        )

    @lru_cache(maxsize=1)
    def _company_tickers(self) -> dict[str, Any]:
        return self._get_json(SEC_TICKERS_URL)

    def _get_json(self, url: str) -> dict[str, Any]:
        cache_path = self._cache_path(url)
        request = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = response.read().decode("utf-8")
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(payload, encoding="utf-8")
                return json.loads(payload)
            except URLError as exc:
                last_error = exc
                time.sleep(0.5 * (attempt + 1))

        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        if last_error:
            raise last_error
        raise RuntimeError(f"SEC request failed for {url}")

    def _cache_path(self, url: str) -> Path:
        safe_name = (
            url.replace("https://", "")
            .replace("http://", "")
            .replace("/", "_")
            .replace("?", "_")
            .replace("&", "_")
            .replace("=", "_")
        )
        return self.cache_dir / f"{safe_name}.json"


def _annual_values(gaap: dict[str, Any], concepts: list[str]) -> list[float]:
    return _values(gaap, concepts, duration=True)


def _instant_values(gaap: dict[str, Any], concepts: list[str]) -> list[float]:
    return _values(gaap, concepts, duration=False)


def _values(gaap: dict[str, Any], concepts: list[str], *, duration: bool) -> list[float]:
    rows = []
    for concept in concepts:
        units = gaap.get(concept, {}).get("units", {})
        for unit_rows in units.values():
            for row in unit_rows:
                if row.get("form") != "10-K" or "fy" not in row or "val" not in row:
                    continue
                has_start = "start" in row
                if duration != has_start:
                    continue
                rows.append((int(row["fy"]), float(row["val"])))
        if rows:
            break
    deduped = {}
    for year, value in rows:
        deduped[year] = value
    return [value for _, value in sorted(deduped.items())[-4:]]


def _growth(current: float | None, prior: float | None) -> float:
    if current is None or prior is None or prior == 0:
        return 0.0
    return (current - prior) / abs(prior)


def _ratio(numerator: float | None, denominator: float | None) -> float:
    if numerator is None or denominator is None or denominator == 0:
        return 0.0
    return numerator / denominator
