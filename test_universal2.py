"""
Универсальный тест форм для сайтов интернет-провайдеров.

Запуск для конкретного сайта:
    pytest -s --headed --site=mts-home-gpon.ru

Запуск для всех сайтов последовательно:
    pytest -s --headed  (прогоняет все сайты из SITE_CONFIGS)
    pytest test_universal2.py --alluredir=allure-results -s - все сайты с аллюр
    pytest test_universal2.py --site=mts-home-gpon.ru --alluredir=allure-results -s - конкретный сайт с аллюр

Добавить новый сайт — достаточно добавить запись в SITE_CONFIGS.
"""

import pytest
from playwright.sync_api import Page, expect
import allure
import os
import requests
from datetime import datetime

REALLY_SUBMIT = True # True — реально отправлять заявки

# ---------------------------------------------------------------------------
# Таблица ошибок → причин для Telegram-алертов
# ---------------------------------------------------------------------------

ERROR_REASONS = {
    "popup_not_found":  ("Попап не распознан",           "Попап не открылся после клика"),
    "form_not_filled":  ("Форма не заполнена",            "Поле недоступно или перекрыто оверлеем"),
    "submit_not_found": ("Кнопка отправки не найдена",    "Форма не в ожидаемом состоянии"),
    "no_confirmation":  ("Подтверждение не получено",     "Сайт не перешёл на /thanks"),
    "click_failed":     ("Клик по кнопке не удался",      "Элемент не виден или не существует"),
    "city_not_found":   ("Город не найден в списке",      "Список городов не загрузился"),
    "city_no_redirect": ("Переход на город не произошёл", "URL не изменился после клика"),
}


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
    time_now = datetime.now().strftime("%H:%M:%S")
    run_url = os.getenv("RUN_URL", "").strip()

    lines = [
        f"❌ [{site_label}] Шаг {step_no}: {step_name} — failed",
        f"Статус: failed",
        f"Причина: {reason}",
        f"URL: {url}",
        f"Время: {time_now}",
    ]
    if run_url:
        lines.append(f"Run: {run_url}")

    print(f"[STEP-ALERT] [{site_label}] Шаг {step_no}: {step_name} | {reason} | {url}")
    send_telegram_alert("\n".join(lines), alert_type="step")


class SiteUnavailableError(RuntimeError):
    """Сайт недоступен/не отвечает — текущий сайт нужно пропустить."""


