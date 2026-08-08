"""Generate WebVTT / SRT transcripts from episode sentences.

Apple Podcasts displays transcripts linked via the Podcasting 2.0
``<podcast:transcript>`` tag. Each cue carries the English line and its
Chinese translation so learners see both while listening.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .audio_utils import format_srt_time, format_vtt_time, probe_duration
from .config import AppConfig
from .models import Episode

logger = logging.getLogger(__name__)

# Generous fallback for the last cue's end when duration is unknown.
LAST_CUE_TAIL_SECONDS = 8.0


def _cue_ends(sentences, duration: float) -> list[float]:
    """End time for each sentence: next sentence's start, last -> duration."""
    ends: list[float] = []
    n = len(sentences)
    for i in range(n):
        if i + 1 < n:
            ends.append(float(sentences[i + 1].start))
        else:
            last_start = float(sentences[i].start)
            if duration > last_start:
                ends.append(duration)
            else:
                ends.append(last_start + LAST_CUE_TAIL_SECONDS)
    return ends


def generate_vtt(episode: Episode, duration: float = 0.0) -> str:
    """Return bilingual WebVTT transcript text (English + Chinese)."""
    lines = ["WEBVTT", ""]
    ends = _cue_ends(episode.sentences, duration)
    for i, s in enumerate(episode.sentences):
        lines.append(f"{format_vtt_time(s.start)} --> {format_vtt_time(ends[i])}")
        lines.append(s.en)
        if s.zh:
            lines.append(s.zh)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate_vtt_en(episode: Episode, duration: float = 0.0) -> str:
    """Return English-only WebVTT transcript for Apple Podcasts.

    Apple Podcasts transcript does not support Chinese, so this variant
    strips the Chinese translation line.
    """
    lines = ["WEBVTT", ""]
    ends = _cue_ends(episode.sentences, duration)
    for i, s in enumerate(episode.sentences):
        lines.append(f"{format_vtt_time(s.start)} --> {format_vtt_time(ends[i])}")
        lines.append(s.en)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate_srt(episode: Episode, duration: float = 0.0) -> str:
    """Return SRT transcript text for an episode."""
    lines: list[str] = []
    ends = _cue_ends(episode.sentences, duration)
    for i, s in enumerate(episode.sentences):
        lines.append(str(i + 1))
        lines.append(f"{format_srt_time(s.start)} --> {format_srt_time(ends[i])}")
        lines.append(s.en)
        if s.zh:
            lines.append(s.zh)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


class TranscriptGenerator:
    """Writes VTT and SRT transcript files for episodes with sentences."""

    def __init__(self, config: AppConfig):
        self._config = config

    def generate_all(self, episodes: list[Episode]) -> int:
        """Write transcript files for every episode that has sentences.

        Returns the number of transcripts written.
        """
        out_dir = self._config.docs_dir / "transcripts"
        out_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for ep in episodes:
            if not ep.sentences:
                continue
            audio_path = self._config.docs_dir / ep.audio_file
            duration = probe_duration(audio_path, ep.audio_size)
            (out_dir / f"{ep.slug}.vtt").write_text(
                generate_vtt(ep, duration), encoding="utf-8"
            )
            (out_dir / f"{ep.slug}.en.vtt").write_text(
                generate_vtt_en(ep, duration), encoding="utf-8"
            )
            (out_dir / f"{ep.slug}.srt").write_text(
                generate_srt(ep, duration), encoding="utf-8"
            )
            count += 1
        if count:
            logger.info("[TRANSCRIPT] Wrote %d VTT/SRT transcripts.", count)
        return count
