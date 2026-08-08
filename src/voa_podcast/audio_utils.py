"""Shared audio helpers: duration probing and timestamp formatting."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def probe_duration(audio_path: Path, file_size: int = 0) -> float:
    """Return audio duration in seconds.

    Uses ffprobe when available; falls back to a 64 kbps CBR estimate (the
    VOA Special English encoding) based on file size.
    """
    if audio_path.exists():
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            try:
                out = subprocess.run(
                    [ffprobe, "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
                    capture_output=True, text=True, timeout=15,
                )
                if out.returncode == 0 and out.stdout.strip():
                    return float(out.stdout.strip())
            except (subprocess.SubprocessError, ValueError) as exc:
                logger.warning("[AUDIO] ffprobe failed: %s", exc)
    # Fallback: VOA Special English MP3s are ~64 kbps CBR.
    return round(file_size * 8 / 64000, 0) if file_size else 0.0


def format_duration(seconds: float) -> str:
    """Format seconds as ``HH:MM:SS`` (or ``MM:SS`` when under an hour)."""
    if seconds <= 0:
        return ""
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_vtt_time(seconds: float) -> str:
    """Format seconds as WebVTT timestamp ``HH:MM:SS.mmm``."""
    if seconds < 0:
        seconds = 0.0
    ms = int(round((seconds - int(seconds)) * 1000))
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp ``HH:MM:SS,mmm`` (comma decimal)."""
    return format_vtt_time(seconds).replace(".", ",")
