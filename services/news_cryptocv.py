"""CryptoScanner — клиент для cryptocurrency.cv (бесплатный, без ключа)."""

from __future__ import annotations

import time

import requests


class CryptoCVClient:
    """Клиент для cryptocurrency.cv — бесплатный, без ключа."""

    def __init__(
        self, base_url: str, timeout: int = 15, delay: float = 2.0
    ) -> None:
        self.base_url: str = base_url.rstrip("/")
        self.timeout: int = timeout
        self.delay: float = delay

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """GET /api/news, True если ответ валидный."""
        try:
            data = self._request(f"{self.base_url}")
            return data is not None
        except Exception:
            return False

    def get_latest_news(self, limit: int = 50) -> list[dict]:
        """
        GET /api/news
        Структура ответа НЕИЗВЕСТНА — извлекаем список автоматически.
        """
        raw = self._request(f"{self.base_url}")
        return self._extract_list(raw, limit)

    def search_news(self, query: str, limit: int = 50) -> list[dict]:
        """GET /api/archive?q={query}&limit={limit}."""
        base = self.base_url.replace("/api/news", "/api/archive")
        raw = self._request(base, params={"q": query, "limit": str(limit)})
        return self._extract_list(raw, limit)

    def get_news_by_ticker(self, ticker: str, limit: int = 50) -> list[dict]:
        """GET /api/archive?ticker={ticker}&limit={limit}."""
        base = self.base_url.replace("/api/news", "/api/archive")
        raw = self._request(base, params={"ticker": ticker, "limit": str(limit)})
        return self._extract_list(raw, limit)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(
        self, url: str, params: dict[str, str] | None = None
    ) -> dict | list | None:
        """HTTP GET. User-Agent: CryptoScanner/1.0. Retry 3x. sleep(delay)."""
        headers = {"User-Agent": "CryptoScanner/1.0"}
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = requests.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )

                if resp.status_code == 429:
                    print("   ⏳ cryptocurrency.cv rate limit, жду 60 сек...")
                    time.sleep(60)
                    continue
                if resp.status_code >= 500:
                    if attempt < max_retries:
                        time.sleep(5)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()

                content_type = resp.headers.get("Content-Type", "")
                if "json" in content_type or resp.text.strip().startswith(("{", "[")):
                    return resp.json()

                # Не JSON — вернуть None
                return None

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

        return None

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_list(data: dict | list | None, limit: int) -> list[dict]:
        """Извлечь список из ответа (может быть list, dict с ключом, или None)."""
        if data is None:
            return []
        if isinstance(data, list):
            return data[:limit]
        if isinstance(data, dict):
            for key in ("results", "data", "articles", "news", "items", "body"):
                if key in data and isinstance(data[key], list):
                    return data[key][:limit]
            # Единственный list-ключ
            list_keys = [k for k, v in data.items() if isinstance(v, list)]
            if len(list_keys) == 1:
                return data[list_keys[0]][:limit]
        return []
