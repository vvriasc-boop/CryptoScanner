"""CryptoScanner — HTTP-клиент для CoinMarketCal через RapidAPI."""

from __future__ import annotations

import time

import requests


class CoinMarketCalClient:
    """HTTP-клиент для CoinMarketCal через RapidAPI."""

    def __init__(
        self,
        rapidapi_key: str,
        host: str,
        base_url: str,
        timeout: int = 15,
        delay: float = 1.0,
    ) -> None:
        """
        Headers для каждого запроса:
        x-rapidapi-key: {rapidapi_key}
        x-rapidapi-host: {host}
        """
        self.rapidapi_key: str = rapidapi_key
        self.host: str = host
        self.base_url: str = base_url.rstrip("/")
        self.timeout: int = timeout
        self.delay: float = delay

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """Запрос /categories. True если 200 и ответ непустой."""
        if not self.rapidapi_key:
            return False
        try:
            data = self._request("/categories")
            return bool(data)
        except Exception:
            return False

    def get_categories(self) -> list | dict:
        """GET /categories — список категорий событий. Возвращает RAW."""
        return self._request("/categories")

    def get_coins(
        self, page: int = 1, max_results: int = 100
    ) -> list | dict:
        """GET /coins — список монет. Возвращает RAW."""
        return self._request(
            "/coins", params={"page": str(page), "max": str(max_results)}
        )

    def get_events(
        self, page: int = 1, max_results: int = 50, **kwargs: str
    ) -> dict | list:
        """
        GET /events — события.
        kwargs может включать: dateRangeStart, dateRangeEnd,
        coins, categories, sortBy.
        Возвращает RAW ответ — структура неизвестна заранее.
        """
        params: dict[str, str] = {
            "page": str(page),
            "max": str(max_results),
        }
        for key, val in kwargs.items():
            if val:
                params[key] = val
        return self._request("/events", params=params)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(
        self, endpoint: str, params: dict[str, str] | None = None
    ) -> dict | list:
        """
        HTTP GET с retry. Добавляет headers (x-rapidapi-key, x-rapidapi-host).
        429 -> sleep(60), retry. 401/403 -> raise ValueError.
        5xx/timeout -> retry 3 раза.
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            "x-rapidapi-key": self.rapidapi_key,
            "x-rapidapi-host": self.host,
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = requests.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )

                if resp.status_code in (401, 403):
                    raise ValueError(
                        f"CoinMarketCal {resp.status_code}: "
                        f"неверный RAPIDAPI_KEY или нет подписки на CoinMarketCal"
                    )
                if resp.status_code == 429:
                    print("   ⏳ CoinMarketCal rate limit, жду 60 сек...")
                    time.sleep(60)
                    self.delay *= 2
                    continue
                if resp.status_code >= 500:
                    if attempt < max_retries:
                        time.sleep(5)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()

                # Проверка что ответ — JSON
                content_type = resp.headers.get("Content-Type", "")
                if "json" not in content_type and not resp.text.strip().startswith(
                    ("{", "[")
                ):
                    raise ValueError(
                        f"Ответ не JSON. Content-Type: {content_type}. "
                        f"Тело (500 символов): {resp.text[:500]}"
                    )

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

        return []
