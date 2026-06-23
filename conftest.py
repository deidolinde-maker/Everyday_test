import os

import allure
import pytest

from video_artifacts import (
    attach_or_cleanup_videos,
    build_recording_dir,
    cleanup_recording_dir,
    record_video_size_for_profile,
)

ADBLOCK_MVP_BLOCKLIST = (
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "adservice.google.com",
    "yandex.ru/ads",
    "an.yandex.ru",
    "mc.yandex.ru",
    "top.mail.ru",
    "adriver.ru",
    "adfox",
    "advert",
    "banner",
)

EXECUTION_PROFILE_ALLOWED_BROWSERS = {
    "desktop": {"chromium", "firefox", "webkit"},
    "mobile-chromium": {"chromium"},
    "mobile-webkit": {"webkit"},
}

EXECUTION_PROFILE_DEVICE_PRESET = {
    "mobile-chromium": "Pixel 5",
    "mobile-webkit": "iPhone 12",
}

NETWORK_PROFILE_ENV = "NETWORK_PROFILE"
NETWORK_PROFILE_VPN = "vpn"
NETWORK_PROXY_ENV_VARS = (
    "PLAYWRIGHT_PROXY_SERVER",
    "HTTPS_PROXY",
    "HTTP_PROXY",
)


def pytest_addoption(parser):
    parser.addoption(
        "--provider",
        action="store",
        default=None,
        help="Имя провайдера из config/providers (например: mts, beeline, megafon, t2).",
    )
    parser.addoption(
        "--site",
        action="store",
        default=None,
        help="Домен сайта (site_id), например: mts-home-gpon.ru",
    )
    parser.addoption(
        "--service-mode",
        action="store",
        default="all",
        choices=("all", "core", "variants"),
        help="Режим submit по Place: all (все), core (базовый), variants (только варианты Place).",
    )
    parser.addoption(
        "--blocking-profile",
        action="store",
        default="none",
        choices=("none", "adblock-mvp"),
        help="Профиль блокировщиков: none (по умолчанию) или adblock-mvp.",
    )
    parser.addoption(
        "--execution-profile",
        action="store",
        default="desktop",
        choices=("desktop", "mobile-chromium", "mobile-webkit"),
        help=(
            "Профиль исполнения: desktop (по умолчанию), "
            "mobile-chromium или mobile-webkit (эмуляция мобильного браузера)."
        ),
    )


def _normalize_browser_option(browser_opt) -> list[str]:
    if browser_opt is None:
        return []
    if isinstance(browser_opt, (list, tuple)):
        return [str(x).strip().lower() for x in browser_opt if str(x).strip()]
    value = str(browser_opt).strip().lower()
    return [value] if value else []


def _should_block_request(url: str, resource_type: str) -> bool:
    current_url = (url or "").lower()
    current_type = (resource_type or "").lower()

    if not current_url:
        return False

    # MVP: блокируем рекламные/трекерные домены и часть тяжёлых рекламных ресурсов.
    if any(marker in current_url for marker in ADBLOCK_MVP_BLOCKLIST):
        return True
    if current_type in {"media", "object"} and "ad" in current_url:
        return True
    return False


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


@pytest.fixture
def blocking_profile(pytestconfig):
    return pytestconfig.getoption("--blocking-profile", default="none")


@pytest.fixture(scope="session")
def execution_profile(pytestconfig):
    return pytestconfig.getoption("--execution-profile", default="desktop")


@pytest.fixture(scope="session", autouse=True)
def expose_execution_profile_to_process_env(execution_profile):
    """
    Экспортируем execution profile в env, чтобы runtime-логика теста
    могла строго разделять desktop/mobile поведение.
    """
    os.environ["PYTEST_EXECUTION_PROFILE"] = execution_profile


@pytest.fixture(scope="session", autouse=True)
def validate_execution_profile(pytestconfig):
    profile = pytestconfig.getoption("--execution-profile", default="desktop")
    browsers = _normalize_browser_option(pytestconfig.getoption("--browser", default=None))
    allowed = EXECUTION_PROFILE_ALLOWED_BROWSERS.get(profile, set())

    if browsers and any(b not in allowed for b in browsers):
        allowed_list = ", ".join(sorted(allowed)) if allowed else "<none>"
        actual_list = ", ".join(browsers)
        raise pytest.UsageError(
            f"--execution-profile={profile} поддерживает только --browser: {allowed_list}. "
            f"Получено: {actual_list}."
        )


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, playwright, execution_profile):
    device_preset_name = EXECUTION_PROFILE_DEVICE_PRESET.get(execution_profile)
    resolved_context_args = dict(browser_context_args)

    if device_preset_name:
        device_preset = playwright.devices[device_preset_name]
        resolved_context_args.update(device_preset)

    proxy_settings = _resolve_network_proxy_settings()
    if proxy_settings:
        resolved_context_args["proxy"] = proxy_settings

    return resolved_context_args


@pytest.fixture
def page(browser, browser_context_args, execution_profile, request):
    recording_dir = build_recording_dir(request.node.nodeid, "suite-a")
    context = browser.new_context(
        **browser_context_args,
        record_video_dir=str(recording_dir),
        record_video_size=record_video_size_for_profile(execution_profile),
    )
    tracked_pages = []

    def _track_page(new_page):
        tracked_pages.append(new_page)

    context.on("page", _track_page)
    page = context.new_page()
    tracked_pages.append(page)
    try:
        yield page
    finally:
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


@pytest.fixture(autouse=True)
def apply_blocking_profile(page, blocking_profile):
    if blocking_profile != "adblock-mvp":
        return

    def _route_handler(route, request):
        try:
            if _should_block_request(request.url, request.resource_type):
                route.abort()
                return
        except Exception:
            pass
        route.continue_()

    page.route("**/*", _route_handler)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    После каждого теста: если упал — делаем скриншот и прикрепляем к Allure.
    """
    outcome = yield
    report  = outcome.get_result()
    if report.when == "call":
        item.rep_call = report

    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page is not None:
            try:
                screenshot = page.screenshot(full_page=True)
                allure.attach(
                    screenshot,
                    name="screenshot_on_failure",
                    attachment_type=allure.attachment_type.PNG,
                )
            except Exception as e:
                print(f"[SCREENSHOT] Не удалось сделать скриншот: {e}")
