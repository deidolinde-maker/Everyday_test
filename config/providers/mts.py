PROVIDER = "mts"
DEFAULT_CITY = "Москва"

SITES = [
    {
        "base_url": "https://mts-home-gpon.ru/",
        "has_checkaddress": True,
        # Временно исключаем бизнес-страницу из прогона: форма недоступна
        # для стабильной проверки до отдельного исправления лендинга.
        "has_business": False,
        "cities": ["Москва"],
    },
    {
        "base_url": "https://mts-home.online/",
        "has_checkaddress": False,
        "has_business": True,
        "cities": ["Москва"],
    },
    {
        "base_url": "https://mts-home-online.ru/",
        "has_checkaddress": False,
        "has_business": True,
        "has_name_field": True,
        "auto_profit_optional": True,
        "cities": ["Москва"],
    },
    {
        "base_url": "https://internet-mts-home.online/",
        "has_checkaddress": False,
        "has_business": False,
        "cities": ["Москва"],
    },
    {
        "base_url": "https://mts-internet.online/",
        "has_checkaddress": False,
        "has_business": False,
        "site_time_budget_ms": 600000,
        "cities": ["Москва"],
    },
]
