"""
conftest.py — фикстуры Pytest для всего проекта.

Содержит:
  - browser_context: Playwright-контекст со стандартными настройками
  - landing_data: параметрическая фикстура для обхода всех лендингов
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import sync_playwright, BrowserContext

from config.landing_data import LANDINGS

NETWORK_PROFILE_ENV = "NETWORK_PROFILE"
NETWORK_PROFILE_VPN = "vpn"
NETWORK_PROXY_ENV_VARS = (
    "PLAYWRIGHT_PROXY_SERVER",
    "HTTPS_PROXY",
    "HTTP_PROXY",
)


# ─────────────────────────────────────────────────────────────────────────────
# Playwright browser context
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_proxy_server(proxy_server: str | None) -> str:
    value = (proxy_server or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://", "socks5://", "socks4://")):
        return value
    return f"http://{value}"


def _resolve_network_proxy_settings() -> dict[str, str] | None:
    profile = (os.getenv(NETWORK_PROFILE_ENV) or "off").strip().lower()
    if profile != NETWORK_PROFILE_VPN:
        return None

    proxy_server = ""
    for env_name in NETWORK_PROXY_ENV_VARS:
        proxy_server = _normalize_proxy_server(os.getenv(env_name))
        if proxy_server:
            break

    if not proxy_server:
        print(
            "[NETWORK] NETWORK_PROFILE=vpn selected, but no proxy env was found. "
            "Proceeding without a Playwright proxy override."
        )
        return None

    proxy_settings: dict[str, str] = {"server": proxy_server}
    bypass = (os.getenv("NETWORK_PROXY_BYPASS") or os.getenv("NO_PROXY") or "").strip()
    if bypass:
        proxy_settings["bypass"] = bypass
    return proxy_settings


@pytest.fixture(scope="session")
def playwright_instance():
    """Запуск и остановка Playwright один раз за сессию."""
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="function")
def browser_context(playwright_instance):
    """
    Новый изолированный browser-контекст для каждого теста.
    Позволяет отслеживать новые вкладки через context.pages.
    """
    proxy_settings = _resolve_network_proxy_settings()
    launch_kwargs = dict(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    if proxy_settings:
        launch_kwargs["proxy"] = proxy_settings

    browser = playwright_instance.chromium.launch(**launch_kwargs)
    context: BrowserContext = browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        ignore_https_errors=True,
    )
    context.set_default_timeout(30_000)  # 30 секунд на ожидание элементов
    yield context
    context.close()
    browser.close()


# ─────────────────────────────────────────────────────────────────────────────
# Параметрическая фикстура по лендингам
# ─────────────────────────────────────────────────────────────────────────────

def pytest_generate_tests(metafunc):
    """
    Генерация параметров для теста test_mobile_tariffs.
    Каждый лендинг из LANDINGS становится отдельным test-case в Allure.
    """
    if "landing" in metafunc.fixturenames:
        metafunc.parametrize(
            "landing",
            LANDINGS,
            ids=[l["name"] for l in LANDINGS],
        )
