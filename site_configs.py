"""
Compatibility layer for legacy imports.

Primary source of truth is now provider configs under `config/providers/`.
This module keeps `SITE_CONFIGS` available in the old shape so legacy scripts
can continue working during PB3 rollout.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

# Защита от конфликта имен пакетов:
# mobile_tariffs_tests/config может быть импортирован как `config` раньше,
# поэтому гарантируем, что дальше загрузится корневой `config`.
existing_config = sys.modules.get("config")
if existing_config is not None:
    existing_file = getattr(existing_config, "__file__", "") or ""
    if existing_file:
        existing_path = Path(existing_file).resolve()
        expected_config_dir = (_ROOT_DIR / "config").resolve()
        if not str(existing_path).startswith(str(expected_config_dir)):
            del sys.modules["config"]

from config.loader import available_providers, load_site_configs, select_site_configs


SITE_CONFIGS = load_site_configs()

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

__all__ = [
    "SITE_CONFIGS",
    "available_providers",
    "load_site_configs",
    "select_site_configs",
    "validate_site_configs",
]
