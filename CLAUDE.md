# CryptoScanner — Event-Driven Crypto Analysis

## Что делает
Сканер крипто-событий для поиска недооценённых токенов. 6-шаговый пайплайн:
- **Шаг 1**: Parallel Search → AI-парсинг → извлечение событий в events_v2
- **Шаг 2**: Генерация MECE-исходов (шаблон для 7 типов + AI для остальных)
- **Шаг 3**: Оценка вероятностей исходов (multi-temperature, 3 итерации → медиана)
- **Шаг 4**: Оценка ценового влияния (multi-temperature + sign validation)
- **Шаг 5**: Расчёт E[return] = Σ(P × impact) → LONG/SHORT/NEUTRAL сигналы
- **Шаг 6**: Генерация текстового отчёта с полной цепочкой рассуждений

Запуск: `python3 tools/run_pipeline.py` (5 тестовых) или `--full` (50 токенов).

## Источники данных
| API | Статус | Назначение | Ключ |
|-----|--------|-----------|------|
| Parallel Search | **OK** | Веб-поиск событий (основной) | .env PARALLEL_API_KEY |
| AI providers (5) | **OK** | Парсинг, вероятности, импакты | .env (5 ключей) |
| Binance Announce | **OK** | Листинги/делистинги (POST скрапинг) | не нужен |
| CoinGecko | **OK** | Метаданные, цены, категории | .env COINGECKO_API_KEY |
| CoinMarketCap | **OK** | Рыночные данные, маппинг | .env CMC_API_KEY |
| Snapshot | **OK** | DAO governance proposals | не нужен |
| Coindar | **WAIT** | Крипто-события | .env (ожидает верификации) |
| CoinMarketCal | **403** | Нужен платный RapidAPI план | .env RAPIDAPI_KEY |
| CryptoPanic | **404** | Токен не активирован | .env CRYPTOPANIC_TOKEN |
| cryptocurrency.cv | **DEAD** | Таймаут, домен мёртв | не нужен |
| Google News RSS | **DNS** | Заблокирован на сервере | не нужен |

### AI-провайдеры (ротация в groq_client.py)
| Провайдер | Модель | RPM | Качество JSON |
|-----------|--------|-----|---------------|
| groq | llama-3.3-70b-versatile | 30 | высокое |
| cohere | command-a-03-2025 | 20 | высокое |
| cerebras | llama3.1-8b | 30 | низкое (8B) |
| sambanova | Meta-Llama-3.3-70B-Instruct | 30 | высокое |
| github | Meta-Llama-3.3-70B-Instruct | 15 | высокое |

## Структура файлов
```
CryptoScanner/
├── main.py                        <- заглушка (будет Telegram-бот)
├── config.py                      <- ключи, пороги, TOP_EXCLUDE, константы
├── database/db.py                 <- SQLite: sync + async функции, 9 таблиц
├── services/
│   ├── groq_client.py             <- AI-клиент с 5-provider rotation (async)
│   ├── parallel_client.py         <- Parallel Search API клиент
│   ├── token_scanner.py           <- Шаг 1: поиск событий для токена
│   ├── binance_tokens.py          <- Список фьючерсных токенов Binance
│   ├── outcome_generator.py       <- Шаг 2: генерация MECE-исходов
│   ├── outcome_templates.py       <- Шаблоны исходов для 7 типов событий
│   ├── probability_estimator.py   <- Шаг 3: оценка вероятностей (multi-T)
│   ├── impact_estimator.py        <- Шаг 4: оценка импактов + sign validation
│   ├── signal_calculator.py       <- Шаги 5-6: E[return], сигналы, дедупликация
│   ├── event_extractor.py         <- Groq AI: новости → события (sync, legacy)
│   ├── coindar.py                 <- CoindarClient
│   ├── coingecko.py               <- CoinGeckoClient
│   ├── coinmarketcap.py           <- CoinMarketCapClient
│   ├── snapshot.py                <- SnapshotClient (GraphQL)
│   ├── news_binance.py            <- BinanceAnnouncementsClient
│   ├── coinmarketcal_events.py    <- CoinMarketCalClient (403)
│   ├── news_cryptocv.py           <- CryptoCVClient (dead)
│   ├── news_cryptopanic.py        <- CryptoPanicClient (404)
│   └── news_google.py             <- GoogleNewsClient (DNS-блокировка)
├── prompts/
│   ├── extract_token_events.md    <- Промпт для Шага 1 (AI-извлечение событий)
│   ├── generate_outcomes.md       <- Промпт для Шага 2 (AI-генерация исходов)
│   ├── estimate_probabilities.md  <- Промпт для Шага 3 (оценка вероятностей)
│   ├── estimate_impact.md         <- Промпт для Шага 4 (оценка импактов)
│   └── extract_events.md          <- Legacy промпт (sync Шаг 1)
├── tools/
│   ├── run_pipeline.py            <- Полный пайплайн 6 шагов (--full / test)
│   ├── generate_report.py         <- Генератор отчёта с цепочкой рассуждений
│   ├── cleanup_db.py              <- Очистка БД от мусора и TOP_EXCLUDE
│   ├── explore_scanner.py         <- Тест token_scanner (Шаг 1)
│   ├── explore_outcomes.py        <- Тест генерации исходов (Шаг 2)
│   ├── explore_probabilities.py   <- Тест оценки вероятностей (Шаг 3)
│   ├── explore_impacts.py         <- Тест оценки импактов (Шаг 4)
│   ├── explore_signals.py         <- Тест расчёта сигналов (Шаги 5-6)
│   ├── explore.py                 <- Multi-API explorer (CoinGecko, CMC, Snapshot)
│   ├── explore_events.py          <- CoinMarketCal explorer (403)
│   ├── explore_news.py            <- News sources + AI explorer (legacy)
│   └── test_pipeline.py           <- Тест связки Шаг 1 → Шаг 2 (legacy)
└── reports/                       <- signal_report_YYYY-MM-DD.txt, api_research.txt
```

