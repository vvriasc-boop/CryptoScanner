"""CryptoScanner — генератор исходов (шаблон + AI)."""

import json
import logging
import os
import re

from services.groq_client import call_groq, GroqAPIError
from services.outcome_templates import OUTCOME_TEMPLATES, GENERIC_OUTCOMES
from config import GROQ_OUTCOME_MODEL, GROQ_OUTCOME_TEMPERATURE, GROQ_OUTCOME_MAX_TOKENS

logger = logging.getLogger(__name__)


def validate_outcomes(outcomes: list) -> bool:
    """Проверить что исходы валидны (MECE)."""
    if not isinstance(outcomes, list):
        return False
    if len(outcomes) < 3 or len(outcomes) > 4:
        return False
    keys = [o.get("key") for o in outcomes]
    if len(set(keys)) != len(keys):
        return False
    valid_cats = {"positive", "neutral", "negative", "cancelled"}
    categories = [o.get("category") for o in outcomes]
    if not all(c in valid_cats for c in categories):
        return False
    if "positive" not in categories:
        return False
    if "negative" not in categories and "cancelled" not in categories:
        return False
    for o in outcomes:
        if not o.get("key") or not o.get("text") or not o.get("category"):
            return False
    return True


def _apply_template(event: dict) -> list:
    """Подставить шаблон для стандартного типа."""
    template = OUTCOME_TEMPLATES[event["event_type"]]
    coin = event.get("coin_symbol", "???")
    title = event.get("title", "")
    outcomes = []
    for o in template["outcomes"]:
        text = o["text"].replace("{coin}", coin).replace("{title}", title)
        outcomes.append({
            "key": o["key"],
            "text": text[:100],
            "category": o["category"],
            "is_template": True,
        })
    return outcomes


def _apply_generic(event: dict) -> list:
    """Generic fallback когда AI не смог."""
    coin = event.get("coin_symbol", "???")
    outcomes = []
    for o in GENERIC_OUTCOMES["outcomes"]:
        text = o["text"].replace("{coin}", coin)
        outcomes.append({
            "key": o["key"],
            "text": text[:100],
            "category": o["category"],
            "is_template": True,
        })
    return outcomes


def _parse_ai_response(text: str) -> list:
    """Извлечь JSON массив из ответа AI."""
    text = text.strip()
    # Попытка 1: прямой парсинг
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "outcomes" in data:
            return data["outcomes"]
    except json.JSONDecodeError:
        pass
    # Попытка 2: regex массив
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Попытка 3: regex объект
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if "outcomes" in data:
                return data["outcomes"]
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("Cannot parse AI response", text, 0)


async def _generate_via_ai(event: dict) -> list:
    """Сгенерировать исходы через Groq AI. 3 попытки, fallback на generic."""
    prompt_path = os.path.join(
        os.path.dirname(__file__), "..", "prompts", "generate_outcomes.md"
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    # Подстановка через .replace() — НЕ .format(), НЕ f-string
    prompt = prompt_template
    prompt = prompt.replace("{event_type}", event.get("event_type", "other"))
    prompt = prompt.replace("{coin_symbol}", event.get("coin_symbol", "???"))
    prompt = prompt.replace("{title}", event.get("title", ""))
    prompt = prompt.replace("{date_event}", event.get("date_event") or "не указано")

    for attempt in range(3):
        try:
            response_text = await call_groq(
                prompt=prompt,
                model=GROQ_OUTCOME_MODEL,
                temperature=GROQ_OUTCOME_TEMPERATURE,
                max_tokens=GROQ_OUTCOME_MAX_TOKENS,
            )
            outcomes = _parse_ai_response(response_text)
            if validate_outcomes(outcomes):
                for o in outcomes:
                    o["is_template"] = False
                return outcomes
            logger.warning(f"Validation failed attempt {attempt + 1}")
        except GroqAPIError as e:
            logger.error(f"Groq error attempt {attempt + 1}: {e}")
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error attempt {attempt + 1}: {e}")

    logger.warning(
        f"AI failed 3x for {event.get('coin_symbol')}, using generic"
    )
    return _apply_generic(event)


async def generate_outcomes(event: dict) -> list:
    """Главная функция. Шаблон для 7 типов, AI для остальных."""
    event_type = event.get("event_type", "other")
    if event_type in OUTCOME_TEMPLATES:
        return _apply_template(event)
    return await _generate_via_ai(event)