def send_critical_alert(site_label: str, step_no: str, step_name: str, reason: str, page: "Page" = None):
    url = page.url if page else ""
    time_now = datetime.now().strftime("%H:%M:%S")
    run_url = os.getenv("RUN_URL", "").strip()

    lines = [
        f"[CRITICAL] [{site_label}] Шаг {step_no}: {step_name}",
        "Статус: critical",
        f"Причина: {reason}",
        f"URL: {url}",
        f"Время: {time_now}",
    ]
    if run_url:
        lines.append(f"Run: {run_url}")

    text = "\n".join(lines)
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
    time = datetime.now().strftime("%H:%M:%S")

    # Консоль
    print(f"  ❌ {error_msg} | {reason} | {url}")

    # Telegram
    lines = [
        "❌ Ошибка в тесте",
        "",
        f"Сайт: {site_label}",
        f"Ошибка: {error_msg}",
        f"Причина: {reason}",
    ]
    if extra:
        lines.append(f"Детали: {extra}")
    lines += [
        f"URL: {url}",
        f"Время: {time}",
    ]
    run_url = os.getenv("RUN_URL", "").strip()
    if run_url:
        lines.append(f"Run: {run_url}")

    send_telegram_alert("\n".join(lines), alert_type="tech")

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
  #  "mts-home-gpon.ru": {
  #     "base_url":        "https://mts-home-gpon.ru/",
   #     "has_checkaddress": True,
   #     "has_business":     True,
    #    "city_name":        "Москва",
    #},
   # "mts-home.online": {
    #    "base_url":        "https://mts-home.online/",
     #   "has_checkaddress": False,
      #  "has_business":     True,
       # "city_name":        "Москва",
    #},
    #"mts-home-online.ru": {
     #   "base_url":        "https://mts-home-online.ru/",
      #  "has_checkaddress": False,
       # "has_business":     True,
        #"city_name":        None,
    #},
    #"internet-mts-home.online": {
     #   "base_url":        "https://internet-mts-home.online/",
      #  "has_checkaddress": False,
       # "has_business":     False,
        #"city_name":        "Москва",
    #},
    #"mts-internet.online": {
     #   "base_url":        "https://mts-internet.online/",
      #  "has_checkaddress": False,
       # "has_business":     False,
        #"city_name":        "Москва",
    #},
    #"beeline-internet.online": {
     #   "base_url":        "https://beeline-internet.online/",
      #  "has_checkaddress": False,
       # "has_business":     True,
        #"city_name":        "Москва",
       # "has_region_popup": True,
  #  },
    #"beeline-ru.online": {
     #   "base_url":        "https://beeline-ru.online/",
      #  "has_checkaddress": False,
       # "has_business":     True,
        #"city_name":        "Москва",
        #"has_region_popup": True,
    #},
    #"online-beeline.ru": {
     #   "base_url":        "https://online-beeline.ru/",
      #  "has_checkaddress": False,
     #   "has_business":     True,
     #   "city_name":        "Москва",
     #   "has_region_popup": True,
    #},
  #  "beeline-ru.pro": {
   #     "base_url":        "https://beeline-ru.pro/",
    #    "has_checkaddress": False,
    #    "has_business":     False,
    #    "city_name":        "Москва",
    #    "has_region_popup": True,
