from playwright.sync_api import Page, expect

BASE_URL      = "https://mts-home-gpon.ru/"
BUSINESS_URL  = "https://mts-home-gpon.ru/business"
CITY_NAME     = "Москва"   # город для теста — меняйте здесь
REALLY_SUBMIT = True  # True — реально отправлять заявки

# ---------------------------------------------------------------------------
# Конфигурация форм
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
    "business": {
        "street":     ".business_no_address_full_address",
        "house":      None,
        "phone":      ".business_no_address_phone",
        "submit":     ".business_no_address_button_send",
        "no_house":   True,
        "no_suggest": True,
    },
}

POPUP_CONTAINER_SELECTORS = [
    "div#popup",
    "div.popup",
    "[id*='popup']:not(script)",
    "[class*='popup']:not(script)",
    "[class*='modal']:not(script)",
    "[class*='fancybox']:not(script)",
    "[class*='overlay']:not(script)",
]

SUCCESS_URL_MARKERS = ["/tilda/form1/submitted", "/thanks"]

POPUP_OPEN_KEYWORDS = ["подключить", "получить консультацию", "оставить заявку",
                       "заказать", "оформить", "узнать подробнее"]
POPUP_SKIP_KEYWORDS = ["проверить адрес", "сменить город"]

SUGGESTION_SELECTORS = [
    "[role='option']",
    "[role='listbox'] li",
    ".suggestions__item",
    ".suggestion-item",
    ".autocomplete__item",
    ".ui-menu-item",
    "[class*='suggest'] li",
    "[class*='autocomplete'] li",
    "[class*='dropdown'] li",
]


# ---------------------------------------------------------------------------
# Базовые утилиты
# ---------------------------------------------------------------------------

def first_visible(locator):
    for i in range(locator.count()):
        item = locator.nth(i)
        try:
            if item.is_visible():
                return item
        except Exception:
            pass
    raise AssertionError("Не найден видимый элемент")


def iter_visible(locator):
    for i in range(locator.count()):
        item = locator.nth(i)
        try:
            if item.is_visible():
                yield item
        except Exception:
            pass


