"""CryptoScanner — точка входа (заглушка для Phase 2: Telegram-бот)."""

import sys
sys.modules["main"] = sys.modules[__name__]


def main() -> None:
    """Заглушка — будет Telegram-бот в Phase 2."""
    print("CryptoScanner v1.0")
    print("Для исследования API запустите: python3 tools/explore.py")
    print("Phase 2: здесь будет Telegram-бот.")


if __name__ == "__main__":
    main()
