from __future__ import annotations

from config.providers import PROVIDER_MODULES
from config.schema import derive_site_id, validate_provider_modules


def available_providers() -> list[str]:
    return sorted(PROVIDER_MODULES.keys())


def _resolve_city_name(site: dict, default_city: str) -> str | None:
    if "city_name" in site:
        return site.get("city_name")

    cities = site.get("cities")
    if isinstance(cities, list):
        for city in cities:
            if isinstance(city, str) and city.strip():
                return city.strip()

    return default_city


def load_site_configs(provider: str | None = None) -> dict[str, dict]:
    validate_provider_modules(PROVIDER_MODULES)

    provider_filter = (provider or "").strip().lower() or None
    if provider_filter and provider_filter not in PROVIDER_MODULES:
        raise ValueError(
            f"--provider={provider!r} не найден. Доступно: {', '.join(available_providers())}"
        )

    combined: dict[str, dict] = {}
    for provider_name, module in PROVIDER_MODULES.items():
        if provider_filter and provider_name != provider_filter:
            continue

        default_city = module.DEFAULT_CITY
        for raw_site in module.SITES:
            site = dict(raw_site)
            site_id = site.get("site_id") or derive_site_id(site["base_url"])
            city_name = _resolve_city_name(site, default_city)
            site.pop("cities", None)
            site["city_name"] = city_name
            site["_provider"] = provider_name
            site["_site_id"] = site_id
            combined[site_id] = site

    return combined


def select_site_configs(
    *,
    provider: str | None = None,
    site: str | None = None,
) -> dict[str, dict]:
    site_configs = load_site_configs(provider=provider)

    if not site:
        return site_configs

    if site not in site_configs:
        if provider:
            available_for_provider = ", ".join(sorted(site_configs.keys())) or "(пусто)"
            raise ValueError(
                f"--site={site!r} не найден для --provider={provider!r}. "
                f"Доступно: {available_for_provider}"
            )
        available_all = ", ".join(sorted(site_configs.keys()))
        raise ValueError(f"--site={site!r} не найден. Доступно: {available_all}")

    return {site: site_configs[site]}

