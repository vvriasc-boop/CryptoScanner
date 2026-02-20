"""CoinMarketCal Events Explorer — разведка API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import os
from datetime import datetime, timedelta

from tabulate import tabulate

import config
from services.coinmarketcal_events import CoinMarketCalClient


# ---------------------------------------------------------------------------
# Вспомогательные
# ---------------------------------------------------------------------------

def _detect_fields(obj: dict | list) -> list[list[str]]:
    """Определить поля и типы из первого объекта. Возвращает [[key, type, example]]."""
    if isinstance(obj, list):
        if not obj:
            return []
        obj = obj[0]
    if not isinstance(obj, dict):
        return [["(value)", type(obj).__name__, str(obj)[:60]]]
    rows: list[list[str]] = []
    for key, val in obj.items():
        type_name = type(val).__name__
        example = _truncate(val, 60)
        rows.append([key, type_name, example])
    return rows


def _truncate(val: object, max_len: int) -> str:
    """Превратить значение в строку, обрезать до max_len."""
    if val is None:
        return "None"
    s = str(val)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def _extract_list(data: dict | list) -> tuple[list, str]:
    """
    Если ответ обёрнут в dict — найти список внутри.
    Возвращает (list, описание_пути).
    """
    if isinstance(data, list):
        return data, "list (top-level)"

    if isinstance(data, dict):
        # Ищем известные ключи-обёртки
        for key in ("body", "data", "results", "events", "items"):
            if key in data and isinstance(data[key], list):
                return data[key], f'dict -> "{key}" (list)'

        # Если один ключ и это список
        list_keys = [k for k, v in data.items() if isinstance(v, list)]
        if len(list_keys) == 1:
            k = list_keys[0]
            return data[k], f'dict -> "{k}" (list)'

    return [], f"unexpected type: {type(data).__name__}"


def _raw_json(data: object, limit: int = 3) -> str:
    """Красивый JSON первых N элементов."""
    if isinstance(data, list):
        subset = data[:limit]
    elif isinstance(data, dict):
        subset = data
    else:
        subset = data
    return json.dumps(subset, indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Шаги исследования
# ---------------------------------------------------------------------------

def step_validate() -> None:
    """Шаг 1: Валидация ключа."""
    print("\n⚙️  Проверяю RAPIDAPI_KEY...")
    if not config.RAPIDAPI_KEY:
        print("❌ RAPIDAPI_KEY не задан в .env")
        print("   Получите ключ на rapidapi.com и добавьте в .env")
        sys.exit(1)
    print(f"✅ RAPIDAPI_KEY задан ({config.RAPIDAPI_KEY[:8]}...)")


def step_check_connection(client: CoinMarketCalClient) -> bool:
    """Шаг 2: Проверка подключения."""
    print("\n🔌 Проверяю CoinMarketCal через RapidAPI...")
    if not client.check_connection():
        print("❌ Подключение не удалось")
        return False
    print("✅ Подключение OK")
    return True


def step_categories(
    client: CoinMarketCalClient, report: dict
) -> None:
    """Шаг 3: Загрузка категорий."""
    print("\n" + "=" * 50)
    print("📋 GET /categories")

    raw = client.get_categories()
    items, path_desc = _extract_list(raw)

    print(f"✅ Ответ получен. Тип: {path_desc}, кол-во: {len(items)}")
    print(f"\n📋 RAW (первые 3):")
    print(_raw_json(items[:3] if items else raw))

    fields = _detect_fields(items)
    if fields:
        print(f"\n📋 Структура полей:")
        print(tabulate(
            fields, headers=["Поле", "Тип", "Пример"],
            tablefmt="simple_outline",
        ))

    report["categories_count"] = len(items)
    report["categories_sample"] = items[:5]
    report["categories_fields"] = {r[0]: r[1] for r in fields}


def step_coins(
    client: CoinMarketCalClient, report: dict
) -> None:
    """Шаг 4: Загрузка монет."""
    print("\n" + "=" * 50)
    print("🪙 GET /coins?page=1&max=20")

    raw = client.get_coins(page=1, max_results=20)
    items, path_desc = _extract_list(raw)

    print(f"✅ Ответ получен. Тип: {path_desc}, кол-во: {len(items)}")
    print(f"\n🪙 RAW (первые 3):")
    print(_raw_json(items[:3] if items else raw))

    fields = _detect_fields(items)
    if fields:
        print(f"\n🪙 Структура полей:")
        print(tabulate(
            fields, headers=["Поле", "Тип", "Пример"],
            tablefmt="simple_outline",
        ))

    # Проверка пагинации — запрос page=2
    has_pagination = False
    try:
        raw2 = client.get_coins(page=2, max_results=20)
        items2, _ = _extract_list(raw2)
        has_pagination = len(items2) > 0
        print(f"\n🪙 Пагинация (page=2): {'✅ есть' if has_pagination else '❌ нет'}"
              f" ({len(items2)} результатов)")
    except Exception as e:
        print(f"\n🪙 Пагинация (page=2): ❌ ошибка — {e}")

    report["coins_count"] = len(items)
    report["coins_sample"] = items[:5]
    report["coins_fields"] = {r[0]: r[1] for r in fields}
    report["coins_pagination"] = has_pagination


def step_events_raw(
    client: CoinMarketCalClient, report: dict
) -> None:
    """Шаг 5: Загрузка событий без фильтров."""
    print("\n" + "=" * 50)
    print("📅 GET /events (без фильтров, первая страница)")

    raw = client.get_events(page=1, max_results=50)
    items, path_desc = _extract_list(raw)

    print(f"✅ Ответ получен. Тип: {path_desc}, кол-во: {len(items)}")
    print(f"\n📅 RAW (первые 2 ПОЛНЫХ объекта):")
    print(_raw_json(items[:2] if items else raw))

    fields = _detect_fields(items)
    if fields:
        print(f"\n📅 Структура полей события:")
        print(tabulate(
            fields, headers=["Поле", "Тип", "Пример"],
            tablefmt="simple_outline",
        ))

    report["events_response_type"] = path_desc
    report["events_count"] = len(items)
    report["events_sample"] = items[:5]
    report["events_fields"] = {r[0]: r[1] for r in fields}


def step_events_by_date(
    client: CoinMarketCalClient, report: dict
) -> None:
    """Шаг 6: Загрузка событий с фильтром по дате."""
    print("\n" + "=" * 50)
    today = datetime.now()
    end = today + timedelta(days=7)

    # Формат dd/mm/yyyy
    date_start_dmy = today.strftime("%d/%m/%Y")
    date_end_dmy = end.strftime("%d/%m/%Y")

    # Формат yyyy-mm-dd
    date_start_iso = today.strftime("%Y-%m-%d")
    date_end_iso = end.strftime("%Y-%m-%d")

    date_filter_works = False
    date_format_used = ""

    # Попытка 1: dd/mm/yyyy
    print(f"📅 GET /events?dateRangeStart={date_start_dmy}&dateRangeEnd={date_end_dmy}")
    try:
        raw = client.get_events(
            dateRangeStart=date_start_dmy, dateRangeEnd=date_end_dmy
        )
        items, _ = _extract_list(raw)
        if items:
            date_filter_works = True
            date_format_used = "dd/mm/yyyy"
            print(f"✅ Работает! Формат: dd/mm/yyyy, событий: {len(items)}")
        else:
            print(f"⚠️ Пустой ответ, пробую другой формат...")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}, пробую другой формат...")

    # Попытка 2: yyyy-mm-dd (если первая не сработала)
    if not date_filter_works:
        print(f"\n📅 GET /events?dateRangeStart={date_start_iso}&dateRangeEnd={date_end_iso}")
        try:
            raw = client.get_events(
                dateRangeStart=date_start_iso, dateRangeEnd=date_end_iso
            )
            items, _ = _extract_list(raw)
            if items:
                date_filter_works = True
                date_format_used = "yyyy-mm-dd"
                print(f"✅ Работает! Формат: yyyy-mm-dd, событий: {len(items)}")
            else:
                print(f"❌ Пустой ответ и с этим форматом")
        except Exception as e:
            print(f"❌ Ошибка: {e}")

    if not date_filter_works:
        print("❌ Фильтр по дате не работает ни в каком формате")

    report["filter_date_works"] = date_filter_works
    report["filter_date_format"] = date_format_used


def step_events_by_coin(
    client: CoinMarketCalClient, report: dict
) -> None:
    """Шаг 7: Загрузка событий по монете."""
    print("\n" + "=" * 50)

    coin_filter_works = False
    coin_format_used = ""

    # Попытка 1: coins=bitcoin
    print("📅 GET /events?coins=bitcoin")
    try:
        raw = client.get_events(coins="bitcoin")
        items, _ = _extract_list(raw)
        if items:
            coin_filter_works = True
            coin_format_used = "slug (bitcoin)"
            print(f"✅ Работает! Формат: slug, событий: {len(items)}")
        else:
            print("⚠️ Пустой ответ, пробую другой формат...")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}, пробую другой формат...")

    # Попытка 2: coins=btc
    if not coin_filter_works:
        print("\n📅 GET /events?coins=btc")
        try:
            raw = client.get_events(coins="btc")
            items, _ = _extract_list(raw)
            if items:
                coin_filter_works = True
                coin_format_used = "symbol (btc)"
                print(f"✅ Работает! Формат: symbol, событий: {len(items)}")
            else:
                print("⚠️ Пустой ответ, пробую другой формат...")
        except Exception as e:
            print(f"⚠️ Ошибка: {e}, пробую другой формат...")

    # Попытка 3: coins=1
    if not coin_filter_works:
        print("\n📅 GET /events?coins=1")
        try:
            raw = client.get_events(coins="1")
            items, _ = _extract_list(raw)
            if items:
                coin_filter_works = True
                coin_format_used = "id (1)"
                print(f"✅ Работает! Формат: numeric id, событий: {len(items)}")
            else:
                print("❌ Пустой ответ и с этим форматом")
        except Exception as e:
            print(f"❌ Ошибка: {e}")

    if not coin_filter_works:
        print("❌ Фильтр по монете не работает ни в каком формате")

    report["filter_coin_works"] = coin_filter_works
    report["filter_coin_format"] = coin_format_used


# ---------------------------------------------------------------------------
# Шаг 8: Сводка
# ---------------------------------------------------------------------------

def build_summary(report: dict) -> str:
    """Формирование текстового отчёта."""
    lines: list[str] = []
    date_str = report["date"]

    lines.append("═" * 63)
    lines.append("         COINMARKETCAL EVENTS — API EXPLORATION")
    lines.append(f"         {date_str}")
    lines.append("═" * 63)

    # Подключение
    conn_ok = report.get("connection", False)
    lines.append(f"\n📡 ПОДКЛЮЧЕНИЕ: {'✅ OK' if conn_ok else '❌ FAIL'}")

    if not conn_ok:
        lines.append("\n⛔ Подключение не удалось. Остальные данные недоступны.")
        lines.append("═" * 63)
        return "\n".join(lines)

    # Категории
    lines.append(f"\n📋 КАТЕГОРИИ")
    cat_count = report.get("categories_count", 0)
    lines.append(f"   Всего: {cat_count}")
    cat_sample = report.get("categories_sample", [])
    if cat_sample:
        names = []
        for c in cat_sample[:8]:
            if isinstance(c, dict):
                names.append(c.get("name", c.get("title", str(c))))
            else:
                names.append(str(c))
        lines.append(f"   Примеры: {', '.join(names)}")

    # Монеты
    lines.append(f"\n🪙 МОНЕТЫ")
    lines.append(f"   На первой странице: {report.get('coins_count', 0)}")
    pag = report.get("coins_pagination", False)
    lines.append(f"   Пагинация: {'есть' if pag else 'нет'}")

    # События
    lines.append(f"\n📅 СОБЫТИЯ")
    lines.append(f"   На первой странице: {report.get('events_count', 0)}")
    lines.append(f"   Структура ответа: {report.get('events_response_type', '?')}")

    ev_fields = report.get("events_fields", {})
    if ev_fields:
        lines.append(f"\n   Поля события:")
        field_rows = []
        ev_sample = report.get("events_sample", [{}])
        first_ev = ev_sample[0] if ev_sample else {}
        for key, type_name in ev_fields.items():
            example = _truncate(first_ev.get(key) if isinstance(first_ev, dict) else "", 40)
            field_rows.append([key, type_name, example])
        lines.append(tabulate(
            field_rows, headers=["Поле", "Тип", "Пример"],
            tablefmt="simple_outline",
        ))

    # Фильтры
    date_ok = report.get("filter_date_works", False)
    date_fmt = report.get("filter_date_format", "?")
    coin_ok = report.get("filter_coin_works", False)
    coin_fmt = report.get("filter_coin_format", "?")

    date_str_f = f"✅ работает (формат: {date_fmt})" if date_ok else "❌ не работает"
    coin_str_f = f"✅ работает (формат: {coin_fmt})" if coin_ok else "❌ не работает"

    lines.append(f"\n   С фильтром по дате: {date_str_f}")
    lines.append(f"   С фильтром по монете: {coin_str_f}")

    # Оценка
    lines.append(f"\n💡 ОЦЕНКА")
    has_date = _field_exists(ev_fields, "date", "event_date", "date_event")
    has_coin = _field_exists(ev_fields, "coins", "coin", "coin_id")
    has_category = _field_exists(ev_fields, "categories", "category")
    has_desc = _field_exists(ev_fields, "description", "source", "proof", "body")

    all_ok = has_date and has_coin
    lines.append(
        f"   События пригодны для trading signals: "
        f"{'ДА' if all_ok else 'НЕТ (недостаточно данных)'}"
    )
    lines.append(f"   Есть дата события: {'ДА' if has_date else 'НЕТ'}")
    lines.append(f"   Есть привязка к монете: {'ДА' if has_coin else 'НЕТ'}")
    lines.append(f"   Есть категория: {'ДА' if has_category else 'НЕТ'}")
    lines.append(f"   Есть описание/source: {'ДА' if has_desc else 'НЕТ'}")

    report["suitable_for_trading"] = all_ok

    lines.append("\n" + "═" * 63)
    return "\n".join(lines)


def _field_exists(fields: dict, *candidates: str) -> bool:
    """Проверить есть ли хотя бы одно из имён полей."""
    field_names_lower = {k.lower() for k in fields}
    return any(c.lower() in field_names_lower for c in candidates)


# ---------------------------------------------------------------------------
# Шаг 9: Сохранение
# ---------------------------------------------------------------------------

def save_reports(report: dict, text_report: str) -> None:
    """Сохранение .txt и .json."""
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    date_str = report["date"].replace("-", "")

    txt_path = config.REPORTS_DIR / f"events_explore_{date_str}.txt"
    json_path = config.REPORTS_DIR / f"events_explore_{date_str}.json"

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text_report)

    # JSON — сериализуемая версия
    json_report = {
        "date": report["date"],
        "connection": report.get("connection", False),
        "categories_count": report.get("categories_count", 0),
        "categories_sample": _make_serializable(report.get("categories_sample", [])),
        "coins_count": report.get("coins_count", 0),
        "coins_sample": _make_serializable(report.get("coins_sample", [])),
        "events_count": report.get("events_count", 0),
        "events_sample": _make_serializable(report.get("events_sample", [])),
        "events_fields": report.get("events_fields", {}),
        "filters_work": {
            "date": report.get("filter_date_works", False),
            "date_format": report.get("filter_date_format", ""),
            "coin": report.get("filter_coin_works", False),
            "coin_format": report.get("filter_coin_format", ""),
        },
        "suitable_for_trading": report.get("suitable_for_trading", False),
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n💾 Отчёт сохранён:")
    print(f"   {txt_path}")
    print(f"   {json_path}")


def _make_serializable(data: object) -> object:
    """Преобразовать в JSON-сериализуемый объект."""
    try:
        json.dumps(data)
        return data
    except (TypeError, ValueError):
        return str(data)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    """Точка входа explore_events.py."""
    print("🚀 CoinMarketCal Events Explorer")
    print(f"   Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    report: dict = {"date": datetime.now().strftime("%Y-%m-%d")}

    # Шаг 1
    step_validate()

    # Клиент
    client = CoinMarketCalClient(
        rapidapi_key=config.RAPIDAPI_KEY,
        host=config.COINMARKETCAL_HOST,
        base_url=config.COINMARKETCAL_BASE_URL,
        timeout=config.REQUEST_TIMEOUT,
        delay=config.DEFAULT_DELAY,
    )

    # Шаг 2
    connected = step_check_connection(client)
    report["connection"] = connected
    if not connected:
        text_report = build_summary(report)
        print(text_report)
        save_reports(report, text_report)
        sys.exit(1)

    # Шаг 3: Категории
    try:
        step_categories(client, report)
    except Exception as e:
        print(f"❌ Категории ошибка: {e}")
        report["categories_count"] = 0

    # Шаг 4: Монеты
    try:
        step_coins(client, report)
    except Exception as e:
        print(f"❌ Монеты ошибка: {e}")
        report["coins_count"] = 0

    # Шаг 5: События (raw)
    try:
        step_events_raw(client, report)
    except Exception as e:
        print(f"❌ События ошибка: {e}")
        report["events_count"] = 0

    # Шаг 6: События с фильтром по дате
    try:
        step_events_by_date(client, report)
    except Exception as e:
        print(f"❌ Фильтр по дате ошибка: {e}")
        report["filter_date_works"] = False

    # Шаг 7: События с фильтром по монете
    try:
        step_events_by_coin(client, report)
    except Exception as e:
        print(f"❌ Фильтр по монете ошибка: {e}")
        report["filter_coin_works"] = False

    # Шаг 8: Сводка
    text_report = build_summary(report)
    print(text_report)

    # Шаг 9: Сохранение
    save_reports(report, text_report)

    print("\n✅ Исследование CoinMarketCal завершено!")


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
