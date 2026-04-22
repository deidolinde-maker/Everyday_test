import pytest
import allure


def pytest_addoption(parser):
    parser.addoption(
        "--site",
        action="store",
        default=None,
        help="Домен сайта из SITE_CONFIGS, например: mts-home-gpon.ru",
    )
    parser.addoption(
        "--service-mode",
        action="store",
        default="all",
        choices=("all", "core", "variants"),
        help="Режим submit по Place: all (все), core (базовый), variants (только варианты Place).",
    )


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
