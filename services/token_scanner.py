"""CryptoScanner — token scanner: Parallel Search → Groq AI → events_v2."""

import asyncio, json, logging, os, re, traceback  # noqa: E401
from datetime import date, timedelta
import httpx
import config
from database.db import ensure_outcome_tables, make_event_id, save_event
from services.binance_tokens import get_futures_tokens
from services.groq_client import GroqAPIError, call_groq
from services.parallel_client import search_token_events

logger = logging.getLogger("crypto_scanner.token_scanner")
KNOWN_TYPES = {"listing", "launch", "burn", "unlock", "fork", "partnership",
               "airdrop", "governance", "upgrade", "conference", "regulatory", "other"}
_prompt_cache: str = ""


def _load_prompt() -> str:
    global _prompt_cache
    if not _prompt_cache:
        p = os.path.join(os.path.dirname(__file__), "..", "prompts", "extract_token_events.md")
        with open(p, encoding="utf-8") as f:
            _prompt_cache = f.read()
    return _prompt_cache


def _format_search_results(results: list[dict]) -> str:
    return "\n".join(
        f"[{i}] {r.get('title', '')}\nURL: {r.get('url', '')}\n"
        f"Excerpt: {r.get('excerpt', '')}\n"
        for i, r in enumerate(results, 1))


def _is_within_horizon(date_str: str, horizon_days: int) -> bool:
    if not date_str:
        return True
    try:
        d = date.fromisoformat(date_str)
        today = date.today()
        return today - timedelta(days=1) <= d <= today + timedelta(days=horizon_days)
    except (ValueError, TypeError):
        return True


def _parse_events_json(text: str, token: str) -> list[dict]:
    """3-stage: direct → regex [...] → regex {...}."""
    raw = None
    for pattern, wrap in [(None, False), (r"\[.*\]", False), (r"\{.*\}", True)]:
        if raw is not None:
            break
        try:
            if pattern is None:
                raw = json.loads(text)
            else:
                m = re.search(pattern, text, re.DOTALL)
                if m:
                    parsed = json.loads(m.group())
                    raw = [parsed] if wrap else parsed
        except (json.JSONDecodeError, TypeError):
            pass
    if not isinstance(raw, list):
        return []
    valid = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        if not e.get("coin_symbol"):
            e["coin_symbol"] = token
        etype, title = e.get("event_type", ""), e.get("title", "")
        if etype not in KNOWN_TYPES:
            logger.warning(f"Unknown event_type '{etype}' for {token}"); continue
        if len(title) < 5:
            logger.warning(f"Title too short for {token}: '{title}'"); continue
        valid.append(e)
    return valid


async def _process_results(token: str, results: list[dict], db) -> list[dict]:
    prompt = _load_prompt().replace("{TOKEN}", token)
    prompt = prompt.replace("{today}", str(date.today()))
    prompt = prompt.replace("{search_results}", _format_search_results(results))
    response = await call_groq(prompt, max_tokens=1000)
    saved = []
    for ev in _parse_events_json(response, token):
        if _is_within_horizon(ev.get("date_event"), config.SCAN_HORIZON_DAYS):
            await save_event(db, ev)
            saved.append(ev)
    return saved


async def scan_single_token(token: str, db, http_client) -> list[dict]:
    """Сканирует один токен: Parallel → Groq → save events."""
    try:
        results = await search_token_events(
            http_client, token, config.PARALLEL_API_KEY,
            config.PARALLEL_MAX_RESULTS, config.PARALLEL_MAX_CHARS)
        if not results:
            return []
        saved = await _process_results(token, results, db)
        logger.info(f"SCAN {token}: {len(results)} results, {len(saved)} events")
        return saved
    except GroqAPIError:
        raise
    except Exception as e:
        logger.error(f"Scanner error for {token}: {e}")
        traceback.print_exc()
        return []


async def scan_all_tokens(db) -> dict:
    """Основной пайплайн: сканирует все токены Binance Futures."""
    s = {"tokens_total": 0, "tokens_with_results": 0, "parallel_requests": 0,
         "groq_calls": 0, "events_found": 0, "events_new": 0,
         "events_duplicate": 0, "errors_parallel": 0, "errors_groq": 0}
    seen: set[str] = set()
    async with httpx.AsyncClient() as http:
        tokens = await get_futures_tokens(http, exclude=config.TOP_EXCLUDE)
        s["tokens_total"] = len(tokens)
        logger.info(f"Scanning {len(tokens)} tokens...")
        await ensure_outcome_tables(db)
        for token in tokens:
            await asyncio.sleep(config.PARALLEL_DELAY)
            s["parallel_requests"] += 1
            if s["groq_calls"] >= config.MAX_GROQ_CALLS_PER_SCAN:
                try:
                    r = await search_token_events(http, token, config.PARALLEL_API_KEY,
                                                  config.PARALLEL_MAX_RESULTS, config.PARALLEL_MAX_CHARS)
                    if r: s["tokens_with_results"] += 1
                except Exception: s["errors_parallel"] += 1
                continue
            try:
                events = await scan_single_token(token, db, http)
            except GroqAPIError:
                s["errors_groq"] += 1; s["groq_calls"] += 1; continue
            except Exception:
                s["errors_parallel"] += 1; continue
            s["groq_calls"] += 1
            if events: s["tokens_with_results"] += 1
            for ev in events:
                eid = make_event_id(ev.get("coin_symbol", ""),
                                    ev.get("event_type", ""), ev.get("title", ""))
                s["events_found"] += 1
                if eid in seen: s["events_duplicate"] += 1
                else: seen.add(eid); s["events_new"] += 1
            if events:
                logger.info(f"SCAN {token}: {len(events)} events saved")
    logger.info(f"Scan complete: {s}")
    return s
