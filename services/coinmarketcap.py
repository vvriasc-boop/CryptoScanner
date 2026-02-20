"""CryptoScanner — HTTP-клиент для CoinMarketCap API."""

from __future__ import annotations

import time

import requests


class CoinMarketCapClient:
    """HTTP-клиент для CoinMarketCap API."""

    def __init__(
        self, api_key: str, base_url: str, timeout: int, delay: float
    ) -> None:
        """delay рекомендуется 2.0 сек (30 req/min)."""
        self.api_key: str = api_key
        self.base_url: str = base_url.rstrip("/")
        self.timeout: int = timeout
        self.delay: float = delay

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def check_connection(self) -> dict | None:
        """GET /v1/key/info. Возвращает {plan, credits_used, credits_left} или None."""
        try:
            data = self._request("/v1/key/info")
            if data is None:
                return None
            plan_info = data.get("plan", {})
            usage = data.get("usage", {}).get("current_month", {})
            credit_limit = plan_info.get("credit_limit_monthly", 0)
            credits_used = usage.get("credits_used", 0)
            return {
                "plan": plan_info.get("plan_slug", "unknown"),
                "credits_used": credits_used,
                "credits_left": credit_limit - credits_used,
                "credit_limit": credit_limit,
            }
        except Exception:
            return None

    def get_map(self, limit: int = 500) -> list[dict]:
        """Маппинг: [{id, name, symbol, slug}]. Отсортирован по cmc_rank."""
        data = self._request(
            "/v1/cryptocurrency/map",
            params={"limit": str(limit), "sort": "cmc_rank"},
        )
        if not data:
            return []
        return [
            {
                "id": c["id"],
                "name": c["name"],
                "symbol": c["symbol"],
                "slug": c.get("slug", ""),
            }
            for c in data
            if "id" in c and "symbol" in c
        ]

    def get_quotes(self, symbols: list[str]) -> dict:
        """
        Котировки. Макс 120 символов за раз.
        Разбивать на чанки если больше.
        Возвращает {symbol: {price, volume_24h, market_cap, percent_change_24h}}.
        """
        result: dict = {}
        chunk_size = 120
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i : i + chunk_size]
            symbols_str = ",".join(chunk)
            data = self._request(
                "/v1/cryptocurrency/quotes/latest",
                params={"symbol": symbols_str, "convert": "USD"},
            )
            if not data:
                continue
            for sym, info in data.items():
                # CMC может вернуть массив (дубли символов) или объект
                if isinstance(info, list):
                    info = info[0] if info else {}
                quote = info.get("quote", {}).get("USD", {})
                result[sym] = {
                    "price": quote.get("price"),
                    "volume_24h": quote.get("volume_24h"),
                    "market_cap": quote.get("market_cap"),
                    "percent_change_24h": quote.get("percent_change_24h"),
                }
        return result

    def check_events_available(self) -> tuple[bool, str]:
        """
        Проверить доступен ли /v1/cryptocurrency/events на free tier.
        Возвращает (True/False, описание).
        """
        try:
            data = self._request(
                "/v1/cryptocurrency/events", params={"limit": "1"}
            )
            if data is not None:
                return True, "Events API доступен"
            return False, "Events API вернул пустой ответ"
        except ValueError as e:
            return False, f"Events API недоступен: {e}"
        except requests.HTTPError as e:
            return False, f"Events API недоступен: HTTP {e.response.status_code}"
        except Exception as e:
            return False, f"Events API ошибка: {e}"

    def get_categories(self, limit: int = 20) -> list[dict]:
        """Список категорий."""
        data = self._request(
            "/v1/cryptocurrency/categories", params={"limit": str(limit)}
        )
        if not data:
            return []
        return [
            {
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "num_tokens": c.get("num_tokens", 0),
            }
            for c in data
        ]

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(
        self, endpoint: str, params: dict[str, str] | None = None
    ) -> dict | list | None:
        """
        HTTP GET. Header: X-CMC_PRO_API_KEY.
        Проверяет status.error_code в ответе.
        error_code 1002 (API key invalid) -> raise ValueError.
        error_code 1008 (plan limit) -> warning, return None.
        429 -> sleep(60), retry.
        Извлекает и возвращает поле "data".
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            "User-Agent": "CryptoScanner/1.0",
            "X-CMC_PRO_API_KEY": self.api_key,
            "Accept": "application/json",
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = requests.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )

                if resp.status_code == 429:
                    print("   ⏳ CMC rate limit, жду 60 сек...")
                    time.sleep(60)
                    continue
                if resp.status_code == 403:
                    raise ValueError(
                        f"CMC 403 Forbidden: endpoint недоступен на текущем плане"
                    )
                if resp.status_code >= 500:
                    if attempt < max_retries:
                        time.sleep(5)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                body = resp.json()

                # Проверка CMC status wrapper
                status = body.get("status", {})
                error_code = status.get("error_code", 0)

                if error_code == 1002:
                    raise ValueError("CMC: невалидный API ключ (error_code 1002)")
                if error_code == 1008:
                    print("   ⚠️ CMC: лимит плана достигнут (error_code 1008)")
                    return None
                if error_code != 0:
                    msg = status.get("error_message", "unknown error")
                    raise ValueError(f"CMC error {error_code}: {msg}")

                return body.get("data")

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
