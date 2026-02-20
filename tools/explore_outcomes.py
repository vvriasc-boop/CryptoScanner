"""Тест генерации исходов: создаёт тестовые события, генерирует исходы, выводит результат."""

import asyncio
import logging
import os
import sqlite3
import sys
import traceback

# Добавить корень проекта в path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aiosqlite

from database.db import (
    ensure_outcome_tables,
    get_unprocessed_events,
    save_event,
    save_outcomes,
)
from services.outcome_generator import generate_outcomes, validate_outcomes
from services.outcome_templates import OUTCOME_TEMPLATES

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Путь к БД — проверить config.py, если нет — default
try:
    from config import DB_PATH
except ImportError:
    DB_PATH = os.path.join(os.path.dirname(__file__), "..", "crypto_scanner.db")

TEST_EVENTS = [
    {"coin_symbol": "ESP", "event_type": "listing", "title": "ESP listed on Binance",
     "importance": "high", "source_name": "binance"},
    {"coin_symbol": "TSLA", "event_type": "launch", "title": "TSLA on Binance Futures",
     "importance": "medium", "source_name": "binance"},
    {"coin_symbol": "BNB", "event_type": "burn", "title": "BNB quarterly burn Q1 2026",
     "importance": "high", "source_name": "binance"},
    {"coin_symbol": "ARB", "event_type": "unlock", "title": "ARB unlocks 1.82% of supply",
     "importance": "medium", "source_name": "binance"},
    {"coin_symbol": "UNI", "event_type": "governance",
     "title": "Uniswap proposal: Enable fee switch for v3",
     "importance": "high", "source_name": "ai_extracted"},
]


async def main():
    db_path = str(DB_PATH)
    print(f"\nБД: {os.path.abspath(db_path)}")
    print("═══ Генерация исходов ══════════════════════════════\n")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await ensure_outcome_tables(db)

        # Вставить тестовые если таблица пуста
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM events_v2")
        row = await cursor.fetchone()
        if row["cnt"] == 0:
            print("Таблица events_v2 пуста, вставляю тестовые события...\n")
            for ev in TEST_EVENTS:
                await save_event(db, ev)

        events = await get_unprocessed_events(db, limit=20)
        if not events:
            print("Нет необработанных событий. Все исходы уже сгенерированы.")
            return

        stats = {"total": len(events), "template": 0, "ai": 0, "errors": 0}

        for i, event in enumerate(events, 1):
            coin = event["coin_symbol"]
            etype = event["event_type"]
            imp = event.get("importance", "?")
            event_id = event["id"]
            method = "шаблон" if etype in OUTCOME_TEMPLATES else "AI (Groq)"

            try:
                outcomes = await generate_outcomes(event)
                is_valid = validate_outcomes(outcomes)

                print(f"[{i}/{stats['total']}] {coin} | {etype} | {imp} → {method}")
                for o in outcomes:
                    cat_pad = o["category"].ljust(10)
                    print(f"  {o['key']}) [{cat_pad}] {o['text']}")

                if is_valid:
                    print(f"  ✅ MECE OK ({len(outcomes)} исхода)")
                    await save_outcomes(db, event_id, outcomes)
                    if any(not o.get("is_template", True) for o in outcomes):
                        stats["ai"] += 1
                    else:
                        stats["template"] += 1
                else:
                    print(f"  ❌ MECE FAIL")
                    stats["errors"] += 1

            except Exception as e:
                print(f"[{i}/{stats['total']}] {coin} | {etype} → ❌ ОШИБКА: {e}")
                traceback.print_exc()
                stats["errors"] += 1

            print()

        print("═══ ИТОГ ═══════════════════════════════════════════")
        print(f"Всего событий:   {stats['total']}")
        print(f"Шаблон:          {stats['template']}")
        print(f"AI-генерация:    {stats['ai']}")
        print(f"Ошибки:          {stats['errors']}")


if __name__ == "__main__":
    asyncio.run(main())
