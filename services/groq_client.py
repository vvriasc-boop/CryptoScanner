"""CryptoScanner — async AI client with provider rotation."""

import asyncio
import json
import logging
import os
import time

import httpx

import config  # noqa: F401 — triggers load_dotenv()

logger = logging.getLogger("crypto_scanner.ai")


class GroqAPIError(Exception):
    pass


PROVIDERS = [
    {
        "name": "groq",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
        "rpm": 30,
    },
    {
        "name": "cohere",
        "url": "https://api.cohere.com/compatibility/v1/chat/completions",
        "key_env": "COHERE_API_KEY",
        "model": "command-a-03-2025",
        "rpm": 20,
    },
    {
        "name": "cerebras",
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "key_env": "CEREBRAS_API_KEY",
        "model": "llama3.1-8b",
        "rpm": 30,
    },
    {
        "name": "sambanova",
        "url": "https://api.sambanova.ai/v1/chat/completions",
        "key_env": "SAMBANOVA_API_KEY",
        "model": "Meta-Llama-3.3-70B-Instruct",
        "rpm": 30,
    },
    {
        "name": "github",
        "url": "https://models.inference.ai.azure.com/chat/completions",
        "key_env": "GITHUB_PAT",
        "model": "Meta-Llama-3.3-70B-Instruct",
        "rpm": 15,
    },
]

# --- Module-level state ---
_current_provider_idx: int = 0
_provider_cooldowns: dict = {}    # {"groq": timestamp_when_available}
_disabled_providers: set = set()  # {"github"} — invalid key


def _is_available(name: str) -> bool:
    if name in _disabled_providers:
        return False
    return time.time() >= _provider_cooldowns.get(name, 0)


def _set_cooldown(name: str, seconds: int = 60):
    _provider_cooldowns[name] = time.time() + seconds


# Build active providers (have API keys) at import time
_active_providers: list[dict] = []
for _p in PROVIDERS:
    if os.getenv(_p["key_env"], ""):
        _active_providers.append(_p)
    else:
        logger.info(f"AI [{_p['name']}] no key ({_p['key_env']}) — skipped")

if not _active_providers:
    logger.warning("No AI providers configured — AI calls will fail")
else:
    logger.info(f"AI providers: {', '.join(p['name'] for p in _active_providers)}")


async def call_groq(
    prompt: str,
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.1,
    max_tokens: int = 500,
    timeout: int = 30,
) -> str:
    """AI request with provider rotation. Raises GroqAPIError on total failure."""
    global _current_provider_idx

    if not _active_providers:
        raise GroqAPIError("No AI providers configured")

    available = [p for p in _active_providers if p["name"] not in _disabled_providers]
    if not available:
        raise GroqAPIError("All AI providers disabled (bad keys)")

    last_error = None

    for round_num in range(3):
        tried = 0

        for _ in range(len(_active_providers)):
            idx = _current_provider_idx % len(_active_providers)
            prov = _active_providers[idx]
            name = prov["name"]

            if not _is_available(name):
                _current_provider_idx = idx + 1
                continue

            tried += 1
            api_key = os.getenv(prov["key_env"], "")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            payload = {
                "model": prov["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(prov["url"], headers=headers, json=payload)

                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    logger.info(f"AI [{name}] 200 (T={temperature})")
                    _current_provider_idx = idx + 1  # round-robin
                    return content

                if resp.status_code == 429:
                    logger.warning(f"AI [{name}] 429 → cooldown 60s, switching")
                    _set_cooldown(name, 60)
                    _current_provider_idx = idx + 1
                    continue

                if resp.status_code == 401:
                    logger.warning(f"AI [{name}] 401 → disabled (bad key)")
                    _disabled_providers.add(name)
                    _current_provider_idx = idx + 1
                    continue

                if resp.status_code in (500, 502, 503):
                    logger.warning(f"AI [{name}] {resp.status_code} → switching")
                    _current_provider_idx = idx + 1
                    last_error = f"{name} HTTP {resp.status_code}"
                    continue

                last_error = f"{name} HTTP {resp.status_code}"
                logger.warning(f"AI [{name}] {resp.status_code}")
                _current_provider_idx = idx + 1

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"AI [{name}] timeout → switching")
                _current_provider_idx = idx + 1
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                last_error = e
                logger.error(f"AI [{name}] parse error: {e}")
                _current_provider_idx = idx + 1

        if tried == 0:
            non_disabled = [p for p in _active_providers
                            if p["name"] not in _disabled_providers]
            if not non_disabled:
                break
            earliest = min(_provider_cooldowns.get(p["name"], 0)
                           for p in non_disabled)
            wait = max(1, earliest - time.time() + 0.5)
            logger.info(
                f"All AI providers in cooldown, sleep {wait:.0f}s "
                f"(round {round_num + 1}/3)"
            )
            await asyncio.sleep(wait)

    raise GroqAPIError(f"All AI providers failed after 3 rounds: {last_error}")
