"""HTTP smoke-check for favicon links on all configured landing pages."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from config.providers import PROVIDER_MODULES
from test_universal2 import send_telegram_alert


USER_AGENT = "Everyday_test/favicon-check"
LANDING_TIMEOUT_SECONDS = 20
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
    }

    try:
        landing = session.get(
            base_url,
            headers={"User-Agent": USER_AGENT},
            timeout=LANDING_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        result["reason"] = f"landing_request_failed: {exc.__class__.__name__}"
        return result

    if landing.status_code != 200:
        result["reason"] = f"landing_http_{landing.status_code}"
        return result

    parser = FaviconLinkParser()
    try:
        parser.feed(landing.text)
    except Exception as exc:
        result["reason"] = f"html_parse_failed: {exc.__class__.__name__}"
        return result

    if not parser.links:
        result["reason"] = "favicon_link_missing_in_head"
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="favicon_report.json")
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
