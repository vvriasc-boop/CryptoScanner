"""CryptoScanner — GraphQL-клиент для Snapshot governance."""

from __future__ import annotations

import time

import requests


class SnapshotClient:
    """GraphQL-клиент для Snapshot governance."""

    def __init__(self, url: str, timeout: int, delay: float) -> None:
        """Ключ не нужен. delay рекомендуется 1.0 сек."""
        self.url: str = url
        self.timeout: int = timeout
        self.delay: float = delay

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """Простой запрос proposals(first:1). True если ответ валидный."""
        query = """
        query {
            proposals(first: 1, orderBy: "created", orderDirection: desc) {
                id
            }
        }
        """
        try:
            data = self._request(query)
            return "proposals" in data.get("data", {})
        except Exception:
            return False

    def get_active_proposals(
        self, spaces: list[str], limit: int = 50
    ) -> list[dict]:
        """
        Активные proposals по списку spaces.
        Возвращает [{id, title, choices, start, end, scores, scores_total,
                      votes, space_id, space_name}].
        """
        spaces_str = ", ".join(f'"{s}"' for s in spaces)
        query = f"""
        query {{
            proposals(
                first: {limit},
                where: {{
                    space_in: [{spaces_str}],
                    state: "active"
                }},
                orderBy: "created",
                orderDirection: desc
            ) {{
                id
                title
                choices
                start
                end
                state
                scores
                scores_total
                votes
                space {{ id name }}
            }}
        }}
        """
        data = self._request(query)
        proposals_raw = data.get("data", {}).get("proposals", [])
        return [self._parse_proposal(p) for p in proposals_raw]

    def get_closed_proposals(
        self, spaces: list[str], limit: int = 20
    ) -> list[dict]:
        """Недавно закрытые proposals для анализа результатов."""
        spaces_str = ", ".join(f'"{s}"' for s in spaces)
        query = f"""
        query {{
            proposals(
                first: {limit},
                where: {{
                    space_in: [{spaces_str}],
                    state: "closed"
                }},
                orderBy: "end",
                orderDirection: desc
            ) {{
                id
                title
                choices
                scores
                scores_total
                votes
                state
                space {{ id name }}
                start
                end
            }}
        }}
        """
        data = self._request(query)
        proposals_raw = data.get("data", {}).get("proposals", [])
        return [self._parse_proposal(p) for p in proposals_raw]

    # ------------------------------------------------------------------
    # Внутренние
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_proposal(raw: dict) -> dict:
        """Нормализация proposal из GraphQL-ответа."""
        space = raw.get("space") or {}
        return {
            "id": raw.get("id", ""),
            "title": raw.get("title", ""),
            "choices": raw.get("choices", []),
            "start_ts": raw.get("start"),
            "end_ts": raw.get("end"),
            "state": raw.get("state", ""),
            "scores": raw.get("scores", []),
            "scores_total": raw.get("scores_total", 0),
            "votes": raw.get("votes", 0),
            "space_id": space.get("id", ""),
            "space_name": space.get("name", ""),
        }

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _request(self, query: str) -> dict:
        """
        POST GraphQL. Content-Type: application/json.
        Body: {"query": query}
        Проверять наличие "errors" в ответе.
        Retry 3 раза при 5xx/timeout.
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "CryptoScanner/1.0",
        }
        payload = {"query": query}

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(self.delay)
                resp = requests.post(
                    self.url, json=payload, headers=headers, timeout=self.timeout
                )

                if resp.status_code == 429:
                    print("   ⏳ Snapshot rate limit, жду 60 сек...")
                    time.sleep(60)
                    continue
                if resp.status_code >= 500:
                    if attempt < max_retries:
                        time.sleep(5)
                        continue
                    resp.raise_for_status()

                resp.raise_for_status()
                body = resp.json()

                if "errors" in body:
                    errors = body["errors"]
                    msg = errors[0].get("message", "unknown") if errors else "unknown"
                    raise ValueError(f"Snapshot GraphQL error: {msg}")

                return body

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
