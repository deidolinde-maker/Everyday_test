from pathlib import Path
import json
import os

RESULTS_DIR   = Path(os.getenv("ALLURE_RESULTS_DIR", "allure-results"))
RUN_URL       = os.getenv("RUN_URL", "").strip()
ALLURE_URL    = os.getenv("ALLURE_URL", "").strip()
SITE_HINT     = os.getenv("SITE_HINT", "").strip()

OUT_MESSAGE_FILE = Path("telegram_message.txt")
OUT_FLAG_FILE    = Path("telegram_should_send.txt")


def normalize_text(value: str, max_len: int = 200) -> str:
    value = " ".join((value or "").split()).strip()
    if len(value) > max_len:
        return value[:max_len - 3] + "..."
    return value


def collect_results(results_dir: Path) -> tuple[int, int, list[dict]]:
    passed = 0
    failed_list = []

    if not results_dir.exists():
        return 0, 0, []

    for path in results_dir.glob("*-result.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        status = (data.get("status") or "").strip().lower()
        if status == "passed":
            passed += 1
        elif status in {"failed", "broken"}:
            name    = normalize_text(data.get("name") or path.name)
            details = data.get("statusDetails") or {}
            message = normalize_text(details.get("message") or "без текста ошибки")
            failed_list.append({"name": name, "message": message})

    return passed, len(failed_list), failed_list


def build_summary(passed: int, failed: int, failed_list: list[dict]) -> str:
    # Заголовок зависит от результата
    if failed == 0:
        header = "✅ Прогон завершён успешно"
    else:
        header = "❌ Прогон завершён с ошибками"

    lines = [header, ""]

    if SITE_HINT:
        lines.append(f"Сайт: {SITE_HINT}")
        lines.append("")

    lines.append(f"✅ Успешно: {passed}")
    lines.append(f"❌ Упало: {failed}")

    if failed_list:
        lines.append("")
        lines.append("Упавшие тесты:")
        for item in failed_list[:5]:
            lines.append(f"  • {item['name']}")
        if len(failed_list) > 5:
            lines.append(f"  ... и ещё {len(failed_list) - 5}")

    lines.append("")
    if RUN_URL:
        lines.append(f"Run: {RUN_URL}")
    if ALLURE_URL:
        lines.append(f"Allure: {ALLURE_URL}")

    return "\n".join(lines).strip()


def main() -> int:
    passed, failed, failed_list = collect_results(RESULTS_DIR)

    message = build_summary(passed, failed, failed_list)

    # Всегда шлём — и при успехе и при падении
    OUT_FLAG_FILE.write_text("1", encoding="utf-8")
    OUT_MESSAGE_FILE.write_text(message, encoding="utf-8")
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
