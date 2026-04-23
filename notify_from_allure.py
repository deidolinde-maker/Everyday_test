from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import json
import os
import re
import sys


RESULTS_DIR = Path(os.getenv("ALLURE_RESULTS_DIR", "allure-results"))
RUN_URL = os.getenv("RUN_URL", "").strip()
ALLURE_URL = os.getenv("ALLURE_URL", "").strip()
SITE_HINT = os.getenv("SITE_HINT", "").strip()

OUT_MESSAGE_FILE = Path("telegram_message.txt")
OUT_FLAG_FILE = Path("telegram_should_send.txt")

STATE_FILE = Path(os.getenv("NOTIFY_STATE_FILE", "notify_state.json"))
STATE_URL = os.getenv("NOTIFY_STATE_URL", "").strip()

NORMAL_ALERT_MAX_PER_SITE = 5
MASS_ALERT_SITE_THRESHOLD = 5
MAX_MESSAGE_LEN = 3600

try:
    # Avoid UnicodeEncodeError on Windows consoles with cp1251.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def env_bool(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


ALERT_ERRORS_ENABLED = env_bool("ALERT_ERRORS_ENABLED", True)
ALERT_AGGREGATES_ENABLED = env_bool("ALERT_AGGREGATES_ENABLED", True)
ALERT_SUMMARY_ENABLED = env_bool("ALERT_SUMMARY_ENABLED", True)
ALERT_RECOVERED_ENABLED = env_bool("ALERT_RECOVERED_ENABLED", True)


