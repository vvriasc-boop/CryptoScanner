"""CryptoScanner — конфигурация проекта."""

import os
import pathlib

from dotenv import load_dotenv

load_dotenv()

# API Keys
COINDAR_TOKEN: str = os.getenv("COINDAR_ACCESS_TOKEN", "")
COINGECKO_KEY: str = os.getenv("COINGECKO_API_KEY", "")
CMC_KEY: str = os.getenv("CMC_API_KEY", "")
RAPIDAPI_KEY: str = os.getenv("RAPIDAPI_KEY", "")
CRYPTOPANIC_TOKEN: str = os.getenv("CRYPTOPANIC_TOKEN", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# Base URLs
COINDAR_BASE_URL: str = "https://coindar.org/api/v2"
COINGECKO_BASE_URL: str = "https://api.coingecko.com/api/v3"
CMC_BASE_URL: str = "https://pro-api.coinmarketcap.com"
SNAPSHOT_BASE_URL: str = "https://hub.snapshot.org/graphql"
COINMARKETCAL_HOST: str = "coinmarketcal.p.rapidapi.com"
COINMARKETCAL_BASE_URL: str = "https://coinmarketcal.p.rapidapi.com"
CRYPTOCV_NEWS_URL: str = "https://cryptocurrency.cv/api/news"
CRYPTOPANIC_BASE_URL: str = "https://cryptopanic.com/api/v1"
BINANCE_ANNOUNCE_URL: str = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
GROQ_API_URL: str = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL: str = "llama-3.3-70b-versatile"
GOOGLE_NEWS_RSS_BASE: str = "https://news.google.com/rss/search"

# Paths
BASE_DIR: pathlib.Path = pathlib.Path(__file__).parent
DB_PATH: pathlib.Path = BASE_DIR / "scanner.db"
REPORTS_DIR: pathlib.Path = BASE_DIR / "reports"

# HTTP
REQUEST_TIMEOUT: int = 15
USER_AGENT: str = "CryptoScanner/1.0"
DEFAULT_DELAY: float = 1.0  # секунд между запросами

# Rate limits для новых источников
CRYPTOCV_DELAY: float = 2.0       # без ключа, не злоупотреблять
CRYPTOPANIC_DELAY: float = 2.0    # free tier
BINANCE_DELAY: float = 2.0        # scraping, осторожно
GROQ_DELAY: float = 1.0           # ~30 req/min на free
GOOGLE_NEWS_DELAY: float = 2.0    # RSS, не злоупотреблять

# Binance-listed символы для фильтрации
# Phase 2: автозагрузка через Binance GET /api/v3/exchangeInfo
BINANCE_SYMBOLS: set[str] = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT",
    "MATIC", "UNI", "ATOM", "LTC", "FIL", "APT", "ARB", "OP", "NEAR", "SUI",
    "INJ", "TIA", "SEI", "RNDR", "FET", "AAVE", "MKR", "SNX", "CRV", "LDO",
    "RUNE", "STX", "IMX", "SAND", "MANA", "AXS", "GALA", "ENS", "COMP", "SUSHI",
    "PEPE", "WIF", "BONK", "FLOKI", "SHIB", "WLD", "JTO", "JUP", "PYTH", "W",
    "PENDLE", "ENA", "ETHFI", "STRK", "ZRO", "EIGEN", "BOME", "MEW", "POPCAT",
    "TAO", "FTM", "ALGO", "HBAR", "ICP", "VET", "TRX", "TON", "THETA", "GRT",
    "ONE", "FLOW", "EGLD", "QNT", "XTZ", "IOTA", "NEO", "ZIL", "KAVA", "CELO",
    "ROSE", "ZEC", "DASH", "EOS", "XLM", "BCH", "ETC", "DYDX", "GMX", "1INCH",
    "BAL", "YFI", "RPL", "SSV", "BLUR", "MAGIC", "AGI", "OCEAN", "ONDO", "TRB",
}

# Google News RSS — поисковые запросы
GOOGLE_NEWS_QUERIES: list[str] = [
    "crypto listing Binance",
    "crypto delisting exchange",
    "token burn crypto",
    "crypto airdrop announcement",
    "blockchain partnership",
    "crypto mainnet launch",
    "token unlock schedule",
    "crypto exchange new coin",
]
MAX_GOOGLE_NEWS_TOTAL: int = 100

# Хардкод маппинга symbol → CoinGecko slug ID для топ-монет
# (symbol неоднозначен: много мем-коинов с тем же тикером)
COINGECKO_ID_MAP: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "LTC": "litecoin",
    "TON": "the-open-network",
    "SHIB": "shiba-inu",
    "TRX": "tron",
    "ARB": "arbitrum",
    "OP": "optimism",
    "NEAR": "near",
    "SUI": "sui",
    "APT": "aptos",
    "PEPE": "pepe",
    "FIL": "filecoin",
    "AAVE": "aave",
    "RNDR": "render-token",
    "FET": "fetch-ai",
    "INJ": "injective-protocol",
    "IMX": "immutable-x",
    "STX": "blockstack",
}

# Топ DAO для тестирования Snapshot
SNAPSHOT_SPACES: list[str] = [
    "uniswap", "aave.eth", "ens.eth", "gitcoindao.eth",
    "arbitrumfoundation.eth", "opcollective.eth", "lido-snapshot.eth",
    "safe.eth", "stgdao.eth", "balancer.eth",
]

# Outcome Generator (Step 2)
GROQ_OUTCOME_MODEL: str = "llama-3.3-70b-versatile"
GROQ_OUTCOME_TEMPERATURE: float = 0.1
GROQ_OUTCOME_MAX_TOKENS: int = 500
MAX_AI_OUTCOMES_PER_RUN: int = 20

# === Step 1 v2: Token Scanner ===
PARALLEL_API_KEY: str = os.getenv("PARALLEL_API_KEY") or ""
PARALLEL_MAX_RESULTS: int = 5
PARALLEL_MAX_CHARS: int = 2000
PARALLEL_DELAY: float = 0.2  # секунд между запросами

TOP_EXCLUDE: set[str] = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "TON", "AVAX",
}
SCAN_HORIZON_DAYS: int = 7
MAX_GROQ_CALLS_PER_SCAN: int = 100

# === Step 3: Probability Estimator ===
GROQ_SCANNER_MODEL: str = "llama-3.3-70b-versatile"

# === Steps 5-6: Signal Calculator ===
SIGNAL_THRESHOLD: float = 3.0  # минимальный |E[return]| для сигнала (в %)
MAX_TOKEN_E_RETURN: float = 15.0  # максимальный |E[return]| на токен (%)

if not PARALLEL_API_KEY:
    import logging as _logging
    _logging.warning("PARALLEL_API_KEY not set — token scanner disabled")
