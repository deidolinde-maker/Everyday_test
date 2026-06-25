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


def video_path(video_obj) -> Path | None:
    if video_obj is None:
        return None

    for _ in range(10):
        try:
            raw_path = video_obj.path()
        except Exception:
            time.sleep(0.2)
            continue

        if raw_path:
            path = Path(raw_path)
            if path.exists():
                return path

        time.sleep(0.2)

    return None


def collect_video_objects(pages: Sequence) -> list:
    seen_video_ids = set()
    video_objects = []
    for page in pages:
        video_obj = getattr(page, "video", None)
        if video_obj is None:
            continue
        video_id = id(video_obj)
        if video_id in seen_video_ids:
            continue
        seen_video_ids.add(video_id)
        video_objects.append(video_obj)
    return video_objects


def attach_or_cleanup_video_objects(video_objects: Sequence, *, attach: bool, prefix: str) -> int:
    handled = 0
    for index, video_obj in enumerate(video_objects, start=1):
        path = video_path(video_obj)
        if path is None:
            continue

        try:
            if attach:
                if path.exists() and path.stat().st_size > 0:
                    attachment_name = prefix if index == 1 else f"{prefix}_{index}"
                    allure.attach.file(
                        str(path),
                        name=attachment_name,
                        attachment_type=VIDEO_ATTACHMENT_TYPE,
                    )
                    print(f"[VIDEO] Attached: {path}")
                else:
                    print(f"[VIDEO] File is missing or empty: {path}")
                    continue
            handled += 1
        except Exception as exc:
            print(f"[VIDEO] Failed to attach {path.name}: {exc}")
        finally:
            try:
                path.unlink()
            except Exception:
                pass

    if attach and handled == 0:
        print("[VIDEO] No finalized video files were found for failed test")

    return handled


def attach_or_cleanup_videos(pages: Sequence, *, attach: bool, prefix: str) -> int:
    return attach_or_cleanup_video_objects(
        collect_video_objects(pages),
        attach=attach,
        prefix=prefix,
    )


def cleanup_recording_dir(recording_dir: Path | str) -> None:
    shutil.rmtree(str(recording_dir), ignore_errors=True)
