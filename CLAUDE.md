# CryptoScanner — Event-Driven Crypto Analysis

## Что делает
Сканер крипто-событий для поиска недооценённых токенов.
- **Шаг 1**: Сбор новостей из API → AI-парсинг → извлечение событий
- **Шаг 2**: Генерация MECE-исходов (шаблон для 7 типов + Groq AI для остальных)
- Шаг 3 (planned): Оценка вероятностей исходов

## Источники данных
| API | Статус | Назначение | Ключ |
|-----|--------|-----------|------|
| Binance Announce | **OK** | Листинги/делистинги (POST скрапинг) | не нужен |
| Groq AI | **OK** | Парсинг новостей → события + генерация исходов | .env GROQ_API_KEY |
| CoinGecko | **OK** | Метаданные, цены, категории | .env |
| CoinMarketCap | **OK** | Рыночные данные, маппинг | .env |
| Snapshot | **OK** | DAO governance proposals | не нужен |
| Coindar | **WAIT** | Крипто-события | .env (ожидает верификации) |
| CoinMarketCal | **403** | Нужен платный RapidAPI план |  .env RAPIDAPI_KEY |
| CryptoPanic | **404** | Токен не активирован или API отключён | .env CRYPTOPANIC_TOKEN |
| cryptocurrency.cv | **DEAD** | Таймаут, домен мёртв | не нужен |
| Google News RSS | **DNS** | Заблокирован на сервере (224.0.0.x) | не нужен |

## Структура файлов
```
CryptoScanner/
├── main.py                    <- заглушка (будет Telegram-бот)
├── config.py                  <- ключи, URL, BINANCE_SYMBOLS, OUTCOME_* константы
├── database/db.py             <- SQLite: 9 таблиц (sync + async функции)
├── services/
│   ├── coindar.py             <- CoindarClient
│   ├── coingecko.py           <- CoinGeckoClient
│   ├── coinmarketcap.py       <- CoinMarketCapClient
│   ├── coinmarketcal_events.py <- CoinMarketCalClient (RapidAPI, 403)
│   ├── news_cryptocv.py       <- CryptoCVClient (dead)
│   ├── news_cryptopanic.py    <- CryptoPanicClient (404)
│   ├── news_binance.py        <- BinanceAnnouncementsClient (OK)
│   ├── news_google.py         <- GoogleNewsClient (DNS-блокировка)
│   ├── event_extractor.py     <- Groq AI: новости → события (sync, requests)
│   ├── groq_client.py         <- Общий async-клиент Groq API (httpx)
│   ├── outcome_templates.py   <- Шаблоны исходов для 7 типов событий
│   ├── outcome_generator.py   <- generate_outcomes(): шаблон + AI + fallback
│   └── snapshot.py            <- SnapshotClient (GraphQL)
├── prompts/
│   ├── extract_events.md      <- Промпт для AI-извлечения событий
│   └── generate_outcomes.md   <- Промпт для AI-генерации исходов
├── tools/
│   ├── explore.py             <- Multi-API explorer (CoinGecko, CMC, Snapshot)
│   ├── explore_events.py      <- CoinMarketCal explorer (403)
│   ├── explore_news.py        <- News sources + AI explorer (Шаг 1)
│   ├── explore_outcomes.py    <- Тест генерации исходов (Шаг 2)
│   └── test_pipeline.py       <- Тест полного пайплайна Шаг 1 → Шаг 2
└── reports/                   <- .txt + .json отчёты
```

## Запуск
```bash
pip install -r requirements.txt
python3 tools/explore.py           # Multi-API explorer
python3 tools/explore_news.py      # Шаг 1: сбор новостей + AI-парсинг
python3 tools/explore_outcomes.py  # Шаг 2: генерация исходов (тестовые данные)
python3 tools/test_pipeline.py     # Тест связки Шаг 1 → Шаг 2
```

