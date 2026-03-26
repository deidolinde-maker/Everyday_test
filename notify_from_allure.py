from pathlib import Path
import json
import os
import sys

RESULTS_DIR = Path(os.getenv("ALLURE_RESULTS_DIR", "allure-results"))
RUN_URL = os.getenv("RUN_URL", "").strip()
ALLURE_URL = os.getenv("ALLURE_URL", "").strip()
SITE_HINT = os.getenv("SITE_HINT", "").strip()

OUT_MESSAGE_FILE = Path("telegram_message.txt")
OUT_FLAG_FILE = Path("telegram_should_send.txt")


def normalize_text(value: str, max_len: int = 350) -> str:
    value = " ".join((value or "").split()).strip()
    if len(value) > max_len:
        return value[: max_len - 3] + "..."
    return value


def extract_site_hint_from_labels(data: dict) -> str:
    labels = data.get("labels") or []
    for label in labels:
        if not isinstance(label, dict):
            continue
        name = (label.get("name") or "").strip().lower()
        value = (label.get("value") or "").strip()
        if name in {"host", "site", "domain"} and value:
            return value
    return ""


def collect_failed_results(results_dir: Path) -> list[dict]:
    failed = []

    if not results_dir.exists():
        return failed

    for path in results_dir.glob("*-result.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        status = (data.get("status") or "").strip().lower()
        if status not in {"failed", "broken"}:
            continue

        name = data.get("name") or data.get("fullName") or path.name
        details = data.get("statusDetails") or {}

        message = normalize_text(details.get("message") or "без текста ошибки")
        trace = normalize_text(details.get("trace") or "", max_len=500)
        site = SITE_HINT or extract_site_hint_from_labels(data)

        failed.append(
            {
                "name": normalize_text(str(name), max_len=200),
                "status": status,
                "message": message,
                "trace": trace,
                "site": site,
            }
        )

    return failed


def build_message(failed: list[dict]) -> str:
    first = failed[0]

    lines = ["❌ Упал ежедневный автотест,проверь!"]

    if first["site"]:
        lines.append(f"Сайт: {first['site']}")

    lines.append(f"Тест: {first['name']}")
    lines.append(f"Статус: {first['status']}")
    lines.append(f"Ошибка: {first['message']}")

    if RUN_URL:
        lines.append(f"Run: {RUN_URL}")

    if ALLURE_URL:
        lines.append(f"Allure: {ALLURE_URL}")

    return "\n".join(lines).strip()


def main() -> int:
    failed = collect_failed_results(RESULTS_DIR)

    if not failed:
        OUT_FLAG_FILE.write_text("0", encoding="utf-8")
        OUT_MESSAGE_FILE.write_text("", encoding="utf-8")
        print("No failed/broken tests in allure-results")
        return 0

    message = build_message(failed)
    OUT_FLAG_FILE.write_text("1", encoding="utf-8")
    OUT_MESSAGE_FILE.write_text(message, encoding="utf-8")
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
