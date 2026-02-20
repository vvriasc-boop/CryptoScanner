"""CryptoScanner News Explorer — тест 4 источников + AI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import os
from datetime import datetime

from tabulate import tabulate

import config
from database import db
from services.news_cryptocv import CryptoCVClient
from services.news_cryptopanic import CryptoPanicClient
from services.news_binance import BinanceAnnouncementsClient
from services.news_google import GoogleNewsClient
from services.event_extractor import EventExtractor


# ---------------------------------------------------------------------------
# Вспомогательные
# ---------------------------------------------------------------------------

def _detect_fields(items: list) -> list[list[str]]:
    """Определить поля и типы из первого объекта."""
    if not items or not isinstance(items[0], dict):
        return []
    first = items[0]
    rows: list[list[str]] = []
    for key, val in first.items():
        type_name = type(val).__name__
        example = str(val)[:50]
        rows.append([key, type_name, example])
    return rows


def _raw_json(data: list, limit: int = 2) -> str:
    """JSON первых N элементов."""
    return json.dumps(data[:limit], indent=2, ensure_ascii=False, default=str)


def _news_to_raw_news(
    items: list[dict], source: str, extractor_fn: callable
) -> list[dict]:
    """Универсальная конвертация в формат raw_news."""
    result: list[dict] = []
    for item in items:
        result.append(extractor_fn(item, source))
    return result


# ---------------------------------------------------------------------------
# Шаг 1: Валидация
# ---------------------------------------------------------------------------

def step_validate() -> dict[str, bool]:
    """Проверка ключей."""
    print("\n⚙️  Конфигурация:")
    status: dict[str, bool] = {}

    if config.CRYPTOPANIC_TOKEN:
        print("   CRYPTOPANIC_TOKEN:  ✅ задан")
        status["cryptopanic"] = True
    else:
        print("   CRYPTOPANIC_TOKEN:  ⚠️ не задан (пропущу CryptoPanic)")
        status["cryptopanic"] = False

    if config.GROQ_API_KEY:
        print("   GROQ_API_KEY:       ✅ задан")
        status["groq"] = True
    else:
        print("   GROQ_API_KEY:       ⚠️ не задан (пропущу AI-парсинг)")
        status["groq"] = False

    print("   cryptocurrency.cv:  ✅ (ключ не нужен)")
    status["cryptocv"] = True
    print("   Binance:            ✅ (ключ не нужен)")
    status["binance"] = True
    print("   Google News RSS:    ✅ (ключ не нужен)")
    status["google"] = True

    return status


# ---------------------------------------------------------------------------
# Шаг 3A: cryptocurrency.cv
# ---------------------------------------------------------------------------

def explore_cryptocv(report: dict) -> list[dict]:
    """Исследование cryptocurrency.cv. Возвращает raw_news items."""
    print("\n══════════════ CRYPTOCURRENCY.CV ══════════════")

    client = CryptoCVClient(
        base_url=config.CRYPTOCV_NEWS_URL,
        timeout=config.REQUEST_TIMEOUT,
        delay=config.CRYPTOCV_DELAY,
    )

    print("🔌 Проверяю подключение...")
    if not client.check_connection():
        print("❌ Подключение не удалось")
        report["sources"]["cryptocv"] = {"status": "error", "count": 0}
        return []
    print("✅ OK")

    print("\n📰 Загружаю последние новости...")
    raw_items = client.get_latest_news(limit=50)
    print(f"✅ Получено: {len(raw_items)} новостей")

    if raw_items:
        print(f"\n📰 RAW (первые 2):")
        print(_raw_json(raw_items))

        fields = _detect_fields(raw_items)
        if fields:
            print(f"\n📰 Поля:")
            print(tabulate(fields, headers=["Поле", "Тип", "Пример"],
                           tablefmt="simple_outline"))

    # Конвертация в raw_news формат
    news_items = [_convert_cryptocv(item) for item in raw_items]
    saved = db.upsert_raw_news(news_items)
    print(f"\n💾 Сохранено в raw_news: {saved} новых")

    report["sources"]["cryptocv"] = {"status": "ok", "count": len(raw_items), "saved": saved}
    return news_items


def _convert_cryptocv(item: dict) -> dict:
    """Конвертация cryptocurrency.cv элемента в формат raw_news."""
    # Структура неизвестна — пробуем разные поля
    title = (item.get("title") or item.get("headline") or
             item.get("name") or str(item)[:200])
    url = item.get("url") or item.get("link") or ""
    published = item.get("published_at") or item.get("date") or item.get("created_at")
    tickers_raw = item.get("tickers") or item.get("currencies") or item.get("symbols")
    if isinstance(tickers_raw, list):
        tickers = ",".join(str(t) for t in tickers_raw)
    elif isinstance(tickers_raw, str):
        tickers = tickers_raw
    else:
        tickers = ""
    domain = item.get("domain") or item.get("source") or "cryptocurrency.cv"
    if isinstance(domain, dict):
        domain = domain.get("domain", domain.get("name", "cryptocurrency.cv"))

    return {
        "source": "cryptocv",
        "title": str(title),
        "url": str(url),
        "published_at": str(published) if published else None,
        "tickers": tickers,
        "domain": str(domain),
        "sentiment": None,
        "votes_positive": 0,
        "votes_important": 0,
        "raw_json": item,
    }


# ---------------------------------------------------------------------------
# Шаг 3B: CryptoPanic
# ---------------------------------------------------------------------------

def explore_cryptopanic(report: dict) -> list[dict]:
    """Исследование CryptoPanic. Возвращает raw_news items."""
    print("\n══════════════ CRYPTOPANIC ══════════════")

    client = CryptoPanicClient(
        auth_token=config.CRYPTOPANIC_TOKEN,
        base_url=config.CRYPTOPANIC_BASE_URL,
        timeout=config.REQUEST_TIMEOUT,
        delay=config.CRYPTOPANIC_DELAY,
    )

    print("🔌 Проверяю подключение...")
    if not client.check_connection():
        print("❌ Подключение не удалось")
        report["sources"]["cryptopanic"] = {"status": "error", "count": 0}
        return []
    print("✅ OK")

    # Важные новости
    print("\n📰 Загружаю важные новости (filter=important)...")
    important = client.get_important_news(limit=30)
    print(f"✅ Получено: {len(important)} важных")

    # Все последние
    print("\n📰 Загружаю все последние...")
    latest = client.get_latest_news(limit=50)
    print(f"✅ Получено: {len(latest)} последних")

    if latest:
        print(f"\n📰 RAW (первые 2):")
        print(_raw_json(latest))

    # Объединяем (дедупликация по title)
    seen_titles: set[str] = set()
    all_items: list[dict] = []
    for item in important + latest:
        t = item.get("title", "")
        if t not in seen_titles:
            seen_titles.add(t)
            all_items.append(item)

    # Конвертация
    news_items = [_convert_cryptopanic(item) for item in all_items]
    saved = db.upsert_raw_news(news_items)
    print(f"\n💾 Сохранено в raw_news: {saved} новых")

    report["sources"]["cryptopanic"] = {
        "status": "ok", "count": len(all_items),
        "important": len(important), "saved": saved,
    }
    return news_items


def _convert_cryptopanic(item: dict) -> dict:
    """Конвертация CryptoPanic поста в формат raw_news."""
    tickers = CryptoPanicClient.extract_tickers(item)
    votes = item.get("votes", {})
    source_info = item.get("source", {})
    domain = source_info.get("domain", "") if isinstance(source_info, dict) else ""

    return {
        "source": "cryptopanic",
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "published_at": item.get("published_at"),
        "tickers": ",".join(tickers),
        "domain": domain,
        "sentiment": None,
        "votes_positive": votes.get("positive", 0) if isinstance(votes, dict) else 0,
        "votes_important": votes.get("important", 0) if isinstance(votes, dict) else 0,
        "raw_json": item,
    }


# ---------------------------------------------------------------------------
# Шаг 3C: Binance Announcements
# ---------------------------------------------------------------------------

def explore_binance(report: dict) -> list[dict]:
    """Исследование Binance Announcements. Возвращает raw_news items."""
    print("\n══════════════ BINANCE ANNOUNCEMENTS ══════════════")

    client = BinanceAnnouncementsClient(
        timeout=config.REQUEST_TIMEOUT,
        delay=config.BINANCE_DELAY,
    )

    print("🔌 Проверяю подключение...")
    if not client.check_connection():
        print("❌ Подключение не удалось (POST может быть заблокирован)")
        report["sources"]["binance"] = {"status": "error", "count": 0}
        return []
    print("✅ OK")

    all_articles: list[dict] = []

    # Листинги
    print("\n📰 Загружаю листинги (catalogId=48)...")
    listings = client.get_listings(page_size=20)
    print(f"✅ Получено: {len(listings)}")
    all_articles.extend(listings)

    # Делистинги
    print("\n📰 Загружаю делистинги (catalogId=131)...")
    delistings = client.get_delistings(page_size=20)
    print(f"✅ Получено: {len(delistings)}")
    all_articles.extend(delistings)

    if all_articles:
        print(f"\n📰 RAW (первые 2):")
        print(_raw_json(all_articles))

        fields = _detect_fields(all_articles)
        if fields:
            print(f"\n📰 Поля:")
            print(tabulate(fields, headers=["Поле", "Тип", "Пример"],
                           tablefmt="simple_outline"))

    # Конвертация
    news_items = [_convert_binance(item) for item in all_articles]
    saved = db.upsert_raw_news(news_items)
    print(f"\n💾 Сохранено в raw_news: {saved} новых")

    report["sources"]["binance"] = {
        "status": "ok", "count": len(all_articles),
        "listings": len(listings), "delistings": len(delistings), "saved": saved,
    }
    return news_items


def _convert_binance(item: dict) -> dict:
    """Конвертация Binance article в формат raw_news."""
    title = item.get("title") or item.get("name") or str(item)[:200]
    code = item.get("code", "")
    url = f"https://www.binance.com/en/support/announcement/{code}" if code else ""
    release_date = item.get("releaseDate") or item.get("publishDate")
    if isinstance(release_date, (int, float)) and release_date > 1e12:
        # Binance может давать timestamp в миллисекундах
        from datetime import datetime as dt
        release_date = dt.fromtimestamp(release_date / 1000).isoformat()

    return {
        "source": "binance",
        "title": str(title),
        "url": url,
        "published_at": str(release_date) if release_date else None,
        "tickers": "",
        "domain": "binance.com",
        "sentiment": None,
        "votes_positive": 0,
        "votes_important": 0,
        "raw_json": item,
    }


# ---------------------------------------------------------------------------
# Шаг 3D: Google News RSS
# ---------------------------------------------------------------------------

def explore_google_news(report: dict) -> list[dict]:
    """Исследование Google News RSS. Возвращает raw_news items."""
    print("\n══════════════ GOOGLE NEWS RSS ══════════════")

    client = GoogleNewsClient(
        base_url=config.GOOGLE_NEWS_RSS_BASE,
        delay=config.GOOGLE_NEWS_DELAY,
        max_total=config.MAX_GOOGLE_NEWS_TOTAL,
    )

    print("🔌 Проверяю подключение...")
    if not client.check_connection():
        print("❌ Google News RSS недоступен")
        report["sources"]["google"] = {"status": "error", "count": 0}
        return []
    print("✅ OK")

    print(f"\n📰 Загружаю новости ({len(config.GOOGLE_NEWS_QUERIES)} запросов)...")
    for q in config.GOOGLE_NEWS_QUERIES:
        print(f"   • {q}")

    all_entries = client.fetch_all(config.GOOGLE_NEWS_QUERIES)
    print(f"✅ Получено: {len(all_entries)} новостей (дедупликация по title)")

    if all_entries:
        print(f"\n📰 RAW (первые 2):")
        print(_raw_json(all_entries))

        fields = _detect_fields(all_entries)
        if fields:
            print(f"\n📰 Поля:")
            print(tabulate(fields, headers=["Поле", "Тип", "Пример"],
                           tablefmt="simple_outline"))

    # Конвертация в raw_news формат
    news_items = [_convert_google(entry) for entry in all_entries]
    saved = db.upsert_raw_news(news_items)
    print(f"\n💾 Сохранено в raw_news: {saved} новых")

    # Статистика по запросам
    from collections import Counter
    query_counter: Counter[str] = Counter(e["query"] for e in all_entries)
    if query_counter:
        print(f"\n📊 По запросам:")
        q_tbl = [[q, cnt] for q, cnt in query_counter.most_common()]
        print(tabulate(q_tbl, headers=["Запрос", "Кол-во"],
                       tablefmt="simple_outline"))

    report["sources"]["google"] = {
        "status": "ok",
        "count": len(all_entries),
        "queries": len(config.GOOGLE_NEWS_QUERIES),
        "saved": saved,
    }
    return news_items


def _convert_google(entry: dict) -> dict:
    """Конвертация Google News RSS entry в формат raw_news."""
    title = entry.get("title", "")
    url = entry.get("link", "")
    published = GoogleNewsClient.parse_published(entry)
    source_name = entry.get("source_name", "Google News")

    return {
        "source": "google_news",
        "title": str(title),
        "url": str(url),
        "published_at": published,
        "tickers": "",
        "domain": str(source_name),
        "sentiment": None,
        "votes_positive": 0,
        "votes_important": 0,
        "raw_json": entry,
    }


# ---------------------------------------------------------------------------
# Шаг 4: AI Event Extraction
# ---------------------------------------------------------------------------

def explore_ai_extraction(report: dict) -> None:
    """AI-парсинг новостей через Groq."""
    print("\n══════════════ AI EVENT EXTRACTION ══════════════")

    extractor = EventExtractor(
        api_key=config.GROQ_API_KEY,
        api_url=config.GROQ_API_URL,
        model=config.GROQ_MODEL,
        delay=config.GROQ_DELAY,
        timeout=30,
    )

    print("🔌 Проверяю Groq API...")
    if not extractor.check_connection():
        print("❌ Groq API не отвечает")
        report["ai"] = {"status": "error"}
        return
    print(f"✅ Groq OK (модель: {config.GROQ_MODEL})")

    # Загрузить необработанные новости
    print("\n🤖 Обрабатываю непроцессированные новости...")
    unprocessed = db.get_unprocessed_news(limit=100)
    print(f"   Новостей для обработки: {len(unprocessed)}")

    if not unprocessed:
        print("   Нет новых новостей для обработки")
        report["ai"] = {"status": "ok", "processed": 0, "events": 0}
        return

    # Подготовка для AI
    news_for_ai: list[dict] = []
    news_ids: list[int] = []
    for n in unprocessed:
        tickers = n.get("tickers", "")
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
        news_for_ai.append({
            "title": n["title"],
            "url": n.get("url", ""),
            "source": n.get("domain", n.get("source", "")),
            "domain": n.get("domain", ""),
            "published_at": n.get("published_at", ""),
            "tickers": ticker_list,
        })
        news_ids.append(n["id"])

    # Извлечение событий
    extracted = extractor.extract_events(news_for_ai)

    # Пометить обработанными
    db.mark_news_processed(news_ids)

    # Конвертация в events и сохранение
    events_to_save: list[dict] = []
    for ev in extracted:
        ni = ev.get("news_index")
        news_id = news_ids[ni] if ni is not None and ni < len(news_ids) else None
        events_to_save.append({
            "caption": ev["title"],
            "source": ev.get("source_url", ""),
            "source_type": "ai_parsed",
            "source_reliable": 0,
            "important": 1 if ev.get("importance") == "high" else 0,
            "date_public": datetime.now().strftime("%Y-%m-%d"),
            "date_start": ev.get("date_event") or datetime.now().strftime("%Y-%m-%d"),
            "coin_symbol": ev.get("coin_symbol"),
            "event_type": ev.get("event_type"),
            "importance": ev.get("importance", "medium"),
            "news_id": news_id,
        })

    saved = db.upsert_events(events_to_save)

    # Статистика
    from collections import Counter
    type_counter: Counter[str] = Counter(ev.get("event_type", "other") for ev in extracted)
    coin_counter: Counter[str] = Counter(ev.get("coin_symbol", "?") for ev in extracted)

    print(f"\n📊 Результат AI-парсинга:")
    print(f"   Всего новостей обработано: {len(unprocessed)}")
    print(f"   Событий извлечено: {len(extracted)}")
    print(f"   Отфильтровано (мусор): {len(unprocessed) - len(extracted)}")

    if type_counter:
        print(f"\n   По типам:")
        type_tbl = [[et, cnt] for et, cnt in type_counter.most_common()]
        print(tabulate(type_tbl, headers=["Тип", "Кол-во"], tablefmt="simple_outline"))

    if coin_counter:
        print(f"\n   По монетам:")
        coin_tbl = [
            [sym, cnt, "✅" if sym in config.BINANCE_SYMBOLS else ""]
            for sym, cnt in coin_counter.most_common(10)
        ]
        print(tabulate(coin_tbl, headers=["Символ", "Кол-во", "Binance?"],
                       tablefmt="simple_outline"))

    # Примеры
    if extracted:
        print(f"\n📅 ПРИМЕРЫ ИЗВЛЕЧЁННЫХ СОБЫТИЙ:")
        for i, ev in enumerate(extracted[:5], 1):
            et = ev.get("event_type", "?")
            imp = ev.get("importance", "?")[:3].upper()
            sym = ev.get("coin_symbol", "?")
            title = ev.get("title", "?")[:60]
            date = ev.get("date_event") or "?"
            print(f"   {i}. [{et}] [{imp}] {sym} — \"{title}\" — {date}")

    print(f"\n💾 Сохранено в events: {saved} новых")

    binance_events = sum(1 for ev in extracted if ev.get("coin_symbol") in config.BINANCE_SYMBOLS)
    report["ai"] = {
        "status": "ok",
        "processed": len(unprocessed),
        "events": len(extracted),
        "saved": saved,
        "binance_events": binance_events,
        "by_type": dict(type_counter),
    }


# ---------------------------------------------------------------------------
# Шаг 5: Сводный отчёт
# ---------------------------------------------------------------------------

def build_summary(report: dict) -> str:
    """Формирование текстового отчёта."""
    lines: list[str] = []

    lines.append("═" * 63)
    lines.append("         CRYPTOSCANNER — NEWS & EVENTS EXPLORATION")
    lines.append(f"         {report['date']}")
    lines.append("═" * 63)

    # Таблица источников
    lines.append("\n📡 ИСТОЧНИКИ НОВОСТЕЙ")
    src_table: list[list[str]] = []
    for src_key, label in [
        ("cryptocv", "cryptocurrency.cv"),
        ("cryptopanic", "CryptoPanic"),
        ("binance", "Binance Announce"),
        ("google", "Google News RSS"),
        ("coindar", "Coindar"),
    ]:
        info = report["sources"].get(src_key, {})
        st = info.get("status", "skip")
        status_str = "✅ OK" if st == "ok" else ("❌ ERR" if st == "error" else "⏳ SKIP")
        count = info.get("count", "-")
        note = info.get("note", "")
        if src_key == "coindar":
            note = "Ждём ключ"
        elif src_key == "cryptocv":
            note = "Без ключа"
        elif src_key == "cryptopanic" and st == "ok":
            note = f"important={info.get('important', '?')}"
        elif src_key == "binance" and st == "ok":
            note = f"listings={info.get('listings', 0)}+delist={info.get('delistings', 0)}"
        elif src_key == "google" and st == "ok":
            note = f"queries={info.get('queries', 0)}"
        src_table.append([label, status_str, str(count), note])

    lines.append(tabulate(
        src_table, headers=["Источник", "Статус", "Новостей", "Примечание"],
        tablefmt="simple_outline",
    ))

    # AI
    ai = report.get("ai", {})
    if ai.get("status") == "ok":
        lines.append(f"\n🤖 AI ПАРСИНГ (Groq)")
        lines.append(f"   Новостей обработано:    {ai.get('processed', 0)}")
        lines.append(f"   Событий извлечено:       {ai.get('events', 0)}")
        binance_ev = ai.get("binance_events", 0)
        lines.append(f"   Из них по Binance:       {binance_ev}")

        by_type = ai.get("by_type", {})
        if by_type:
            lines.append(f"\n📊 СОБЫТИЯ ПО ТИПАМ")
            type_tbl = [[et, cnt] for et, cnt in
                        sorted(by_type.items(), key=lambda x: -x[1])]
            lines.append(tabulate(type_tbl, headers=["Тип", "Кол-во"],
                                  tablefmt="simple_outline"))
    elif ai.get("status") == "error":
        lines.append(f"\n🤖 AI ПАРСИНГ: ❌ Groq недоступен")
    else:
        lines.append(f"\n🤖 AI ПАРСИНГ: ⏳ GROQ_API_KEY не задан")

    # Пригодность
    lines.append(f"\n💡 ПРИГОДНОСТЬ")
    active_sources = sum(
        1 for s in report["sources"].values() if s.get("status") == "ok"
    )
    total_events = ai.get("events", 0) if ai.get("status") == "ok" else 0
    lines.append(f"   Новостных источников:    {active_sources} из 5")
    lines.append(f"   Событий для анализа:     {total_events}")

    if total_events >= 15:
        quality = "ХОРОШО"
    elif total_events >= 5:
        quality = "СРЕДНЕ"
    else:
        quality = "СЛАБО"
    lines.append(f"   Качество AI-парсинга:    {quality}")

    if active_sources >= 3 and total_events >= 10:
        rec = "ДОСТАТОЧНО ДЛЯ MVP"
    elif active_sources >= 2:
        rec = "ДОБАВИТЬ COINDAR для полноты"
    else:
        rec = "МАЛО ИСТОЧНИКОВ"
    lines.append(f"\n   Рекомендация: {rec}")
    report["verdict"] = rec

    lines.append("\n" + "═" * 63)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Шаг 6: Сохранение
# ---------------------------------------------------------------------------

def save_reports(report: dict, text_report: str) -> None:
    """Сохранение .txt и .json."""
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    date_str = report["date"].replace("-", "")

    txt_path = config.REPORTS_DIR / f"news_explore_{date_str}.txt"
    json_path = config.REPORTS_DIR / f"news_explore_{date_str}.json"

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text_report)

    # JSON — без raw_json (слишком большой)
    json_safe = {
        "date": report["date"],
        "sources": {},
        "ai": report.get("ai", {}),
        "verdict": report.get("verdict", ""),
    }
    for key, val in report["sources"].items():
        json_safe["sources"][key] = {
            k: v for k, v in val.items() if k != "raw_json"
        }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_safe, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n💾 Отчёт сохранён:")
    print(f"   {txt_path}")
    print(f"   {json_path}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    """Точка входа explore_news.py."""
    print("🚀 CryptoScanner News & Events Explorer")
    print(f"   Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Шаг 1
    api_status = step_validate()

    # Шаг 2
    print("\n💾 Инициализирую БД (raw_news + events)...")
    db.init_db()
    print(f"✅ БД готова: {config.DB_PATH.name}")

    report: dict = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sources": {"coindar": {"status": "skip", "count": 0, "note": "Ждём ключ"}},
    }

    # Шаг 3A: cryptocurrency.cv
    try:
        explore_cryptocv(report)
    except Exception as e:
        report["sources"]["cryptocv"] = {"status": "error", "count": 0}
        print(f"❌ cryptocurrency.cv ошибка: {e}")

    # Шаг 3B: CryptoPanic
    if api_status.get("cryptopanic"):
        try:
            explore_cryptopanic(report)
        except Exception as e:
            report["sources"]["cryptopanic"] = {"status": "error", "count": 0}
            print(f"❌ CryptoPanic ошибка: {e}")
    else:
        report["sources"]["cryptopanic"] = {"status": "skip", "count": 0}

    # Шаг 3C: Binance
    try:
        explore_binance(report)
    except Exception as e:
        report["sources"]["binance"] = {"status": "error", "count": 0}
        print(f"❌ Binance ошибка: {e}")

    # Шаг 3D: Google News RSS
    try:
        explore_google_news(report)
    except Exception as e:
        report["sources"]["google"] = {"status": "error", "count": 0}
        print(f"❌ Google News RSS ошибка: {e}")

    # Шаг 4: AI
    if api_status.get("groq"):
        try:
            explore_ai_extraction(report)
        except Exception as e:
            report["ai"] = {"status": "error"}
            print(f"❌ AI-парсинг ошибка: {e}")
    else:
        report["ai"] = {"status": "skip"}

    # Шаг 5: Сводка
    text_report = build_summary(report)
    print(text_report)

    # Шаг 6: Сохранение
    save_reports(report, text_report)

    print("\n✅ Исследование новостей завершено!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⛔ Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