#    },
  #  "beeline-home.online": {
  #      "base_url":        "https://beeline-home.online/",
   #     "has_checkaddress": False,
    #    "has_business":     False,
     #   "city_name":        "Москва",
     #   "has_region_popup": True,
   # },
   # "beelline-internet.ru": {
   #     "base_url":        "https://beelline-internet.ru/",
    #    "has_checkaddress": False,
     #   "has_business":     False,
      #  "city_name":        "Москва",
       # "has_region_popup": True,
   # },
    "rtk-ru.online": {
        "base_url":        "https://rtk-ru.online/",
        "has_checkaddress": False,
        "has_business":     True,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "rt-internet.online": {
        "base_url":        "https://rt-internet.online/",
        "has_checkaddress": False,
        "has_business":     True,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "rtk-home-internet.ru": {
        "base_url":        "https://rtk-home-internet.ru/",
        "has_checkaddress": False,
        "has_business":     True,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "rtk-internet.online": {
        "base_url":        "https://rtk-internet.online/",
        "has_checkaddress": False,
        "has_business":     True,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "rtk-home.ru": {
        "base_url":        "http://rtk-home.ru/",
        "has_checkaddress": False,
        "has_business":     True,
        "city_name":        "Москва",
        "has_name_field": True,
    },
    "dom-provider.online": {
        "base_url":        "https://dom-provider.online/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        None,
    },
    "providerdom.ru": {
        "base_url":        "https://providerdom.ru/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        None,
    },
    "mega-premium.ru": {
        "base_url":        "https://mega-premium.ru/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        None,
    },
    "mega-home-internet.ru": {
        "base_url":        "https://mega-home-internet.ru/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        None,
    },
    "t2-official.ru": {
        "base_url":        "https://t2-official.ru/",
        "has_checkaddress": False,
        "has_business":     False,
        "city_name":        None,
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
}

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

SUCCESS_URL_MARKERS = ["/tilda/form1/submitted", "/thanks"]
SUBMIT_CONFIRM_TIMEOUT_MS = 25_000
SUBMIT_CONFIRM_GRACE_MS = 2_000

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
        if site_arg:
            configs = [SITE_CONFIGS[site_arg]]
            ids     = [site_arg]
        else:
            configs = list(SITE_CONFIGS.values())
            ids     = list(SITE_CONFIGS.keys())
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

    # Вариант 1: есть кнопка "Да" — кликаем её
    try:
        yes_btn = page.locator("#yesButton").first
        if yes_btn.count() > 0 and yes_btn.is_visible():
            yes_btn.click(force=True)
            page.wait_for_timeout(400)
            print("  [REGION] Попап региона закрыт (кнопка 'Да')")
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


def safe_goto(page: Page, url: str, retries: int = 2, goto_timeout_ms: int = 20_000) -> bool:
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

    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=goto_timeout_ms)
            page.wait_for_timeout(500)
            print(f"  [NAV] {url}")
            return True
        except Exception as e:
            print(f"  [NAV] Попытка {attempt}/{retries}: {e}")
            page.wait_for_timeout(1500)
    print(f"  [NAV] ❌ Не удалось перейти на {url}")
    return False


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


# ---------------------------------------------------------------------------
# Заполнение формы
# ---------------------------------------------------------------------------

def fill_form(page: Page, container, form_type: str,
              has_name_field: bool = False) -> bool:
    cfg        = FORM_CONFIGS[form_type]
    no_house   = cfg.get("no_house", False)
    no_suggest = cfg.get("no_suggest", False)

    # Адрес / Улица
    street = container.locator(cfg["street"]).first
    if street.count() > 0 and street.is_visible():
        street.scroll_into_view_if_needed()
        street.click(force=True)
        street.fill("Ленина")
        if no_suggest:
            print("  [FORM] Адрес введён (без подсказки)")
        else:
            print("  [FORM] Улица введена, ждём подсказку...")
            choose_first_suggestion(page)
    else:
        print(f"  [FORM] Поле адреса не найдено ({cfg['street']})")

    # Дом
    if no_house:
        print("  [FORM] Поле Дом пропущено")
    else:
        house_sel = cfg.get("house")
        if house_sel:
            house = container.locator(house_sel).first
            if house.count() > 0:
                print("  [FORM] Ждём активации поля Дом...")
                try:
                    expect(house).to_be_enabled(timeout=8000)
                    house.scroll_into_view_if_needed()
                    house.click(force=True)
                    house.fill("1")
                    print("  [FORM] Дом введён, ждём подсказку...")
                    choose_first_suggestion(page, timeout_ms=1500)
                except Exception:
                    print("  [FORM] Поле Дом не активировалось — продолжаем")

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

    for cb in iter_visible(container.locator("input[type='checkbox']")):
        try:
            if not cb.is_checked():
                cb.check(force=True)
        except Exception:
            pass

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


def _run_popup_cycle(page: Page, buttons: list, base_url: str,
                     btn_locator_fn, label: str = "POPUP",
                     has_name_field: bool = False) -> tuple[int, int]:
    success    = 0
    failed     = 0
    site_label = base_url.replace("https://", "").replace("http://", "").strip("/")

    for num, entry in enumerate(buttons, 1):
        text      = entry.get("text", "")
        form_hint = entry.get("form_hint")
        sep       = "=" * 55
        print(f"\n{sep}\n[{label} {num}/{len(buttons)}] '{text}' hint={form_hint}\n{sep}")

        if not safe_goto(page, base_url):
            raise SiteUnavailableError(
                f"{label}: сайт недоступен на этапе {num}/{len(buttons)} ({base_url})"
            )
        accept_cookie_banner(page)
        # Закрываем profit если всплыл сам — но не когда тестируем сам profit
        if form_hint != "profit":
            dismiss_profit_popup(page)

        try:
            btn = btn_locator_fn(page, entry)
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            page.wait_for_timeout(500)
        except Exception as e:
            log_error("click_failed", page, site_label, extra=str(e)[:150])
            failed += 1
            continue

        form_type, container = wait_for_popup_with_fields(page, form_hint=form_hint)
        if form_type is None:
            log_error("popup_not_found", page, site_label)
            failed += 1
            continue

        if not fill_form(page, container, form_type, has_name_field=has_name_field):
            log_error("form_not_filled", page, site_label)
            failed += 1
            continue

        submit = find_submit(container, form_type)
        if submit is None:
            log_error("submit_not_found", page, site_label)
            failed += 1
            continue

        submit.scroll_into_view_if_needed()

        if REALLY_SUBMIT:
            ok = submit_with_confirmation(
                page, container, form_type,
                timeout_ms=SUBMIT_CONFIRM_TIMEOUT_MS, attempts=2
            )
            if ok:
                print(f"  [{label}] ✅ Заявка принята")
                # Ждём завершения редиректов перед следующим safe_goto
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                page.wait_for_timeout(500)
                success += 1
            else:
                log_error("no_confirmation", page, site_label)
                failed += 1
        else:
            print(f"  [{label}] ✅ Форма готова (REALLY_SUBMIT=False)")
            close_popup_or_page(page)
            success += 1

    sep = "=" * 55
    print(f"\n{sep}\n[{label} RESULT] ✅ {success}  ❌ {failed}  Всего: {len(buttons)}\n{sep}\n")
    return success, failed


def process_all_popups(page: Page, base_url: str,
                        has_name_field: bool = False) -> tuple[int, int]:
    buttons = collect_popup_buttons(page)
    if not buttons:
        print("[POPUP] Кнопки не найдены — пропускаем")
        return 0, 0

    def locate(page, entry):
        css = entry.get("css")
        if css:
            return page.locator(css).first
        return page.locator("button").nth(entry["index"])

    return _run_popup_cycle(page, buttons, base_url, locate, label="POPUP",
                            has_name_field=has_name_field)


def process_business_popups(page: Page, base_url: str,
                             has_name_field: bool = False) -> tuple[int, int]:
    buttons = collect_business_buttons(page)
    if not buttons:
        print("[BUSINESS] Кнопки не найдены — пропускаем")
        return 0, 0

    def locate(page, entry):
        return page.locator(POPUP_BUTTON_CLASSES["business"]).nth(entry["nth"])

    return _run_popup_cycle(page, buttons, base_url, locate, label="BUSINESS",
                            has_name_field=has_name_field)


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

    if not safe_goto(page, base_url):
        raise SiteUnavailableError(f"CITY: не удалось открыть {base_url}")
    close_overlays(page)

    # Все известные варианты кнопки открытия попапа города
    CITY_BUTTON_SELECTORS = [
        "xpath=(//span[@id='city'])[1]",
        "xpath=(//span[@id='city'])[2]",
        "xpath=(//a[@id='city'])[1]",
        "xpath=(//a[@class='city'])[2]",
        "xpath=//div[@class='header__wrapper-middle']//span[@id='city']",
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
        try:
            link.scroll_into_view_if_needed()
            link.click(timeout=4000, force=True)
            city_link_clicked = True
            break
        except Exception as e:
            print(f"  [CITY] Клик по городу, попытка {attempt}/3: {e}")
            page.wait_for_timeout(500)

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
            page.wait_for_load_state("domcontentloaded")
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

    print(f"\n{'#'*55}\n# САЙТ: {site_label}\n{'#'*55}")

    # ── 1. Форма checkaddress ─────────────────────────────────────────────
    with allure.step("Шаг 1: форма checkaddress"):
        if cfg.get("has_checkaddress"):
            print(f"\n{sep}\n[{site_label}] Шаг 1: форма checkaddress\n{sep}")
            if not safe_goto(page, base_url):
                skip_site_due_unavailability(
                    site_label, "1", "форма checkaddress",
                    f"не удалось открыть {base_url}", page
                )
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
                        ok = submit_with_confirmation(
                            page, container, "checkaddress",
                            timeout_ms=SUBMIT_CONFIRM_TIMEOUT_MS, attempts=2
                        )
                        if ok:
                            safe_goto(page, base_url)
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
        if not safe_goto(page, base_url):
            skip_site_due_unavailability(
                site_label, "2", "попапы главной",
                f"не удалось открыть {base_url}", page
            )
        close_overlays(page)
        try:
            s, f = process_all_popups(page, base_url, has_name_field=has_name_field)
        except SiteUnavailableError as e:
            skip_site_due_unavailability(site_label, "2", "попапы главной", str(e), page)
        if f > 0:
            send_step_alert(site_label, "2", "попапы главной", f"{f} ошибок, {s} успешно", page)
        assert f == 0, f"[{site_label}] Попапы главной: {f} ошибок, {s} успешно"

    # ── 3. Попапы /business ───────────────────────────────────────────────
    with allure.step("Шаг 3: попапы /business"):
        if cfg.get("has_business"):
            business_url = base_url.rstrip("/") + "/business"
            print(f"\n{sep}\n[{site_label}] Шаг 3: попапы /business\n{sep}")
            if not safe_goto(page, business_url):
                skip_site_due_unavailability(
                    site_label, "3", "попапы /business",
                    f"не удалось открыть {business_url}", page
                )
            close_overlays(page)
            try:
                s, f = process_business_popups(page, business_url, has_name_field=has_name_field)
            except SiteUnavailableError as e:
                skip_site_due_unavailability(site_label, "3", "попапы /business", str(e), page)
            if f > 0:
                send_step_alert(site_label, "3", "попапы /business", f"{f} ошибок, {s} успешно", page)
            assert f == 0, f"[{site_label}] Бизнес: {f} ошибок, {s} успешно"
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
            if not safe_goto(page, city_base):
                skip_site_due_unavailability(
                    site_label, "4a", "попапы главной города",
                    f"не удалось открыть {city_base}", page
                )
            close_overlays(page)
            try:
                s, f = process_all_popups(page, city_base, has_name_field=has_name_field)
            except SiteUnavailableError as e:
                skip_site_due_unavailability(site_label, "4a", "попапы главной города", str(e), page)
            if f > 0:
                send_step_alert(site_label, "4a", "попапы главной города", f"{f} ошибок, {s} успешно", page)
            assert f == 0, f"[{site_label}] Попапы города: {f} ошибок"

    # ── 4b. Попапы /business города ───────────────────────────────────────
    with allure.step("Шаг 4b: попапы /business города"):
        if city_name is None:
            mark_step_not_applicable(site_label, "4b", "попапы /business города", "city_name=None")
        elif not cfg.get("has_business"):
            mark_step_not_applicable(site_label, "4b", "попапы /business города", "has_business=False")
        elif city_biz is None:
            mark_step_not_applicable(site_label, "4b", "попапы /business города", "городской сценарий недоступен по условию")
        else:
            if not safe_goto(page, city_biz):
                skip_site_due_unavailability(
                    site_label, "4b", "попапы /business города",
                    f"не удалось открыть {city_biz}", page
                )
            close_overlays(page)
            try:
                s, f = process_business_popups(page, city_biz, has_name_field=has_name_field)
            except SiteUnavailableError as e:
                skip_site_due_unavailability(site_label, "4b", "попапы /business города", str(e), page)
            if f > 0:
                send_step_alert(site_label, "4b", "попапы /business города", f"{f} ошибок, {s} успешно", page)
            assert f == 0, f"[{site_label}] Бизнес города: {f} ошибок"

    print(f"\n{'#'*55}\n# ✅ ГОТОВО: {site_label}\n{'#'*55}\n")


# ---------------------------------------------------------------------------
# Тест
# ---------------------------------------------------------------------------

def test_site(page: Page, site_cfg: dict):
    """
    Запуск для одного сайта:
        pytest -s --headed --site=mts-home-gpon.ru

    Запуск для всех сайтов:
        pytest -s --headed
    """
    allure.dynamic.title(f"Сайт: {site_cfg['base_url']}")
    allure.dynamic.label("suite", "Формы провайдеров")
    run_site_scenario(page, site_cfg)
