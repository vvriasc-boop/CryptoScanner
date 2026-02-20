"""CryptoScanner — оценка влияния на цену через multi-temperature Groq."""

import json, logging, os, re  # noqa: E401

import config
from services.groq_client import GroqAPIError, call_groq

logger = logging.getLogger("crypto_scanner.impact")
TEMPERATURES = [0.3, 0.5, 0.7]
_prompt_cache: str = ""


def _load_prompt() -> str:
    global _prompt_cache
    if not _prompt_cache:
        p = os.path.join(os.path.dirname(__file__), "..", "prompts",
                         "estimate_impact.md")
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


def _validate_impacts(impacts: dict, expected_keys: set) -> bool:
    """Ключи совпадают, значения float в [-50, 50]."""
    if not isinstance(impacts, dict) or set(impacts.keys()) != expected_keys:
        return False
    return all(isinstance(v, (int, float)) and -50.0 <= v <= 50.0
               for v in impacts.values())


def _clamp_impacts(impacts: dict) -> dict:
    """Clamp [-50, +50], round."""
    return {k: round(max(-50.0, min(50.0, float(v))), 2)
            for k, v in impacts.items()}


def _validate_sign_logic(impacts: dict) -> dict:
    """Если ВСЕ импакты одного знака — исправить первый/последний."""
    vals = [v for v in impacts.values() if v != 0]
    if len(vals) < 2:
        return impacts
    all_neg = all(v < 0 for v in vals)
    all_pos = all(v > 0 for v in vals)
    if not all_neg and not all_pos:
        return impacts
    corrected = dict(impacts)
    keys = list(corrected.keys())
    if all_neg:
        corrected[keys[0]] = abs(corrected[keys[0]])
        logger.warning(f"Sign fix: all negative → {keys[0]} flipped to +{corrected[keys[0]]}")
    elif all_pos:
        corrected[keys[-1]] = -abs(corrected[keys[-1]])
        logger.warning(f"Sign fix: all positive → {keys[-1]} flipped to {corrected[keys[-1]]}")
    return corrected


async def _single_iteration(prompt: str, temperature: float,
                             expected_keys: set) -> dict:
    """Один вызов Groq → parse → validate → sign check → clamp. {} при ошибке."""
    try:
        text = await call_groq(
            prompt, model=config.GROQ_SCANNER_MODEL,
            temperature=temperature, max_tokens=200)
        impacts = _parse_json(text)
        impacts = {k: float(v) for k, v in impacts.items() if k in expected_keys}
        if not _validate_impacts(impacts, expected_keys):
            logger.warning(f"Invalid impacts at T={temperature}: {impacts}")
            return {}
        impacts = _validate_sign_logic(impacts)
        return _clamp_impacts(impacts)
    except GroqAPIError as e:
        logger.warning(f"Groq error at T={temperature}: {e}")
        return {}
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.warning(f"Parse error at T={temperature}: {e}")
        return {}


def _aggregate_iterations(iterations: list[dict]) -> dict:
    """Из 1-3 итераций → медиана + low/high."""
    ok = [i for i in iterations if i]
    if not ok: return {}
    if len(ok) == 1:
        r = {}
        for k, v in ok[0].items():
            d = max(abs(v) * 0.3, 1.0)
            r[k] = {"impact": v, "low": round(v - d, 2),
                     "high": round(v + d, 2)}
        return r
    result = {}
    for k in ok[0].keys():
        vals = sorted(it[k] for it in ok if k in it)
        if not vals: continue
        median = vals[len(vals) // 2]
        result[k] = {"impact": round(median, 2),
                      "low": round(vals[0], 2), "high": round(vals[-1], 2)}
    return result


async def estimate_event_impacts(event: dict,
                                  outcomes: list[dict]) -> dict:
    """
    3 итерации Groq (T=0.3, 0.5, 0.7) → медиана + low/high.
    Возвращает {"A": {"impact", "low", "high"}, ...}. {} при ошибке.
    """
    expected = {o.get("outcome_key", o.get("key", "")) for o in outcomes}
    if not (3 <= len(expected) <= 4):
        logger.error(f"Invalid outcome count: {len(expected)}"); return {}
    lines = [
        f"{o.get('outcome_key', o.get('key','?'))}) "
        f"[{o.get('outcome_category', o.get('category','?'))}] "
        f"{o.get('outcome_text', o.get('text','?'))} "
        f"(P={o.get('probability') or 0:.2f})"
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
        logger.info(f"Impacts for {event.get('coin_symbol')}: "
                     f"{len(result)} outcomes, {ok_cnt}/3 OK")
    return result
