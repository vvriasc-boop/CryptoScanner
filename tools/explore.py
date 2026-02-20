"""CryptoScanner Multi-API Explorer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import os
from collections import Counter
from datetime import datetime, timedelta

from tabulate import tabulate

import config
from database import db
from services.coindar import CoindarClient
from services.coingecko import CoinGeckoClient
from services.coinmarketcap import CoinMarketCapClient
from services.snapshot import SnapshotClient


# Детерминированный топ-10 для тестирования цен (оба API)
TOP10_SYMBOLS: list[str] = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT",
]


# ---------------------------------------------------------------------------
# Вспомогательные
# ---------------------------------------------------------------------------

def _fmt_price(val: float | None) -> str:
    """Форматирование цены: $97,500."""
    if val is None:
        return "N/A"
    if val >= 1:
        return f"${val:,.0f}"
    return f"${val:.4f}"


def _fmt_pct(val: float | None) -> str:
    """Форматирование процента: +2.5%."""
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


def _fmt_big(val: float | None) -> str:
    """Форматирование больших чисел: $1.9T, $45B."""
    if val is None:
        return "N/A"
    if val >= 1e12:
        return f"${val / 1e12:.1f}T"
    if val >= 1e9:
        return f"${val / 1e9:.1f}B"
    if val >= 1e6:
        return f"${val / 1e6:.1f}M"
    return f"${val:,.0f}"


def _safe_div(a: float, b: float) -> float:
    """Безопасное деление."""
    if b == 0:
        return 0.0
    return a / b


# ---------------------------------------------------------------------------
# Шаг 1: Валидация конфигурации
# ---------------------------------------------------------------------------

def validate_config() -> dict[str, bool]:
    """Проверка ключей. Возвращает {api: доступен}."""
    print("\n⚙️  Проверяю конфигурацию...")
    status: dict[str, bool] = {}

    if config.COINDAR_TOKEN:
        print("   COINDAR_ACCESS_TOKEN:  ✅ задан")
        status["coindar"] = True
    else:
        print("   COINDAR_ACCESS_TOKEN:  ⚠️ не задан (пропущу Coindar)")
        status["coindar"] = False

    if config.COINGECKO_KEY:
        print("   COINGECKO_API_KEY:     ✅ задан")
        status["coingecko"] = True
    else:
        print("   COINGECKO_API_KEY:     ⚠️ не задан (пропущу CoinGecko)")
        status["coingecko"] = False

    if config.CMC_KEY:
        print("   CMC_API_KEY:           ✅ задан")
        status["cmc"] = True
    else:
        print("   CMC_API_KEY:           ⚠️ не задан (пропущу CoinMarketCap)")
        status["cmc"] = False

    print("   Snapshot:              ✅ ключ не нужен")
    status["snapshot"] = True

    # Проверка: если ни одного ключа нет (кроме Snapshot)
    if not any([status["coindar"], status["coingecko"], status["cmc"]]):
        print("\n⛔ Ни один API-ключ не задан (кроме Snapshot).")
        print("   Заполните .env и перезапустите.")
        sys.exit(1)

    return status


# ---------------------------------------------------------------------------
# Шаг 3A: Coindar
# ---------------------------------------------------------------------------

def explore_coindar(report: dict) -> None:
    """Исследование Coindar API."""
    print("\n══════════════ COINDAR ══════════════")

    client = CoindarClient(
        token=config.COINDAR_TOKEN,
        base_url=config.COINDAR_BASE_URL,
        timeout=config.REQUEST_TIMEOUT,
        delay=config.DEFAULT_DELAY,
    )

    print("🔌 Проверяю подключение...")
    if not client.check_connection():
        print("❌ Подключение не удалось")
        report["apis"]["coindar"] = {"status": "error", "reason": "connection failed"}
        return
    print("✅ Подключение OK")

    # Теги
    print("\n📋 Загружаю теги...")
    tags = client.get_tags()
    db.upsert_tags(tags)
    tag_names = ", ".join(t["name"] for t in tags[:10])
    print(f"✅ {len(tags)} тегов: {tag_names}{'...' if len(tags) > 10 else ''}")

    # Монеты
    print("\n🪙 Загружаю монеты (все страницы)...")
    coins = client.get_coins()
    db.upsert_coindar_coins(coins)
    binance_map = db.get_coins_by_symbols("coins_coindar", config.BINANCE_SYMBOLS)
    binance_count = len(binance_map)
    print(f"✅ {len(coins)} монет (на Binance: {binance_count})")

    # События на 7 дней
    today = datetime.now()
    date_start = today.strftime("%Y-%m-%d")
    date_end = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    print(f"\n📅 Загружаю события на 7 дней ({date_start} — {date_end})...")
    events = client.get_events(date_start=date_start, date_end=date_end)
    db.upsert_events(events)

    binance_coin_ids = set(binance_map.values())
    binance_events = [
        e for e in events if e.get("coin_id") in binance_coin_ids
    ]
    print(f"✅ {len(events)} событий (Binance: {len(binance_events)})")

    # События по BNB (30 дней)
    date_end_30 = (today + timedelta(days=30)).strftime("%Y-%m-%d")
    bnb_id = binance_map.get("BNB")
    if bnb_id:
        print(f"\n🔍 События по BNB (30 дней)...")
        bnb_events = client.get_events(
            date_start=date_start, date_end=date_end_30,
            coin_ids=[bnb_id],
        )
        print(f"✅ {len(bnb_events)} событий")

    # Статистика
    stats = db.get_events_stats(binance_coin_ids)

    report["apis"]["coindar"] = {
        "status": "ok",
        "tags_count": len(tags),
        "coins_count": len(coins),
        "binance_coins": binance_count,
        "events_7d": len(events),
        "events_binance": len(binance_events),
        "events_reliable": stats["reliable"],
        "events_important": stats["important"],
        "top_tags": stats["top_tags"],
        "top_coins": stats["top_coins"],
    }


# ---------------------------------------------------------------------------
# Шаг 3B: CoinGecko
# ---------------------------------------------------------------------------

def explore_coingecko(report: dict) -> None:
    """Исследование CoinGecko API."""
    print("\n══════════════ COINGECKO ══════════════")

    client = CoinGeckoClient(
        api_key=config.COINGECKO_KEY,
        base_url=config.COINGECKO_BASE_URL,
        timeout=config.REQUEST_TIMEOUT,
        delay=2.0,
    )

    print("🔌 Проверяю подключение...")
    if not client.check_connection():
        print("❌ Подключение не удалось")
        report["apis"]["coingecko"] = {"status": "error", "reason": "connection failed"}
        return
    print("✅ (V3) To the Moon!")

    # Список монет
    print("\n🪙 Загружаю список монет...")
    coins = client.get_coins_list()
    db.upsert_coingecko_coins(coins)
    print(f"✅ {len(coins):,} монет")

    # Категории
    print("\n📋 Загружаю категории...")
    categories = client.get_categories()
    print(f"✅ {len(categories)} категорий")

    # Маппинг symbol → coingecko id: сначала хардкод, потом fallback из coins_list
    symbol_to_cg: dict[str, str] = dict(config.COINGECKO_ID_MAP)
    for c in coins:
        sym = c["symbol"].upper()
        if sym in config.BINANCE_SYMBOLS and sym not in symbol_to_cg:
            symbol_to_cg[sym] = c["id"]

    # Цены топ-10 (детерминированный порядок)
    top10_symbols = TOP10_SYMBOLS
    top10_ids = [symbol_to_cg[s] for s in top10_symbols if s in symbol_to_cg]

    print(f"\n💰 Загружаю цены топ-10 Binance монет...")
    prices = client.get_prices(top10_ids)
    price_parts: list[str] = []
    btc_price: float | None = None
    btc_change: float | None = None
    for cg_id in top10_ids:
        p = prices.get(cg_id, {})
        usd = p.get("usd")
        sym = next((s for s, i in symbol_to_cg.items() if i == cg_id), cg_id)
        price_parts.append(f"{sym}={_fmt_price(usd)}")
        if cg_id == symbol_to_cg.get("BTC"):
            btc_price = usd
            btc_change = p.get("usd_24h_change")
    print(f"✅ {' '.join(price_parts)}")

    # Детали BTC
    btc_cg_id = symbol_to_cg.get("BTC", "bitcoin")
    print(f"\n🔍 Детальная информация по BTC...")
    btc_info = client.get_coin_info(btc_cg_id)
    if btc_info:
        cats = btc_info.get("categories", [])
        cats_str = ", ".join(c for c in cats if c) if cats else "N/A"
        md = btc_info.get("market_data", {})
        mcap = md.get("market_cap", {}).get("usd")
        vol = md.get("total_volume", {}).get("usd")
        print(f"✅ Категории: {cats_str}")
        print(f"   Market Cap: {_fmt_big(mcap)} | Volume 24h: {_fmt_big(vol)}")

    binance_coverage = len(symbol_to_cg)

    report["apis"]["coingecko"] = {
        "status": "ok",
        "coins_count": len(coins),
        "binance_coverage": binance_coverage,
        "categories_count": len(categories),
        "btc_price": btc_price,
        "btc_24h_change": btc_change,
    }


# ---------------------------------------------------------------------------
# Шаг 3C: CoinMarketCap
# ---------------------------------------------------------------------------

def explore_cmc(report: dict) -> None:
    """Исследование CoinMarketCap API."""
    print("\n══════════════ COINMARKETCAP ══════════════")

    client = CoinMarketCapClient(
        api_key=config.CMC_KEY,
        base_url=config.CMC_BASE_URL,
        timeout=config.REQUEST_TIMEOUT,
        delay=2.0,
    )

    print("🔌 Проверяю подключение...")
    key_info = client.check_connection()
    if key_info is None:
        print("❌ Подключение не удалось")
        report["apis"]["coinmarketcap"] = {
            "status": "error", "reason": "connection failed",
        }
        return
    plan = key_info.get("plan", "unknown")
    used = key_info.get("credits_used", 0)
    limit = key_info.get("credit_limit", 0)
    print(f"✅ Plan: {plan} | Credits used: {used}/{limit}")

    credits_start = used

    # Маппинг
    print("\n🪙 Загружаю маппинг монет (топ-500)...")
    coins = client.get_map(limit=500)
    db.upsert_cmc_coins(coins)
    print(f"✅ {len(coins)} монет")

    # Категории
    print("\n📋 Загружаю категории...")
    categories = client.get_categories(limit=20)
    print(f"✅ {len(categories)} категорий")

    # Events
    print("\n🔍 Проверяю доступность Events API...")
    events_ok, events_msg = client.check_events_available()
    if events_ok:
        print(f"✅ {events_msg}")
    else:
        print(f"⚠️ {events_msg}")

    # Котировки топ-10
    top10 = TOP10_SYMBOLS
    print(f"\n💰 Загружаю котировки топ-10 Binance...")
    quotes = client.get_quotes(top10)
    quote_parts: list[str] = []
    for sym in top10:
        q = quotes.get(sym, {})
        price = q.get("price")
        quote_parts.append(f"{sym}={_fmt_price(price)}")
    print(f"✅ {' '.join(quote_parts)}")

    # Подсчёт credits
    key_info_after = client.check_connection()
    credits_end = key_info_after.get("credits_used", used) if key_info_after else used
    credits_spent = credits_end - credits_start
    print(f"   Использовано credits: ~{credits_spent}")

    report["apis"]["coinmarketcap"] = {
        "status": "ok",
        "coins_count": len(coins),
        "categories_count": len(categories),
        "credits_used": credits_end,
        "credits_spent_session": credits_spent,
        "credit_limit": limit,
        "events_available": events_ok,
        "events_msg": events_msg,
    }


# ---------------------------------------------------------------------------
# Шаг 3D: Snapshot
# ---------------------------------------------------------------------------

def explore_snapshot(report: dict) -> None:
    """Исследование Snapshot GraphQL API."""
    print("\n══════════════ SNAPSHOT ══════════════")

    client = SnapshotClient(
        url=config.SNAPSHOT_BASE_URL,
        timeout=config.REQUEST_TIMEOUT,
        delay=config.DEFAULT_DELAY,
    )

    print("🔌 Проверяю подключение...")
    if not client.check_connection():
        print("❌ GraphQL недоступен")
        report["apis"]["snapshot"] = {"status": "error", "reason": "connection failed"}
        return
    print("✅ GraphQL OK")

    # Активные proposals
    print(f"\n📊 Загружаю активные proposals ({len(config.SNAPSHOT_SPACES)} DAO)...")
    active = client.get_active_proposals(config.SNAPSHOT_SPACES, limit=50)
    db.upsert_proposals(active)
    print(f"✅ {len(active)} активных proposals")

    # Закрытые proposals
    print("\n📊 Загружаю недавно закрытые (для анализа)...")
    closed = client.get_closed_proposals(config.SNAPSHOT_SPACES, limit=20)
    db.upsert_proposals(closed)
    print(f"✅ {len(closed)} закрытых proposals")

    # Статистика
    stats = db.get_proposals_stats()
    daos_with_activity = len(stats["by_dao"])

    report["apis"]["snapshot"] = {
        "status": "ok",
        "active_proposals": len(active),
        "closed_proposals": len(closed),
        "daos_with_activity": daos_with_activity,
        "by_dao": stats["by_dao"],
    }


# ---------------------------------------------------------------------------
# Шаг 4: Сводный отчёт (текст)
# ---------------------------------------------------------------------------

def build_text_report(report: dict) -> str:
    """Формирование текстового отчёта."""
    lines: list[str] = []
    date_str = report["date"]

    lines.append("═" * 63)
    lines.append("          CRYPTOSCANNER — MULTI-API EXPLORATION REPORT")
    lines.append(f"          {date_str}")
    lines.append("═" * 63)

    # --- Статус API ---
    lines.append("\n📡 СТАТУС API")
    api_table: list[list[str]] = []
    for api_name, label in [
        ("coindar", "Coindar"),
        ("coingecko", "CoinGecko"),
        ("coinmarketcap", "CoinMarketCap"),
        ("snapshot", "Snapshot"),
    ]:
        info = report["apis"].get(api_name, {})
        st = info.get("status", "skip")
        if st == "ok":
            status_str = "✅ OK"
        elif st == "error":
            status_str = "❌ ERR"
        else:
            status_str = "⚠️ SKIP"
        note = _api_note(api_name, info)
        api_table.append([label, status_str, note])

    lines.append(tabulate(
        api_table,
        headers=["API", "Статус", "Примечания"],
        tablefmt="simple_outline",
    ))

    # --- Coindar ---
    cd = report["apis"].get("coindar", {})
    if cd.get("status") == "ok":
        lines.append("\n📊 COINDAR")
        total = cd.get("events_7d", 0)
        bn = cd.get("events_binance", 0)
        rel = cd.get("events_reliable", 0)
        imp = cd.get("events_important", 0)
        pct_bn = _safe_div(bn * 100, total)
        pct_rel = _safe_div(rel * 100, total)
        pct_imp = _safe_div(imp * 100, total)
        lines.append(f"   Событий на 7 дней:          {total}")
        lines.append(f"   Из них по Binance-монетам:   {bn} ({pct_bn:.1f}%)")
        lines.append(f"   С надёжным источником:      {rel} ({pct_rel:.1f}%)")
        lines.append(f"   Важных:                      {imp} ({pct_imp:.1f}%)")

        top_tags = cd.get("top_tags", [])
        if top_tags:
            lines.append("\n   ТОП-5 КАТЕГОРИЙ:")
            tag_tbl = [
                [i + 1, t["name"], t["count"]]
                for i, t in enumerate(top_tags)
            ]
            lines.append(tabulate(
                tag_tbl, headers=["#", "Категория", "Кол-во"],
                tablefmt="simple_outline",
            ))

        top_coins = cd.get("top_coins", [])
        if top_coins:
            lines.append("\n   ТОП-5 МОНЕТ:")
            coin_tbl = [
                [c["symbol"], c["name"], c["count"], "✅" if c["binance"] else ""]
                for c in top_coins
            ]
            lines.append(tabulate(
                coin_tbl, headers=["Символ", "Название", "Кол-во", "Binance?"],
                tablefmt="simple_outline",
            ))

    # --- CoinGecko ---
    cg = report["apis"].get("coingecko", {})
    if cg.get("status") == "ok":
        lines.append("\n📊 COINGECKO")
        lines.append(f"   Всего монет в базе:     {cg.get('coins_count', 0):,}")
        lines.append(
            f"   Совпадений с Binance:   {cg.get('binance_coverage', 0)} "
            f"из {len(config.BINANCE_SYMBOLS)}"
        )
        lines.append(f"   Категорий:              {cg.get('categories_count', 0)}")
        lines.append(f"   BTC цена:               {_fmt_price(cg.get('btc_price'))}")
        lines.append(f"   BTC 24h change:         {_fmt_pct(cg.get('btc_24h_change'))}")

    # --- CMC ---
    cmc = report["apis"].get("coinmarketcap", {})
    if cmc.get("status") == "ok":
        lines.append("\n📊 COINMARKETCAP")
        lines.append(f"   Монет в маппинге:       {cmc.get('coins_count', 0)}")
        lines.append(
            f"   Credits использовано:   ~{cmc.get('credits_spent_session', 0)} "
            f"(всего {cmc.get('credits_used', 0)}/{cmc.get('credit_limit', 0)})"
        )
        ev = "✅ доступен" if cmc.get("events_available") else "⚠️ недоступен"
        lines.append(f"   Events API:             {ev}")

    # --- Snapshot ---
    snap = report["apis"].get("snapshot", {})
    if snap.get("status") == "ok":
        lines.append("\n📊 SNAPSHOT")
        lines.append(f"   Активных proposals:     {snap.get('active_proposals', 0)}")

        by_dao = snap.get("by_dao", [])
        if by_dao:
            lines.append("\n   По DAO:")
            dao_tbl = [
                [d["space_name"], d["active"], d["total_votes"]]
                for d in by_dao
            ]
            lines.append(tabulate(
                dao_tbl, headers=["DAO", "Активных", "Голосов"],
                tablefmt="simple_outline",
            ))

        # Примеры активных proposals из БД
        _append_proposal_examples(lines)

    # --- Перекрытие данных ---
    lines.append("\n🔗 ПЕРЕКРЫТИЕ ДАННЫХ")
    overlap = _calc_overlap(report)
    lines.append(f"   Монет в Coindar ∩ CoinGecko ∩ CMC (по symbol): {overlap['common']}")
    lines.append(
        f"   Binance-монет с данными из всех источников: "
        f"{overlap['binance']} из {len(config.BINANCE_SYMBOLS)}"
    )
    report["overlap"] = overlap

    # --- Пригодность для MVP ---
    lines.append("\n🔧 ПРИГОДНОСТЬ ДЛЯ MVP")
    verdict = _calc_verdict(report)
    for api_name, assessment in verdict["assessments"].items():
        lines.append(f"   {api_name:14s} {assessment}")
    lines.append(f"\n   Рекомендация: {verdict['recommendation']}")
    report["verdict"] = verdict["recommendation"]

    lines.append("\n" + "═" * 63)
    return "\n".join(lines)


def _api_note(api_name: str, info: dict) -> str:
    """Краткое примечание для таблицы статуса."""
    st = info.get("status", "skip")
    if st == "skip":
        return info.get("reason", "Ключ не задан")
    if st == "error":
        return info.get("reason", "Ошибка")
    if api_name == "coindar":
        return f"{info.get('coins_count', 0)} монет, {info.get('events_7d', 0)} событий"
    if api_name == "coingecko":
        return f"{info.get('coins_count', 0):,} монеты"
    if api_name == "coinmarketcap":
        used = info.get("credits_used", 0)
        limit = info.get("credit_limit", 0)
        return f"Credits: {used}/{limit}"
    if api_name == "snapshot":
        return f"{info.get('active_proposals', 0)} активных proposals"
    return ""


def _append_proposal_examples(lines: list[str]) -> None:
    """Добавить примеры активных proposals в отчёт."""
    import sqlite3
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM proposals WHERE state = 'active' "
            "ORDER BY end_ts ASC LIMIT 5"
        ).fetchall()
        if not rows:
            return
        lines.append("\n   ПРИМЕРЫ АКТИВНЫХ PROPOSALS:")
        now_ts = int(datetime.now().timestamp())
        for i, row in enumerate(rows, 1):
            title = row["title"][:60]
            space = row["space_name"] or row["space_id"]
            end_ts = row["end_ts"] or 0
            days_left = max(0, (end_ts - now_ts) // 86400)
            votes = row["votes"] or 0

            choices_raw = row["choices"] or "[]"
            scores_raw = row["scores"] or "[]"
            try:
                choices = json.loads(choices_raw)
                scores = json.loads(scores_raw)
            except (json.JSONDecodeError, TypeError):
                choices, scores = [], []

            total = row["scores_total"] or 0
            choice_parts: list[str] = []
            for ci, ch in enumerate(choices):
                sc = scores[ci] if ci < len(scores) else 0
                pct = _safe_div(sc * 100, total)
                choice_parts.append(f"{ch} ({pct:.0f}%)")

            lines.append(
                f"   {i}. [{space}] \"{title}\" — {days_left} дн. до конца"
            )
            if choice_parts:
                lines.append(
                    f"      {', '.join(choice_parts)} | {votes} voters"
                )
    finally:
        conn.close()


def _calc_overlap(report: dict) -> dict:
    """Подсчёт перекрытия данных между API."""
    import sqlite3
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cd_syms: set[str] = set()
        cg_syms: set[str] = set()
        cmc_syms: set[str] = set()

        for row in conn.execute("SELECT UPPER(symbol) AS s FROM coins_coindar"):
            cd_syms.add(row["s"])
        for row in conn.execute("SELECT UPPER(symbol) AS s FROM coins_coingecko"):
            cg_syms.add(row["s"])
        for row in conn.execute("SELECT UPPER(symbol) AS s FROM coins_cmc"):
            cmc_syms.add(row["s"])

        # Пересечение только непустых
        sets = [s for s in [cd_syms, cg_syms, cmc_syms] if s]
        if sets:
            common = sets[0]
            for s in sets[1:]:
                common = common & s
        else:
            common = set()

        binance_in_all = config.BINANCE_SYMBOLS & common if common else set()

        return {
            "common": len(common),
            "binance": len(binance_in_all),
            "coindar_symbols": len(cd_syms),
            "coingecko_symbols": len(cg_syms),
            "cmc_symbols": len(cmc_syms),
        }
    finally:
        conn.close()


def _calc_verdict(report: dict) -> dict:
    """Оценка пригодности для MVP."""
    assessments: dict[str, str] = {}

    cd = report["apis"].get("coindar", {})
    if cd.get("status") == "ok":
        ev = cd.get("events_7d", 0)
        assessments["Coindar:"] = "OK" if ev >= 10 else "МАЛО событий"
    elif cd.get("status") == "skip":
        assessments["Coindar:"] = "SKIP — ключ не задан"
    else:
        assessments["Coindar:"] = f"ОШИБКА — {cd.get('reason', '?')}"

    cg = report["apis"].get("coingecko", {})
    if cg.get("status") == "ok":
        assessments["CoinGecko:"] = "OK — метаданные и цены"
    else:
        assessments["CoinGecko:"] = f"ОШИБКА — {cg.get('reason', '?')}"

    cmc = report["apis"].get("coinmarketcap", {})
    if cmc.get("status") == "ok":
        ev_note = ""
        if not cmc.get("events_available"):
            ev_note = " (Events недоступен)"
        assessments["CoinMarketCap:"] = f"OK — цены и маппинг{ev_note}"
    else:
        assessments["CoinMarketCap:"] = f"ОШИБКА — {cmc.get('reason', '?')}"

    snap = report["apis"].get("snapshot", {})
    if snap.get("status") == "ok":
        active = snap.get("active_proposals", 0)
        if active >= 5:
            assessments["Snapshot:"] = f"OK — {active} активных proposals"
        else:
            assessments["Snapshot:"] = f"МАЛО — только {active} активных"
    else:
        assessments["Snapshot:"] = f"ОШИБКА — {snap.get('reason', '?')}"

    # Общая рекомендация
    ok_apis = sum(
        1 for a in report["apis"].values() if a.get("status") == "ok"
    )
    if ok_apis >= 3:
        recommendation = "ДОСТАТОЧНО ДЛЯ MVP"
    elif cd.get("status") != "ok" and ok_apis >= 2:
        recommendation = "НУЖЕН COINDAR для полного покрытия"
    else:
        recommendation = "НУЖНЫ ДОППОИСТОЧНИКИ"

    return {"assessments": assessments, "recommendation": recommendation}


# ---------------------------------------------------------------------------
# Шаг 5: Сохранение
# ---------------------------------------------------------------------------

def save_reports(report: dict, text_report: str) -> None:
    """Сохранение .txt и .json отчётов."""
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    date_str = report["date"].replace("-", "")

    txt_path = config.REPORTS_DIR / f"explore_{date_str}.txt"
    json_path = config.REPORTS_DIR / f"explore_{date_str}.json"

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text_report)

    # JSON-отчёт: упрощённая версия
    json_report = {
        "date": report["date"],
        "apis": {},
        "overlap": report.get("overlap", {}),
        "verdict": report.get("verdict", ""),
    }
    for api_name in ["coindar", "coingecko", "coinmarketcap", "snapshot"]:
        info = report["apis"].get(api_name, {})
        json_report["apis"][api_name] = _simplify_api_report(api_name, info)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Отчёт сохранён:")
    print(f"   {txt_path}")
    print(f"   {json_path}")


def _simplify_api_report(api_name: str, info: dict) -> dict:
    """Упрощённая версия для JSON."""
    st = info.get("status", "skip")
    if st == "skip":
        return {"status": "skip", "reason": info.get("reason", "no key")}
    if st == "error":
        return {"status": "error", "reason": info.get("reason", "unknown")}

    if api_name == "coindar":
        return {
            "status": "ok",
            "coins_count": info.get("coins_count", 0),
            "events_7d": info.get("events_7d", 0),
            "events_binance": info.get("events_binance", 0),
        }
    if api_name == "coingecko":
        return {
            "status": "ok",
            "coins_count": info.get("coins_count", 0),
            "categories_count": info.get("categories_count", 0),
            "btc_price": info.get("btc_price"),
        }
    if api_name == "coinmarketcap":
        return {
            "status": "ok",
            "coins_count": info.get("coins_count", 0),
            "credits_used": info.get("credits_used", 0),
            "events_available": info.get("events_available", False),
        }
    if api_name == "snapshot":
        return {
            "status": "ok",
            "active_proposals": info.get("active_proposals", 0),
            "daos_with_activity": info.get("daos_with_activity", 0),
        }
    return {"status": st}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    """Точка входа explore.py."""
    print("🚀 CryptoScanner Multi-API Explorer")
    print(f"   Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Шаг 1: конфиг
    api_status = validate_config()

    # Шаг 2: БД
    print("\n💾 Инициализирую базу данных...")
    db.init_db()
    print(f"✅ БД готова: {config.DB_PATH.name}")

    # Шаг 3: исследование
    report: dict = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "apis": {},
    }

    # 3A: Coindar
    if api_status.get("coindar"):
        try:
            explore_coindar(report)
        except Exception as e:
            report["apis"]["coindar"] = {"status": "error", "reason": str(e)}
            print(f"❌ Coindar ошибка: {e}")
    else:
        report["apis"]["coindar"] = {"status": "skip", "reason": "no key"}

    # 3B: CoinGecko
    if api_status.get("coingecko"):
        try:
            explore_coingecko(report)
        except Exception as e:
            report["apis"]["coingecko"] = {"status": "error", "reason": str(e)}
            print(f"❌ CoinGecko ошибка: {e}")
    else:
        report["apis"]["coingecko"] = {"status": "skip", "reason": "no key"}

    # 3C: CMC
    if api_status.get("cmc"):
        try:
            explore_cmc(report)
        except Exception as e:
            report["apis"]["coinmarketcap"] = {"status": "error", "reason": str(e)}
            print(f"❌ CoinMarketCap ошибка: {e}")
    else:
        report["apis"]["coinmarketcap"] = {"status": "skip", "reason": "no key"}

    # 3D: Snapshot
    try:
        explore_snapshot(report)
    except Exception as e:
        report["apis"]["snapshot"] = {"status": "error", "reason": str(e)}
        print(f"❌ Snapshot ошибка: {e}")

    # Шаг 4: отчёт
    text_report = build_text_report(report)
    print(text_report)

    # Шаг 5: сохранение
    save_reports(report, text_report)

    print("\n✅ Исследование завершено!")


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