def normalize_text(value: str, max_len: int = 220) -> str:
    text = " ".join((value or "").split()).strip()
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def normalize_site_label(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return SITE_HINT or "unknown-site"

    if not raw.startswith(("http://", "https://")):
        return raw.strip("/")

    parsed = urlsplit(raw)
    host = (parsed.netloc or "").strip().lower()
    if host:
        return host
    return raw.strip("/")


def parse_site_from_site_cfg(value: str) -> str:
    if not value:
        return ""
    match = re.search(r"['\"]base_url['\"]\s*:\s*['\"]([^'\"]+)['\"]", value)
    if not match:
        return ""
    return normalize_site_label(match.group(1))


def parse_site_from_test_name(name: str) -> str:
    if not name:
        return ""
    match = re.search(r"https?://[^\s\]]+", name)
    if not match:
        return ""
    return normalize_site_label(match.group(0))


def extract_site_label(data: dict) -> str:
    for param in data.get("parameters") or []:
        if (param.get("name") or "").strip() == "site_cfg":
            parsed = parse_site_from_site_cfg(str(param.get("value") or ""))
            if parsed:
                return parsed

    parsed_from_name = parse_site_from_test_name(str(data.get("name") or ""))
    if parsed_from_name:
        return parsed_from_name

    return normalize_site_label(SITE_HINT or "unknown-site")


def extract_browser_name(data: dict) -> str:
    for param in data.get("parameters") or []:
        if (param.get("name") or "").strip() == "browser_name":
            return normalize_text(str(param.get("value") or "").strip("'\""), max_len=40)
    return ""


def collect_results(results_dir: Path) -> tuple[int, list[dict]]:
    passed = 0
    failed_records: list[dict] = []

    if not results_dir.exists():
        return 0, []

    for path in results_dir.glob("*-result.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        status = (data.get("status") or "").strip().lower()
        if status == "passed":
            passed += 1
            continue
        if status not in {"failed", "broken"}:
            continue

        details = data.get("statusDetails") or {}
        failed_records.append(
            {
                "site": extract_site_label(data),
                "name": normalize_text(data.get("name") or path.name, max_len=180),
                "message": normalize_text(details.get("message") or "без текста ошибки", max_len=240),
                "browser": extract_browser_name(data),
            }
        )

    return passed, failed_records


def group_failed_by_site(failed_records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for record in failed_records:
        grouped.setdefault(record["site"], []).append(record)
    return grouped


def load_json_from_url(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "everyday-test-notify"})
    with urlopen(req, timeout=8) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def load_previous_failed_sites() -> set[str]:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return set(data.get("failed_sites") or [])
    except Exception:
        pass

    if not STATE_URL:
        return set()

    try:
        data = load_json_from_url(STATE_URL)
        return set(data.get("failed_sites") or [])
    except Exception:
        return set()


def save_current_failed_sites(failed_sites: set[str]) -> None:
    payload = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "failed_sites": sorted(failed_sites),
    }
    try:
        if STATE_FILE.parent:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def append_site_lines(lines: list[str], sites: list[tuple[str, list[dict]]]) -> None:
    for site, items in sites:
        count = len(items)
        browsers = sorted({item.get("browser") for item in items if item.get("browser")})
        browsers_text = f" | браузеры: {', '.join(browsers)}" if browsers else ""
        sample = normalize_text(items[0].get("message") or items[0].get("name") or "без деталей", max_len=180)
        lines.append(f"• {site} — {count} падений{browsers_text}")
        lines.append(f"  пример: {sample}")


def trim_message(message: str, max_len: int = MAX_MESSAGE_LEN) -> str:
    if len(message) <= max_len:
        return message
    return message[: max_len - 15].rstrip() + "\n... (обрезано)"


def build_summary(
    passed: int,
    failed_records: list[dict],
    resolved_sites: list[str],
) -> tuple[str, bool]:
    failed_total = len(failed_records)
    grouped = group_failed_by_site(failed_records)
    failed_sites_count = len(grouped)

    lines: list[str] = []
    has_any_category_output = False

    if failed_total == 0:
        header = "✅ Прогон завершён успешно"
    else:
        header = "❌ Прогон завершён с ошибками"

    if ALERT_SUMMARY_ENABLED:
        has_any_category_output = True
        lines.extend([header, ""])
        if SITE_HINT:
            lines.append(f"Сайт (input): {SITE_HINT}")
            lines.append("")
        lines.append(f"✅ Успешно: {passed}")
        lines.append(f"❌ Упало: {failed_total}")
        lines.append(f"🌐 Лендингов с ошибками: {failed_sites_count}")

    if failed_total > 0:
        sorted_sites = sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True)
        regular_sites = [(site, items) for site, items in sorted_sites if len(items) <= NORMAL_ALERT_MAX_PER_SITE]
        aggregated_sites = [(site, items) for site, items in sorted_sites if len(items) > NORMAL_ALERT_MAX_PER_SITE]

        if ALERT_AGGREGATES_ENABLED and failed_sites_count > MASS_ALERT_SITE_THRESHOLD:
            has_any_category_output = True
            lines.append("")
            lines.append(
                f"🚨 Массовая ошибка: {failed_sites_count} лендингов имеют падения (всего {failed_total} ошибок)."
            )

        if ALERT_ERRORS_ENABLED and regular_sites:
            has_any_category_output = True
            lines.append("")
            lines.append("Точечные алерты (1–5 падений на лендинг):")
            append_site_lines(lines, regular_sites)

        if ALERT_AGGREGATES_ENABLED and aggregated_sites:
            has_any_category_output = True
            lines.append("")
            lines.append("Агрегированные алерты (>5 падений на лендинг):")
            append_site_lines(lines, aggregated_sites)

    if ALERT_RECOVERED_ENABLED and resolved_sites:
        has_any_category_output = True
        lines.append("")
        lines.append("✅ Исправлено после восстановления:")
        for site in resolved_sites[:10]:
            lines.append(f"• {site}")
        if len(resolved_sites) > 10:
            lines.append(f"... и ещё {len(resolved_sites) - 10}")

    if has_any_category_output:
        lines.append("")
        if RUN_URL:
            lines.append(f"Run: {RUN_URL}")
        if ALLURE_URL:
            lines.append(f"Allure: {ALLURE_URL}")

    return trim_message("\n".join(lines).strip()), has_any_category_output


def main() -> int:
    passed, failed_records = collect_results(RESULTS_DIR)
    current_failed_sites = {record["site"] for record in failed_records if record.get("site")}
    previous_failed_sites = load_previous_failed_sites()
    resolved_sites = sorted(previous_failed_sites - current_failed_sites)

    message, should_send = build_summary(passed, failed_records, resolved_sites)
    save_current_failed_sites(current_failed_sites)

    OUT_FLAG_FILE.write_text("1" if should_send else "0", encoding="utf-8")
    OUT_MESSAGE_FILE.write_text(message, encoding="utf-8")
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