## Запуск
```bash
pip install -r requirements.txt
python3 tools/run_pipeline.py          # Test mode: 5 токенов
python3 tools/run_pipeline.py --full   # Full mode: 50 токенов (~13 мин)
python3 tools/generate_report.py       # Генерация отчёта из БД
python3 tools/cleanup_db.py            # Очистка мусора из БД (интерактивная)
```

## Таблицы БД (scanner.db)
| Таблица | Поток | Назначение |
|---------|-------|-----------|
| events_v2 | Шаги 1-6 (async) | События: TEXT id (MD5), title, outcomes_generated |
| event_outcomes | Шаги 2-6 (async) | MECE-исходы: probability, price_impact_pct, low/high |
| events | Legacy (sync) | События: INTEGER id, caption, date_start |
| raw_news | Legacy (sync) | Сырые новости из всех источников |
| tags | Coindar → explore.py | Категории событий |
| coins_coindar | Coindar | Монеты (id, symbol) |
| coins_coingecko | CoinGecko | Монеты (slug id, symbol) |
| coins_cmc | CMC | Монеты (cmc_id, symbol) |
| proposals | Snapshot | DAO governance proposals |

## Critical Rules
1. **Две таблицы событий**: `events` (legacy, sync, INTEGER id) и `events_v2` (основная, async, TEXT MD5 id) — разные схемы, не смешивать
2. **sys.path.insert(0, ...)**: обязателен в каждом tools/*.py для импортов из корня проекта
3. **Промпты в prompts/*.md**: подстановка через `.replace()` — НЕ `.format()`, НЕ f-string (фигурные скобки в JSON)
4. **AI-парсинг JSON**: json.loads() → regex `\[.*\]` → regex `\{.*\}` → fallback (3 уровня)
5. **call_groq() — единая точка входа для AI**: сигнатура `call_groq(prompt, model, temperature, max_tokens, timeout) → str`. Все 5 провайдеров под капотом, вызывающий код не знает о ротации
6. **Sign validation обязательна**: `_validate_sign_logic()` в impact_estimator.py проверяет что не все импакты одного знака. Без неё AI может выдать all-negative для unlock events
7. **TOP_EXCLUDE**: BTC, ETH, BNB, SOL, XRP, ADA, DOGE, TRX, TON, AVAX — исключаются из сканирования и из БД (cleanup_db.py)

## Lessons Learned
- **AI-провайдер ротация решает rate limits**: с 1 провайдером (Groq, 30 rpm) — 96 ошибок 429, 29 failed токенов. С 5 провайдерами — 11 ошибок 429, 0 failed, ~110 rpm суммарная ёмкость.
- **Cerebras 8B модель ненадёжна для JSON**: Возвращает 200 OK, но structured output (impact estimation JSON) часто невалидный. Пригоден только для простых текстовых задач. Groq/Cohere/SambaNova (70B модели) надёжны.
- **AI считает price predictions за события**: "1000CAT Price Prediction 2026-2030" → listing. Фикс: явный junk-фильтр в промпте extract_token_events.md + cleanup_db.py для очистки.
- **AI генерирует все отрицательные импакты для unlock**: "tokens held" = -4.5% (должно быть +). Фикс: калибровка unlock в промпте estimate_impact.md + `_validate_sign_logic()` как страховка.
- **Бесплатных unlock API нет**: Tokenomist=$249/мес, DefiLlama emissions=платный, CryptoRank/CoinMarketCal=платные. Лучшая стратегия: Parallel Search + AI-парсинг веб-страниц. CoinPaprika — единственный бесплатный events API (только BTC/ETH).
- **Binance Announcements — основной рабочий источник**: POST к `/bapi/composite/v1/public/cms/article/list/query`. catalogId: 48=листинги, 131=делистинги.
- **CoinGecko ID = slug** ("bitcoin"), не символ ("BTC") — для топ-монет хардкод `COINGECKO_ID_MAP` в config.py.
