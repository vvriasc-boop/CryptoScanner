"""CryptoScanner — извлечение событий из новостей через Groq AI."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

# Допустимые значения event_type
VALID_EVENT_TYPES: set[str] = {
    "listing", "delisting", "burn", "unlock", "fork",
    "launch", "partnership", "airdrop", "governance", "funding", "other",
}

# Допустимые значения importance
VALID_IMPORTANCE: set[str] = {"high", "medium", "low"}


class EventExtractor:
    """Извлечение структурированных событий из новостей через Groq AI."""

    def __init__(
        self,
        api_key: str,
        api_url: str,
        model: str,
        delay: float = 1.0,
        timeout: int = 30,
    ) -> None:
        self.api_key: str = api_key
        self.api_url: str = api_url
        self.model: str = model
        self.delay: float = delay
        self.timeout: int = timeout
        self.prompt: str = self._load_prompt()

    def _load_prompt(self) -> str:
        """Читает prompts/extract_events.md."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "extract_events.md"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Промпт не найден: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """Простой запрос к Groq. True если ответ OK."""
        if not self.api_key:
            return False
        try:
            resp = self._call_groq("Respond with exactly: OK")
            return "OK" in resp
        except Exception:
            return False

    def extract_events(self, news_items: list[dict]) -> list[dict]:
        """
        Основной метод:
        1. Разбивает на чанки по 30
        2. Для каждого чанка: формат -> Groq -> парсинг -> валидация
        3. Возвращает список валидных событий
        """
        if not news_items:
            return []

        chunk_size = 30
        all_events: list[dict] = []

        for i in range(0, len(news_items), chunk_size):
            chunk = news_items[i : i + chunk_size]
            chunk_num = i // chunk_size + 1
            total_chunks = (len(news_items) + chunk_size - 1) // chunk_size
            print(f"   Чанк {chunk_num}/{total_chunks} ({len(chunk)} новостей):"
                  f" отправляю в Groq...")

            try:
                user_msg = self._format_news_for_prompt(chunk)
                response_text = self._call_groq(user_msg)
                raw_events = self._parse_response(response_text)

                valid_events: list[dict] = []
                for raw_ev in raw_events:
                    ev = self._validate_event(raw_ev)
                    if ev:
                        # Скорректировать news_index на глобальный offset
                        if ev.get("news_index") is not None:
                            ev["news_index"] = ev["news_index"] + i
                        valid_events.append(ev)

                all_events.extend(valid_events)
                print(f"   ✅ Извлечено событий: {len(valid_events)}")

            except Exception as e:
                print(f"   ❌ Ошибка чанка {chunk_num}: {e}")

        return all_events

    # ------------------------------------------------------------------
    # Форматирование
    # ------------------------------------------------------------------

    def _format_news_for_prompt(self, news_items: list[dict]) -> str:
        """
        Формат:
        0. [BTC, ETH] "Binance Will List XYZ" (coindesk.com) url
        """
        lines: list[str] = []
        for idx, item in enumerate(news_items):
            tickers = item.get("tickers", [])
            tickers_str = f"[{', '.join(tickers)}]" if tickers else "[?]"
            title = item.get("title", "")
            domain = item.get("domain", item.get("source", ""))
            url = item.get("url", "")
            lines.append(f'{idx}. {tickers_str} "{title}" ({domain}) {url}')
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Groq API
    # ------------------------------------------------------------------

    def _call_groq(self, user_message: str) -> str:
        """
        POST к Groq chat completions.
        Возвращает текст ответа.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.1,
            "max_tokens": 4000,
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = requests.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )

                if resp.status_code == 401:
                    raise ValueError("Groq 401: неверный API ключ")
                if resp.status_code == 429:
                    print("   ⏳ Groq rate limit, жду 60 сек...")
                    time.sleep(60)
                    continue
                if resp.status_code >= 500:
                    if attempt < max_retries:
                        time.sleep(5)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                body = resp.json()
                choices = body.get("choices", [])
                if not choices:
                    return ""
                return choices[0].get("message", {}).get("content", "")

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

        return ""

    # ------------------------------------------------------------------
    # Парсинг ответа
    # ------------------------------------------------------------------

    def _parse_response(self, response_text: str) -> list[dict]:
        """
        Извлечь JSON-массив из ответа:
        1. json.loads
        2. Если ошибка — regex [...] из текста
        3. Если всё ещё ошибка — []
        """
        text = response_text.strip()

        # Попытка 1: прямой парсинг
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                # Может быть {"events": [...]}
                for key in ("events", "data", "results"):
                    if key in parsed and isinstance(parsed[key], list):
                        return parsed[key]
                return []
        except json.JSONDecodeError:
            pass

        # Попытка 2: regex для массива
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        return []

    # ------------------------------------------------------------------
    # Валидация
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_event(event: dict) -> dict | None:
        """
        Проверить обязательные поля, нормализовать значения.
        Вернуть None если невалидный.
        """
        if not isinstance(event, dict):
            return None

        title = event.get("title")
        coin_symbol = event.get("coin_symbol")
        event_type = event.get("event_type")

        if not title or not coin_symbol or not event_type:
            return None

        # Нормализация
        coin_symbol = str(coin_symbol).upper().strip()
        event_type = str(event_type).lower().strip()
        if event_type not in VALID_EVENT_TYPES:
            event_type = "other"

        importance = str(event.get("importance", "medium")).lower().strip()
        if importance not in VALID_IMPORTANCE:
            importance = "medium"

        # date_event — проверка формата YYYY-MM-DD
        date_event = event.get("date_event")
        if date_event:
            date_event = str(date_event).strip()
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_event):
                date_event = None

        # news_index
        news_index = event.get("news_index")
        if news_index is not None:
            try:
                news_index = int(news_index)
            except (ValueError, TypeError):
                news_index = None

        return {
            "title": str(title).strip()[:100],
            "coin_symbol": coin_symbol,
            "event_type": event_type,
            "date_event": date_event,
            "importance": importance,
            "source_title": str(event.get("source_title", "")).strip(),
            "source_url": str(event.get("source_url", "")).strip(),
            "news_index": news_index,
        }
