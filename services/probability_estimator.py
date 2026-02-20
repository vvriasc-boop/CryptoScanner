"""CryptoScanner — оценка вероятностей исходов через multi-temperature Groq."""

import json, logging, os, re  # noqa: E401

import config
from services.groq_client import GroqAPIError, call_groq

logger = logging.getLogger("crypto_scanner.probability")
TEMPERATURES = [0.3, 0.5, 0.7]
_prompt_cache: str = ""


def _load_prompt() -> str:
    global _prompt_cache
    if not _prompt_cache:
        p = os.path.join(os.path.dirname(__file__), "..", "prompts",
                         "estimate_probabilities.md")
        with open(p, encoding="utf-8") as f:
            _prompt_cache = f.read()
    return _prompt_cache


def _parse_json(text: str) -> dict:
    """2-stage: direct → regex {...}."""
    for src in [text, None]:
        try:
            if src is None:
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if not m: return {}
                src = m.group()
            parsed = json.loads(src)
            if isinstance(parsed, dict): return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _validate_probabilities(probs: dict, expected_keys: set) -> bool:
    """Ключи совпадают, значения float в [0,1], сумма в [0.8, 1.2]."""
    if not isinstance(probs, dict) or set(probs.keys()) != expected_keys:
        return False
    if not all(isinstance(v, (int, float)) and 0.0 <= v <= 1.0 for v in probs.values()):
        return False
    return 0.8 <= sum(probs.values()) <= 1.2


def _normalize_probabilities(probs: dict) -> dict:
    """Clamp [0.02, 0.85], нормализовать сумму к 1.0."""
    clamped = {k: max(0.02, min(0.85, float(v))) for k, v in probs.items()}
    total = sum(clamped.values())
    return {k: round(v / total, 4) for k, v in clamped.items()}


async def _single_iteration(prompt: str, temperature: float,
                             expected_keys: set) -> dict:
    """Один вызов Groq → parse → validate → normalize. {} при ошибке."""
    try:
        text = await call_groq(
            prompt, model=config.GROQ_SCANNER_MODEL,
            temperature=temperature, max_tokens=200)
        probs = _parse_json(text)
        probs = {k: float(v) for k, v in probs.items() if k in expected_keys}
        if not _validate_probabilities(probs, expected_keys):
            logger.warning(f"Invalid probabilities at T={temperature}: {probs}")
            return {}
        return _normalize_probabilities(probs)
    except GroqAPIError as e:
        logger.warning(f"Groq error at T={temperature}: {e}")
        return {}
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.warning(f"Parse error at T={temperature}: {e}")
        return {}


def _aggregate_iterations(iterations: list[dict]) -> dict:
    """Из 1-3 итераций → медиана + low/high. Нормализация медиан."""
    ok = [i for i in iterations if i]
    if not ok: return {}
    if len(ok) == 1:
        return {k: {"probability": v, "low": round(v * 0.7, 4),
                     "high": round(min(v * 1.3, 0.85), 4)}
                for k, v in ok[0].items()}
    keys = ok[0].keys()
    raw, result = {}, {}
    for k in keys:
        vals = sorted(it[k] for it in ok if k in it)
        if not vals:
            continue
        raw[k] = vals[len(vals) // 2]
        result[k] = {"low": round(vals[0], 4), "high": round(vals[-1], 4)}
    total = sum(raw.values())
    if total > 0:
        for k in raw:
            result[k]["probability"] = round(raw[k] / total, 4)
    return result


async def estimate_event_probabilities(event: dict,
                                        outcomes: list[dict]) -> dict:
    """
    3 итерации Groq (T=0.3, 0.5, 0.7) → медиана + low/high.
    Возвращает {"A": {"probability", "low", "high"}, ...}. {} при ошибке.
    """
    expected = {o.get("outcome_key", o.get("key", "")) for o in outcomes}
    if not (3 <= len(expected) <= 4):
        logger.error(f"Invalid outcome count: {len(expected)}"); return {}
    lines = [
        f"{o.get('outcome_key', o.get('key','?'))}) "
        f"[{o.get('outcome_category', o.get('category','?'))}] "
        f"{o.get('outcome_text', o.get('text','?'))}"
        for o in outcomes]
    prompt = _load_prompt()
    for old, new in [("{coin_symbol}", event.get("coin_symbol", "?")),
                     ("{event_type}", event.get("event_type", "?")),
                     ("{title}", event.get("title", "?")),
                     ("{date_event}", event.get("date_event") or "unknown"),
                     ("{importance}", event.get("importance", "medium")),
                     ("{outcomes_text}", "\n".join(lines))]:
        prompt = prompt.replace(old, new)
    iters = [await _single_iteration(prompt, t, expected) for t in TEMPERATURES]
    result = _aggregate_iterations(iters)
    ok_cnt = sum(1 for i in iters if i)
    if not result:
        logger.error(f"All iterations failed for {event.get('coin_symbol')}")
    else:
        logger.info(f"Probabilities for {event.get('coin_symbol')}: "
                     f"{len(result)} outcomes, {ok_cnt}/3 OK")
    return result
