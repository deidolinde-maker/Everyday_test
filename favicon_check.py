"""HTTP smoke-check for favicon links on all configured landing pages."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from config.providers import PROVIDER_MODULES
from test_universal2 import send_telegram_alert


USER_AGENT = "Everyday_test/favicon-check"
LANDING_TIMEOUT_SECONDS = 20
LANDING_ATTEMPTS = 3
LANDING_RETRY_DELAY_SECONDS = 1
FAVICON_TIMEOUT_SECONDS = 15
SUPPORTED_CONTENT_TYPES = {
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/svg+xml",
    "image/vnd.microsoft.icon",
    "image/x-icon",
}
FAVICON_REL_VALUES = {"icon", "shortcut", "apple-touch-icon", "apple-touch-icon-precomposed"}


class FaviconLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_head = False
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "head":
            self._in_head = True
            return
        if not self._in_head or tag != "link":
            return

        data = {str(key).lower(): str(value or "").strip() for key, value in attrs}
        rel_values = {value.lower() for value in data.get("rel", "").split()}
        if rel_values.intersection(FAVICON_REL_VALUES) and data.get("href"):
            self.links.append(
                {
                    "href": data["href"],
                    "rel": data.get("rel", ""),
                    "type": data.get("type", "").lower(),
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "head":
            self._in_head = False


def _site_inventory() -> list[dict[str, object]]:
    sites: list[dict[str, object]] = []
    seen: set[str] = set()
    for provider_name, module in PROVIDER_MODULES.items():
        for raw_site in module.SITES:
            base_url = str(raw_site.get("base_url", "")).strip()
            if not base_url:
                continue
            site_id = base_url.rstrip("/").split("//", 1)[-1].lower()
            if site_id in seen:
                continue
            seen.add(site_id)
            sites.append(
                {
                    "site_id": site_id,
                    "base_url": base_url,
                    "provider": provider_name,
                    "enabled": raw_site.get("enabled", True) is not False,
                }
            )
    return sites


def _check_favicon(session: requests.Session, site: dict[str, object]) -> dict[str, object]:
    base_url = str(site["base_url"])
    result: dict[str, object] = {
        **site,
        "status": "failed",
        "favicon_url": None,
        "reason": None,
        "landing_http_status": None,
        "landing_response_url": None,
        "landing_content_length": 0,
        "landing_html_sha256": None,
        "landing_head_preview": "",
        "landing_attempts": 0,
        "detected_favicon_links": [],
        "detected_favicon_rel_values": [],
    }

    landing = None
    parser = None
    for attempt in range(1, LANDING_ATTEMPTS + 1):
        result["landing_attempts"] = attempt
        try:
            landing = session.get(
                base_url,
                headers={"User-Agent": USER_AGENT},
                timeout=LANDING_TIMEOUT_SECONDS,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            result["reason"] = f"landing_request_failed: {exc.__class__.__name__}"
            if attempt < LANDING_ATTEMPTS:
                time.sleep(LANDING_RETRY_DELAY_SECONDS)
                continue
            return result

        result["landing_http_status"] = landing.status_code
        result["landing_response_url"] = landing.url
        result["landing_content_length"] = len(landing.content)
        result["landing_html_sha256"] = hashlib.sha256(landing.content).hexdigest()
        head_match = re.search(r"<head\b[^>]*>(.*?)</head\s*>", landing.text, flags=re.IGNORECASE | re.DOTALL)
        if head_match:
            result["landing_head_preview"] = re.sub(r"\s+", " ", head_match.group(1)).strip()[:2000]
        if landing.status_code != 200:
            result["reason"] = f"landing_http_{landing.status_code}"
        else:
            parser = FaviconLinkParser()
            try:
                parser.feed(landing.text)
            except Exception as exc:
                result["reason"] = f"html_parse_failed: {exc.__class__.__name__}"
            else:
                result["detected_favicon_links"] = [link["href"] for link in parser.links]
                result["detected_favicon_rel_values"] = [link["rel"] for link in parser.links]
                if parser.links:
                    break
                result["reason"] = "favicon_link_missing_in_head"

        if attempt < LANDING_ATTEMPTS:
            time.sleep(LANDING_RETRY_DELAY_SECONDS)

    if not parser or not parser.links or not landing or landing.status_code != 200:
        return result

    reasons: list[str] = []
    for link in parser.links:
        href = link["href"]
        if href.startswith(("data:", "blob:", "javascript:")):
            reasons.append("unsupported_favicon_scheme")
            continue

        favicon_url = urljoin(landing.url, href)
        result["favicon_url"] = favicon_url
        parsed = urlsplit(favicon_url)
        if parsed.scheme not in {"http", "https"}:
            reasons.append("favicon_url_not_http")
            continue

        try:
            icon = session.get(
                favicon_url,
                headers={"User-Agent": USER_AGENT},
                timeout=FAVICON_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            reasons.append(f"favicon_request_failed: {exc.__class__.__name__}")
            continue

        if icon.status_code != 200:
            reasons.append(f"favicon_http_{icon.status_code}")
            continue
        if not icon.content:
            reasons.append("favicon_empty_response")
            continue

        content_type = icon.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        declared_type = link.get("type", "").split(";", 1)[0].strip().lower()
        if content_type not in SUPPORTED_CONTENT_TYPES and declared_type not in SUPPORTED_CONTENT_TYPES:
            reasons.append(f"favicon_content_type_invalid: {content_type or 'missing'}")
            continue

        result["status"] = "passed"
        result["reason"] = None
        return result

    result["reason"] = "; ".join(reasons) or "favicon_resource_invalid"
    return result


def _write_allure_results(results: list[dict[str, object]], results_dir: str) -> None:
    """Write one inspectable Allure test case for every checked landing."""
    output_dir = Path(results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    now_ms = int(time.time() * 1000)

    for item in results:
        test_uuid = str(uuid.uuid4())
        status = str(item["status"])
        site_id = str(item["site_id"])
        base_url = str(item["base_url"])
        favicon_url = item.get("favicon_url")
        reason = item.get("reason")
        links = [{"name": "Landing page", "url": base_url, "type": "custom"}]
        if favicon_url:
            links.append({"name": "Favicon resource", "url": str(favicon_url), "type": "custom"})

        payload = {
            "name": f"Favicon: {base_url}",
            "fullName": f"favicon_check::{site_id}",
            "status": status,
            "statusDetails": {"message": str(reason)} if reason else {},
            "start": now_ms,
            "stop": int(time.time() * 1000),
            "uuid": test_uuid,
            "historyId": f"favicon::{site_id}",
            "links": links,
            "labels": [
                {"name": "suite", "value": "Favicon checks"},
                {"name": "package", "value": str(item["provider"])},
                {"name": "feature", "value": "Landing favicon"},
                {"name": "tag", "value": "enabled" if item["enabled"] else "disabled"},
            ],
            "parameters": [
                {"name": "landing_url", "value": base_url},
                {"name": "favicon_url", "value": str(favicon_url or "not found")},
                {"name": "landing_response_url", "value": str(item.get("landing_response_url") or "not available")},
                {"name": "landing_http_status", "value": str(item.get("landing_http_status") or "not available")},
                {"name": "landing_attempts", "value": str(item.get("landing_attempts", 0))},
                {
                    "name": "detected_favicon_links",
                    "value": ", ".join(str(link) for link in item.get("detected_favicon_links", [])) or "none",
                },
                {
                    "name": "detected_favicon_rel_values",
                    "value": ", ".join(str(rel) for rel in item.get("detected_favicon_rel_values", [])) or "none",
                },
                {"name": "landing_html_sha256", "value": str(item.get("landing_html_sha256") or "not available")},
                {"name": "landing_head_preview", "value": str(item.get("landing_head_preview") or "not available")},
            ],
            "steps": [
                {
                    "name": f"Landing URL: {base_url}",
                    "status": "passed",
                    "start": now_ms,
                    "stop": now_ms,
                },
                {
                    "name": f"Favicon URL: {favicon_url or 'not found'}",
                    "status": status,
                    "statusDetails": {"message": str(reason)} if reason else {},
                    "start": now_ms,
                    "stop": int(time.time() * 1000),
                },
            ],
        }
        (output_dir / f"{test_uuid}-result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="favicon_report.json")
    parser.add_argument("--allure-results", default="allure-results")
    args = parser.parse_args()

    session = requests.Session()
    results = [_check_favicon(session, site) for site in _site_inventory()]
    failed = [item for item in results if item["status"] != "passed"]

    Path(args.report).write_text(
        json.dumps(
            {
                "checked": len(results),
                "passed": len(results) - len(failed),
                "failed": len(failed),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_allure_results(results, args.allure_results)

    if failed:
        lines = ["🚨 Favicon check: проблемы на лендингах"]
        for item in failed:
            lines.append(f"- {item['site_id']}: {item['reason']}")
        message = "\n".join(lines)
        print(message)
        send_telegram_alert(message, alert_type="favicon")
        return 1

    print(f"✅ Favicon check: {len(results)} sites passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
