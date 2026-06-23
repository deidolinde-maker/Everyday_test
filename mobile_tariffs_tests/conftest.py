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
from video_artifacts import (
    attach_or_cleanup_videos,
    build_recording_dir,
    cleanup_recording_dir,
)

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
def browser_context(playwright_instance, request):
    """
    Новый изолированный browser-контекст для каждого теста.
    Позволяет отслеживать новые вкладки через context.pages.
    """
    recording_dir = build_recording_dir(request.node.nodeid, "mobile-suite")
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
        record_video_dir=str(recording_dir),
        record_video_size={"width": 360, "height": 640},
    )
    tracked_pages = []

    def _track_page(new_page):
        tracked_pages.append(new_page)

    context.on("page", _track_page)
    context.set_default_timeout(30_000)  # 30 секунд на ожидание элементов
    yield context
    pages = []
    seen_page_ids = set()
    for current_page in tracked_pages:
        page_id = id(current_page)
        if page_id in seen_page_ids:
            continue
        seen_page_ids.add(page_id)
        pages.append(current_page)
    try:
        context.close()
    finally:
        failed = bool(getattr(getattr(request.node, "rep_call", None), "failed", False))
        attach_or_cleanup_videos(pages, attach=failed, prefix="video_on_failure")
        cleanup_recording_dir(recording_dir)
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