## Таблицы БД (scanner.db)
| Таблица | Поток | Назначение |
|---------|-------|-----------|
| tags | Coindar → explore.py | Категории событий |
| coins_coindar | Coindar | Монеты (id, symbol) |
| coins_coingecko | CoinGecko | Монеты (slug id, symbol) |
| coins_cmc | CMC | Монеты (cmc_id, symbol) |
| events | Шаг 1 (sync) | События: INTEGER id, caption, date_start |
| raw_news | Шаг 1 (sync) | Сырые новости из всех источников |
| events_v2 | Шаг 2 (async) | События: TEXT id (MD5), title, outcomes_generated |
| event_outcomes | Шаг 2 (async) | 3-4 MECE-исхода на событие |
| proposals | Snapshot | DAO governance proposals |

## Critical Rules
1. **Две таблицы событий**: `events` (Шаг 1, sync, INTEGER id) и `events_v2` (Шаг 2, async, TEXT MD5 id) — разные схемы, не смешивать
2. **sys.path.insert(0, ...)**: обязателен в каждом tools/*.py для импортов из корня проекта
3. **Промпты в prompts/*.md**: подстановка через `.replace()` — НЕ `.format()`, НЕ f-string (фигурные скобки в JSON)
4. **AI-парсинг JSON**: json.loads() → regex `\[.*\]` → regex `\{.*\}` → fallback (3 уровня)
5. **Rate limits**: CoinGecko 2с, CMC 2с, Binance 2с, Groq 1с, Google News 2с; при 429 → sleep + retry
6. **Каждый API в отдельном try/except**: падение одного не ломает остальные
7. **CoinGecko ID = slug** ("bitcoin"), не символ ("BTC") — для топ-монет использовать хардкод `COINGECKO_ID_MAP`

## Lessons Learned
- **Нерабочие источники** (проверено многократно, напрямую + через прокси): CoinMarketCal → 403 (нужен платный RapidAPI), CryptoPanic → 404 HTML, cryptocurrency.cv → timeout (мёртв), Google News RSS → DNS-блокировка на сервере (224.0.0.x). Не рассчитывать как источники, периодически перепроверять.
- **Binance Announcements — основной рабочий источник**: POST к `/bapi/composite/v1/public/cms/article/list/query`. catalogId: 48=листинги, 131=делистинги. Поля: id, code, title, type, releaseDate (ms).
- **Groq AI-парсинг работает**: llama-3.3-70b-versatile, чанки по 30 новостей, temperature=0.1. Конверсия ~55%. Для исходов: 7 типов по шаблону (мгновенно), остальные через AI с 3 попытками + generic fallback.
- **SQLite: выражения в UNIQUE constraint запрещены**: `UNIQUE(col1, COALESCE(col2, -1))` → `OperationalError`. Решение: `CREATE UNIQUE INDEX`.
- **CoinGecko symbol→id неоднозначен**: один symbol может быть у десятков мем-коинов. Хардкод `COINGECKO_ID_MAP` в config.py обязателен для топ-монет.
- **Sync + Async сосуществуют**: Шаг 1 (requests + sqlite3), Шаг 2 (httpx + aiosqlite). Для db.py — sync функции используют внутренний _connect(), async функции принимают db параметр.
- **events_v2 отдельная таблица**: создана вместо модификации events, чтобы не ломать Шаг 1. TEXT id (MD5 hash от coin_symbol+event_type+title). Будущая миграция объединит.

### Шаг 2: Генерация исходов (Outcome Generation)
- services/groq_client.py — async-клиент Groq API с retry (429→10s, 5xx→5/15/45s)
- services/outcome_templates.py — OUTCOME_TEMPLATES (7 типов) + GENERIC_OUTCOMES
- services/outcome_generator.py — generate_outcomes(): шаблон → AI → generic fallback
- prompts/generate_outcomes.md — промпт для AI-генерации нестандартных типов
- validate_outcomes(): 3-4 исхода, уникальные ключи, category ∈ {positive, neutral, negative, cancelled}, 1+ positive, 1+ negative/cancelled
- Тест: python3 tools/explore_outcomes.py (5 событий: 4 шаблон + 1 AI, 0 ошибок)
- Pipeline: python3 tools/test_pipeline.py (20 статей → 4 события → 3 исхода, 0 ошибок)
