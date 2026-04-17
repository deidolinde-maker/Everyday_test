"""
test_mobile_tariffs.py
======================
UI-автотест проверки блока мобильных тарифов на лендингах.

Сценарий (для каждого лендинга):
  1.   Открыть сайт
  1.5. Закрыть попап выбора региона (Beeline) — ПЕРВЫМ
  1.6. Принять куки
  2.   Найти и кликнуть элемент перехода в раздел мобильных тарифов
  3.   Скриншот страницы с мобильными тарифами
  4.   Проверить наличие карточек / кнопок «Подключить»
  5-7. Прокликать кнопки «Подключить», проверить редирект, вернуться
"""

from __future__ import annotations

import allure
import pytest
from playwright.sync_api import Page, BrowserContext

from utils.helpers import (
    RunLogger,
    allure_attach_screenshot,
    step_ok,
    step_fail,
    attach_card_result,
    send_step_alert,
)

SMOKE_CARD_LIMIT = 3          # None = проверять все карточки (full run)
CARDS_APPEAR_TIMEOUT = 15_000 # мс — ожидание карточек в DOM
REDIRECT_TIMEOUT = 8_000      # мс — пауза после клика на кнопку
GOTO_TIMEOUT = 30_000         # мс — таймаут загрузки сайта

EXCLUDED_BUTTON_CLASSES = {
    "checkaddress",
    "connection",
    "profit",
    "express-connection",
}


def _fail_step(page: Page, landing: dict, logger: RunLogger, step_name: str, reason: str) -> None:
    """
    Единая точка падения шага:
      1) фиксируем в Allure/логе
      2) шлём Telegram step-alert
      3) падаем через pytest.fail
    """
    step_fail(logger, step_name, reason)
    send_step_alert(landing["name"], step_name, reason, page)
    pytest.fail(f"[{landing['name']}] {reason}")


def _allowed_redirect_types(expected_redirect_type: str) -> set[str]:
    """
    Нормализовать ожидаемый тип редиректа из конфигурации лендинга.
    """
    mapping = {
        "new_tab": {"new_tab"},
        "same_tab": {"same_tab"},
        "either": {"new_tab", "same_tab"},
        "modal": {"modal"},
        "any": {"new_tab", "same_tab", "modal"},
    }
    return mapping.get(expected_redirect_type, {"new_tab", "same_tab"})


