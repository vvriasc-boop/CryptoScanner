"""CryptoScanner — HTTP-клиент для CoinGecko API v3."""

from __future__ import annotations

import time

import requests


class CoinGeckoClient:
    """HTTP-клиент для CoinGecko API v3."""

    def __init__(
        self, api_key: str, base_url: str, timeout: int, delay: float
    ) -> None:
        """delay рекомендуется 2.0 сек (30 calls/min = 1 call/2 sec)."""
        self.api_key: str = api_key
        self.base_url: str = base_url.rstrip("/")
        self.timeout: int = timeout
        self.delay: float = delay

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """GET /ping, True если gecko_says в ответе."""
        try:
            data = self._request("/ping")
            return "gecko_says" in data
        except Exception:
            return False

    def get_coins_list(self) -> list[dict]:
        """Полный список монет. [{id, symbol, name}]. Один запрос, без пагинации."""
        data = self._request("/coins/list")
        return [
            {"id": c["id"], "symbol": c["symbol"], "name": c["name"]}
            for c in data
            if "id" in c and "symbol" in c and "name" in c
        ]

    def get_coin_info(self, coin_id: str) -> dict | None:
        """Детальная информация: categories, description, market_data."""
        try:
            data = self._request(
                f"/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                },
            )
            return data
        except Exception:
            return None

    def get_prices(self, coin_ids: list[str]) -> dict:
        """
        Цены пачкой. Макс 250 ids за раз.
        Если больше — разбить на чанки по 250.
        Возвращает {coin_id: {usd, usd_24h_change, usd_market_cap}}.
        """
        result: dict = {}
        chunk_size = 250
        for i in range(0, len(coin_ids), chunk_size):
            chunk = coin_ids[i : i + chunk_size]
            ids_str = ",".join(chunk)
            data = self._request(
                "/simple/price",
                params={
                    "ids": ids_str,
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_market_cap": "true",
                },
            )
            if isinstance(data, dict):
                result.update(data)
        return result

    def get_categories(self) -> list[dict]:
        """Список категорий. [{category_id, name}]."""
        data = self._request("/coins/categories/list")
        return [
            {"category_id": c.get("category_id", ""), "name": c.get("name", "")}
            for c in data
            if "category_id" in c
        ]

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(
        self, endpoint: str, params: dict[str, str] | None = None
    ) -> dict | list:
        """
        HTTP GET. Header: x-cg-demo-api-key.
        429 -> sleep(60), retry. 5xx -> retry 3 раза.
        sleep(self.delay) после каждого запроса.
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            "User-Agent": "CryptoScanner/1.0",
            "x-cg-demo-api-key": self.api_key,
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = requests.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )

                if resp.status_code == 429:
                    print("   ⏳ CoinGecko rate limit, жду 60 сек...")
                    time.sleep(60)
                    continue
                if resp.status_code >= 500:
                    if attempt < max_retries:
                        time.sleep(5)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                return resp.json()

            except requests.ConnectionError:
                if attempt < max_retries:
                    time.sleep(10)
                    continue
                raise
            except requests.Timeout:
                if attempt < max_retries:
                    time.sleep(5)
                    continue
                raise

        return {}
