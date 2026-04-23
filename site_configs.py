"""
Конфигурация лендингов для test_universal2.py.

ИНСТРУКЦИЯ ПО РЕДАКТИРОВАНИЮ
1. Добавление нового сайта:
   - добавьте новый ключ верхнего уровня в SITE_CONFIGS (обычно домен, например "example.ru");
   - заполните обязательные поля:
       * base_url (str, полный URL с http/https),
       * has_checkaddress (bool),
       * has_business (bool),
       * city_name (str | None).
2. Не переименовывайте существующие ключи сайта без необходимости:
   - параметр CLI --site использует именно ключ словаря (site_id).
3. Дополнительные флаги:
   - has_name_field (bool),
   - has_region_popup (bool).
4. Допускаются и другие специфичные поля (для будущих задач), но
   обязательные поля и их типы должны оставаться валидными.
5. Перед пушем:
   - проверьте точечно: pytest -s --site=<site_id> --service-mode=core
"""

from __future__ import annotations


SITE_CONFIGS = {
    "mts-home-gpon.ru": {
        "base_url": "https://mts-home-gpon.ru/",
        "has_checkaddress": True,
        "has_business": True,
        "city_name": "Москва",
    },
    "mts-home.online": {
        "base_url": "https://mts-home.online/",
        "has_checkaddress": False,
        "has_business": True,
        "city_name": "Москва",
    },
    "mts-home-online.ru": {
        "base_url": "https://mts-home-online.ru/",
        "has_checkaddress": False,
        "has_business": True,
        "city_name": "Москва",
        "has_name_field": True,
    },
    "internet-mts-home.online": {
        "base_url": "https://internet-mts-home.online/",
        "has_checkaddress": False,
        "has_business": False,
        "city_name": "Москва",
    },
    "mts-internet.online": {
        "base_url": "https://mts-internet.online/",
        "has_checkaddress": False,
        "has_business": False,
        "city_name": "Москва",
    },
    "beeline-internet.online": {
        "base_url": "https://beeline-internet.online/",
        "has_checkaddress": False,
        "has_business": True,
        "city_name": "Москва",
        "has_region_popup": True,
    },
    "beeline-ru.online": {
        "base_url": "https://beeline-ru.online/",
        "has_checkaddress": False,
        "has_business": True,
        "city_name": "Москва",
        "has_region_popup": True,
    },
    "online-beeline.ru": {
        "base_url": "https://online-beeline.ru/",
        "has_checkaddress": False,
        "has_business": True,
        "city_name": "Москва",
        "has_region_popup": True,
    },
    "beeline-ru.pro": {
        "base_url": "https://beeline-ru.pro/",
        "has_checkaddress": False,
        "has_business": False,
        "city_name": "Москва",
        "has_region_popup": True,
    },
    "beeline-home.online": {
        "base_url": "https://beeline-home.online/",
        "has_checkaddress": False,
        "has_business": False,
        "city_name": "Москва",
        "has_region_popup": True,
    },
    "beelline-internet.ru": {
        "base_url": "https://beelline-internet.ru/",
        "has_checkaddress": False,
        "has_business": False,
        "city_name": "Москва",
        "has_region_popup": True,
    },
    "rtk-ru.online": {
        "base_url": "https://rtk-ru.online/",
        "has_checkaddress": True,
        "has_business": True,
        "city_name": "Москва",
        "has_name_field": True,
    },
    "rt-internet.online": {
        "base_url": "https://rt-internet.online/",
        "has_checkaddress": True,
        "has_business": False,
        "city_name": "Москва",
        "has_name_field": True,
    },
    "rtk-home-internet.ru": {
        "base_url": "https://rtk-home-internet.ru/",
        "has_checkaddress": True,
        "has_business": False,
        "city_name": "Москва",
        "has_name_field": True,
    },
    "rtk-internet.online": {
        "base_url": "https://rtk-internet.online/",
        "has_checkaddress": True,
        "has_business": True,
        "city_name": "Москва",
        "has_name_field": True,
    },
    "rtk-home.ru": {
        "base_url": "http://rtk-home.ru/",
        "has_checkaddress": True,
        "has_business": True,
        "city_name": "Москва",
        "has_name_field": True,
    },
    "dom-provider.online": {
        "base_url": "https://dom-provider.online/",
        "has_checkaddress": False,
        "has_business": False,
        "city_name": "Москва",
        "has_name_field": True,
    },
    "providerdom.ru": {
        "base_url": "https://providerdom.ru/",
        "has_checkaddress": False,
        "has_business": False,
        "city_name": "Москва",
        "has_name_field": True,
    },
    "mega-premium.ru": {
        "base_url": "https://mega-premium.ru/",
        "has_checkaddress": True,
        "has_business": False,
        "city_name": "Москва",
        "has_name_field": True,
    },
    "mega-home-internet.ru": {
        "base_url": "https://mega-home-internet.ru/",
        "has_checkaddress": True,
        "has_business": False,
        "city_name": "Москва",
        "has_name_field": True,
    },
    "t2-ru.online": {
        "base_url": "https://t2-ru.online",
        "has_checkaddress": False,
        "has_business": False,
        "city_name": "Москва",
        "has_name_field": True,
    },
    "ttk-internet.ru": {
        "base_url": "https://ttk-internet.ru/",
        "has_checkaddress": False,
        "has_business": False,
        "city_name": None,  # нет Москвы в списке городов
    },
    "ttk-ru.online": {
        "base_url": "https://ttk-ru.online/",
        "has_checkaddress": False,
        "has_business": False,
        "city_name": None,  # нет Москвы в списке городов
    },
    # "stage-project.ru": {
    #     "base_url": "https://stage-project.ru/",
    #     "has_checkaddress": True,
    #     "has_business": True,
    #     "city_name": "Москва",
    #     "has_name_field": True,
    # },
}


_REQUIRED_KEYS = ("base_url", "has_checkaddress", "has_business", "city_name")
_BOOL_KEYS = ("has_checkaddress", "has_business", "has_name_field", "has_region_popup")


def validate_site_configs(site_configs: dict[str, dict]) -> None:
    errors: list[str] = []

    if not isinstance(site_configs, dict) or not site_configs:
        raise ValueError("SITE_CONFIGS must be a non-empty dict")

    for site_id, cfg in site_configs.items():
        if not isinstance(site_id, str) or not site_id.strip():
            errors.append(f"invalid site_id: {site_id!r}")
            continue
        if not isinstance(cfg, dict):
            errors.append(f"{site_id}: config must be dict")
            continue

        missing = [k for k in _REQUIRED_KEYS if k not in cfg]
        if missing:
            errors.append(f"{site_id}: missing required keys: {', '.join(missing)}")
            continue

        base_url = cfg.get("base_url")
        if not isinstance(base_url, str) or not base_url.strip():
            errors.append(f"{site_id}: base_url must be non-empty string")
        elif not base_url.startswith(("http://", "https://")):
            errors.append(f"{site_id}: base_url must start with http:// or https://")

        city_name = cfg.get("city_name")
        if city_name is not None and not isinstance(city_name, str):
            errors.append(f"{site_id}: city_name must be string or None")

        for key in _BOOL_KEYS:
            if key in cfg and not isinstance(cfg.get(key), bool):
                errors.append(f"{site_id}: {key} must be bool")

    if errors:
        raise ValueError("Invalid SITE_CONFIGS:\n- " + "\n- ".join(errors))


validate_site_configs(SITE_CONFIGS)

