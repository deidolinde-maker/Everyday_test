from __future__ import annotations

from types import ModuleType
from urllib.parse import urlsplit


REQUIRED_SITE_KEYS = ("base_url", "has_checkaddress", "has_business")
BOOL_SITE_KEYS = ("has_checkaddress", "has_business", "has_name_field", "has_region_popup")


def derive_site_id(base_url: str) -> str:
    parsed = urlsplit(base_url)
    host = (parsed.netloc or parsed.path or "").strip().lower()
    if "/" in host:
        host = host.split("/", 1)[0]
    return host


def _validate_single_provider(
    *,
    provider_key: str,
    module: ModuleType,
    seen_site_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    provider_name = getattr(module, "PROVIDER", None)
    default_city = getattr(module, "DEFAULT_CITY", None)
    sites = getattr(module, "SITES", None)

    if provider_name != provider_key:
        errors.append(
            f"provider '{provider_key}': module.PROVIDER must match key (got {provider_name!r})"
        )
    if not isinstance(default_city, str) or not default_city.strip():
        errors.append(f"provider '{provider_key}': DEFAULT_CITY must be non-empty string")
    if not isinstance(sites, list) or not sites:
        errors.append(f"provider '{provider_key}': SITES must be non-empty list")
        return errors

    for idx, site in enumerate(sites):
        site_label = f"provider '{provider_key}', site[{idx}]"
        if not isinstance(site, dict):
            errors.append(f"{site_label}: must be dict")
            continue

        missing = [k for k in REQUIRED_SITE_KEYS if k not in site]
        if missing:
            errors.append(f"{site_label}: missing required keys: {', '.join(missing)}")
            continue

        base_url = site.get("base_url")
        if not isinstance(base_url, str) or not base_url.strip():
            errors.append(f"{site_label}: base_url must be non-empty string")
            continue
        if not base_url.startswith(("http://", "https://")):
            errors.append(f"{site_label}: base_url must start with http:// or https://")
            continue

        site_id = site.get("site_id") or derive_site_id(base_url)
        if not site_id:
            errors.append(f"{site_label}: cannot derive site_id from base_url={base_url!r}")
            continue
        if site_id in seen_site_ids:
            errors.append(f"{site_label}: duplicate site_id across providers: {site_id!r}")
        else:
            seen_site_ids.add(site_id)

        for key in BOOL_SITE_KEYS:
            if key in site and not isinstance(site.get(key), bool):
                errors.append(f"{site_label}: {key} must be bool")

        city_name = site.get("city_name", "__missing__")
        if city_name != "__missing__" and city_name is not None and not isinstance(city_name, str):
            errors.append(f"{site_label}: city_name must be string or None")

        cities = site.get("cities", "__missing__")
        if cities != "__missing__":
            if not isinstance(cities, list):
                errors.append(f"{site_label}: cities must be list[str]")
            else:
                for city_idx, city in enumerate(cities):
                    if not isinstance(city, str):
                        errors.append(f"{site_label}: cities[{city_idx}] must be string")
                    elif city and not city.strip():
                        errors.append(f"{site_label}: cities[{city_idx}] must not be blank string")

    return errors


def validate_provider_modules(provider_modules: dict[str, ModuleType]) -> None:
    errors: list[str] = []
    seen_site_ids: set[str] = set()

    if not isinstance(provider_modules, dict) or not provider_modules:
        raise ValueError("provider_modules must be a non-empty dict")

    for provider_key, module in provider_modules.items():
        if not isinstance(provider_key, str) or not provider_key.strip():
            errors.append(f"invalid provider key: {provider_key!r}")
            continue
        errors.extend(
            _validate_single_provider(
                provider_key=provider_key,
                module=module,
                seen_site_ids=seen_site_ids,
            )
        )

    if errors:
        raise ValueError("Invalid provider configs:\n- " + "\n- ".join(errors))

