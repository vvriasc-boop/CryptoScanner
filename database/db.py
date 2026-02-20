"""CryptoScanner — SQLite: схема, insert, query."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3

import config

logger = logging.getLogger("crypto_scanner.db")

# ---------------------------------------------------------------------------
# Соединение
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """Соединение с Row factory."""
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Инициализация
# ---------------------------------------------------------------------------

_SCHEMA: list[str] = [
    # tags (Coindar)
    """CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    )""",

    # coins_coindar
    """CREATE TABLE IF NOT EXISTS coins_coindar (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        symbol TEXT NOT NULL,
        image_url TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cc_symbol ON coins_coindar(symbol)",

    # coins_coingecko
    """CREATE TABLE IF NOT EXISTS coins_coingecko (
        id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        name TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cg_symbol ON coins_coingecko(symbol)",

    # coins_cmc
    """CREATE TABLE IF NOT EXISTS coins_cmc (
        id INTEGER PRIMARY KEY,
        symbol TEXT NOT NULL,
        name TEXT NOT NULL,
        slug TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cmc_symbol ON coins_cmc(symbol)",

    # events (расширенная: Coindar + AI-parsed + Binance direct)
    """CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        caption TEXT NOT NULL,
        source TEXT,
        source_type TEXT DEFAULT 'unknown',
        source_reliable INTEGER DEFAULT 0,
        important INTEGER DEFAULT 0,
        date_public TEXT,
        date_start TEXT NOT NULL,
        date_end TEXT,
        coin_id INTEGER,
        coin_symbol TEXT,
        coin_price_changes REAL,
        tags TEXT,
        event_type TEXT,
        importance TEXT DEFAULT 'medium',
        news_id INTEGER,
        fetched_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_uniq ON events(caption, date_start, COALESCE(coin_symbol, 'UNKNOWN'))",
    "CREATE INDEX IF NOT EXISTS idx_events_coin ON events(coin_id)",
    "CREATE INDEX IF NOT EXISTS idx_events_symbol ON events(coin_symbol)",
    "CREATE INDEX IF NOT EXISTS idx_events_date ON events(date_start)",
    "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)",

    # raw_news (сырые новости из всех источников)
    """CREATE TABLE IF NOT EXISTS raw_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT,
        published_at TEXT,
        tickers TEXT,
        domain TEXT,
        sentiment TEXT,
        votes_positive INTEGER DEFAULT 0,
        votes_important INTEGER DEFAULT 0,
        raw_json TEXT,
        fetched_at TEXT DEFAULT (datetime('now')),
        processed INTEGER DEFAULT 0
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rn_uniq ON raw_news(source, title, COALESCE(published_at, ''))",
    "CREATE INDEX IF NOT EXISTS idx_rn_source ON raw_news(source)",
    "CREATE INDEX IF NOT EXISTS idx_rn_processed ON raw_news(processed)",
    "CREATE INDEX IF NOT EXISTS idx_rn_fetched ON raw_news(fetched_at)",

    # proposals (Snapshot)
    """CREATE TABLE IF NOT EXISTS proposals (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        space_id TEXT NOT NULL,
        space_name TEXT,
        choices TEXT,
        scores TEXT,
        scores_total REAL,
        votes INTEGER,
        state TEXT,
        start_ts INTEGER,
        end_ts INTEGER,
        fetched_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_proposals_space ON proposals(space_id)",
    "CREATE INDEX IF NOT EXISTS idx_proposals_state ON proposals(state)",
]


def init_db() -> None:
    """Создать ВСЕ таблицы и индексы."""
    conn = _connect()
    try:
        cur = conn.cursor()
        for stmt in _SCHEMA:
            cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Coindar
# ---------------------------------------------------------------------------

def upsert_tags(tags: list[dict]) -> int:
    """INSERT OR REPLACE теги. Возвращает кол-во."""
    conn = _connect()
    try:
        cur = conn.cursor()
        for t in tags:
            cur.execute(
                "INSERT OR REPLACE INTO tags (id, name) VALUES (?, ?)",
                (t["id"], t["name"]),
            )
        conn.commit()
        return len(tags)
    finally:
        conn.close()


def upsert_coindar_coins(coins: list[dict]) -> int:
    """INSERT OR REPLACE монеты Coindar. Возвращает кол-во."""
    conn = _connect()
    try:
        cur = conn.cursor()
        for c in coins:
            cur.execute(
                "INSERT OR REPLACE INTO coins_coindar (id, name, symbol, image_url) "
                "VALUES (?, ?, ?, ?)",
                (c["id"], c["name"], c["symbol"], c.get("image_url")),
            )
        conn.commit()
        return len(coins)
    finally:
        conn.close()


def upsert_events(events: list[dict]) -> int:
    """INSERT OR IGNORE события. Возвращает кол-во вставленных."""
    conn = _connect()
    try:
        cur = conn.cursor()
        inserted = 0
        for e in events:
            try:
                cur.execute(
                    "INSERT OR IGNORE INTO events "
                    "(caption, source, source_type, source_reliable, important, "
                    "date_public, date_start, date_end, coin_id, coin_symbol, "
                    "coin_price_changes, tags, event_type, importance, news_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        e["caption"],
                        e.get("source"),
                        e.get("source_type", "unknown"),
                        e.get("source_reliable", 0),
                        e.get("important", 0),
                        e.get("date_public"),
                        e["date_start"],
                        e.get("date_end"),
                        e.get("coin_id"),
                        e.get("coin_symbol"),
                        e.get("coin_price_changes"),
                        e.get("tags"),
                        e.get("event_type"),
                        e.get("importance", "medium"),
                        e.get("news_id"),
                    ),
                )
                if cur.rowcount > 0:
                    inserted += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        return inserted
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CoinGecko
# ---------------------------------------------------------------------------

def upsert_coingecko_coins(coins: list[dict]) -> int:
    """INSERT OR REPLACE монеты CoinGecko. Возвращает кол-во."""
    conn = _connect()
    try:
        cur = conn.cursor()
        for c in coins:
            cur.execute(
                "INSERT OR REPLACE INTO coins_coingecko (id, symbol, name) "
                "VALUES (?, ?, ?)",
                (c["id"], c["symbol"], c["name"]),
            )
        conn.commit()
        return len(coins)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CoinMarketCap
# ---------------------------------------------------------------------------

def upsert_cmc_coins(coins: list[dict]) -> int:
    """INSERT OR REPLACE монеты CMC. Возвращает кол-во."""
    conn = _connect()
    try:
        cur = conn.cursor()
        for c in coins:
            cur.execute(
                "INSERT OR REPLACE INTO coins_cmc (id, symbol, name, slug) "
                "VALUES (?, ?, ?, ?)",
                (c["id"], c["symbol"], c["name"], c.get("slug")),
            )
        conn.commit()
        return len(coins)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def upsert_proposals(proposals: list[dict]) -> int:
    """INSERT OR REPLACE proposals. Возвращает кол-во."""
    conn = _connect()
    try:
        cur = conn.cursor()
        for p in proposals:
            choices_json = json.dumps(p.get("choices", []), ensure_ascii=False)
            scores_json = json.dumps(p.get("scores", []), ensure_ascii=False)
            cur.execute(
                "INSERT OR REPLACE INTO proposals "
                "(id, title, space_id, space_name, choices, scores, "
                "scores_total, votes, state, start_ts, end_ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    p["id"],
                    p["title"],
                    p["space_id"],
                    p.get("space_name"),
                    choices_json,
                    scores_json,
                    p.get("scores_total"),
                    p.get("votes"),
                    p.get("state"),
                    p.get("start_ts"),
                    p.get("end_ts"),
                ),
            )
        conn.commit()
        return len(proposals)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def get_coin_id_by_symbol(table: str, symbol: str) -> int | str | None:
    """Получить id монеты по символу из указанной таблицы."""
    allowed = {"coins_coindar", "coins_coingecko", "coins_cmc"}
    if table not in allowed:
        raise ValueError(f"Недопустимая таблица: {table}")
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT id FROM {table} WHERE UPPER(symbol) = UPPER(?) LIMIT 1",
            (symbol,),
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def get_coins_by_symbols(
    table: str, symbols: set[str]
) -> dict[str, int | str]:
    """Маппинг symbol → id для набора символов."""
    allowed = {"coins_coindar", "coins_coingecko", "coins_cmc"}
    if table not in allowed:
        raise ValueError(f"Недопустимая таблица: {table}")
    if not symbols:
        return {}
    conn = _connect()
    try:
        placeholders = ",".join("?" for _ in symbols)
        upper_symbols = [s.upper() for s in symbols]
        rows = conn.execute(
            f"SELECT id, symbol FROM {table} WHERE UPPER(symbol) IN ({placeholders})",
            upper_symbols,
        ).fetchall()
        return {row["symbol"].upper(): row["id"] for row in rows}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_events_stats(binance_coin_ids: set[int]) -> dict:
    """Статистика событий: всего, binance, reliable, important, top_tags, top_coins."""
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
        reliable = conn.execute(
            "SELECT COUNT(*) AS c FROM events WHERE source_reliable = 1"
        ).fetchone()["c"]
        important = conn.execute(
            "SELECT COUNT(*) AS c FROM events WHERE important = 1"
        ).fetchone()["c"]

        binance_count = 0
        if binance_coin_ids:
            placeholders = ",".join("?" for _ in binance_coin_ids)
            binance_count = conn.execute(
                f"SELECT COUNT(*) AS c FROM events WHERE coin_id IN ({placeholders})",
                list(binance_coin_ids),
            ).fetchone()["c"]

        # top tags — считаем в Python через разбор CSV
        rows = conn.execute("SELECT tags FROM events WHERE tags IS NOT NULL").fetchall()
        from collections import Counter
        tag_counter: Counter[str] = Counter()
        for row in rows:
            for tag_id in str(row["tags"]).split(","):
                tag_id = tag_id.strip()
                if tag_id:
                    tag_counter[tag_id] += 1

        # маппинг tag id → name
        tag_names: dict[str, str] = {}
        for trow in conn.execute("SELECT id, name FROM tags").fetchall():
            tag_names[str(trow["id"])] = trow["name"]

        top_tags = [
            {"id": tid, "name": tag_names.get(tid, f"tag_{tid}"), "count": cnt}
            for tid, cnt in tag_counter.most_common(5)
        ]

        # top coins
        top_coins_rows = conn.execute(
            "SELECT coin_id, COUNT(*) AS cnt FROM events "
            "WHERE coin_id IS NOT NULL GROUP BY coin_id ORDER BY cnt DESC LIMIT 5"
        ).fetchall()
        top_coins = []
        for r in top_coins_rows:
            cid = r["coin_id"]
            crow = conn.execute(
                "SELECT symbol, name FROM coins_coindar WHERE id = ?", (cid,)
            ).fetchone()
            symbol = crow["symbol"] if crow else str(cid)
            name = crow["name"] if crow else "?"
            on_binance = cid in binance_coin_ids
            top_coins.append({
                "coin_id": cid,
                "symbol": symbol,
                "name": name,
                "count": r["cnt"],
                "binance": on_binance,
            })

        return {
            "total": total,
            "binance": binance_count,
            "reliable": reliable,
            "important": important,
            "top_tags": top_tags,
            "top_coins": top_coins,
        }
    finally:
        conn.close()


def get_proposals_stats() -> dict:
    """Статистика proposals: всего активных, по DAO."""
    conn = _connect()
    try:
        active = conn.execute(
            "SELECT COUNT(*) AS c FROM proposals WHERE state = 'active'"
        ).fetchone()["c"]

        by_dao = conn.execute(
            "SELECT space_id, space_name, COUNT(*) AS cnt, SUM(votes) AS total_votes "
            "FROM proposals WHERE state = 'active' "
            "GROUP BY space_id ORDER BY cnt DESC"
        ).fetchall()

        dao_list = [
            {
                "space_id": r["space_id"],
                "space_name": r["space_name"] or r["space_id"],
                "active": r["cnt"],
                "total_votes": r["total_votes"] or 0,
            }
            for r in by_dao
        ]

        return {"active": active, "by_dao": dao_list}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Raw News
# ---------------------------------------------------------------------------

def upsert_raw_news(news_items: list[dict]) -> int:
    """INSERT OR IGNORE в raw_news. Возвращает кол-во новых."""
    conn = _connect()
    try:
        cur = conn.cursor()
        inserted = 0
        for n in news_items:
            try:
                raw_json_str = json.dumps(n.get("raw_json", {}), ensure_ascii=False)
                cur.execute(
                    "INSERT OR IGNORE INTO raw_news "
                    "(source, title, url, published_at, tickers, domain, "
                    "sentiment, votes_positive, votes_important, raw_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        n["source"],
                        n["title"],
                        n.get("url"),
                        n.get("published_at"),
                        n.get("tickers", ""),
                        n.get("domain"),
                        n.get("sentiment"),
                        n.get("votes_positive", 0),
                        n.get("votes_important", 0),
                        raw_json_str,
                    ),
                )
                if cur.rowcount > 0:
                    inserted += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        return inserted
    finally:
        conn.close()


def get_unprocessed_news(limit: int = 50) -> list[dict]:
    """SELECT * FROM raw_news WHERE processed = 0."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM raw_news WHERE processed = 0 "
            "ORDER BY fetched_at LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_news_processed(news_ids: list[int]) -> None:
    """UPDATE raw_news SET processed = 1 WHERE id IN (...)."""
    if not news_ids:
        return
    conn = _connect()
    try:
        placeholders = ",".join("?" for _ in news_ids)
        conn.execute(
            f"UPDATE raw_news SET processed = 1 WHERE id IN ({placeholders})",
            news_ids,
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# News Stats
# ---------------------------------------------------------------------------

def get_news_stats() -> dict:
    """Статистика: кол-во по source, processed vs unprocessed."""
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM raw_news").fetchone()["c"]
        processed = conn.execute(
            "SELECT COUNT(*) AS c FROM raw_news WHERE processed = 1"
        ).fetchone()["c"]

        by_source = conn.execute(
            "SELECT source, COUNT(*) AS cnt FROM raw_news GROUP BY source"
        ).fetchall()
        sources = {r["source"]: r["cnt"] for r in by_source}

        return {
            "total": total,
            "processed": processed,
            "unprocessed": total - processed,
            "by_source": sources,
        }
    finally:
        conn.close()


def get_events_by_type() -> dict:
    """Группировка событий по event_type."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT event_type, COUNT(*) AS cnt FROM events "
            "WHERE event_type IS NOT NULL GROUP BY event_type ORDER BY cnt DESC"
        ).fetchall()
        return {r["event_type"]: r["cnt"] for r in rows}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Async: Шаг 2 — Outcome Generator (aiosqlite)
# ---------------------------------------------------------------------------

async def ensure_outcome_tables(db) -> None:
    """Создать таблицы для Шага 2 если не существуют."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS events_v2 (
            id TEXT PRIMARY KEY,
            coin_symbol TEXT NOT NULL,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            date_event TEXT,
            importance TEXT DEFAULT 'medium',
            source TEXT,
            source_name TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            outcomes_generated BOOLEAN DEFAULT 0
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_ev2_type ON events_v2(event_type)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_ev2_coin ON events_v2(coin_symbol)"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS event_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            outcome_key TEXT NOT NULL,
            outcome_text TEXT NOT NULL,
            outcome_category TEXT NOT NULL,
            is_template BOOLEAN DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            probability REAL,
            probability_low REAL,
            probability_high REAL,
            price_impact_pct REAL,
            price_impact_low REAL,
            price_impact_high REAL,
            UNIQUE(event_id, outcome_key)
        )
    """)
    await db.commit()


_DATE_RE = re.compile(
    r"\b(?:"
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}"
    r"|\d{1,2}/\d{1,2}/\d{4}"
    r")\b", re.IGNORECASE)
_NUM_RE = re.compile(r"[+\-]?\$?\d[\d,.]*[%$BMKbmk]?")
_PUNCT_RE = re.compile(r"[^\w\s]")
_MULTI_SPACE = re.compile(r"\s+")


def normalize_event_title(title: str) -> str:
    """Нормализовать заголовок для дедупликации.

    1. lowercase  2. убрать даты  3. убрать числа/$/%
    4. убрать пунктуацию  5. отсортировать слова
    """
    t = title.lower()
    t = _DATE_RE.sub("", t)
    t = _NUM_RE.sub("", t)
    t = _PUNCT_RE.sub(" ", t)
    t = _MULTI_SPACE.sub(" ", t).strip()
    return " ".join(sorted(t.split()))


async def find_similar_event(db, coin_symbol: str, event_type: str,
                             title: str, date_event: str = None) -> bool:
    """Проверить есть ли в БД похожее событие (fuzzy-дедупликация).

    Критерии: тот же coin_symbol + event_type, совпадение >=60% слов
    в нормализованных заголовках, дата +/-3 дня (если обе есть).
    """
    cursor = await db.execute(
        "SELECT title, date_event FROM events_v2 "
        "WHERE coin_symbol = ? AND event_type = ?",
        (coin_symbol, event_type),
    )
    rows = await cursor.fetchall()
    words_new = set(normalize_event_title(title).split())
    if not words_new:
        return False
    for row in rows:
        words_ex = set(normalize_event_title(row["title"]).split())
        if not words_ex:
            continue
        overlap = len(words_new & words_ex) / max(len(words_new), len(words_ex))
        if overlap >= 0.6:
            if date_event and row["date_event"]:
                try:
                    from datetime import datetime
                    d1 = datetime.strptime(date_event[:10], "%Y-%m-%d")
                    d2 = datetime.strptime(str(row["date_event"])[:10], "%Y-%m-%d")
                    if abs((d1 - d2).days) > 3:
                        continue
                except ValueError:
                    pass
            return True
    return False


def make_event_id(coin_symbol: str, event_type: str, title: str) -> str:
    """MD5 хэш для дедупликации событий."""
    raw = coin_symbol.lower() + event_type + title.lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()


async def save_event(db, event: dict) -> str | None:
    """Сохранить событие. Fuzzy + exact дедупликация. Возвращает event_id или None."""
    is_dup = await find_similar_event(
        db, event["coin_symbol"], event["event_type"],
        event["title"], event.get("date_event"),
    )
    if is_dup:
        logger.info("Duplicate skipped: %s", event["title"])
        return None

    event_id = make_event_id(
        event["coin_symbol"], event["event_type"], event["title"]
    )
    await db.execute(
        """INSERT OR IGNORE INTO events_v2
           (id, coin_symbol, event_type, title, date_event,
            importance, source, source_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id,
            event["coin_symbol"],
            event["event_type"],
            event["title"],
            event.get("date_event"),
            event.get("importance", "medium"),
            event.get("source"),
            event.get("source_name"),
        ),
    )
    await db.commit()
    return event_id


async def get_unprocessed_events(db, limit: int = 50) -> list:
    """Получить события без сгенерированных исходов. Возвращает list[dict]."""
    cursor = await db.execute(
        "SELECT * FROM events_v2 WHERE outcomes_generated = 0 "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def save_outcomes(db, event_id: str, outcomes: list) -> None:
    """Сохранить исходы. Удаляет старые перед вставкой (чистая перегенерация)."""
    await db.execute(
        "DELETE FROM event_outcomes WHERE event_id = ?", (event_id,)
    )
    for o in outcomes:
        text = o["text"][:100]
        await db.execute(
            """INSERT INTO event_outcomes
               (event_id, outcome_key, outcome_text, outcome_category, is_template)
               VALUES (?, ?, ?, ?, ?)""",
            (
                event_id,
                o["key"],
                text,
                o["category"],
                1 if o.get("is_template", True) else 0,
            ),
        )
    await db.execute(
        "UPDATE events_v2 SET outcomes_generated = 1 WHERE id = ?",
        (event_id,),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Async: queries for token scanner
# ---------------------------------------------------------------------------

async def get_events_by_date_range(db, start_date: str, end_date: str) -> list:
    """Получить события из events_v2 в диапазоне дат. Формат: YYYY-MM-DD."""
    cursor = await db.execute(
        "SELECT * FROM events_v2 WHERE date_event BETWEEN ? AND ? "
        "ORDER BY date_event",
        (start_date, end_date),
    )
    return await cursor.fetchall()


async def count_events_by_token(db) -> list:
    """Сколько событий по каждому токену в events_v2."""
    cursor = await db.execute(
        "SELECT coin_symbol, COUNT(*) as cnt FROM events_v2 "
        "GROUP BY coin_symbol ORDER BY cnt DESC"
    )
    return await cursor.fetchall()


# ---------------------------------------------------------------------------
# Async: probability estimator (Step 3)
# ---------------------------------------------------------------------------

async def ensure_probability_columns(db) -> None:
    """Добавить колонки probability если их нет. Idempotent."""
    for col in ["probability REAL", "probability_low REAL", "probability_high REAL"]:
        col_name = col.split()[0]
        try:
            await db.execute(f"SELECT {col_name} FROM event_outcomes LIMIT 1")
        except Exception:
            await db.execute(f"ALTER TABLE event_outcomes ADD COLUMN {col}")
    await db.commit()


async def get_outcomes_for_event(db, event_id: str) -> list:
    """Все исходы для конкретного события."""
    cursor = await db.execute(
        "SELECT * FROM event_outcomes WHERE event_id = ? ORDER BY outcome_key",
        (event_id,),
    )
    return await cursor.fetchall()


async def get_events_with_outcomes(db, limit: int = 50) -> list[dict]:
    """События с исходами но без вероятностей."""
    cursor = await db.execute(
        "SELECT DISTINCT e.* FROM events_v2 e "
        "JOIN event_outcomes eo ON e.id = eo.event_id "
        "WHERE eo.probability IS NULL "
        "ORDER BY e.created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def update_outcome_probability(db, event_id: str, outcome_key: str,
                                      probability: float, prob_low: float,
                                      prob_high: float) -> None:
    """Обновить вероятность одного исхода."""
    await db.execute(
        "UPDATE event_outcomes "
        "SET probability = ?, probability_low = ?, probability_high = ? "
        "WHERE event_id = ? AND outcome_key = ?",
        (probability, prob_low, prob_high, event_id, outcome_key),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Async: impact estimator (Step 4)
# ---------------------------------------------------------------------------

async def ensure_impact_columns(db) -> None:
    """Добавить колонки price_impact если их нет. Idempotent."""
    for col in ["price_impact_pct REAL", "price_impact_low REAL",
                "price_impact_high REAL"]:
        col_name = col.split()[0]
        try:
            await db.execute(f"SELECT {col_name} FROM event_outcomes LIMIT 1")
        except Exception:
            await db.execute(f"ALTER TABLE event_outcomes ADD COLUMN {col}")
    await db.commit()


async def get_events_without_impacts(db, limit: int = 50) -> list[dict]:
    """События с вероятностями но без оценки влияния на цену."""
    cursor = await db.execute(
        "SELECT DISTINCT e.* FROM events_v2 e "
        "JOIN event_outcomes eo ON e.id = eo.event_id "
        "WHERE eo.probability IS NOT NULL AND eo.price_impact_pct IS NULL "
        "ORDER BY e.created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def update_outcome_impact(db, event_id: str, outcome_key: str,
                                 impact_pct: float, impact_low: float,
                                 impact_high: float) -> None:
    """Обновить оценку влияния на цену одного исхода."""
    await db.execute(
        "UPDATE event_outcomes "
        "SET price_impact_pct = ?, price_impact_low = ?, price_impact_high = ? "
        "WHERE event_id = ? AND outcome_key = ?",
        (impact_pct, impact_low, impact_high, event_id, outcome_key),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Async: signal calculator (Steps 5-6)
# ---------------------------------------------------------------------------

async def get_events_with_complete_data(db, limit: int = 50) -> list:
    """События у которых ВСЕ outcomes имеют probability И price_impact_pct."""
    cursor = await db.execute(
        "SELECT e.*, eo.outcome_key, eo.outcome_text, eo.outcome_category, "
        "eo.probability, eo.probability_low, eo.probability_high, "
        "eo.price_impact_pct, eo.price_impact_low, eo.price_impact_high "
        "FROM events_v2 e "
        "JOIN event_outcomes eo ON e.id = eo.event_id "
        "WHERE eo.probability IS NOT NULL AND eo.price_impact_pct IS NOT NULL "
        "AND e.id NOT IN ("
        "  SELECT event_id FROM event_outcomes "
        "  WHERE probability IS NULL OR price_impact_pct IS NULL"
        ") "
        "ORDER BY e.coin_symbol, e.created_at DESC "
        "LIMIT ?",
        (limit,),
    )
    return await cursor.fetchall()
