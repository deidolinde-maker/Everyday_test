PROVIDER = "mts"
DEFAULT_CITY = "Москва"

SITES = [
    {
        "base_url": "https://mts-home-gpon.ru/",
        "has_checkaddress": True,
        "has_business": True,
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
        "cities": ["Москва"],
    },
]

