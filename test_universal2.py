"""
Универсальный тест форм для сайтов интернет-провайдеров.

Запуск для конкретного сайта:
    pytest -s --headed --site=mts-home-gpon.ru

Запуск для всех сайтов последовательно:
    pytest -s --headed  (прогоняет все сайты из SITE_CONFIGS)
    pytest test_universal2.py --alluredir=allure-results -s - все сайты с аллюр
    pytest test_universal2.py --site=mts-home-gpon.ru --alluredir=allure-results -s - конкретный сайт с аллюр
    pytest test_universal2.py --service-mode=core -s - базовый submit без полного перебора Place
    pytest test_universal2.py --service-mode=variants -s - отдельный прогон только Place-вариантов

Добавить новый сайт — достаточно добавить запись в SITE_CONFIGS.
"""

import pytest
from playwright.sync_api import Page, expect
import allure
import os
import requests
import time
import sys
from urllib.parse import urlsplit
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

try:
    # Avoid UnicodeEncodeError on Windows consoles with cp1251.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REALLY_SUBMIT = True # True — реально отправлять заявки

# ---------------------------------------------------------------------------
# Таблица ошибок → причин для Telegram-алертов
# ---------------------------------------------------------------------------

ERROR_REASONS = {
    "navigation_failed": ("Навигация на сайт не удалась", "Сайт не открылся в пределах таймаута"),
    "popup_not_found":  ("Попап не распознан",           "Попап не открылся после клика"),
    "form_not_filled":  ("Форма не заполнена",            "Поле недоступно или перекрыто оверлеем"),
    "submit_not_found": ("Кнопка отправки не найдена",    "Форма не в ожидаемом состоянии"),
    "no_confirmation":  ("Подтверждение не получено",     "Сайт не перешёл на /thanks"),
    "thanks_return_failed": ("Не выполнено закрытие страницы Спасибо", "Не удалось вернуться на главную без региона"),
    "click_failed":     ("Клик по кнопке не удался",      "Элемент не виден или не существует"),
    "city_not_found":   ("Город не найден в списке",      "Список городов не загрузился"),
    "city_no_redirect": ("Переход на город не произошёл", "URL не изменился после клика"),
}

ERROR_STEP_NAMES = {
    "navigation_failed": "Открытие страницы лендинга",
    "popup_not_found": "Появился попап заявки",
    "form_not_filled": "Заполнение формы заявки",
    "submit_not_found": "Отправка заявки после клика на кнопку отправки",
    "no_confirmation": "Отправка заявки после клика на кнопку отправки",
    "thanks_return_failed": "Закрытие страницы Спасибо и переход на главную без региона",
    "click_failed": "Клик по кнопке открытия формы",
    "city_not_found": "Изменить город в попапе заявки",
    "city_no_redirect": "Изменить город в попапе заявки",
}


def _now_msk_str() -> str:
    try:
        dt = datetime.now(ZoneInfo("Europe/Moscow"))
    except Exception:
        # Windows-среды без tzdata: fallback к фиксированному UTC+3.
        dt = datetime.now(timezone(timedelta(hours=3)))
    return dt.strftime("%Y-%m-%d %H:%M:%S (MSK)")


def _normalize_alert_text(text: str, max_len: int = 900) -> str:
    value = " ".join((text or "").split()).strip()
    if len(value) > max_len:
        return value[: max_len - 3] + "..."
    return value


def _build_form_alert_message(
    site_label: str,
    url: str,
    error_text: str,
    details: str = "",
    *,
    critical: bool = False,
) -> str:
    header = "🚨 Критическая ошибка автотеста формы" if critical else "🚨 Ошибка автотеста формы"
    report_url = os.getenv("ALLURE_URL", "").strip() or os.getenv("RUN_URL", "").strip()

    lines = [
        header,
        "",
        f"🕒 Время: {_now_msk_str()}",
        f"🌐 Лендинг: {site_label}",
    ]
    if url:
        lines.append(f"🔗 URL: {url}")
    lines.append(f"❌ Ошибка: {error_text}")
    if details:
        lines.append(f"🔎 Детали: {details}")
    if report_url:
        lines.append(f"🔗 Отчёт: {report_url}")

    return "\n".join(lines)


def send_telegram_alert(text: str, alert_type: str = "tech") -> bool:
    """Отправляет сообщение в Telegram и логирует результат отправки."""
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print(f"[TELEGRAM][{alert_type}] Пропуск отправки: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы")
        return False
    print(f"[TELEGRAM][{alert_type}] Попытка отправки")
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if resp.ok:
            print(f"[TELEGRAM][{alert_type}] Успешно отправлено (status={resp.status_code})")
            return True
        body = (resp.text or "").strip().replace("\n", " ")
        print(f"[TELEGRAM][{alert_type}] Ошибка отправки (status={resp.status_code}): {body[:180]}")
        return False
    except Exception as e:
        print(f"[TELEGRAM][{alert_type}] Исключение при отправке: {e}")
        return False


def mark_step_not_applicable(site_label: str, step_no: str, step_name: str, reason: str):
    text = f"[{site_label}] Шаг {step_no}: {step_name} — неприменим ({reason})"
    print(f"  ℹ️ {text}")
    allure.attach(
        text,
        name=f"Шаг {step_no}: {step_name} — пропуск",
        attachment_type=allure.attachment_type.TEXT,
    )


def send_step_alert(site_label: str, step_no: str, step_name: str, reason: str, page: "Page" = None):
    url = page.url if page else ""
    error_text = f'Не выполнен шаг "{step_name}"'
    details = _normalize_alert_text(reason)
    message = _build_form_alert_message(site_label, url, error_text, details)

    print(f"[STEP-ALERT] [{site_label}] Шаг {step_no}: {step_name} | {reason} | {url}")
    send_telegram_alert(message, alert_type="step")


class SiteUnavailableError(RuntimeError):
    """Сайт недоступен/не отвечает — текущий сайт нужно пропустить."""


def send_critical_alert(site_label: str, step_no: str, step_name: str, reason: str, page: "Page" = None):
    url = page.url if page else ""
    error_text = f'Не выполнен шаг "{step_name}"'
    details = _normalize_alert_text(reason)
    text = _build_form_alert_message(
        site_label,
        url,
        error_text,
        details,
        critical=True,
    )

    print(f"[CRITICAL] [{site_label}] Шаг {step_no}: {step_name} | {reason} | {url}")
    allure.attach(
        text,
        name=f"CRITICAL: Шаг {step_no} {step_name}",
        attachment_type=allure.attachment_type.TEXT,
    )
    send_telegram_alert(text, alert_type="critical")


def skip_site_due_unavailability(
    site_label: str,
    step_no: str,
    step_name: str,
    reason: str,
    page: "Page" = None,
):
    send_critical_alert(site_label, step_no, step_name, reason, page)
    pytest.skip(f"[{site_label}] {step_name}: {reason}")


def goto_or_handle_step(
    page: "Page",
    url: str,
    site_label: str,
    step_no: str,
    step_name: str,
):
    ok, is_critical, nav_reason = safe_goto(page, url)
    if ok:
        return

    reason = f"не удалось открыть {url} | {nav_reason}"
    if is_critical:
        skip_site_due_unavailability(site_label, step_no, step_name, reason, page)

    send_step_alert(site_label, step_no, step_name, reason, page)
    pytest.fail(f"[{site_label}] Шаг {step_no}: {step_name} | {reason}")



def _is_business_target_url(current_url: str, business_url: str) -> bool:
    target_host = (urlsplit(business_url).netloc or "").lower()
    target_path = (urlsplit(business_url).path or "").rstrip("/").lower()

    cur_host = (urlsplit(current_url).netloc or "").lower()
    cur_path = (urlsplit(current_url).path or "").rstrip("/").lower()

    if target_host and cur_host and cur_host != target_host:
        return False
    if not target_path:
        return False
    return cur_path == target_path or cur_path.startswith(target_path + "/")


def try_open_business_via_navigation(page: "Page", business_url: str) -> tuple[bool, str]:
    if _is_business_target_url(page.url, business_url):
        return True, "already_on_business"

    checked = 0
    for sel in BUSINESS_NAV_SELECTORS:
        try:
            loc = page.locator(sel)
            total = loc.count()
        except Exception:
            continue

        for idx in range(min(total, 8)):
            checked += 1
            cand = loc.nth(idx)
            try:
                if not cand.is_visible():
                    continue
            except Exception:
                continue

            try:
                href = (cand.get_attribute("href") or "").strip().lower()
            except Exception:
                href = ""

            if href.startswith("mailto:") or href.startswith("tel:"):
                continue

            before_url = page.url
            try:
                cand.scroll_into_view_if_needed()
                cand.click(timeout=BUSINESS_NAV_CLICK_TIMEOUT_MS, force=True)
            except Exception:
                continue

            page.wait_for_timeout(500)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=BUSINESS_NAV_WAIT_TIMEOUT_MS)
            except Exception:
                pass

            if _is_business_target_url(page.url, business_url):
                return True, f"selector={sel} idx={idx}"

            if page.url != before_url and _is_business_target_url(page.url, business_url):
                return True, f"selector={sel} idx={idx} delayed_url"

    if checked == 0:
        return False, "business nav candidates not found"
    return False, "business nav click did not lead to target"


def goto_business_or_handle_step(
    page: "Page",
    start_url: str,
    business_url: str,
    site_label: str,
    step_no: str,
    step_name: str,
):
    goto_or_handle_step(page, start_url, site_label, step_no, step_name)
    close_overlays(page)

    nav_ok, nav_reason = try_open_business_via_navigation(page, business_url)
    if nav_ok:
        print(f"  [BUSINESS-NAV] success via landing nav ({nav_reason})")
        return

    print(f"  [BUSINESS-NAV] fallback goto -> {business_url} ({nav_reason})")
    goto_or_handle_step(page, business_url, site_label, step_no, step_name)


def log_error(error_code: str, page: "Page", site_label: str, extra: str = ""):
    """
    Печатает ошибку в консоль и мгновенно шлёт Telegram-алерт.

    error_code — ключ из ERROR_REASONS
    page       — для получения текущего URL
    site_label — домен сайта
    extra      — дополнительный контекст (опционально)
    """
    error_msg, reason = ERROR_REASONS.get(
        error_code, (error_code, "Неизвестная причина")
    )
    url  = page.url if page else ""

    # Консоль
    print(f"  ❌ {error_msg} | {reason} | {url}")

    step_name = ERROR_STEP_NAMES.get(error_code, error_msg)
    error_text = f'Не выполнен шаг "{step_name}"'
    if error_code == "no_confirmation":
        error_text += ", не произошел редирект на страницу Спасибо"

    detail_parts = [_normalize_alert_text(reason, max_len=300)]
    if extra:
        detail_parts.append(_normalize_alert_text(extra, max_len=500))
    details = " | ".join(p for p in detail_parts if p)

    message = _build_form_alert_message(site_label, url, error_text, details)
    send_telegram_alert(message, alert_type="tech")

