from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .database import DATA_DIR

UPLOADS = DATA_DIR / "uploads"
_FFMPEG: Optional[str] = None
_FFMPEG_READY = False


def _ffmpeg_bin() -> Optional[str]:
    global _FFMPEG, _FFMPEG_READY
    if _FFMPEG_READY:
        return _FFMPEG
    _FFMPEG_READY = True
    found = shutil.which("ffmpeg")
    if found:
        _FFMPEG = found
        return _FFMPEG
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        _FFMPEG = get_ffmpeg_exe()
    except Exception:
        _FFMPEG = None
    return _FFMPEG


def local_upload_path(url: str) -> Optional[Path]:
    if not url or "/media/uploads/" not in url:
        return None
    name = Path(url.split("?")[0]).name
    if not name or name in {".", ".."}:
        return None
    path = (UPLOADS / name).resolve()
    try:
        path.relative_to(UPLOADS.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def extract_video_poster(media_url: str) -> Optional[str]:
    """One fast JPEG frame (~1s in). Used only when the client did not send a poster."""
    src = local_upload_path(media_url)
    ffmpeg = _ffmpeg_bin()
    if not src or not ffmpeg:
        return None

    UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS / f"poster_{uuid4().hex[:10]}.jpg"
    kwargs: dict = {"capture_output": True, "timeout": 8}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                "1",
                "-i",
                str(src),
                "-an",
                "-frames:v",
                "1",
                "-vf",
                "scale=640:-2",
                "-q:v",
                "6",
                str(dest),
            ],
            **kwargs,
        )
    except (subprocess.TimeoutExpired, OSError):
        if dest.exists():
            dest.unlink(missing_ok=True)
        return None

    if result.returncode == 0 and dest.is_file() and dest.stat().st_size > 800:
        return f"/media/uploads/{dest.name}"
    if dest.exists():
        dest.unlink(missing_ok=True)
    return None