def _validate_redirect_url(landing: dict, actual_url: str) -> str | None:
    """
    Проверить итоговый URL по опциональному правилу landing["expected_url_contains"].
    Возвращает текст причины ошибки или None.
    """
    expected_parts = landing.get("expected_url_contains") or []
    if not expected_parts:
        return None

    missing_parts = [part for part in expected_parts if part not in actual_url]
    if not missing_parts:
        return None

    return (
        f"итоговый URL '{actual_url}' не содержит ожидаемые фрагменты: "
        f"{', '.join(missing_parts)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Попапы
# ─────────────────────────────────────────────────────────────────────────────

def _dismiss_region_popup(page: Page, logger: RunLogger) -> None:
    """
    Закрыть попап выбора региона (Beeline). ВСЕГДА вызывается первым.
    Вариант 1: #yesButton («Да»)
    Вариант 2: .popup__close (крестик)
    """
    for selector, label in [("#yesButton", "«Да»"), (".popup__close", "крестик")]:
        try:
            btn = page.locator(selector).first
            btn.wait_for(state="visible", timeout=5_000)
            btn.click()
            logger.log(f"Попап региона закрыт: {label} ({selector})")
            return
        except Exception:
            pass
    logger.log("Попап региона не обнаружен — продолжаем")


def _accept_cookies(page: Page, logger: RunLogger) -> None:
    """Принять куки (#cookieAccept). Вызывается ПОСЛЕ закрытия попапа региона."""
    try:
        btn = page.locator("#cookieAccept").first
        btn.wait_for(state="visible", timeout=5_000)
        btn.click()
        logger.log("Куки приняты: #cookieAccept")
    except Exception:
        logger.log("Баннер куки не обнаружен — продолжаем")


# ─────────────────────────────────────────────────────────────────────────────
# Навигация
# ─────────────────────────────────────────────────────────────────────────────

def _open_mobile_section(page: Page, landing: dict, logger: RunLogger) -> None:
    """
    Шаг 2: найти ВИДИМЫЙ элемент навигации, проверить текст, кликнуть.

    На МТС и T2 один и тот же селектор встречается несколько раз в DOM:
    десктопный хедер (visible) + скрытые мобильное меню и микроразметка.
    Решение: берём все совпадения, фильтруем по is_visible().
    """
    nav_selector = landing["nav_selector"]
    expected_text = landing["nav_text"]
    step_name = "Шаг 2: Переход в раздел мобильных тарифов"

    with allure.step(f"Поиск элемента навигации: {nav_selector}"):
        try:
            page.wait_for_selector(nav_selector, state="attached", timeout=15_000)
        except Exception as e:
            reason = f"элемент {nav_selector} не найден в DOM"
            _fail_step(page, landing, logger, step_name, reason)

        all_nav = page.locator(nav_selector).all()
        nav_element = next((el for el in all_nav if el.is_visible()), None)

        if nav_element is None:
            reason = (
                f"элемент {nav_selector} есть в DOM ({len(all_nav)} шт.), "
                f"но все скрыты"
            )
            _fail_step(page, landing, logger, step_name, reason)

        logger.log(f"Элемент навигации найден: {nav_selector} "
                   f"({len(all_nav)} в DOM, используем видимый)")

    with allure.step(f"Проверка текста навигации: ожидается '{expected_text}'"):
        actual_text = nav_element.inner_text().strip()
        logger.log(f"Текст навигации: '{actual_text}'")
        if expected_text not in actual_text:
            reason = f"текст '{actual_text}' не содержит '{expected_text}'"
            _fail_step(page, landing, logger, step_name, reason)
        step_ok(logger, "Текст навигации", f"'{actual_text}'")

    with allure.step("Клик по элементу навигации"):
        nav_element.scroll_into_view_if_needed()
        nav_element.click()
        step_ok(logger, step_name, f"кликнут {nav_selector}")


# ─────────────────────────────────────────────────────────────────────────────
# Карточки
# ─────────────────────────────────────────────────────────────────────────────

def _is_mobile_button(button) -> bool:
    """Исключить кнопки нецелевых разделов (интернет, форма заявки и т.д.)."""
    try:
        classes = set((button.get_attribute("class") or "").split())
        return classes.isdisjoint(EXCLUDED_BUTTON_CLASSES)
    except Exception:
        return True


def _get_mobile_buttons(page: Page, card_selector: str) -> tuple[list, int, int]:
    """
    Вернуть (видимые мобильные кнопки, всего в DOM, всего после фильтра классов).
    """
    all_buttons = page.locator(card_selector).all()
    mobile = [b for b in all_buttons if _is_mobile_button(b)]
    visible = [b for b in mobile if b.is_visible()]
    return (visible if visible else mobile), len(all_buttons), len(mobile)


def _wait_for_cards(page: Page, landing: dict, logger: RunLogger) -> list:
    """Шаг 4: дождаться карточек и вернуть список для проверки."""
    card_selector = landing["card_button_selector"]
    step_name = "Шаг 4: Наличие блока мобильных тарифов"

    with allure.step(f"Ожидание карточек: {card_selector}"):
        try:
            page.wait_for_selector(card_selector, state="attached",
                                   timeout=CARDS_APPEAR_TIMEOUT)
        except Exception:
            reason = f"карточки {card_selector} не появились в DOM за {CARDS_APPEAR_TIMEOUT}мс"
            _fail_step(page, landing, logger, step_name, reason)

        cards, total_dom, total_mobile = _get_mobile_buttons(page, card_selector)
        count = len(cards)

        logger.log(
            f"Карточки: {count} для проверки "
            f"(в DOM: {total_dom}, после фильтра классов: {total_mobile}, видимых: {count})"
        )

        if count == 0:
            reason = f"после фильтрации не осталось видимых карточек. Селектор: {card_selector}"
            _fail_step(page, landing, logger, step_name, reason)

        step_ok(logger, step_name, f"найдено {count} карточек мобильных тарифов")
        allure.attach(
            f"Всего в DOM       : {total_dom}\n"
            f"После фильтра     : {total_mobile}\n"
            f"Видимых (итог)    : {count}\n",
            name="📊 Статистика карточек",
            attachment_type=allure.attachment_type.TEXT,
        )

    return cards


# ─────────────────────────────────────────────────────────────────────────────
# Редирект
# ─────────────────────────────────────────────────────────────────────────────

def _modal_appeared(page: Page, logger: RunLogger, card_index: int) -> bool:
    """Проверить появление модального окна после клика (таймаут 2 сек)."""
    modal_selectors = [
        ".popup:not(#cookieCloud):not(.popup-select-region__content-wrapper)",
        ".modal",
        "[class*='popup']:not(#cookieCloud)",
        ".connection_address_popup",
        ".card-popup",
        "[class*='modal']",
    ]
    for sel in modal_selectors:
        try:
            page.locator(sel).first.wait_for(state="visible", timeout=2_000)
            logger.log(f"Карточка #{card_index + 1}: модалка {sel} — валидный результат")
            return True
        except Exception:
            continue
    return False


def _close_modal(page: Page, logger: RunLogger, card_index: int) -> None:
    """Закрыть модальное окно (крестики → Escape)."""
    for sel in [".popup__close", ".modal__close", "[class*='close']",
                "button[aria-label='Close']", "button[aria-label='Закрыть']"]:
        try:
            btn = page.locator(sel).first
            btn.wait_for(state="visible", timeout=1_000)
            btn.click()
            logger.log(f"Карточка #{card_index + 1}: модалка закрыта ({sel})")
            return
        except Exception:
            continue
    page.keyboard.press("Escape")
    logger.log(f"Карточка #{card_index + 1}: модалка закрыта (Escape)")


def _check_card_button(
    page: Page,
    context: BrowserContext,
    landing: dict,
    card_index: int,
    logger: RunLogger,
) -> None:
    """
    Шаги 5-7: кликнуть кнопку «Подключить», зафиксировать результат,
    вернуться к списку карточек.

    Возможные исходы после клика:
      1. Новая вкладка           → проверить URL, закрыть вкладку
      2. Редирект в текущей      → зафиксировать URL, вернуться назад
      3. Модальное окно          → зафиксировать как валидный результат, закрыть
      4. Ничего не произошло     → тест падает
    """
    card_selector = landing["card_button_selector"]
    url_before = page.url
    step_name = f"Карточка #{card_index + 1}: кнопка «Подключить»"
    expected_redirect_type = landing.get("expected_redirect_type", "either")
    allowed_redirect_types = _allowed_redirect_types(expected_redirect_type)

    cards, _, _ = _get_mobile_buttons(page, card_selector)

    if card_index >= len(cards):
        reason = f"карточка #{card_index + 1} не найдена (доступно {len(cards)})"
        _fail_step(page, landing, logger, step_name, reason)

    button = cards[card_index]
    href = button.get_attribute("href") or "нет href"
    logger.log(f"Карточка #{card_index + 1}: href='{href}', URL='{url_before}'")

    with allure.step(step_name):
        pages_before = set(context.pages)
        button.scroll_into_view_if_needed()
        button.click()
        page.wait_for_timeout(REDIRECT_TIMEOUT)

        pages_after = set(context.pages)
        new_pages = list(pages_after - pages_before)

        if new_pages:
            # ── Случай 1: новая вкладка ───────────────────────────────────────
            new_page = new_pages[-1]
            try:
                new_page.wait_for_load_state("domcontentloaded",
                                             timeout=REDIRECT_TIMEOUT)
            except Exception:
                pass
            new_url = new_page.url

            if new_url in ("about:blank", ""):
                attach_card_result(card_index, href, url_before, new_url,
                                   "new_tab", "❌ FAILED")
                reason = f"новая вкладка пустая (about:blank). href='{href}'"
                new_page.close()
                _fail_step(page, landing, logger, step_name, reason)

            if "new_tab" not in allowed_redirect_types:
                attach_card_result(card_index, href, url_before, new_url,
                                   "new_tab", "❌ FAILED")
                reason = (
                    f"получен redirect_type='new_tab', ожидается '{expected_redirect_type}'"
                )
                new_page.close()
                _fail_step(page, landing, logger, step_name, reason)

            url_validation_error = _validate_redirect_url(landing, new_url)
            if url_validation_error:
                attach_card_result(card_index, href, url_before, new_url,
                                   "new_tab", "❌ FAILED")
                new_page.close()
                _fail_step(page, landing, logger, step_name, url_validation_error)

            attach_card_result(card_index, href, url_before, new_url,
                               "new_tab", "✅ PASSED")
            step_ok(logger, step_name, f"новая вкладка → {new_url}")
            new_page.close()

        elif page.url != url_before:
            # ── Случай 2: редирект в текущей вкладке ─────────────────────────
            url_after = page.url
            if "same_tab" not in allowed_redirect_types:
                attach_card_result(card_index, href, url_before, url_after,
                                   "same_tab", "❌ FAILED")
                reason = (
                    f"получен redirect_type='same_tab', ожидается '{expected_redirect_type}'"
                )
                _fail_step(page, landing, logger, step_name, reason)

            url_validation_error = _validate_redirect_url(landing, url_after)
            if url_validation_error:
                attach_card_result(card_index, href, url_before, url_after,
                                   "same_tab", "❌ FAILED")
                _fail_step(page, landing, logger, step_name, url_validation_error)

            attach_card_result(card_index, href, url_before, url_after,
                               "same_tab", "✅ PASSED")
            step_ok(logger, step_name,
                    f"редирект в текущей вкладке → {url_after}")
            _navigate_back_and_reopen(page, landing, logger)

        elif _modal_appeared(page, logger, card_index):
            # ── Случай 3: модальное окно ──────────────────────────────────────
            if "modal" not in allowed_redirect_types:
                attach_card_result(card_index, href, url_before, url_before,
                                   "modal", "❌ FAILED")
                reason = (
                    f"получен redirect_type='modal', ожидается '{expected_redirect_type}'"
                )
                _close_modal(page, logger, card_index)
                _fail_step(page, landing, logger, step_name, reason)

            attach_card_result(card_index, href, url_before, url_before,
                               "modal", "⚠️ MODAL (форма на странице)")
            step_ok(logger, step_name, "открылась модалка с формой заявки")
            _close_modal(page, logger, card_index)

        else:
            # ── Случай 4: ничего не произошло ────────────────────────────────
            attach_card_result(card_index, href, url_before, page.url,
                               "none", "❌ FAILED")
            reason = f"кнопка не инициировала редирект. href='{href}'"
            _fail_step(page, landing, logger, step_name, reason)


def _navigate_back_and_reopen(page: Page, landing: dict, logger: RunLogger) -> None:
    """Вернуться на лендинг и повторно открыть мобильный раздел."""
    logger.log("Возврат назад после редиректа в текущей вкладке")
    page.go_back()
    page.wait_for_load_state("domcontentloaded", timeout=15_000)
    _dismiss_region_popup(page, logger)
    _accept_cookies(page, logger)

    try:
        all_nav = page.locator(landing["nav_selector"]).all()
        nav = next((el for el in all_nav if el.is_visible()), None)
        if nav:
            nav.scroll_into_view_if_needed()
            nav.click()
            page.wait_for_selector(
                landing["card_button_selector"], state="attached",
                timeout=CARDS_APPEAR_TIMEOUT,
            )
            logger.log("Мобильный раздел повторно открыт после возврата")
    except Exception as e:
        logger.log(f"Предупреждение: не удалось повторно открыть раздел: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Основной тест
# ─────────────────────────────────────────────────────────────────────────────

@allure.feature("Мобильные тарифы на лендингах")
@allure.story("Проверка блока мобильных тарифов")
@pytest.mark.mobile_tariffs
def test_mobile_tariffs(landing: dict, browser_context: BrowserContext) -> None:
    """
    Сквозной smoke-тест для одного лендинга из LANDINGS.
    Параметр landing — через pytest_generate_tests (conftest.py).
    """
    allure.dynamic.title(f"Мобильные тарифы: {landing['name']}")
    allure.dynamic.description(
        f"URL      : {landing['url']}\n"
        f"Навигация: {landing['nav_selector']}\n"
        f"Карточки : {landing['card_button_selector']}\n"
        f"Примечание: {landing['comment']}"
    )

    logger = RunLogger(landing["name"])
    logger.log(f"=== СТАРТ ТЕСТА: {landing['name']} ===")
    logger.log(f"URL: {landing['url']}")

    page: Page = browser_context.new_page()

    try:
        # ── ШАГ 1: Открыть сайт ──────────────────────────────────────────────
        with allure.step(f"Шаг 1: Открыть сайт {landing['url']}"):
            try:
                page.goto(landing["url"], wait_until="domcontentloaded",
                          timeout=GOTO_TIMEOUT)
            except Exception as e:
                reason = f"сайт недоступен: {e}"
                _fail_step(page, landing, logger, "Шаг 1: Открыть сайт", reason)
            step_ok(logger, "Шаг 1: Открыть сайт", f"текущий URL: {page.url}")

        # ── ШАГ 1.5: Попап региона (Beeline) — ПЕРВЫМ ────────────────────────
        with allure.step("Шаг 1.5: Закрыть попап выбора региона"):
            _dismiss_region_popup(page, logger)

        # ── ШАГ 1.6: Принять куки ────────────────────────────────────────────
        with allure.step("Шаг 1.6: Принять куки"):
            _accept_cookies(page, logger)

        # ── ШАГ 2: Навигация в мобильный раздел ──────────────────────────────
        with allure.step("Шаг 2: Перейти в раздел мобильных тарифов"):
            _open_mobile_section(page, landing, logger)

        # ── ШАГ 3: Скриншот ───────────────────────────────────────────────────
        with allure.step("Шаг 3: Скриншот мобильного раздела"):
            page.wait_for_timeout(1_000)
            shot_name = f"{landing['name'].replace(' ', '_')}_mobile_tariffs_opened"
            allure_attach_screenshot(page, shot_name)
            step_ok(logger, "Шаг 3: Скриншот", shot_name)

        # ── ШАГ 4: Наличие карточек ───────────────────────────────────────────
        with allure.step("Шаг 4: Проверить наличие блока мобильных тарифов"):
            cards = _wait_for_cards(page, landing, logger)
            total_cards = len(cards)

        # ── ШАГИ 5-7: Кнопки «Подключить» ────────────────────────────────────
        limit = SMOKE_CARD_LIMIT if SMOKE_CARD_LIMIT else total_cards
        cards_to_check = min(limit, total_cards)

        logger.log(
            f"Проверяем {cards_to_check} из {total_cards} карточек "
            f"({'smoke' if SMOKE_CARD_LIMIT else 'full run'})"
        )

        with allure.step(
            f"Шаги 5-7: Кнопки «Подключить» — {cards_to_check} шт. "
            f"({'smoke' if SMOKE_CARD_LIMIT else 'full'})"
        ):
            passed = 0
            for idx in range(cards_to_check):
                with allure.step(f"Карточка #{idx + 1} из {cards_to_check}"):
                    _check_card_button(
                        page, browser_context, landing, idx, logger
                    )
                    passed += 1

            step_ok(
                logger,
                "Шаги 5-7: Кнопки «Подключить»",
                f"проверено {passed}/{cards_to_check}, все редиректы успешны",
            )

        # ── Итог ─────────────────────────────────────────────────────────────
        summary = (
            f"Лендинг       : {landing['name']}\n"
            f"URL           : {landing['url']}\n"
            f"Карточек всего: {total_cards}\n"
            f"Проверено     : {cards_to_check}\n"
            f"Результат     : ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ\n"
        )
        allure.attach(
            summary,
            name="📋 Итог теста",
            attachment_type=allure.attachment_type.TEXT,
        )
        logger.log(f"=== ТЕСТ ПРОЙДЕН: {landing['name']} ===")

    except Exception as exc:
        # При любом падении — финальный скриншот + итог с причиной
        send_step_alert(
            landing["name"],
            "Непредвиденное падение теста",
            str(exc),
            page,
        )
        allure_attach_screenshot(
            page, f"{landing['name'].replace(' ', '_')}_FAIL"
        )
        summary = (
            f"Лендинг  : {landing['name']}\n"
            f"URL      : {landing['url']}\n"
            f"Результат: ❌ ТЕСТ УПАЛ\n"
            f"Причина  : {exc}\n"
        )
        allure.attach(
            summary,
            name="❌ Итог теста — ПАДЕНИЕ",
            attachment_type=allure.attachment_type.TEXT,
        )
        logger.log(f"=== ТЕСТ УПАЛ: {exc} ===")
        raise

    finally:
        logger.attach_to_allure()
        page.close()
