"""CryptoScanner — клиент Parallel Search API для поиска событий токенов."""

import asyncio
import logging

import httpx

logger = logging.getLogger("crypto_scanner.parallel")


async def search_token_events(
    http_client: httpx.AsyncClient, token: str, api_key: str,
    max_results: int = 5, max_chars: int = 2000, timeout: int = 15,
) -> list[dict]:
    """Поиск событий для токена через Parallel Search API.
    Возвращает [{"url", "title", "excerpt"}]. При ошибке — []."""
    url = "https://api.parallel.ai/v1beta/search"
    headers = {"Content-Type": "application/json", "x-api-key": api_key}
    payload = {
        "objective": (
            f"Find specific upcoming events for {token} cryptocurrency token "
            f"in the next 7 days: token unlocks, burns, hardforks, upgrades, "
            f"partnerships, listings, airdrops, governance votes. "
            f"Only events specific to {token}, not general crypto market."
        ),
        "search_queries": [
            f"{token} token unlock burn schedule 2026",
            f"{token} upcoming event upgrade partnership airdrop",
        ],
        "max_results": max_results,
        "excerpts": {"max_chars_per_result": max_chars},
    }

    try:
        resp = await http_client.post(
            url, headers=headers, json=payload, timeout=timeout
        )
        resp.raise_for_status()
        data = resp.json()

        logger.info(f"Parallel raw response keys: {list(data.keys())}")
        results = data.get("results", [])
        if results:
            logger.info(f"First result keys: {list(results[0].keys())}")

        parsed = []
        for r in results:
            excerpts = r.get("excerpts", r.get("excerpt", ""))
            if isinstance(excerpts, list):
                excerpts = "\n".join(excerpts)
            parsed.append({
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "excerpt": excerpts or "",
            })
        return parsed

    except httpx.TimeoutException:
        logger.warning(f"Parallel timeout for {token}")
        return []
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 429:
            logger.warning(f"Parallel rate limit for {token}, sleep 10s")
            await asyncio.sleep(10)
        elif status in (500, 502, 503):
            logger.warning(f"Parallel server error {status} for {token}")
        elif status == 401:
            logger.error("Parallel API key invalid!")
        else:
            logger.warning(f"Parallel HTTP {status} for {token}")
        return []
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f"Parallel unexpected response for {token}: {e}")
        return []
