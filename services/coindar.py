"""CryptoScanner — HTTP-клиент для Coindar API v2."""

from __future__ import annotations

import time

import requests


# ---------------------------------------------------------------------------
# Утилиты: безопасная конвертация строк Coindar
# ---------------------------------------------------------------------------

def _safe_int(val: str | None) -> int | None:
    """Строку в int. Coindar возвращает всё строками."""
    if not val or not str(val).strip():
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val: str | None) -> float | None:
    """Строку в float."""
    if not val or not str(val).strip():
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Клиент
# ---------------------------------------------------------------------------

class CoindarClient:
    """HTTP-клиент для Coindar API v2."""

    def __init__(
        self, token: str, base_url: str, timeout: int, delay: float
    ) -> None:
        """Инициализация. token может быть пустым — тогда check_connection вернёт False."""
        self.token: str = token
        self.base_url: str = base_url.rstrip("/")
        self.timeout: int = timeout
        self.delay: float = delay

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """Проверка: если token пуст — False. Иначе запрос /tags, True если 200."""
        if not self.token:
            return False
        try:
            self._request("/tags")
            return True
        except Exception:
            return False

    def get_tags(self) -> list[dict]:
        """Все теги. Возвращает [{id: int, name: str}]."""
        raw = self._request("/tags")
        result: list[dict] = []
        for item in raw:
            tag_id = _safe_int(item.get("id"))
            if tag_id is None:
                continue
            result.append({"id": tag_id, "name": item.get("name", "")})
        return result

    def get_coins(self, max_pages: int = 0) -> list[dict]:
        """Все монеты с пагинацией. Остановка: len(result) < page_size."""
        page_size = 100
        page = 1
        all_coins: list[dict] = []

        while True:
            data = self._request(
                "/coins",
                params={"page": str(page), "page_size": str(page_size)},
            )
            if not data:
                break

            for item in data:
                coin_id = _safe_int(item.get("id"))
                if coin_id is None:
                    continue
                all_coins.append({
                    "id": coin_id,
                    "name": item.get("name", ""),
                    "symbol": item.get("symbol", ""),
                    "image_url": item.get("image", ""),
                })

            print(f"   Страница {page}: {len(data)}", end="")
            if page > 1:
                print("", end="")
            print(" |", end="")

            if len(data) < page_size:
                break
            if max_pages and page >= max_pages:
                break
            page += 1

        print()  # новая строка после прогресса
        return all_coins

    def get_events(
        self,
        date_start: str,
        date_end: str,
        coin_ids: list[int] | None = None,
        max_pages: int = 0,
    ) -> list[dict]:
        """События с пагинацией. Возвращает распарсенные через parse_event."""
        page_size = 100
        page = 1
        all_events: list[dict] = []

        while True:
            params: dict[str, str] = {
                "page": str(page),
                "page_size": str(page_size),
                "filter_date_start": date_start,
                "filter_date_end": date_end,
                "sort_by": "date_start",
                "order_by": "0",
            }
            if coin_ids:
                params["filter_coins"] = ",".join(str(c) for c in coin_ids)

            data = self._request("/events", params=params)
            if not data:
                break

            for item in data:
                all_events.append(self.parse_event(item))

            if len(data) < page_size:
                break
            if max_pages and page >= max_pages:
                break
            page += 1

        return all_events

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(
        self, endpoint: str, params: dict[str, str] | None = None
    ) -> list | dict:
        """
        HTTP GET с retry. Добавляет access_token, User-Agent.
        429 -> sleep(60), delay *= 2.  401 -> raise ValueError.
        5xx/timeout -> retry 3 раза.
        """
        url = f"{self.base_url}{endpoint}"
        req_params = dict(params) if params else {}
        req_params["access_token"] = self.token
        headers = {"User-Agent": "CryptoScanner/1.0"}

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = requests.get(
                    url, params=req_params, headers=headers, timeout=self.timeout
                )

                if resp.status_code == 401:
                    raise ValueError(
                        f"Coindar 401 Unauthorized: невалидный токен"
                    )
                if resp.status_code == 429:
                    print("   ⏳ Coindar rate limit, жду 60 сек...")
                    time.sleep(60)
                    self.delay *= 2
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

        return []

    # ------------------------------------------------------------------
    # Парсинг
    # ------------------------------------------------------------------

    @staticmethod
    def parse_event(raw: dict) -> dict:
        """Конвертация: coin_id->int|None, source_reliable->0/1, coin_price_changes->float|None."""
        reliable_str = str(raw.get("source_reliable", "")).lower().strip()
        reliable = 1 if reliable_str in ("true", "1") else 0

        important_str = str(raw.get("important", "")).lower().strip()
        important = 1 if important_str in ("true", "1") else 0

        return {
            "caption": raw.get("caption", ""),
            "source": raw.get("source"),
            "source_reliable": reliable,
            "important": important,
            "date_public": raw.get("date_public"),
            "date_start": raw.get("date_start", ""),
            "date_end": raw.get("date_end") or None,
            "coin_id": _safe_int(raw.get("coin_id")),
            "coin_price_changes": _safe_float(raw.get("coin_price_changes")),
            "tags": raw.get("tags"),
        }
