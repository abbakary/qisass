from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .database import DATA_DIR

UPLOADS = DATA_DIR / "uploads"
_FFMPEG: Optional[str] = None
_FFMPEG_READY = False

PALETTES = (
    (30, 132, 119),
    (201, 162, 39),
    (21, 102, 92),
    (59, 87, 68),
    (138, 110, 25),
    (46, 90, 76),
)


def write_fallback_poster(order: int = 1) -> str:
    """Solid-color PNG so every episode has a cover even without ffmpeg."""
    UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS / f"poster_{uuid4().hex[:10]}.png"
    dest.write_bytes(_solid_png(320, 180, PALETTES[max(0, order - 1) % len(PALETTES)]))
    return f"/media/uploads/{dest.name}"


def _solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    row = bytes(rgb) * width
    raw = b"".join(b"\x00" + row for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _ffmpeg_bin() -> Optional[str]:
    global _FFMPEG, _FFMPEG_READY
    if _FFMPEG_READY:
        return _FFMPEG
    _FFMPEG_READY = True
    # System ffmpeg only. imageio-ffmpeg downloads a large binary on first use
    # and made even tiny uploads hang for tens of seconds.
    _FFMPEG = shutil.which("ffmpeg")
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
    kwargs: dict = {"capture_output": True, "timeout": 2}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-noaccurate_seek",
                "-ss",
                "0.2",
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