# ---------------------------------------------------------------------------
# Конфигурация форм (CSS-классы полей)
# ---------------------------------------------------------------------------

FORM_CONFIGS = {
    "checkaddress": {
        "street":     ".checkaddress_address_street",
        "house":      ".checkaddress_address_house",
        "phone":      ".checkaddress_address_phone",
        "submit":     ".checkaddress_address_button_send",
        "no_house":   False,
        "no_suggest": False,
    },
    "connection": {
        "street":     ".connection_address_street",
        "house":      ".connection_address_house",
        "phone":      ".connection_address_phone",
        "submit":     ".connection_address_button_send",
        "no_house":   False,
        "no_suggest": False,
    },
    "profit": {
        "street":     ".profit_address_street",
        "house":      ".profit_address_house",
        "phone":      ".profit_address_phone",
        "submit":     ".profit_address_button_send",
        "no_house":   False,
        "no_suggest": False,
    },
    "express-connection": {
        "street":     ".express-connection_address_street",
        "house":      ".express-connection_address_house",
        "phone":      ".express-connection_address_phone",
        "submit":     ".express-connection_address_button_send",
        "no_house":   False,
        "no_suggest": False,
    },
    "business": {
        "street":     ".business_no_address_full_address",
        "house":      None,
        "phone":      ".business_no_address_phone",
        "submit":     ".business_no_address_button_send",
        "no_house":   True,
        "no_suggest": True,
    },
}

# CSS-классы кнопок, открывающих попапы (по типу формы)
POPUP_BUTTON_CLASSES = {
    "profit":             ".profit_address_button",
    "express-connection": ".express-connection_address_button",
    "business":           ".business_no_address_button",
}

# ---------------------------------------------------------------------------
# Конфигурация сайтов
# has_checkaddress — есть ли форма "Проверить адрес" на главной
# has_business     — есть ли страница /business
# has_city         — есть ли попап смены города и нужно ли его тестировать
# city_name        — город для теста (None = пропустить тест города)
# popup_keywords   — тексты кнопок открытия попапов (для connection и др.)
# ---------------------------------------------------------------------------

