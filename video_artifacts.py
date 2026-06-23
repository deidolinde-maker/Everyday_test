from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

import allure

VIDEO_ROOT = Path(tempfile.gettempdir()) / "everyday_test_playwright_videos"
VIDEO_ATTACHMENT_TYPE = getattr(allure.attachment_type, "WEBM", "video/webm")


def _slugify(value: str, limit: int = 80) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return slug[:limit] or "test"


def build_recording_dir(test_id: str, suite_name: str) -> Path:
    digest = hashlib.sha1(test_id.encode("utf-8", "ignore")).hexdigest()[:10]
    path = VIDEO_ROOT / f"{suite_name}_{_slugify(test_id)}_{digest}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def record_video_size_for_profile(execution_profile: str | None) -> dict[str, int]:
    profile = (execution_profile or "").strip().lower()
    if profile.startswith("mobile"):
        return {"width": 360, "height": 640}
    return {"width": 640, "height": 360}


def _video_path(page) -> Path | None:
    video = getattr(page, "video", None)
    if video is None:
        return None

    for _ in range(10):
        try:
            raw_path = video.path()
        except Exception:
            time.sleep(0.2)
            continue

        if raw_path:
            path = Path(raw_path)
            if path.exists():
                return path

        time.sleep(0.2)

    return None


def attach_or_cleanup_videos(pages: Sequence, *, attach: bool, prefix: str) -> int:
    handled = 0
    for index, page in enumerate(pages, start=1):
        path = _video_path(page)
        if path is None:
            continue

        try:
            if attach:
                attachment_name = prefix if index == 1 else f"{prefix}_{index}"
                allure.attach(
                    path.read_bytes(),
                    name=attachment_name,
                    attachment_type=VIDEO_ATTACHMENT_TYPE,
                )
            handled += 1
        except Exception as exc:
            print(f"[VIDEO] Failed to attach {path.name}: {exc}")
        finally:
            try:
                path.unlink()
            except Exception:
                pass

    return handled


def cleanup_recording_dir(recording_dir: Path | str) -> None:
    shutil.rmtree(str(recording_dir), ignore_errors=True)
