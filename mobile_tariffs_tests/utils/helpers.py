"""
Вспомогательные утилиты:
  - RunLogger          — накапливает строки лога теста, крепит их в Allure
  - allure_attach_screenshot — делает full-page скриншот и крепит в Allure
  - step_ok / step_fail      — единообразное оформление итога шага в Allure
"""

from __future__ import annotations

import allure
import os
from datetime import datetime

import requests
from playwright.sync_api import Page


class RunLogger:
    """Простой аккумулятор строк лога для одного теста."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._lines: list[str] = []

    def log(self, message: str) -> None:
        line = f"[{self._name}] {message}"
        self._lines.append(line)
        print(line)

    def attach_to_allure(self) -> None:
        full_log = "\n".join(self._lines)
        allure.attach(
            full_log,
            name="📋 Полный лог теста",
            attachment_type=allure.attachment_type.TEXT,
        )


def allure_attach_screenshot(page: Page, name: str) -> None:
    screenshot_bytes = page.screenshot(full_page=True)
    allure.attach(
        screenshot_bytes,
        name=name,
        attachment_type=allure.attachment_type.PNG,
    )


def step_ok(logger: RunLogger, step: str, detail: str = "") -> None:
    """
    Зафиксировать успешный результат шага:
      - в лог теста
      - как текстовое вложение в Allure с иконкой ✅
    """
    msg = f"✅ {step}" + (f" — {detail}" if detail else "")
    logger.log(msg)
    allure.attach(
        msg,
        name=f"✅ {step}",
        attachment_type=allure.attachment_type.TEXT,
    )


def step_fail(logger: RunLogger, step: str, reason: str) -> None:
    """
    Зафиксировать причину падения шага:
      - в лог теста
      - как текстовое вложение в Allure с иконкой ❌
    Не вызывает pytest.fail — только фиксирует. Падение вызывает вызывающий код.
    """
    msg = f"❌ {step} — ПРИЧИНА: {reason}"
    logger.log(msg)
    allure.attach(
        msg,
        name=f"❌ {step}",
        attachment_type=allure.attachment_type.TEXT,
    )


def attach_card_result(
    card_index: int,
    href: str,
    url_before: str,
    url_after: str,
    redirect_type: str,
    status: str,
) -> None:
    """
    Прикрепить подробную карточку результата проверки кнопки в Allure.

    status: '✅ PASSED' | '❌ FAILED' | '⚠️ MODAL'
    redirect_type: 'new_tab' | 'same_tab' | 'modal' | 'none'
    """
    report = (
        f"Карточка #{card_index + 1}\n"
        f"{'─' * 40}\n"
        f"  href          : {href}\n"
        f"  URL до клика  : {url_before}\n"
        f"  URL после     : {url_after}\n"
        f"  Тип перехода  : {redirect_type}\n"
        f"  Результат     : {status}\n"
    )
    allure.attach(
        report,
        name=f"{status} Карточка #{card_index + 1}",
        attachment_type=allure.attachment_type.TEXT,
    )


def send_telegram_alert(text: str, alert_type: str = "step") -> bool:
    """
    Отправить сообщение в Telegram.
    Возвращает True/False и пишет диагностические логи отправки.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        print(f"[TELEGRAM][{alert_type}] Пропуск отправки: переменные окружения не заданы")
        return False

    print(f"[TELEGRAM][{alert_type}] Попытка отправки")
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as exc:
        print(f"[TELEGRAM][{alert_type}] Исключение при отправке: {exc}")
        return False

    if resp.ok:
        print(f"[TELEGRAM][{alert_type}] Успешно отправлено (status={resp.status_code})")
        return True

    body = (resp.text or "").strip().replace("\n", " ")
    print(f"[TELEGRAM][{alert_type}] Ошибка отправки (status={resp.status_code}): {body[:180]}")
    return False


def send_step_alert(
    landing_name: str,
    step_name: str,
    reason: str,
    page: Page | None = None,
) -> bool:
    """
    Отправить шаговый alert по падению конкретного шага.
    """
    url = page.url if page else ""
    run_url = os.getenv("RUN_URL", "").strip()
    now = datetime.now().strftime("%H:%M:%S")

    lines = [
        f"❌ [{landing_name}] {step_name} — failed",
        "Статус: failed",
        f"Причина: {reason}",
        f"URL: {url}",
        f"Время: {now}",
    ]
    if run_url:
        lines.append(f"Run: {run_url}")

    return send_telegram_alert("\n".join(lines), alert_type="step")
