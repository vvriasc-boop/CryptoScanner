"""CryptoScanner — Google News RSS клиент."""

from __future__ import annotations

import time
import urllib.parse
from datetime import datetime

import feedparser
import requests


class GoogleNewsClient:
    """Парсинг Google News RSS по крипто-запросам.

    Использует requests для загрузки (поддержка прокси, User-Agent),
    feedparser для парсинга XML.
    """

    _USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        base_url: str = "https://news.google.com/rss/search",
        delay: float = 2.0,
        max_total: int = 100,
        timeout: int = 15,
        proxies: dict | None = None,
    ) -> None:
        self.base_url = base_url
        self.delay = delay
        self.max_total = max_total
        self.timeout = timeout
        self.proxies = proxies
        self._session = requests.Session()
        self._session.headers["User-Agent"] = self._USER_AGENT
        if proxies:
            self._session.proxies.update(proxies)

    def check_connection(self) -> bool:
        """Проверка доступности Google News RSS."""
        try:
            url = self._build_url("bitcoin")
            content = self._fetch_rss(url)
            if content is None:
                return False
            feed = feedparser.parse(content)
            return not feed.bozo and len(feed.entries) > 0
        except Exception:
            return False

    def fetch_query(self, query: str, max_items: int = 30) -> list[dict]:
        """Загрузить RSS для одного запроса. Возвращает список entry-dict."""
        url = self._build_url(query)
        content = self._fetch_rss(url)
        if content is None:
            return []

        feed = feedparser.parse(content)
        if feed.bozo:
            return []

        entries: list[dict] = []
        for entry in feed.entries[:max_items]:
            entries.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "published_parsed": entry.get("published_parsed"),
                "source_name": self._extract_source(entry),
                "query": query,
            })
        return entries

    def fetch_all(self, queries: list[str]) -> list[dict]:
        """Загрузить RSS для всех запросов с дедупликацией по title."""
        all_entries: list[dict] = []
        seen_titles: set[str] = set()

        for i, query in enumerate(queries):
            if len(all_entries) >= self.max_total:
                break

            entries = self.fetch_query(query)
            for entry in entries:
                title = entry["title"]
                if title not in seen_titles and len(all_entries) < self.max_total:
                    seen_titles.add(title)
                    all_entries.append(entry)

            if i < len(queries) - 1:
                time.sleep(self.delay)

        return all_entries

    def _fetch_rss(self, url: str) -> str | None:
        """Загрузить RSS через requests. Возвращает XML-строку или None."""
        try:
            resp = self._session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.text
            return None
        except requests.RequestException:
            return None

    def _build_url(self, query: str) -> str:
        """Сформировать URL для Google News RSS."""
        params = urllib.parse.urlencode({
            "q": query,
            "hl": "en",
            "gl": "US",
            "ceid": "US:en",
        })
        return f"{self.base_url}?{params}"

    @staticmethod
    def _extract_source(entry: dict) -> str:
        """Извлечь название источника из entry."""
        # feedparser: source.title или title содержит " - SourceName"
        source = entry.get("source", {})
        if isinstance(source, dict) and source.get("title"):
            return source["title"]
        title = entry.get("title", "")
        if " - " in title:
            return title.rsplit(" - ", 1)[-1]
        return "Google News"

    @staticmethod
    def parse_published(entry: dict) -> str | None:
        """Конвертировать published_parsed в ISO строку."""
        pp = entry.get("published_parsed")
        if pp:
            try:
                dt = datetime(*pp[:6])
                return dt.isoformat()
            except (TypeError, ValueError):
                pass
        # Fallback: published строка
        raw = entry.get("published")
        return str(raw) if raw else None
