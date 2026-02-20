"""CryptoScanner — клиент для CryptoPanic API."""

from __future__ import annotations

import time

import requests


class CryptoPanicClient:
    """Клиент для CryptoPanic API."""

    def __init__(
        self,
        auth_token: str,
        base_url: str,
        timeout: int = 15,
        delay: float = 2.0,
    ) -> None:
        """Если auth_token пуст — check_connection вернёт False."""
        self.auth_token: str = auth_token
        self.base_url: str = base_url.rstrip("/")
        self.timeout: int = timeout
        self.delay: float = delay

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """GET /posts/?auth_token=...&public=true с limit. True если results в ответе."""
        if not self.auth_token:
            return False
        try:
            data = self._request(
                f"{self.base_url}/posts/",
                params={
                    "auth_token": self.auth_token,
                    "public": "true",
                    "page": "1",
                },
            )
            return "results" in data
        except Exception:
            return False

    def get_latest_news(
        self,
        filter_type: str | None = None,
        currencies: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        GET /posts/?auth_token=...&public=true
        filter_type: "rising", "hot", "bullish", "bearish", "important" или None
        currencies: "BTC,ETH" или None
        Пагинация через next URL.
        """
        all_items: list[dict] = []
        url: str | None = f"{self.base_url}/posts/"
        params: dict[str, str] = {
            "auth_token": self.auth_token,
            "public": "true",
            "kind": "news",
            "regions": "en",
        }
        if filter_type:
            params["filter"] = filter_type
        if currencies:
            params["currencies"] = currencies

        page = 0
        while url and len(all_items) < limit:
            page += 1
            data = self._request(url, params=params if page == 1 else None)
            results = data.get("results", [])
            all_items.extend(results)
            url = data.get("next")
            if not results:
                break

        return all_items[:limit]

    def get_important_news(self, limit: int = 50) -> list[dict]:
        """Shortcut: get_latest_news(filter_type='important')."""
        return self.get_latest_news(filter_type="important", limit=limit)

    @staticmethod
    def extract_tickers(post: dict) -> list[str]:
        """Извлечь тикеры из post['currencies'] -> ['BTC', 'ETH']."""
        currencies = post.get("currencies")
        if not currencies:
            return []
        return [c.get("code", "") for c in currencies if c.get("code")]

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(
        self, url: str, params: dict[str, str] | None = None
    ) -> dict:
        """HTTP GET. 429 -> sleep(60). Retry 3x."""
        headers = {"User-Agent": "CryptoScanner/1.0"}
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = requests.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )

                if resp.status_code in (401, 403):
                    raise ValueError(
                        f"CryptoPanic {resp.status_code}: неверный auth_token"
                    )
                if resp.status_code == 429:
                    print("   ⏳ CryptoPanic rate limit, жду 60 сек...")
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
