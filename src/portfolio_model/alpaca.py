from __future__ import annotations

import json
import os
from urllib.parse import urlencode
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class AlpacaConfigError(RuntimeError):
    pass


class AlpacaApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class AlpacaConfig:
    api_key_id: str
    api_secret_key: str
    base_url: str = "https://paper-api.alpaca.markets"
    data_url: str = "https://data.alpaca.markets"

    @classmethod
    def from_env(cls) -> "AlpacaConfig":
        api_key_id = os.getenv("APCA_API_KEY_ID", "").strip()
        api_secret_key = os.getenv("APCA_API_SECRET_KEY", "").strip()
        base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").strip()
        data_url = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets").strip()
        if not api_key_id or not api_secret_key:
            raise AlpacaConfigError(
                "Set APCA_API_KEY_ID and APCA_API_SECRET_KEY in your environment before using Alpaca."
            )
        return cls(
            api_key_id=api_key_id,
            api_secret_key=api_secret_key,
            base_url=base_url.rstrip("/"),
            data_url=data_url.rstrip("/"),
        )


class AlpacaClient:
    def __init__(self, config: AlpacaConfig | None = None, timeout_seconds: int = 20) -> None:
        self.config = config or AlpacaConfig.from_env()
        self.timeout_seconds = timeout_seconds

    def account(self) -> dict[str, Any]:
        return self._request("GET", "/v2/account")

    def positions(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/v2/positions")
        return response if isinstance(response, list) else []

    def orders(self, *, status: str = "all", limit: int = 50) -> list[dict[str, Any]]:
        query = urlencode({"status": status, "limit": str(limit), "direction": "desc"})
        response = self._request("GET", f"/v2/orders?{query}")
        return response if isinstance(response, list) else []

    def clock(self) -> dict[str, Any]:
        return self._request("GET", "/v2/clock")

    def calendar(self, *, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
        params = {key: value for key, value in {"start": start, "end": end}.items() if value}
        query = f"?{urlencode(params)}" if params else ""
        response = self._request("GET", f"/v2/calendar{query}")
        return response if isinstance(response, list) else []

    def assets(self, *, status: str = "active", asset_class: str = "us_equity") -> list[dict[str, Any]]:
        query = urlencode({"status": status, "asset_class": asset_class})
        response = self._request("GET", f"/v2/assets?{query}")
        return response if isinstance(response, list) else []

    def latest_bars(self, symbols: list[str], *, feed: str = "iex") -> dict[str, Any]:
        if not symbols:
            return {}
        query = urlencode({"symbols": ",".join(symbols), "feed": feed})
        response = self._request("GET", f"/v2/stocks/bars/latest?{query}", data_api=True)
        return response.get("bars", {}) if isinstance(response, dict) else {}

    def historical_bars(
        self,
        symbols: list[str],
        *,
        start: str,
        end: str,
        timeframe: str = "1Day",
        feed: str = "iex",
        adjustment: str = "all",
        limit: int = 10000,
    ) -> dict[str, list[dict[str, Any]]]:
        if not symbols:
            return {}
        all_bars: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
        page_token = None
        while True:
            params = {
                "symbols": ",".join(symbols),
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "feed": feed,
                "adjustment": adjustment,
                "limit": str(limit),
            }
            if page_token:
                params["page_token"] = page_token
            response = self._request("GET", f"/v2/stocks/bars?{urlencode(params)}", data_api=True)
            if not isinstance(response, dict):
                return all_bars
            for symbol, bars in response.get("bars", {}).items():
                all_bars.setdefault(symbol, []).extend(bars)
            page_token = response.get("next_page_token")
            if not page_token:
                return all_bars

    def news(self, symbols: list[str], *, limit: int = 10) -> list[dict[str, Any]]:
        if not symbols:
            return []
        query = urlencode({"symbols": ",".join(symbols), "limit": str(limit)})
        response = self._request("GET", f"/v1beta1/news?{query}", data_api=True)
        return response.get("news", []) if isinstance(response, dict) else []

    def submit_market_order(
        self,
        *,
        symbol: str,
        side: str,
        notional: float,
        qty: float | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        if side not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")
        if notional <= 0 and (qty is None or qty <= 0):
            raise ValueError("notional or qty must be positive")

        body: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        if qty is not None:
            body["qty"] = f"{qty:.6f}".rstrip("0").rstrip(".")
        else:
            body["notional"] = f"{notional:.2f}"
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", "/v2/orders", body)

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        data_api: bool = False,
    ) -> Any:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        base_url = self.config.data_url if data_api else self.config.base_url
        request = Request(
            f"{base_url}{path}",
            data=payload,
            method=method,
            headers={
                "APCA-API-KEY-ID": self.config.api_key_id,
                "APCA-API-SECRET-KEY": self.config.api_secret_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AlpacaApiError(f"Alpaca {method} {path} failed with HTTP {exc.code}: {detail}") from exc