def close_overlays(page: Page):
    try:
        ok_btn = page.get_by_role("button", name="ОК", exact=True)
        if ok_btn.count() > 0:
            ok_btn.first.click(timeout=1000, force=True)
    except Exception:
        pass
    for btn in iter_visible(page.locator(
        "button, [role='button'], .popup__close, .modal__close, .fancybox-close-small"
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
    """Закрывает попап. Если текущий URL — /thanks, возвращается на предыдущий."""
    current_url = page.url.lower()
    if any(m in current_url for m in SUCCESS_URL_MARKERS):
        # Возврат обрабатывается в safe_goto — здесь просто выходим
        return
    for btn in iter_visible(page.locator(
        "button, [role='button'], .popup__close, .modal__close, .fancybox-close-small"
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


def safe_goto(page: Page, url: str, retries: int = 3):
    """
    Навигация с повторными попытками.
    ОПТИМИЗАЦИЯ: убрано wait_for_load_state("networkidle") —
    оно добавляло до 5с на каждый переход. Используем только domcontentloaded.
    """
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(500)   # минимальная пауза вместо 800мс
            print(f"  [NAV] {url}")
            return
        except Exception as e:
            print(f"  [NAV] Попытка {attempt}/{retries}: {e}")
            page.wait_for_timeout(1000)
    print(f"  [NAV] ❌ Не удалось перейти на {url}")


# ---------------------------------------------------------------------------
# Ожидание успешной отправки
# ---------------------------------------------------------------------------

def wait_for_success_url(page: Page, timeout_ms: int = 15_000) -> bool:
    print(f"  [SUBMIT] Ждём подтверждения (до {timeout_ms // 1000}с)...")
    poll_ms = 300
    elapsed = 0
    while elapsed < timeout_ms:
        if any(m in page.url.lower() for m in SUCCESS_URL_MARKERS):
            print(f"  [SUBMIT] ✅ {page.url}")
            return True
        page.wait_for_timeout(poll_ms)
        elapsed += poll_ms
    print(f"  [SUBMIT] ❌ Текущий URL: {page.url}")
    return False


# ---------------------------------------------------------------------------
# Подсказки автодополнения
# ОПТИМИЗАЦИЯ: сокращён таймаут ожидания до 1500мс вместо 5000мс,
# т.к. сайт не возвращает подсказки — быстрее упасть на ArrowDown+Enter.
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
                        text = item.inner_text().strip()
                        print(f"  [SUGGEST] '{text[:50]}'")
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

def fill_form(page: Page, container, form_type: str) -> bool:
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
        print("  [FORM] Поле Дом пропущено (бизнес-форма)")
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
            else:
                print(f"  [FORM] Поле Дом не найдено ({house_sel})")

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


# ---------------------------------------------------------------------------
# Ожидание открытия попапа
# ---------------------------------------------------------------------------

def wait_for_popup_with_fields(page: Page, timeout_ms: int = 10_000, form_hint=None):
    form_types_to_check = (
        [(form_hint, FORM_CONFIGS[form_hint])] if form_hint and form_hint in FORM_CONFIGS
        else list(FORM_CONFIGS.items())
    )
    poll_ms = 300
    elapsed = 0

    while elapsed < timeout_ms:
        # Приоритет 1: точные попап-контейнеры
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
                            print(f"  [POPUP FOUND] sel='{popup_sel}' type='{form_type}'")
                            return form_type, container
                    except Exception:
                        pass

        # Приоритет 2: поднимаемся по предкам от поля телефона
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
                        print(f"  [POPUP FOUND] ancestor type='{form_type}'")
                        return form_type, parent
                    form_parent = phone.locator("xpath=ancestor::form").last
                    if form_parent.count() > 0 and form_parent.is_visible():
                        print(f"  [POPUP FOUND] form-ancestor type='{form_type}'")
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
    """Собирает ВСЕ кнопки попапов без дедупликации по тексту."""
    all_btns = page.locator("button")
    total    = all_btns.count()
    result   = []
    seen_idx = set()

    print(f"\n[COLLECT] Кнопок на странице: {total}")

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

    # Кнопка попапа "Выгодное спецпредложение" по CSS-классу
    profit_btns = page.locator(".profit_address_button")
    for i in range(profit_btns.count()):
        btn = profit_btns.nth(i)
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
                           "form_hint": "profit", "css": ".profit_address_button"})
            print(f"  [COLLECT] #{len(result)} index={global_idx} '{text}' (profit)")
        except Exception:
            pass

    print(f"[COLLECT] Итого: {len(result)}\n")
    return result


def _collect_business_buttons(page: Page) -> list:
    """Собирает кнопки попапов бизнес-страницы по классу .business_no_address_button."""
    business_btns = page.locator(".business_no_address_button")
    total  = business_btns.count()
    result = []
    print(f"\n[BUSINESS COLLECT] Элементов .business_no_address_button: {total}")
    for i in range(total):
        btn = business_btns.nth(i)
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
# Общий цикл обработки попапов
# ---------------------------------------------------------------------------

def _run_popup_cycle(page: Page, buttons: list, base_url: str,
                     btn_locator_fn, label: str = "POPUP") -> tuple[int, int]:
    """
    Универсальный цикл: для каждой кнопки из списка —
    1. safe_goto(base_url)
    2. Клик через btn_locator_fn(page, entry)
    3. Заполнить попап → отправить → ждать /thanks

    ОПТИМИЗАЦИЯ: safe_goto вынесен сюда и делается ОДИН РАЗ перед кликом,
    а не дважды (больше нет дублирующих переходов).
    """
    success = 0
    failed  = 0

    for num, entry in enumerate(buttons, 1):
        text      = entry.get("text", "")
        form_hint = entry.get("form_hint")
        sep       = "=" * 55
        print(f"\n{sep}")
        print(f"[{label} {num}/{len(buttons)}] '{text}' hint={form_hint}")
        print(sep)

        safe_goto(page, base_url)

        try:
            btn = btn_locator_fn(page, entry)
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            page.wait_for_timeout(500)
        except Exception as e:
            print(f"  [{label}] ❌ Клик не удался: {e}")
            failed += 1
            continue

        form_type, container = wait_for_popup_with_fields(page, form_hint=form_hint)
        if form_type is None:
            print(f"  [{label}] ❌ Попап не распознан")
            failed += 1
            continue

        if not fill_form(page, container, form_type):
            print(f"  [{label}] ❌ Форма не заполнена")
            failed += 1
            continue

        submit = find_submit(container, form_type)
        if submit is None:
            print(f"  [{label}] ❌ Кнопка отправки не найдена")
            failed += 1
            continue

        submit.scroll_into_view_if_needed()

        if REALLY_SUBMIT:
            submit.click(force=True)
            ok = wait_for_success_url(page, timeout_ms=15_000)
            if ok:
                print(f"  [{label}] ✅ Заявка принята")
                success += 1
            else:
                print(f"  [{label}] ⚠️  Подтверждение не получено")
                failed += 1
        else:
            print(f"  [{label}] ✅ Форма готова (REALLY_SUBMIT=False)")
            close_popup_or_page(page)
            success += 1

    sep = "=" * 55
    print(f"\n{sep}")
    print(f"[{label} RESULT] ✅ {success}  ❌ {failed}  Всего: {len(buttons)}")
    print(f"{sep}\n")
    return success, failed


def process_all_popups(page: Page, base_url: str = None) -> tuple[int, int]:
    if base_url is None:
        base_url = BASE_URL
    buttons = collect_popup_buttons(page)
    assert buttons, "Кнопки для попапов не найдены"

    def locate_btn(page, entry):
        css = entry.get("css")
        if css:
            return page.locator(css).first
        return page.locator("button").nth(entry["index"])

    return _run_popup_cycle(page, buttons, base_url, locate_btn, label="POPUP")


def process_business_popups(page: Page, base_url: str) -> tuple[int, int]:
    buttons = _collect_business_buttons(page)
    if not buttons:
        print(f"[BUSINESS] Кнопки не найдены на {base_url} — пропускаем")
        return 0, 0

    def locate_btn(page, entry):
        return page.locator(".business_no_address_button").nth(entry["nth"])

    return _run_popup_cycle(page, buttons, base_url, locate_btn, label="BUSINESS")



# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

def test_checkaddress_form(page: Page):
    """Форма 'Проверить адрес' на главной странице."""
    page.goto(BASE_URL, wait_until="domcontentloaded")
    close_overlays(page)

    cfg       = FORM_CONFIGS["checkaddress"]
    container = page.locator("section, form, div").filter(
        has=page.locator(cfg["phone"])
    ).first
    assert container.count() > 0, "Форма checkaddress не найдена"

    filled = fill_form(page, container, "checkaddress")
    assert filled, "Форма checkaddress не заполнена"

    submit = find_submit(container, "checkaddress")
    assert submit is not None, "Кнопка отправки checkaddress не найдена"
    submit.scroll_into_view_if_needed()
    print("[TEST checkaddress] ✅ Форма готова")

    if REALLY_SUBMIT:
        submit.click(force=True)
        ok = wait_for_success_url(page, timeout_ms=15_000)
        assert ok, "Страница подтверждения не открылась"
        safe_goto(page, BASE_URL)


def test_all_popup_forms(page: Page):
    """Все попапы 'Подключить' на главной странице."""
    page.goto(BASE_URL, wait_until="domcontentloaded")
    close_overlays(page)

    success, failed = process_all_popups(page)
    assert failed == 0, f"{failed} попап(ов) не обработано. Успешно: {success}."


def test_business_popup_forms(page: Page):
    """Все попапы на странице /business."""
    page.goto(BUSINESS_URL, wait_until="domcontentloaded")
    close_overlays(page)

    success, failed = process_business_popups(page, BUSINESS_URL)
    assert success > 0 or failed == 0, \
        f"Бизнес-попапы: {failed} ошибок, {success} успешно."


def test_city_popup_forms(page: Page):
    """
    Сценарий города:
    1. Открываем CITIES_URL, ищем CITY_NAME в списке .region_item.region_link
    2. Кликаем, ждём перехода на поддомен/подпапку
    3. На странице города: все попапы главной (process_all_popups)
    4. На странице города/business: бизнес-попапы (process_business_popups)
    """
    sep = "=" * 55

    # ── Шаг 1: выбор города ───────────────────────────────────────────────
    print(f"\n{sep}\n[CITY] Шаг 1: открываем попап выбора города\n{sep}")
    safe_goto(page, BASE_URL)
    close_overlays(page)

    # Кликаем на кнопку выбора города в шапке: <a class="header__city city">
    city_btn = page.locator("a.header__city.city").first
    assert city_btn.count() > 0, "Кнопка выбора города (a.header__city.city) не найдена"
    city_btn.click(force=True)
    page.wait_for_timeout(600)
    print(f"  [CITY] Попап открыт")

    # Ждём появления ссылок городов в DOM
    city_links = page.locator(".region_item.region_link")
    try:
        city_links.first.wait_for(state="attached", timeout=10_000)
    except Exception:
        raise AssertionError("Список городов (.region_item.region_link) не появился в DOM")

    # Поле поиска — фильтруем список если есть
    for sel in ["input[placeholder*='оиск']", "input[placeholder*='ород']",
                "input[type='search']", "input[type='text']"]:
        inp = page.locator(sel).first
        try:
            if inp.count() > 0 and inp.is_visible():
                inp.click(force=True)
                inp.fill(CITY_NAME)
                page.wait_for_timeout(400)
                print(f"  [CITY] Введено '{CITY_NAME}' в поле поиска")
                break
        except Exception:
            pass

    # Кликаем на нужный город
    link = page.locator(".region_item.region_link").filter(has_text=CITY_NAME).first
    assert link.count() > 0, \
        f"Город '{CITY_NAME}' не найден в списке (.region_item.region_link)"

    old_url = page.url
    # force=True — элемент может быть hidden пока попап анимируется
    link.click(force=True)
    print(f"  [CITY] Клик по '{CITY_NAME}'")

    # Ждём смены URL (поддомен или подпапка)
    city_base_url = None
    for _ in range(50):          # до 15 секунд
        page.wait_for_timeout(300)
        if page.url != old_url:
            page.wait_for_load_state("domcontentloaded")
            city_base_url = page.url.rstrip("/")
            break

    assert city_base_url, \
        f"Переход на страницу города не произошёл. URL остался: {page.url}"
    print(f"  [CITY] ✅ Перешли на: {city_base_url}")

    city_business_url = city_base_url + "/business"

    # ── Шаг 2: попапы главной страницы города ────────────────────────────
    print(f"\n{sep}\n[CITY] Шаг 2: попапы главной — {city_base_url}\n{sep}")
    safe_goto(page, city_base_url)
    close_overlays(page)

    success_main, failed_main = process_all_popups(page, base_url=city_base_url)
    assert failed_main == 0, \
        f"Попапы города: {failed_main} ошибок, {success_main} успешно."

    # ── Шаг 3: бизнес-попапы города ──────────────────────────────────────
    print(f"\n{sep}\n[CITY] Шаг 3: бизнес-попапы — {city_business_url}\n{sep}")
    safe_goto(page, city_business_url)
    close_overlays(page)

    success_biz, failed_biz = process_business_popups(page, city_business_url)
    assert failed_biz == 0, \
        f"Бизнес-попапы города: {failed_biz} ошибок, {success_biz} успешно."

    print(f"\n{sep}\n[CITY] ✅ Тест завершён. {city_base_url}\n{sep}")
