from __future__ import annotations

import json
import os
from pathlib import Path

import requests


RESULTS_DIR = Path(os.getenv("ALLURE_RESULTS_DIR", "allure-results"))
RUN_URL = os.getenv("RUN_URL", "").strip()
ALLURE_URL = os.getenv("ALLURE_URL", "").strip()


def _collect() -> tuple[int, int, int, list[str]]:
    passed = 0
    failed = 0
    skipped = 0
    failed_names: list[str] = []

    if not RESULTS_DIR.exists():
        return passed, failed, skipped, failed_names

    for file in RESULTS_DIR.glob("*-result.json"):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            continue

        status = (data.get("status") or "").strip().lower()
        name = (data.get("name") or data.get("fullName") or file.name).strip()

        if status == "passed":
            passed += 1
        elif status in {"failed", "broken"}:
            failed += 1
            failed_names.append(name)
        elif status == "skipped":
            skipped += 1

    return passed, failed, skipped, failed_names


def _send(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("[TELEGRAM][summary] Пропуск отправки: переменные окружения не заданы")
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as exc:
        print(f"[TELEGRAM][summary] Исключение при отправке: {exc}")
        return False

    if resp.ok:
        print(f"[TELEGRAM][summary] Успешно отправлено (status={resp.status_code})")
        return True

    body = (resp.text or "").replace("\n", " ").strip()
    print(f"[TELEGRAM][summary] Ошибка отправки (status={resp.status_code}): {body[:180]}")
    return False


def main() -> int:
    passed, failed, skipped, failed_names = _collect()
    total = passed + failed + skipped

    status_line = "✅ Прогон завершён успешно" if failed == 0 else "❌ Прогон завершён с ошибками"
    lines = [
        status_line,
        "",
        f"Всего: {total}",
        f"✅ Успешно: {passed}",
        f"❌ Упало: {failed}",
        f"⚪ Пропущено: {skipped}",
    ]

    if failed_names:
        lines.append("")
        lines.append("Упавшие тесты:")
        for name in failed_names[:5]:
            lines.append(f"- {name}")

    if RUN_URL:
        lines.append("")
        lines.append(f"Run: {RUN_URL}")
    if ALLURE_URL:
        lines.append(f"Allure: {ALLURE_URL}")

    message = "\n".join(lines)
    print(message)
    _send(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
