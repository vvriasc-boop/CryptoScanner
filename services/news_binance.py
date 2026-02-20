"""CryptoScanner — клиент для Binance Announcements."""

from __future__ import annotations

import time

import requests

# catalogId констант Binance CMS
CATALOG_LISTING: int = 48
CATALOG_LATEST: int = 49
CATALOG_DELISTING: int = 131


class BinanceAnnouncementsClient:
    """Клиент для Binance Announcements (внутренний CMS API)."""

    QUERY_URL: str = (
        "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
    )
    # Реалистичный User-Agent
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, timeout: int = 15, delay: float = 2.0) -> None:
        self.timeout: int = timeout
        self.delay: float = delay

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """POST запрос с pageSize=1. True если ответ валидный."""
        try:
            data = self._request(CATALOG_LISTING, page=1, page_size=1)
            return data is not None
        except Exception:
            return False

    def get_listings(
        self, page: int = 1, page_size: int = 20
    ) -> list[dict]:
        """catalogId=48 (New Cryptocurrency Listing)."""
        return self._fetch_articles(CATALOG_LISTING, page, page_size)

    def get_delistings(
        self, page: int = 1, page_size: int = 20
    ) -> list[dict]:
        """catalogId=131 (Delisting)."""
        return self._fetch_articles(CATALOG_DELISTING, page, page_size)

    def get_latest_news(
        self, page: int = 1, page_size: int = 20
    ) -> list[dict]:
        """catalogId=49 (Latest News)."""
        return self._fetch_articles(CATALOG_LATEST, page, page_size)

    # ------------------------------------------------------------------
    # Внутренние
    # ------------------------------------------------------------------

    def _fetch_articles(
        self, catalog_id: int, page: int, page_size: int
    ) -> list[dict]:
        """Извлечь список статей из ответа."""
        raw = self._request(catalog_id, page, page_size)
        if raw is None:
            return []
        return self._extract_articles(raw)

    @staticmethod
    def _extract_articles(data: dict | list) -> list[dict]:
        """
        Извлечь статьи из ответа Binance CMS.
        Структура может быть:
        - {"data": {"catalogs": [{"articles": [...]}]}}
        - {"data": {"articles": [...]}}
        - {"data": [...]}
        """
        if isinstance(data, list):
            return data

        if not isinstance(data, dict):
            return []

        d = data.get("data")
        if d is None:
            return []

        # {"data": {"catalogs": [{"articles": [...]}]}}
        if isinstance(d, dict):
            catalogs = d.get("catalogs", [])
            if catalogs and isinstance(catalogs, list):
                for cat in catalogs:
                    articles = cat.get("articles", [])
                    if articles:
                        return articles

            # {"data": {"articles": [...]}}
            articles = d.get("articles", [])
            if articles:
                return articles

        # {"data": [...]}
        if isinstance(d, list):
            return d

        return []

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(
        self, catalog_id: int, page: int, page_size: int
    ) -> dict | None:
        """
        POST запрос к Binance CMS API.
        Если POST не работает — попробовать GET альтернативу.
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
        }
        payload = {
            "type": 1,
            "pageNo": page,
            "pageSize": page_size,
            "catalogId": catalog_id,
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = requests.post(
                    self.QUERY_URL,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )

                if resp.status_code == 429:
                    print("   ⏳ Binance rate limit, жду 60 сек...")
                    time.sleep(60)
                    continue
                if resp.status_code in (403, 404):
                    # POST заблокирован — пробуем GET fallback
                    return self._request_get_fallback(catalog_id)
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

        return None

    def _request_get_fallback(self, catalog_id: int) -> dict | None:
        """GET fallback если POST заблокирован."""
        alt_url = (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
        )
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
        }
        params = {
            "type": "1",
            "catalogId": str(catalog_id),
            "pageNo": "1",
            "pageSize": "20",
        }
        try:
            time.sleep(self.delay)
            resp = requests.get(
                alt_url, params=params, headers=headers, timeout=self.timeout
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None
