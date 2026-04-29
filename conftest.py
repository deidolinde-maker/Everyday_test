import pytest
import allure

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
        choices=("desktop", "mobile-chromium"),
        help="Профиль исполнения: desktop (по умолчанию) или mobile-chromium (эмуляция мобильного браузера).",
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


@pytest.fixture
def blocking_profile(pytestconfig):
    return pytestconfig.getoption("--blocking-profile", default="none")


@pytest.fixture(scope="session")
def execution_profile(pytestconfig):
    return pytestconfig.getoption("--execution-profile", default="desktop")


@pytest.fixture(scope="session", autouse=True)
def validate_execution_profile(pytestconfig):
    profile = pytestconfig.getoption("--execution-profile", default="desktop")
    browsers = _normalize_browser_option(pytestconfig.getoption("--browser", default=None))
    if profile == "mobile-chromium" and browsers and any(b != "chromium" for b in browsers):
        raise pytest.UsageError(
            "--execution-profile=mobile-chromium поддерживает только --browser chromium."
        )


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, playwright, execution_profile):
    if execution_profile != "mobile-chromium":
        return browser_context_args

    pixel_5 = playwright.devices["Pixel 5"]
    return {
        **browser_context_args,
        **pixel_5,
    }


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
