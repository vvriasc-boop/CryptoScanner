"""CryptoScanner — получение списка торгуемых USDT Futures токенов Binance."""

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger("crypto_scanner.binance_tokens")

_cached_tokens: list[str] = []
_cache_time: float = 0.0


async def get_futures_tokens(
    http_client: httpx.AsyncClient, exclude: Optional[set] = None,
    cache_ttl: int = 86400,
) -> list[str]:
    """Список USDT Perpetual Futures токенов с Binance.
    Кэш на cache_ttl сек. При ошибке — fallback на кэш."""
    global _cached_tokens, _cache_time

    if _cached_tokens and (time.time() - _cache_time < cache_ttl):
        return _cached_tokens

    try:
        resp = await http_client.get(
            "https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        tokens = {
            s.get("baseAsset", "")
            for s in data.get("symbols", [])
            if s.get("status") == "TRADING"
            and s.get("contractType") == "PERPETUAL"
            and s.get("quoteAsset") == "USDT"
        }
        tokens.discard("")

        if exclude:
            tokens -= exclude

        result = sorted(tokens)
        _cached_tokens, _cache_time = result, time.time()
        logger.info(f"Binance Futures: {len(result)} tokens (excluded {len(exclude or set())})")
        return result

    except httpx.TimeoutException:
        logger.warning("Binance exchangeInfo timeout")
        return _cached_tokens
    except httpx.HTTPStatusError as e:
        logger.warning(f"Binance HTTP {e.response.status_code}")
        return _cached_tokens
    except (KeyError, TypeError) as e:
        logger.warning(f"Binance unexpected response: {e}")
        return _cached_tokens