SITE_CONFIGS = {
     "mts-home-gpon.ru": {
       "base_url":        "https://mts-home-gpon.ru/",
        "has_checkaddress": True,
        "has_business":     True,
        "city_name":        "Москва",
    },
    "mts-home.online": {
        "base_url":        "https://mts-home.online/",
        "has_checkaddress": False,
        "has_business":     True,
        "city_name":        "Москва",
    },
    "mts-home-online.ru": {
        "base_url":        "https://mts-home-online.ru/",
        "has_checkaddress": False,
        "has_business":     True,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "internet-mts-home.online": {
        "base_url":        "https://internet-mts-home.online/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        "Москва",
    },
    "mts-internet.online": {
        "base_url":        "https://mts-internet.online/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        "Москва",
   },
    "beeline-internet.online": {
        "base_url":        "https://beeline-internet.online/",
        "has_checkaddress": False,
        "has_business":     True,
        "city_name":        "Москва",
        "has_region_popup": True,
    },
    "beeline-ru.online": {
        "base_url":        "https://beeline-ru.online/",
        "has_checkaddress": False,
        "has_business":     True,
        "city_name":        "Москва",
        "has_region_popup": True,
    },
    "online-beeline.ru": {
        "base_url":        "https://online-beeline.ru/",
        "has_checkaddress": False,
        "has_business":     True,
        "city_name":        "Москва",
        "has_region_popup": True,
    },
    "beeline-ru.pro": {
        "base_url":        "https://beeline-ru.pro/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        "Москва",
        "has_region_popup": True,
    },
    "beeline-home.online": {
        "base_url":        "https://beeline-home.online/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        "Москва",
        "has_region_popup": True,
    },
    "beelline-internet.ru": {
        "base_url":        "https://beelline-internet.ru/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        "Москва",
        "has_region_popup": True,
    },
    "rtk-ru.online": {
        "base_url":        "https://rtk-ru.online/",
        "has_checkaddress": True,
        "has_business":     True,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "rt-internet.online": {
        "base_url":        "https://rt-internet.online/",
        "has_checkaddress": True,
        "has_business":     False,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "rtk-home-internet.ru": {
        "base_url":        "https://rtk-home-internet.ru/",
        "has_checkaddress": True,
        "has_business":     False,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "rtk-internet.online": {
        "base_url":        "https://rtk-internet.online/",
        "has_checkaddress": True,
        "has_business":     True,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "rtk-home.ru": {
        "base_url":        "http://rtk-home.ru/",
        "has_checkaddress": True,
        "has_business":     True,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "dom-provider.online": {
        "base_url":        "https://dom-provider.online/",
        "has_checkaddress": False,
        "has_business":     False,
         "city_name":        "Москва",
        "has_name_field": True,
    },
    "providerdom.ru": {
        "base_url":        "https://providerdom.ru/",
        "has_checkaddress": False,
        "has_business":     False,
         "city_name":        "Москва",
        "has_name_field": True,
    },
    "mega-premium.ru": {
        "base_url":        "https://mega-premium.ru/",
        "has_checkaddress": True,
        "has_business":     False,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "mega-home-internet.ru": {
        "base_url":        "https://mega-home-internet.ru/",
        "has_checkaddress": True,
        "has_business":     False,
         "city_name":        "Москва",
        "has_name_field": True,
    },
    "t2-ru.online": {
        "base_url":        "https://t2-ru.online",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "ttk-internet.ru": {
        "base_url":        "https://ttk-internet.ru/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        None,   # нет Москвы в списке городов
    },
    "ttk-ru.online": {
        "base_url":        "https://ttk-ru.online/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        None,   # нет Москвы в списке городов
    },
    # "stage-project.ru": {
    #    "base_url":        "https://stage-project.ru/",
     #   "has_checkaddress": True,
      #  "has_business":     True,
       # "city_name":        "Москва",
        #"has_name_field": True,
#    },
}

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

SUCCESS_URL_MARKERS = ["/tilda/form1/submitted", "/thanks"]
SITE_UNAVAILABLE_THRESHOLD_MS = 60_000
NAV_GOTO_TIMEOUT_MS = 20_000
NAV_RETRIES = 3
SUBMIT_CONFIRM_TIMEOUT_MS = 25_000
SUBMIT_CONFIRM_GRACE_MS = 2_000
CITY_LOADSTATE_TIMEOUT_MS = 7_000
HOUSE_ENABLE_TIMEOUT_MS = 3_500
CHECKBOX_SCAN_LIMIT = 20
CHECKBOX_CHECK_LIMIT = 4
CHECKBOX_VISIBILITY_TIMEOUT_MS = 250
CHECKBOX_ACTION_TIMEOUT_MS = 1_200

POPUP_CONTAINER_SELECTORS = [
    "div#popup", "div.popup",
    "[id*='popup']:not(script)",
    "[class*='popup']:not(script)",
    "[class*='modal']:not(script)",
    "[class*='fancybox']:not(script)",
    "[class*='overlay']:not(script)",
]

POPUP_OPEN_KEYWORDS = [
    "подключить", "получить консультацию", "оставить заявку",
    "заказать", "оформить", "узнать подробнее",
]
POPUP_SKIP_KEYWORDS = ["проверить адрес", "сменить город"]

SUGGESTION_SELECTORS = [
    "[role='option']", "[role='listbox'] li",
    ".suggestions__item", ".suggestion-item",
    ".autocomplete__item", ".ui-menu-item",
    "[class*='suggest'] li", "[class*='autocomplete'] li",
    "[class*='dropdown'] li",
]

SERVICE_PLACE_VALUES = [
    "В квартиру",
    "В частный дом",
    "Для бизнеса",
]

REGION_POPUP_DETECT_SELECTORS = [
    "#yesButton",
    "#noButton",
    ".popup-select-region__button.city",
    "button.region-search__button",
    ".region-search__button.button.button-red",
    ".region-search__button.button.button-green",
    ".popup-select-region__content-wrapper .popup__close",
]

THANKS_RETURN_SELECTORS = [
    "a:has-text('На главную')",
    "button:has-text('На главную')",
    "a:has-text('Вернуться')",
    "button:has-text('Вернуться')",
    "a:has-text('Закрыть')",
    "button:has-text('Закрыть')",
    "a:has-text('Продолжить')",
    "button:has-text('Продолжить')",
    ".popup__close",
    ".modal__close",
    ".fancybox-close-small",
    "[aria-label*='close']",
    "[aria-label*='закры']",
]

BUSINESS_NAV_SELECTORS = [
    "header a[href*='/business']",
    "nav a[href*='/business']",
    "a[href*='/business']",
    "header a[href*='business']",
    "nav a[href*='business']",
    "a[href*='business']",
    "a:has-text('\u0414\u043b\u044f \u0431\u0438\u0437\u043d\u0435\u0441\u0430')",
    "button:has-text('\u0414\u043b\u044f \u0431\u0438\u0437\u043d\u0435\u0441\u0430')",
    "a:has-text('\u0411\u0438\u0437\u043d\u0435\u0441')",
    "button:has-text('\u0411\u0438\u0437\u043d\u0435\u0441')",
]
BUSINESS_NAV_CLICK_TIMEOUT_MS = 2_500
BUSINESS_NAV_WAIT_TIMEOUT_MS = 5_000

SERVICE_MODE_ALL = "all"
SERVICE_MODE_CORE = "core"
SERVICE_MODE_VARIANTS = "variants"
SERVICE_MODE_CHOICES = {SERVICE_MODE_ALL, SERVICE_MODE_CORE, SERVICE_MODE_VARIANTS}


def normalize_service_mode(value: str | None) -> str:
    mode = (value or SERVICE_MODE_ALL).strip().lower()
    if mode not in SERVICE_MODE_CHOICES:
        return SERVICE_MODE_ALL
    return mode


# ---------------------------------------------------------------------------
# pytest: параметр --site
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--site", action="store", default=None,
        help="Домен сайта из SITE_CONFIGS, например: mts-home-gpon.ru"
    )


def pytest_generate_tests(metafunc):
    """Параметризует фикстуру site_cfg — один прогон на каждый сайт."""
    if "site_cfg" in metafunc.fixturenames:
        site_arg = metafunc.config.getoption("--site", default=None)
        service_mode = normalize_service_mode(
            metafunc.config.getoption("--service-mode", default=SERVICE_MODE_ALL)
        )

        if site_arg:
            selected_items = [(site_arg, SITE_CONFIGS[site_arg])]
        else:
            selected_items = list(SITE_CONFIGS.items())

        configs = []
        ids = []
        for site_id, cfg in selected_items:
            cfg_copy = dict(cfg)
            cfg_copy["_service_mode"] = service_mode
            configs.append(cfg_copy)
            ids.append(site_id if service_mode == SERVICE_MODE_ALL else f"{site_id}[{service_mode}]")

        metafunc.parametrize("site_cfg", configs, ids=ids)


@pytest.fixture
def site_cfg(request):
    return request.param


# ---------------------------------------------------------------------------
# Базовые утилиты
# ---------------------------------------------------------------------------

def iter_visible(locator):
    for i in range(locator.count()):
        item = locator.nth(i)
        try:
            if item.is_visible():
                yield item
        except Exception:
            pass


def dismiss_region_popup(page: Page):
    """
    Закрывает попап выбора/подтверждения региона на сайтах Beeline.
    Два варианта попапа:
      1. Кнопка "Да" (id=yesButton) — подтверждаем город
      2. Кнопка закрытия .popup__close внутри .popup-select-region__content-wrapper
    Безопасно вызывать на любом сайте — если попапа нет, просто ничего не делает.
    """
    # Ждём чуть — попап появляется с небольшой задержкой после загрузки
    page.wait_for_timeout(600)

    # Вариант 1: явные кнопки управления регионом (Да/Нет/Выбрать город)
    region_action_buttons = [
        ("#yesButton", "кнопка 'Да'"),
        ("#noButton", "кнопка 'Нет'"),
        (".popup-select-region__button.city", "кнопка выбора города (.popup-select-region__button.city)"),
        ("button.region-search__button", "кнопка выбора города (.region-search__button)"),
        (".region-search__button.button.button-red", "кнопка выбора города (red)"),
        (".region-search__button.button.button-green", "кнопка выбора города (green)"),
    ]
    for sel, label in region_action_buttons:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                btn.click(force=True)
                page.wait_for_timeout(400)
                print(f"  [REGION] Попап региона обработан ({label})")
                return
        except Exception:
            pass

    # Вариант 1b: текстовая кнопка "Выбрать город"
    try:
        choose_btn = page.get_by_role("button", name="Выбрать город").first
        if choose_btn.count() > 0 and choose_btn.is_visible():
            choose_btn.click(force=True)
            page.wait_for_timeout(400)
            print("  [REGION] Попап региона обработан (кнопка 'Выбрать город')")
            return
    except Exception:
        pass

    # Вариант 2: кнопка .popup__close внутри .popup-select-region__content-wrapper
    try:
        close_btn = page.locator(
            ".popup-select-region__content-wrapper .popup__close"
        ).first
        if close_btn.count() > 0 and close_btn.is_visible():
            close_btn.click(force=True)
            page.wait_for_timeout(400)
            print("  [REGION] Попап региона закрыт (кнопка .popup__close)")
            return
    except Exception:
        pass


def accept_cookie_banner(page: Page):
    """
    Принимает баннер согласия на cookies.
    Безопасно вызывать на любом сайте — если баннера нет, ничего не делает.
    Ищет кнопку по нескольким вариантам — разные сайты используют разную вёрстку.
    """
    # Ждём — Tilda/Beeline баннеры появляются с задержкой 0.5-1.5с
    page.wait_for_timeout(1500)

    cookie_selectors = [
        "#cookieButton",                       # Beeline: <div id="cookieButton">OK</div>
        "#cookieAccept",                       # РТК: <button id="cookieAccept">
        ".cookie-btn",                         # РТК: <button class="cookie-btn">
        "#cookie-accept",
        ".cookie-accept",
        "[class*='cookie'][class*='btn']",
        "[class*='cookie'][class*='button']",
        "[id*='cookie'][id*='accept']",
        "[id*='cookieAccept']",
        "[id*='cookieButton']",
        ".t886__btn",                          # Tilda cookie banner button
    ]
    for sel in cookie_selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                btn.click(force=True)
                page.wait_for_timeout(400)
                print(f"  [COOKIE] Баннер принят ({sel})")
                return
        except Exception:
            pass

    # Запасной вариант: любой видимый элемент с текстом OK/Принять
    for sel in ["div", "button", "a", "span"]:
        try:
            elems = page.locator(sel)
            for i in range(min(elems.count(), 30)):
                el = elems.nth(i)
                if not el.is_visible(timeout=500):
                    continue
                text = (el.inner_text() or "").strip().lower()
                if text in {"ok", "ок", "принять", "accept", "agree"}:
                    el.click(force=True)
                    page.wait_for_timeout(400)
                    print(f"  [COOKIE] Баннер принят (текст: '{text}', тег: {sel})")
                    return
        except Exception:
            pass


def close_overlays(page: Page):
    # Шаг 1: попап подтверждения региона (Beeline-сайты) — важен, идёт первым
    dismiss_region_popup(page)

    # Шаг 2: баннер согласия на cookies (РТК и другие)
    accept_cookie_banner(page)

    try:
        ok = page.get_by_role("button", name="ОК", exact=True)
        if ok.count() > 0:
            ok.first.click(timeout=1000, force=True)
    except Exception:
        pass
    for btn in iter_visible(page.locator(
        "button,[role='button'],.popup__close,.modal__close,.fancybox-close-small"
    )):
        try:
            aria  = (btn.get_attribute("aria-label") or "").lower()
            title = (btn.get_attribute("title") or "").lower()
            text  = (btn.inner_text() or "").strip().lower()
            if ("close" in aria or "закры" in aria or "close" in title
                    or "закры" in title or text in {"x", "×", "✕", "закрыть"}):
                btn.click(timeout=1000, force=True)
        except Exception:
            pass
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass


def close_popup_or_page(page: Page):
    current = page.url.lower()
    if any(m in current for m in SUCCESS_URL_MARKERS):
        return
    for btn in iter_visible(page.locator(
        "button,[role='button'],.popup__close,.modal__close,.fancybox-close-small"
    )):
        try:
            aria  = (btn.get_attribute("aria-label") or "").lower()
            title = (btn.get_attribute("title") or "").lower()
            text  = (btn.inner_text() or "").strip().lower()
            if ("close" in aria or "закры" in aria or "close" in title
                    or "закры" in title or text in {"x", "×", "✕", "закрыть"}):
                btn.click(force=True)
                page.wait_for_timeout(400)
                return
        except Exception:
            pass
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass


def safe_goto(
    page: Page,
    url: str,
    retries: int = NAV_RETRIES,
    goto_timeout_ms: int = NAV_GOTO_TIMEOUT_MS,
    outage_threshold_ms: int = SITE_UNAVAILABLE_THRESHOLD_MS,
) -> tuple[bool, bool, str]:
    # Если застряли на странице благодарности — даём браузеру завершить редирект
    try:
        if any(m in page.url.lower() for m in SUCCESS_URL_MARKERS):
            page.wait_for_timeout(2000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(300)

    started_at = time.monotonic()
    last_error = ""

    for attempt in range(1, retries + 1):
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=goto_timeout_ms)
            page.wait_for_timeout(500)

            status = None
            try:
                status = response.status if response else None
            except Exception:
                status = None

            if status is not None and status >= 400:
                reason = f"HTTP {status}"
                print(f"  [NAV] ❌ {url} ({reason})")
                return False, True, reason

            current_url = (page.url or "").lower()
            if current_url.startswith("chrome-error://") or "about:neterror" in current_url:
                last_error = f"browser net error ({current_url})"
                print(f"  [NAV] Попытка {attempt}/{retries}: {last_error}")
                page.wait_for_timeout(1500)
                continue

            print(f"  [NAV] {url}")
            return True, False, ""
        except Exception as e:
            last_error = str(e).replace("\n", " ")[:220]
            print(f"  [NAV] Попытка {attempt}/{retries}: {last_error}")
            page.wait_for_timeout(1500)

    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    is_critical = elapsed_ms >= outage_threshold_ms
    if is_critical:
        reason = f"timeout {elapsed_ms // 1000}с (>={outage_threshold_ms // 1000}с), last_error={last_error or 'n/a'}"
    else:
        reason = f"nav_failed {elapsed_ms // 1000}с, last_error={last_error or 'n/a'}"
    print(f"  [NAV] ❌ Не удалось перейти на {url} | {reason}")
    return False, is_critical, reason


def _is_success_url(url: str) -> bool:
    return any(m in (url or "").lower() for m in SUCCESS_URL_MARKERS)


def wait_for_success_url(page: Page, timeout_ms: int = SUBMIT_CONFIRM_TIMEOUT_MS) -> bool:
    print(f"  [SUBMIT] Ждём подтверждения (до {timeout_ms // 1000}с)...")
    poll_ms = 300
    elapsed = 0

    while elapsed < timeout_ms:
        current_url = page.url
        if _is_success_url(current_url):
            print(f"  [SUBMIT] ✅ {current_url}")
            return True
        page.wait_for_timeout(poll_ms)
        elapsed += poll_ms

    # Грейс-период: часть сайтов делает поздний redirect после сабмита
    page.wait_for_timeout(SUBMIT_CONFIRM_GRACE_MS)
    if _is_success_url(page.url):
        print(f"  [SUBMIT] ✅ {page.url} (grace)")
        return True

    # Редкий кейс: подтверждение открылось в новой вкладке
    for p in page.context.pages:
        try:
            if _is_success_url(p.url):
                print(f"  [SUBMIT] ✅ в новой вкладке: {p.url}")
                return True
        except Exception:
            pass

    print(f"  [SUBMIT] ❌ URL: {page.url}")
    return False


def detect_visible_region_popup(page: Page) -> str | None:
    for sel in REGION_POPUP_DETECT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                return sel
        except Exception:
            pass

    try:
        choose_btn = page.get_by_role("button", name="Выбрать город").first
        if choose_btn.count() > 0 and choose_btn.is_visible():
            return "button:has-text('Выбрать город')"
    except Exception:
        pass

    return None


def _wait_until_left_success_url(page: Page, timeout_ms: int = 6000) -> bool:
    poll_ms = 250
    elapsed = 0
    while elapsed < timeout_ms:
        if not _is_success_url(page.url):
            return True
        page.wait_for_timeout(poll_ms)
        elapsed += poll_ms
    return not _is_success_url(page.url)


def verify_thanks_close_and_return(page: Page, return_url: str) -> tuple[bool, str]:
    with allure.step("Проверка: закрытие Thanks и возврат на главную без региона"):
        if not _is_success_url(page.url):
            return False, f"страница не в состоянии Thanks ({page.url})"

        action = "none"
        for sel in THANKS_RETURN_SELECTORS:
            try:
                btn = page.locator(sel).first
                if btn.count() == 0 or not btn.is_visible():
                    continue
                btn.click(force=True)
                if _wait_until_left_success_url(page, timeout_ms=5000):
                    action = f"click:{sel}"
                    break
            except Exception:
                pass

        if _is_success_url(page.url):
            try:
                page.go_back(wait_until="domcontentloaded", timeout=7000)
                page.wait_for_timeout(500)
                if _wait_until_left_success_url(page, timeout_ms=2500):
                    action = "go_back"
            except Exception:
                pass

        if _is_success_url(page.url):
            try:
                page.goto(return_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(500)
                if _wait_until_left_success_url(page, timeout_ms=2500):
                    action = "goto_return_url"
            except Exception as e:
                return False, f"не удалось вернуться на главную ({e})"

        if _is_success_url(page.url):
            return False, f"после action={action} остались на Thanks ({page.url})"

        expected_host = (urlsplit(return_url).netloc or "").lower()
        current_host = (urlsplit(page.url).netloc or "").lower()
        if expected_host and current_host and expected_host != current_host:
            return False, f"возврат на другой хост ({current_host} вместо {expected_host})"

        expected_path = (urlsplit(return_url).path or "").rstrip("/")
        current_path = (urlsplit(page.url).path or "").rstrip("/")
        if expected_path and expected_path != "/" and not current_path.startswith(expected_path):
            return False, f"возврат на другой путь ({current_path} вместо {expected_path})"

        region_sel = detect_visible_region_popup(page)
        if region_sel:
            return False, f"после возврата виден region-popup ({region_sel})"

        print(f"  [THANKS] ✅ Возврат на главную подтверждён ({action})")
        return True, action


# ---------------------------------------------------------------------------
# Подсказки
# ---------------------------------------------------------------------------

def choose_first_suggestion(page: Page, timeout_ms: int = 1500) -> bool:
    poll_ms = 150
    elapsed = 0
    while elapsed < timeout_ms:
        for sel in SUGGESTION_SELECTORS:
            loc = page.locator(sel)
            for i in range(loc.count()):
                item = loc.nth(i)
                try:
                    if item.is_visible() and (item.inner_text() or "").strip():
                        print(f"  [SUGGEST] '{item.inner_text().strip()[:50]}'")
                        item.click(timeout=3000, force=True)
                        page.wait_for_timeout(300)
                        return True
                except Exception:
                    pass
        page.wait_for_timeout(poll_ms)
        elapsed += poll_ms

    print("  [SUGGEST FALLBACK] ArrowDown+Enter")
    try:
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(200)
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        return True
    except Exception:
        return False


def _service_place_locator(container, service_value: str):
    return container.locator(f"input[name='Place'][value='{service_value}']")


def detect_service_place_values(container) -> list[str]:
    values = []
    for service_value in SERVICE_PLACE_VALUES:
        try:
            if _service_place_locator(container, service_value).count() > 0:
                values.append(service_value)
        except Exception:
            pass
    return values


def resolve_service_values_for_mode(
    form_type: str,
    detected_service_values: list[str],
    service_mode: str,
) -> list[str | None]:
    mode = normalize_service_mode(service_mode)

    if mode == SERVICE_MODE_VARIANTS:
        if form_type in ("profit", "business"):
            print("  [FORM] VARIANTS: тип формы без Place — пропускаем")
            return []
        if detected_service_values:
            print(f"  [FORM] VARIANTS: submit по Place: {', '.join(detected_service_values)}")
            return detected_service_values
        print("  [FORM] VARIANTS: Place не найден — пропускаем")
        return []

    if form_type in ("profit", "business"):
        return [None]

    if not detected_service_values:
        print("  [FORM] Варианты услуги Place не обнаружены — submit без переключения")
        return [None]

    if mode == SERVICE_MODE_CORE:
        primary_value = detected_service_values[0]
        print(f"  [FORM] CORE: используем базовый вариант услуги: {primary_value}")
        return [primary_value]

    print(f"  [FORM] Найдены варианты услуги: {', '.join(detected_service_values)}")
    return detected_service_values


def select_service_place_value(container, service_value: str) -> bool:
    options = _service_place_locator(container, service_value)
    try:
        count = options.count()
    except Exception:
        count = 0
    if count == 0:
        print(f"  [FORM] Вариант услуги не найден: {service_value}")
        return False

    for idx in range(count):
        option = options.nth(idx)
        try:
            option.check(force=True)
            print(f"  [FORM] Вариант услуги выбран: {service_value}")
            return True
        except Exception:
            try:
                option.click(force=True)
                print(f"  [FORM] Вариант услуги выбран (click): {service_value}")
                return True
            except Exception:
                pass
    print(f"  [FORM] Не удалось выбрать вариант услуги: {service_value}")
    return False


def apply_form_checkboxes(container):
    """
    Ставит только ограниченное число видимых чекбоксов.
    Это защищает от длинных/залипающих циклов в формах с большим количеством hidden checkbox.
    """
    checkboxes = container.locator("input[type='checkbox']")
    try:
        total = checkboxes.count()
    except Exception:
        total = 0

    if total <= 0:
        return

    scan_total = min(total, CHECKBOX_SCAN_LIMIT)
    checked_total = 0
    print(
        f"  [FORM] Checkbox scan: total={total}, scan_limit={scan_total}, "
        f"check_limit={CHECKBOX_CHECK_LIMIT}"
    )

    for idx in range(scan_total):
        if checked_total >= CHECKBOX_CHECK_LIMIT:
            print(f"  [FORM] Checkbox check limit reached: {checked_total}")
            break

        cb = checkboxes.nth(idx)
        try:
            if not cb.is_visible(timeout=CHECKBOX_VISIBILITY_TIMEOUT_MS):
                continue
        except Exception:
            continue

        try:
            if cb.is_checked():
                continue
        except Exception:
            pass

        try:
            cb.check(force=True, timeout=CHECKBOX_ACTION_TIMEOUT_MS)
            checked_total += 1
        except Exception as e:
            err = str(e).replace("\n", " ")[:160]
            print(f"  [FORM] Checkbox skip #{idx + 1}: {err}")

    print(f"  [FORM] Checkbox checked: {checked_total}")


# ---------------------------------------------------------------------------
# Заполнение формы
# ---------------------------------------------------------------------------

def fill_form(page: Page, container, form_type: str,
              has_name_field: bool = False,
              service_place_value: str | None = None) -> bool:
    cfg        = FORM_CONFIGS[form_type]
    no_house   = cfg.get("no_house", False)
    no_suggest = cfg.get("no_suggest", False)

    if service_place_value:
        if not select_service_place_value(container, service_place_value):
            return False

    def fill_street_and_pick() -> bool:
        street_local = container.locator(cfg["street"]).first
        if street_local.count() == 0 or not street_local.is_visible():
            print(f"  [FORM] Address field not found ({cfg['street']})")
            return False

        street_local.scroll_into_view_if_needed()
        street_local.click(force=True)
        try:
            street_local.fill("")
        except Exception:
            pass
        street_local.fill("\u041b\u0435\u043d\u0438\u043d\u0430")

        if no_suggest:
            print("  [FORM] Address entered (no suggestion)")
            return True

        print("  [FORM] Street entered, waiting suggestion...")
        choose_first_suggestion(page)
        return True

    # Address / Street
    if not fill_street_and_pick():
        return False

    # House
    if no_house:
        print("  [FORM] House field skipped")
    else:
        house_sel = cfg.get("house")
        if house_sel:
            house_ready = False

            for house_attempt in range(1, 3):
                house = container.locator(house_sel).first
                if house.count() == 0 or not house.is_visible():
                    print(f"  [FORM] House field not found/visible ({house_sel}) | attempt {house_attempt}/2")
                else:
                    print(f"  [FORM] Waiting house field enable... attempt {house_attempt}/2")
                    try:
                        expect(house).to_be_enabled(timeout=HOUSE_ENABLE_TIMEOUT_MS)
                        house.scroll_into_view_if_needed()
                        house.click(force=True)
                        house.fill("1")
                        print("  [FORM] House entered, waiting suggestion...")
                        choose_first_suggestion(page, timeout_ms=1500)
                        house_ready = True
                        break
                    except Exception as e:
                        print(f"  [FORM] House field did not activate: {e}")

                if house_attempt == 1:
                    print("  [FORM] Retry with full refill...")
                    if not fill_street_and_pick():
                        print("  [FORM] Retry failed: address could not be refilled")
                        return False

            if not house_ready:
                print("  [FORM] House field did not activate after retry; mark form as not filled")
                return False

    # Имя (только для RTK-сайтов, has_name_field=True)
    if has_name_field:
        # Поле Имя — ищем по placeholder или name атрибуту
        name_inp = None
        for sel in ['input[name="Name"]', 'input[name="name"]',
                    'input[placeholder*="мя"]', 'input[placeholder*="ame"]']:
            candidate = container.locator(sel).first
            try:
                if candidate.count() > 0 and candidate.is_visible():
                    name_inp = candidate
                    break
            except Exception:
                pass
        if name_inp is not None:
            name_inp.scroll_into_view_if_needed()
            name_inp.click(force=True)
            name_inp.fill("Тестер")
            print("  [FORM] Имя введено: Тестер")
        else:
            print("  [FORM] ⚠️  Поле Имя не найдено (has_name_field=True)")

    # Телефон (обязательное)
    phone = container.locator(cfg["phone"]).first
    if phone.count() == 0 or not phone.is_visible():
        print(f"  [FORM] ❌ Телефон не найден ({cfg['phone']})")
        return False

    phone.scroll_into_view_if_needed()
    phone.click(force=True)
    phone.press_sequentially("1111111111", delay=50)
    print("  [FORM] Телефон введён")

    apply_form_checkboxes(container)

    return True


def find_submit(container, form_type: str):
    cfg    = FORM_CONFIGS[form_type]
    submit = container.locator(cfg["submit"]).first
    try:
        if submit.count() > 0 and submit.is_visible() and submit.is_enabled():
            print(f"  [SUBMIT] Найдена '{cfg['submit']}'")
            return submit
    except Exception:
        pass
    print(f"  [SUBMIT] ❌ Не найдена '{cfg['submit']}'")
    return None


def submit_with_confirmation(
    page: Page,
    container,
    form_type: str,
    timeout_ms: int = SUBMIT_CONFIRM_TIMEOUT_MS,
    attempts: int = 2,
) -> bool:
    """
    Пытается отправить форму и дождаться подтверждения.
    Делает повторную попытку submit при редких флаках no_confirmation.
    """
    last_submit = find_submit(container, form_type)
    if last_submit is None:
        return False

    for attempt in range(1, attempts + 1):
        try:
            last_submit.scroll_into_view_if_needed()
            last_submit.click(force=True)
        except Exception:
            # Форма могла перерендериться — пробуем найти submit снова
            last_submit = find_submit(container, form_type)
            if last_submit is None:
                return False
            last_submit.scroll_into_view_if_needed()
            last_submit.click(force=True)

        ok = wait_for_success_url(page, timeout_ms=timeout_ms)
        if ok:
            return True

        if attempt < attempts:
            print(f"  [SUBMIT] Повторная попытка {attempt + 1}/{attempts}")
            page.wait_for_timeout(1200)

    return False


# ---------------------------------------------------------------------------
# Ожидание попапа
# ---------------------------------------------------------------------------

def wait_for_popup_with_fields(page: Page, timeout_ms: int = 10_000,
                                form_hint=None):
    form_types_to_check = (
        [(form_hint, FORM_CONFIGS[form_hint])]
        if form_hint and form_hint in FORM_CONFIGS
        else list(FORM_CONFIGS.items())
    )
    poll_ms = 300
    elapsed = 0

    while elapsed < timeout_ms:
        for popup_sel in POPUP_CONTAINER_SELECTORS:
            for form_type, cfg in form_types_to_check:
                containers = page.locator(popup_sel)
                for i in range(containers.count()):
                    container = containers.nth(i)
                    try:
                        if not container.is_visible():
                            continue
                        phone = container.locator(cfg["phone"]).first
                        if phone.count() > 0 and phone.is_visible():
                            print(f"  [POPUP] sel='{popup_sel}' type='{form_type}'")
                            return form_type, container
                    except Exception:
                        pass

        for form_type, cfg in form_types_to_check:
            phone_fields = page.locator(cfg["phone"])
            for i in range(phone_fields.count()):
                phone = phone_fields.nth(i)
                try:
                    if not phone.is_visible():
                        continue
                    parent = phone.locator(
                        "xpath=ancestor::div[contains(@class,'popup') or "
                        "contains(@class,'modal') or contains(@id,'popup')]"
                    ).last
                    if parent.count() > 0 and parent.is_visible():
                        print(f"  [POPUP] ancestor type='{form_type}'")
                        return form_type, parent
                    form_parent = phone.locator("xpath=ancestor::form").last
                    if form_parent.count() > 0 and form_parent.is_visible():
                        print(f"  [POPUP] form-ancestor type='{form_type}'")
                        return form_type, form_parent
                except Exception:
                    pass

        page.wait_for_timeout(poll_ms)
        elapsed += poll_ms

    print(f"  [POPUP] ❌ Попап не появился за {timeout_ms // 1000}с")
    return None, None


# ---------------------------------------------------------------------------
# Сбор кнопок
# ---------------------------------------------------------------------------

def collect_popup_buttons(page: Page) -> list:
    """Все кнопки попапов: по ключевым словам + по CSS-классам из POPUP_BUTTON_CLASSES."""
    all_btns = page.locator("button")
    total    = all_btns.count()
    result   = []
    seen_idx = set()

    print(f"\n[COLLECT] Кнопок на странице: {total}")

    # По ключевым словам (connection и др.)
    for i in range(total):
        btn = all_btns.nth(i)
        try:
            if not btn.is_visible() or not btn.is_enabled():
                continue
            text = (btn.inner_text() or "").strip().lower()
            if not any(kw in text for kw in POPUP_OPEN_KEYWORDS):
                continue
            if any(kw in text for kw in POPUP_SKIP_KEYWORDS):
                continue
            seen_idx.add(i)
            result.append({"index": i, "text": text, "form_hint": None, "css": None})
            print(f"  [COLLECT] #{len(result)} index={i} '{text}'")
        except Exception:
            pass

    # По CSS-классам (profit, express-connection)
    for form_hint, css_class in POPUP_BUTTON_CLASSES.items():
        if form_hint == "business":
            continue   # бизнес собирается отдельно
        btns = page.locator(css_class)
        for i in range(btns.count()):
            btn = btns.nth(i)
            try:
                if not btn.is_visible() or not btn.is_enabled():
                    continue
                global_idx = btn.evaluate(
                    "el => Array.from(document.querySelectorAll('button')).indexOf(el)"
                )
                if global_idx in seen_idx:
                    continue
                seen_idx.add(global_idx)
                text = (btn.inner_text() or "").strip().lower()
                result.append({"index": global_idx, "text": text,
                               "form_hint": form_hint, "css": css_class})
                print(f"  [COLLECT] #{len(result)} index={global_idx} "
                      f"'{text}' ({form_hint})")
            except Exception:
                pass

    print(f"[COLLECT] Итого: {len(result)}\n")
    return result


def collect_business_buttons(page: Page) -> list:
    btns   = page.locator(POPUP_BUTTON_CLASSES["business"])
    total  = btns.count()
    result = []
    print(f"\n[BUSINESS COLLECT] Элементов: {total}")
    for i in range(total):
        btn = btns.nth(i)
        try:
            if not btn.is_visible() or not btn.is_enabled():
                continue
            text = (btn.inner_text() or "").strip().lower()
            tag  = btn.evaluate("el => el.tagName.toLowerCase()")
            result.append({"nth": i, "text": text, "tag": tag})
            print(f"  [BUSINESS COLLECT] #{len(result)} nth={i} <{tag}> '{text}'")
        except Exception:
            pass
    print(f"[BUSINESS COLLECT] Итого: {len(result)}\n")
    return result


# ---------------------------------------------------------------------------
# Универсальный цикл попапов
# ---------------------------------------------------------------------------

def dismiss_profit_popup(page: Page):
    """
    Закрывает автоматически всплывший попап 'Выгодное спецпредложение'
    если он появился сам (мешает другим шагам).
    Не заполняет форму — просто закрывает. Безопасно вызывать в любой момент.
    """
    try:
        phone = page.locator(FORM_CONFIGS["profit"]["phone"]).first
        if phone.count() == 0 or not phone.is_visible():
            return
        for close_sel in [
            ".popup__close", ".fancybox-close-small", ".modal__close",
            "[aria-label*='close']", "[aria-label*='закры']",
        ]:
            btn = page.locator(close_sel).first
            if btn.count() > 0 and btn.is_visible():
                btn.click(force=True)
                page.wait_for_timeout(300)
                print("  [PROFIT] Автоматический profit-попап закрыт")
                return
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        print("  [PROFIT] Profit-попап закрыт (Escape)")
    except Exception:
        pass


def process_auto_profit_popup(
    page: Page,
    base_url: str,
    has_name_field: bool = False,
    service_mode: str = SERVICE_MODE_ALL,
) -> tuple[int, int, str | None, bool]:
    """
    Проверяет автопоявляющийся profit-попап как полноценную форму:
    fill -> submit -> confirm.

    Возвращает:
      success, failed, first_fail, auto_popup_tested
    """
    site_label = base_url.replace("https://", "").replace("http://", "").strip("/")
    sep = "=" * 55
    print(f"\n{sep}\n[AUTO-PROFIT] Проверка автопопапа\n{sep}")

    if normalize_service_mode(service_mode) == SERVICE_MODE_VARIANTS:
        print("  [AUTO-PROFIT] VARIANTS-режим: автопопап не проверяем")
        return 0, 0, None, False

    nav_ok, nav_critical, nav_reason = safe_goto(page, base_url)
    if not nav_ok:
        if nav_critical:
            raise SiteUnavailableError(
                f"AUTO-PROFIT: сайт недоступен ({base_url}) | {nav_reason}"
            )
        log_error("navigation_failed", page, site_label, extra=nav_reason[:180])
        first_fail = f"AUTO-PROFIT code=navigation_failed | {nav_reason[:180]}"
        return 0, 1, first_fail[:220], False

    # Для корректного ожидания авто-попапа закрываем только region/cookie.
    dismiss_region_popup(page)
    accept_cookie_banner(page)

    form_type, container = wait_for_popup_with_fields(timeout_ms=12_000, page=page, form_hint="profit")
    if form_type is None:
        print("  [AUTO-PROFIT] Автопопап не появился — продолжаем обычный цикл")
        allure.attach(
            "Автопопап profit не появился за 12с. Сценарий пропущен как неприменимый.",
            name=f"AUTO-PROFIT skip ({site_label})",
            attachment_type=allure.attachment_type.TEXT,
        )
        return 0, 0, None, False

    print("  [AUTO-PROFIT] Попап появился автоматически, запускаем полный submit-сценарий")
    if not fill_form(page, container, form_type, has_name_field=has_name_field):
        log_error("form_not_filled", page, site_label, extra="auto profit popup")
        return 0, 1, "AUTO-PROFIT code=form_not_filled"[:220], True

    submit = find_submit(container, form_type)
    if submit is None:
        log_error("submit_not_found", page, site_label, extra="auto profit popup")
        return 0, 1, "AUTO-PROFIT code=submit_not_found"[:220], True

    if REALLY_SUBMIT:
        return_url_before_submit = page.url or base_url
        ok = submit_with_confirmation(
            page,
            container,
            form_type,
            timeout_ms=SUBMIT_CONFIRM_TIMEOUT_MS,
            attempts=2,
        )
        if ok:
            print("  [AUTO-PROFIT] ✅ Заявка принята")
            thanks_ok, thanks_reason = verify_thanks_close_and_return(page, return_url_before_submit)
            if not thanks_ok:
                log_error("thanks_return_failed", page, site_label, extra=f"auto profit popup | {thanks_reason}")
                return 0, 1, "AUTO-PROFIT code=thanks_return_failed"[:220], True
            return 1, 0, None, True

        log_error("no_confirmation", page, site_label, extra="auto profit popup")
        return 0, 1, "AUTO-PROFIT code=no_confirmation"[:220], True

    print("  [AUTO-PROFIT] ✅ Форма готова (REALLY_SUBMIT=False)")
    close_popup_or_page(page)
    return 1, 0, None, True


def process_unexpected_auto_profit_popup(
    page: Page,
    base_url: str,
    has_name_field: bool = False,
    context: str = "",
) -> tuple[bool, bool, str]:
    """
    Подстраховка: если auto-profit всплыл во время проверки другой формы,
    отправляем его и возвращаемся к исходному сценарию.

    Возвращает:
      handled, ok, fail_code
    """
    site_label = base_url.replace("https://", "").replace("http://", "").strip("/")
    form_type, container = wait_for_popup_with_fields(
        page=page, timeout_ms=2_000, form_hint="profit"
    )
    if form_type is None:
        return False, True, ""

    print(f"  [AUTO-PROFIT] Неожиданное появление во время '{context}' — обрабатываем")
    if not fill_form(page, container, form_type, has_name_field=has_name_field):
        log_error("form_not_filled", page, site_label, extra=f"auto profit during {context}")
        return True, False, "form_not_filled"

    submit = find_submit(container, form_type)
    if submit is None:
        log_error("submit_not_found", page, site_label, extra=f"auto profit during {context}")
        return True, False, "submit_not_found"

    if REALLY_SUBMIT:
        return_url_before_submit = page.url or base_url
        ok = submit_with_confirmation(
            page, container, form_type,
            timeout_ms=SUBMIT_CONFIRM_TIMEOUT_MS, attempts=2
        )
        if not ok:
            log_error("no_confirmation", page, site_label, extra=f"auto profit during {context}")
            return True, False, "no_confirmation"
        thanks_ok, thanks_reason = verify_thanks_close_and_return(page, return_url_before_submit)
        if not thanks_ok:
            log_error("thanks_return_failed", page, site_label, extra=f"auto profit during {context} | {thanks_reason}")
            return True, False, "thanks_return_failed"
        return True, True, ""

    close_popup_or_page(page)
    return True, True, ""


def _run_popup_cycle(page: Page, buttons: list, base_url: str,
                     btn_locator_fn, label: str = "POPUP",
                     has_name_field: bool = False,
                     service_mode: str = SERVICE_MODE_ALL) -> tuple[int, int, str | None]:
    success    = 0
    failed     = 0
    first_fail = None
    fail_details = []
    site_label = base_url.replace("https://", "").replace("http://", "").strip("/")

    for num, entry in enumerate(buttons, 1):
        text      = entry.get("text", "")
        form_hint = entry.get("form_hint")
        sep       = "=" * 55
        print(f"\n{sep}\n[{label} {num}/{len(buttons)}] '{text}' hint={form_hint}\n{sep}")

        def register_failure(code: str, details: str = ""):
            nonlocal failed, first_fail
            failed += 1
            current_url = ""
            try:
                current_url = page.url
            except Exception:
                current_url = "n/a"
            entry_line = (
                f"{label} {num}/{len(buttons)} text='{text}' hint={form_hint} "
                f"code={code} url={current_url}"
            )
            if details:
                entry_line += f" | {details}"
            fail_details.append(entry_line[:600])
            if first_fail is None:
                first_fail = entry_line[:220]
            print(f"  [FAIL-DETAIL] {entry_line}")

        def recover_from_unexpected_profit(current_context: str) -> str:
            # Когда целевая форма сама profit — это не "неожиданное" появление.
            if form_hint == "profit":
                return "none"

            handled, ok, fail_code = process_unexpected_auto_profit_popup(
                page,
                base_url,
                has_name_field=has_name_field,
                context=current_context,
            )
            if not handled:
                return "none"
            if not ok:
                register_failure(fail_code or "auto_profit_failed", f"context={current_context}")
                return "failed"

            # Возобновляем исходный сценарий: повторно открываем целевую форму.
            try:
                retry_btn = btn_locator_fn(page, entry)
                retry_btn.scroll_into_view_if_needed()
                retry_btn.click(force=True)
                page.wait_for_timeout(500)
                print(f"  [{label}] Возобновляем проверку после AUTO-PROFIT")
                return "reopened"
            except Exception as e:
                err = str(e).replace("\n", " ")[:180]
                log_error("click_failed", page, site_label, extra=f"reopen after auto-profit | {err}")
                register_failure("click_failed", f"reopen after auto-profit | {err}")
                return "failed"

        def reopen_target_popup(current_context: str):
            nav_ok_local, nav_critical_local, nav_reason_local = safe_goto(page, base_url)
            if not nav_ok_local:
                if nav_critical_local:
                    raise SiteUnavailableError(
                        f"{label}: сайт недоступен при повторном открытии формы ({base_url}) | {nav_reason_local}"
                    )
                log_error("navigation_failed", page, site_label, extra=nav_reason_local[:180])
                register_failure("navigation_failed", f"{current_context} | {nav_reason_local[:180]}")
                return None, None, "failed"

            accept_cookie_banner(page)
            try:
                retry_btn = btn_locator_fn(page, entry)
                retry_btn.scroll_into_view_if_needed()
                retry_btn.click(force=True)
                page.wait_for_timeout(500)
            except Exception as e:
                err = str(e).replace("\n", " ")[:180]
                log_error("click_failed", page, site_label, extra=f"{current_context} | {err}")
                register_failure("click_failed", f"{current_context} | {err}")
                return None, None, "failed"

            reopened_form_type, reopened_container = wait_for_popup_with_fields(page, form_hint=form_hint)
            if reopened_form_type is None:
                recover_status_local = recover_from_unexpected_profit(
                    f"{current_context}: ожидание целевого попапа"
                )
                if recover_status_local == "reopened":
                    reopened_form_type, reopened_container = wait_for_popup_with_fields(
                        page, form_hint=form_hint
                    )
                elif recover_status_local == "failed":
                    return None, None, "failed"

            if reopened_form_type is None:
                log_error("popup_not_found", page, site_label, extra=current_context)
                register_failure("popup_not_found", current_context)
                return None, None, "failed"

            return reopened_form_type, reopened_container, "ok"

        nav_ok, nav_critical, nav_reason = safe_goto(page, base_url)
        if not nav_ok:
            if nav_critical:
                raise SiteUnavailableError(
                    f"{label}: сайт недоступен на этапе {num}/{len(buttons)} ({base_url}) | {nav_reason}"
                )
            log_error("navigation_failed", page, site_label, extra=nav_reason[:180])
            register_failure("navigation_failed", nav_reason[:180])
            continue
        accept_cookie_banner(page)

        try:
            btn = btn_locator_fn(page, entry)
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            page.wait_for_timeout(500)
        except Exception as e:
            log_error("click_failed", page, site_label, extra=str(e)[:150])
            register_failure("click_failed", str(e).replace("\n", " ")[:180])
            continue

        form_type, container = wait_for_popup_with_fields(page, form_hint=form_hint)
        if form_type is None:
            recover_status = recover_from_unexpected_profit("ожидание целевого попапа")
            if recover_status == "reopened":
                form_type, container = wait_for_popup_with_fields(page, form_hint=form_hint)
            elif recover_status == "failed":
                continue
        if form_type is None:
            log_error("popup_not_found", page, site_label)
            register_failure("popup_not_found")
            continue

        detected_service_values = []
        if form_type not in ("profit", "business"):
            detected_service_values = detect_service_place_values(container)

        service_values = resolve_service_values_for_mode(
            form_type=form_type,
            detected_service_values=detected_service_values,
            service_mode=service_mode,
        )
        if not service_values:
            print(f"  [{label}] Пропуск формы: нет применимых вариантов для режима '{service_mode}'")
            continue

        for service_idx, service_value in enumerate(service_values, start=1):
            service_label = service_value if service_value else "без выбора варианта"
            print(
                f"  [{label}] Вариант submit {service_idx}/{len(service_values)}: {service_label}"
            )

            if not fill_form(
                page,
                container,
                form_type,
                has_name_field=has_name_field,
                service_place_value=service_value,
            ):
                recover_status = recover_from_unexpected_profit(
                    f"заполнение целевой формы ({service_label})"
                )
                if recover_status == "reopened":
                    form_type, container = wait_for_popup_with_fields(page, form_hint=form_hint)
                    if form_type is None:
                        log_error("popup_not_found", page, site_label, extra="after auto-profit recovery")
                        register_failure("popup_not_found", f"after auto-profit recovery | service={service_label}")
                        continue
                    if fill_form(
                        page,
                        container,
                        form_type,
                        has_name_field=has_name_field,
                        service_place_value=service_value,
                    ):
                        pass
                    else:
                        log_error("form_not_filled", page, site_label, extra=f"service={service_label}")
                        register_failure("form_not_filled", f"service={service_label}")
                        continue
                elif recover_status == "failed":
                    continue
                else:
                    log_error("form_not_filled", page, site_label, extra=f"service={service_label}")
                    register_failure("form_not_filled", f"service={service_label}")
                    continue

            submit = find_submit(container, form_type)
            if submit is None:
                recover_status = recover_from_unexpected_profit(
                    f"поиск submit в целевой форме ({service_label})"
                )
                if recover_status == "reopened":
                    form_type, container = wait_for_popup_with_fields(page, form_hint=form_hint)
                    if form_type is None:
                        log_error("popup_not_found", page, site_label, extra="after auto-profit recovery")
                        register_failure("popup_not_found", f"after auto-profit recovery | service={service_label}")
                        continue
                    submit = find_submit(container, form_type)
                    if submit is None:
                        log_error("submit_not_found", page, site_label, extra=f"service={service_label}")
                        register_failure("submit_not_found", f"service={service_label}")
                        continue
                elif recover_status == "failed":
                    continue
                else:
                    log_error("submit_not_found", page, site_label, extra=f"service={service_label}")
                    register_failure("submit_not_found", f"service={service_label}")
                    continue

            submit.scroll_into_view_if_needed()

            if REALLY_SUBMIT:
                return_url_before_submit = page.url or base_url
                ok = submit_with_confirmation(
                    page, container, form_type,
                    timeout_ms=SUBMIT_CONFIRM_TIMEOUT_MS, attempts=2
                )
                if ok:
                    print(f"  [{label}] ✅ Заявка принята ({service_label})")
                    thanks_ok, thanks_reason = verify_thanks_close_and_return(
                        page, return_url_before_submit
                    )
                    if not thanks_ok:
                        log_error(
                            "thanks_return_failed",
                            page,
                            site_label,
                            extra=f"service={service_label} | {thanks_reason}",
                        )
                        register_failure("thanks_return_failed", f"service={service_label} | {thanks_reason}")
                        continue
                    success += 1
                else:
                    log_error("no_confirmation", page, site_label, extra=f"service={service_label}")
                    register_failure("no_confirmation", f"service={service_label}")
                    continue
            else:
                print(f"  [{label}] ✅ Форма готова (REALLY_SUBMIT=False, {service_label})")
                close_popup_or_page(page)
                success += 1

            if service_idx < len(service_values):
                form_type, container, reopen_status = reopen_target_popup(
                    f"переоткрытие формы для варианта услуги ({service_label})"
                )
                if reopen_status != "ok":
                    break

    if fail_details:
        allure.attach(
            "\n".join(fail_details),
            name=f"{label} failure details ({site_label})",
            attachment_type=allure.attachment_type.TEXT,
        )

    sep = "=" * 55
    total_attempts = success + failed
    print(
        f"\n{sep}\n[{label} RESULT] ✅ {success}  ❌ {failed}  "
        f"Submit-попыток: {total_attempts}\n{sep}\n"
    )
    return success, failed, first_fail


def process_all_popups(page: Page, base_url: str,
                        has_name_field: bool = False,
                        service_mode: str = SERVICE_MODE_ALL) -> tuple[int, int, str | None]:
    auto_success, auto_failed, auto_first_fail, auto_tested = process_auto_profit_popup(
        page, base_url, has_name_field=has_name_field, service_mode=service_mode
    )

    buttons = collect_popup_buttons(page)
    if auto_tested and buttons:
        before = len(buttons)
        buttons = [b for b in buttons if b.get("form_hint") != "profit"]
        removed = before - len(buttons)
        if removed > 0:
            print(f"[POPUP] AUTO-PROFIT уже проверен, исключено profit-кнопок: {removed}")

    if not buttons:
        print("[POPUP] Кнопки не найдены — пропускаем")
        return auto_success, auto_failed, auto_first_fail

    def locate(page, entry):
        css = entry.get("css")
        if css:
            return page.locator(css).first
        return page.locator("button").nth(entry["index"])

    success, failed, first_fail = _run_popup_cycle(
        page, buttons, base_url, locate, label="POPUP",
        has_name_field=has_name_field, service_mode=service_mode
    )
    total_success = auto_success + success
    total_failed = auto_failed + failed
    total_first_fail = auto_first_fail if auto_first_fail else first_fail
    return total_success, total_failed, total_first_fail


def process_business_popups(page: Page, base_url: str,
                             has_name_field: bool = False,
                             service_mode: str = SERVICE_MODE_ALL) -> tuple[int, int, str | None]:
    if normalize_service_mode(service_mode) == SERVICE_MODE_VARIANTS:
        print("[BUSINESS] VARIANTS-режим: шаг /business пропущен")
        return 0, 0, None

    buttons = collect_business_buttons(page)
    if not buttons:
        print("[BUSINESS] Кнопки не найдены — пропускаем")
        return 0, 0, None

    def locate(page, entry):
        return page.locator(POPUP_BUTTON_CLASSES["business"]).nth(entry["nth"])

    return _run_popup_cycle(
        page, buttons, base_url, locate, label="BUSINESS",
        has_name_field=has_name_field, service_mode=service_mode
    )


# ---------------------------------------------------------------------------
# Выбор города
# ---------------------------------------------------------------------------

def run_city_scenario(page: Page, base_url: str, city_name: str) -> tuple[str | None, str | None]:
    """
    Открывает попап выбора города, кликает на нужный город,
    возвращает (city_base_url, city_business_url).
    Поддерживает все варианты вёрстки из набора локаторов RegionChoice.
    """
    sep = "=" * 55
    print(f"\n{sep}\n[CITY] Выбор города '{city_name}'\n{sep}")

    nav_ok, nav_critical, nav_reason = safe_goto(page, base_url)
    if not nav_ok:
        if nav_critical:
            raise SiteUnavailableError(f"CITY: не удалось открыть {base_url} | {nav_reason}")
        log_error("navigation_failed", page,
                  base_url.replace("https://", "").replace("http://", "").strip("/"),
                  extra=nav_reason[:180])
        return None, None
    close_overlays(page)

    # Все известные варианты кнопки открытия попапа города
    CITY_BUTTON_SELECTORS = [
        "xpath=(//span[@id='city'])[1]",
        "xpath=(//span[@id='city'])[2]",
        "xpath=(//span[@id='city'])[3]",
        "xpath=(//a[@id='city'])[1]",
        "xpath=(//a[@id='city'])[2]",
        "xpath=(//a[@id='city'])[3]",
        "xpath=(//a[@class='city'])[2]",
        "xpath=//div[@class='header__wrapper-middle']//span[@id='city']",
        "xpath=(//button[@id='noButton'])[1]",
        "xpath=(//button[contains(@class,'popup-select-region__button') and contains(@class,'city')])[1]",
        ".region-search__button.button.button-red",
        ".region-search__button.button.button-green",
        "button.region-search__button",
        "button:has-text('Выбрать город')",
        "a.header__city.city",
        "a.header__city",
        "#city",
        "span#city",
        "a#city",
        "[class*='header'][class*='city']",
        "xpath=//div[@class='footer__city']//a",
    ]

    city_btn = None
    city_btn_sel = None
    city_btn_idx = None
    for sel in CITY_BUTTON_SELECTORS:
        try:
            loc = page.locator(sel)
            for i in range(loc.count()):
                candidate = loc.nth(i)
                try:
                    if candidate.is_visible():
                        city_btn = candidate
                        city_btn_sel = sel
                        city_btn_idx = i
                        print(f"  [CITY] Кнопка найдена (visible): '{sel}' idx={i}")
                        break
                except Exception:
                    pass
            if city_btn is not None:
                break
        except Exception:
            pass

    if city_btn is None or city_btn_sel is None or city_btn_idx is None:
        print("  [CITY] ❌ Кнопка выбора города не найдена — шаг пропущен")
        return None, None

    city_btn_clicked = False
    for attempt in range(1, 4):
        try:
            city_btn = page.locator(city_btn_sel).nth(city_btn_idx)
            city_btn.scroll_into_view_if_needed()
            city_btn.click(timeout=4000, force=True)
            city_btn_clicked = True
            break
        except Exception as e:
            print(f"  [CITY] Попытка клика {attempt}/3 не удалась: {e}")
            page.wait_for_timeout(500)

    if not city_btn_clicked:
        log_error(
            "click_failed", page,
            base_url.replace("https://", "").replace("http://", "").strip("/"),
            extra=f"city button click failed sel={city_btn_sel}"
        )
        return None, None

    page.wait_for_timeout(800)

    # Все известные варианты поля поиска города
    CITY_INPUT_SELECTORS = [
        "xpath=//input[@placeholder='Введите название города']",
        "xpath=//input[@id='city-input']",
        "xpath=//input[@placeholder='Поиск города']",
        "xpath=//input[@placeholder='Город']",
        "input[name='city']",
        "input[placeholder*='оиск']",
        "input[placeholder*='ород']",
        "input[type='search']",
    ]

    city_input_filled = False
    for sel in CITY_INPUT_SELECTORS:
        if city_input_filled:
            break
        try:
            inputs = page.locator(sel)
            for i in range(inputs.count()):
                inp = inputs.nth(i)
                try:
                    if not inp.is_visible():
                        continue
                    inp.click(force=True)
                    inp.fill(city_name)
                    page.wait_for_timeout(500)
                    print(f"  [CITY] Введено '{city_name}' в поле поиска ({sel}, idx={i})")
                    city_input_filled = True
                    break
                except Exception:
                    pass
        except Exception:
            pass

    # Все известные варианты списка городов
    CITY_LINK_SELECTORS = [
        "xpath=(//a[@class='region_item region_link'])",
        "xpath=//a[@class='region_item']",
        "xpath=//div[@class='city-coverage__capital']//a",
        "xpath=(//table[@class='city_list']//tbody//tr//td//a)",
        ".region_item.region_link",
        ".region_item",
    ]

    link = None
    for sel in CITY_LINK_SELECTORS:
        if link is not None:
            break
        try:
            locs = page.locator(sel).filter(has_text=city_name)
            for i in range(locs.count()):
                candidate = locs.nth(i)
                try:
                    candidate.wait_for(state="attached", timeout=3000)
                except Exception:
                    pass
                try:
                    if not candidate.is_visible():
                        continue
                    link = candidate
                    print(f"  [CITY] Город '{city_name}' найден: '{sel}' idx={i}")
                    break
                except Exception:
                    pass
        except Exception:
            pass

    if link is None or link.count() == 0:
        log_error("city_not_found", page,
                  base_url.replace("https://","").replace("http://","").strip("/"),
                  extra=f"city={city_name}")
        return None, None

    old_url = page.url
    city_link_clicked = False
    for attempt in range(1, 4):
        # Антифлак: если URL уже сменился, считаем выбор города успешным.
        if page.url != old_url:
            city_link_clicked = True
            print("  [CITY] URL уже сменился до повторного клика — считаем выбор успешным")
            break
        try:
            link.scroll_into_view_if_needed()
            link.click(timeout=4000, force=True)
            city_link_clicked = True
            break
        except Exception as e:
            print(f"  [CITY] Клик по городу, попытка {attempt}/3: {e}")
            page.wait_for_timeout(500)
            # Антифлак: click мог сработать, но Playwright выбросил timeout
            # при ожидании завершения навигации.
            if page.url != old_url:
                city_link_clicked = True
                print("  [CITY] После исключения URL сменился — считаем выбор успешным")
                break

    if not city_link_clicked:
        log_error("click_failed", page,
                  base_url.replace("https://","").replace("http://","").strip("/"),
                  extra=f"city link click failed city={city_name}")
        return None, None

    print(f"  [CITY] Клик по '{city_name}'")

    city_base_url = None
    for _ in range(50):
        page.wait_for_timeout(300)
        if page.url != old_url:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=CITY_LOADSTATE_TIMEOUT_MS)
            except Exception as e:
                print(f"  [CITY] domcontentloaded timeout ({CITY_LOADSTATE_TIMEOUT_MS}ms), continue without wait: {e}")
            city_base_url = page.url.rstrip("/")
            break

    if not city_base_url:
        log_error("city_no_redirect", page,
                  base_url.replace("https://","").replace("http://","").strip("/"),
                  extra=f"city={city_name}")
        return None, None

    print(f"  [CITY] ✅ {city_base_url}")
    return city_base_url, city_base_url + "/business"
def run_site_scenario(page: Page, cfg: dict):
    """
    Полный сценарий для сайта:
    1. Форма checkaddress (если есть)
    2. Все попапы главной
    3. Попапы /business (если есть)
    4. Сценарий города (если задан city_name):
       4a. Попапы главной города
       4b. Попапы /business города (если has_business)
    """
    base_url       = cfg["base_url"]
    has_name_field = cfg.get("has_name_field", False)
    sep            = "=" * 55
    site_label     = base_url.replace("https://", "").replace("http://", "").strip("/")
    city_name      = cfg.get("city_name")
    city_base      = None
    city_biz       = None
    service_mode   = normalize_service_mode(cfg.get("_service_mode", SERVICE_MODE_ALL))

    print(f"\n{'#'*55}\n# САЙТ: {site_label} | MODE: {service_mode}\n{'#'*55}")

    # ── 1. Форма checkaddress ─────────────────────────────────────────────
    with allure.step("Шаг 1: форма checkaddress"):
        if service_mode == SERVICE_MODE_VARIANTS:
            mark_step_not_applicable(site_label, "1", "форма checkaddress", "service_mode=variants")
        elif cfg.get("has_checkaddress"):
            print(f"\n{sep}\n[{site_label}] Шаг 1: форма checkaddress\n{sep}")
            goto_or_handle_step(page, base_url, site_label, "1", "форма checkaddress")
            close_overlays(page)

            step_reason = None
            fcfg      = FORM_CONFIGS["checkaddress"]
            container = page.locator("section, form, div").filter(
                has=page.locator(fcfg["phone"])
            ).first

            if container.count() > 0:
                filled = fill_form(page, container, "checkaddress")
                submit = find_submit(container, "checkaddress") if filled else None
                if submit:
                    submit.scroll_into_view_if_needed()
                    print(f"  ✅ checkaddress готова")
                    if REALLY_SUBMIT:
                        return_url_before_submit = page.url or base_url
                        ok = submit_with_confirmation(
                            page, container, "checkaddress",
                            timeout_ms=SUBMIT_CONFIRM_TIMEOUT_MS, attempts=2
                        )
                        if ok:
                            thanks_ok, thanks_reason = verify_thanks_close_and_return(
                                page, return_url_before_submit
                            )
                            if thanks_ok:
                                nav_ok, _, nav_reason = safe_goto(page, base_url)
                                if not nav_ok:
                                    step_reason = f"не удалось вернуться на {base_url} после Thanks: {nav_reason}"
                            else:
                                step_reason = f"не выполнен шаг закрытия Thanks: {thanks_reason}"
                        else:
                            step_reason = "подтверждение отправки не получено"
                elif not filled:
                    step_reason = "форма checkaddress не заполнена"
                else:
                    step_reason = "кнопка отправки checkaddress не найдена"
            else:
                print("  ⚠️  Форма checkaddress не найдена на странице")
                step_reason = "форма checkaddress не найдена на странице"

            if step_reason:
                send_step_alert(site_label, "1", "форма checkaddress", step_reason, page)
        else:
            mark_step_not_applicable(site_label, "1", "форма checkaddress", "has_checkaddress=False")

    # ── 2. Попапы главной ─────────────────────────────────────────────────
    with allure.step("Шаг 2: попапы главной"):
        print(f"\n{sep}\n[{site_label}] Шаг 2: попапы главной\n{sep}")
        goto_or_handle_step(page, base_url, site_label, "2", "попапы главной")
        close_overlays(page)
        try:
            s, f, first_fail = process_all_popups(
                page, base_url, has_name_field=has_name_field, service_mode=service_mode
            )
        except SiteUnavailableError as e:
            skip_site_due_unavailability(site_label, "2", "попапы главной", str(e), page)
        if f > 0:
            reason = f"{f} ошибок, {s} успешно"
            if first_fail:
                reason += f" | first={first_fail}"
            send_step_alert(site_label, "2", "попапы главной", reason[:900], page)
        assert f == 0, (
            f"[{site_label}] Попапы главной: {f} ошибок, {s} успешно"
            + (f" | first={first_fail}" if first_fail else "")
        )

    # ── 3. Попапы /business ───────────────────────────────────────────────
    with allure.step("Шаг 3: попапы /business"):
        if service_mode == SERVICE_MODE_VARIANTS:
            mark_step_not_applicable(site_label, "3", "попапы /business", "service_mode=variants")
        elif cfg.get("has_business"):
            business_url = base_url.rstrip("/") + "/business"
            print(f"\n{sep}\n[{site_label}] Шаг 3: попапы /business\n{sep}")
            goto_business_or_handle_step(page, base_url, business_url, site_label, "3", "\u043f\u043e\u043f\u0430\u043f\u044b /business")
            # close_overlays is already handled inside goto_business_or_handle_step
            try:
                s, f, first_fail = process_business_popups(
                    page, business_url, has_name_field=has_name_field, service_mode=service_mode
                )
            except SiteUnavailableError as e:
                skip_site_due_unavailability(site_label, "3", "попапы /business", str(e), page)
            if f > 0:
                reason = f"{f} ошибок, {s} успешно"
                if first_fail:
                    reason += f" | first={first_fail}"
                send_step_alert(site_label, "3", "попапы /business", reason[:900], page)
            assert f == 0, (
                f"[{site_label}] Бизнес: {f} ошибок, {s} успешно"
                + (f" | first={first_fail}" if first_fail else "")
            )
        else:
            mark_step_not_applicable(site_label, "3", "попапы /business", "has_business=False")

    # ── 4. Сценарий города ────────────────────────────────────────────────
    with allure.step("Шаг 4: выбор города"):
        if city_name:
            print(f"\n{sep}\n[{site_label}] Шаг 4: город '{city_name}'\n{sep}")
            try:
                city_base, city_biz = run_city_scenario(page, base_url, city_name)
            except SiteUnavailableError as e:
                skip_site_due_unavailability(site_label, "4", "выбор города", str(e), page)
            if city_base is None:
                reason = f"город '{city_name}' не выбран или не произошёл редирект"
                send_step_alert(site_label, "4", "выбор города", reason, page)
                assert city_base is not None, f"[{site_label}] Шаг 4: {reason}"
        else:
            mark_step_not_applicable(site_label, "4", "выбор города", "city_name=None")

    # ── 4a. Попапы главной города ─────────────────────────────────────────
    with allure.step("Шаг 4a: попапы главной города"):
        if city_name is None:
            mark_step_not_applicable(site_label, "4a", "попапы главной города", "city_name=None")
        elif city_base is None:
            mark_step_not_applicable(site_label, "4a", "попапы главной города", "городской сценарий недоступен по условию")
        else:
            goto_or_handle_step(page, city_base, site_label, "4a", "попапы главной города")
            close_overlays(page)
            try:
                s, f, first_fail = process_all_popups(
                    page, city_base, has_name_field=has_name_field, service_mode=service_mode
                )
            except SiteUnavailableError as e:
                skip_site_due_unavailability(site_label, "4a", "попапы главной города", str(e), page)
            if f > 0:
                reason = f"{f} ошибок, {s} успешно"
                if first_fail:
                    reason += f" | first={first_fail}"
                send_step_alert(site_label, "4a", "попапы главной города", reason[:900], page)
            assert f == 0, (
                f"[{site_label}] Попапы города: {f} ошибок"
                + (f" | first={first_fail}" if first_fail else "")
            )

    # ── 4b. Попапы /business города ───────────────────────────────────────
    with allure.step("Шаг 4b: попапы /business города"):
        if city_name is None:
            mark_step_not_applicable(site_label, "4b", "попапы /business города", "city_name=None")
        elif service_mode == SERVICE_MODE_VARIANTS:
            mark_step_not_applicable(site_label, "4b", "попапы /business города", "service_mode=variants")
        elif not cfg.get("has_business"):
            mark_step_not_applicable(site_label, "4b", "попапы /business города", "has_business=False")
        elif city_biz is None:
            mark_step_not_applicable(site_label, "4b", "попапы /business города", "городской сценарий недоступен по условию")
        else:
            goto_business_or_handle_step(page, city_base, city_biz, site_label, "4b", "\u043f\u043e\u043f\u0430\u043f\u044b /business \u0433\u043e\u0440\u043e\u0434\u0430")
            # close_overlays is already handled inside goto_business_or_handle_step
            try:
                s, f, first_fail = process_business_popups(
                    page, city_biz, has_name_field=has_name_field, service_mode=service_mode
                )
            except SiteUnavailableError as e:
                skip_site_due_unavailability(site_label, "4b", "попапы /business города", str(e), page)
            if f > 0:
                reason = f"{f} ошибок, {s} успешно"
                if first_fail:
                    reason += f" | first={first_fail}"
                send_step_alert(site_label, "4b", "попапы /business города", reason[:900], page)
            assert f == 0, (
                f"[{site_label}] Бизнес города: {f} ошибок"
                + (f" | first={first_fail}" if first_fail else "")
            )

    print(f"\n{'#'*55}\n# ✅ ГОТОВО: {site_label}\n{'#'*55}\n")


# ---------------------------------------------------------------------------
# Тест
# ---------------------------------------------------------------------------

def test_site(page: Page, site_cfg: dict, browser_name: str, blocking_profile: str):
    """
    Запуск для одного сайта:
        pytest -s --headed --site=mts-home-gpon.ru

    Запуск для всех сайтов:
        pytest -s --headed
    """
    service_mode = normalize_service_mode(site_cfg.get("_service_mode", SERVICE_MODE_ALL))
    allure.dynamic.title(
        f"Сайт: {site_cfg['base_url']} [{service_mode}] [{browser_name}] [{blocking_profile}]"
    )
    allure.dynamic.label("suite", "Формы провайдеров")
    allure.dynamic.label("subSuite", f"service-mode: {service_mode}")
    allure.dynamic.parameter("browser", browser_name)
    allure.dynamic.parameter("blocking_profile", blocking_profile)
    run_site_scenario(page, site_cfg)
