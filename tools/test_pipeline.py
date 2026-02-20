"""CryptoScanner — тест пайплайна: Новости → События → Исходы."""
import asyncio, logging, os, sqlite3, sys, traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aiosqlite
import config
from database.db import ensure_outcome_tables, get_unprocessed_events, save_event, save_outcomes
from services.event_extractor import EventExtractor
from services.news_binance import BinanceAnnouncementsClient
from services.outcome_generator import generate_outcomes, validate_outcomes
from services.outcome_templates import OUTCOME_TEMPLATES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
MAX_ARTICLES = 5
MAX_EVENTS = 10


def step1_collect() -> tuple[list[dict], list[dict]]:
    """Шаг 1 (sync): сбор статей Binance + извлечение событий через Groq."""
    client = BinanceAnnouncementsClient(
        timeout=config.REQUEST_TIMEOUT, delay=config.BINANCE_DELAY,
    )
    articles = client.get_listings(page_size=20)
    if not articles:
        return [], []
    news_for_ai: list[dict] = []
    for art in articles[:MAX_ARTICLES]:
        title = art.get("title") or str(art)[:200]
        code = art.get("code", "")
        url = f"https://www.binance.com/en/support/announcement/{code}" if code else ""
        news_for_ai.append({
            "title": title, "url": url, "source": "binance.com",
            "domain": "binance.com", "published_at": "", "tickers": [],
        })
    extractor = EventExtractor(
        api_key=config.GROQ_API_KEY, api_url=config.GROQ_API_URL,
        model=config.GROQ_MODEL, delay=config.GROQ_DELAY, timeout=30,
    )
    return articles, extractor.extract_events(news_for_ai)


async def main() -> None:
    db_path = str(config.DB_PATH)
    print("══════════════════════════════════════════════════")
    print("ТЕСТ ПАЙПЛАЙНА: Новости → События → Исходы")
    print(f"БД: {os.path.abspath(db_path)}")
    print("══════════════════════════════════════════════════")
    # --- Шаг 1 (sync) ---
    print("\n📡 Шаг 1: Сбор новостей...")
    articles, extracted = step1_collect()
    print(f"  Статей получено: {len(articles)}")
    if not articles:
        print("  ❌ Нет статей (проверь интернет)")
        return
    print(f"  Обрабатываю первые {min(MAX_ARTICLES, len(articles))}...")
    print(f"  Событий извлечено: {len(extracted)}")
    if not extracted:
        print("  ⚠️ AI не извлёк событий")
        return
    for ev in extracted[:MAX_EVENTS]:
        print(f"  → {ev.get('coin_symbol','?')} | {ev.get('event_type','?')} | {ev.get('title','?')[:50]}")
    # --- Шаг 2 (async) ---
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await ensure_outcome_tables(db)
        saved = 0
        for ev in extracted[:MAX_EVENTS]:
            await save_event(db, {
                "coin_symbol": ev.get("coin_symbol", "???"),
                "event_type": ev.get("event_type", "other"),
                "title": ev.get("title", "")[:100],
                "importance": ev.get("importance", "medium"),
                "source_name": "binance", "date_event": ev.get("date_event"),
            })
            saved += 1
        print(f"\n💾 Сохранено в БД: {saved} события")
        print("\n🎯 Шаг 2: Генерация исходов...")
        events = await get_unprocessed_events(db, limit=MAX_EVENTS)
        print(f"  Необработанных: {len(events)}")
        stats = {"template": 0, "ai": 0, "errors": 0}
        for i, event in enumerate(events, 1):
            coin, etype, eid = event["coin_symbol"], event["event_type"], event["id"]
            method = "шаблон" if etype in OUTCOME_TEMPLATES else "AI (Groq)"
            try:
                outcomes = await generate_outcomes(event)
                valid = validate_outcomes(outcomes)
                print(f"\n  [{i}/{len(events)}] {coin} | {etype} → {method}")
                for o in outcomes:
                    print(f"    {o['key']}) [{o['category'].ljust(10)}] {o['text']}")
                if valid:
                    print(f"    ✅ MECE OK")
                    await save_outcomes(db, eid, outcomes)
                    stats["ai" if any(not o.get("is_template", True) for o in outcomes) else "template"] += 1
                else:
                    print(f"    ❌ MECE FAIL")
                    stats["errors"] += 1
            except Exception as e:
                print(f"\n  [{i}/{len(events)}] {coin} | {etype} → ❌ {e}")
                traceback.print_exc()
                stats["errors"] += 1
        c1 = await (await db.execute("SELECT COUNT(*) as c FROM events_v2")).fetchone()
        c2 = await (await db.execute("SELECT COUNT(*) as c FROM event_outcomes")).fetchone()
        print("\n══════════════════════════════════════════════════")
        print("ИТОГ")
        print(f"  Статей:          {len(articles)}")
        print(f"  Событий:         {len(extracted)}")
        print(f"  Шаблон:          {stats['template']}")
        print(f"  AI-генерация:    {stats['ai']}")
        print(f"  Ошибки:          {stats['errors']}")
        print(f"  В БД events:     {c1['c']}")
        print(f"  В БД outcomes:   {c2['c']}")
        print("══════════════════════════════════════════════════")


if __name__ == "__main__":
    asyncio.run(main())
