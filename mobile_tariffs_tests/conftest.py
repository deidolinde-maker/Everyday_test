"""
conftest.py — фикстуры Pytest для всего проекта.

Содержит:
  - browser_context: Playwright-контекст со стандартными настройками
  - landing_data: параметрическая фикстура для обхода всех лендингов
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright, BrowserContext

from config.landing_data import LANDINGS


# ─────────────────────────────────────────────────────────────────────────────
# Playwright browser context
# ─────────────────────────────────────────────────────────────────────────────

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
    browser = playwright_instance.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
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
