"""Шаблоны исходов для 7 стандартных типов событий."""

OUTCOME_TEMPLATES = {
    "listing": {
        "question": "Как пройдёт листинг {coin} на бирже?",
        "outcomes": [
            {"key": "A", "text": "Листинг в срок + высокий объём торгов (первые 24ч)", "category": "positive"},
            {"key": "B", "text": "Листинг в срок + низкий объём (слабый интерес)", "category": "neutral"},
            {"key": "C", "text": "Листинг отложен или перенесён на другую дату", "category": "negative"},
            {"key": "D", "text": "Листинг отменён полностью", "category": "cancelled"},
        ],
    },
    "launch": {
        "question": "Как пройдёт запуск {title}?",
        "outcomes": [
            {"key": "A", "text": "Запуск в срок + сильный спрос", "category": "positive"},
            {"key": "B", "text": "Запуск в срок + умеренный интерес", "category": "neutral"},
            {"key": "C", "text": "Запуск отложен", "category": "negative"},
            {"key": "D", "text": "Запуск отменён или продукт убран", "category": "cancelled"},
        ],
    },
    "burn": {
        "question": "Каким будет результат сжигания токенов {coin}?",
        "outcomes": [
            {"key": "A", "text": "Сожжено больше ожиданий (>120% от прогноза)", "category": "positive"},
            {"key": "B", "text": "Сожжено в рамках ожиданий (80-120%)", "category": "neutral"},
            {"key": "C", "text": "Сожжено меньше ожиданий (<80%)", "category": "negative"},
            {"key": "D", "text": "Сжигание отложено или не состоялось", "category": "cancelled"},
        ],
    },
    "unlock": {
        "question": "Что произойдёт после разблокировки токенов {coin}?",
        "outcomes": [
            {"key": "A", "text": "Токены удерживаются (не продаются 48ч после unlock)", "category": "positive"},
            {"key": "B", "text": "Частичная продажа (<50% разблокированного)", "category": "neutral"},
            {"key": "C", "text": "Массовая продажа (>50% разблокированного)", "category": "negative"},
            {"key": "D", "text": "Разблокировка перенесена или отменена", "category": "cancelled"},
        ],
    },
    "fork": {
        "question": "Как пройдёт обновление сети {coin}?",
        "outcomes": [
            {"key": "A", "text": "Успешное обновление без проблем", "category": "positive"},
            {"key": "B", "text": "Обновление с минорными багами (исправлены за 24ч)", "category": "neutral"},
            {"key": "C", "text": "Серьёзные проблемы, откат или экстренный патч", "category": "negative"},
            {"key": "D", "text": "Обновление отложено", "category": "cancelled"},
        ],
    },
    "partnership": {
        "question": "Какой масштаб партнёрства для {coin}?",
        "outcomes": [
            {"key": "A", "text": "Стратегическое партнёрство с реальной интеграцией", "category": "positive"},
            {"key": "B", "text": "Техническое сотрудничество ограниченного масштаба", "category": "neutral"},
            {"key": "C", "text": "Только MoU или письмо о намерениях (без обязательств)", "category": "negative"},
            {"key": "D", "text": "Партнёрство не подтверждено или оказалось слухом", "category": "cancelled"},
        ],
    },
    "airdrop": {
        "question": "Каким будет результат аирдропа {coin}?",
        "outcomes": [
            {"key": "A", "text": "Аирдроп состоялся, большинство удерживают (>50%)", "category": "positive"},
            {"key": "B", "text": "Аирдроп состоялся, массовая продажа (>70% продают)", "category": "negative"},
            {"key": "C", "text": "Аирдроп уменьшен или условия изменены", "category": "negative"},
            {"key": "D", "text": "Аирдроп отложен или отменён", "category": "cancelled"},
        ],
    },
}

GENERIC_OUTCOMES = {
    "question": "Каким будет результат события для {coin}?",
    "outcomes": [
        {"key": "A", "text": "Событие прошло с положительным результатом", "category": "positive"},
        {"key": "B", "text": "Событие прошло с нейтральным результатом", "category": "neutral"},
        {"key": "C", "text": "Событие прошло с негативным результатом", "category": "negative"},
        {"key": "D", "text": "Событие отменено или перенесено", "category": "cancelled"},
    ],
}
